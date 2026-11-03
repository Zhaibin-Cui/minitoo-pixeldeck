"""Small desk utilities: externally supplied wall time and monotonic elapsed time.

Every renderer is deterministic for its state and timestamp. These cartridges do
not read the host clock, open a device, or perform I/O.
"""
from datetime import datetime
import math

from ..pixels import Canvas, CYAN, GOLD, INK, LINE, MINT, MUTED, PANEL, PINK, WHITE
from .base import Demo


def _button(event):
    return event.get("button") if event.get("type") == "button" else None


class Clock(Demo):
    key = "clock"
    title = "Neon Clock // two time zones"
    description = "A neon desk clock with local/UTC switching and a seconds skyline."
    sources = ("wallclock",)
    source_interval = 1.0

    def __init__(self):
        self.zone = "local"
        self.times = {}

    def handle(self, event, now):
        if _button(event) == "activate":
            self.zone = "utc" if self.zone == "local" else "local"
        elif event.get("type") == "wallclock":
            if event.get("available") is False:
                self.times = {}
                return
            values = {}
            for zone in ("local", "utc"):
                value = event.get(zone)
                if not isinstance(value, str) or len(value) > 64:
                    raise ValueError("Wallclock values must be ISO timestamp strings")
                values[zone] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            self.times = values

    def next_delay(self, now):
        # The visible source subscription wakes the host once per second.
        return None

    def render(self, now):
        c = Canvas()
        c.header("NEON CLOCK", "08")
        value = self.times.get(self.zone)
        second = value.second if value else 0
        for i in range(16):
            x = i * 10
            height = 6 + (i * 17) % 22
            c.d.rectangle((x, 111-height, x+7, 111), fill="#172941")
            for y in range(113-height, 108, 5):
                c.d.rectangle((x+2, y, x+3, y+1), fill=CYAN if (i+second)%5 == 0 else LINE)
        c.text(9, 29, "UTC / ZULU" if self.zone == "utc" else "LOCAL TIME", CYAN)
        c.d.rectangle((8, 42, 151, 74), fill=PANEL, outline=LINE)
        c.text(16, 47, value.strftime("%H:%M") if value else "--:--", WHITE, 3)
        c.text(119, 52, f"{second:02}" if value else "--", CYAN, 2)
        if value:
            weekday = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[value.weekday()]
            month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")[value.month-1]
            label = f"{weekday} {value.day:02} {month} {value.year:04}"
        else:
            label = "WAITING FOR CLOCK"
        c.text(80, 81, label, MUTED, center=True)
        c.d.rectangle((8, 96, 151, 98), fill=LINE)
        if value:
            c.d.rectangle((8, 96, 8+round(second/59*143), 98), fill=CYAN)
        c.footer("ACTIVATE / LOCAL <> UTC")
        return c.image


class _Elapsed(Demo):
    """One scalar accumulator plus an optional monotonic origin."""
    supports_reset = True

    def __init__(self):
        self.accumulated = 0.0
        self.started = None

    @property
    def running(self):
        return self.started is not None

    def elapsed(self, now):
        return self.accumulated + (max(0.0, now-self.started) if self.running else 0.0)

    def handle(self, event, now):
        button = _button(event)
        if button == "reset":
            self.accumulated = 0.0
            self.started = None
        elif button == "activate":
            if self.running:
                self.accumulated = self.elapsed(now)
                self.started = None
            else:
                self.started = now

    def next_delay(self, now):
        return 1/3 if self.running else None


class Stopwatch(_Elapsed):
    key = "stopwatch"
    title = "Chronograph // elapsed-time instrument"
    description = "A precise elapsed-time counter. Activate starts/pauses; desktop R resets."

    def render(self, now):
        c = Canvas()
        c.header("CHRONOGRAPH", "09", GOLD)
        elapsed = self.elapsed(now)
        total = int(elapsed)
        minutes, seconds = (total//60)%60, total%60
        hundredths = int((elapsed-total)*100)
        c.text(8, 29, "RUNNING" if self.running else "PAUSED" if elapsed else "READY", GOLD)
        c.text(111, 29, f"{min(total//3600, 999):03}H", MUTED)
        c.d.rectangle((8, 42, 151, 76), fill=PANEL, outline=LINE)
        c.text(16, 48, f"{minutes:02}:{seconds:02}", WHITE, 3)
        c.text(119, 53, f"{hundredths:02}", GOLD, 2)
        for i in range(30):
            x = 8 + i*5
            height = 11 if i%5 == 0 else 5
            c.d.line((x, 101-height, x, 101), fill=GOLD if i <= seconds/2 else LINE)
        x = 8 + elapsed%60/60*145
        c.d.polygon([(x-3, 85), (x+3, 85), (x, 89)], fill=GOLD)
        c.footer("ACTIVATE / RUN-PAUSE  R:0")
        return c.image


class Pomodoro(_Elapsed):
    key = "pomodoro"
    title = "Pomodoro Reactor // work and recharge"
    description = "A repeating 25-minute focus / 5-minute break reactor. Activate pauses; R resets."
    focus_seconds = 25*60
    break_seconds = 5*60

    def phase(self, now):
        elapsed = self.elapsed(now)
        cycle_length = self.focus_seconds+self.break_seconds
        cycle = int(elapsed//cycle_length)+1
        position = elapsed%cycle_length
        if position < self.focus_seconds:
            duration = self.focus_seconds
            return "FOCUS", duration-position, position/duration, cycle
        position -= self.focus_seconds
        duration = self.break_seconds
        return "BREAK", duration-position, position/duration, cycle

    def render(self, now):
        c = Canvas()
        c.header("POMO REACTOR", "10", PINK)
        phase, remaining, progress, cycle = self.phase(now)
        color = PINK if phase == "FOCUS" else MINT
        angle = self.elapsed(now)/5
        cx, cy = 40, 67
        for radius in (27, 21):
            c.d.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=LINE)
        for index in range(12):
            theta = index*math.tau/12-math.pi/2
            x, y = round(cx+25*math.cos(theta)), round(cy+25*math.sin(theta))
            c.d.rectangle((x-2, y-2, x+2, y+2), fill=color if index < progress*12 else MUTED)
        core = [(cx+round(12*math.cos(angle+i*math.pi/2)), cy+round(12*math.sin(angle+i*math.pi/2))) for i in range(4)]
        c.d.polygon(core, fill="#3c2548" if phase == "FOCUS" else "#153d32", outline=color)
        c.d.rectangle((cx-3, cy-3, cx+3, cy+3), fill=WHITE)
        left = math.ceil(remaining)
        c.text(78, 36, phase, color)
        c.text(78, 51, f"{left//60:02}:{left%60:02}", WHITE, 2)
        c.text(78, 74, f"CYCLE {min(cycle, 999):03}", MUTED)
        c.text(78, 89, "ACTIVE" if self.running else "PAUSED" if self.elapsed(now) else "READY", color)
        c.text(40, 102, "25 / 5 MIN", MUTED, center=True)
        c.footer("ACTIVATE / RUN-PAUSE  R:0")
        return c.image


class Breathe(_Elapsed):
    key = "breathe"
    title = "Breathing Beacon // a quiet rhythm"
    description = "A gentle 4-4-4-4 visual pace. Activate starts/pauses; desktop R resets."
    phases = ("INHALE", "HOLD", "EXHALE", "HOLD")

    def phase(self, now):
        position = self.elapsed(now)%16
        index = int(position//4)
        fraction = (position%4)/4
        radius = 9+18*fraction if index == 0 else 27 if index == 1 else 27-18*fraction if index == 2 else 9
        return index, fraction, radius

    def render(self, now):
        c = Canvas("#09191d")
        c.header("BREATH BEACON", "11", MINT)
        index, fraction, radius = self.phase(now)
        color = MINT if index < 2 else CYAN
        cx, cy = 80, 67
        for r in (31, 35):
            c.d.ellipse((cx-r, cy-r, cx+r, cy+r), outline="#244047")
        r = round(radius)
        c.d.ellipse((cx-r, cy-r, cx+r, cy+r), fill="#123e3c", outline=color, width=2)
        inner = max(3, r-6)
        c.d.ellipse((cx-inner, cy-inner, cx+inner, cy+inner), outline="#39766d")
        left = max(1, math.ceil(4*(1-fraction)))
        c.text(cx, cy-7, str(left), WHITE, 2, center=True)
        c.text(80, 25, self.phases[index] if self.running or self.elapsed(now) else "READY", color, center=True)
        for i in range(4):
            x = 55+i*14
            c.d.rectangle((x, 105, x+7, 107), fill=color if i == index else LINE)
        c.text(10, 58, "4", MUTED)
        c.text(143, 58, "4", MUTED)
        c.footer("ACTIVATE / PACE-PAUSE R:0")
        return c.image
