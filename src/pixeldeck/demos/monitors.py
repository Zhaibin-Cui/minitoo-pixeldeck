"""Useful instruments driven by sampled or pushed events, never by renderer I/O."""
from collections import deque
import math
import textwrap

from .base import Demo
from ..pixels import Canvas, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD


def _number(value, name, maximum=None):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(name + " must be a finite nonnegative number or null")
    if maximum is not None and value > maximum:
        raise ValueError(name + " exceeds its range")
    return value


def _flag(value, name, nullable=False):
    if type(value) is not bool and not (nullable and value is None):
        raise ValueError(name + " must be boolean" + (" or null" if nullable else ""))
    return value


def _scaled(value):
    if value is None:
        return "--", ""
    scaled = float(value)
    suffixes = ("B", "K", "M", "G", "T", "P", "E")
    suffix = suffixes[0]
    for suffix in suffixes:
        if scaled < 1024 or suffix == suffixes[-1]:
            break
        scaled /= 1024
    if scaled >= 100 or scaled == int(scaled):
        number = f"{scaled:.0f}"
    else:
        number = f"{scaled:.1f}"
    return number, suffix


def _amount(value):
    number, suffix = _scaled(value)
    return number + suffix


def _activate(event):
    return event.get("type") == "button" and event.get("button") == "activate"


class NetScope(Demo):
    key = "network"
    title = "NetScope // traffic in neon"
    description = "Aggregate interface receive/transmit rates in bytes per second. Activate freezes the trace."
    sources = ("network",)
    source_interval = 1

    def __init__(self):
        self.held = False
        self.available = False
        self.rx = None
        self.tx = None
        self.history = deque(maxlen=61)

    def handle(self, event, now):
        if _activate(event):
            self.held = not self.held
        elif event.get("type") == "network":
            available = _flag(event.get("available", True), "available")
            rx = _number(event.get("rx_bps"), "rx_bps")
            tx = _number(event.get("tx_bps"), "tx_bps")
            if not self.held:
                self.available = available
                self.rx, self.tx = (rx, tx) if available else (None, None)
                self.history.append((self.rx, self.tx))

    def render(self, now):
        c = Canvas()
        c.header("NETSCOPE", "12", CYAN)
        c.text(8, 28, "RX / DOWN", CYAN)
        c.text(86, 28, "TX / UP", PINK)
        for x, value, color in ((8, self.rx, CYAN), (86, self.tx, PINK)):
            number, unit = _scaled(value)
            c.text(x, 41, number, color, 2)
            rate_unit = "B/S" if unit == "B" else unit + "IB/S"
            c.text(x, 58, rate_unit if unit else "NO DATA", MUTED)
        c.d.rectangle((7, 75, 152, 105), fill=PANEL, outline=LINE)
        if self.available:
            values = list(self.history)
            peak = max([1024] + [v for pair in values for v in pair if v is not None])
            for series, color in ((0, CYAN), (1, PINK)):
                run = []
                for index, pair in enumerate(values):
                    value = pair[series]
                    if value is None:
                        if len(run) > 1:
                            c.d.line(run, fill=color)
                        run = []
                    else:
                        run.append((round(151-(len(values)-1-index)*143/60), round(103-25*value/peak)))
                if len(run) > 1:
                    c.d.line(run, fill=color)
            c.text(10, 78, "ALL IFACES", MUTED)
        else:
            c.text(80, 87, "ADD TELEMETRY EXTRA", MUTED, center=True)
        c.footer("HOLD / ACTIVATE TO RESUME" if self.held else "ACTIVATE / FREEZE TRAFFIC")
        return c.image


class VolumeVault(Demo):
    key = "storage"
    title = "Volume Vault // disk headroom"
    description = "Local volume capacity as pixel blocks. Activate selects the next volume."
    sources = ("storage",)
    source_interval = 10

    def __init__(self):
        self.volumes = []
        self.selected = 0
        self.available = False

    def handle(self, event, now):
        if _activate(event):
            self.selected = (self.selected + 1) % max(1, len(self.volumes))
        elif event.get("type") == "storage":
            available = _flag(event.get("available", True), "available")
            incoming = event.get("volumes", [])
            if not isinstance(incoming, list):
                raise ValueError("volumes must be a list")
            volumes = []
            for index, item in enumerate(incoming[:16]):
                if not isinstance(item, dict):
                    raise ValueError("Each volume must be an object")
                total = _number(item.get("total"), "total")
                free = _number(item.get("free"), "free")
                if total is None or free is None or free > total:
                    raise ValueError("Each volume needs total and free, with free <= total")
                label = item.get("label", "")
                if not isinstance(label, str):
                    raise ValueError("Volume label must be a string")
                # A provider should send generic labels. Never render a filesystem path.
                if not label or any(ch in label for ch in ("/", "\\", ":")):
                    label = f"VOLUME {index+1:02}"
                label = "".join(ch for ch in label.upper() if ch.isascii() and (ch.isalnum() or ch in " -_"))[:16]
                volumes.append({"label": label or f"VOLUME {index+1:02}", "total": total, "free": free})
            self.available = available
            self.volumes = volumes if available else []
            self.selected %= max(1, len(self.volumes))

    def render(self, now):
        c = Canvas()
        c.header("VOLUME VAULT", "13", GOLD)
        if not self.volumes:
            c.d.rectangle((57, 35, 102, 66), fill=PANEL, outline=LINE)
            c.d.line((63, 58, 96, 58), fill=MUTED)
            c.d.rectangle((90, 61, 94, 63), fill=GOLD)
            c.text(80, 80, "NO VOLUMES" if self.available else "SOURCE UNAVAILABLE", MUTED, center=True)
            c.footer("ACTIVATE / NEXT VOLUME")
            return c.image
        item = self.volumes[self.selected]
        used = 1-item["free"]/item["total"] if item["total"] else None
        c.text(8, 29, item["label"], GOLD)
        c.text(137, 29, f"{self.selected+1:02}", MUTED)
        number = "--" if used is None else f"{used*100:.0f}"
        c.text(8, 43, number, WHITE, 3)
        c.text(68, 56, "% USED", MUTED)
        occupied = round(40*used) if used is not None else 0
        color = PINK if used is not None and used >= .9 else GOLD
        for index in range(40):
            x = 8+(index % 20)*7
            y = 72+(index // 20)*8
            c.d.rectangle((x, y, x+4, y+5), fill=color if index < occupied else LINE)
        c.text(8, 94, _amount(item["free"])+" FREE", MINT)
        c.text(8, 105, _amount(item["total"])+" TOTAL", MUTED)
        c.footer("ACTIVATE / NEXT VOLUME")
        return c.image


class PowerCell(Demo):
    key = "power"
    title = "Power Cell // portable power"
    description = "Battery charge and power-source status. Activate toggles detail; missing data stays missing."
    sources = ("power",)
    source_interval = 5

    def __init__(self):
        self.available = False
        self.present = False
        self.percent = None
        self.plugged = None
        self.seconds_left = None
        self.detail = False

    def handle(self, event, now):
        if _activate(event):
            self.detail = not self.detail
        elif event.get("type") == "power":
            available = _flag(event.get("available", True), "available")
            present = _flag(event.get("present", False), "present")
            plugged = _flag(event.get("plugged"), "plugged", nullable=True)
            percent = _number(event.get("percent"), "percent", 100)
            seconds = _number(event.get("seconds_left"), "seconds_left")
            self.available = available
            self.present = present if available else False
            self.percent = percent if self.present else None
            self.plugged = plugged if available else None
            self.seconds_left = seconds if self.present else None

    def render(self, now):
        c = Canvas()
        c.header("POWER CELL", "14", MINT)
        if not self.available or not self.present:
            c.d.rectangle((60, 35, 99, 65), fill=PANEL, outline=LINE)
            c.d.rectangle((73, 31, 86, 35), fill=MUTED)
            c.d.line((65, 60, 93, 40), fill=MUTED, width=2)
            c.text(80, 78, "NO BATTERY" if self.available else "SOURCE UNAVAILABLE", WHITE, center=True)
            label = ("ON AC POWER" if self.plugged else "POWER SOURCE UNKNOWN") if self.available else "ADD TELEMETRY EXTRA"
            c.text(80, 96, label, MUTED, center=True)
            c.footer("ACTIVATE / DETAILS")
            return c.image
        color = MINT if self.percent is None or self.percent > 30 else GOLD if self.percent > 15 else PINK
        if self.detail:
            c.d.rectangle((10, 34, 145, 52), fill=PANEL, outline=LINE)
            c.d.rectangle((146, 39, 150, 47), fill=MUTED)
            if self.percent is not None and self.percent > 0:
                c.d.rectangle((13, 37, 13+round(129*self.percent/100), 49), fill=color)
            c.text(9, 66, "CAPACITY", MUTED)
            c.text(104, 66, "--" if self.percent is None else f"{self.percent:.0f}%", color)
            c.text(9, 82, "ESTIMATE", MUTED)
            if self.seconds_left is None or self.plugged:
                remaining = "--"
            else:
                hours, minutes = int(self.seconds_left)//3600, (int(self.seconds_left)%3600)//60
                remaining = f"{hours}H {minutes:02}M" if hours < 100 else "100H+"
            c.text(98, 82, remaining, WHITE)
            c.text(80, 101, "ON AC" if self.plugged is True else "ON BATTERY" if self.plugged is False else "POWER UNKNOWN", MUTED, center=True)
        else:
            c.d.rectangle((15, 39, 56, 99), fill=PANEL, outline=MUTED, width=2)
            c.d.rectangle((27, 34, 44, 38), fill=MUTED)
            filled = round(self.percent/100*7) if self.percent is not None else 0
            for index in range(7):
                y = 92-index*7
                c.d.rectangle((20, y-4, 51, y), fill=color if index < filled else LINE)
            c.text(75, 46, "--" if self.percent is None else f"{self.percent:.0f}", color, 3)
            c.text(135, 58, "%", MUTED)
            c.text(75, 79, "AC POWER" if self.plugged is True else "BATTERY" if self.plugged is False else "UNKNOWN", MUTED)
            c.text(75, 95, "LIVE CHARGE", MUTED)
        c.footer("ACTIVATE / TOGGLE DETAILS")
        return c.image


class BuildBeacon(Demo):
    key = "build"
    title = "Build Beacon // a signal for your pipeline"
    description = "Pushed build status and progress. Activate toggles detail; the demo never executes a command."
    STATES = {"idle", "running", "passed", "failed"}

    def __init__(self):
        self.project = "NO BUILD YET"
        self.state = "idle"
        self.progress = None
        self.step = "WAITING FOR A PUSH"
        self.detail = False

    def handle(self, event, now):
        if _activate(event):
            self.detail = not self.detail
        elif event.get("type") == "build":
            state = event.get("state")
            project, step = event.get("project", "LOCAL BUILD"), event.get("step", "")
            if state not in self.STATES or not isinstance(project, str) or not isinstance(step, str):
                raise ValueError("Build needs a valid state and string project/step")
            progress = _number(event.get("progress"), "progress", 100)
            self.project = " ".join(project.split())[:20]
            self.step = " ".join(step.split())[:40]
            self.state, self.progress = state, progress

    def next_delay(self, now):
        return 1/3 if self.state == "running" else None

    def render(self, now):
        c = Canvas()
        color = {"idle": MUTED, "running": CYAN, "passed": MINT, "failed": PINK}[self.state]
        c.header("BUILD BEACON", "15", color)
        if self.detail:
            c.text(8, 29, "PROJECT", MUTED)
            c.text(8, 42, self.project, WHITE)
            c.text(8, 60, "STEP", MUTED)
            for i, line in enumerate(textwrap.wrap(self.step, 24)[:2]):
                c.text(8, 73+i*11, line, WHITE)
            c.text(8, 101, self.state, color)
            c.text(113, 101, "--" if self.progress is None else f"{self.progress:.0f}%", color)
        else:
            c.d.rectangle((10, 32, 38, 60), fill=PANEL, outline=color)
            if self.state == "passed":
                c.d.line((16, 47, 22, 53, 33, 39), fill=color, width=3)
            elif self.state == "failed":
                c.d.line((17, 39, 31, 53), fill=color, width=3)
                c.d.line((17, 53, 31, 39), fill=color, width=3)
            else:
                c.text(24, 39, ">" if self.state == "running" else "-", color, 2, center=True)
            c.text(50, 39, self.state, color, 2)
            c.text(8, 65, self.project, MUTED)
            c.d.rectangle((8, 80, 151, 89), fill=PANEL, outline=LINE)
            if self.progress is not None and self.progress > 0:
                c.d.rectangle((10, 82, 10+round(139*self.progress/100), 87), fill=color)
            if self.state == "running":
                x = 10+int(now*38)%133
                c.d.rectangle((x, 82, x+5, 87), fill=WHITE)
            c.text(80, 100, "PROGRESS UNKNOWN" if self.progress is None else f"{self.progress:.0f}% COMPLETE", MUTED, center=True)
        c.footer("ACTIVATE / TOGGLE DETAILS")
        return c.image
