"""Windows COM ownership checks; no real COM initialization or audio hardware."""
from array import array
import ctypes
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pixeldeck.audio import AudioBackend, _initialize_com


class AudioComTests(unittest.TestCase):
    def apartment(self, result):
        return SimpleNamespace(CoInitializeEx=Mock(return_value=result), CoUninitialize=Mock())

    def test_success_and_already_initialized_are_balanced_once_on_owner_thread(self):
        for result in (0, 1):
            with self.subTest(result=result):
                ole = self.apartment(result)
                with patch('pixeldeck.audio.sys.platform', 'win32'), \
                     patch.object(ctypes, 'WinDLL', return_value=ole, create=True):
                    cleanup = _initialize_com()
                    ole.CoInitializeEx.assert_called_once_with(None, 0)
                    ole.CoUninitialize.assert_not_called()
                    cleanup()
                    cleanup()
                ole.CoUninitialize.assert_called_once_with()

    def test_existing_different_apartment_is_not_uninitialized(self):
        ole = self.apartment(-2147417850)  # RPC_E_CHANGED_MODE as signed HRESULT.
        with patch('pixeldeck.audio.sys.platform', 'win32'), \
             patch.object(ctypes, 'WinDLL', return_value=ole, create=True):
            self.assertIsNone(_initialize_com())
        ole.CoUninitialize.assert_not_called()

    def test_failed_initialization_reports_hresult_and_has_no_cleanup(self):
        ole = self.apartment(-2147024882)  # E_OUTOFMEMORY.
        with patch('pixeldeck.audio.sys.platform', 'win32'), \
             patch.object(ctypes, 'WinDLL', return_value=ole, create=True):
            with self.assertRaisesRegex(RuntimeError, 'HRESULT 0x8007000E'):
                _initialize_com()
        ole.CoUninitialize.assert_not_called()

    def test_non_windows_does_not_load_ole32(self):
        with patch('pixeldeck.audio.sys.platform', 'linux'), \
             patch.object(ctypes, 'WinDLL', create=True) as load:
            self.assertIsNone(_initialize_com())
        load.assert_not_called()

    def test_wrong_thread_cannot_release_the_owners_reference(self):
        ole = self.apartment(0)
        errors = []
        with patch('pixeldeck.audio.sys.platform', 'win32'), \
             patch.object(ctypes, 'WinDLL', return_value=ole, create=True):
            cleanup = _initialize_com()

            def wrong_thread():
                try:
                    cleanup()
                except RuntimeError as error:
                    errors.append(str(error))

            thread = threading.Thread(target=wrong_thread)
            thread.start()
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            ole.CoUninitialize.assert_not_called()
            cleanup()
        ole.CoUninitialize.assert_called_once_with()

    def run_with_trace(self, *, stream_failure=False, terminal_failure=False):
        trace = []
        cancelled = threading.Event()
        owner = threading.get_ident()

        class Stream:
            latency = .01

            def __init__(self, **values):
                trace.append('open')
                self.values = values

            def start(self):
                trace.append('start')
                if stream_failure:
                    raise RuntimeError('Simulated native start failure')
                self.values['callback'](array('h', [1000]*80).tobytes(), 80, None, False)

            def abort(self):
                trace.append('abort')

            def close(self):
                trace.append('close')

        class SoundDevice:
            def query_devices(self, index):
                trace.append('query')
                return dict(max_input_channels=1, default_samplerate=8000)

            def check_input_settings(self, **values):
                trace.append('settings')

            RawInputStream = Stream

        def initialize():
            trace.append('initialize')

            def cleanup():
                self.assertEqual(threading.get_ident(), owner)
                trace.append('uninitialize')
            return cleanup

        def receive(event):
            trace.append(event.get('state', event['type']))
            if event.get('state') == 'ready':
                cancelled.set()
            if terminal_failure and event.get('state') in ('stopped', 'error'):
                raise RuntimeError('Simulated terminal callback failure')

        with patch('pixeldeck.audio._initialize_com', side_effect=initialize):
            if terminal_failure:
                with self.assertRaisesRegex(RuntimeError, 'terminal callback failure'):
                    AudioBackend(input_device=0, sd_module=SoundDevice()).run(
                        'microphone', 5, cancelled, receive)
            else:
                AudioBackend(input_device=0, sd_module=SoundDevice()).run(
                    'microphone', 5, cancelled, receive)
        return trace

    def test_direct_backend_covers_device_query_through_final_partial_and_terminal_callback(self):
        trace = self.run_with_trace()
        self.assertEqual(trace, ['starting', 'initialize', 'query', 'settings', 'open', 'start',
                                 'ready', 'abort', 'close', 'audio.level', 'stopped', 'uninitialize'])

    def test_native_start_error_still_closes_stream_before_com_cleanup(self):
        trace = self.run_with_trace(stream_failure=True)
        self.assertEqual(trace[-4:], ['abort', 'close', 'error', 'uninitialize'])

    def test_terminal_callback_exception_still_releases_owned_com(self):
        trace = self.run_with_trace(terminal_failure=True)
        self.assertEqual(trace[-3:], ['audio.level', 'stopped', 'uninitialize'])

    def test_com_failure_becomes_terminal_status_before_optional_audio_import(self):
        events = []
        with patch('pixeldeck.audio._initialize_com', side_effect=RuntimeError(
                'Windows audio COM initialization failed (HRESULT 0x8007000E)')), \
             patch('pixeldeck.audio._load_sounddevice') as load:
            AudioBackend(input_device=0).run('microphone', 5, threading.Event(), events.append)
        load.assert_not_called()
        self.assertEqual(events[-1]['state'], 'error')
        self.assertIn('0x8007000E', events[-1]['message'])
        self.assertEqual(events[-1]['metered_frames'], 0)


if __name__ == '__main__':
    unittest.main()
