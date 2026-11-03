"""Command-line entry points. Hardware access is explicit in each command."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from PIL import Image, ImageSequence

from . import __version__
from .config import DeviceConfig, home
from .demos import CATALOG
from .driver import MiniToo
from .instance import InstanceLock
from .protocol import fit_image, jpeg_clip, upload


def build_parser():
    parser = argparse.ArgumentParser(prog='pixeldeck', description='MiniToo pixel display toolkit')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List bundled cartridges')
    commands.add_parser('stop', help='Release the running session through local IPC')

    doctor = commands.add_parser('doctor', help='Inspect dependencies and pairing without connecting')
    doctor.add_argument('--config')
    build = commands.add_parser('build-input', help='Check WinRT input or compile the legacy bridge')
    build.add_argument('--backend', choices=('auto', 'winrt', 'legacy'), default='auto')
    audio = commands.add_parser('audio-devices', help='List audio endpoints without opening streams')
    audio.add_argument('--match', help='Filter by device name, for example MiniToo')

    config = commands.add_parser('configure')
    config.add_argument('--address', required=True)
    config.add_argument('--endpoint', default='MiniToo')
    config.add_argument('--output', type=Path)
    config.add_argument('--codec', choices=('jpeg', 'zstd', 'auto'), default='jpeg')

    run = commands.add_parser('run')
    run.add_argument('demo', nargs='?', choices=list(CATALOG), default='buddy')
    run.add_argument('--send', action='store_true')
    run.add_argument('--media', action='store_true')
    run.add_argument('--input-backend', choices=('auto', 'winrt', 'legacy'), default='auto')
    run.add_argument('--audio', action='store_true', help='Enable Audio Lab actions; idle until activated')
    run.add_argument('--audio-input', type=int, help='Explicit microphone index from audio-devices')
    run.add_argument('--audio-output', type=int, help='Explicit speaker index from audio-devices')
    run.add_argument('--stdin', action='store_true')
    run.add_argument('--duration', type=int, default=600)
    run.add_argument('--config')
    run.add_argument('--codec', choices=('jpeg', 'zstd', 'auto'), help='Override live-frame encoding for this run')
    run.add_argument('--chunk-delay-ms', type=float, help='Override packet pacing (0..100 ms) for this run')

    show = commands.add_parser('image')
    show.add_argument('path', type=Path)
    show.add_argument('--fit', choices=('contain', 'cover', 'stretch'), default='contain')
    show.add_argument('--codec', choices=('jpeg', 'zstd', 'auto'))
    clip = commands.add_parser('clip', help='Experimental small GIF upload; preview by default')
    clip.add_argument('path', type=Path)
    clip.add_argument('--frames', type=int, default=2)
    clip.add_argument('--period', type=int, default=250)
    bright = commands.add_parser('brightness', help='Experimental brightness command; dry-run by default')
    bright.add_argument('level', type=int)
    for command in (show, clip, bright):
        command.add_argument('--send', action='store_true')
        command.add_argument('--config')

    export = commands.add_parser('export', help='Render offline PNG/GIF demo previews')
    export.add_argument('demo', choices=list(CATALOG))
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--seconds', type=int, default=4)
    return parser


def _display_config(args, parser):
    config = DeviceConfig.load(args.config)
    overrides = {field: getattr(args, field) for field in ('codec', 'chunk_delay_ms')
                 if getattr(args, field, None) is not None}
    try:
        return replace(config, **overrides) if overrides else config
    except ValueError as exc:
        parser.error(str(exc))


def run_host(args, parser):
    if not 0 <= args.duration <= 86400:
        parser.error('duration must be 0..86400; 0 means until closed')
    if args.media and not args.send:
        parser.error('--media requires --send')
    audio_devices = (args.audio_input, args.audio_output)
    if any(index is not None and index < 0 for index in audio_devices):
        parser.error('Audio device indices must be nonnegative')
    if not args.audio and any(index is not None for index in audio_devices):
        parser.error('Audio device selection requires --audio')
    if args.audio and all(index is None for index in audio_devices):
        parser.error('Select --audio-input and/or --audio-output from audio-devices')
    config = _display_config(args, parser)
    if args.send and not config.address:
        parser.error('No device configured. Use configure --address YOUR_ADDRESS or --config PRIVATE_FILE. '
                     'Preview alone does not update the MiniToo.')
    from .app import Application
    Application(config, args.demo, args.send, args.media, args.stdin, args.duration,
                input_backend=args.input_backend, audio=args.audio,
                audio_input=args.audio_input, audio_output=args.audio_output).run()


def device_command(args, parser):
    config = _display_config(args, parser)
    home().mkdir(parents=True, exist_ok=True)
    if args.command == 'brightness':
        from .protocol import brightness_packet
        raw = brightness_packet(args.level)
        if not args.send:
            print('Experimental packet (not sent): ' + raw.hex(' '))
            return
        job = lambda device: device.brightness(args.level)
    elif args.command == 'image':
        with Image.open(args.path) as source:
            picture = fit_image(source, args.fit)
        preview = home() / 'image-preview.png'
        picture.save(preview)
        if not args.send:
            print(preview)
            return
        job = lambda device: device.show(picture)
    else:
        if not 1 <= args.frames <= 8:
            parser.error('frames must be 1..8 within the 16 KB upload budget')
        with Image.open(args.path) as source:
            pictures = []
            for index, picture in enumerate(ImageSequence.Iterator(source)):
                if index >= args.frames:
                    break
                pictures.append(fit_image(picture))
        data = upload(jpeg_clip(pictures, args.period, config.quality))
        if not args.send:
            print(json.dumps({'experimental': True, 'frames': len(pictures),
                              'bytes': data.size, 'chunks': len(data.chunks), 'sent': False}))
            return
        job = lambda device: device.show_clip(pictures, args.period)
    lock = InstanceLock(home() / 'instance.lock')
    try:
        with MiniToo(config) as device:
            print(json.dumps(job(device)))
    finally:
        lock.close()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == 'list':
        for key, cls in CATALOG.items():
            print(f'{key:9} {cls.title}\n          {cls.description}')
    elif args.command == 'configure':
        print(DeviceConfig(address=args.address, endpoint=args.endpoint, codec=args.codec).save(args.output))
    elif args.command == 'doctor':
        import importlib.util
        import PIL
        from .diagnostics import report
        result = report(DeviceConfig.load(args.config))
        result.update(version=__version__, python=sys.version.split()[0], pillow=PIL.__version__,
                      tkinter=importlib.util.find_spec('tkinter') is not None,
                      telemetry_extra=importlib.util.find_spec('psutil') is not None,
                      audio_extra=importlib.util.find_spec('sounddevice') is not None)
        result.update(display_codec=DeviceConfig.load(args.config).codec,
                      zstd_extra=importlib.util.find_spec('zstandard') is not None)
        print(json.dumps(result, indent=2))
    elif args.command == 'audio-devices':
        from .audio import list_devices
        print(json.dumps(list_devices(args.match), indent=2))
    elif args.command == 'build-input':
        from .input_backends import select_backend
        from .inputs import build_bridge
        if select_backend(args.backend) == 'winrt':
            print('WinRT input dependencies found; the session will verify startup')
        else:
            print(build_bridge())
    elif args.command == 'stop':
        from .control import stop
        print('Stop acknowledged' if stop(home()) else 'No active session')
    elif args.command == 'export':
        from .export import export_demo
        if not 1 <= args.seconds <= 15:
            parser.error('seconds must be 1..15')
        export_demo(args.demo, args.output, args.seconds)
        print(args.output)
    elif args.command == 'run':
        run_host(args, parser)
    else:
        device_command(args, parser)
