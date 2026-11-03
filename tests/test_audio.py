"""Audio driver checks with fake callback streams; no hardware is opened."""
from array import array
import builtins
import json
import math
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pixeldeck.audio import AudioBackend, _WindowMeter, _levels, _load_sounddevice, _stream_latency_ms, _tone, list_devices


class FakeStream:
    def __init__(self, owner, direction, values):
        self.owner, self.direction, self.values = owner, direction, values
        self.started = self.aborted = self.closed = False
        self.output = None
        self.latency = .012 if direction == 'input' else .034

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

    def test_actual_stream_latencies_are_reported_independently_of_the_low_request(self):
        sd = FakeSoundDevice()
        stopped = threading.Event()
        events = []

        def receive(event):
            events.append(event)
            if event.get('state') == 'ready':
                stopped.set()

        AudioBackend(0, 1, sd).run('duplex', 5, stopped, receive)
        for event in (next(event for event in events if event.get('state') == 'ready'), events[-1]):
            self.assertEqual(event['input_latency_ms'], 12)
            self.assertEqual(event['output_latency_ms'], 34)
        self.assertTrue(all(stream.values['latency'] == 'low' for stream in sd.streams))

    def test_unavailable_or_invalid_native_latency_stays_unknown(self):
        for value in (None, -1, float('nan'), float('inf'), 1e308, True, '0.01', (0.01, 0.02)):
            with self.subTest(value=value):
                self.assertIsNone(_stream_latency_ms(SimpleNamespace(latency=value)))
        self.assertIsNone(_stream_latency_ms(object()))

        class Unavailable:
            @property
            def latency(self):
                raise RuntimeError('Native latency unavailable')

        self.assertIsNone(_stream_latency_ms(Unavailable()))
        self.assertEqual(_stream_latency_ms(SimpleNamespace(latency=0)), 0)

    def test_inactive_stream_direction_has_no_reported_latency(self):
        sd = FakeSoundDevice()
        stopped = threading.Event()
        events = []

        def receive(event):
            events.append(event)
            if event.get('state') == 'ready':
                stopped.set()

        AudioBackend(input_device=0, sd_module=sd).run('microphone', 5, stopped, receive)
        self.assertEqual(events[-1]['input_latency_ms'], 12)
        self.assertIsNone(events[-1]['output_latency_ms'])

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
        self.assertTrue(all(stream.values['latency'] == 'low' for stream in sd.streams))
        self.assertTrue(all(stream.values['blocksize'] == 0 for stream in sd.streams))
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

    def test_speaker_repeats_motif_across_buffers_until_cancelled(self):
        sd = FakeSoundDevice()
        sd.devices[1]['default_samplerate'] = 8000
        stopped = threading.Event()
        events, rendered = [], bytearray()

        def receive(event):
            events.append(event)
            if event.get('state') != 'ready':
                return
            stream = sd.streams[0]
            rendered.extend(stream.output)
            # Unequal buffers cross the one-second boundary several times.
            for frames in (2000, 4000, 4000, 4000, 4000):
                output = bytearray(frames*stream.values['channels']*2)
                stream.values['callback'](output, frames, None, False)
                rendered.extend(output)
            stopped.set()
            output = bytearray([255]*64)
            with self.assertRaises(sd.CallbackAbort):
                stream.values['callback'](output, 16, None, False)
            self.assertEqual(output, bytes(64))

        AudioBackend(output_device=1, sd_module=sd).run('speaker', 5, stopped, receive)
        cycle_bytes = 8000*2*2
        self.assertEqual(rendered[:cycle_bytes], rendered[cycle_bytes:2*cycle_bytes])
        self.assertTrue(any(rendered[2*cycle_bytes:]))
        self.assertLessEqual(max(abs(value) for value in memoryview(rendered).cast('h')), 1400)
        self.assertTrue(sd.streams[0].aborted and sd.streams[0].closed)
        self.assertEqual(events[-1]['state'], 'stopped')

    def test_fragmented_callbacks_capture_a_transient_before_the_old_sample_boundary(self):
        meter = _WindowMeter(8000, 1, 5)
        # Ten ten-millisecond callbacks: only an early callback has a transient.
        # A full measurement is available at 100 ms, without waiting for 250 ms.
        for block in range(10):
            data = array('h', [0]*80)
            if block == 2:
                data[37] = -24576
            meter.offer(data.tobytes(), 80)
        record = meter.take()
        self.assertEqual(record[1], 800)
        meter.measure(record)
        self.assertAlmostEqual(meter.latest['rms'], .75/math.sqrt(800))
        self.assertEqual(meter.latest['peak'], .75)
        self.assertIn(-.75, meter.latest['waveform'])
        self.assertLessEqual(len(meter.latest['waveform']), 32)
        self.assertEqual(meter.summary()['metered_frames'], 800)
        self.assertEqual(meter.summary()['dropped_frames'], 0)

    def test_session_rms_weights_partial_window_samples_and_counts_frames_not_channels(self):
        meter = _WindowMeter(8000, 2, 5)
        meter.offer(array('h', [16384]*1600).tobytes(), 800)
        meter.offer(array('h', [0]*800).tobytes(), 400)
        meter.measure(meter.take())
        self.assertIsNone(meter.take())
        meter.finish()
        meter.measure(meter.take())
        self.assertEqual(meter.latest['rms'], 0)
        self.assertEqual(meter.latest['elapsed'], .15)
        summary = meter.summary()
        self.assertAlmostEqual(summary['session_rms'], .5*math.sqrt(2/3))
        self.assertEqual(summary['session_peak'], .5)
        self.assertEqual(summary['metered_frames'], 1200)
        self.assertEqual(summary['dropped_frames'], 0)
        self.assertIsNone(meter.take())

    def test_meter_overrun_and_lock_contention_are_bounded_and_report_missing_frames(self):
        meter = _WindowMeter(8000, 1, 5)
        sizes = [len(buffer) for buffer in meter.buffers]
        meter.offer(array('h', [1000]*10000).tobytes(), 10000)
        self.assertEqual(meter.pending, 4)
        self.assertEqual(meter.dropped_frames, 6800)
        with meter.lock:
            # Producer must return without waiting on the consumer's lock.
            meter.offer(array('h', [1000]*80).tobytes(), 80)
        meter.measure(meter.take())
        # A freed slot can accept new data after overflow; final partial wraps.
        meter.offer(array('h', [1000]*80).tobytes(), 80)
        meter.finish()
        while (record := meter.take()) is not None:
            meter.measure(record)
        self.assertEqual([len(buffer) for buffer in meter.buffers], sizes)
        self.assertEqual(meter.metered_frames, 3280)
        self.assertEqual(meter.dropped_frames, 6880)
        self.assertEqual(meter.seen_frames, meter.metered_frames+meter.dropped_frames)
        self.assertAlmostEqual(meter.summary()['session_rms'], 1000/32768)

    def test_cancelled_partial_window_is_processed_after_close_before_terminal_status(self):
        sd = FakeSoundDevice()
        stopped = threading.Event()
        events = []

        def short_start(stream):
            stream.started = True
            stream.values['callback'](array('h', [-8192]*160).tobytes(), 160, None, False)

        def receive(event):
            if event['type'] == 'audio.level':
                self.assertTrue(sd.streams[0].closed)
            events.append(event)
            if event.get('state') == 'ready':
                stopped.set()

        with patch.object(FakeStream, 'start', short_start):
            AudioBackend(input_device=0, sd_module=sd).run('microphone', 5, stopped, receive)
        terminal = events[-1]
        self.assertEqual(terminal['state'], 'stopped')
        self.assertEqual(terminal['session_rms'], .25)
        self.assertEqual(terminal['session_peak'], .25)
        self.assertEqual(terminal['metered_frames'], 160)
        self.assertEqual(terminal['dropped_frames'], 0)
        self.assertAlmostEqual(terminal['elapsed'], .01)
        self.assertEqual([event['type'] for event in events],
                         ['audio.status', 'audio.status', 'audio.level', 'audio.status'])
        self.assertTrue(sd.streams[0].aborted and sd.streams[0].closed)

    def test_final_summary_includes_a_partial_peak_even_when_live_event_is_throttled(self):
        sd = FakeSoundDevice()
        stopped = threading.Event()
        events = []

        def receive(event):
            events.append(event)
            if event['type'] == 'audio.level':
                partial = array('h', [0]*1600)
                partial[17] = 30000
                sd.streams[0].values['callback'](partial.tobytes(), 1600, None, False)
                stopped.set()

        AudioBackend(input_device=0, sd_module=sd).run('microphone', 5, stopped, receive)
        self.assertEqual(sum(event['type'] == 'audio.level' for event in events), 1)
        terminal = events[-1]
        self.assertEqual(terminal['state'], 'stopped')
        self.assertEqual(terminal['session_peak'], 30000/32768)
        self.assertAlmostEqual(terminal['session_rms'],
                               math.sqrt((4000*12000**2+30000**2)/5600)/32768)
        self.assertEqual(terminal['metered_frames'], 5600)
        self.assertEqual(terminal['dropped_frames'], 0)
        self.assertAlmostEqual(terminal['elapsed'], .35)

    def test_error_stays_terminal_after_pending_window_measurement(self):
        sd = FakeSoundDevice(fail_start='output')
        events = []
        AudioBackend(0, 1, sd).run('duplex', 5, threading.Event(), events.append)
        self.assertEqual(events[-1]['state'], 'error')
        self.assertEqual(events[-1]['metered_frames'], 4000)
        self.assertAlmostEqual(events[-1]['session_peak'], 12000/32768)
        self.assertFalse(any(event.get('state') == 'stopped' for event in events))


if __name__ == '__main__':
    unittest.main()
