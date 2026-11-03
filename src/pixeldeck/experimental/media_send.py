"""Synthetic Windows media commands to one exact Pixeldeck diagnostic session.

Default operation only discovers the session. Explicit --send requests commands;
accepted requests do not prove receiver callbacks or Bluetooth hardware delivery.
No current/default session fallback is used, and other app metadata is not logged.
https://learn.microsoft.com/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys
from types import SimpleNamespace

from .media_probe import SESSION_TITLE


METHODS = {'next': 'try_skip_next_async', 'previous': 'try_skip_previous_async',
           'pause': 'try_pause_async', 'play': 'try_play_async'}


class ProbeError(RuntimeError):
    """A diagnostic message that contains no external session metadata."""


def emit(kind, value, **fields):
    print(json.dumps({'source': 'gsmtc-synthetic', 'type': kind, 'value': value,
                      'synthetic': True, 'hardware_positive_control': False,
                      'utc': datetime.now(timezone.utc).isoformat(), **fields},
                     ensure_ascii=True), flush=True)


def _load_winrt():
    """Optional bindings are loaded only for explicit live discovery or sending."""
    if sys.platform != 'win32':
        raise ProbeError('Live media diagnostics require Windows; --self-test-json works offline')
    if sys.version_info < (3, 11):
        raise ProbeError('Live media diagnostics require Python 3.11 or later')
    try:
        from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    except ImportError as exc:
        raise ProbeError(
            'Optional PyWinRT dependencies are unavailable. Install '
            '"minitoo-pixeldeck[windows-input]" with Python 3.11 or later on Windows'
        ) from exc
    return SimpleNamespace(ApartmentType=ApartmentType, init_apartment=init_apartment,
                           uninit_apartment=uninit_apartment,
                           SessionManager=GlobalSystemMediaTransportControlsSessionManager)


async def target_session(manager):
    sessions = list(manager.get_sessions())
    if len(sessions) > 32:
        raise ProbeError('Too many sessions for this bounded probe')

    async def matches(session):
        try:
            properties = await asyncio.wait_for(session.try_get_media_properties_async(), 3)
            return properties is not None and properties.title == SESSION_TITLE
        except Exception:
            # Another app's name, metadata and exception text stay private.
            return False

    flags = await asyncio.gather(*(matches(session) for session in sessions))
    selected = [session for session, match in zip(sessions, flags) if match]
    if len(selected) != 1:
        raise ProbeError('Expected exactly one exact-title probe session; matches=' + str(len(selected)))
    return selected[0]


async def _run_live(args, api):
    manager = await asyncio.wait_for(api.SessionManager.request_async(), 8)
    target = await target_session(manager)
    source_identity = target.source_app_user_model_id  # Never logged.
    emit('matched', 'exact_probe_title', unique=True)
    if not args.send:
        emit('complete', 'discovery_only_no_commands')
        return 0
    accepted = True
    for index, action in enumerate(args.actions):
        # Revalidate immediately before calling the SAME original session object.
        properties = await asyncio.wait_for(target.try_get_media_properties_async(), 3)
        if (properties is None or properties.title != SESSION_TITLE
                or target.source_app_user_model_id != source_identity):
            raise ProbeError('Probe identity changed; command cancelled')
        emit('marker', 'synthetic_' + action + '_before')
        result = bool(await asyncio.wait_for(getattr(target, METHODS[action])(), 5))
        emit('command_result', action, accepted=result, callback_observed=False)
        emit('marker', 'synthetic_' + action + '_after')
        accepted = accepted and result
        if index + 1 < len(args.actions):
            await asyncio.sleep(0.5)
    emit('complete', 'synthetic_requests_finished', all_accepted=accepted)
    return 0 if accepted else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true',
                        help='Send to the uniquely matched probe; default is discovery only')
    parser.add_argument('--actions', nargs='+', choices=tuple(METHODS), default=['next', 'previous'])
    parser.add_argument('--self-test-json', action='store_true')
    args = parser.parse_args(argv)
    if len(args.actions) > 4:
        parser.error('At most four synthetic commands per run')
    if args.self_test_json:
        emit('marker', 'synthetic_next_before', self_test=True)
        emit('command_result', 'next', accepted=True, callback_observed=False, self_test=True)
        emit('complete', 'format_only_no_session', self_test=True, hardware_accessed=False)
        return 0
    api = None
    initialized = False
    try:
        api = _load_winrt()
        api.init_apartment(api.ApartmentType.MULTI_THREADED)
        initialized = True
        return asyncio.run(asyncio.wait_for(_run_live(args, api), 25))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        missing = exc if isinstance(exc, ModuleNotFoundError) else exc.__cause__
        fields = {'missing_module': missing.name} if isinstance(missing, ModuleNotFoundError) else {}
        emit('error', type(exc).__name__,
             detail=str(exc) if isinstance(exc, ProbeError) else 'query_or_command_failed', **fields)
        return 1
    finally:
        if initialized:
            api.uninit_apartment()


if __name__ == '__main__':
    raise SystemExit(main())
