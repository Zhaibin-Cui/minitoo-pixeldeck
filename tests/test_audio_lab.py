"""Audio cartridge checks with synthetic events and no audio provider imports."""
import copy
import math
import unittest
from unittest.mock import patch

from PIL import ImageColor

from pixeldeck.demos.audio_lab import AudioLab, _dbfs, _dbfs_label
from pixeldeck.pixels import Canvas, CYAN
from pixeldeck.protocol import MAX_BLOB, jpeg_clip, zstd_clip

try:
    import zstandard
except (ImportError, OSError):
    zstandard = None


class AudioLabTests(unittest.TestCase):
    def action(self, lab, name):
        return lab.handle({'type': 'button', 'button': name}, 0)

    def test_entering_or_navigating_never_requests_audio(self):
        lab = AudioLab()
        self.assertEqual(lab.sources, ())
        self.assertIsNone(lab.next_delay(100))
        for _ in range(4):
            self.assertIsNone(self.action(lab, 'next'))
            self.assertEqual(lab.state, 'idle')
            lab.render(0)
        self.assertEqual(lab.selected, 1)
        self.assertEqual(self.action(lab, 'back'), 'leave')

    def test_each_mode_requires_explicit_bounded_request(self):
        for index, mode in enumerate(AudioLab.MODES):
            with self.subTest(mode=mode):
                lab = AudioLab()
                lab.selected = index
                self.assertEqual(self.action(lab, 'activate'),
                                 {'type': 'audio.request', 'mode': mode, 'seconds': 5})
                self.assertEqual(lab.state, 'starting')
                self.assertIsNone(lab.rms)
                self.assertEqual(lab.waveform, ())
                self.assertIsNone(self.action(lab, 'next'))
                self.assertEqual(lab.selected, index, 'A running test must keep its selected mode')

    def test_starting_ready_and_back_stop_once_then_leave(self):
        for initial in ('starting', 'ready'):
            with self.subTest(state=initial):
                lab = AudioLab()
                lab.handle({'type': 'audio.status', 'state': initial, 'mode': 'microphone'}, 0)
                self.assertEqual(self.action(lab, 'back'), {'type': 'audio.stop'})
                self.assertEqual(lab.state, 'stopping')
                self.assertIsNone(self.action(lab, 'activate'))
                lab.handle({'type': 'audio.status', 'state': 'stopped'}, 0)
                self.assertEqual(self.action(lab, 'back'), 'leave')

    def test_levels_do_not_claim_readiness_and_missing_values_stay_missing(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.level', 'mode': 'microphone', 'elapsed': 1.25,
                    'rms': .25, 'peak': .8, 'waveform': [-.8, .2, .8]}, 0)
        self.assertEqual(lab.state, 'idle')
        self.assertEqual(lab.waveform, (-.8, .2, .8))
        lab.handle({'type': 'audio.level'}, 0)
        self.assertIsNone(lab.rms)
        self.assertIsNone(lab.peak)
        self.assertEqual(lab.waveform, ())

    def test_invalid_levels_are_rejected_atomically(self):
        lab = AudioLab()
        event = {'type': 'audio.level', 'mode': 'duplex', 'elapsed': 2,
                 'rms': .2, 'peak': .7, 'waveform': [-.7, 0, .7]}
        lab.handle(event, 0)
        previous = (lab.mode, lab.rms, lab.peak, lab.elapsed, lab.waveform)
        for field, value in (('rms', True), ('rms', float('nan')), ('peak', 1.1),
                             ('elapsed', -1), ('elapsed', None), ('mode', 'unknown'),
                             ('waveform', [0]*33), ('waveform', [None]),
                             ('waveform', [1.1]), ('waveform', 'samples')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                lab.handle(dict(event, **{field: value}), 0)
            self.assertEqual((lab.mode, lab.rms, lab.peak, lab.elapsed, lab.waveform), previous)

    def test_microphone_indicator_requires_ready_and_error_is_visible(self):
        lab = AudioLab()
        lab.selected = 1
        self.assertEqual(lab._state_label()[0], 'MIC IDLE')
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'microphone'}, 0)
        self.assertEqual(lab._state_label()[0], 'MIC LIVE')
        lab.handle({'type': 'audio.status', 'state': 'stopping'}, 0)
        self.assertEqual(lab._state_label()[0], 'MIC STOPPING')
        lab.handle({'type': 'audio.status', 'state': 'error',
                    'message': 'Enable audio and select devices'}, 0)
        self.assertEqual(lab._state_label()[0], 'UNAVAILABLE')
        self.assertFalse(lab.active)
        self.assertEqual(self.action(lab, 'back'), 'leave')

    def test_all_modes_and_states_fit_frame_and_encoding_budget(self):
        lab = AudioLab()
        for mode in lab.MODES:
            for state in lab.STATES:
                lab.handle({'type': 'audio.status', 'state': state, 'mode': mode,
                            'message': 'Enable audio and select devices'}, 0)
                lab.handle({'type': 'audio.level', 'mode': mode, 'elapsed': 4.75,
                            'rms': .5, 'peak': 1, 'waveform': [-1, 1]*16}, 0)
                image = lab.render(0)
                self.assertEqual((image.mode, image.size), ('RGB', (160, 128)))
                self.assertLessEqual(len(jpeg_clip([image])), MAX_BLOB)
                self.assertIsNone(lab.next_delay(100))

    def test_dbfs_distinguishes_missing_silence_quiet_and_full_scale(self):
        for amplitude, expected, label in ((None, None, '--'), (0, -math.inf, '-INF'),
                                           (.01, -40, '-40.0'), (.001, -60, '-60.0'),
                                           (.0001, -80, '-80.0'), (1, 0, '0.0')):
            with self.subTest(amplitude=amplitude):
                level = _dbfs(amplitude)
                self.assertEqual(level, expected)
                self.assertEqual(_dbfs_label(level), label)

    def test_quiet_meter_is_visible_and_values_below_floor_are_not_boosted(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'microphone'}, 0)
        for amplitude, expected_color in ((.01, '#80edc0'), (.001, '#202020'),
                                           (.0001, '#202020'), (0, '#202020'), (1, '#80edc0')):
            with self.subTest(amplitude=amplitude):
                lab.handle({'type': 'audio.level', 'rms': amplitude, 'peak': amplitude}, 0)
                image = lab.render(0)
                self.assertEqual(image.getpixel((32, 80)), ImageColor.getrgb(expected_color))

    def test_scope_display_gain_makes_quiet_wave_visible_without_changing_samples(self):
        lab = AudioLab()
        samples = [-.01, .01]*16
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'speaker'}, 0)
        lab.handle({'type': 'audio.level', 'rms': .01, 'peak': .01,
                    'waveform': samples, 'elapsed': 1}, 0)
        before = (lab.rms, lab.peak, lab.waveform)
        image = lab.render(0)
        rows = {y for x in range(10, 108) for y in range(60, 83)
                if image.getpixel((x, y)) == ImageColor.getrgb(CYAN)}
        self.assertLess(min(rows), 71)
        self.assertGreater(max(rows), 71)
        self.assertEqual((lab.rms, lab.peak, lab.waveform), before)
        self.assertEqual(samples, [-.01, .01]*16)

    def test_scope_clamps_display_only_and_extreme_finite_labels_fit(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'speaker'}, 0)
        lab.handle({'type': 'audio.level', 'rms': 1, 'peak': 1, 'waveform': [-1, 1]}, 0)
        image = lab.render(0)
        self.assertEqual(image.getpixel((10, 81)), ImageColor.getrgb(CYAN))
        self.assertEqual(image.getpixel((107, 61)), ImageColor.getrgb(CYAN))
        self.assertEqual(lab.waveform, (-1., 1.))
        self.assertLessEqual(len(_dbfs_label(_dbfs(math.nextafter(0, 1)))), 6)

    def test_live_peak_hold_uses_event_elapsed_without_changing_window_peak(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'microphone'}, 0)
        for elapsed, peak, held in ((0, .8, .8), (.25, .1, .8), (.75, .3, .8),
                                    (1.01, .2, .3), (1.8, .1, .2), (2.02, 0, .1)):
            lab.handle({'type': 'audio.level', 'elapsed': elapsed, 'rms': peak/2, 'peak': peak}, 0)
            self.assertEqual(lab.peak, peak)
            self.assertEqual(lab._display_levels(), (peak/2, held))
        before = lab.render(0).tobytes()
        self.assertEqual(lab.render(10000).tobytes(), before)
        self.assertIsNone(lab.next_delay(10000))

    def test_stopped_uses_real_session_summary_instead_of_final_quiet_window(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'microphone'}, 0)
        lab.handle({'type': 'audio.level', 'elapsed': .25, 'rms': .2, 'peak': .8,
                    'session_rms': .2, 'session_peak': .8,
                    'metered_frames': 12000, 'dropped_frames': 0}, 0)
        lab.handle({'type': 'audio.level', 'elapsed': 5, 'rms': 0, 'peak': 0,
                    'waveform': [0]*32, 'session_rms': .14, 'session_peak': .8,
                    'metered_frames': 240000, 'dropped_frames': 64}, 0)
        self.assertEqual(lab._display_levels(), (0, 0))
        lab.handle({'type': 'audio.status', 'state': 'stopped', 'elapsed': 5,
                    'session_rms': .139, 'session_peak': .81,
                    'metered_frames': 240128, 'dropped_frames': 64}, 0)
        self.assertEqual(lab._display_levels(), (.139, .81))
        self.assertEqual((lab.rms, lab.peak, lab.waveform), (0, 0, (0,)*32))
        self.assertEqual((lab.metered_frames, lab.dropped_frames), (240128, 64))
        self.assertEqual(lab._state_label()[0], 'SESSION')
        self.assertLessEqual(len(jpeg_clip([lab.render(0)])), MAX_BLOB)

    def test_missing_summary_stays_unknown_and_existing_summary_survives_status_only_stop(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.level', 'rms': .3, 'peak': .6}, 0)
        lab.handle({'type': 'audio.status', 'state': 'stopped'}, 0)
        self.assertEqual(lab._display_levels(), (None, None))
        lab.handle({'type': 'audio.level', 'session_rms': .2, 'session_peak': .7,
                    'metered_frames': 100, 'dropped_frames': 2}, 0)
        lab.handle({'type': 'audio.status', 'state': 'stopped'}, 0)
        self.assertEqual(lab._display_levels(), (.2, .7))
        self.assertEqual((lab.metered_frames, lab.dropped_frames), (100, 2))

    def test_new_summary_fields_are_validated_before_any_state_change(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'microphone'}, 0)
        lab.handle({'type': 'audio.level', 'elapsed': 1, 'rms': .2, 'peak': .6,
                    'session_rms': .2, 'session_peak': .6,
                    'metered_frames': 48000, 'dropped_frames': 0}, 0)
        previous = copy.deepcopy(vars(lab))
        for kind in ('audio.status', 'audio.level'):
            for field, value in (('session_rms', float('nan')), ('session_peak', 1.1),
                                 ('metered_frames', -1), ('dropped_frames', True),
                                 ('metered_frames', 1.5), ('elapsed', None)):
                with self.subTest(kind=kind, field=field), self.assertRaises(ValueError):
                    lab.handle({'type': kind, 'state': 'stopped', 'mode': 'duplex',
                                'elapsed': 2, field: value}, 0)
                self.assertEqual(vars(lab), previous)

    def test_history_is_bounded_old_windows_ignored_and_new_test_clears_summary(self):
        lab = AudioLab()
        for index in range(100):
            lab.handle({'type': 'audio.level', 'elapsed': index/4, 'rms': .1, 'peak': .5,
                        'session_rms': .1, 'session_peak': .5, 'metered_frames': index*12000}, 0)
        self.assertEqual(len(lab.peak_history), 20)
        previous = copy.deepcopy(vars(lab))
        lab.handle({'type': 'audio.level', 'elapsed': 1, 'rms': 1, 'peak': 1}, 0)
        self.assertEqual(vars(lab), previous)
        self.action(lab, 'activate')
        self.assertEqual(len(lab.peak_history), 0)
        self.assertIsNone(lab.held_peak)
        self.assertIsNone(lab.session_rms)
        self.assertIsNone(lab.metered_frames)

    def test_error_remains_visible_with_session_summary(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'error', 'mode': 'microphone',
                    'message': 'Input stream failed', 'session_rms': .1, 'session_peak': .5,
                    'metered_frames': 1000, 'dropped_frames': 50}, 0)
        self.assertEqual(lab._state_label()[0], 'UNAVAILABLE')
        self.assertEqual(lab.message, 'Input stream failed')
        self.assertFalse(lab.active)

    def test_compact_meter_uses_instantaneous_rms_and_does_not_mutate_history(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'microphone'}, 0)
        lab.handle({'type': 'audio.level', 'elapsed': 1, 'rms': .5, 'peak': .9}, 0)
        lab.handle({'type': 'audio.level', 'elapsed': 1.1, 'rms': .001, 'peak': .002,
                    'waveform': [-.002, .002], 'session_rms': .2, 'session_peak': .9,
                    'metered_frames': 52800, 'dropped_frames': 0}, 0)
        self.assertEqual(lab.held_peak, .9)
        before = copy.deepcopy(vars(lab))
        image = lab.render(0)
        self.assertEqual(image.getpixel((32, 80)), ImageColor.getrgb('#202020'))
        self.assertEqual(image.tobytes(), lab.render(10000).tobytes())
        self.assertEqual(vars(lab), before)

    def test_compact_silence_is_distinct_from_unknown_and_values_are_truthful(self):
        lab = AudioLab()
        lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': 'duplex'}, 0)
        original = Canvas.text
        for rms, expected in ((None, '--'), (0, '-INF'), (.012, '-38'), (.0001, '-80'), (1, '0')):
            with self.subTest(rms=rms):
                lab.handle({'type': 'audio.level', 'rms': rms, 'peak': rms}, 0)
                with patch.object(Canvas, 'text', autospec=True, side_effect=original) as text:
                    image = lab.render(0)
                labels = [call.args[3] for call in text.call_args_list]
                self.assertIn(expected, labels)
                self.assertEqual((image.mode, image.size), ('RGB', (160, 128)))
                if rms is None:
                    self.assertNotIn('-INF', labels)
                    self.assertIn('WAITING FOR LEVELS', labels)
                else:
                    self.assertIn('DUPLEX LIVE', labels)
                    self.assertIn('ACT STOP', labels)
                    self.assertNotIn('PEAK HOLD 1S  ACT STOP', labels)

    def test_compact_render_keeps_other_states_and_speaker_on_full_view(self):
        lab = AudioLab()
        for mode in lab.MODES:
            for state in lab.STATES:
                if mode in ('microphone', 'duplex') and state == 'ready':
                    continue
                with self.subTest(mode=mode, state=state):
                    lab.handle({'type': 'audio.status', 'mode': mode, 'state': state}, 0)
                    lab.handle({'type': 'audio.level', 'rms': .1, 'peak': .5}, 0)
                    with patch.object(lab, '_live_meter', side_effect=AssertionError('Full view required')):
                        self.assertEqual(lab.render(0).size, (160, 128))

    @unittest.skipIf(zstandard is None, 'Optional zstandard package is not installed')
    def test_compact_live_payload_stays_below_one_kib_without_losing_rgb(self):
        lab = AudioLab()
        for mode in ('microphone', 'duplex'):
            lab.handle({'type': 'audio.status', 'state': 'ready', 'mode': mode}, 0)
            for rms in (0, math.nextafter(0, 1), .0001, .001, .012, .2, 1):
                with self.subTest(mode=mode, rms=rms):
                    lab.handle({'type': 'audio.level', 'rms': rms, 'peak': rms}, 0)
                    image = lab.render(0)
                    blob = zstd_clip([image])
                    self.assertLess(len(blob), 1024)
                    decoded = zstandard.ZstdDecompressor().decompress(blob[10:])
                    self.assertEqual(decoded, image.tobytes())


if __name__ == '__main__':
    unittest.main()
