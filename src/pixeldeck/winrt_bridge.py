"""Production JSONL child: an endpoint-specific muted WinRT input carrier."""
import argparse
import asyncio
from pathlib import Path
import sys

from .windows_media import SessionOptions, forward_stdin, load_winrt, make_emitter, run_session


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ['--stdin-reader']:
        forward_stdin(sys.stdin, sys.stdout)
        return 0
    emit = make_emitter(sys.stdout, production=True)
    if arguments == ['--self-test-json']:
        emit('button', 'Next')
        emit('button', 'Play')
        emit('button', 'Pause')
        emit('closed', 'format_only', hardware_accessed=False)
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('endpoint_hint', metavar='ENDPOINT_HINT')
    parser.add_argument('wave', type=Path, metavar='SILENCE_WAV')
    args = parser.parse_args(arguments)
    api = None
    initialized = False
    try:
        if not args.endpoint_hint.strip():
            raise ValueError('A nonempty audio endpoint hint is required')
        if not args.wave.is_file():
            raise ValueError('The selected silent WAV file does not exist')
        api = load_winrt()
        api.init_apartment(api.ApartmentType.MULTI_THREADED)
        initialized = True
        # Commands, playback item, follow-state, unlimited session, stop on stdin EOF.
        options = SessionOptions(wave=args.wave)
        return asyncio.run(run_session(options, args.endpoint_hint, api, emit, sys.stdin))
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
