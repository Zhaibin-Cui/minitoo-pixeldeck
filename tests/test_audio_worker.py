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

    def test_superseded_run_cannot_publish_stale_data(self):
        started = threading.Event()
        stopped = threading.Event()
        events = []

        class Backend:
            def __init__(self, **devices):
                self.devices = devices

            def run(self, mode, seconds, cancelled, emit):
                if mode == 'speaker':
                    emit({'type': 'audio.status', 'state': 'stopped'})
                    return
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
            worker.request('speaker')
            self.assertTrue(stopped.wait(2))
            self.assertFalse(any(event['type'] == 'audio.level' for event in events))
        finally:
            worker.close()

    def test_manual_stop_retains_the_active_runs_terminal_summary(self):
        started, finished = threading.Event(), threading.Event()
        events = []

        class Backend:
            def __init__(self, **devices):
                pass

            def run(self, mode, seconds, cancelled, emit):
                started.set()
                if not cancelled.wait(2):
                    raise AssertionError('Stop was not delivered')
                emit({'type': 'audio.status', 'state': 'stopped', 'session_peak': .6,
                      'session_rms': .2, 'metered_frames': 4000, 'dropped_frames': 0})

        def receive(event):
            events.append(event)
            finished.set()

        worker = AudioWorker(receive, backend_factory=Backend)
        try:
            worker.request('microphone')
            self.assertTrue(started.wait(1))
            generation = worker.generation
            worker.stop()
            self.assertTrue(finished.wait(1))
            self.assertEqual(worker.generation, generation)
            self.assertEqual(events[-1]['session_peak'], .6)
            self.assertEqual(events[-1]['metered_frames'], 4000)
        finally:
            worker.close()

    def test_stop_after_completion_preserves_queued_summary_or_error_generation(self):
        for state in ('stopped', 'error'):
            with self.subTest(state=state):
                entered, idle = threading.Event(), threading.Event()
                events = []

                class Backend:
                    def __init__(self, **devices):
                        pass

                    def run(self, mode, seconds, cancelled, emit):
                        entered.set()
                        emit({'type': 'audio.status', 'state': state, 'mode': mode,
                              'message': 'Completed' if state == 'stopped' else 'Native stream failed',
                              'session_peak': .8, 'session_rms': .2,
                              'metered_frames': 8000, 'dropped_frames': 0})

                worker = AudioWorker(events.append, backend_factory=Backend)
                original_get = worker.pending.get

                def observed_get():
                    # The next dequeue happens after backend.finally cleared
                    # active_generation, while events remain queued for the UI.
                    if entered.is_set():
                        idle.set()
                    return original_get()

                worker.pending.get = observed_get
                try:
                    worker.request('microphone')
                    self.assertTrue(idle.wait(1))
                    self.assertIsNone(worker.active_generation)
                    generation = worker.generation
                    self.assertEqual(worker.completed_generation, generation)
                    self.assertTrue(worker.stop())
                    self.assertTrue(worker.stop())
                    self.assertEqual(worker.generation, generation)
                    # This is the same generation filter used by the UI.
                    visible = [event for event in events if event['generation'] == worker.generation]
                    self.assertEqual(len(visible), 1)
                    self.assertEqual(visible[0]['state'], state)
                    self.assertEqual(visible[0]['session_peak'], .8)
                    self.assertEqual(visible[0]['metered_frames'], 8000)
                finally:
                    worker.close()

    def test_stop_cancels_unstarted_request_and_its_completed_stop_is_idempotent(self):
        started, release, stopped = threading.Event(), threading.Event(), threading.Event()
        calls, events = [], []

        class Backend:
            def __init__(self, **devices):
                pass

            def run(self, mode, seconds, cancelled, emit):
                calls.append(mode)
                started.set()
                if not release.wait(2):
                    raise AssertionError('Test did not release the running backend')
                emit({'type': 'audio.status', 'state': 'stopped', 'session_peak': .9})

        def receive(event):
            events.append(event)
            if event.get('state') == 'stopped':
                stopped.set()

        worker = AudioWorker(receive, backend_factory=Backend)
        try:
            worker.request('microphone')
            self.assertTrue(started.wait(1))
            worker.request('speaker')
            pending_generation = worker.generation
            worker.stop()
            self.assertGreater(worker.generation, pending_generation)
            stop_generation = worker.generation
            release.set()
            self.assertTrue(stopped.wait(1))
            self.assertEqual(calls, ['microphone'])
            self.assertEqual(worker.completed_generation, stop_generation)
            self.assertEqual(len(events), 1)
            self.assertNotIn('session_peak', events[0])
            worker.stop()
            self.assertEqual(worker.generation, stop_generation)
        finally:
            release.set()
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
