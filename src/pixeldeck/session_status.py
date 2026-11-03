"""Keep display and input health separate: an image ACK cannot clear an input error."""

class SessionStatus:
    def __init__(self, send=False, media=False):
        self.mode = 'LIVE DEVICE' if send else 'PREVIEW ONLY / DEVICE OUTPUT OFF'
        self.display = 'DISPLAY / CONNECTING' if send else 'DISPLAY / Desktop preview only'
        self.input = 'INPUT / STARTING MEDIA SESSION' if media else 'INPUT / Desktop controls only'
        self.input_count = 0
        self.input_state = 'starting' if media else 'off'
        self.last_action = ''
        self.input_error = None

    def handle(self, event):
        kind = event.get('type')
        if kind == 'frame.ack':
            self.display = f"DISPLAY / ACK {event['sequence']} / {event['transfer_ms']:.0f} ms / skipped {event['replaced']}"
        elif kind in ('link.error', 'link.lost', 'link.stopped'):
            self.display = 'DISPLAY / ' + str(event.get('message', kind))[:150]
        elif kind == 'input.status':
            state = event.get('kind')
            if state == 'stage':
                # MediaOpened can race the constructor's final progress message.
                # Late progress must not replace readiness or a terminal failure.
                if self.input_state in ('ready', 'error', 'stopped', 'closed'):
                    return
                self.input_state = 'starting'
                self.input = 'INPUT / STARTING: ' + str(event.get('message', ''))[:150]
                return
            self.input_state = state if state in ('ready','error','retrying','stopped','closed') else 'starting'
            if state == 'ready':
                self.input_error = None
                self.input = 'INPUT / Media session ready; awaiting a button'
            elif state == 'error':
                self.input_error = str(event.get('message', 'Media input failed'))[:150]
                self.input = 'INPUT / ERROR: ' + self.input_error
            elif state == 'closed' and self.input_error:
                self.input = 'INPUT / ERROR: ' + self.input_error
            else:
                self.input = 'INPUT / ' + str(event.get('message', state))[:150]
        elif kind == 'button':
            self.input_count += 1
            source = 'DEVICE MEDIA' if event.get('source') == 'media' else 'DESKTOP'
            self.last_action = f"{source}: {event.get('button')} / count {self.input_count}"
