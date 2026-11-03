"""Blocking RFCOMM transactions plus a dedicated, continuously draining reader."""
from collections import deque
import os
import socket
import threading
import time
from .config import DeviceConfig
from .protocol import Decoder, HEARTBEAT_PREFIX, brightness_packet, jpeg_clip, response, upload

class MiniToo:
    """Context-managed MiniToo link. Inject socket_factory for another platform/test.

    Public methods serialize complete transactions. Receives never run on the sender.
    Windows is the only bundled hardware backend; the protocol is platform-neutral.
    """
    def __init__(self, config: DeviceConfig, socket_factory=None, on_disconnect=None, packet_tap=None,
                 channel=1, decode_packets=True):
        if not config.address:
            raise ValueError("Configure a paired device address before connecting")
        if type(channel) is not int or not 1 <= channel <= 30:
            raise ValueError("RFCOMM channel must be 1..30")
        self.config = config
        self.trace = deque(maxlen=32)
        self._decoder = Decoder()
        self._condition = threading.Condition()
        self._messages = deque()
        self._lock = threading.Lock()
        self._failure = None
        self._closed = False
        self._active = False
        self._on_disconnect = on_disconnect
        self._packet_tap = packet_tap
        self._decode_packets = decode_packets
        if socket_factory is None:
            if os.name != "nt":
                raise RuntimeError("Hardware backend currently supports Windows; use preview or inject a socket factory")
            import winreg
            key_path = "SYSTEM\\CurrentControlSet\\Services\\BTHPORT\\Parameters\\Devices\\" + config.address.replace(":", "").lower()
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                name, _ = winreg.QueryValueEx(key, "Name")
            if isinstance(name, bytes):
                name = name.split(b"\0", 1)[0].decode("utf-8")
            if str(name).strip().casefold() != config.name.casefold():
                raise ValueError("Paired device name does not match configuration")
            socket_factory = lambda: socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self._socket = socket_factory()
        try:
            self._socket.settimeout(config.timeout)
            self._socket.connect((config.address, channel))
            self._socket.settimeout(None)
        except Exception:
            self._socket.close()
            if self._packet_tap is not None:
                self._packet_tap.close()
            raise
        self._reader = threading.Thread(target=self._read, name="pixeldeck-rx", daemon=True)
        self._reader.start()

    @property
    def healthy(self):
        return not self._closed and self._failure is None

    def _read(self):
        try:
            while not self._closed:
                data = self._socket.recv(4096)
                if not data:
                    raise ConnectionError("Device disconnected")
                if self._packet_tap is not None:
                    self._packet_tap.put_bytes(data)
                if not self._decode_packets:
                    continue
                for raw in self._decoder.feed(data):
                    if self._packet_tap is not None:
                        self._packet_tap.put(raw)
                    self.trace.append(raw.hex())
                    if raw[3:6] == HEARTBEAT_PREFIX:
                        continue
                    with self._condition:
                        if self._active:
                            if len(self._messages) >= 64:
                                raise RuntimeError("Response queue limit exceeded")
                            self._messages.append(raw)
                            self._condition.notify()
        except Exception as exc:
            with self._condition:
                self._failure = exc
                self._condition.notify_all()
            if not self._closed and self._on_disconnect:
                self._on_disconnect(exc)
        finally:
            if self._packet_tap is not None:
                self._packet_tap.close()

    def _receive(self, deadline):
        with self._condition:
            self._condition.wait_for(lambda: self._messages or self._failure or self._closed,
                                     timeout=max(0, deadline-time.monotonic()))
            if self._messages:
                return self._messages.popleft()
            if self._failure:
                raise self._failure
            if self._closed:
                raise ConnectionError("Connection closed")
            raise TimeoutError("Device acknowledgment timed out")

    def _transaction(self, operation, budget):
        if not self._decode_packets:
            raise RuntimeError("Transactions are disabled on a receive-only raw connection")
        with self._lock:
            with self._condition:
                if not self.healthy:
                    raise ConnectionError("Connection is not healthy") from self._failure
                self._messages.clear()
                self._active = True
            deadline = threading.Timer(budget, self.close)
            deadline.daemon = True
            deadline.start()
            try:
                return operation()
            finally:
                deadline.cancel()
                with self._condition:
                    self._active = False
                    self._messages.clear()

    def show(self, image):
        return self.show_clip([image], period_ms=1000)

    def show_clip(self, images, period_ms=250):
        job = upload(jpeg_clip(images, period_ms, self.config.quality))
        def transfer():
            start = time.monotonic()
            self._socket.sendall(job.announce)
            end = start + self.config.timeout
            while True:
                op, body = response(self._receive(end))
                if op == 0x8B and body[:2] == b"\x00\x01":
                    break
            ready_at = time.monotonic()
            for raw in job.chunks:
                self._socket.sendall(raw)
                if self.config.chunk_delay_ms:
                    time.sleep(self.config.chunk_delay_ms / 1000)  # Only TX pacing.
            sent_at = time.monotonic()
            end = sent_at + self.config.timeout
            retries = {}
            while True:
                op, body = response(self._receive(end))
                if op == 0xBD and body[:2] == b"\x13\x01":
                    completed_at = time.monotonic()
                    return {"bytes": job.size, "chunks": len(job.chunks),
                            "retransmissions": sum(retries.values()),
                            "transfer_ms": round((completed_at-start)*1000, 2),
                            "announce_ms": round((ready_at-start)*1000, 2),
                            "send_ms": round((sent_at-ready_at)*1000, 2),
                            "completion_ms": round((completed_at-sent_at)*1000, 2)}
                if op == 0x8B and len(body) >= 3 and body[0] == 1:
                    index = int.from_bytes(body[1:3], "little")
                    if index >= len(job.chunks):
                        raise ValueError("Device requested an invalid chunk")
                    retries[index] = retries.get(index, 0) + 1
                    if retries[index] > 3:
                        raise RuntimeError("Retransmission limit reached")
                    self._socket.sendall(job.chunks[index])
        return self._transaction(transfer, 2*self.config.timeout + len(job.chunks)*self.config.chunk_delay_ms/1000 + 2)

    def brightness(self, level):
        """Experimental: documented upstream, not yet verified on this test device."""
        raw = brightness_packet(level)
        def change():
            self._socket.sendall(raw)
            deadline = time.monotonic() + self.config.timeout
            while True:
                op, body = response(self._receive(deadline))
                if op == 0x32 and body and body[0] == level:
                    return level
        return self._transaction(change, self.config.timeout + 1)

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._condition.notify_all()
        if self._packet_tap is not None:
            self._packet_tap.close()
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._socket.close()
        if threading.current_thread() is not self._reader:
            self._reader.join(timeout=1)

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
