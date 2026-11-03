"""Experimental Windows media-input observer, separate from the production backend.

The selected endpoint receives a muted carrier. No system volume, default audio
device, display, or firmware setting is changed. Enter ``mark LABEL`` to annotate
physical actions and ``stop`` to finish. Raw observations are not extra actions.
"""
import argparse
import asyncio
from pathlib import Path
import sys

from ..config import DeviceConfig
from ..windows_media import (
    BUTTON_NAMES, DEFAULT_WAVE, SESSION_TITLE, ReadinessGate, apply_transport_command,
    load_winrt as _load_winrt, make_emitter, run_session as _run_live, validate_limits,
)


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(diagnostics=True, stop_on_eof=False)
    parser.add_argument('--self-test-json', action='store_true')
    parser.add_argument('--config', type=Path, help='Defaults to the normal runtime device configuration')
    parser.add_argument('--endpoint-hint', help='Override the configured audio endpoint hint')
    parser.add_argument('--wave', type=Path, default=DEFAULT_WAVE, help='Defaults to the bundled silent WAV')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--ready-timeout', type=float, default=30)
    parser.add_argument('--receiver', choices=('manual', 'commands'), default='manual')
    parser.add_argument('--playback-item', action='store_true')
    parser.add_argument('--keep-playing', action='store_true',
                        help='Observe commands without changing muted carrier playback state')
    return parser


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        validate_limits(args.seconds, args.ready_timeout)
    except ValueError as exc:
        parser.error(str(exc))
    emit = make_emitter(sys.stdout)
    if args.self_test_json:
        emit('button', 'ChannelUp', raw='CHANNEL_UP', button_code=8)
        emit('raw_button', 'Pause', raw='PAUSE', button_code=1, receiver='smtc_observer')
        emit('closed', 'format_only', hardware_accessed=False)
        return 0
    api = None
    initialized = False
    try:
        api = _load_winrt()
        config = DeviceConfig.load(args.config)
        endpoint_hint = args.endpoint_hint if args.endpoint_hint is not None else config.endpoint
        if not endpoint_hint.strip():
            raise ValueError('A nonempty audio endpoint hint is required')
        if not args.wave.is_file():
            raise ValueError('The selected silent WAV file does not exist')
        api.init_apartment(api.ApartmentType.MULTI_THREADED)
        initialized = True
        return asyncio.run(_run_live(args, endpoint_hint, api, emit, sys.stdin))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        emit('error', f'Initialization failed: {type(exc).__name__}: {exc}')
        emit('closed', 'initialization_failed', ready=False)
        return 1
    finally:
        if initialized:
            api.uninit_apartment()


if __name__ == '__main__':
    raise SystemExit(main())
