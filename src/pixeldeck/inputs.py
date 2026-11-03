"""Blocking input streams. The producer callback is the wake-up mechanism."""
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from .config import home

BUTTONS={"Next":"next","Previous":"previous","Play":"activate","Pause":"activate"}

def decode_push(data):
    if not isinstance(data,dict): raise ValueError('Expected a JSON object')
    if data.get('type')=='notice' and isinstance(data.get('text'),str):
        return {'type':'notice','text':data['text'][:80]}
    if data.get('type')=='build':
        state=data.get('state'); progress=data.get('progress')
        project=data.get('project','LOCAL BUILD'); step=data.get('step','')
        if state not in ('idle','running','passed','failed'): raise ValueError('Invalid build state')
        if not isinstance(project,str) or not isinstance(step,str): raise ValueError('Build labels must be strings')
        if progress is not None and (type(progress) not in (int,float) or not math.isfinite(progress) or not 0<=progress<=100):
            raise ValueError('Build progress must be 0..100 or null')
        return {'type':'build','project':project[:20],'state':state,'progress':progress,'step':step[:40]}
    raise ValueError('Expected a notice or build event')

def decode_media(line):
    data=json.loads(line)
    if data.get('type')=='button':
        return {'type':'button','button':BUTTONS[data['value']], 'raw':data['value'],
                'sequence':data['sequence'],'received_at':time.monotonic(),'source':'media'}
    return {'type':'input.status','kind':data.get('type'),'message':str(data.get('value',''))[:300]}

def read_notices(stream, callback):
    while True:
        line=stream.readline(4097)
        if not line: return
        if len(line)>4096:
            callback({'type':'input.status','kind':'error','message':'Notice exceeds 4 KB'})
            while line and not line.endswith('\n'): line=stream.readline(4097)
            continue
        try:
            data=json.loads(line)
            callback(decode_push(data))
        except (ValueError,TypeError) as exc:
            callback({'type':'input.status','kind':'error','message':str(exc)})

def build_bridge():
    if os.name!='nt': raise RuntimeError('Media input requires Windows')
    output=home()/'native'; output.mkdir(parents=True,exist_ok=True)
    script=Path(__file__).parent/'native/build.ps1'
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-OutputDirectory',str(output)],
                   check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    return output/'MediaBridge.exe'

class MediaInput:
    """Supervise the blocking native stream with finite, cancellable retries."""

    class _Run:
        def __init__(self, process, attempt):
            self.process=process; self.attempt=attempt
            self.ready=False; self.expired=False; self.ended=False; self.timer=None
            self.stop_lock=threading.Lock()

    def __init__(self, config, callback, *, process_factory=None, ready_timeout=30.0,
                 restart_delay=1.0, max_restarts=2, stop_timeout=1.0):
        for name,value,allow_zero in (('ready_timeout',ready_timeout,False),
                                      ('restart_delay',restart_delay,True),
                                      ('stop_timeout',stop_timeout,False)):
            if not math.isfinite(value) or value<0 or (not allow_zero and value==0):
                raise ValueError(name+' must be finite and positive'+(' or zero' if allow_zero else ''))
        if type(max_restarts) is not int or not 0<=max_restarts<=2:
            raise ValueError('max_restarts must be 0, 1, or 2')
        executable=home()/'native/MediaBridge.exe'
        if not executable.exists(): raise FileNotFoundError('Run pixeldeck build-input first')
        self.closed=False; self.callback=callback
        self.process=None; self._run=None
        self._stop=threading.Event(); self._state_lock=threading.RLock()
        self._factory=process_factory or subprocess.Popen
        self._command=[str(executable),config.endpoint,str(Path(__file__).parent/'native/silence.wav')]
        self._ready_timeout=ready_timeout; self._restart_delay=restart_delay
        self._max_restarts=max_restarts; self._stop_timeout=stop_timeout
        self.thread=threading.Thread(target=self._read,name='pixeldeck-input',daemon=True); self.thread.start()

    def _emit(self, event, run=None):
        with self._state_lock:
            if not self.closed and (run is None or self._run is run): self.callback(event)

    def _launch(self, attempt):
        with self._state_lock:
            if self._stop.is_set(): return None
            process=self._factory(self._command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,text=True,encoding='utf-8',bufsize=1,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            run=self._Run(process,attempt); self._run=run; self.process=process
            run.timer=threading.Timer(self._ready_timeout,self._deadline,args=(run,))
            run.timer.daemon=True; run.timer.start()
            return run

    def _deadline(self, run):
        with self._state_lock:
            if self.closed or self._run is not run or run.ready or run.ended: return
            run.expired=True
        try:
            self._emit({'type':'input.status','kind':'error','ready':False,'attempt':run.attempt,
                'message':f'Media input did not become ready within {self._ready_timeout:g} s; stopping bridge'},run)
        finally:
            self._stop_child(run,graceful=False)

    def _stop_child(self, run, *, graceful):
        """Bound every wait; only this method writes to the child's stdin."""
        process=run.process
        with run.stop_lock:
            if graceful:
                try:
                    process.stdin.write('stop\n'); process.stdin.flush()
                except (OSError,ValueError): pass
                try: return process.wait(timeout=self._stop_timeout)
                except subprocess.TimeoutExpired: pass
            try: process.terminate()
            except OSError: pass
            try: return process.wait(timeout=self._stop_timeout)
            except subprocess.TimeoutExpired:
                try: process.kill()
                except OSError: pass
                try: return process.wait(timeout=self._stop_timeout)
                except subprocess.TimeoutExpired: return None

    def _read_run(self, run):
        process=run.process; failure=None
        try:
            try:
                for line in process.stdout:
                    with self._state_lock:
                        if self.closed or self._run is not run or run.expired: break
                        event=decode_media(line)
                        if event.get('kind')=='ready':
                            run.ready=True; run.timer.cancel()
                        # EOF supplies the exit code and is the authoritative stop event.
                        if event.get('kind')!='closed': self._emit(event,run)
            except Exception as exc:
                failure=f'Media input read failed: {type(exc).__name__}: {str(exc)[:180]}'
            finally:
                with self._state_lock:
                    run.ended=True; run.timer.cancel()
            if failure or run.expired:
                code=self._stop_child(run,graceful=False)
            else:
                try: code=process.wait(timeout=self._stop_timeout)
                except subprocess.TimeoutExpired:
                    failure='Media input output ended while the bridge was still running'
                    code=self._stop_child(run,graceful=False)
            readiness='after ready' if run.ready else 'before ready'
            reason=f'Media bridge exited with code {code if code is not None else "unknown"} {readiness}'
            if run.expired: reason+=' (readiness deadline expired)'
            if failure: reason+='; '+failure
            return reason,code
        finally:
            # The reader owns stream disposal: never close stdout during a blocking read.
            with run.stop_lock:
                for stream in (process.stdin,process.stdout):
                    if stream is not None:
                        try: stream.close()
                        except (OSError,ValueError): pass

    def _read(self):
        for attempt in range(1,self._max_restarts+2):
            run=None; code=None
            try:
                run=self._launch(attempt)
                if run is None: return
                reason,code=self._read_run(run)
            except Exception as exc:
                reason=f'Media bridge could not start: {type(exc).__name__}: {str(exc)[:180]}'
            if self._stop.is_set(): return
            detail={'exit_code':code,'ready':bool(run and run.ready),'attempt':attempt}
            self._emit({'type':'input.status','kind':'error','message':reason,**detail},run)
            if attempt>self._max_restarts:
                self._emit({'type':'input.status','kind':'stopped',
                    'message':f'Media input stopped after {attempt} launch attempts. {reason}',**detail},run)
                return
            self._emit({'type':'input.status','kind':'retrying',
                'message':f'Retrying media input in {self._restart_delay:g} s ({attempt}/{self._max_restarts}). {reason}',
                **detail},run)
            if self._stop.wait(self._restart_delay): return

    def close(self):
        with self._state_lock:
            if self.closed: return
            self.closed=True; self._stop.set(); run=self._run
            if run is not None: run.timer.cancel()
        if run is not None: self._stop_child(run,graceful=True)
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=self._stop_timeout*3+0.5)
