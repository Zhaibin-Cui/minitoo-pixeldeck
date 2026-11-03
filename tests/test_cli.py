import contextlib
import io
import unittest
from unittest.mock import patch

from pixeldeck.cli import main
from pixeldeck.config import DeviceConfig


class CliTests(unittest.TestCase):
    def test_invalid_audio_selection_fails_before_opening_host(self):
        cases = (
            ['--audio'],
            ['--audio-input', '0'],
            ['--audio', '--audio-input', '-1'],
            ['--media'],
        )
        with patch('pixeldeck.app.Application') as host:
            for options in cases:
                with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main(['run', 'buddy', *options])
                    self.assertEqual(raised.exception.code, 2)
            host.assert_not_called()

    def test_preview_leaves_audio_disabled(self):
        with patch('pixeldeck.cli.DeviceConfig.load', return_value=DeviceConfig()), \
                patch('pixeldeck.app.Application') as host:
            main(['run', 'buddy'])
            self.assertFalse(host.call_args.kwargs['audio'])
            self.assertIsNone(host.call_args.kwargs['audio_input'])
            self.assertIsNone(host.call_args.kwargs['audio_output'])

    def test_audio_selection_is_passed_without_changing_display_mode(self):
        with patch('pixeldeck.cli.DeviceConfig.load', return_value=DeviceConfig()), \
                patch('pixeldeck.app.Application') as host:
            main(['run', 'buddy', '--audio', '--audio-input', '0', '--audio-output', '3'])
            self.assertFalse(host.call_args.args[2])
            self.assertEqual(host.call_args.kwargs['audio_input'], 0)
            self.assertEqual(host.call_args.kwargs['audio_output'], 3)
            self.assertTrue(host.call_args.kwargs['audio'])
