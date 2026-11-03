"""Transport and input snapshots: observations never create another frame."""
from collections import deque
import math

from .base import Demo
from ..pixels import Canvas, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD


def _metric(value, name, integer=False):
    if value is None:
        return None
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise ValueError(name + ' must be a nonnegative number or null')
    try:
        valid = math.isfinite(value) and 0 <= value <= 2**63-1
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + ' must be a finite nonnegative metric')
    return value


def _label(value):
    if not isinstance(value, str):
        return '--'
    return ''.join(char if char.isascii() and (char.isalnum() or char in ' /_-') else '?'
                   for char in value[:18]).upper()


def _short(value):
    if value is None:
        return '--'
    return str(round(value)) if value < 10000 else '9999+'


class LinkLab(Demo):
    key = 'link'
    title = 'Link Lab // pixels on the wire'
    description = 'Inspect frozen ACK and input snapshots. Activate advances a numbered test pattern; observations never trigger uploads.'
    captures_navigation = True
    PANELS = ('LINK', 'INPUT', 'PATTERN')
    METRICS = ('sequence', 'transfer_ms', 'bytes', 'chunks', 'retransmissions',
               'replaced', 'input_to_ack_ms')

    def __init__(self):
        self.selected = 0
        self.detail = False
        self.pattern = 0
        self.latest = {name: None for name in self.METRICS}
        self.latencies = deque(maxlen=24)
        self.counts = dict.fromkeys(('acks', 'lost', 'errors', 'recoveries', 'media',
                                    'desktop', 'other', 'unmapped', 'coalesced'), 0)
        self.link_state = 'NO ACK'
        self.input_state = 'NO SESSION'
        self.last_input = '--'
        self.snapshot = self._snapshot()

    def _increment(self, name):
        self.counts[name] = min(999999999, self.counts[name]+1)

    def _snapshot(self):
        return {'metrics': dict(self.latest), 'latencies': tuple(self.latencies),
                'counts': dict(self.counts), 'link': self.link_state,
                'input': self.input_state, 'last_input': self.last_input}

    def observe(self, event, now):
        """The host calls this once per event, even while another page is visible."""
        kind = event.get('type')
        if kind == 'frame.ack':
            metrics = {name: _metric(event.get(name), name,
                                    integer=name not in ('transfer_ms', 'input_to_ack_ms'))
                       for name in self.METRICS}
            self.latest = metrics
            self._increment('acks')
            if metrics['transfer_ms'] is not None:
                self.latencies.append(metrics['transfer_ms'])
            if self.link_state in ('LOST', 'ERROR'):
                self._increment('recoveries')
            self.link_state = 'ACK OK'
        elif kind in ('link.lost', 'link.error', 'link.stopped'):
            self.link_state = {'link.lost': 'LOST', 'link.error': 'ERROR', 'link.stopped': 'STOPPED'}[kind]
            if kind != 'link.stopped':
                self._increment('lost' if kind == 'link.lost' else 'errors')
        elif kind == 'input.status':
            state = event.get('kind')
            self.input_state = {'ready': 'READY', 'stage': 'STARTING', 'retrying': 'RETRYING',
                                'error': 'ERROR', 'closed': 'CLOSED', 'stopped': 'STOPPED'}.get(state, 'OBSERVED')
        elif kind == 'button':
            source = event.get('source')
            self._increment(source if source in ('media', 'desktop') else 'other')
            self.last_input = _label(event.get('raw', event.get('button')))
        elif kind == 'input.unmapped':
            self._increment('unmapped')
            self.last_input = _label(event.get('raw', event.get('name')))
        elif kind == 'input.coalesced':
            self._increment('coalesced')

    def handle(self, event, now):
        if event.get('type') != 'button':
            self.observe(event, now)
            return None
        button = event.get('button')
        if button in ('next', 'previous'):
            self.selected = (self.selected + (1 if button == 'next' else -1)) % len(self.PANELS)
        elif button == 'activate':
            self.pattern = (self.pattern+1) % 10000
            self.snapshot = self._snapshot()
            self.detail = True
        elif button == 'back':
            if self.detail:
                self.detail = False
            else:
                return 'leave'
        return None

    def _overview(self, c):
        data = self.snapshot
        metrics, counts = data['metrics'], data['counts']
        values = (_short(metrics['transfer_ms'])+' MS',
                  _short(counts['media']+counts['desktop']+counts['other'])+' EVENTS',
                  f'TEST {self.pattern:04}')
        for index, label in enumerate(self.PANELS):
            y = 26+29*index
            active = index == self.selected
            color = (CYAN, PINK, MINT)[index]
            c.d.rectangle((5, y, 154, y+24), fill=PANEL, outline=color if active else LINE,
                          width=2 if active else 1)
            c.text(12, y+5, label, color)
            c.text(84, y+13, values[index], WHITE)
            if active:
                c.text(139, y+4, '>', color)
        c.footer('ACT SNAPSHOT  BACK LEAVE')

    def _link(self, c):
        data = self.snapshot
        metrics = data['metrics']
        c.text(8, 27, data['link'], CYAN if data['link'] == 'ACK OK' else GOLD)
        c.text(92, 27, 'SEQ '+_short(metrics['sequence']), MUTED)
        c.text(8, 42, _short(metrics['transfer_ms']), CYAN, 2)
        c.text(8, 61, 'ACK MS', MUTED)
        c.d.rectangle((91, 43, 151, 65), fill=PANEL, outline=LINE)
        samples = data['latencies']
        if samples:
            ceiling = max(1, max(samples))
            points = [(93+round(i*56/max(1, len(samples)-1)),
                       63-round(value/ceiling*18)) for i, value in enumerate(samples)]
            if len(points) > 1:
                c.d.line(points, fill=CYAN)
            else:
                c.d.point(points[0], fill=CYAN)
        c.text(8, 76, 'BYTES '+_short(metrics['bytes'])+' CH '+_short(metrics['chunks']), WHITE)
        c.text(8, 87, 'RETX '+_short(metrics['retransmissions'])+' SKIP '+_short(metrics['replaced']), GOLD)
        c.text(8, 99, 'INPUT ACK '+_short(metrics['input_to_ack_ms'])+' MS', MINT)

    def _input(self, c):
        data = self.snapshot
        counts = data['counts']
        c.text(8, 28, 'SESSION '+data['input'], PINK)
        c.text(8, 44, 'MEDIA '+_short(counts['media'])+' DESK '+_short(counts['desktop']), WHITE)
        c.text(8, 57, 'UNMAPPED '+_short(counts['unmapped']), GOLD)
        c.text(8, 70, 'FILTERED '+_short(counts['coalesced']), CYAN)
        c.text(8, 85, 'LAST '+data['last_input'], MINT)
        c.text(8, 101, 'EVENTS ARE NOT RAW KEYS', MUTED)

    def _pattern(self, c):
        color = (CYAN, MINT, PINK, GOLD)[self.pattern % 4]
        c.d.rectangle((7, 27, 152, 107), fill=PANEL, outline=color, width=2)
        for row in range(4):
            for column in range(16):
                if (row+column+self.pattern) % 3 == 0:
                    x, y = 15+8*column, 34+17*row
                    c.d.rectangle((x, y, x+3, y+3), fill=color)
        c.d.rectangle((17, 46, 142, 83), fill=PANEL, outline=LINE)
        c.text(80, 53, f'TEST {self.pattern:04}', color, 2, center=True)
        c.text(80, 73, 'ACTIVATE TO ADVANCE', MUTED, center=True)
        c.text(80, 94, 'NO IDLE ANIMATION', WHITE, center=True)

    def render(self, now):
        c = Canvas()
        c.header('LINK LAB', f'{self.selected+1}/3', (CYAN, PINK, MINT)[self.selected])
        if not self.detail:
            self._overview(c)
        else:
            (self._link, self._input, self._pattern)[self.selected](c)
            c.footer('L/R PANEL ACT SNAP BACK')
        return c.image
