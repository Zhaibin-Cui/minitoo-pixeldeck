"""Production child CLI contract, tested without importing optional native bindings."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pixeldeck import winrt_bridge as bridge
from pixeldeck.experimental.media_probe import SESSION_TITLE
from pixeldeck.windows_media import SESSION_TITLE as SHARED_TITLE


class WinrtBridgeTests(unittest.TestCase):
    def test_format_selftest_is_hardware_free_and_jsonl_compatible(self):
        output = io.StringIO()
        with patch.object(bridge, 'load_winrt') as native, redirect_stdout(output):
            self.assertEqual(bridge.main(['--self-test-json']), 0)
        native.assert_not_called()
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row['value'] for row in records[:-1]], ['Next', 'Play', 'Pause'])
        self.assertTrue(all(row['backend'] == 'winrt' for row in records))
        self.assertFalse(records[-1]['hardware_accessed'])
        self.assertEqual(SESSION_TITLE, SHARED_TITLE)

    def test_production_defaults_follow_state_without_a_session_timeout(self):
        api = SimpleNamespace(ApartmentType=SimpleNamespace(MULTI_THREADED='mta'),
                              init_apartment=Mock(), uninit_apartment=Mock())
        with patch.object(bridge, 'load_winrt', return_value=api), \
                patch.object(bridge, 'run_session', new_callable=AsyncMock, return_value=0) as session, \
                patch.object(Path, 'is_file', return_value=True):
            self.assertEqual(bridge.main(['test output', 'silent.wav']), 0)
        options, hint = session.call_args.args[:2]
        self.assertEqual(hint, 'test output')
        self.assertEqual(options.receiver, 'commands')
        self.assertTrue(options.playback_item)
        self.assertFalse(options.keep_playing or options.diagnostics)
        self.assertIsNone(options.seconds)
        self.assertTrue(options.stop_on_eof)
        api.init_apartment.assert_called_once_with('mta')
        api.uninit_apartment.assert_called_once_with()

    def test_missing_dependencies_are_reported_as_jsonl(self):
        output = io.StringIO()
        with patch.object(bridge, 'load_winrt', side_effect=RuntimeError('Optional dependencies missing')), \
                patch.object(Path, 'is_file', return_value=True), redirect_stdout(output):
            self.assertEqual(bridge.main(['test output', 'silent.wav']), 1)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row['type'] for row in records], ['error', 'closed'])
        self.assertIn('Optional dependencies missing', records[0]['value'])

    def test_internal_stdin_reader_does_not_load_winrt(self):
        output = io.StringIO()
        with patch.object(bridge.sys, 'stdin', io.StringIO('mark check\n')), \
                patch.object(bridge, 'load_winrt') as native, redirect_stdout(output):
            self.assertEqual(bridge.main(['--stdin-reader']), 0)
        native.assert_not_called()
        self.assertEqual(output.getvalue().splitlines(), ['CHECK', '!EOF'])


if __name__ == '__main__':
    unittest.main()
