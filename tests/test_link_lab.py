"""Pure Link Lab state checks: no sockets, Tk, timers or media sessions."""
import unittest

from pixeldeck.demos import create
from pixeldeck.demos.link_lab import LinkLab
from pixeldeck.protocol import MAX_BLOB, jpeg_clip


ACK = {'type': 'frame.ack', 'sequence': 12, 'transfer_ms': 430.5, 'bytes': 3840,
       'chunks': 15, 'retransmissions': 1, 'replaced': 2, 'input_to_ack_ms': 455.2}


class LinkLabTests(unittest.TestCase):
    def action(self, lab, button, source='desktop'):
        event = {'type': 'button', 'button': button, 'source': source, 'raw': button}
        lab.observe(event, 0)
        return lab.handle(event, 0)

    def test_registered_navigation_snapshot_pattern_and_back(self):
        lab = create('link')
        self.assertIsInstance(lab, LinkLab)
        self.assertEqual(lab.sources, ())
        self.assertTrue(lab.captures_navigation)
        self.action(lab, 'previous')
        self.assertEqual(lab.selected, 2)
        self.action(lab, 'activate')
        self.assertTrue(lab.detail)
        self.assertEqual(lab.pattern, 1)
        self.assertEqual(lab.snapshot['counts']['desktop'], 2)
        self.assertIsNone(self.action(lab, 'back'))
        self.assertFalse(lab.detail)
        self.assertEqual(self.action(lab, 'back'), 'leave')

    def test_observations_never_change_render_or_schedule_a_tick(self):
        lab = LinkLab()
        self.action(lab, 'activate')
        before = lab.render(0).tobytes()
        for event in (ACK, {'type': 'link.lost'}, {'type': 'link.error'},
                      {'type': 'input.status', 'kind': 'ready'},
                      {'type': 'input.unmapped', 'raw': 'ChannelUp'},
                      {'type': 'input.coalesced', 'raw': 'Pause'}):
            lab.observe(event, 1)
            self.assertEqual(lab.render(100).tobytes(), before)
            self.assertIsNone(lab.next_delay(100))
        self.action(lab, 'activate')
        self.assertNotEqual(lab.render(100).tobytes(), before)
        self.assertEqual(lab.snapshot['metrics']['transfer_ms'], 430.5)
        self.assertEqual(lab.snapshot['counts']['unmapped'], 1)
        self.assertEqual(lab.snapshot['counts']['coalesced'], 1)

    def test_observe_counts_once_while_handle_only_controls(self):
        lab = LinkLab()
        self.action(lab, 'activate', source='media')
        self.assertEqual(lab.counts['media'], 1)
        self.assertEqual(lab.snapshot['counts']['media'], 1)
        lab.handle({'type': 'input.unmapped', 'raw': 'ChannelDown'}, 0)
        self.assertEqual(lab.counts['unmapped'], 1)

    def test_metrics_are_atomic_validated_bounded_and_missing_is_honest(self):
        lab = LinkLab()
        for i in range(100):
            lab.observe(dict(ACK, sequence=i, transfer_ms=i), i)
        self.assertEqual(len(lab.latencies), 24)
        self.assertEqual(lab.counts['acks'], 100)
        previous = dict(lab.latest)
        for field, value in (('transfer_ms', float('nan')), ('bytes', -1),
                             ('sequence', True), ('chunks', 1.5), ('input_to_ack_ms', 'fast')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                lab.observe(dict(ACK, **{field: value}), 0)
            self.assertEqual(lab.latest, previous)
            self.assertEqual(lab.counts['acks'], 100)
        lab.observe({'type': 'frame.ack'}, 0)
        self.assertTrue(all(value is None for value in lab.latest.values()))
        lab.observe({'type': 'input.unmapped', 'raw': 'X'*10000}, 0)
        self.assertEqual(len(lab.last_input), 18)

    def test_recovery_does_not_clear_input_failure_or_imply_button_delivery(self):
        lab = LinkLab()
        lab.observe({'type': 'input.status', 'kind': 'error'}, 0)
        lab.observe({'type': 'link.lost'}, 0)
        lab.observe(ACK, 0)
        self.assertEqual(lab.counts['recoveries'], 1)
        self.assertEqual(lab.input_state, 'ERROR')
        self.assertEqual(lab.counts['media'], 0)

    def test_all_panels_and_patterns_fit_live_encoding_budget(self):
        lab = LinkLab()
        lab.observe(ACK, 0)
        for detail in (False, True):
            for panel in range(3):
                for pattern in range(4):
                    lab.selected = panel
                    self.action(lab, 'activate')
                    lab.detail = detail
                    image = lab.render(0)
                    self.assertEqual((image.mode, image.size), ('RGB', (160, 128)))
                    self.assertLessEqual(len(jpeg_clip([image])), MAX_BLOB)


if __name__ == '__main__':
    unittest.main()
