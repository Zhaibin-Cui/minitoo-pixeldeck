import math
import unittest

from pixeldeck.demos.monitors import NetScope, VolumeVault, PowerCell, BuildBeacon
from pixeldeck.protocol import jpeg_clip


ACTIVATE = {"type": "button", "button": "activate"}


class NetScopeTests(unittest.TestCase):
    def test_history_is_bounded_and_hold_preserves_picture(self):
        demo = NetScope()
        for i in range(200):
            demo.handle({"type": "network", "rx_bps": i*1024, "tx_bps": i*64, "available": True}, i)
        self.assertEqual(len(demo.history), 61)
        demo.handle(ACTIVATE, 201)
        before = demo.render(201).tobytes()
        demo.handle({"type": "network", "rx_bps": 0, "tx_bps": 0, "available": True}, 202)
        self.assertEqual(demo.rx, 199*1024)
        self.assertEqual(before, demo.render(1000).tobytes())
        self.assertIsNone(demo.next_delay(1000))
        demo.handle(ACTIVATE, 1001)
        demo.handle({"type": "network", "rx_bps": 0, "tx_bps": 0, "available": True}, 1002)
        self.assertEqual(demo.rx, 0)

    def test_missing_rates_stay_missing_and_invalid_rates_are_rejected(self):
        demo = NetScope()
        demo.handle({"type": "network", "available": False}, 0)
        self.assertIsNone(demo.rx)
        for value in (-1, float("inf"), float("nan"), True):
            with self.assertRaises(ValueError):
                demo.handle({"type": "network", "rx_bps": value, "tx_bps": 0, "available": True}, 1)
        self.assertEqual(len(demo.history), 1)


class VolumeVaultTests(unittest.TestCase):
    def test_cycles_bounded_volume_list_and_hides_paths(self):
        demo = VolumeVault()
        demo.handle({"type": "storage", "volumes": [{"label": "/private/mount", "total": 100, "free": 25}]*25}, 0)
        self.assertEqual(len(demo.volumes), 16)
        self.assertEqual(demo.volumes[0]["label"], "VOLUME 01")
        for _ in range(17):
            demo.handle(ACTIVATE, 0)
        self.assertEqual(demo.selected, 1)
        self.assertIsNone(demo.next_delay(0))

    def test_invalid_volume_does_not_replace_state(self):
        demo = VolumeVault()
        demo.handle({"type": "storage", "volumes": [{"label": "SYSTEM", "total": 100, "free": 25}]}, 0)
        for total, free in ((100, 101), (-1, 0), (None, 0), (True, 0)):
            with self.assertRaises(ValueError):
                demo.handle({"type": "storage", "volumes": [{"label": "SYSTEM", "total": total, "free": free}]}, 1)
        self.assertEqual(demo.volumes[0]["free"], 25)
        demo.handle({"type": "storage", "volumes": []}, 2)
        demo.handle(ACTIVATE, 2)
        self.assertEqual(demo.selected, 0)


class PowerCellTests(unittest.TestCase):
    def test_no_battery_differs_from_unavailable_provider(self):
        demo = PowerCell()
        demo.handle({"type": "power", "available": False, "present": False}, 0)
        unavailable = demo.render(0).tobytes()
        demo.handle({"type": "power", "available": True, "present": False, "plugged": True}, 1)
        self.assertNotEqual(unavailable, demo.render(1).tobytes())
        self.assertIsNone(demo.percent)
        self.assertIsNone(demo.seconds_left)

    def test_detail_does_not_fabricate_estimates_and_validates_charge(self):
        demo = PowerCell()
        demo.handle({"type": "power", "present": True, "percent": 67, "plugged": False, "seconds_left": None}, 0)
        demo.handle(ACTIVATE, 1)
        self.assertTrue(demo.detail)
        self.assertIsNone(demo.seconds_left)
        self.assertIsNone(demo.next_delay(1))
        for value in (-1, 101, float("nan"), False):
            with self.assertRaises(ValueError):
                demo.handle({"type": "power", "present": True, "percent": value}, 2)
        self.assertEqual(demo.percent, 67)


class BuildBeaconTests(unittest.TestCase):
    def test_running_animation_stops_on_terminal_event(self):
        demo = BuildBeacon()
        event = {"type": "build", "project": "PIXEL ENGINE", "state": "running", "progress": 42, "step": "COMPILE SHADERS"}
        demo.handle(event, 1)
        self.assertAlmostEqual(demo.next_delay(1), 1/3)
        self.assertNotEqual(demo.render(1).tobytes(), demo.render(1.5).tobytes())
        demo.handle(dict(event, state="passed", progress=100), 2)
        self.assertIsNone(demo.next_delay(2))
        self.assertEqual(demo.render(2).tobytes(), demo.render(200).tobytes())

    def test_build_strings_are_bounded_and_bad_updates_are_atomic(self):
        demo = BuildBeacon()
        demo.handle({"type": "build", "project": "X"*1000, "step": "Y"*1000, "state": "running", "progress": None}, 0)
        self.assertEqual(len(demo.project), 20)
        self.assertEqual(len(demo.step), 40)
        demo.handle(ACTIVATE, 1)
        self.assertTrue(demo.detail)
        for event in ({"type": "build", "state": "execute"}, {"type": "build", "state": "failed", "progress": 101}):
            with self.assertRaises(ValueError):
                demo.handle(event, 2)
        self.assertEqual(demo.state, "running")
        self.assertIsNone(demo.progress)


class MonitorRenderTests(unittest.TestCase):
    def test_each_monitor_stays_within_frame_and_encoding_budget(self):
        for cls in (NetScope, VolumeVault, PowerCell, BuildBeacon):
            with self.subTest(demo=cls.key):
                demo = cls()
                image = demo.render(0)
                self.assertEqual(image.size, (160, 128))
                self.assertEqual(image.mode, "RGB")
                self.assertLessEqual(len(jpeg_clip([image])), 16000)
                demo.handle({"type": "button", "button": "reset"}, 0)
                self.assertEqual(image.tobytes(), demo.render(0).tobytes())


if __name__ == "__main__":
    unittest.main()
