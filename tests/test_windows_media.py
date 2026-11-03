"""Shared-session and cancellable-stdin checks without Windows media access."""
import asyncio
from enum import IntEnum
import io
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pixeldeck.windows_media import (
    ControlInput, SessionOptions, forward_stdin, make_emitter, run_session,
)


class SharedMediaTests(unittest.TestCase):
    def test_production_writer_filters_diagnostic_and_extra_button_events(self):
        output = io.StringIO()
        emit = make_emitter(output, production=True)
        for kind, value in (('stage', 'opening'), ('raw_button', 'Pause'),
                            ('playback', 'PLAYING'), ('ready', 'playing'),
                            ('button', 'ChannelUp'), ('button', 'Pause'),
                            ('action', 'pause_requested'), ('closed', 'released')):
            emit(kind, value)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([record['type'] for record in records], ['stage', 'ready', 'button', 'closed'])
        self.assertEqual([record['sequence'] for record in records], [1, 2, 3, 4])
        self.assertTrue(all(record['backend'] == 'winrt' for record in records))

    def test_stdin_protocol_is_bounded_and_distinguishes_stop_from_eof(self):
        output = io.StringIO()
        forward_stdin(io.StringIO('mark ' + 'x'*1000 + '\nmark !STOP\nmark check\n'), output)
        self.assertEqual(output.getvalue().splitlines(), ['CHECK', '!EOF'])
        output = io.StringIO()
        forward_stdin(io.StringIO('stop\nmark AFTER_STOP\n'), output)
        self.assertEqual(output.getvalue().splitlines(), ['!STOP'])

    def test_control_reader_preserves_tty_flags_and_production_eof_semantics(self):
        for is_tty, stop_on_eof in ((True, True), (False, True), (False, False)):
            with self.subTest(is_tty=is_tty, stop_on_eof=stop_on_eof):
                stream = Mock()
                stream.isatty.return_value = is_tty
                stopped, marked = Mock(), Mock()
                with patch('pixeldeck.windows_media.subprocess.Popen') as factory, \
                        patch('pixeldeck.windows_media.subprocess.CREATE_NO_WINDOW', 0x08000000, create=True):
                    process = factory.return_value
                    process.stdout = io.StringIO('UP\n!EOF\n')
                    process.poll.return_value = 0
                    reader = ControlInput(stream, stopped, marked, stop_on_eof=stop_on_eof)
                    reader.thread.join(timeout=1)
                    reader.close()
                    self.assertEqual(factory.call_args.kwargs['creationflags'], 0 if is_tty else 0x08000000)
                    marked.assert_called_once_with('UP')
                    self.assertEqual(stopped.call_count, int(stop_on_eof))
                    self.assertFalse(reader.thread.is_alive())
                    self.assertTrue(process.stdout.closed)

    def test_real_helper_eof_stops_production_and_releases_pipe(self):
        read_fd, write_fd = os.pipe()
        stopped = threading.Event()
        labels = []
        with os.fdopen(read_fd, 'r', encoding='utf-8') as stream:
            reader = ControlInput(stream, stopped.set, labels.append, stop_on_eof=True)
            try:
                with os.fdopen(write_fd, 'w', encoding='utf-8') as producer:
                    producer.write('mark EOF_CHECK\n')
                self.assertTrue(stopped.wait(5), 'EOF did not stop the production receiver')
                self.assertEqual(labels, ['EOF_CHECK'])
            finally:
                reader.close()
            self.assertFalse(reader.thread.is_alive())
            self.assertTrue(reader.process.stdout.closed)

    def test_close_cancels_real_helper_blocked_on_open_input(self):
        read_fd, write_fd = os.pipe()
        stopped = Mock()
        with os.fdopen(read_fd, 'r', encoding='utf-8') as stream, \
                os.fdopen(write_fd, 'w', encoding='utf-8'):
            reader = ControlInput(stream, stopped, Mock(), stop_on_eof=True)
            reader.close()
            stopped.assert_not_called()
            self.assertFalse(reader.thread.is_alive())
            self.assertIsNotNone(reader.process.returncode)

    def test_production_session_follows_pause_play_and_closes_on_stdin_signal(self):
        class State(IntEnum):
            PAUSED = 4
            PLAYING = 3

        class Events:
            def __init__(self):
                self.handlers = {}
                self.registered = []

            def __getattr__(self, name):
                if name.startswith('add_'):
                    event = name[4:]
                    def add(handler):
                        self.handlers[event] = handler
                        self.registered.append(event)
                        return event
                    return add
                if name.startswith('remove_'):
                    return lambda token: self.handlers.pop(token)
                raise AttributeError(name)

        controls = Events()
        controls.display_updater = SimpleNamespace(music_properties=SimpleNamespace(), update=Mock())
        commands = Events()
        for name in ('next', 'previous', 'play', 'pause'):
            setattr(commands, name + '_behavior', SimpleNamespace())
        session = Events()
        player = Events()
        player.command_manager = commands
        player.system_media_transport_controls = controls
        player.playback_session = session
        player.close = Mock()

        def play():
            session.playback_state = State.PLAYING
            player.handlers['media_opened'](player, None)
            session.handlers['playback_state_changed'](session, None)

        def pause():
            session.playback_state = State.PAUSED
            session.handlers['playback_state_changed'](session, None)

        player.play = Mock(side_effect=play)
        player.pause = Mock(side_effect=pause)
        source = SimpleNamespace(close=Mock())
        item = SimpleNamespace(get_display_properties=lambda: SimpleNamespace(music_properties=SimpleNamespace()),
                               apply_display_properties=Mock())

        async def find_devices(_):
            return [SimpleNamespace(name='test output', id='test-id')]

        async def get_file(_):
            return object()

        api = SimpleNamespace(
            DeviceInformation=SimpleNamespace(find_all_async=find_devices),
            DeviceClass=SimpleNamespace(AUDIO_RENDER=1), MediaPlayer=lambda: player,
            MediaPlaybackState=State, MediaPlaybackStatus=State,
            MediaCommandEnablingRule=SimpleNamespace(ALWAYS=1),
            MediaPlaybackType=SimpleNamespace(MUSIC=1),
            StorageFile=SimpleNamespace(get_file_from_path_async=get_file),
            MediaSource=SimpleNamespace(create_from_storage_file=lambda _: source),
            MediaPlaybackItem=lambda _: item,
        )
        pause_event, play_event = SimpleNamespace(handled=False), SimpleNamespace(handled=False)
        readers = []

        class Input:
            def __init__(self, stream, on_stop, on_marker, *, stop_on_eof):
                self.closed = False
                self.stop_on_eof = stop_on_eof
                readers.append(self)
                loop = asyncio.get_running_loop()
                loop.call_soon(commands.handlers['pause_received'], commands, pause_event)
                loop.call_later(.01, commands.handlers['play_received'], commands, play_event)
                loop.call_later(.02, on_stop)

            def close(self):
                self.closed = True

        output = io.StringIO()
        with patch('pixeldeck.windows_media.ControlInput', Input):
            result = asyncio.run(run_session(SessionOptions(Path('silent.wav')), 'test output',
                                             api, make_emitter(output, production=True), object()))
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(result, 0)
        self.assertEqual([record['value'] for record in records if record['type'] == 'button'], ['Pause', 'Play'])
        self.assertEqual(sum(record['type'] == 'ready' for record in records), 1)
        self.assertFalse(any(record['type'] == 'error' for record in records))
        self.assertTrue(pause_event.handled and play_event.handled)
        self.assertEqual(player.play.call_count, 2)
        player.pause.assert_called_once_with()
        self.assertTrue(player.is_muted)
        self.assertEqual(controls.registered, [])
        self.assertFalse(commands.handlers or player.handlers or session.handlers)
        player.close.assert_called_once_with()
        source.close.assert_called_once_with()
        self.assertTrue(readers[0].closed and readers[0].stop_on_eof)


if __name__ == '__main__':
    unittest.main()
