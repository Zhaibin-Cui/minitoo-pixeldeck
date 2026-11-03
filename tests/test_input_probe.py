import io
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image
from pixeldeck.config import DeviceConfig
from pixeldeck.driver import MiniToo
from pixeldeck.instance import InstanceLock
from pixeldeck.experimental.input_probe import BoundedJsonLog, MarkerInput, PacketTap, _marker_lines, run_probe
from pixeldeck.protocol import READY, DONE, packet


class ProbeSocket:
    def __init__(self):
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = False

    def settimeout(self, value):
        pass

    def connect(self, address):
        self.address = address

    def recv(self, size):
        value = self.incoming.get()
        if isinstance(value, Exception):
            raise value
        return value

    def sendall(self, raw):
        self.sent.append(raw)
        if raw[4] == 0:
            self.incoming.put(packet(4, b"\xf7\x55\x00") + READY)
        else:
            self.incoming.put(DONE)

    def shutdown(self, how):
        self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.incoming.put(b"")


class InputProbeTests(unittest.TestCase):
    def config(self):
        return DeviceConfig(address="AA:BB:CC:DD:EE:FF", chunk_delay_ms=0, timeout=.2)

    def test_tap_sees_heartbeats_before_filter_and_transactions_still_work(self):
        fake = ProbeSocket()
        tap = PacketTap()
        with MiniToo(self.config(), socket_factory=lambda: fake, packet_tap=tap) as device:
            report = device.show(Image.new("RGB", (160, 128)))
            self.assertEqual(report["retransmissions"], 0)
            self.assertEqual(tap.snapshot()["packet_classes"]["response:F7"], 1)
            self.assertEqual(len(device._messages), 0)
        kinds = []
        while (event := tap.get()) is not None:
            kinds.append(event.kind)
        self.assertIn("packet", kinds)
        self.assertIn("rx_bytes", kinds)
        self.assertFalse(device._reader.is_alive())

    def test_raw_unframed_bytes_are_kept_before_decoder(self):
        fake = ProbeSocket()
        tap = PacketTap()
        with MiniToo(self.config(), socket_factory=lambda: fake, packet_tap=tap):
            fake.incoming.put(b"unframed joystick candidate")
            event = tap.get(timeout=1)
            self.assertEqual(event.kind, "rx_bytes")
            self.assertEqual(event.data, b"unframed joystick candidate")
            self.assertEqual(tap.snapshot()["packet_classes"], {})
        self.assertEqual(fake.sent, [])

    def test_shared_bound_keeps_newest_and_counts_all_decoded_packets(self):
        tap = PacketTap(2)
        raw = packet(4, b"\xf7\x55\x00")
        tap.put(raw)
        tap.put_bytes(b"raw")
        tap.mark("UP")
        tap.put(raw)
        self.assertEqual(tap.snapshot()["pending"], 2)
        self.assertEqual(tap.snapshot()["dropped"], {"packet": 1, "rx_bytes": 1})
        self.assertEqual(tap.snapshot()["packet_classes"], {"response:F7": 2})
        self.assertEqual(tap.get().kind, "marker")
        self.assertEqual(tap.get().kind, "packet")
        tap.close()
        self.assertFalse(tap.mark("DOWN"))
        self.assertIsNone(tap.get())

    def test_close_wakes_a_blocked_listener(self):
        tap = PacketTap()
        done = threading.Event()
        observed = []
        thread = threading.Thread(target=lambda: (observed.append(tap.get()), done.set()))
        thread.start()
        tap.close()
        self.assertTrue(done.wait(1))
        thread.join(1)
        self.assertEqual(observed, [None])

    def test_log_budget_reserves_summary_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "probe.jsonl"
            log = BoundedJsonLog(output, 1024)
            for _ in range(100):
                log.write({"kind": "rx_bytes", "hex": "ff" * 100})
            self.assertGreater(log.skipped, 0)
            self.assertTrue(log.write({"kind": "summary", "skipped": log.skipped}, final=True))
            log.close()
            self.assertLessEqual(output.stat().st_size, 1024)
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(records[-1]["kind"], "summary")
            with self.assertRaises(FileExistsError):
                BoundedJsonLog(output)

    def test_marker_parser_is_bounded_and_eof_is_normal(self):
        data = "mark UP\nmark DOWN\n" + "mark " + "x"*1000 + "\nmark BACK\nignore\n"
        self.assertEqual(list(_marker_lines(io.StringIO(data))), ["UP", "DOWN", "BACK"])

    def test_receive_only_probe_closes_at_deadline_and_writes_private_log(self):
        fake = ProbeSocket()
        heartbeat = packet(4, b"\xf7\x55\x00")
        fake.incoming.put(heartbeat)
        status = []
        with tempfile.TemporaryDirectory() as folder, patch("pixeldeck.experimental.input_probe.home", return_value=Path(folder)):
            summary = run_probe(self.config(), .05, socket_factory=lambda: fake, on_status=status.append)
            logs = list((Path(folder)/"probes").glob("*.jsonl"))
            self.assertEqual(len(logs), 1)
            rows = [json.loads(line) for line in logs[0].read_text().splitlines()]
            self.assertEqual(rows[0]["kind"], "session")
            self.assertEqual(rows[-1]["kind"], "summary")
            self.assertEqual(summary["packet_classes"], {"response:F7": 1})
            self.assertEqual(summary["reason"], "duration")
            self.assertEqual([item["event"] for item in status], ["ready", "end"])
            self.assertEqual(fake.sent, [])
            self.assertTrue(fake.closed)

    def test_channel_ten_keeps_unknown_framing_and_disables_transactions(self):
        fake = ProbeSocket()
        tap = PacketTap()
        with MiniToo(self.config(), socket_factory=lambda: fake, packet_tap=tap,
                     channel=10, decode_packets=False) as device:
            fake.incoming.put(b"\x01\x00\x00unknown-format")
            self.assertEqual(tap.get(timeout=1).kind, "rx_bytes")
            fake.incoming.put(b"second observation")
            self.assertEqual(tap.get(timeout=1).data, b"second observation")
            self.assertTrue(device.healthy)
            with self.assertRaises(RuntimeError):
                device.brightness(50)
            self.assertEqual(fake.sent, [])
            self.assertEqual(fake.address[1], 10)

    def test_marker_helper_eof_does_not_close_packet_tap(self):
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stream:
            stream.write("mark UP\nmark DOWN\nmark BACK\n")
            stream.seek(0)
            tap = PacketTap()
            markers = MarkerInput(stream, tap)
            try:
                self.assertEqual([tap.get(timeout=3).data for _ in range(3)], ["UP", "DOWN", "BACK"])
                markers.process.wait(timeout=3)
                self.assertFalse(tap.snapshot()["closed"])
            finally:
                markers.close()
            self.assertFalse(markers.thread.is_alive())

    def test_stdin_stop_ends_early_and_keeps_queued_observations(self):
        fake = ProbeSocket()
        fake.incoming.put(packet(4, b"\xf7\x55\x00"))
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "r", encoding="utf-8") as stream, os.fdopen(write_fd, "w", encoding="utf-8") as producer:
            def status(event):
                if event["event"] == "ready":
                    producer.write("mark UP\nmark BACK\nstop\n")
                    producer.flush()
            with tempfile.TemporaryDirectory() as folder, patch("pixeldeck.experimental.input_probe.home", return_value=Path(folder)):
                started = time.monotonic()
                summary = run_probe(self.config(), 30, socket_factory=lambda: fake, stdin=stream, on_status=status)
                self.assertLess(time.monotonic()-started, 10)
                self.assertEqual(summary["reason"], "stopped")
                self.assertEqual(summary["pending"], 0)
                rows = [json.loads(line) for line in next((Path(folder)/"probes").glob("*.jsonl")).read_text().splitlines()]
                self.assertEqual([row["label"] for row in rows if row["kind"] == "marker"], ["UP", "BACK"])
                self.assertTrue(any(row["kind"] == "packet" for row in rows))
                self.assertEqual(rows[-1]["reason"], "stopped")
                self.assertEqual(fake.sent, [])
                self.assertTrue(fake.closed)

    def test_marker_close_failure_still_releases_log_and_instance_lock(self):
        fake = ProbeSocket()
        logs = []
        def log_factory(*args):
            log = BoundedJsonLog(*args)
            logs.append(log)
            return log
        with tempfile.TemporaryDirectory() as folder, patch("pixeldeck.experimental.input_probe.home", return_value=Path(folder)):
            with patch("pixeldeck.experimental.input_probe.BoundedJsonLog", side_effect=log_factory), \
                 patch("pixeldeck.experimental.input_probe.MarkerInput") as marker_class:
                marker_class.return_value.close.side_effect = RuntimeError("Marker reader did not release its pipe")
                with self.assertRaisesRegex(RuntimeError, "Marker reader"):
                    run_probe(self.config(), .02, socket_factory=lambda: fake, stdin=io.StringIO(), on_status=lambda _: None)
                marker_class.return_value.close.assert_called_once()
            self.assertTrue(logs[0].file.closed)
            self.assertTrue(fake.closed)
            lock = InstanceLock(Path(folder)/"instance.lock")
            lock.close()

    def test_receive_failure_records_type_without_exception_details(self):
        secret = "PRIVATE_ENDPOINT_AND_LOCAL_PATH"
        cases = [(OSError(secret), "OSError"), (b"\x01\x00\x00", "ValueError")]
        for received, expected in cases:
            with self.subTest(error=expected), tempfile.TemporaryDirectory() as folder, \
                 patch("pixeldeck.experimental.input_probe.home", return_value=Path(folder)):
                fake = ProbeSocket()
                fake.incoming.put(received)
                status = []
                summary = run_probe(self.config(), 1, socket_factory=lambda: fake, on_status=status.append)
                self.assertEqual(summary["reason"], "disconnected")
                self.assertEqual(summary["receive_error_type"], expected)
                text = next((Path(folder)/"probes").glob("*.jsonl")).read_text()
                self.assertNotIn(secret, text)
                self.assertNotIn(secret, json.dumps(status))
                self.assertEqual(json.loads(text.splitlines()[-1])["receive_error_type"], expected)
                if isinstance(received, bytes):
                    self.assertIn(received.hex(), text)


if __name__ == "__main__":
    unittest.main()
