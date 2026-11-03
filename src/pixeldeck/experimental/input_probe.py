"""Receive-only RFCOMM observation; captured bytes are not verified button events.

Run with --seconds 180. During capture, enter `mark UP`, `mark DOWN`, or
`mark BACK` around physical operations. Markers describe the operator's action;
they do not label a packet as a recognized input. Enter `stop` to finish early.
No device command is sent.
"""
import argparse
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from ..config import DeviceConfig, home
from ..driver import MiniToo
from ..instance import InstanceLock

MAX_LOG_BYTES = 4 * 1024 * 1024
_STOP_CONTROL = "!STOP"  # Outside the allowed marker alphabet.


def packet_class(raw):
    if len(raw) >= 9 and raw[3] == 4 and raw[5] == 0x55:
        return f"response:{raw[4]:02X}"
    return f"opcode:{raw[3]:02X}" if len(raw) >= 4 else "short"


@dataclass(frozen=True)
class TapEvent:
    kind: str
    time_ns: int
    monotonic_ns: int
    data: bytes | str


class PacketTap:
    """Bounded shared mailbox. Producers copy data; only the consumer does I/O."""
    def __init__(self, capacity=128):
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError("Tap capacity must be 1..1024")
        self.capacity = capacity
        self._condition = threading.Condition()
        self._queue = deque()
        self._closed = False
        self._stop_requested = False
        self._observed = Counter()
        self._dropped = Counter()
        self._classes = Counter()
        self._received_bytes = 0

    def _put(self, kind, data):
        event = TapEvent(kind, time.time_ns(), time.monotonic_ns(), data)
        with self._condition:
            if self._closed:
                return False
            self._observed[kind] += 1
            if kind == "packet":
                self._classes[packet_class(data)] += 1
            elif kind == "rx_bytes":
                self._received_bytes += len(data)
            if len(self._queue) == self.capacity:
                self._dropped[self._queue.popleft().kind] += 1
            self._queue.append(event)
            self._condition.notify()
            return True

    def put(self, raw):
        """Observe one decoded packet before response/heartbeat filtering."""
        if not 1 <= len(raw) <= 65536:
            raise ValueError("Packet exceeds decoder bounds")
        return self._put("packet", bytes(raw))

    def put_bytes(self, raw):
        """Observe the original recv chunk, including non-framed bytes."""
        if not 1 <= len(raw) <= 65536:
            raise ValueError("Receive chunk exceeds decoder bounds")
        return self._put("rx_bytes", bytes(raw))

    def mark(self, label):
        if not isinstance(label, str) or not label.strip() or not re.fullmatch(r"[A-Za-z0-9 _./+\-]{1,48}", label):
            return False
        return self._put("marker", label.strip().upper())

    def get(self, timeout=None):
        with self._condition:
            self._condition.wait_for(lambda: self._queue or self._closed, timeout=timeout)
            return self._queue.popleft() if self._queue else None

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def request_stop(self):
        with self._condition:
            self._stop_requested = True
            self._closed = True
            self._condition.notify_all()

    def snapshot(self):
        with self._condition:
            return {"observed": dict(self._observed), "dropped": dict(self._dropped),
                    "packet_classes": dict(self._classes), "received_bytes": self._received_bytes,
                    "pending": len(self._queue), "capacity": self.capacity, "closed": self._closed,
                    "stop_requested": self._stop_requested}


class BoundedJsonLog:
    """Exclusive new file, fixed byte budget, with room reserved for a summary."""
    def __init__(self, output, max_bytes=MAX_LOG_BYTES):
        if type(max_bytes) is not int or not 1024 <= max_bytes <= MAX_LOG_BYTES:
            raise ValueError("Log budget must be 1 KiB..4 MiB")
        self.max_bytes = max_bytes
        self.reserve = min(65536, max_bytes // 2)
        self.bytes_written = 0
        self.skipped = 0
        self.records_written = 0
        self.file = open(output, "xb")

    def write(self, record, final=False):
        encoded = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        limit = self.max_bytes if final else self.max_bytes - self.reserve
        if self.bytes_written + len(encoded) > limit:
            self.skipped += 1
            return False
        self.file.write(encoded)
        self.file.flush()
        self.bytes_written += len(encoded)
        self.records_written += 1
        return True

    def close(self):
        self.file.close()


def _marker_lines(stream):
    """Bound input lines independently of the packet/log budgets."""
    while True:
        line = stream.readline(258)
        if not line:
            return
        if len(line) > 257:
            while line and not line.endswith("\n"):
                line = stream.readline(258)
            continue
        line = line.strip()
        if line == "stop":
            yield _STOP_CONTROL
            return
        if line[:5].casefold() == "mark ":
            label = line[5:].strip()
            if re.fullmatch(r"[A-Za-z0-9 _./+\-]{1,48}", label):
                yield label.upper()


def _forward_markers():
    for label in _marker_lines(sys.stdin):
        print(label, flush=True)


class MarkerInput:
    """A helper process makes a blocked console/pipe readline cancellable."""
    def __init__(self, stream, tap):
        self.tap = tap
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
        # A console input handle is valid only while the child shares that console.
        # Flags=0 inherits the existing console; it does not request a new window.
        creationflags = 0 if stream.isatty() else getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "pixeldeck.experimental.input_probe", "--marker-reader"],
            stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env,
            creationflags=creationflags)
        self.thread = threading.Thread(target=self._read, name="pixeldeck-probe-markers", daemon=True)
        self.thread.start()

    def _read(self):
        for line in self.process.stdout:
            if line.strip() == _STOP_CONTROL:
                self.tap.request_stop()
                return
            self.tap.mark(line.strip())

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise RuntimeError("Marker reader did not release its pipe")
        self.process.stdout.close()


def _record(event):
    result = {"kind": event.kind, "time_ns": event.time_ns, "monotonic_ns": event.monotonic_ns}
    if event.kind == "marker":
        result["label"] = event.data
    else:
        result.update(bytes=len(event.data), hex=event.data.hex())
        if event.kind == "packet":
            result["packet_class"] = packet_class(event.data)
    return result


def run_probe(config, duration=180, output=None, *, channel=1, raw_only=False, socket_factory=None, stdin=None,
              max_bytes=MAX_LOG_BYTES, on_status=None):
    """Connect and receive only; EOF on marker input never ends the capture.

    socket_factory is for offline simulation. The same runtime instance lock as
    the normal display host prevents simultaneous senders in that runtime.
    """
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 3600:
        raise ValueError("Capture duration must be greater than 0 and at most 3600 seconds")
    if type(channel) is not int or channel not in (1, 10):
        raise ValueError("Probe channel must be explicitly selected as 1 or 10")
    decode_packets = not (raw_only or channel == 10)
    runtime = home()
    runtime.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = Path(output) if output else runtime / "probes" / f"rfcomm-ch{channel}-{stamp}.jsonl"
    output = output.resolve()
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / "pyproject.toml").exists() and output.is_relative_to(checkout):
        raise ValueError("Probe logs must be outside the source checkout")
    output.parent.mkdir(parents=True, exist_ok=True)
    emit = on_status or (lambda event: print(json.dumps(event), flush=True))
    lock = InstanceLock(runtime / "instance.lock")
    tap = PacketTap()
    log = device = markers = None
    reason = "duration"
    receive_error_type = None
    def disconnected(exc):
        nonlocal receive_error_type
        name = type(exc).__name__
        receive_error_type = name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"
    try:
        log = BoundedJsonLog(output, max_bytes)
        device = MiniToo(config, socket_factory=socket_factory, packet_tap=tap,
                         channel=channel, decode_packets=decode_packets, on_disconnect=disconnected)
        if stdin is not None:
            markers = MarkerInput(stdin, tap)
        started = time.monotonic()
        log.write({"kind": "session", "time_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns(),
                   "receive_only": True, "seconds": duration, "log_limit_bytes": max_bytes,
                   "channel": channel, "decode_packets": decode_packets})
        emit({"event": "ready", "receive_only": True, "seconds": duration,
              "channel": channel, "decode_packets": decode_packets,
              "output": str(output), "markers": "mark UP / mark DOWN / mark BACK; stop to finish"})
        try:
            while True:
                if tap.snapshot()["stop_requested"]:
                    reason = "stopped"
                    break
                remaining = started + duration - time.monotonic()
                if remaining <= 0:
                    break
                event = tap.get(timeout=remaining)
                if event is None:
                    state = tap.snapshot()
                    reason = "stopped" if state["stop_requested"] else "disconnected" if state["closed"] else "duration"
                    break
                log.write(_record(event))
        except KeyboardInterrupt:
            reason = "interrupted"
        finally:
            device.close()
            if markers is not None:
                closing_markers, markers = markers, None
                closing_markers.close()
        # Producers are closed. Drain the finite remaining queue before summary.
        while (event := tap.get(timeout=0)) is not None:
            log.write(_record(event))
        if tap.snapshot()["stop_requested"]:
            reason = "stopped"
        summary = {"kind": "summary", "reason": reason, "channel": channel,
                   "receive_error_type": receive_error_type,
                   "duration_seconds": round(time.monotonic()-started, 3),
                   **tap.snapshot(), "log_records": log.records_written, "log_skipped": log.skipped}
        if not log.write(summary, final=True):
            raise RuntimeError("Capture summary exceeded its reserved log budget")
        emit({"event": "end", **summary})
        return summary
    finally:
        try:
            if device is not None:
                device.close()
        finally:
            tap.close()
            try:
                if markers is not None:
                    markers.close()
            finally:
                try:
                    if log is not None:
                        log.close()
                finally:
                    lock.close()


def main():
    if sys.argv[1:] == ["--marker-reader"]:
        _forward_markers()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--channel", type=int, choices=(1, 10), default=1)
    parser.add_argument("--raw-only", action="store_true", help="Bypass packet decoding (always used on channel 10)")
    args = parser.parse_args()
    run_probe(DeviceConfig.load(args.config), args.seconds, args.output, stdin=sys.stdin,
              channel=args.channel, raw_only=args.raw_only)


if __name__ == "__main__":
    main()
