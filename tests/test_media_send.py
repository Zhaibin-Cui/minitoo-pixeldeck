"""Synthetic command targeting tests with no WinRT imports or media sessions."""
import asyncio
import builtins
from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pixeldeck.experimental import media_send as sender
from pixeldeck.experimental.media_probe import SESSION_TITLE


def fake_session(title=SESSION_TITLE):
    session = SimpleNamespace(
        source_app_user_model_id='test-probe-identity',
        try_get_media_properties_async=AsyncMock(return_value=SimpleNamespace(title=title)))
    for method in sender.METHODS.values():
        setattr(session, method, AsyncMock(return_value=True))
    return session


def fake_api(*sessions):
    manager = SimpleNamespace(get_sessions=Mock(return_value=sessions))
    api = SimpleNamespace(SessionManager=SimpleNamespace(request_async=AsyncMock(return_value=manager)))
    return api, manager


class TargetingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unique_exact_title_selected_without_logging_other_metadata(self):
        target = fake_session()
        other = fake_session('Unrelated private media title')
        unavailable = fake_session()
        unavailable.try_get_media_properties_async.side_effect = RuntimeError('Private app error')
        api, manager = fake_api(other, target, unavailable)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertIs(await sender.target_session(manager), target)
        self.assertEqual(output.getvalue(), '')

    async def test_missing_duplicate_and_inexact_matches_are_rejected(self):
        for sessions in ((), (fake_session(SESSION_TITLE.lower()),),
                         (fake_session(SESSION_TITLE + ' copy'),),
                         (fake_session(), fake_session())):
            with self.subTest(count=len(sessions)):
                _, manager = fake_api(*sessions)
                with self.assertRaisesRegex(sender.ProbeError, 'exactly one exact-title'):
                    await sender.target_session(manager)

    async def test_session_count_is_bounded_before_property_queries(self):
        sessions = [fake_session() for _ in range(33)]
        _, manager = fake_api(*sessions)
        with self.assertRaisesRegex(sender.ProbeError, 'Too many sessions'):
            await sender.target_session(manager)
        for session in sessions:
            session.try_get_media_properties_async.assert_not_awaited()

    async def test_discovery_never_sends_a_command(self):
        target = fake_session()
        api, _ = fake_api(target)
        with patch.object(sender, 'emit') as emit:
            result = await sender._run_live(SimpleNamespace(send=False, actions=['next']), api)
        self.assertEqual(result, 0)
        emit.assert_any_call('complete', 'discovery_only_no_commands')
        for method in sender.METHODS.values():
            getattr(target, method).assert_not_awaited()

    async def test_title_or_identity_change_cancels_before_sending(self):
        for change in ('title', 'identity', 'missing_properties'):
            with self.subTest(change=change):
                target = fake_session()
                reads = 0

                async def properties():
                    nonlocal reads
                    reads += 1
                    if reads > 1:
                        if change == 'identity':
                            target.source_app_user_model_id = 'different-test-identity'
                        if change == 'missing_properties':
                            return None
                        if change == 'title':
                            return SimpleNamespace(title='Changed title')
                    return SimpleNamespace(title=SESSION_TITLE)

                target.try_get_media_properties_async.side_effect = properties
                api, _ = fake_api(target)
                with patch.object(sender, 'emit'), self.assertRaisesRegex(sender.ProbeError, 'identity changed'):
                    await sender._run_live(SimpleNamespace(send=True, actions=['next']), api)
                target.try_skip_next_async.assert_not_awaited()

    async def test_commands_target_same_session_and_acceptance_is_not_callback_proof(self):
        target, other = fake_session(), fake_session('Other media')
        target.try_skip_previous_async.return_value = False
        api, _ = fake_api(other, target)
        with patch.object(sender, 'emit') as emit, patch.object(sender.asyncio, 'sleep', new_callable=AsyncMock):
            result = await sender._run_live(SimpleNamespace(send=True, actions=['next', 'previous']), api)
        self.assertEqual(result, 1)
        self.assertEqual(target.try_get_media_properties_async.await_count, 3)
        target.try_skip_next_async.assert_awaited_once_with()
        target.try_skip_previous_async.assert_awaited_once_with()
        for method in sender.METHODS.values():
            getattr(other, method).assert_not_awaited()
        emit.assert_any_call('command_result', 'next', accepted=True, callback_observed=False)
        emit.assert_any_call('command_result', 'previous', accepted=False, callback_observed=False)


class CommandTests(unittest.TestCase):
    def test_import_and_format_selftest_never_load_winrt(self):
        original_import = builtins.__import__

        def no_winrt(name, *args, **kwargs):
            if name == 'winrt' or name.startswith('winrt.'):
                raise AssertionError('Offline operation attempted to import WinRT')
            return original_import(name, *args, **kwargs)

        output = io.StringIO()
        with patch('builtins.__import__', side_effect=no_winrt), redirect_stdout(output):
            importlib.reload(sender)
            with patch.object(sender, '_load_winrt') as load:
                self.assertEqual(sender.main(['--self-test-json']), 0)
                load.assert_not_called()
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(all(event['synthetic'] and not event['hardware_positive_control'] for event in events))
        self.assertFalse(events[1]['callback_observed'])
        self.assertFalse(events[-1]['hardware_accessed'])

    def test_command_limit_is_checked_before_loading_optional_runtime(self):
        with patch.object(sender, '_load_winrt') as load, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                sender.main(['--send', '--actions', 'next', 'next', 'next', 'next', 'next'])
        self.assertEqual(error.exception.code, 2)
        load.assert_not_called()

    def test_live_path_has_overall_deadline_and_releases_apartment(self):
        api = SimpleNamespace(ApartmentType=SimpleNamespace(MULTI_THREADED='mta'),
                              init_apartment=Mock(), uninit_apartment=Mock())
        actual_wait_for = asyncio.wait_for
        with patch.object(sender, '_load_winrt', return_value=api), \
                patch.object(sender, '_run_live', new_callable=AsyncMock, return_value=0) as run, \
                patch.object(sender.asyncio, 'wait_for', wraps=actual_wait_for) as wait:
            self.assertEqual(sender.main([]), 0)
        self.assertEqual(wait.call_args.args[1], 25)
        self.assertFalse(run.call_args.args[0].send)
        api.init_apartment.assert_called_once_with('mta')
        api.uninit_apartment.assert_called_once_with()

    def test_native_failure_text_is_not_logged_and_apartment_is_released(self):
        api = SimpleNamespace(ApartmentType=SimpleNamespace(MULTI_THREADED='mta'),
                              init_apartment=Mock(), uninit_apartment=Mock())
        output = io.StringIO()
        with patch.object(sender, '_load_winrt', return_value=api), \
                patch.object(sender, '_run_live', new_callable=AsyncMock,
                             side_effect=RuntimeError('Unrelated private metadata')), redirect_stdout(output):
            self.assertEqual(sender.main(['--send']), 1)
        self.assertNotIn('Unrelated private metadata', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['detail'], 'query_or_command_failed')
        api.uninit_apartment.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
