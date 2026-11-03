"""Blocking input streams. The producer callback is the wake-up mechanism."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from .config import home

BUTTONS={"Next":"next","Previous":"previous","Play":"activate","Pause":"activate"}

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
            if not isinstance(data,dict) or data.get('type')!='notice' or not isinstance(data.get('text'),str):
                raise ValueError('Expected {"type":"notice","text":"..."}')
            callback({'type':'notice','text':data['text'][:80]})
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
    def __init__(self, config, callback):
        executable=home()/'native/MediaBridge.exe'
        if not executable.exists(): raise FileNotFoundError('Run pixeldeck build-input first')
        self.closed=False; self.callback=callback
        self.process=subprocess.Popen([str(executable),config.endpoint,str(Path(__file__).parent/'native/silence.wav')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',bufsize=1,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.thread=threading.Thread(target=self._read,name='pixeldeck-input',daemon=True); self.thread.start()
    def _read(self):
        try:
            for line in self.process.stdout:
                if self.closed: break
                self.callback(decode_media(line))
        except Exception as exc:
            if not self.closed: self.callback({'type':'input.status','kind':'error','message':str(exc)})
        finally:
            if not self.closed: self.callback({'type':'input.status','kind':'closed','message':'Media input ended'})
    def close(self):
        self.closed=True
        try:
            self.process.stdin.write('stop\n'); self.process.stdin.flush()
        except (OSError,ValueError): pass
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate(); self.process.wait(timeout=5)
        self.thread.join(timeout=1)
        self.process.stdin.close(); self.process.stdout.close()
