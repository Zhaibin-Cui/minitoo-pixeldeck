"""Pure navigation and cartridge ownership; no GUI or platform imports."""
from .demos import CATALOG, create


class Deck:
    def __init__(self, selected='buddy'):
        self.demos = {key: create(key) for key in CATALOG}
        self.keys = list(self.demos)
        self.index = self.keys.index(selected)

    @property
    def active(self):
        return self.demos[self.keys[self.index]]

    def observe(self, event, now):
        """Update diagnostic state without navigation or a render request."""
        for demo in self.demos.values():
            demo.observe(event, now)

    def handle(self, event, now):
        kind = event['type']
        if kind.startswith('audio.'):
            return self.demos['audio'].handle(event, now)
        if kind == 'button':
            if self.active.captures_navigation:
                action = self.active.handle(event, now)
                if action == 'leave':
                    self.index = self.keys.index('buddy')
                return action
            button = event['button']
            if button == 'back' or (button == 'reset' and not self.active.supports_reset):
                return
            if button in ('next', 'previous'):
                offset = 1 if button == 'next' else -1
                self.index = (self.index + offset) % len(self.keys)
                return
        if kind == 'select':
            self.index = self.keys.index(event['demo'])
        elif kind == 'notice':
            self.demos['signal'].handle(event, now)
        elif kind == 'build':
            self.demos['build'].handle(event, now)
        else:
            return self.active.handle(event, now)
