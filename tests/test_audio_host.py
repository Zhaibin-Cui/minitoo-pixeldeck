"""Hidden host integration with fake audio, source and control workers."""
import os
import tempfile
import unittest
from unittest.mock import patch

from pixeldeck.config import DeviceConfig


class FakeAudioWorker:
    def __init__(self, callback, **devices):
        self.callback = callback
        self.devices = devices
        self.generation = 0
        self.requests = []
        self.stops = 0
        self.closed = False

    def request(self, mode, seconds):
        if self.closed:
            return False
        self.generation += 1
        self.requests.append((mode, seconds))
        return True

    def stop(self):
        self.generation += 1
        self.stops += 1
        return True

    def emit(self, kind, generation=None, **fields):
        self.callback({'type': 'audio.'+kind,
                       'generation': self.generation if generation is None else generation,
                       **fields})

    def close(self):
        self.closed = True


class FakeSourceWorker:
    def __init__(self, callback):
        self.closed = False

    def request(self, names, generation):
        return not self.closed

    def close(self):
        self.closed = True


class FakeControl:
    def __init__(self, runtime, callback):
        self.closed = False

    def close(self):
        self.closed = True


@unittest.skipUnless(os.name == 'nt', 'Windows hidden GUI integration')
class AudioHostTests(unittest.TestCase):
    def run_host(self, scenario, *, audio=True):
        from pixeldeck.app import Application

        workers = []
        failures = []

        def worker(callback, **devices):
            result = FakeAudioWorker(callback, **devices)
            workers.append(result)
            return result

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'PIXELDECK_HOME': directory}), \
                patch('pixeldeck.audio_worker.AudioWorker', side_effect=worker), \
                patch('pixeldeck.app.SourceWorker', FakeSourceWorker), \
                patch('pixeldeck.app.Control', FakeControl):
            app = Application(DeviceConfig(), demo='audio', duration=0, audio=audio,
                              audio_input=7 if audio else None, audio_output=9 if audio else None)
            app.root.withdraw()

            def timeout():
                failures.append(AssertionError('Hidden audio host did not finish within five seconds'))
                app.close()
                app.root.destroy()

            deadline = app.root.after(5000, timeout)

            def exercise():
                try:
                    scenario(app, workers[0] if workers else None)
                except Exception as exc:
                    failures.append(exc)
                finally:
                    app.root.after_cancel(deadline)
                    app.close()

            app.root.after(30, exercise)
            app.run()
            self.assertIsNotNone(app.release_thread)
            self.assertFalse(app.release_thread.is_alive())
            self.assertIsNone(app.root)
            self.assertTrue(app.lock.file.closed)
            self.assertTrue(app.source_worker.closed)
            self.assertTrue(app.control.closed)
            self.assertIsNone(app.pump)
            self.assertIsNone(app.media)
            self.assertEqual(len(workers), 1 if audio else 0)
            self.assertTrue(all(item.closed for item in workers))
        if failures:
            raise failures[0]

    @staticmethod
    def action(app, button):
        app.button(button)
        app.process()

    def test_only_activate_requests_the_selected_mode_and_explicit_devices(self):
        def scenario(app, worker):
            self.assertEqual(worker.requests, [])
            self.assertEqual(worker.devices, {'input_device': 7, 'output_device': 9})
            for index, mode in enumerate(('speaker', 'microphone', 'duplex')):
                if index:
                    self.action(app, 'next')
                self.assertEqual(len(worker.requests), index)
                self.action(app, 'activate')
                self.assertEqual(worker.requests[-1], (mode, 5))
                worker.emit('status', state='stopped', mode=mode, message='Test finished')
                app.process()
            self.assertEqual(len(worker.requests), 3)

        self.run_host(scenario)

    def test_navigation_away_cancels_and_hidden_stop_updates_the_audio_page(self):
        def scenario(app, worker):
            self.action(app, 'activate')
            generation = worker.generation
            app.post({'type': 'select', 'demo': 'buddy'})
            app.process()
            self.assertEqual(app.deck.active.key, 'buddy')
            self.assertEqual(worker.stops, 1)
            self.assertGreater(worker.generation, generation)
            worker.emit('status', state='stopped', message='Audio stopped')
            app.process()
            self.assertEqual(app.deck.demos['audio'].state, 'stopped')
            self.assertEqual(app.audio_status.get(), 'Audio stopped')
            self.assertEqual(app.deck.active.key, 'buddy')

        self.run_host(scenario)

    def test_current_status_and_levels_update_ui_including_stop_and_error(self):
        def scenario(app, worker):
            self.action(app, 'next')
            self.action(app, 'activate')
            worker.emit('status', state='ready', mode='microphone', message='Microphone test ready')
            worker.emit('level', mode='microphone', rms=.25, peak=.75,
                        waveform=[-.5, 0, .5], elapsed=1.5)
            app.process()
            lab = app.deck.demos['audio']
            self.assertEqual((lab.state, lab.rms, lab.waveform), ('ready', .25, (-.5, 0., .5)))
            self.assertEqual(app.audio_status.get(), 'Microphone test ready')
            live_frame = app.last_preview.tobytes()
            worker.emit('status', state='stopped', message='Audio stopped')
            app.process()
            self.assertEqual(lab.state, 'stopped')
            self.assertNotEqual(app.last_preview.tobytes(), live_frame)
            worker.emit('status', state='error', message='Selected microphone unavailable')
            app.process()
            self.assertEqual(lab.state, 'error')
            self.assertEqual(app.audio_status.get(), 'Selected microphone unavailable')
            self.assertFalse(lab.active)

        self.run_host(scenario)

    def test_old_generation_status_and_levels_cannot_overwrite_current_run(self):
        def scenario(app, worker):
            self.action(app, 'activate')
            old_generation = worker.generation
            worker.emit('status', state='stopped', message='First run finished')
            app.process()
            self.action(app, 'activate')
            worker.emit('status', state='ready', mode='speaker', message='Current run ready')
            worker.emit('level', mode='speaker', rms=.2, peak=.4, waveform=[0, .4], elapsed=.5)
            app.process()
            frame = app.last_preview.tobytes()
            worker.emit('status', generation=old_generation, state='error', message='Obsolete failure')
            worker.emit('level', generation=old_generation, rms=float('nan'), waveform=[1]*33)
            app.process()
            lab = app.deck.demos['audio']
            self.assertEqual((lab.state, lab.rms), ('ready', .2))
            self.assertEqual(app.audio_status.get(), 'Current run ready')
            self.assertEqual(app.last_preview.tobytes(), frame)

        self.run_host(scenario)

    def test_disabled_audio_explains_requirement_without_constructing_worker(self):
        def scenario(app, worker):
            self.assertIsNone(worker)
            self.action(app, 'activate')
            self.assertEqual(app.deck.demos['audio'].state, 'error')
            self.assertIn('--audio', app.audio_status.get())
            self.assertIsNone(app.audio)

        self.run_host(scenario, audio=False)

    def test_close_releases_worker_during_an_active_request(self):
        def scenario(app, worker):
            self.action(app, 'activate')
            worker.emit('status', state='ready', mode='speaker', message='Current run ready')
            app.process()
            self.assertEqual(app.deck.demos['audio'].state, 'ready')
            self.assertFalse(worker.closed)

        self.run_host(scenario)


if __name__ == '__main__':
    unittest.main()
