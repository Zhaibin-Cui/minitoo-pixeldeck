import sys
import unittest
from importlib import metadata
from types import SimpleNamespace
from unittest.mock import patch

from pixeldeck.input_backends import input_command, select_backend, winrt_status
from pixeldeck.inputs import ActivationGuard


class ActivationPolicyTests(unittest.TestCase):
    @staticmethod
    def event(raw, at):
        return {'type': 'button', 'raw': raw, 'received_at': at}

    def test_first_event_is_immediate_and_echo_does_not_extend_window(self):
        guard = ActivationGuard()
        self.assertTrue(guard.accept(self.event('Pause', 10)))
        self.assertFalse(guard.accept(self.event('Play', 10.137)))
        self.assertFalse(guard.accept(self.event('Pause', 10.240)))
        self.assertTrue(guard.accept(self.event('Play', 10.251)))

    def test_separate_taps_and_navigation_are_preserved(self):
        guard = ActivationGuard()
        for index in range(20):
            self.assertTrue(guard.accept(self.event('Pause', index * 0.5)))
            self.assertFalse(guard.accept(self.event('Play', index * 0.5 + 0.137)))
            self.assertTrue(guard.accept(self.event('Next', index * 0.5 + 0.15)))

    def test_raw_mode_and_parameter_bounds(self):
        guard = ActivationGuard(0)
        self.assertTrue(guard.accept(self.event('Pause', 1)))
        self.assertTrue(guard.accept(self.event('Play', 1)))
        for value in (-1, 2, True, float('nan'), float('inf')):
            with self.assertRaises(ValueError): ActivationGuard(value)


class BackendTests(unittest.TestCase):
    def test_explicit_legacy_does_not_check_optional_dependencies(self):
        with patch('pixeldeck.input_backends.winrt_status', side_effect=AssertionError):
            self.assertEqual(select_backend('legacy'), 'legacy')

    def test_auto_selection_and_explicit_failure(self):
        with patch('pixeldeck.input_backends.winrt_status', return_value={'available': True}):
            self.assertEqual(select_backend(), 'winrt')
        with patch('pixeldeck.input_backends.winrt_status', return_value={'available': False, 'reason': 'fixture missing'}):
            self.assertEqual(select_backend(), 'legacy')
            with self.assertRaisesRegex(RuntimeError, 'fixture missing'): select_backend('winrt')
        with self.assertRaises(ValueError): select_backend('unknown')

    def test_metadata_check_never_imports_native_bindings(self):
        def version(name): return '4.1.0' if name == 'winrt-runtime' else '4!10.0.28000.2957'
        with patch('pixeldeck.input_backends.sys.platform', 'win32'), \
                patch('pixeldeck.input_backends.sys.version_info', (3, 12)), \
                patch('pixeldeck.input_backends.metadata.version', side_effect=version):
            self.assertTrue(winrt_status()['available'])
        with patch('pixeldeck.input_backends.sys.platform', 'win32'), \
                patch('pixeldeck.input_backends.sys.version_info', (3, 12)), \
                patch('pixeldeck.input_backends.metadata.version', return_value='4.0.0'):
            self.assertFalse(winrt_status()['available'])

    def test_missing_or_inaccessible_metadata_is_redacted(self):
        with patch('pixeldeck.input_backends.sys.platform', 'win32'), \
                patch('pixeldeck.input_backends.sys.version_info', (3, 12)):
            for error in (metadata.PackageNotFoundError('fixture'), PermissionError('private detail')):
                with patch('pixeldeck.input_backends.metadata.version', side_effect=error):
                    result = winrt_status()
                    self.assertFalse(result['available'])
                    self.assertNotIn('private detail', result['reason'])

    def test_winrt_child_uses_current_interpreter_and_private_endpoint_argument(self):
        command = input_command(SimpleNamespace(endpoint='fixture endpoint'), 'winrt')
        self.assertEqual(command[:4], [sys.executable, '-u', '-m', 'pixeldeck.winrt_bridge'])
        self.assertEqual(command[4], 'fixture endpoint')
        with patch('pixeldeck.input_backends.Path.is_file', return_value=False):
            with self.assertRaises(FileNotFoundError): input_command(SimpleNamespace(endpoint='fixture'), 'legacy')
