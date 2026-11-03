"""An event-driven demo host; Bluetooth and media input are explicit options."""
from collections import deque
import json
import logging
from logging.handlers import RotatingFileHandler
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from .config import home
from .control import Control
from .demos import CATALOG, create
from .deck import Deck
from .driver import MiniToo
from .engine import FramePump
from .inputs import MediaInput, read_notices
from .instance import InstanceLock
from .telemetry import Telemetry

class Application:
    def __init__(self, config, demo='buddy', send=False, media=False, stdin=False, duration=600):
        self.config=config; self.send=send; self.media_enabled=media; self.stdin=stdin; self.duration=duration
        self.runtime=home(); self.runtime.mkdir(parents=True,exist_ok=True)
        self.lock=InstanceLock(self.runtime/'instance.lock')
        self.deck=Deck(demo); self.closing=threading.Event()
        self.events=queue.Queue(128); self.buttons=queue.Queue(32)
        self.timer=None; self.telemetry=None; self.pump=None; self.media=None; self.control=None
        self.log=logging.getLogger('pixeldeck.'+str(id(self))); self.log.setLevel(logging.INFO)
        self.handler=RotatingFileHandler(self.runtime/'events.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
        self.handler.setFormatter(logging.Formatter('%(asctime)s %(message)s')); self.log.addHandler(self.handler)
        self.root=tk.Tk(); self.root.title('MiniToo Pixeldeck'); self.root.configure(bg='#080d19'); self.root.resizable(False,False)
        tk.Label(self.root,text='P I X E L D E C K',font=('Consolas',20,'bold'),bg='#080d19',fg='#54edff').pack(pady=(16,4))
        tk.Label(self.root,text='SMALL SCREEN. BIG PERSONALITY.',font=('Consolas',10),bg='#080d19',fg='#7088ae').pack(pady=(0,12))
        self.screen=tk.Label(self.root,bg='#080d19'); self.screen.pack(padx=20)
        self.choice=ttk.Combobox(self.root,values=self.deck.keys,state='readonly',width=28)
        self.choice.set(demo); self.choice.pack(pady=12)
        self.choice.bind('<<ComboboxSelected>>',lambda _:self.post({'type':'select','demo':self.choice.get()}))
        row=tk.Frame(self.root,bg='#080d19'); row.pack()
        for label,key in (('< PREV','previous'),('ACTIVATE','activate'),('NEXT >','next')):
            tk.Button(row,text=label,width=14,bg='#152440',fg='#e5f5ff',activebackground='#253554',relief='flat',command=lambda k=key:self.button(k)).pack(side='left',padx=3)
        self.status=tk.StringVar(value='LIVE DEVICE' if send else 'PREVIEW / NO DEVICE')
        tk.Label(self.root,textvariable=self.status,bg='#080d19',fg='#9affb3',wraplength=470,font=('Consolas',10)).pack(pady=14)
        self.root.bind('<Left>',lambda _:self.button('previous')); self.root.bind('<Right>',lambda _:self.button('next'))
        self.root.bind('<Return>',lambda _:self.button('activate')); self.root.bind('<space>',lambda _:self.button('activate'))
        self.root.bind('<<Events>>',self.process); self.root.bind('<<Quit>>',lambda _:self.close())
        self.root.bind('<<Released>>',lambda _:self.root.destroy())
        self.root.protocol('WM_DELETE_WINDOW',self.close); self.root.after(0,self.start)

    def post(self,event):
        if self.closing.is_set(): return False
        target=self.buttons if event['type']=='button' else self.events
        try: target.put_nowait(event)
        except queue.Full:
            self.log.error('event_overflow %s',event['type'])
            return False
        try: self.root.event_generate('<<Events>>',when='tail')
        except (RuntimeError,tk.TclError): return False
        return True

    def button(self,key):
        self.post({'type':'button','button':key,'raw':'KEYBOARD','source':'desktop','received_at':time.monotonic()})

    def start(self):
        try:
            self.control=Control(self.runtime,lambda:self.root.event_generate('<<Quit>>',when='tail'))
        except Exception as exc: self.status.set('Local stop unavailable: '+str(exc))
        if self.send:
            def connect():
                return MiniToo(self.config,on_disconnect=lambda exc:self.pump.reconnect(exc))
            self.pump=FramePump(connect,self.post,retries=self.config.retries)
        if self.media_enabled:
            try: self.media=MediaInput(self.config,self.post)
            except Exception as exc: self.status.set('Input unavailable: '+str(exc)); self.log.error('input_start %s',exc)
        if self.stdin:
            threading.Thread(target=read_notices,args=(sys.stdin,self.post),daemon=True).start()
        self.draw()
        if self.duration: self.root.after(self.duration*1000,self.close)

    def process(self,_=None):
        if self.closing.is_set(): return
        dirty=False; received_at=None
        for _ in range(160):
            try: event=self.buttons.get_nowait()
            except queue.Empty:
                try: event=self.events.get_nowait()
                except queue.Empty: break
            kind=event.get('type'); now=time.monotonic()
            if kind in ('button','select','tick','notice','telemetry'):
                try:
                    if kind=='tick' and self.deck.active.key=='pulse' and not self.deck.active.held:
                        if self.telemetry is None: self.telemetry=Telemetry()
                        self.deck.handle(self.telemetry.sample(),now)
                    self.deck.handle(event,now); dirty=True
                    if kind=='button':
                        received_at=event.get('received_at')
                        self.log.info('input %s',json.dumps(dict(event,page=self.deck.active.key),ensure_ascii=True))
                except Exception as exc:
                    self.status.set('Event rejected: '+str(exc)); self.log.exception('event_rejected')
            else:
                self.log.info('%s %s',kind,json.dumps(event,ensure_ascii=True))
                if kind=='frame.ack': self.status.set(f"LIVE / ACK {event['sequence']} / {event['transfer_ms']:.0f} ms / skipped {event['replaced']}")
                else: self.status.set(str(event.get('message',kind))[:160])
        if dirty: self.draw(received_at)

    def draw(self,received_at=None):
        now=time.monotonic(); image=self.deck.active.render(now)
        photo=ImageTk.PhotoImage(image.resize((480,384),Image.Resampling.NEAREST))
        self.screen.configure(image=photo); self.screen.image=photo
        self.choice.set(self.deck.active.key)
        if self.pump: self.pump.submit(image,received_at)
        image.save(self.runtime/'latest.png')  # Replaces one preview, never an image archive.
        if self.timer is not None: self.root.after_cancel(self.timer); self.timer=None
        if self.deck.active.key!='pulse' or self.deck.active.held: self.telemetry=None
        elif self.telemetry is None: self.telemetry=Telemetry()
        delay=self.deck.active.next_delay(now)
        if delay is not None:
            self.timer=self.root.after(max(1,round(delay*1000)),lambda:self.post({'type':'tick'}))

    def close(self):
        if self.closing.is_set(): return
        self.closing.set()
        if self.timer is not None: self.root.after_cancel(self.timer)
        self.status.set('Releasing device and input session...')
        def release():
            for resource in (self.pump,self.media,self.control):
                if resource:
                    try: resource.close()
                    except Exception: self.log.exception('release_error')
            self.log.info('session_closed'); self.lock.close()
            self.handler.close(); self.log.removeHandler(self.handler)
            try: self.root.event_generate('<<Released>>',when='tail')
            except (RuntimeError,tk.TclError): pass
        threading.Thread(target=release,daemon=True).start()

    def run(self): self.root.mainloop()
