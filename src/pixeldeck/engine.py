"""Latest-frame rendering pipeline. No polling, unbounded history, or replay backlog."""
from collections import deque
import hashlib
import threading
import time
from .protocol import SIZE

class Latest:
    def __init__(self):
        self.condition = threading.Condition()
        self.value = None
        self.closed = False
        self.replaced = 0

    def put(self, item):
        with self.condition:
            if self.closed:
                return False
            if self.value is not None:
                self.replaced += 1
            self.value = item
            self.condition.notify()
            return True

    def get(self):
        with self.condition:
            self.condition.wait_for(lambda: self.value is not None or self.closed)
            if self.closed:
                return None
            item, self.value = self.value, None
            return item

    def close(self):
        with self.condition:
            self.closed = True
            self.value = None
            self.condition.notify_all()

class FramePump:
    """Own one sink and one writer. sink_factory returns an object with show/close.

    A frame already on the wire completes before the newest pending state is sent.
    on_status runs on a worker thread; marshal GUI changes onto your UI event loop.
    """
    def __init__(self, sink_factory, on_status=lambda event: None, retries=3):
        self.factory, self.on_status, self.retries = sink_factory, on_status, retries
        self.pending = Latest()
        self.stop = threading.Event()
        self.guard = threading.Lock()
        self.sink = None
        self.last = None
        self.digest = None
        self.sequence = 0
        self.acknowledged = 0
        self.timings = deque(maxlen=256)
        self.thread = threading.Thread(target=self._run, name="pixeldeck-tx", daemon=True)
        self.thread.start()

    def submit(self, image, received_at=None):
        if image.size != SIZE:
            raise ValueError("Frames must be 160 x 128")
        picture = image.convert("RGB").copy()
        digest = hashlib.sha256(picture.tobytes()).digest()
        with self.guard:
            if self.stop.is_set() or digest == self.digest:
                return False
            self.digest = digest
            self.sequence += 1
            self.last = (self.sequence, picture, received_at)
            return self.pending.put(self.last)

    def reconnect(self, error=None):
        """Called by a sink's disconnect event, including while the screen is idle."""
        if not self.stop.is_set():
            self.on_status({"type": "link.lost", "message": str(error)})
            with self.guard:
                if self.last:
                    self.pending.put(self.last)

    def _run(self):
        try:
            while not self.stop.is_set():
                job = self.pending.get()
                if job is None:
                    return
                if job[0] == self.acknowledged and self.sink is not None and getattr(self.sink, "healthy", True):
                    continue
                for attempt in range(self.retries + 1):
                    if self.stop.is_set():
                        return
                    try:
                        if self.sink is not None and not getattr(self.sink, "healthy", True):
                            self.sink.close()
                            self.sink = None
                        if self.sink is None:
                            self.sink = self.factory()
                        number, picture, received_at = job
                        report = self.sink.show(picture)
                        self.acknowledged = number
                        report.update(type="frame.ack", sequence=number, replaced=self.pending.replaced)
                        if received_at is not None:
                            report["input_to_ack_ms"] = round((time.monotonic()-received_at)*1000, 2)
                        self.timings.append(report["transfer_ms"])
                        self.on_status(report)
                        break
                    except Exception as exc:
                        if self.stop.is_set():
                            return
                        self.on_status({"type": "link.error", "attempt": attempt+1, "message": str(exc)})
                        if self.sink:
                            self.sink.close()
                            self.sink = None
                        if attempt == self.retries:
                            self.stop.set()
                            self.on_status({"type": "link.stopped", "message": "Reconnect budget exhausted; restart the session"})
                            return
                        if self.stop.wait(min(attempt+1, 3)):
                            return
                        with self.guard:
                            job = self.last or job
        finally:
            if self.sink:
                self.sink.close()

    def close(self):
        self.stop.set()
        self.pending.close()
        if self.sink:
            self.sink.close()
        self.thread.join(timeout=7)
        if self.thread.is_alive():
            raise RuntimeError("Display worker did not exit")
