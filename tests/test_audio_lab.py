"""Audio cartridge checks with synthetic events and no audio provider imports."""
import unittest

from pixeldeck.demos.audio_lab import AudioLab
from pixeldeck.protocol import MAX_BLOB, jpeg_clip


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


if __name__ == '__main__':
    unittest.main()
