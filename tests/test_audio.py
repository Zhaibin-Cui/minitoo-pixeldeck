"""Audio driver checks with fake callback streams; no hardware is opened."""
from array import array
import builtins
import json
import threading
import unittest
from unittest.mock import patch

from pixeldeck.audio import AudioBackend, _levels, _load_sounddevice, _tone, list_devices


class FakeStream:
    def __init__(self, owner, direction, values):
        self.owner, self.direction, self.values = owner, direction, values
        self.started = self.aborted = self.closed = False
        self.output = None

    def start(self):
        self.started = True
        if self.owner.fail_start == self.direction:
            raise RuntimeError('Simulated stream start failure')
        frames = int(self.values['samplerate']*.25)
        callback = self.values['callback']
        self.owner.native_threads.append(threading.get_ident())
        if self.direction == 'input':
            data = array('h', (12000 if index % 2 else -12000 for index in range(frames)))
            callback(data.tobytes(), frames, None, self.owner.xrun)
        else:
            self.output = bytearray(frames*self.values['channels']*2)
            callback(self.output, frames, None, self.owner.xrun)

    def abort(self):
        self.aborted = True
        self.values['finished_callback']()

    def close(self):
        self.closed = True


class FakeSoundDevice:
    class CallbackAbort(Exception):
        pass

    def __init__(self, *, fail_start=None, xrun=False):
        self.fail_start, self.xrun = fail_start, xrun
        self.streams, self.queries, self.checked, self.native_threads = [], [], [], []
        self.devices = [
            {'index': 0, 'name': 'Example microphone AA:BB:CC:DD:EE:FF', 'hostapi': 0,
             'max_input_channels': 4, 'max_output_channels': 0, 'default_samplerate': 16000},
            {'index': 1, 'name': 'Example speaker', 'hostapi': 0,
             'max_input_channels': 0, 'max_output_channels': 8, 'default_samplerate': 48000},
        ]

    def query_hostapis(self):
        return [{'name': 'Example Host API'}]

    def query_devices(self, index=None):
        self.queries.append(index)
        return self.devices if index is None else self.devices[index]

    def check_input_settings(self, **values):
        self.checked.append(('input', values))

    def check_output_settings(self, **values):
        self.checked.append(('output', values))

    def RawInputStream(self, **values):
        stream = FakeStream(self, 'input', values)
        self.streams.append(stream)
        return stream

    def RawOutputStream(self, **values):
        stream = FakeStream(self, 'output', values)
        self.streams.append(stream)
        return stream


class AudioTests(unittest.TestCase):
    def test_device_enumeration_is_serializable_redacted_and_does_not_start_streams(self):
        sd = FakeSoundDevice()
        devices = list_devices('MICROPHONE', sd_module=sd)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['index'], 0)
        self.assertEqual(devices[0]['input_channels'], 4)
        self.assertEqual(devices[0]['hostapi'], 'Example Host API')
        self.assertNotIn('AA:BB:CC:DD:EE:FF', json.dumps(devices))
        self.assertEqual(sd.streams, [])
        self.assertEqual(sd.checked, [])

    def test_constructor_and_pre_cancelled_job_do_not_import_audio_support(self):
        stopped = threading.Event()
        stopped.set()
        with patch('pixeldeck.audio._load_sounddevice') as load:
            backend = AudioBackend()
            events = []
            backend.run('microphone', 1, stopped, events.append)
        load.assert_not_called()
        self.assertEqual(events[-1]['state'], 'stopped')

    def test_missing_dependency_explains_optional_extra(self):
        original_import = builtins.__import__

        def unavailable(name, *args, **kwargs):
            if name == 'sounddevice':
                raise ImportError('Optional dependency excluded by test')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=unavailable):
            with self.assertRaisesRegex(RuntimeError, r'minitoo-pixeldeck\[audio\]'):
                _load_sounddevice()

    def test_invalid_mode_or_duration_never_queries_devices(self):
        for mode, seconds in (('unknown', 1), ('speaker', 0), ('speaker', 11),
                              ('microphone', float('nan')), ('duplex', float('inf'))):
            with self.subTest(mode=mode, seconds=seconds):
                sd = FakeSoundDevice()
                events = []
                AudioBackend(sd_module=sd).run(mode, seconds, threading.Event(), events.append)
                self.assertEqual(sd.queries, [])
                self.assertEqual(sd.streams, [])
                self.assertEqual(events[-1]['state'], 'error')

    def test_explicit_indices_and_direction_are_required_without_default_fallback(self):
        for index in (None, -1, True, 'Example speaker', 0):
            with self.subTest(output_device=index):
                sd = FakeSoundDevice()
                events = []
                AudioBackend(output_device=index, sd_module=sd).run(
                    'speaker', 1, threading.Event(), events.append)
                self.assertEqual(sd.streams, [])
                self.assertNotIn(None, sd.queries)
                self.assertEqual(events[-1]['state'], 'error')

    def test_duplex_uses_individual_rates_and_never_echoes_microphone_data(self):
        sd = FakeSoundDevice()
        stopped = threading.Event()
        events, level_threads = [], []

        def receive(event):
            events.append(event)
            if event['type'] == 'audio.level':
                level_threads.append(threading.get_ident())
                stopped.set()

        AudioBackend(0, 1, sd).run('duplex', 1, stopped, receive)
        input_stream, output_stream = sd.streams
        self.assertEqual(input_stream.values['device'], 0)
        self.assertEqual(output_stream.values['device'], 1)
        self.assertEqual(input_stream.values['samplerate'], 16000)
        self.assertEqual(output_stream.values['samplerate'], 48000)
        self.assertEqual(input_stream.values['channels'], 1)
        self.assertEqual(output_stream.values['channels'], 2)
        self.assertTrue(all(stream.aborted and stream.closed for stream in sd.streams))
        level = next(event for event in events if event['type'] == 'audio.level')
        self.assertAlmostEqual(level['rms'], 12000/32768)
        self.assertAlmostEqual(level['peak'], 12000/32768)
        self.assertLessEqual(len(level['waveform']), 32)
        self.assertTrue(all(-1 <= value <= 1 for value in level['waveform']))
        self.assertTrue(0 <= level['elapsed'] <= 1)
        self.assertTrue(all(thread not in sd.native_threads for thread in level_threads))
        self.assertLess(max(abs(value) for value in memoryview(output_stream.output).cast('h')), 1000)
        self.assertEqual(events[-1]['state'], 'stopped')

    def test_partial_start_failure_closes_both_streams_and_keeps_error_terminal(self):
        sd = FakeSoundDevice(fail_start='output')
        events = []
        AudioBackend(0, 1, sd).run('duplex', 1, threading.Event(), events.append)
        self.assertEqual(len(sd.streams), 2)
        self.assertTrue(all(stream.closed and stream.aborted for stream in sd.streams))
        self.assertEqual(events[-1]['state'], 'error')
        self.assertNotIn('ready', [event.get('state') for event in events])
        self.assertNotIn('stopped', [event.get('state') for event in events])

    def test_xruns_are_reported_without_native_callback_logging(self):
        sd = FakeSoundDevice(xrun=True)
        stopped = threading.Event()
        events = []

        def receive(event):
            events.append(event)
            if event['type'] == 'audio.level':
                stopped.set()

        AudioBackend(input_device=0, sd_module=sd).run('microphone', 1, stopped, receive)
        self.assertEqual(next(event['xruns'] for event in events if event['type'] == 'audio.level'), 1)
        self.assertEqual(events[-1]['xruns'], 1)

    def test_user_cancellation_closes_promptly_without_waiting_for_duration(self):
        sd = FakeSoundDevice()
        stopped = threading.Event()
        events = []

        def receive(event):
            events.append(event)
            if event.get('state') == 'ready':
                stopped.set()

        AudioBackend(output_device=1, sd_module=sd).run('speaker', 10, stopped, receive)
        self.assertEqual(events[-1]['state'], 'stopped')
        self.assertTrue(sd.streams[0].closed)

    def test_quiet_generation_and_preview_bounds(self):
        for mode, maximum in (('speaker', 1400), ('duplex', 700)):
            pcm = _tone(8000, 1, mode, threading.Event())
            self.assertEqual(len(pcm), 16000)
            self.assertLessEqual(max(abs(value) for value in memoryview(pcm).cast('h')), maximum)
        self.assertEqual(_levels(b''), (0.0, 0.0, []))
        rms, peak, waveform = _levels(array('h', [-32768, 32767]*100).tobytes())
        self.assertTrue(0 <= rms <= 1 and 0 <= peak <= 1)
        self.assertEqual(len(waveform), 32)


if __name__ == '__main__':
    unittest.main()
