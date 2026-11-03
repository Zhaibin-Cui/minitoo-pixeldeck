"""On-demand host metrics. No hidden sampler, threads, or optional dependencies."""
import os
from pathlib import Path
import sys

class Telemetry:
    def __init__(self):
        self.previous = self._times()

    def _times(self):
        if os.name == "nt":
            import ctypes as c
            from ctypes import wintypes as w
            values = [w.FILETIME() for _ in range(3)]
            if not c.windll.kernel32.GetSystemTimes(*(c.byref(v) for v in values)):
                raise OSError("CPU statistics unavailable")
            idle, kernel, user = [(v.dwHighDateTime<<32)|v.dwLowDateTime for v in values]
            return idle, kernel+user
        if sys.platform.startswith("linux"):
            fields = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            return fields[3]+fields[4], sum(fields)
        return None

    def _memory(self):
        if os.name == "nt":
            import ctypes as c
            class Memory(c.Structure):
                _fields_=[('length',c.c_uint32),('load',c.c_uint32)]+[(f'v{i}',c.c_uint64) for i in range(7)]
            data=Memory(); data.length=c.sizeof(data)
            if not c.windll.kernel32.GlobalMemoryStatusEx(c.byref(data)):
                raise OSError("Memory statistics unavailable")
            return float(data.load)
        if sys.platform.startswith('linux'):
            fields={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
            return 100*(1-fields['MemAvailable']/fields['MemTotal'])
        return None

    def sample(self):
        current=self._times(); cpu=None
        if current is not None and self.previous is not None:
            total=current[1]-self.previous[1]
            if total>0: cpu=max(0,min(100,100*(1-(current[0]-self.previous[0])/total)))
        self.previous=current
        return {'type':'telemetry','cpu':cpu,'memory':self._memory()}
