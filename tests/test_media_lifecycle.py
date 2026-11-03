"""Event-driven bridge lifecycle tests with pipes that never access hardware."""
import json
import queue
import subprocess
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pixeldeck.inputs import MediaInput


class FakeStdout:
    def __init__(self):
        self.items=queue.Queue(); self.closed=False; self.reading=False

    def __iter__(self): return self

    def __next__(self):
        self.reading=True
        try: item=self.items.get()
        finally: self.reading=False
        if item is None: raise StopIteration
        return item

    def close(self):
        if self.reading: raise AssertionError('stdout closed while the reader was blocked')
        self.closed=True


class FakeStdin:
    def __init__(self, process):
        self.process=process; self.closed=False; self.text=''

    def write(self, text):
        if self.closed: raise ValueError('closed stdin')
        self.text+=text

    def flush(self):
        if self.process.graceful and 'stop\n' in self.text: self.process.finish(0)

    def close(self): self.closed=True


class FakeProcess:
    def __init__(self, *, graceful=True, terminate_works=True):
        self.stdout=FakeStdout(); self.stdin=FakeStdin(self)
        self.graceful=graceful; self.terminate_works=terminate_works
        self.done=threading.Event(); self.lock=threading.Lock(); self.returncode=None
        self.terminations=0; self.kills=0

    def emit(self, kind, value='', **extra):
        self.stdout.items.put(json.dumps({'type':kind,'value':value,**extra})+'\n')

    def finish(self, code):
        with self.lock:
            if self.done.is_set(): return
            self.returncode=code; self.done.set(); self.stdout.items.put(None)

    def wait(self, timeout):
        if not self.done.wait(timeout): raise subprocess.TimeoutExpired('fake-bridge',timeout)
        return self.returncode

    def terminate(self):
        self.terminations+=1
        if self.terminate_works: self.finish(-15)

    def kill(self):
        self.kills+=1; self.finish(-9)


class Factory:
    def __init__(self, *results):
        self.results=results; self.calls=0; self.condition=threading.Condition()

    def __call__(self, *args, **kwargs):
        with self.condition:
            result=self.results[self.calls]; self.calls+=1; self.condition.notify_all()
        if isinstance(result,Exception): raise result
        return result

    def wait_for_calls(self, count):
        with self.condition:
            return self.condition.wait_for(lambda:self.calls>=count,timeout=1)


class Events:
    def __init__(self): self.items=[]; self.condition=threading.Condition()

    def __call__(self, event):
        with self.condition:
            self.items.append(event); self.condition.notify_all()

    def wait_for(self, predicate):
        with self.condition:
            return self.condition.wait_for(lambda:any(predicate(event) for event in self.items),timeout=2)

    def kind(self, kind): return [event for event in self.items if event.get('kind')==kind]


class MediaLifecycleTests(unittest.TestCase):
    def start(self, factory, events, **options):
        defaults={'ready_timeout':1,'restart_delay':0,'stop_timeout':0.03}
        defaults.update(options)
        with patch('pixeldeck.inputs.Path.exists',return_value=True):
            media=MediaInput(SimpleNamespace(endpoint='test endpoint'),events,process_factory=factory,**defaults)
        self.addCleanup(media.close)
        return media

    def assert_finished(self, media, *processes):
        media.thread.join(timeout=1)
        self.assertFalse(media.thread.is_alive())
        for process in processes:
            self.assertTrue(process.done.is_set())
            self.assertTrue(process.stdin.closed)
            self.assertTrue(process.stdout.closed)

    def test_ready_only_after_native_event_and_one_button_callback(self):
        process=FakeProcess(); factory=Factory(process); events=Events()
        media=self.start(factory,events)
        self.assertTrue(factory.wait_for_calls(1))
        self.assertEqual(events.kind('ready'),[])
        process.emit('ready','Input connected')
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='ready'))
        process.emit('button','Pause',sequence=17)
        self.assertTrue(events.wait_for(lambda event:event.get('type')=='button'))
        media.close()
        buttons=[event for event in events.items if event['type']=='button']
        self.assertEqual(len(buttons),1)
        self.assertEqual((buttons[0]['button'],buttons[0]['sequence']),('activate',17))
        self.assertEqual(events.kind('error'),[])
        self.assert_finished(media,process)

    def test_silent_startup_exit_reports_code_and_stops_after_two_restarts(self):
        processes=[FakeProcess() for _ in range(3)]
        for process in processes: process.finish(-1073741819)
        factory=Factory(*processes); events=Events(); media=self.start(factory,events)
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='stopped'))
        self.assertEqual(factory.calls,3)
        self.assertEqual(len(events.kind('retrying')),2)
        errors=events.kind('error')
        self.assertEqual([event['attempt'] for event in errors],[1,2,3])
        for event in errors:
            self.assertEqual(event['exit_code'],-1073741819)
            self.assertFalse(event['ready'])
            self.assertIn('before ready',event['message'])
        self.assertIn('-1073741819',events.kind('stopped')[0]['message'])
        self.assert_finished(media,*processes)

    def test_ready_does_not_reset_the_session_retry_budget(self):
        processes=[FakeProcess() for _ in range(3)]
        for process in processes:
            process.emit('ready'); process.emit('closed'); process.finish(23)
        factory=Factory(*processes); events=Events(); media=self.start(factory,events)
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='stopped'))
        self.assertEqual(len(events.kind('ready')),3)
        self.assertEqual(factory.calls,3)
        self.assertEqual(events.kind('closed'),[])
        for event in events.kind('error'):
            self.assertTrue(event['ready']); self.assertEqual(event['exit_code'],23)
            self.assertIn('after ready',event['message'])
        self.assert_finished(media,*processes)

    def test_readiness_deadline_terminates_and_kills_a_hung_bridge(self):
        process=FakeProcess(graceful=False,terminate_works=False); events=Events()
        media=self.start(Factory(process),events,ready_timeout=0.03,max_restarts=0)
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='stopped'))
        self.assertGreaterEqual(process.terminations,1); self.assertEqual(process.kills,1)
        stopped=events.kind('stopped')[0]
        self.assertEqual(stopped['exit_code'],-9); self.assertFalse(stopped['ready'])
        self.assertIn('readiness deadline expired',stopped['message'])
        self.assert_finished(media,process)

    def test_close_cancels_a_long_backoff_without_another_launch(self):
        process=FakeProcess(); process.finish(12)
        factory=Factory(process); events=Events()
        media=self.start(factory,events,restart_delay=60)
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='retrying'))
        started=time.monotonic(); media.close()
        self.assertLess(time.monotonic()-started,0.5)
        self.assertEqual(factory.calls,1)
        self.assert_finished(media,process)

    def test_close_cancels_deadline_and_bounds_child_shutdown(self):
        process=FakeProcess(graceful=False,terminate_works=False)
        factory=Factory(process); events=Events(); media=self.start(factory,events,ready_timeout=60)
        self.assertTrue(factory.wait_for_calls(1))
        started=time.monotonic(); media.close(); media.close()
        self.assertLess(time.monotonic()-started,0.5)
        self.assertEqual(factory.calls,1); self.assertEqual(process.kills,1)
        self.assertEqual(events.items,[])
        self.assert_finished(media,process)

    def test_old_deadline_cannot_stop_or_overwrite_new_ready_session(self):
        first=FakeProcess(); second=FakeProcess(); factory=Factory(first,second); events=Events()
        media=self.start(factory,events)
        self.assertTrue(factory.wait_for_calls(1))
        with media._state_lock: old_run=media._run
        first.finish(8)
        self.assertTrue(factory.wait_for_calls(2))
        second.emit('ready','Second session')
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='ready'))
        count=len(events.items); media._deadline(old_run)
        self.assertEqual(len(events.items),count)
        self.assertEqual(second.terminations,0)
        self.assertFalse(media._run.expired)
        media.close(); self.assert_finished(media,first,second)

    def test_process_launch_failure_is_reported_and_can_recover(self):
        process=FakeProcess(); process.emit('ready')
        factory=Factory(OSError('Cannot launch bridge'),process); events=Events()
        media=self.start(factory,events)
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='ready'))
        self.assertEqual(factory.calls,2)
        self.assertIn('Cannot launch bridge',events.kind('error')[0]['message'])
        self.assertIsNone(events.kind('error')[0]['exit_code'])
        media.close(); self.assert_finished(media,process)

    def test_malformed_native_output_stops_child_with_explicit_read_error(self):
        process=FakeProcess(); process.stdout.items.put('not json\n'); events=Events()
        media=self.start(Factory(process),events,max_restarts=0)
        self.assertTrue(events.wait_for(lambda event:event.get('kind')=='stopped'))
        self.assertIn('Media input read failed',events.kind('stopped')[0]['message'])
        self.assertEqual(events.kind('stopped')[0]['exit_code'],-15)
        self.assert_finished(media,process)


if __name__=='__main__': unittest.main()
