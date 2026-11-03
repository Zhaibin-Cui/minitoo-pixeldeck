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


def _levels(pcm):
    samples = memoryview(pcm).cast('h')
    count = len(samples)
    if not count:
        return 0.0, 0.0, []
    rms = math.sqrt(sum(value*value for value in samples) / count) / 32768
    peak = max(abs(value) for value in samples) / 32768
    size = min(32, count)
    waveform = [samples[index*(count-1)//max(1, size-1)] / 32768 for index in range(size)]
    return min(1.0, rms), min(1.0, peak), waveform


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
        wake = threading.Event()
        lock = threading.Lock()
        storage = bytearray(16384)
        storage_view = memoryview(storage)
        silence = memoryview(bytes(16384))
        latest_size = [0]
        latest_elapsed = [0.0]
        failure = [None]
        xruns = [0, 0]
        started = time.monotonic()

        def status(state, message):
            callback({'type': 'audio.status', 'state': state, 'mode': mode,
                      'message': message, 'xruns': sum(xruns)})

        def fail(message):
            failure[0] = message
            stop_event.set()

        def report():
            last = -math.inf
            while True:
                wake.wait()
                wake.clear()
                if closing.is_set():
                    return
                now = time.monotonic()
                if now-last < .25:
                    continue
                with lock:
                    pcm = bytes(storage_view[:latest_size[0]])
                    elapsed = latest_elapsed[0]
                rms, peak, waveform = _levels(pcm)
                last = now
                try:
                    callback({'type': 'audio.level', 'mode': mode, 'rms': rms, 'peak': peak,
                              'waveform': waveform, 'elapsed': elapsed, 'xruns': sum(xruns)})
                except Exception:
                    fail('Audio reporting callback failed')
                    return

        def sampler(rate):
            seen, next_report = [0], [int(rate*.25)]

            def offer(data, frames):
                seen[0] += frames
                if seen[0] < next_report[0]:
                    return
                next_report[0] = seen[0] + max(1, int(rate*.25))
                if not lock.acquire(blocking=False):
                    return
                try:
                    data_view = memoryview(data).cast('B')
                    size = min(len(data_view), len(storage)) // 2 * 2
                    storage_view[:size] = data_view[:size]
                    latest_size[0] = size
                    latest_elapsed[0] = min(seconds, max(0.0, time.monotonic()-started))
                finally:
                    lock.release()
                wake.set()
            return offer

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
            if input_settings is not None:
                offer_input = sampler(input_settings['samplerate'])

                def input_callback(data, frames, timing, flags):
                    if flags:
                        xruns[0] += 1
                    try:
                        if stop_event.is_set():
                            raise sd.CallbackAbort
                        offer_input(data, frames)
                    except sd.CallbackAbort:
                        raise
                    except Exception:
                        fail('Audio input callback failed')
                        raise sd.CallbackAbort
                streams.append(sd.RawInputStream(**input_settings, blocksize=0,
                    callback=input_callback, finished_callback=finished))
            if output_settings is not None:
                tone = memoryview(_tone(output_settings['samplerate'], output_settings['channels'], mode, stop_event))
                position = [0]
                offer_output = sampler(output_settings['samplerate'])

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
                                if mode == 'speaker':
                                    break
                                position[0] = 0
                            size = min(len(tone)-position[0], len(output)-offset)
                            output[offset:offset+size] = tone[position[0]:position[0]+size]
                            offset += size
                            position[0] += size
                        if mode == 'speaker':
                            offer_output(output, frames)
                    except sd.CallbackAbort:
                        raise
                    except Exception:
                        fail('Audio output callback failed')
                        raise sd.CallbackAbort
                streams.append(sd.RawOutputStream(**output_settings, blocksize=0,
                    callback=output_callback, finished_callback=finished))
            if stop_event.is_set():
                return
            for stream in streams:
                if stop_event.is_set():
                    return
                stream.start()
            if stop_event.is_set():
                return
            started = time.monotonic()
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
            wake.set()
            if reporter is not None:
                reporter.join(timeout=1)
                if reporter.is_alive():
                    failure[0] = failure[0] or 'Audio reporting callback did not return'
            if failure[0] is not None:
                status('error', failure[0])
            else:
                status('stopped', 'Audio stopped')
