"""Explicit audio-test controls and callback-fed levels; no audio I/O here."""
from collections import deque
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


def _dbfs(amplitude):
    if amplitude is None:
        return None
    return 20*math.log10(amplitude) if amplitude > 0 else -math.inf


def _dbfs_label(level):
    if level is None:
        return '--'
    if level == -math.inf:
        return '-INF'
    label = f'{level:.1f}'
    return label if len(label) <= 6 else f'{level:.0f}'


def _count(value, name):
    if value is not None and (type(value) is not int or not 0 <= value <= 2**63-1):
        raise ValueError(name + ' must be a nonnegative integer or null')
    return value


def _count_label(value):
    if value is None:
        return '--'
    if value < 1000000:
        return str(value)
    return f'{value/1000000:.1f}M' if value < 1000000000 else '999M+'


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
    DBFS_FLOOR = -60.0
    WAVE_GAIN = 16

    def __init__(self):
        self.selected = 0
        self.state = 'idle'
        self.mode = None
        self.message = ''
        self._clear_levels()

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
        self.session_rms = self.session_peak = None
        self.metered_frames = self.dropped_frames = None
        self.peak_history = deque(maxlen=20)
        self.held_peak = None

    def _summary(self, event):
        return (_number(event.get('session_rms', self.session_rms), 'session_rms'),
                _number(event.get('session_peak', self.session_peak), 'session_peak'),
                _count(event.get('metered_frames', self.metered_frames), 'metered_frames'),
                _count(event.get('dropped_frames', self.dropped_frames), 'dropped_frames'))

    def _display_levels(self):
        if self.state == 'stopped':
            return self.session_rms, self.session_peak
        return self.rms, self.held_peak if self.active else self.peak

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
            summary = self._summary(event)
            elapsed = _number(event.get('elapsed', self.elapsed), 'elapsed', high=600)
            if state not in self.STATES or not isinstance(message, str):
                raise ValueError('Invalid audio status')
            if elapsed is None:
                raise ValueError('Elapsed time cannot be null')
            self.state = 'idle' if state == 'available' else state
            self.message = message[:80]
            self.mode = mode
            self.elapsed = elapsed
            self.session_rms, self.session_peak, self.metered_frames, self.dropped_frames = summary
            if mode is not None:
                self.selected = self.MODES.index(mode)
        elif kind == 'audio.level':
            mode = self._mode(event)
            rms = _number(event.get('rms'), 'rms')
            peak = _number(event.get('peak'), 'peak')
            elapsed = _number(event.get('elapsed', self.elapsed), 'elapsed', high=600)
            summary = self._summary(event)
            samples = event.get('waveform', ())
            if not isinstance(samples, (list, tuple)) or len(samples) > 32:
                raise ValueError('Waveform must contain at most 32 samples')
            waveform = tuple(_number(value, 'waveform sample', -1, 1) for value in samples)
            if any(value is None for value in waveform) or elapsed is None:
                raise ValueError('Waveform and elapsed time cannot contain null')
            if elapsed < self.elapsed:
                return None
            self.mode = mode
            self.rms, self.peak = rms, peak
            self.elapsed, self.waveform = elapsed, waveform
            self.session_rms, self.session_peak, self.metered_frames, self.dropped_frames = summary
            self.peak_history.append((elapsed, peak))
            self.held_peak = max((value for stamp, value in self.peak_history
                                  if value is not None and elapsed-stamp <= 1), default=None)
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
        if self.state == 'stopped':
            return 'SESSION', MINT
        return ('MIC IDLE' if self.MODES[self.selected] in ('microphone', 'duplex') else 'IDLE', MUTED)

    def _peak_trace(self, c, color):
        if not self.peak_history:
            c.text(80, 68, 'NO PEAK HISTORY', MUTED, center=True)
            return
        c.d.line((9, 81, 107, 81), fill=LINE)
        c.d.line((111, 61, 111, 81), fill=LINE)
        c.text(118, 62, 'PEAK', MUTED)
        c.text(115, 74, f'LAST{len(self.peak_history)}', MUTED)
        previous = None
        for index, (_, value) in enumerate(self.peak_history):
            if value is None:
                previous = None
                continue
            fraction = max(0, min(1, (_dbfs(value)-self.DBFS_FLOOR)/-self.DBFS_FLOOR))
            point = (10+round(index*97/max(1, len(self.peak_history)-1)), 81-round(fraction*20))
            if previous is None:
                c.d.point(point, fill=color)
            else:
                c.d.line((previous, point), fill=color)
            previous = point

    def _wave(self, c, color):
        c.d.rectangle((8, 59, 151, 83), fill=PANEL, outline=LINE)
        if self.state == 'error':
            lines = textwrap.wrap(self.message or 'Audio unavailable', width=23,
                                  max_lines=2, placeholder='...')
            for index, line in enumerate(lines):
                c.text(80, 63+11*index, line, GOLD, center=True)
        elif self.state == 'stopped':
            self._peak_trace(c, color)
        elif self.waveform:
            c.d.line((9, 71, 107, 71), fill=LINE)
            c.d.line((111, 61, 111, 81), fill=LINE)
            c.text(118, 62, 'WAVE', MUTED)
            c.text(122, 74, f'X{self.WAVE_GAIN}', MUTED)
            points = [(10+round(index*97/max(1, len(self.waveform)-1)),
                       71-round(max(-1, min(1, value*self.WAVE_GAIN))*10))
                      for index, value in enumerate(self.waveform)]
            if len(points) == 1:
                c.d.point(points[0], fill=color)
            else:
                c.d.line(points, fill=color)
        else:
            label = ('SHORT TEST TONE', 'MIC OFF UNTIL START', 'TONE + MIC / NO ECHO')[self.selected]
            if self.active:
                label = 'WAITING FOR LEVELS'
            c.text(80, 68, label, MUTED, center=True)

    @classmethod
    def _meter(cls, c, label, y, value, color):
        level = _dbfs(value)
        c.text(8, y, label, MUTED)
        c.d.rectangle((38, y, 110, y+6), fill=LINE)
        if level is not None and level > cls.DBFS_FLOOR:
            fraction = min(1, (level-cls.DBFS_FLOOR)/-cls.DBFS_FLOOR)
            c.d.rectangle((38, y, 38+round(fraction*72), y+6), fill=color)
        c.text(116, y, _dbfs_label(level), color)

    def _live_meter(self):
        """Keep capture frames small; retain detailed measurements for SESSION."""
        c = Canvas('#000000')
        accent = '#80edc0'
        c.text(8, 10, 'MIC LIVE' if self.mode == 'microphone' else 'DUPLEX LIVE', accent)
        level = _dbfs(self.rms)
        label = '-INF' if level == -math.inf else str(round(level))
        c.text(8, 34, label, '#ffffff', size=3)
        c.text(111, 48, 'DBFS', accent)
        c.d.rectangle((8, 70, 151, 91), fill='#202020')
        width = round(144*max(0, min(1, (level-self.DBFS_FLOOR)/-self.DBFS_FLOOR)))
        if width:
            c.d.rectangle((8, 70, 7+width, 91), fill=accent)
        c.text(8, 110, 'ACT STOP', accent)
        return c.image

    def render(self, now):
        if self.state == 'ready' and self.mode in ('microphone', 'duplex') and self.rms is not None:
            return self._live_meter()
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
        c.text(8, 86, 'DBFS', MUTED)
        c.text(38, 86, '-60', MUTED)
        c.text(105, 86, '0', MUTED)
        rms, peak = self._display_levels()
        self._meter(c, 'RMS', 94, rms, color)
        self._meter(c, 'PEAK', 104, peak, PINK if peak is not None and peak >= .95 else MINT)
        if self.state == 'stopping':
            c.footer('STOP REQUESTED')
        elif self.active:
            c.footer('PEAK HOLD 1S  ACT STOP')
        elif self.state == 'stopped':
            c.footer('FRAMES '+_count_label(self.metered_frames)+' DROP '+_count_label(self.dropped_frames),
                     GOLD if self.dropped_frames else MUTED)
        else:
            c.footer('ACT START  BACK LEAVE')
        return c.image
