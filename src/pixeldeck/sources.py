"""On-demand data reads on one worker; the visible cartridge owns subscriptions.

There is no background sampling loop. Requests arrive from explicit UI deadlines;
slow requests are coalesced and stale generations are rejected by the host.
"""
from datetime import datetime, timezone
import importlib
import os
from pathlib import Path
import shutil
import threading
import time
from .engine import Latest
from .telemetry import Telemetry

AUTO = object()

class MetricReader:
    def __init__(self, psutil_module=AUTO, clock=time.monotonic):
        if psutil_module is AUTO:
            try: psutil_module=importlib.import_module('psutil')
            except ImportError: psutil_module=None
        self.psutil=psutil_module
        self.clock=clock
        self.cpu=None
        self.network_previous=None

    def reset(self):
        self.cpu=None
        self.network_previous=None

    def read(self, name):
        if name=='telemetry':
            if self.cpu is None: self.cpu=Telemetry()
            event=self.cpu.sample(); event['sampled_at']=self.clock()
            return event
        if name=='wallclock':
            now=datetime.now(timezone.utc)
            return {'type':'wallclock','local':now.astimezone().isoformat(),'utc':now.isoformat()}
        if name=='network': return self.network()
        if name=='power': return self.power()
        if name=='storage': return self.storage()
        raise ValueError('Unknown source: '+name)

    def network(self):
        result={'type':'network','available':False,'rx_bps':None,'tx_bps':None}
        if self.psutil is None: return result
        counters=self.psutil.net_io_counters(pernic=False,nowrap=True)
        if counters is None: return result
        now=self.clock(); current=(now,counters.bytes_recv,counters.bytes_sent)
        previous,self.network_previous=self.network_previous,current
        result['available']=True
        if previous:
            elapsed=now-previous[0]
            rx=current[1]-previous[1]; tx=current[2]-previous[2]
            if elapsed>0 and rx>=0 and tx>=0:
                result.update(rx_bps=rx/elapsed,tx_bps=tx/elapsed)
        return result

    def power(self):
        result={'type':'power','available':False,'present':False,'percent':None,'plugged':None,'seconds_left':None}
        if self.psutil is None or not hasattr(self.psutil,'sensors_battery'): return result
        battery=self.psutil.sensors_battery(); result['available']=True
        if battery is None: return result
        result.update(present=True,percent=float(battery.percent),plugged=bool(battery.power_plugged),
                      seconds_left=battery.secsleft if battery.secsleft>=0 else None)
        return result

    def storage(self):
        # Local fixed disks only on Windows: no network shares or removable drives.
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetDriveTypeW.argtypes=[wintypes.LPCWSTR]
            kernel.GetDriveTypeW.restype=wintypes.UINT
            mask=kernel.GetLogicalDrives()
            candidates=[f'{chr(65+i)}:\\' for i in range(26) if mask&(1<<i)]
            paths=[path for path in candidates if kernel.GetDriveTypeW(path)==3]
        else:
            # One system filesystem without third-party enumeration dependencies.
            paths=[str(Path.home().anchor or '/')]
        volumes=[]
        for path in paths[:8]:
            try:
                usage=shutil.disk_usage(path)
                volumes.append({'label':f'VOLUME {len(volumes)+1:02}', 'total':usage.total,'free':usage.free})
            except OSError: continue
        return {'type':'storage','available':bool(volumes),'volumes':volumes}

class SourceWorker:
    """A single I/O worker with a one-request mailbox and generation-tagged results."""
    def __init__(self, callback, reader_factory=MetricReader):
        self.callback=callback; self.reader_factory=reader_factory
        self.pending=Latest(); self.stopping=threading.Event()
        self.thread=threading.Thread(target=self._run,name='pixeldeck-sources',daemon=True)
        self.thread.start()

    def request(self, names, generation):
        return self.pending.put((tuple(names),generation))

    def _run(self):
        try: reader=self.reader_factory()
        except Exception:
            self._fail(); return
        generation=None
        while not self.stopping.is_set():
            job=self.pending.get()
            if job is None: return
            names,new_generation=job
            if generation!=new_generation:
                try: reader.reset()
                except Exception:
                    self._fail(); return
                generation=new_generation
            if not names: continue
            events=[]
            for name in names:
                try: events.append(reader.read(name))
                except Exception:
                    # Do not publish host-specific paths or provider exception details.
                    events.append({'type':name,'available':False,'cpu':None,'memory':None,
                                   'rx_bps':None,'tx_bps':None,'volumes':[],
                                   'present':False,'percent':None,'plugged':None,'seconds_left':None})
            if not self.stopping.is_set():
                self.callback({'type':'source.result','generation':generation,'events':events})

    def _fail(self):
        self.stopping.set(); self.pending.close()
        self.callback({'type':'source.error','message':'Source provider failed to initialize; restart the session'})

    def close(self):
        self.stopping.set(); self.pending.close(); self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError('Source worker is still waiting on a host API; no further results will be delivered')
