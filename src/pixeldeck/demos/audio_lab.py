"""Explicit audio-test controls and callback-fed levels; no audio I/O here."""
import math
import textwrap

from .base import Demo
from ..pixels import Canvas, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD


def _number(value, name, low=0, high=1):
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError(name + ' must be numeric or null')
    try:
        valid = math.isfinite(value) and low <= value <= high
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + ' is outside its finite range')
    return float(value)


class AudioLab(Demo):
    key = 'audio'
    title = 'Audio Lab // speaker and microphone'
    description = 'Select a five-second speaker, microphone or duplex test. Activate starts or stops; entering the page opens no audio device.'
    captures_navigation = True
    MODES = ('speaker', 'microphone', 'duplex')
    LABELS = ('SPEAKER', 'MIC', 'DUPLEX')
    COLORS = (CYAN, PINK, GOLD)
    ACTIVE_STATES = ('starting', 'ready', 'stopping')
    STATES = ('idle', 'available', 'starting', 'ready', 'stopping', 'stopped', 'error')

    def __init__(self):
        self.selected = 0
        self.state = 'idle'
        self.mode = None
        self.message = ''
        self.rms = None
        self.peak = None
        self.waveform = ()
        self.elapsed = 0.0

    @property
    def active(self):
        return self.state in self.ACTIVE_STATES

    def _mode(self, event):
        mode = event.get('mode', self.mode)
        if mode is not None and mode not in self.MODES:
            raise ValueError('Unknown audio mode')
        return mode

    def _clear_levels(self):
        self.rms = self.peak = None
        self.waveform = ()
        self.elapsed = 0.0

    def _stop(self):
        if self.state == 'stopping':
            return None
        self.state = 'stopping'
        return {'type': 'audio.stop'}

    def handle(self, event, now):
        kind = event.get('type')
        if kind == 'button':
            button = event.get('button')
            if button in ('next', 'previous') and not self.active:
                self.selected = (self.selected + (1 if button == 'next' else -1)) % len(self.MODES)
                self.mode = None
                self._clear_levels()
            elif button == 'activate':
                if self.active:
                    return self._stop()
                self.mode = self.MODES[self.selected]
                self.state = 'starting'
                self.message = ''
                self._clear_levels()
                return {'type': 'audio.request', 'mode': self.mode, 'seconds': 5}
            elif button == 'back':
                return self._stop() if self.active else 'leave'
        elif kind == 'audio.status':
            state = event.get('state')
            message = event.get('message', '')
            mode = self._mode(event)
            if state not in self.STATES or not isinstance(message, str):
                raise ValueError('Invalid audio status')
            self.state = 'idle' if state == 'available' else state
            self.message = message[:80]
            self.mode = mode
            if mode is not None:
                self.selected = self.MODES.index(mode)
        elif kind == 'audio.level':
            mode = self._mode(event)
            rms = _number(event.get('rms'), 'rms')
            peak = _number(event.get('peak'), 'peak')
            elapsed = _number(event.get('elapsed', self.elapsed), 'elapsed', high=600)
            samples = event.get('waveform', ())
            if not isinstance(samples, (list, tuple)) or len(samples) > 32:
                raise ValueError('Waveform must contain at most 32 samples')
            waveform = tuple(_number(value, 'waveform sample', -1, 1) for value in samples)
            if any(value is None for value in waveform) or elapsed is None:
                raise ValueError('Waveform and elapsed time cannot contain null')
            self.mode = mode
            self.rms, self.peak = rms, peak
            self.elapsed, self.waveform = elapsed, waveform
        return None

    def _state_label(self):
        microphone = self.mode in ('microphone', 'duplex')
        if self.state == 'ready':
            return ('MIC LIVE', PINK) if microphone else ('TONE LIVE', MINT)
        if self.state == 'starting':
            return ('MIC STARTING' if microphone else 'STARTING', GOLD)
        if self.state == 'stopping':
            return ('MIC STOPPING' if microphone else 'STOPPING', GOLD)
        if self.state == 'error':
            return 'UNAVAILABLE', PINK
        return ('MIC IDLE' if self.MODES[self.selected] in ('microphone', 'duplex') else 'IDLE', MUTED)

    def _wave(self, c, color):
        c.d.rectangle((8, 62, 151, 88), fill=PANEL, outline=LINE)
        if self.state == 'error':
            lines = textwrap.wrap(self.message or 'Audio unavailable', width=23,
                                  max_lines=2, placeholder='...')
            for index, line in enumerate(lines):
                c.text(80, 66+11*index, line, GOLD, center=True)
        elif self.waveform:
            c.d.line((9, 75, 150, 75), fill=LINE)
            points = [(10+round(index*139/max(1, len(self.waveform)-1)), 75-round(value*10))
                      for index, value in enumerate(self.waveform)]
            if len(points) == 1:
                c.d.point(points[0], fill=color)
            else:
                c.d.line(points, fill=color)
        else:
            label = ('SHORT TEST TONE', 'MIC OFF UNTIL START', 'TONE + MIC / NO ECHO')[self.selected]
            if self.active:
                label = 'WAITING FOR LEVELS'
            c.text(80, 72, label, MUTED, center=True)

    @staticmethod
    def _meter(c, label, y, value, color):
        c.text(8, y, label, MUTED)
        c.d.rectangle((38, y, 110, y+6), fill=LINE)
        if value is not None and value > 0:
            c.d.rectangle((38, y, 38+round(value*72), y+6), fill=color)
        c.text(119, y, '--' if value is None else f'{value*100:.0f}%', color)

    def render(self, now):
        c = Canvas()
        color = self.COLORS[self.selected]
        c.header('AUDIO LAB', f'{self.selected+1}/3', color)
        for index, label in enumerate(self.LABELS):
            x = 5+51*index
            c.d.rectangle((x, 26, x+47, 41), fill=PANEL,
                          outline=self.COLORS[index] if index == self.selected else LINE)
            c.text(x+24, 30, label, WHITE if index == self.selected else MUTED, center=True)
        label, state_color = self._state_label()
        c.text(8, 49, label, state_color)
        c.text(109, 49, f'{min(self.elapsed, 99.9):.1f}/5S', MUTED)
        self._wave(c, color)
        self._meter(c, 'RMS', 94, self.rms, color)
        self._meter(c, 'PEAK', 104, self.peak, PINK if self.peak is not None and self.peak >= .95 else MINT)
        if self.state == 'stopping':
            c.footer('STOP REQUESTED')
        elif self.active:
            c.footer('ACT / BACK STOP')
        else:
            c.footer('ACT START  BACK LEAVE')
        return c.image
