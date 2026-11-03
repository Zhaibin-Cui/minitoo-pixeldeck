import threading
import unittest

from pixeldeck.audio_worker import AudioWorker


class AudioWorkerTests(unittest.TestCase):
    def test_idle_does_not_load_backend_and_close_wakes_worker(self):
        def forbidden(**devices):
            raise AssertionError('Idle preview opened audio')
        worker = AudioWorker(lambda event: None, backend_factory=forbidden)
        worker.close()
        self.assertFalse(worker.thread.is_alive())
        self.assertFalse(worker.request('speaker'))

    def test_cancelled_run_cannot_publish_stale_data(self):
        started = threading.Event()
        stopped = threading.Event()
        events = []

        class Backend:
            def __init__(self, **devices):
                self.devices = devices

            def run(self, mode, seconds, cancelled, emit):
                started.set()
                self.assert_devices = self.devices == {'input_device': 2, 'output_device': 3}
                if not self.assert_devices:
                    raise AssertionError('Device selection changed')
                if not cancelled.wait(2):
                    raise AssertionError('Stop did not reach backend')
                emit({'type': 'audio.level', 'peak': 1})

        def receive(event):
            events.append(event)
            if event.get('state') == 'stopped':
                stopped.set()

        worker = AudioWorker(receive, input_device=2, output_device=3, backend_factory=Backend)
        try:
            worker.request('microphone')
            self.assertTrue(started.wait(1))
            worker.stop()
            self.assertTrue(stopped.wait(2))
            self.assertFalse(any(event['type'] == 'audio.level' for event in events))
        finally:
            worker.close()

    def test_backend_failure_is_visible_without_retrying(self):
        done = threading.Event()
        events = []

        def missing(**devices):
            raise ImportError('Install the audio extra')

        def receive(event):
            events.append(event)
            done.set()

        worker = AudioWorker(receive, backend_factory=missing)
        try:
            worker.request('speaker')
            self.assertTrue(done.wait(1))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['state'], 'error')
            self.assertIn('audio extra', events[0]['message'])
        finally:
            worker.close()

    def test_invalid_jobs_never_reach_worker(self):
        worker = AudioWorker(lambda event: None, backend_factory=lambda **devices: None)
        try:
            for mode, duration in (('unknown', 5), ('speaker', 0), ('speaker', 11),
                                   ('speaker', True), ('speaker', float('nan'))):
                with self.assertRaises(ValueError):
                    worker.request(mode, duration)
        finally:
            worker.close()
