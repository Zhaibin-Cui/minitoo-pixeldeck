"""Authenticated local stop request, not a watched STOP file."""
import json
from multiprocessing.connection import Listener, Client, AuthenticationError
import os
from pathlib import Path
import secrets
import threading
import uuid

class Control:
    def __init__(self, runtime, callback):
        self.path=Path(runtime)/'control.json'
        self.family='AF_PIPE' if os.name=='nt' else 'AF_UNIX'
        self.address=(r'\\.\pipe\pixeldeck-'+uuid.uuid4().hex) if os.name=='nt' else str(Path(runtime)/('control-'+uuid.uuid4().hex[:8]+'.sock'))
        self.key=secrets.token_bytes(32); self.closed=False; self.callback=callback
        self.listener=Listener(self.address,family=self.family,authkey=self.key)
        self.path.write_text(json.dumps({'address':self.address,'key':self.key.hex(),'family':self.family}),encoding='utf-8')
        if os.name!='nt': self.path.chmod(0o600)
        self.thread=threading.Thread(target=self._run,daemon=True); self.thread.start()
    def _run(self):
        while not self.closed:
            try:
                with self.listener.accept() as connection:
                    data=json.loads(connection.recv_bytes(1024))
                    ok=isinstance(data,dict) and data.get('command')=='stop'
                    connection.send_bytes(json.dumps({'ok':ok}).encode())
                    if ok: self.callback(); return
            except (OSError,ValueError,EOFError,AuthenticationError):
                if self.closed: return
    def close(self):
        self.closed=True; self.listener.close()
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('address')==self.address: self.path.unlink()
        except (OSError,ValueError): pass

def stop(runtime):
    path=Path(runtime)/'control.json'
    if not path.exists(): return False
    data=json.loads(path.read_text(encoding='utf-8'))
    try:
        with Client(data['address'],family=data['family'],authkey=bytes.fromhex(data['key'])) as connection:
            connection.send_bytes(b'{"command":"stop"}')
            if not connection.poll(5): raise TimeoutError('Stop was not acknowledged')
            return json.loads(connection.recv_bytes(1024)).get('ok',False)
    except (FileNotFoundError,ConnectionRefusedError): return False
