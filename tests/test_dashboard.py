import unittest

from pixeldeck.demos.dashboard import Dashboard
from pixeldeck.protocol import jpeg_clip


def button(key):
    return {"type": "button", "button": key}


class DashboardNavigationTests(unittest.TestCase):
    def test_overview_wraps_six_tiles_and_only_exit_activation_quits(self):
        demo = Dashboard()
        self.assertTrue(demo.captures_navigation)
        self.assertIsNone(demo.handle(button("previous"), 0))
        self.assertEqual(demo.selected, 5)
        self.assertFalse(demo.detail)
        self.assertEqual(demo.handle(button("activate"), 0), "exit")
        demo.handle(button("next"), 0)
        self.assertEqual(demo.selected, 0)
        for index in range(5):
            demo.selected = index
            self.assertIsNone(demo.handle(button("activate"), 0))
            self.assertTrue(demo.detail)
            self.assertIsNone(demo.handle(button("activate"), 0))
            self.assertFalse(demo.detail)

    def test_detail_navigation_never_selects_exit(self):
        demo = Dashboard()
        demo.handle(button("activate"), 0)
        demo.handle(button("previous"), 0)
        self.assertEqual(demo.selected, 4)
        for _ in range(30):
            self.assertIsNone(demo.handle(button("next"), 0))
            self.assertLess(demo.selected, 5)
            self.assertTrue(demo.detail)

    def test_back_returns_overview_then_leaves_without_quitting(self):
        demo = Dashboard()
        demo.handle(button("activate"), 0)
        self.assertIsNone(demo.handle(button("back"), 0))
        self.assertFalse(demo.detail)
        self.assertEqual(demo.handle(button("back"), 0), "leave")
        self.assertIsNone(demo.handle(button("reset"), 0))
        self.assertFalse(demo.detail)


class DashboardMetricsTests(unittest.TestCase):
    def test_sample_timestamps_are_preserved_bounded_and_ordered(self):
        demo = Dashboard()
        for i in range(200):
            demo.handle({"type": "telemetry", "cpu": i % 100, "memory": 43, "sampled_at": i*2}, 10000)
        self.assertEqual(len(demo.cpu_history), 61)
        self.assertEqual(len(demo.memory_history), 61)
        self.assertEqual(demo.cpu_history[-1], (398, 99))
        demo.handle({"type": "telemetry", "cpu": 1, "memory": 2, "sampled_at": 300}, 10001)
        self.assertEqual(demo.cpu, 99)
        demo.handle({"type": "telemetry", "cpu": 3, "memory": 4, "sampled_at": 398}, 10001)
        self.assertEqual(len(demo.cpu_history), 61)
        self.assertEqual(demo.cpu_history[-1], (398, 3))

    def test_missing_and_bad_values_do_not_fabricate_data(self):
        demo = Dashboard()
        demo.handle({"type": "telemetry", "cpu": 12, "memory": 34}, 10)
        self.assertEqual(demo.cpu_history[-1], (10, 12))
        for extra in ({"cpu": 101}, {"memory": -1}, {"cpu": True},
                      {"sampled_at": float("nan")}, {"sampled_at": True}):
            event = dict(type="telemetry", cpu=15, memory=45, sampled_at=11)
            event.update(extra)
            with self.assertRaises(ValueError):
                demo.handle(event, 11)
        self.assertEqual(demo.cpu, 12)
        self.assertEqual(len(demo.cpu_history), 1)
        demo.handle({"type": "telemetry", "available": False}, 12)
        self.assertIsNone(demo.cpu)
        self.assertIsNone(demo.memory)
        self.assertEqual(demo.cpu_history[-1], (12, None))

    def test_sources_update_independently_on_any_selected_tile(self):
        demo = Dashboard()
        demo.selected = 5
        demo.handle({"type": "network", "available": True, "rx_bps": 1024, "tx_bps": 2048}, 0)
        demo.handle({"type": "storage", "volumes": [{"label": "SYSTEM", "total": 100, "free": 25}]}, 0)
        demo.handle({"type": "power", "available": True, "present": True, "percent": 67, "plugged": False}, 0)
        demo.handle({"type": "telemetry", "cpu": 33, "memory": 44}, 0)
        self.assertEqual(demo.selected, 5)
        self.assertEqual(demo.network.rx, 1024)
        self.assertEqual(demo.storage.volumes[0]["free"], 25)
        self.assertEqual(demo.power.percent, 67)
        self.assertEqual(demo.cpu, 33)
        self.assertEqual(demo.memory, 44)
        self.assertEqual(demo._storage_summary(), (75, 100, 25))
        self.assertIsNone(demo.next_delay(0))

    def test_cpu_and_memory_have_distinct_detail_data(self):
        demo = Dashboard()
        demo.handle({"type": "telemetry", "cpu": 12, "memory": 87}, 0)
        demo.detail = True
        cpu_picture = demo.render(0).tobytes()
        demo.selected = 1
        self.assertNotEqual(cpu_picture, demo.render(0).tobytes())
        self.assertEqual(demo.cpu_history[-1][1], 12)
        self.assertEqual(demo.memory_history[-1][1], 87)

    def test_external_metric_histories_and_volume_lists_are_bounded(self):
        demo = Dashboard()
        for i in range(200):
            demo.handle({"type": "network", "available": True, "rx_bps": i, "tx_bps": i}, i)
        demo.handle({"type": "storage", "volumes": [{"label": "DATA", "total": 100, "free": 30}]*30}, 0)
        self.assertEqual(len(demo.network.history), 61)
        self.assertEqual(len(demo.storage.volumes), 16)
        with self.assertRaises(ValueError):
            demo.handle({"type": "power", "present": True, "percent": 101}, 0)
        with self.assertRaises(ValueError):
            demo.handle({"type": "network", "rx_bps": -1}, 0)


class DashboardRenderingTests(unittest.TestCase):
    def test_every_tile_and_detail_fit_the_display_budget(self):
        demo = Dashboard()
        demo.handle({"type": "telemetry", "cpu": 100, "memory": 100}, 0)
        demo.handle({"type": "network", "available": True, "rx_bps": 2**30, "tx_bps": 2**28}, 0)
        demo.handle({"type": "storage", "volumes": [{"label": "SYSTEM", "total": 512*2**30, "free": 184*2**30}]}, 0)
        demo.handle({"type": "power", "present": True, "percent": 100, "plugged": True}, 0)
        for selected in range(6):
            demo.selected = selected
            for detail in ((False, True) if selected < 5 else (False,)):
                demo.detail = detail
                image = demo.render(10)
                self.assertEqual(image.size, (160, 128))
                self.assertEqual(image.mode, "RGB")
                self.assertLessEqual(len(jpeg_clip([image])), 16000)
                self.assertEqual(image.tobytes(), demo.render(10000).tobytes())

    def test_empty_details_render_without_zero_measurements(self):
        demo = Dashboard()
        self.assertIsNone(demo.cpu)
        self.assertIsNone(demo.memory)
        for selected in range(5):
            demo.selected = selected
            demo.detail = True
            self.assertEqual(demo.render(0).size, (160, 128))


if __name__ == "__main__":
    unittest.main()
