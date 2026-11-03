import unittest
from unittest.mock import patch
from pixeldeck.export import export_demo, frames


class ExportLimitsTests(unittest.TestCase):
    def test_invalid_duration_is_rejected_before_filesystem_changes(self):
        with patch('pixeldeck.export.Path.mkdir', side_effect=AssertionError('Must validate first')):
            for seconds in (0, -1, 16, True, 1.2):
                with self.assertRaises(ValueError): export_demo('buddy', 'unused.gif', seconds)

    def test_generator_frame_rate_is_bounded(self):
        for fps in (0, -1, 31, True, 1.2):
            with self.assertRaises(ValueError): next(frames('buddy', fps=fps))
