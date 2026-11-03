"""Optional, explicit-device audio exercises with bounded sample previews.

No recording is saved and microphone samples are never sent to an output device.
Raw PortAudio callbacks only fill/copy buffers and wake the reporting worker.
"""
from array import array
import math
import re
import threading
import time


def _load_sounddevice():
    try:
        import sounddevice
    except (ImportError, OSError) as exc:
        raise RuntimeError('Audio support is unavailable; install "minitoo-pixeldeck[audio]" and PortAudio') from exc
    return sounddevice


def _friendly(value):
    value = re.sub(r'\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b', '<device>', str(value))
    value = re.sub(r'\{[0-9a-fA-F-]{36}\}', '<device>', value)
    value = re.sub(r'(?:[A-Za-z]:[\\/]|\\\\)[^\s,;)]*', '<path>', value)
    return ''.join(char for char in value if char.isprintable()).strip()[:160]


def list_devices(match=None, *, sd_module=None):
    """Read capabilities only; friendly labels omit addresses and endpoint IDs."""
    if match is not None and not isinstance(match, str):
        raise ValueError('Device match must be text or None')
    sd = sd_module if sd_module is not None else _load_sounddevice()
    hosts = sd.query_hostapis()
    result = []
    for index, device in enumerate(sd.query_devices()):
        if match is not None and match.casefold() not in str(device['name']).casefold():
            continue
        host = int(device['hostapi'])
        rate = float(device['default_samplerate'])
        result.append({'index': int(device.get('index', index)), 'name': _friendly(device['name']),
                       'hostapi': _friendly(hosts[host]['name']),
                       'input_channels': int(device['max_input_channels']),
                       'output_channels': int(device['max_output_channels']),
                       'default_samplerate': rate if math.isfinite(rate) else 0.0})
    return result


def _measure(pcm):
    samples = memoryview(pcm).cast('h')
    count = len(samples)
    if not count:
        return 0, 0, 0, []
    squares = sum(value*value for value in samples)
    peak = max(abs(value) for value in samples)
    size = min(32, count)
    # Signed peaks preserve short transients; this is a time-bin preview, not
    # uniformly spaced PCM samples. All analysis happens off the audio callback.
    waveform = [max(samples[index*count//size:(index+1)*count//size], key=abs) / 32768
                for index in range(size)]
    return squares, count, peak, waveform


def _levels(pcm):
    squares, count, peak, waveform = _measure(pcm)
    return (math.sqrt(squares/count) / 32768 if count else 0.0), peak / 32768, waveform


def _stream_latency_ms(stream):
    """Read the host's actual estimate; a 'low' request is not a measurement."""
    try:
        seconds = stream.latency
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            return None
        milliseconds = seconds*1000
        return milliseconds if math.isfinite(milliseconds) else None
    except Exception:
        return None


_METER_INTERVAL = .1


class _WindowMeter:
    """Four preallocated 100 ms slots; producer never waits for the consumer."""
    SLOTS = 4

    def __init__(self, rate, channels, seconds):
        self.rate, self.channels, self.seconds = rate, channels, seconds
        self.window_frames = max(1, int(rate*_METER_INTERVAL))
        self.frame_bytes = channels*2
        self.buffers = [memoryview(bytearray(self.window_frames*self.frame_bytes))
                        for _ in range(self.SLOTS)]
        self.ends = [0]*self.SLOTS
        self.read = self.write = self.pending = self.filled = 0
        self.seen_frames = self.dropped_frames = self.metered_frames = 0
        self.squares = self.samples = self.peak = 0
        self.latest = None
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.finished = threading.Event()

    def offer(self, data, frames):
        """Native callback: bounded copies, counters, and one worker wake only."""
        self.seen_frames += frames
        if not self.lock.acquire(blocking=False):
            self.dropped_frames += frames
            return
        completed = False
        try:
            source = memoryview(data).cast('B')
            offset = 0
            while offset < frames:
                if self.pending == self.SLOTS:
                    self.dropped_frames += frames-offset
                    break
                count = min(frames-offset, self.window_frames-self.filled)
                start, end = self.filled*self.frame_bytes, (self.filled+count)*self.frame_bytes
                self.buffers[self.write][start:end] = source[offset*self.frame_bytes:(offset+count)*self.frame_bytes]
                self.filled += count
                offset += count
                self.ends[self.write] = self.seen_frames-frames+offset
                if self.filled == self.window_frames:
                    self.pending += 1
                    self.write = (self.write+1) % self.SLOTS
                    self.filled = 0
                    completed = True
        finally:
            self.lock.release()
        if completed:
            self.wake.set()

    def take(self):
        """Copy one complete window (or the final partial) outside the callback."""
        with self.lock:
            if self.pending:
                slot, frames = self.read, self.window_frames
                pcm = bytes(self.buffers[slot])
                self.read = (self.read+1) % self.SLOTS
                self.pending -= 1
            elif self.finished.is_set() and self.filled:
                slot, frames = self.write, self.filled
                pcm = bytes(self.buffers[slot][:frames*self.frame_bytes])
                self.filled = 0
            else:
                return None
            return pcm, frames, min(self.seconds, self.ends[slot]/self.rate)

    def measure(self, record):
        pcm, frames, elapsed = record
        squares, count, peak, waveform = _measure(pcm)
        self.squares += squares
        self.samples += count
        self.peak = max(self.peak, peak)
        self.metered_frames += frames
        self.latest = {'rms': math.sqrt(squares/count)/32768, 'peak': peak/32768,
                       'waveform': waveform, 'elapsed': elapsed}

    def summary(self):
        return {'session_rms': math.sqrt(self.squares/self.samples)/32768 if self.samples else None,
                'session_peak': self.peak/32768 if self.samples else None,
                'metered_frames': self.metered_frames, 'dropped_frames': self.dropped_frames}

    def finish(self):
        # Call only after native streams have closed, so the last partial is stable.
        self.finished.set()
        self.wake.set()


def _tone(rate, channels, mode, cancelled):
    """Generate at most one second outside the real-time callback."""
    values = array('h')
    for frame in range(int(rate)):
        if frame % 512 == 0 and cancelled.is_set():
            return b''
        moment = frame / rate
        if mode == 'speaker':
            note = int(moment / .32)
            phase = moment % .32
            duration = .22
            frequency = (523.25, 659.25, 783.99)[min(note, 2)]
            gain = .04 if note < 3 else 0
        else:
            phase, duration, frequency, gain = moment, .10, 440, .02
        envelope = max(0, min(1, phase/.01, (duration-phase)/.02))
        value = int(32767 * gain * envelope * math.sin(2*math.pi*frequency*moment))
        for _ in range(channels):
            values.append(value)
    return values.tobytes()


class AudioBackend:
    def __init__(self, input_device=None, output_device=None, sd_module=None):
        self.input_device = input_device
        self.output_device = output_device
        self._sd = sd_module

    def run(self, mode, seconds, stop_event, callback):
        """Run one bounded job; a native failure also signals the job's stop event."""
        streams = []
        reporter = None
        closing = threading.Event()
        delivery_closed = threading.Event()
        meter = None
        silence = memoryview(bytes(16384))
        failure = [None]
        xruns = [0, 0]
        latencies = {'input_latency_ms': None, 'output_latency_ms': None}

        def status(state, message):
            summary = (meter.summary() if meter is not None else
                       dict(session_rms=None, session_peak=None, metered_frames=0, dropped_frames=0))
            callback({'type': 'audio.status', 'state': state, 'mode': mode,
                      'message': message, 'xruns': sum(xruns),
                      'elapsed': min(seconds, meter.seen_frames/meter.rate) if meter else 0.0,
                      **summary, **latencies})

        def fail(message):
            failure[0] = message
            stop_event.set()

        def report():
            last = -math.inf
            pending = False
            while True:
                delay = max(0, last+_METER_INTERVAL-time.monotonic()) if pending else None
                meter.wake.wait(delay)
                meter.wake.clear()
                finished = meter.finished.is_set()
                while (record := meter.take()) is not None:
                    meter.measure(record)
                    pending = True
                now = time.monotonic()
                if pending and now-last >= _METER_INTERVAL and not delivery_closed.is_set():
                    last, pending = now, False
                    try:
                        callback({'type': 'audio.level', 'mode': mode, **meter.latest,
                                  **meter.summary(), 'xruns': sum(xruns)})
                    except Exception:
                        fail('Audio reporting callback failed')
                        delivery_closed.set()
                if finished:
                    # The terminal status carries any final partial measurement
                    # suppressed by the ten-events-per-second live limit.
                    return

        def finished():
            if not closing.is_set() and not stop_event.is_set():
                fail('The selected audio stream stopped unexpectedly')

        try:
            if mode not in ('speaker', 'microphone', 'duplex'):
                raise ValueError('Unknown audio mode')
            if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 10:
                raise ValueError('Audio duration must be greater than 0 and at most 10 seconds')
            status('starting', 'Preparing explicit audio devices')
            if stop_event.is_set():
                return
            sd = self._sd if self._sd is not None else _load_sounddevice()

            def settings(index, direction):
                if type(index) is not int or index < 0:
                    raise ValueError(f'Select an explicit {direction} device index first')
                device = sd.query_devices(index)
                maximum = int(device['max_' + direction + '_channels'])
                if maximum < 1:
                    raise ValueError(f'The selected device has no {direction} channels')
                channels = 1 if direction == 'input' else min(2, maximum)
                rate = float(device['default_samplerate'])
                if not math.isfinite(rate) or not 8000 <= rate <= 384000:
                    raise ValueError('The selected device reports an unsupported sample rate')
                values = dict(device=index, channels=channels, dtype='int16', samplerate=rate)
                getattr(sd, 'check_' + direction + '_settings')(**values)
                return values

            input_settings = settings(self.input_device, 'input') if mode != 'speaker' else None
            output_settings = settings(self.output_device, 'output') if mode != 'microphone' else None
            measured_settings = input_settings if input_settings is not None else output_settings
            meter = _WindowMeter(measured_settings['samplerate'], measured_settings['channels'], seconds)
            if input_settings is not None:
                def input_callback(data, frames, timing, flags):
                    if flags:
                        xruns[0] += 1
                    try:
                        if stop_event.is_set():
                            raise sd.CallbackAbort
                        meter.offer(data, frames)
                    except sd.CallbackAbort:
                        raise
                    except Exception:
                        fail('Audio input callback failed')
                        raise sd.CallbackAbort
                streams.append(sd.RawInputStream(**input_settings, blocksize=0, latency='low',
                    callback=input_callback, finished_callback=finished))
                latencies['input_latency_ms'] = _stream_latency_ms(streams[-1])
            if output_settings is not None:
                tone = memoryview(_tone(output_settings['samplerate'], output_settings['channels'], mode, stop_event))
                position = [0]

                def output_callback(data, frames, timing, flags):
                    if flags:
                        xruns[1] += 1
                    output = memoryview(data).cast('B')
                    for offset in range(0, len(output), len(silence)):
                        size = min(len(silence), len(output)-offset)
                        output[offset:offset+size] = silence[:size]
                    try:
                        if stop_event.is_set():
                            raise sd.CallbackAbort
                        offset = 0
                        while offset < len(output) and tone:
                            if position[0] == len(tone):
                                position[0] = 0
                            size = min(len(tone)-position[0], len(output)-offset)
                            output[offset:offset+size] = tone[position[0]:position[0]+size]
                            offset += size
                            position[0] += size
                        if mode == 'speaker':
                            meter.offer(output, frames)
                    except sd.CallbackAbort:
                        raise
                    except Exception:
                        fail('Audio output callback failed')
                        raise sd.CallbackAbort
                streams.append(sd.RawOutputStream(**output_settings, blocksize=0, latency='low',
                    callback=output_callback, finished_callback=finished))
                latencies['output_latency_ms'] = _stream_latency_ms(streams[-1])
            if stop_event.is_set():
                return
            for stream in streams:
                if stop_event.is_set():
                    return
                stream.start()
            if stop_event.is_set():
                return
            status('ready', 'Audio active; no recording is saved')
            reporter = threading.Thread(target=report, name='pixeldeck-audio-levels', daemon=True)
            reporter.start()
            stop_event.wait(seconds)
        except Exception as exc:
            failure[0] = f'{type(exc).__name__}: {_friendly(exc)}'
        finally:
            closing.set()
            for stream in reversed(streams):
                try:
                    stream.abort()
                except Exception:
                    failure[0] = failure[0] or 'Audio stream abort failed'
                finally:
                    try:
                        stream.close()
                    except Exception:
                        failure[0] = failure[0] or 'Audio stream close failed'
            if meter is not None:
                meter.finish()
            if reporter is not None:
                reporter.join(timeout=1)
                if reporter.is_alive():
                    failure[0] = failure[0] or 'Audio reporting callback did not return'
            elif meter is not None:
                report()
            delivery_closed.set()
            if failure[0] is not None:
                status('error', failure[0])
            else:
                status('stopped', 'Audio stopped')
