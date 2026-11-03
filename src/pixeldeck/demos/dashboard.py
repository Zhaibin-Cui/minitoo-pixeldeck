"""An interactive system overview built entirely from source events."""
from collections import deque
import math

from PIL import ImageDraw

from .base import Demo
from .monitors import NetScope, VolumeVault, PowerCell, _number, _flag, _scaled, _amount
from ..pixels import Canvas, INK, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD


class Dashboard(Demo):
    key = "dashboard"
    title = "System Deck // one screen, five instruments"
    description = "Select CPU, memory, network, storage or power details. The EXIT tile explicitly closes the session."
    sources = ("telemetry", "network", "storage", "power")
    source_interval = 1.0
    captures_navigation = True
    TILES = ("CPU", "MEMORY", "NETWORK", "STORAGE", "POWER", "EXIT")
    COLORS = (CYAN, PINK, MINT, GOLD, MINT, PINK)

    def __init__(self):
        self.selected = 0
        self.detail = False
        self.cpu = None
        self.memory = None
        self.cpu_history = deque(maxlen=61)
        self.memory_history = deque(maxlen=61)
        self.sampled_at = None
        self.network = NetScope()
        self.storage = VolumeVault()
        self.power = PowerCell()
        self.power.detail = True

    def handle(self, event, now):
        kind = event.get("type")
        if kind == "button":
            button = event.get("button")
            if button in ("next", "previous"):
                count = 5 if self.detail else len(self.TILES)
                self.selected = (self.selected + (1 if button == "next" else -1)) % count
            elif button == "activate":
                if self.detail:
                    self.detail = False
                elif self.selected == 5:
                    return "exit"
                else:
                    self.detail = True
            elif button == "back":
                if self.detail:
                    self.detail = False
                else:
                    return "leave"
        elif kind == "telemetry":
            self._telemetry(event, now)
        elif kind == "network":
            self.network.handle(event, now)
        elif kind == "storage":
            self.storage.handle(event, now)
        elif kind == "power":
            self.power.handle(event, now)
        return None

    def _telemetry(self, event, now):
        available = _flag(event.get("available", True), "available")
        cpu = _number(event.get("cpu"), "cpu", 100)
        memory = _number(event.get("memory"), "memory", 100)
        stamp = event.get("sampled_at", now)
        if type(stamp) not in (int, float):
            raise ValueError("sampled_at must be a finite monotonic timestamp")
        try:
            finite = math.isfinite(stamp)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("sampled_at must be a finite monotonic timestamp")
        # Older data cannot roll the display back; a revised sample replaces its slot.
        if self.sampled_at is not None and stamp < self.sampled_at:
            return
        if self.sampled_at == stamp:
            self.cpu_history.pop()
            self.memory_history.pop()
        self.cpu, self.memory = (cpu, memory) if available else (None, None)
        self.sampled_at = stamp
        self.cpu_history.append((stamp, self.cpu))
        self.memory_history.append((stamp, self.memory))

    def _storage_summary(self):
        total = sum(volume["total"] for volume in self.storage.volumes)
        free = sum(volume["free"] for volume in self.storage.volumes)
        return (100*(1-free/total) if total else None), total, free

    @staticmethod
    def _percent(value):
        return "--" if value is None else f"{value:.0f}%"

    def _rate(self):
        if self.network.rx is None or self.network.tx is None:
            return "--"
        number, unit = _scaled(self.network.rx+self.network.tx)
        suffix = "B/S" if unit == "B" else unit+"IB/S"
        if len(number+suffix) > 8:
            number = f"{float(number):.0f}"
        label = number+suffix
        return label if len(label) <= 8 else "VERY HIGH"

    @staticmethod
    def _mini_trace(c, x, y, samples, color):
        # The detail graph uses timestamps; this tiny sparkline is a sample summary.
        values = [value for _, value in list(samples)[-12:] if value is not None]
        if len(values) < 2:
            c.d.line((x, y+7, x+23, y+7), fill=LINE)
            return
        points = [(x+round(index*23/max(1, len(values)-1)), y+8-round(value*.08))
                  for index, value in enumerate(values)]
        c.d.line(points, fill=color)

    def _overview(self):
        c = Canvas()
        c.header("SYSTEM DECK", f"{self.selected+1}/6", CYAN)
        used, _, _ = self._storage_summary()
        power = (self._percent(self.power.percent) if self.power.present else "NO BATT") if self.power.available else "--"
        values = (self._percent(self.cpu), self._percent(self.memory), self._rate(),
                  self._percent(used)+" USED" if used is not None else "--", power, "STOP APP")
        for index, title in enumerate(self.TILES):
            x = 5+(index % 2)*77
            y = 26+(index // 2)*29
            color = self.COLORS[index]
            active = index == self.selected
            c.d.rectangle((x, y, x+72, y+25), fill="#173149" if active else PANEL,
                          outline=color if active else LINE, width=2 if active else 1)
            c.text(x+5, y+4, f"{index+1} {title}", color if active else MUTED)
            c.text(x+5, y+15, values[index], WHITE if active else color)
            if index in (0, 1):
                self._mini_trace(c, x+44, y+14, self.cpu_history if index == 0 else self.memory_history, color)
            elif index == 5:
                c.text(x+59, y+15, ">", PINK)
        c.footer("PLAY/PAUSE: EXIT APP" if self.selected == 5 else "L/R SELECT PLAY/PAUSE OPEN")
        return c.image

    def _percentage_detail(self, memory=False):
        c = Canvas()
        value = self.memory if memory else self.cpu
        samples = self.memory_history if memory else self.cpu_history
        color = PINK if memory else CYAN
        c.text(8, 28, "USED MEMORY" if memory else "CPU BUSY", MUTED)
        c.text(8, 41, "--" if value is None else f"{value:.0f}", color, 3)
        c.text(69, 55, "%", MUTED)
        for i in range(10):
            filled = value is not None and i < value/10
            c.d.rectangle((94+i*5, 41, 96+i*5, 61), fill=color if filled else LINE)
        c.d.rectangle((8, 74, 151, 106), fill=PANEL, outline=LINE)
        for y in (82, 90, 98):
            c.d.line((9, y, 150, y), fill=LINE)
        end = samples[-1][0] if samples else 0
        points = []
        for stamp, sample in samples:
            if stamp < end-60:
                continue
            if sample is None:
                if len(points) > 1:
                    c.d.line(points, fill=color)
                points = []
                continue
            points.append((round(150-(end-stamp)*141/60), round(104-sample*.28)))
        if len(points) > 1:
            c.d.line(points, fill=color)
        elif points:
            c.d.point(points[0], fill=color)
        c.text(91, 28, "60 SEC", MUTED)
        if value is None:
            c.text(80, 86, "WAITING FOR DATA", MUTED, center=True)
        return c.image

    def _storage_detail(self):
        if not self.storage.volumes:
            return self.storage.render(0)
        c = Canvas()
        _, total, free = self._storage_summary()
        c.text(8, 28, f"ALL {len(self.storage.volumes):02} / {min(3,len(self.storage.volumes))} SHOWN", MUTED)
        c.text(8, 40, _amount(free)+" FREE", GOLD, 2)
        for index, volume in enumerate(self.storage.volumes[:3]):
            y = 66+index*15
            percent = 100*(1-volume["free"]/volume["total"]) if volume["total"] else None
            color = PINK if percent is not None and percent >= 90 else GOLD
            c.text(8, y, volume["label"][:12], MUTED)
            c.text(122, y, self._percent(percent), color)
            c.d.rectangle((8, y+9, 151, y+11), fill=LINE)
            if percent is not None and percent > 0:
                c.d.rectangle((8, y+9, 8+round(percent*1.43), y+11), fill=color)
        return c.image

    def render(self, now):
        if not self.detail:
            return self._overview()
        if self.selected == 0:
            image = self._percentage_detail()
        elif self.selected == 1:
            image = self._percentage_detail(memory=True)
        elif self.selected == 2:
            image = self.network.render(now)
        elif self.selected == 3:
            image = self._storage_detail()
        else:
            image = self.power.render(now)
        c = Canvas()
        c.image = image
        c.d = ImageDraw.Draw(image)
        c.header("DASH / "+self.TILES[self.selected], f"{self.selected+1}/5", self.COLORS[self.selected])
        c.footer("L/R NEXT  PLAY/PAUSE BACK")
        return c.image
