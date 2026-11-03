import unittest
from unittest.mock import patch
from pixeldeck.export import export_demo, frames
from pixeldeck.demos.audio_lab import AudioLab


class ExportLimitsTests(unittest.TestCase):
    def test_invalid_duration_is_rejected_before_filesystem_changes(self):
        with patch('pixeldeck.export.Path.mkdir', side_effect=AssertionError('Must validate first')):
            for seconds in (0, -1, 16, True, 1.2):
                with self.assertRaises(ValueError): export_demo('buddy', 'unused.gif', seconds)

    def test_generator_frame_rate_is_bounded(self):
        for fps in (0, -1, 31, True, 1.2):
            with self.assertRaises(ValueError): next(frames('buddy', fps=fps))

    def test_audio_samples_advance_in_every_mode_segment(self):
        rendered = []
        original_render = AudioLab.render

        def record(demo, now):
            rendered.append((demo.mode, demo.elapsed, demo.rms, demo.waveform))
            return original_render(demo, now)

        with patch.object(AudioLab, 'render', record):
            pictures = list(frames('audio', seconds=4, fps=8))

        self.assertEqual(len(pictures), 32)
        for mode in ('speaker', 'microphone', 'duplex'):
            samples = [row for row in rendered if row[0] == mode]
            self.assertGreater(len(samples), 1)
            self.assertEqual(samples[0][1], 0)
            self.assertTrue(all(a[1] < b[1] for a, b in zip(samples, samples[1:])))
            self.assertTrue(all(row[2] is not None and len(row[3]) == 32 for row in samples))
            self.assertGreater(len({row[3] for row in samples}), 1)
