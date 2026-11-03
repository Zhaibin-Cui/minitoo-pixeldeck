"""Serialize audio jobs off the UI thread and discard superseded events."""
import threading

from .engine import Latest


class AudioWorker:
    def __init__(self, callback, *, input_device=None, output_device=None, backend_factory=None):
        if backend_factory is None:
            from .audio import AudioBackend
            backend_factory = AudioBackend
        self.callback = callback
        self.factory = backend_factory
        self.devices = dict(input_device=input_device, output_device=output_device)
        self.pending = Latest()
        self.guard = threading.Lock()
        self.closed = False
        self.generation = 0
        self.cancelled = threading.Event()
        self.thread = threading.Thread(target=self._run, name='pixeldeck-audio', daemon=True)
        self.thread.start()

    def request(self, mode, seconds=5):
        if mode not in ('speaker', 'microphone', 'duplex', None):
            raise ValueError('Unknown audio mode')
        if type(seconds) not in (int, float) or not 0 < seconds <= 10:
            raise ValueError('Audio duration must be within 0..10 seconds')
        with self.guard:
            if self.closed:
                return False
            self.cancelled.set()
            self.cancelled = threading.Event()
            self.generation += 1
            self.pending.put((self.generation, mode, seconds, self.cancelled))
            return True

    def stop(self):
        return self.request(None)

    def _emit(self, generation, event):
        with self.guard:
            if self.closed or generation != self.generation:
                return
        self.callback(dict(event, generation=generation))

    def _run(self):
        while True:
            job = self.pending.get()
            if job is None:
                return
            generation, mode, seconds, cancelled = job
            if cancelled.is_set():
                continue
            if mode is None:
                self._emit(generation, {'type': 'audio.status', 'state': 'stopped', 'message': 'Audio stopped'})
                continue
            emit = lambda event: self._emit(generation, event)
            try:
                backend = self.factory(**self.devices)
                backend.run(mode, seconds, cancelled, emit)
            except Exception as exc:
                emit({'type': 'audio.status', 'state': 'error', 'mode': mode,
                      'message': f'Audio unavailable: {type(exc).__name__}: {exc}'[:200]})

    def close(self):
        with self.guard:
            if self.closed:
                return
            self.closed = True
            self.cancelled.set()
            self.pending.close()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise TimeoutError('Audio backend did not release within 3 seconds')
