"""Select an input process without opening an audio or Bluetooth session."""
from importlib import metadata
from pathlib import Path
import sys

from .config import home


WINRT_PACKAGES = (
    'winrt-Windows.Foundation', 'winrt-Windows.Foundation.Collections',
    'winrt-Windows.Storage.Streams', 'winrt-Windows.Devices.Enumeration',
    'winrt-Windows.Media', 'winrt-Windows.Media.Core',
    'winrt-Windows.Media.Playback', 'winrt-Windows.Storage',
)


def winrt_status():
    """Inspect package metadata only; the child verifies imports at startup."""
    if sys.platform != 'win32':
        return {'available': False, 'reason': 'Windows is required'}
    if sys.version_info < (3, 11):
        return {'available': False, 'reason': 'Python 3.11 or later is required'}
    try:
        runtime = metadata.version('winrt-runtime')
        projections = [metadata.version(name) for name in WINRT_PACKAGES]
    except metadata.PackageNotFoundError:
        return {'available': False, 'reason': 'Install the windows-input extra'}
    except OSError:
        return {'available': False, 'reason': 'Dependency metadata could not be read'}
    try:
        family = tuple(int(part) for part in runtime.split('.')[:2])
    except ValueError:
        family = ()
    if not (len(family) == 2 and (4, 1) <= family < (5, 0)) or not all(value.startswith('4!') for value in projections):
        return {'available': False, 'reason': 'Install the validated windows-input dependency family'}
    return {'available': True, 'reason': 'Dependency metadata found; live startup still required'}


def select_backend(requested='auto'):
    if requested not in ('auto', 'winrt', 'legacy'):
        raise ValueError('Input backend must be auto, winrt or legacy')
    if requested == 'legacy':
        return requested
    status = winrt_status()
    if status['available']:
        return 'winrt'
    if requested == 'winrt':
        raise RuntimeError('WinRT input unavailable: ' + status['reason'])
    return 'legacy'


def input_command(config, backend):
    wave = Path(__file__).parent / 'native' / 'silence.wav'
    if backend == 'winrt':
        return [sys.executable, '-u', '-m', 'pixeldeck.winrt_bridge', config.endpoint, str(wave)]
    if backend != 'legacy':
        raise ValueError('Resolve the input backend before constructing its command')
    executable = home() / 'native' / 'MediaBridge.exe'
    if not executable.is_file():
        raise FileNotFoundError('Install the windows-input extra or run pixeldeck build-input --backend legacy')
    return [str(executable), config.endpoint, str(wave)]
