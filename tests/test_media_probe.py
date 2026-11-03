"""Offline media-probe checks: no WinRT imports, endpoints, or media playback."""
import builtins
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pixeldeck.experimental import media_probe as probe


class MediaProbeTests(unittest.TestCase):
    def test_duration_and_readiness_limits_reject_unbounded_values(self):
        for value in (0, -1, 601, float('nan'), float('inf'), True, '10', None):
            with self.subTest(seconds=value), self.assertRaises(ValueError):
                probe.validate_limits(value, 30)
        for value in (0, 61, float('nan'), float('-inf'), False):
            with self.subTest(ready_timeout=value), self.assertRaises(ValueError):
                probe.validate_limits(10, value)
        probe.validate_limits(1, 1)
        probe.validate_limits(600, 60)

    def test_ready_requires_opened_and_actual_playing_in_either_order(self):
        for first, second in (('opened', 'playing'), ('playing', 'opened')):
            with self.subTest(first=first):
                gate = probe.ReadinessGate()
                setattr(gate, first, True)
                self.assertFalse(gate.take_ready())
                setattr(gate, second, True)
                self.assertTrue(gate.take_ready())
                self.assertFalse(gate.take_ready(), 'A second ready event must not be emitted')

    def test_failure_before_open_stays_failed_even_after_playing(self):
        gate = probe.ReadinessGate()
        self.assertFalse(gate.take_ready(failure_seen=True))
        gate.opened = gate.playing = True
        self.assertFalse(gate.take_ready())
        self.assertFalse(gate.announced)

    def test_queued_native_failure_or_closed_gate_cannot_announce_ready(self):
        failed = probe.ReadinessGate(opened=True, playing=True)
        self.assertFalse(failed.take_ready(failure_seen=True))
        closed = probe.ReadinessGate(opened=True, playing=True, closed=True)
        self.assertFalse(closed.take_ready())

    def test_keep_playing_has_no_play_pause_or_status_side_effects(self):
        play, pause, status = Mock(), Mock(), Mock()
        for name in ('Play', 'Pause', 'Pause', 'Play'):
            self.assertEqual(probe.apply_transport_command(
                name, keep_playing=True, play=play, pause=pause, set_status=status),
                'carrier_state_unchanged')
        play.assert_not_called()
        pause.assert_not_called()
        status.assert_not_called()

    def test_normal_commands_are_explicit_and_next_is_not_activation(self):
        play, pause, status = Mock(), Mock(), Mock()
        self.assertEqual(probe.apply_transport_command(
            'Play', keep_playing=False, play=play, pause=pause, set_status=status), 'play_requested')
        play.assert_called_once_with()
        pause.assert_not_called()
        status.assert_called_once_with('Playing')
        self.assertEqual(probe.apply_transport_command(
            'Pause', keep_playing=False, play=play, pause=pause), 'pause_requested')
        pause.assert_called_once_with()
        self.assertIsNone(probe.apply_transport_command(
            'Next', keep_playing=False, play=play, pause=pause, set_status=status))
        self.assertEqual(play.call_count, 1)
        self.assertEqual(pause.call_count, 1)
        self.assertEqual(status.call_count, 1)

    def test_format_selftest_never_loads_runtime_or_configuration(self):
        output = io.StringIO()
        with patch.object(probe, '_load_winrt') as runtime, \
                patch.object(probe.DeviceConfig, 'load') as config, redirect_stdout(output):
            result = probe.main(['--self-test-json', '--receiver', 'commands',
                                 '--playback-item', '--keep-playing'])
        self.assertEqual(result, 0)
        runtime.assert_not_called()
        config.assert_not_called()
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([event['type'] for event in events], ['button', 'raw_button', 'closed'])
        self.assertEqual([event['sequence'] for event in events], [1, 2, 3])
        self.assertFalse(events[-1]['hardware_accessed'])

    def test_defaults_and_config_override_flow_to_live_entry_without_native_work(self):
        api = SimpleNamespace(ApartmentType=SimpleNamespace(MULTI_THREADED='mta'),
                              init_apartment=Mock(), uninit_apartment=Mock())
        for argv, expected_path, expected_hint in (
            ([], None, 'configured output'),
            (['--config', 'example.json', '--endpoint-hint', 'override output'],
             Path('example.json'), 'override output'),
        ):
            with self.subTest(argv=argv), \
                    patch.object(probe, '_load_winrt', return_value=api), \
                    patch.object(probe.DeviceConfig, 'load', return_value=SimpleNamespace(endpoint='configured output')) as load, \
                    patch.object(probe, '_run_live', new_callable=AsyncMock, return_value=0) as run, \
                    patch.object(Path, 'is_file', return_value=True):
                self.assertEqual(probe.main(argv), 0)
                load.assert_called_once_with(expected_path)
                args, hint = run.call_args.args[:2]
                self.assertEqual(hint, expected_hint)
                self.assertEqual(args.wave, probe.DEFAULT_WAVE)
                self.assertEqual(args.receiver, 'manual')
                self.assertFalse(args.keep_playing)
        self.assertEqual(api.init_apartment.call_count, 2)
        self.assertEqual(api.uninit_apartment.call_count, 2)

    def test_platform_and_python_requirements_are_clear_without_imports(self):
        with patch.object(probe.sys, 'platform', 'linux'):
            with self.assertRaisesRegex(RuntimeError, 'requires Windows'):
                probe._load_winrt()
        with patch.object(probe.sys, 'platform', 'win32'), \
                patch.object(probe.sys, 'version_info', (3, 10, 0)):
            with self.assertRaisesRegex(RuntimeError, 'Python 3.11'):
                probe._load_winrt()

    def test_blank_endpoint_or_missing_wave_fails_before_runtime_activation(self):
        for hint, file_exists, expected in (('  ', True, 'nonempty'),
                                            ('configured output', False, 'WAV file')):
            with self.subTest(hint=hint, file_exists=file_exists):
                api = SimpleNamespace(init_apartment=Mock())
                output = io.StringIO()
                with patch.object(probe, '_load_winrt', return_value=api), \
                        patch.object(probe.DeviceConfig, 'load', return_value=SimpleNamespace(endpoint=hint)), \
                        patch.object(Path, 'is_file', return_value=file_exists), redirect_stdout(output):
                    self.assertEqual(probe.main([]), 1)
                api.init_apartment.assert_not_called()
                events = [json.loads(line) for line in output.getvalue().splitlines()]
                self.assertIn(expected, events[0]['value'])
                self.assertEqual(events[-1]['type'], 'closed')
    def test_missing_dependency_identifies_optional_extra(self):
        original_import = builtins.__import__

        def import_without_winrt(name, *args, **kwargs):
            if name == 'winrt' or name.startswith('winrt.'):
                raise ImportError('Test deliberately excludes optional native bindings')
            return original_import(name, *args, **kwargs)

        with patch.object(probe.sys, 'platform', 'win32'), \
                patch.object(probe.sys, 'version_info', (3, 11, 0)), \
                patch('builtins.__import__', side_effect=import_without_winrt):
            with self.assertRaisesRegex(RuntimeError, r'minitoo-pixeldeck\[windows-input\]'):
                probe._load_winrt()


if __name__ == '__main__':
    unittest.main()
