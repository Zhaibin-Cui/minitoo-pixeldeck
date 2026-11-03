import contextlib
import io
import unittest
from unittest.mock import patch

from pixeldeck.cli import main
from pixeldeck.config import DeviceConfig


class CliTests(unittest.TestCase):
    def test_display_overrides_leave_saved_config_unchanged(self):
        original = DeviceConfig()
        with patch('pixeldeck.cli.DeviceConfig.load', return_value=original), \
                patch('pixeldeck.app.Application') as host:
            main(['run', 'audio', '--codec', 'auto', '--chunk-delay-ms', '2'])
            config = host.call_args.args[0]
            self.assertEqual((config.codec, config.chunk_delay_ms), ('auto', 2))
            self.assertEqual((original.codec, original.chunk_delay_ms), ('jpeg', 10))

    def test_invalid_display_pacing_does_not_open_host(self):
        with patch('pixeldeck.cli.DeviceConfig.load', return_value=DeviceConfig()), \
                patch('pixeldeck.app.Application') as host:
            for value in ('-1', '101', 'nan', 'inf'):
                with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main(['run', 'audio', '--chunk-delay-ms', value])
            host.assert_not_called()

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
