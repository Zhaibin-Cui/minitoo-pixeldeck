import io
import threading
import unittest
from types import SimpleNamespace
from pixeldeck.inputs import decode_push,read_notices
from pixeldeck.sources import MetricReader,SourceWorker

class SourceTests(unittest.TestCase):
    def test_initialization_failure_is_reported_and_rejects_requests(self):
        failed=threading.Event(); events=[]
        def factory(): raise OSError('provider unavailable')
        def callback(event): events.append(event); failed.set()
        worker=SourceWorker(callback,factory); self.addCleanup(worker.close)
        self.assertTrue(failed.wait(1)); self.assertEqual(events[0]['type'],'source.error')
        self.assertFalse(worker.request(('network',),1))

    def test_reset_failure_stops_source_worker_explicitly(self):
        failed=threading.Event()
        class Reader:
            def reset(self): raise OSError('reset failed')
        worker=SourceWorker(lambda event:failed.set(),Reader); self.addCleanup(worker.close)
        worker.request(('network',),1)
        self.assertTrue(failed.wait(1)); self.assertFalse(worker.request(('network',),2))
    def test_optional_missing_is_unavailable_not_faked(self):
        reader=MetricReader(psutil_module=None)
        self.assertFalse(reader.network()['available'])
        self.assertIsNone(reader.network()['rx_bps'])
        self.assertFalse(reader.power()['available'])
    def test_network_rate_baseline_elapsed_and_counter_reset(self):
        times=iter([10,12,13])
        samples=iter([SimpleNamespace(bytes_recv=100,bytes_sent=50),SimpleNamespace(bytes_recv=1100,bytes_sent=250),SimpleNamespace(bytes_recv=1,bytes_sent=1)])
        module=SimpleNamespace(net_io_counters=lambda **kwargs:next(samples))
        reader=MetricReader(module,clock=lambda:next(times))
        self.assertIsNone(reader.network()['rx_bps'])
        value=reader.network(); self.assertEqual(value['rx_bps'],500); self.assertEqual(value['tx_bps'],100)
        self.assertIsNone(reader.network()['rx_bps'])
        reader.reset(); self.assertIsNone(reader.network_previous)
    def test_battery_absent_is_different_from_missing_provider(self):
        module=SimpleNamespace(sensors_battery=lambda:None)
        value=MetricReader(module).power()
        self.assertTrue(value['available']); self.assertFalse(value['present'])
    def test_unknown_battery_time_is_none(self):
        module=SimpleNamespace(sensors_battery=lambda:SimpleNamespace(percent=81,power_plugged=True,secsleft=-2))
        value=MetricReader(module).power()
        self.assertEqual(value['percent'],81); self.assertIsNone(value['seconds_left'])
    def test_worker_coalesces_slow_requests_and_preserves_generation(self):
        entered=threading.Event(); release=threading.Event(); done=threading.Event(); results=[]; calls=[]
        class Reader:
            def reset(self): pass
            def read(self,name):
                calls.append(name)
                if name=='slow': entered.set(); release.wait(2)
                return {'type':name}
        def callback(event):
            results.append(event)
            if event['generation']==100: done.set()
        worker=SourceWorker(callback,Reader); self.addCleanup(worker.close)
        worker.request(('slow',),0); self.assertTrue(entered.wait(1))
        for i in range(1,101): worker.request(('latest',),i)
        release.set(); self.assertTrue(done.wait(2))
        self.assertEqual(calls,['slow','latest'])
        self.assertEqual([e['generation'] for e in results],[0,100])
    def test_build_schema_and_nonexecution(self):
        value=decode_push({'type':'build','state':'running','project':'x'*500,'step':'y'*500,'progress':32})
        self.assertEqual(len(value['project']),20); self.assertEqual(len(value['step']),40)
        for progress in (True,float('nan'),-1,101,'25'):
            with self.assertRaises(ValueError): decode_push({'type':'build','state':'running','progress':progress})
        with self.assertRaises(ValueError): decode_push({'type':'shell.run','command':'anything'})
        events=[]
        read_notices(io.StringIO('{"type":"build","state":"passed","progress":100}\n'),events.append)
        self.assertEqual(events[0]['state'],'passed')

if __name__=='__main__': unittest.main()
