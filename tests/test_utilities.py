import unittest

from pixeldeck.demos.utilities import Breathe, Clock, Pomodoro, Stopwatch
from pixeldeck.protocol import jpeg_clip


ACTIVATE = {"type": "button", "button": "activate"}
RESET = {"type": "button", "button": "reset"}


class UtilityTests(unittest.TestCase):
    def test_clock_uses_push_values_and_toggles_zone(self):
        clock = Clock()
        original = clock.render(1).tobytes()
        self.assertEqual(original, clock.render(999999).tobytes())
        self.assertIsNone(clock.next_delay(1))
        self.assertEqual(clock.sources, ("wallclock",))
        clock.handle({"type": "wallclock", "local": "2026-11-03T20:18:35+08:00", "utc": "2026-11-03T12:18:35+00:00"}, 1)
        local = clock.render(1).tobytes()
        self.assertNotEqual(local, original)
        clock.handle(ACTIVATE, 2)
        self.assertEqual(clock.zone, "utc")
        self.assertNotEqual(clock.render(2).tobytes(), local)
        clock.handle(ACTIVATE, 3)
        self.assertEqual(clock.zone, "local")
        self.assertEqual(clock.render(3).tobytes(), local)

    def test_invalid_wallclock_update_preserves_previous_pair(self):
        clock = Clock()
        clock.handle({"type": "wallclock", "local": "2026-11-03T20:18:35+08:00", "utc": "2026-11-03T12:18:35Z"}, 1)
        before = dict(clock.times)
        with self.assertRaises(ValueError):
            clock.handle({"type": "wallclock", "local": "2026-11-04T01:00:00", "utc": "not a time"}, 2)
        self.assertEqual(clock.times, before)

    def test_unavailable_clock_clears_stale_time_and_stays_stable(self):
        clock = Clock()
        empty = clock.render(1).tobytes()
        clock.handle({"type": "wallclock", "local": "2026-11-03T20:18:35+08:00", "utc": "2026-11-03T12:18:35Z"}, 1)
        self.assertTrue(clock.times)
        clock.handle({"type": "wallclock", "available": False}, 2)
        self.assertEqual(clock.times, {})
        self.assertEqual(clock.render(2).tobytes(), empty)
        self.assertEqual(clock.render(10000).tobytes(), empty)

    def test_stopwatch_resume_excludes_paused_time_and_reset_stops(self):
        watch = Stopwatch()
        watch.handle(ACTIVATE, 10)
        self.assertAlmostEqual(watch.elapsed(71.25), 61.25)
        watch.handle(ACTIVATE, 71.25)
        picture = watch.render(71.25).tobytes()
        self.assertAlmostEqual(watch.elapsed(1000), 61.25)
        self.assertIsNone(watch.next_delay(1000))
        self.assertEqual(watch.render(1000).tobytes(), picture)
        watch.handle(ACTIVATE, 1000)
        self.assertAlmostEqual(watch.elapsed(1002), 63.25)
        watch.handle(RESET, 1002)
        self.assertEqual(watch.elapsed(9999), 0)
        self.assertIsNone(watch.next_delay(9999))

    def test_pomodoro_transitions_and_large_hidden_gaps(self):
        demo = Pomodoro()
        demo.handle(ACTIVATE, 100)
        self.assertEqual(demo.phase(1599)[:2], ("FOCUS", 1))
        self.assertEqual(demo.phase(1600)[:2], ("BREAK", 300))
        self.assertEqual(demo.phase(1900), ("FOCUS", 1500, 0, 2))
        # A very large elapsed gap is evaluated arithmetically, without replaying ticks.
        phase, remaining, progress, cycle = demo.phase(100 + 1800*100000 + 1510)
        self.assertEqual((phase, remaining, cycle), ("BREAK", 290, 100001))
        self.assertAlmostEqual(progress, 10/300)
        demo.handle(ACTIVATE, 100 + 1800*100000 + 1510)
        frozen = demo.phase(999999999)
        self.assertEqual(frozen, (phase, remaining, progress, cycle))
        self.assertIsNone(demo.next_delay(999999999))

    def test_breathe_phase_lengths_and_paused_pixels(self):
        demo = Breathe()
        demo.handle(ACTIVATE, 10)
        self.assertEqual([demo.phase(t)[0] for t in (10, 14, 18, 22, 26)], [0, 1, 2, 3, 0])
        self.assertEqual(demo.phase(10)[2], 9)
        self.assertEqual(demo.phase(14)[2], 27)
        self.assertEqual(demo.phase(22)[2], 9)
        demo.handle(ACTIVATE, 20)
        before = demo.render(20).tobytes()
        self.assertEqual(demo.render(1000).tobytes(), before)
        self.assertIsNone(demo.next_delay(1000))
        demo.handle(RESET, 1000)
        self.assertEqual(demo.elapsed(1000), 0)

    def test_only_activate_and_supported_reset_change_utilities(self):
        for cls in (Clock, Stopwatch, Pomodoro, Breathe):
            demo = cls()
            before = demo.render(10).tobytes()
            demo.handle({"type": "button", "button": "next"}, 20)
            demo.handle({"type": "button", "button": "unknown"}, 30)
            self.assertEqual(demo.render(40).tobytes(), before, cls.__name__)

    def test_all_utility_states_fit_device_payload_budget(self):
        for cls in (Clock, Stopwatch, Pomodoro, Breathe):
            demo = cls()
            for now in (0, 1.5, 61.25, 1801, 1000000):
                with self.subTest(demo=cls.__name__, now=now):
                    demo.handle(ACTIVATE, now)
                    image = demo.render(now + .25)
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(image.size, (160, 128))
                    self.assertLess(len(jpeg_clip([image])), 16000)


if __name__ == "__main__":
    unittest.main()
