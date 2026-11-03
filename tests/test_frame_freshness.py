import math
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from pixeldeck.engine import FramePump


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class FrameFreshnessTests(unittest.TestCase):
    def test_initial_connection_uses_latest_frame_and_its_submission_time(self):
        connecting = threading.Event()
        connected = threading.Event()
        acknowledged = threading.Event()
        seen, reports = [], []
        clock = Clock(10)

        class Sink:
            def show(self, image):
                seen.append(image.getpixel((0, 0)))
                clock.value = 45
                return {"transfer_ms": 5000}

            def close(self):
                connected.set()

        def factory():
            connecting.set()
            if not connected.wait(2):
                raise TimeoutError("Test did not release connection")
            return Sink()

        def status(event):
            if event["type"] == "frame.ack":
                reports.append(event)
                acknowledged.set()

        with patch("pixeldeck.engine.time", SimpleNamespace(monotonic=clock)):
            pump = FramePump(factory, status, retries=0)
            try:
                pump.submit(Image.new("RGB", (160, 128), "red"))
                self.assertTrue(connecting.wait(2))
                clock.value = 20
                pump.submit(Image.new("RGB", (160, 128), "green"))
                clock.value = 30
                pump.submit(Image.new("RGB", (160, 128), "blue"), received_at=28)
                clock.value = 40
                connected.set()
                self.assertTrue(acknowledged.wait(2))
            finally:
                connected.set()
                pump.close()

        self.assertEqual(seen, [(0, 0, 255)])
        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report["sequence"], 3)
        self.assertEqual(report["queue_ms"], 10000)
        self.assertEqual(report["frame_age_ms"], 15000)
        self.assertEqual(report["input_to_ack_ms"], 17000)

    def test_reconnection_does_not_replay_obsolete_frame(self):
        first_ack = threading.Event()
        reconnecting = threading.Event()
        reconnected = threading.Event()
        last_ack = threading.Event()
        seen, reports, sinks = [], [], []

        class Sink:
            healthy = True

            def show(self, image):
                seen.append(image.getpixel((0, 0)))
                return {"transfer_ms": 1}

            def close(self):
                self.healthy = False

        def factory():
            if sinks:
                reconnecting.set()
                if not reconnected.wait(2):
                    raise TimeoutError("Test did not release reconnection")
            sink = Sink()
            sinks.append(sink)
            return sink

        def status(event):
            if event["type"] == "frame.ack":
                reports.append(event)
                (first_ack if len(reports) == 1 else last_ack).set()

        pump = FramePump(factory, status, retries=0)
        try:
            pump.submit(Image.new("RGB", (160, 128), "red"))
            self.assertTrue(first_ack.wait(2))
            sinks[0].healthy = False
            pump.reconnect(ConnectionError("Simulated disconnect"))
            self.assertTrue(reconnecting.wait(2))
            pump.submit(Image.new("RGB", (160, 128), "green"))
            pump.submit(Image.new("RGB", (160, 128), "blue"))
            reconnected.set()
            self.assertTrue(last_ack.wait(2))
        finally:
            reconnected.set()
            pump.close()

        self.assertEqual(seen, [(255, 0, 0), (0, 0, 255)])
        self.assertEqual([event["sequence"] for event in reports], [1, 3])
        for event in reports:
            for field in ("queue_ms", "frame_age_ms"):
                self.assertTrue(math.isfinite(event[field]))
                self.assertGreaterEqual(event[field], 0)
            self.assertGreaterEqual(event["frame_age_ms"], event["queue_ms"])
            self.assertNotIn("input_to_ack_ms", event)


if __name__ == "__main__":
    unittest.main()
