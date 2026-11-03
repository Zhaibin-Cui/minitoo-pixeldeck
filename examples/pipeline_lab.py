"""Finite offline pipeline demo: first/latest frames, deduplication and recovery.

Two small injected sinks demonstrate the real FramePump without device access.
Events, not polling loops, coordinate the deliberately blocked first upload.
"""
import json
import threading

from PIL import Image

from pixeldeck import FramePump


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def latest_and_recovery():
    entered, release, latest_ack, recovered = (threading.Event() for _ in range(4))
    seen, reports, sinks = [], [], []

    class SimulatedSink:
        def __init__(self, blocked=False):
            self.blocked = blocked
            self.healthy = True

        def show(self, image):
            seen.append(image.getpixel((0, 0)))
            if self.blocked:
                self.blocked = False
                entered.set()
                check(release.wait(2), 'Simulated upload release deadline expired')
            return {'transfer_ms': 1.0, 'bytes': 1, 'chunks': 1, 'retransmissions': 0}

        def close(self):
            self.healthy = False
            release.set()

    def factory():
        sink = SimulatedSink(blocked=not sinks)
        sinks.append(sink)
        return sink

    def status(event):
        if event['type'] == 'frame.ack':
            reports.append(dict(event))
            if len(reports) == 2:
                latest_ack.set()
            elif len(reports) == 3:
                recovered.set()

    pump = FramePump(factory, status, retries=0)
    final = Image.new('RGB', (160, 128), (100, 0, 0))
    try:
        pump.submit(Image.new('RGB', (160, 128)))
        check(entered.wait(2), 'First simulated upload did not start')
        for number in range(1, 101):
            pump.submit(Image.new('RGB', (160, 128), (number, 0, 0)))
        check(len(seen) == 1, 'Submit waited for or bypassed the blocked sink')
        release.set()
        check(latest_ack.wait(2), 'Latest frame was not acknowledged')
        check(seen == [(0, 0, 0), (100, 0, 0)], 'Obsolete intermediate frames were replayed')
        check(not pump.submit(final), 'Identical frame was not suppressed')
        sinks[0].healthy = False
        pump.reconnect(ConnectionError('Simulated idle disconnect'))
        check(recovered.wait(2), 'Idle disconnect did not restore the latest frame')
        check(len(sinks) == 2 and seen[-1] == (100, 0, 0), 'Recovery used the wrong state')
        check(reports[-1]['sequence'] == reports[-2]['sequence'], 'Recovery changed frame identity')
    finally:
        pump.close()
    check(not pump.thread.is_alive() and all(not sink.healthy for sink in sinks),
          'Pipeline resources were not released')
    return {'submitted_frames': 101, 'sent_before_disconnect': 2,
            'obsolete_pending_frames_replaced': reports[1]['replaced'],
            'identical_frame_suppressed': True, 'idle_recovery_sent_latest': True,
            'worker_released': True}


def finite_failure():
    stopped = threading.Event()
    attempts = 0

    def fail():
        nonlocal attempts
        attempts += 1
        raise ConnectionError('Simulated unavailable sink')

    def status(event):
        if event['type'] == 'link.stopped':
            stopped.set()

    pump = FramePump(fail, status, retries=0)
    try:
        pump.submit(Image.new('RGB', (160, 128)))
        check(stopped.wait(2), 'Exhausted retry budget was not reported')
        check(attempts == 1, 'A zero-retry budget attempted another connection')
        check(not pump.submit(Image.new('RGB', (160, 128), 'red')), 'Stopped pump accepted a frame')
    finally:
        pump.close()
    return {'connection_attempts': attempts, 'budget_exhausted_event': True,
            'new_frames_rejected': True, 'worker_released': not pump.thread.is_alive()}


def main():
    print(json.dumps({'simulation': True, 'hardware_accessed': False,
                      'latest_and_recovery': latest_and_recovery(), 'finite_failure': finite_failure()}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
