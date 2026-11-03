"""Shared event-driven Windows media session; native bindings load only on request."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from types import SimpleNamespace

BUTTON_NAMES = dict(enumerate((
    'Play', 'Pause', 'Stop', 'Record', 'FastForward', 'Rewind',
    'Next', 'Previous', 'ChannelUp', 'ChannelDown',
)))
DEFAULT_WAVE = Path(__file__).resolve().parent / 'native' / 'silence.wav'
SESSION_TITLE = 'Pixeldeck input diagnostics'


@dataclass(frozen=True)
class SessionOptions:
    wave: Path
    seconds: float | None = None
    ready_timeout: float = 30
    receiver: str = 'commands'
    playback_item: bool = True
    keep_playing: bool = False
    diagnostics: bool = False
    stop_on_eof: bool = True


@dataclass
class ReadinessGate:
    """Readiness is announced once, only after opening and actual playback."""
    opened: bool = False
    playing: bool = False
    failed: bool = False
    closed: bool = False
    announced: bool = False

    def take_ready(self, *, failure_seen=False):
        self.failed = self.failed or failure_seen
        if (self.announced or self.failed or self.closed
                or not self.opened or not self.playing):
            return False
        self.announced = True
        return True


def apply_transport_command(name, *, keep_playing, play, pause, set_status=None):
    """Apply only explicit Play/Pause; keep-playing has no playback side effects."""
    if name not in ('Play', 'Pause'):
        return None
    if keep_playing:
        return 'carrier_state_unchanged'
    if name == 'Play':
        play()
        if set_status is not None:
            set_status('Playing')
        return 'play_requested'
    pause()
    if set_status is not None:
        set_status('Paused')
    return 'pause_requested'


def validate_limits(seconds, ready_timeout):
    for name, value, maximum in (('seconds', seconds, 600),
                                 ('ready-timeout', ready_timeout, 60)):
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not 1 <= value <= maximum):
            raise ValueError(f'{name} must be finite and within 1..{maximum}')


def make_emitter(stream, *, production=False):
    sequence = 0

    def emit(kind, value='', **extra):
        nonlocal sequence
        if production:
            if kind not in ('stage', 'ready', 'error', 'closed', 'button'):
                return
            if kind == 'button' and value not in ('Next', 'Previous', 'Play', 'Pause'):
                return
        sequence += 1
        record = {'source': 'python-media', 'type': kind, 'value': value,
                          'sequence': sequence, 'utc': datetime.now(timezone.utc).isoformat(),
                          **extra}
        if production:
            record['backend'] = 'winrt'
        print(json.dumps(record, ensure_ascii=True), file=stream, flush=True)
    return emit


def load_winrt():
    """Import optional native bindings only after an explicit live invocation."""
    if sys.platform != 'win32':
        raise RuntimeError('Live media observation requires Windows; --self-test-json works offline')
    if sys.version_info < (3, 11):
        raise RuntimeError('Live media observation requires Python 3.11 or later')
    try:
        from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
        from winrt.windows.devices.enumeration import DeviceClass, DeviceInformation
        from winrt.windows.media import MediaPlaybackStatus, MediaPlaybackType
        from winrt.windows.media.core import MediaSource
        from winrt.windows.media.playback import (
            MediaCommandEnablingRule, MediaPlaybackItem, MediaPlaybackState, MediaPlayer,
        )
        from winrt.windows.storage import StorageFile
    except ImportError as exc:
        raise RuntimeError(
            'Optional PyWinRT dependencies are unavailable. Install '
            '"minitoo-pixeldeck[windows-input]" with Python 3.11 or later on Windows'
        ) from exc
    return SimpleNamespace(**{name: value for name, value in locals().items()
                              if not name.startswith('_')})


def forward_stdin(stream, output):
    """Internal helper protocol: bounded markers, explicit stop, and explicit EOF."""
    while True:
        line = stream.readline(258)
        if not line:
            print('!EOF', file=output, flush=True)
            return
        if len(line) > 257:
            while line and not line.endswith('\n'):
                line = stream.readline(258)
            continue
        line = line.strip()
        if line == 'stop':
            print('!STOP', file=output, flush=True)
            return
        if line[:5].casefold() == 'mark ':
            label = line[5:].strip()
            if re.fullmatch(r'[A-Za-z0-9 _./+\-]{1,48}', label):
                print(label.upper(), file=output, flush=True)


class ControlInput:
    """A disposable helper keeps a blocking console/pipe read out of the host."""
    def __init__(self, stream, on_stop, on_marker, *, stop_on_eof):
        self.on_stop = on_stop
        self.on_marker = on_marker
        self.stop_on_eof = stop_on_eof
        self.closed = threading.Event()
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parent.parent)
        env['PYTHONPATH'] = source_root + os.pathsep + env.get('PYTHONPATH', '')
        # Preserve an existing console input handle without opening a new window.
        flags = 0 if stream.isatty() else getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        self.process = subprocess.Popen(
            [sys.executable, '-u', '-m', 'pixeldeck.winrt_bridge', '--stdin-reader'],
            stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', env=env, creationflags=flags)
        self.thread = threading.Thread(target=self._read, name='pixeldeck-media-stdin', daemon=True)
        self.thread.start()

    def _read(self):
        stop_requested = False
        try:
            for line in self.process.stdout:
                if self.closed.is_set():
                    return
                value = line.strip()
                if value == '!STOP' or (value == '!EOF' and self.stop_on_eof):
                    stop_requested = True
                    self.on_stop()
                    return
                if value == '!EOF':
                    return
                self.on_marker(value)
        finally:
            if self.stop_on_eof and not stop_requested and not self.closed.is_set():
                self.on_stop()

    def close(self):
        self.closed.set()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise RuntimeError('Media stdin reader did not release its pipe')
        self.process.stdout.close()


async def run_session(args, endpoint_hint, api, emit, stdin):

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    failure_seen = threading.Event()
    gate = ReadinessGate()
    subscriptions = []
    player = controls = source = commands = item = session = markers = None
    closing = False
    ready_deadline = None

    def dispatch(function, *values):
        if closing:
            return
        try:
            loop.call_soon_threadsafe(function, *values)
        except RuntimeError:
            pass

    def error(message):
        if closing:
            return
        failure_seen.set()
        gate.failed = True
        emit('error', str(message)[:400])
        stop.set()

    def maybe_ready():
        if stop.is_set():
            return
        if gate.take_ready(failure_seen=failure_seen.is_set()):
            if ready_deadline is not None:
                ready_deadline.cancel()
            emit('ready', 'media_opened_and_playing', muted=True, receiver=args.receiver,
                 playback_item=args.playback_item, keep_playing=args.keep_playing)

    def opened():
        if closing:
            return
        gate.opened = True
        emit('stage', 'media_opened')
        maybe_ready()

    def playback_changed(state):
        if closing:
            return
        gate.playing = state == api.MediaPlaybackState.PLAYING
        emit('playback', state.name, state_code=int(state))
        maybe_ready()

    def media_failed(sender, event):
        # Stop a queued ready notification even before the loop handles this failure.
        failure_seen.set()
        dispatch(error, f'MediaFailed {event.error.name} '
                 f'(0x{int(event.extended_error_code) & 0xffffffff:08X}): '
                 f'{event.error_message or "no error message"}')

    def set_transport_status(name):
        controls.playback_status = (api.MediaPlaybackStatus.PLAYING if name == 'Playing'
                                    else api.MediaPlaybackStatus.PAUSED)

    def button(code, raw_name):
        if closing:
            return
        name = BUTTON_NAMES.get(code, 'Unknown')
        emit('button', name, raw=raw_name, button_code=code, receiver=args.receiver)
        try:
            action = apply_transport_command(
                name, keep_playing=args.keep_playing, play=player.play, pause=player.pause,
                set_status=set_transport_status if args.receiver == 'manual' else None)
            if action is not None:
                emit('action', action, command=name)
        except Exception as exc:
            error(f'Button handling failed: {type(exc).__name__}: {exc}')

    def command_received(event, code, name):
        event.handled = True
        dispatch(button, code, name)

    def raw_button(code, raw_name):
        if not closing:
            emit('raw_button', BUTTON_NAMES.get(code, 'Unknown'), raw=raw_name,
                 button_code=code, receiver='smtc_observer')

    def observe(kind, value):
        if not closing:
            emit(kind, value, receiver='smtc_observer')

    def mark(label):
        if not closing:
            emit('marker', label, receiver='operator')

    def subscribe(owner, event, callback):
        def safe_handler(sender, event_args):
            try:
                callback(sender, event_args)
            except Exception as exc:
                failure_seen.set()
                dispatch(error, f'Event callback failed: {type(exc).__name__}: {exc}')
        token = getattr(owner, 'add_' + event)(safe_handler)
        subscriptions.append((owner, event, token, safe_handler))

    try:
        emit('stage', 'endpoint_lookup')
        devices = await asyncio.wait_for(
            api.DeviceInformation.find_all_async(api.DeviceClass.AUDIO_RENDER), timeout=8)
        hint = endpoint_hint.casefold()
        matches = [device for device in devices
                   if hint in device.name.casefold() or hint in device.id.casefold()]
        if len(matches) != 1:
            raise ValueError('Endpoint hint must match exactly one audio output')
        selected = matches[0]
        emit('stage', 'endpoint_matched')
        player = api.MediaPlayer()
        player.audio_device = selected
        player.is_muted = True
        player.is_looping_enabled = True
        commands = player.command_manager
        commands.is_enabled = args.receiver == 'commands'
        controls = player.system_media_transport_controls
        controls.is_enabled = True
        behaviors = []
        enabled_buttons = ('play', 'pause', 'next', 'previous')
        if args.diagnostics or args.receiver == 'manual':
            enabled_buttons += ('stop', 'record', 'fast_forward', 'rewind', 'channel_up', 'channel_down')
        for name in enabled_buttons:
            setattr(controls, 'is_' + name + '_enabled', True)
        if args.receiver == 'manual':
            subscribe(controls, 'button_pressed',
                      lambda sender, event: dispatch(button, int(event.button), event.button.name))
        else:
            if args.diagnostics:
                subscribe(controls, 'button_pressed',
                          lambda sender, event: dispatch(raw_button, int(event.button), event.button.name))
            for name, code in (('next', 6), ('previous', 7), ('play', 0), ('pause', 1)):
                behavior = getattr(commands, name + '_behavior')
                behavior.enabling_rule = api.MediaCommandEnablingRule.ALWAYS
                behaviors.append(behavior)
                subscribe(commands, name + '_received',
                          lambda sender, event, code=code, name=name:
                          command_received(event, code, name.upper()))
        if args.diagnostics:
            subscribe(controls, 'property_changed',
                      lambda sender, event: dispatch(observe, 'property', event.property.name))
            subscribe(controls, 'playback_position_change_requested',
                      lambda sender, event: dispatch(observe, 'seek', str(event.requested_playback_position)))
        session = player.playback_session
        subscribe(session, 'playback_state_changed',
                  lambda sender, event: dispatch(playback_changed, sender.playback_state))
        subscribe(player, 'media_opened', lambda sender, event: dispatch(opened))
        subscribe(player, 'media_failed', media_failed)
        updater = controls.display_updater
        updater.type = api.MediaPlaybackType.MUSIC
        updater.music_properties.title = SESSION_TITLE
        updater.music_properties.artist = 'Muted local observer'
        updater.update()
        if args.receiver == 'manual':
            controls.playback_status = api.MediaPlaybackStatus.PLAYING
        emit('stage', 'controls_configured', receiver=args.receiver,
             playback_item=args.playback_item, keep_playing=args.keep_playing)
        emit('stage', 'source_file_opening')
        source_file = await asyncio.wait_for(
            api.StorageFile.get_file_from_path_async(str(args.wave.resolve())), timeout=8)
        source = api.MediaSource.create_from_storage_file(source_file)
        if args.playback_item:
            item = api.MediaPlaybackItem(source)
            properties = item.get_display_properties()
            properties.type = api.MediaPlaybackType.MUSIC
            properties.music_properties.title = SESSION_TITLE
            properties.music_properties.artist = 'Muted local observer'
            item.apply_display_properties(properties)
        player.source = item if item is not None else source
        emit('stage', 'source_assigned')
        ready_deadline = loop.call_later(args.ready_timeout, error, 'Media readiness deadline expired')
        player.play()
        emit('stage', 'play_requested')
        if stdin is not None:
            markers = ControlInput(stdin, lambda: dispatch(stop.set),
                                   lambda label: dispatch(mark, label), stop_on_eof=args.stop_on_eof)
        if args.seconds is None:
            await stop.wait()
        else:
            try:
                await asyncio.wait_for(stop.wait(), timeout=args.seconds)
            except asyncio.TimeoutError:
                emit('stage', 'duration_complete')
        if not gate.announced and not gate.failed:
            error('Session ended before media became ready')
    except Exception as exc:
        error(f'{type(exc).__name__}: {exc}')
    finally:
        closing = True
        gate.closed = True
        if ready_deadline is not None:
            ready_deadline.cancel()
        if markers is not None:
            try:
                markers.close()
            except Exception as exc:
                gate.failed = True
                emit('error', f'Marker reader close failed: {type(exc).__name__}: {exc}')
        for owner, event, token, handler in reversed(subscriptions):
            try:
                getattr(owner, 'remove_' + event)(token)
            except Exception as exc:
                gate.failed = True
                emit('error', f'Unsubscribe failed: {type(exc).__name__}: {exc}')
        subscriptions.clear()
        for action in ((lambda: setattr(commands, 'is_enabled', False)) if commands else None,
                       (lambda: setattr(controls, 'is_enabled', False)) if controls else None,
                       player.close if player else None, source.close if source else None):
            if action is not None:
                try:
                    action()
                except Exception as exc:
                    gate.failed = True
                    emit('error', f'Close failed: {type(exc).__name__}: {exc}')
        emit('closed', 'released', ready=gate.announced)
    return 1 if gate.failed else 0


