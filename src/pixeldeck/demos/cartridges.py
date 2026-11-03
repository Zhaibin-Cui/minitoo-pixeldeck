"""Original procedural demos: no downloaded sprite sheets or fonts."""
from collections import deque
import math
import textwrap
from ..pixels import Canvas, INK, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD
from .base import Demo, Animation

class Pulse(Demo):
    key, title = "pulse", "Pulse // system telemetry"
    description = "A cyan CPU waveform and memory meter. Activate freezes the sample."
    def __init__(self):
        self.samples = deque(maxlen=61)
        self.ram = None
        self.held = False
    def handle(self, event, now):
        if event.get("type") == "button": self.held = not self.held
        if event.get("type") == "telemetry" and not self.held:
            self.samples.append(event.get("cpu"))
            self.ram = event.get("memory")
    def next_delay(self, now): return None if self.held else 1.0
    def render(self, now):
        c = Canvas(); c.header("PULSE", "01"); c.grid()
        value = self.samples[-1] if self.samples else None
        c.text(7,29,"CPU",MUTED)
        c.text(7,42,"--" if value is None else f"{value:.0f}",CYAN,size=3)
        c.text(68,55,"%",CYAN)
        c.text(100,29,"MEM",MUTED)
        c.text(100,44,"--" if self.ram is None else f"{self.ram:.0f}%",PINK)
        for i in range(10):
            c.d.rectangle((101+i*5,58,103+i*5,66), fill=PINK if self.ram is not None and i<self.ram/10 else LINE)
        values = list(self.samples)
        points = [(154-(len(values)-1-i)*2,105-v*.30) for i,v in enumerate(values) if v is not None]
        if len(points)>1:
            c.d.polygon([(points[0][0],106),*points,(points[-1][0],106)],fill="#12333f")
            c.d.line(points,fill=CYAN,width=1)
            x,y=points[-1]; c.d.rectangle((x-1,y-1,x+1,y+1),fill=WHITE)
        c.text(7,76,"LAST 61 SAMPLES",MUTED)
        c.footer("HOLD / ACTIVATE TO RESUME" if self.held else "LIVE / ACTIVATE TO HOLD")
        return c.image

class Buddy(Animation):
    key, title = "buddy", "Bit Buddy // tiny companion"
    description = "A little CRT creature with blinks, antennae and a heart reaction."
    def __init__(self):
        super().__init__(); self.cheer_until = 0
    def handle(self, event, now):
        if event.get("type") == "button": self.cheer_until = now+2.5
    def render(self, now):
        c=Canvas(); c.header("BIT BUDDY","02",MINT)
        t=now; happy=now<self.cheer_until; bob=round(math.sin(t*3)*2)
        for i in range(13):
            x=(i*41+9)%160; y=27+(i*23)%77
            c.d.point((x,y), fill=MUTED if (int(t*2)+i)%5 else MINT)
        c.d.ellipse((42,101,118,108),fill="#1b253b")
        c.d.rectangle((52,41+bob,107,86+bob),fill="#334a64")
        c.d.rectangle((49,44+bob,110,82+bob),fill="#bdd7d9")
        c.d.rectangle((55,48+bob,104,77+bob),fill="#142b36")
        c.d.rectangle((77,33+bob,81,41+bob),fill=MUTED)
        c.d.rectangle((75,29+bob,83,34+bob),fill=PINK if happy else MINT)
        c.d.rectangle((56,86+bob,66,96+bob),fill="#6d94a8")
        c.d.rectangle((94,86+bob,104,96+bob),fill="#6d94a8")
        c.d.rectangle((52,94+bob,67,99+bob),fill=CYAN)
        c.d.rectangle((93,94+bob,108,99+bob),fill=CYAN)
        blink = t%4.7>4.35
        for x in (63,88):
            if happy:
                c.d.line((x,61+bob,x+3,58+bob,x+6,61+bob),fill=MINT,width=2)
            else:
                c.d.rectangle((x,57+bob,x+6,59+bob if blink else 66+bob),fill=MINT)
        c.d.line((76,70+bob,83,70+bob),fill=WHITE)
        if happy:
            for i in range(4):
                c.heart(28+i*31,31+int((i*11-t*16)%30),PINK,1 if i%2 else 2)
        c.footer("THANK YOU, HUMAN!" if happy else "ACTIVATE / SAY HELLO",MINT)
        return c.image

class Rain(Animation):
    key, title = "rain", "Neon Rain // code weather"
    description = "Deterministic code waterfalls. Activate pauses without an idle timer."
    def render(self, now):
        c=Canvas(); t=self.time(now)
        for col in range(19):
            head=int((t*(13+(col*7)%23)+col*29)%150)-15
            for trail in range(8):
                y=head-trail*9
                if 21<y<109:
                    color=WHITE if trail==0 else (PINK if col%5==0 else CYAN) if trail<3 else "#245568"
                    c.text(5+col*8,y,"0123456789ABCDEF"[(col*7+trail*3+int(t*2))%16],color)
        c.header("NEON RAIN","03",PINK)
        c.footer("PAUSED / ACTIVATE TO FLOW" if self.paused else "ACTIVATE / FREEZE THE RAIN")
        return c.image

class Orbit(Animation):
    key, title = "orbit", "Orbital // deep-space signal"
    description = "A ringed planet, orbiting satellite and deterministic starfield."
    def render(self, now):
        c=Canvas(); t=self.time(now)
        for i in range(38):
            x=int((i*47-t*(2+i%5))%160); y=24+(i*31)%85
            c.d.rectangle((x,y,x+(i%7==0),y+(i%7==0)),fill=WHITE if i%6==0 else MUTED)
        c.d.ellipse((54,43,107,96),fill="#44365d",outline="#b38ce4",width=2)
        for y in range(51,91,6):
            span=math.sqrt(max(0,25**2-(y-69)**2))
            c.d.line((81-span,y,81+span,y),fill="#7b5ea0",width=2)
        c.d.arc((34,57,125,84),5,177,fill=PINK,width=3)
        a=t*.65; x=int(80+62*math.cos(a)); y=int(69+34*math.sin(a))
        c.d.rectangle((x-3,y-3,x+3,y+3),fill=WHITE)
        c.d.rectangle((x-9,y-2,x-5,y+2),fill=CYAN)
        c.d.rectangle((x+5,y-2,x+9,y+2),fill=CYAN)
        c.header("ORBITAL","04",PINK)
        c.footer("ORBIT PAUSED" if self.paused else "ACTIVATE / SUSPEND TIME")
        return c.image

class Focus(Demo):
    key, title = "focus", "Focus Foundry // time in pixels"
    description = "A one-minute hourglass driven by elapsed time, not frame count."
    def __init__(self):
        self.remaining=60.; self.started=None
    def left(self, now): return max(0,self.remaining-(now-self.started if self.started is not None else 0))
    def handle(self,event,now):
        left=self.left(now)
        if event.get("type")=="button":
            if left<=0: self.remaining,self.started=60.,now
            elif self.started is None: self.started=now
            else: self.remaining,self.started=left,None
        elif event.get("type")=="tick" and left<=0:
            self.remaining,self.started=0.,None
    def next_delay(self,now): return min(1/3,max(.01,self.left(now))) if self.started is not None else None
    def render(self,now):
        c=Canvas(); c.header("FOCUS FOUNDRY","05",GOLD)
        left=self.left(now); progress=1-left/60
        c.d.polygon([(17,35),(61,35),(61,44),(43,63),(43,71),(61,89),(61,101),(17,101),(17,89),(35,71),(35,63),(17,44)],fill=PANEL,outline=GOLD)
        sand=int(18*(1-progress))
        if sand: c.d.polygon([(22,43),(56,43),(39,43+sand)],fill=GOLD)
        base=int(24*progress)
        if base: c.d.polygon([(22,96),(56,96),(39,96-base)],fill=GOLD)
        if self.started is not None and left>0:
            for y in range(67+int(now*18)%5,90,5): c.d.point((39,y),fill=WHITE)
        c.text(76,45,f"{math.ceil(left)//60:02}",GOLD,size=2)
        c.text(104,45,":",MUTED,size=2)
        c.text(115,45,f"{math.ceil(left)%60:02}",WHITE,size=2)
        c.text(77,70,"COMPLETE" if left<=0 else "FOCUSING" if self.started is not None else "READY",MUTED)
        c.text(77,85,"ONE MINUTE",MUTED)
        c.footer("ACTIVATE / START OR PAUSE")
        return c.image

class Buttons(Demo):
    key, title = "buttons", "Button Lab // one press, one tick"
    description = "A static counter to check input delivery and duplicate-frame suppression."
    def __init__(self): self.count=0; self.raw="READY"
    def handle(self,event,now):
        if event.get("type")=="button":
            self.count=(self.count+1)%10000
            self.raw=event.get("raw", "ACTIVATE")
    def render(self,now):
        c=Canvas(); c.header("BUTTON LAB","06",MINT); c.grid()
        c.d.rectangle((8,33,151,86),fill=PANEL,outline=LINE)
        c.text(80,44,f"{self.count:04}",MINT,size=4,center=True)
        c.text(80,97,self.raw[:20],MUTED,center=True)
        c.footer("ONE PRESS = ONE TICK",MINT)
        return c.image

class Signal(Demo):
    key,title="signal","Signal Inbox // push a little joy"
    description="JSONL notifications, no file watching. Activate clears the inbox."
    def __init__(self): self.messages=deque(maxlen=8)
    def handle(self,event,now):
        if event.get("type")=="notice": self.messages.append(str(event.get("text",""))[:80])
        elif event.get("type")=="button": self.messages.clear()
    def render(self,now):
        c=Canvas(); c.header("SIGNAL INBOX","07",PINK)
        c.d.rectangle((63,30,96,49),outline=PINK,width=2)
        c.d.line((64,31,80,42,95,31),fill=PINK,width=2)
        c.text(80,58,"WAITING FOR A SIGNAL" if not self.messages else f"{len(self.messages):02} SIGNALS RECEIVED",MUTED,center=True)
        message=self.messages[-1] if self.messages else "SEND SOMETHING NICE"
        for i,line in enumerate(textwrap.wrap(message,24)[:2]): c.text(80,77+i*12,line,WHITE,center=True)
        c.footer("EVENTS IN / ACTIVATE CLEAR")
        return c.image
