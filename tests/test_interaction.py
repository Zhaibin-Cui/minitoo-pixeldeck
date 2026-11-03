import unittest
from pixeldeck.deck import Deck
from pixeldeck.session_status import SessionStatus


class InteractionTests(unittest.TestCase):
    def test_preview_and_live_modes_are_explicit(self):
        self.assertIn('OUTPUT OFF', SessionStatus().mode)
        live = SessionStatus(send=True, media=False)
        self.assertEqual(live.mode, 'LIVE DEVICE')
        self.assertIn('Desktop controls only', live.input)

    def test_display_ack_and_desktop_action_do_not_clear_input_failure(self):
        status = SessionStatus(send=True, media=True)
        status.handle({'type':'input.status', 'kind':'error', 'message':'Input unavailable: bridge missing'})
        failure = status.input
        status.handle({'type':'frame.ack', 'sequence':3, 'transfer_ms':270, 'replaced':1})
        status.handle({'type':'button', 'source':'desktop', 'button':'activate'})
        status.handle({'type':'input.status', 'kind':'closed', 'message':'Media input ended'})
        self.assertEqual(status.input, failure)
        self.assertEqual(status.input_state, 'closed')
        self.assertIn('ACK 3', status.display)
        self.assertIn('activate', status.last_action)

    def test_dashboard_keeps_navigation_until_explicit_leave(self):
        deck = Deck('dashboard')
        deck.handle({'type':'button', 'button':'next'}, 0)
        self.assertEqual(deck.active.key, 'dashboard')
        deck.handle({'type':'button', 'button':'activate'}, 1)
        self.assertEqual(deck.active.key, 'dashboard')
        deck.handle({'type':'button', 'button':'back'}, 2)
        self.assertEqual(deck.active.key, 'dashboard')
        self.assertEqual(deck.handle({'type':'button', 'button':'back'}, 3), 'leave')
        self.assertEqual(deck.active.key, 'buddy')

    def test_late_startup_progress_does_not_replace_ready_or_failure(self):
        status = SessionStatus(send=True, media=True)
        status.handle({'type':'input.status', 'kind':'stage', 'message':'endpoint_lookup'})
        self.assertEqual(status.input_state, 'starting')
        for state in ('ready', 'error', 'stopped'):
            status.handle({'type':'input.status', 'kind':state, 'message':'receiver state'})
            message = status.input
            status.handle({'type':'input.status', 'kind':'stage', 'message':'play_requested'})
            self.assertEqual(status.input_state, state)
            self.assertEqual(status.input, message)
        status.handle({'type':'input.status', 'kind':'retrying', 'message':'new attempt'})
        status.handle({'type':'input.status', 'kind':'stage', 'message':'endpoint_lookup'})
        self.assertEqual(status.input_state, 'starting')

    def test_back_does_not_trigger_old_cartridge_activation(self):
        deck = Deck('buttons')
        deck.handle({'type':'button', 'button':'back'}, 0)
        self.assertEqual(deck.active.count, 0)

    def test_explicit_exit_is_returned_to_host(self):
        deck = Deck('dashboard')
        deck.handle({'type':'button', 'button':'previous'}, 0)
        self.assertEqual(deck.handle({'type':'button', 'button':'activate'}, 1), 'exit')
