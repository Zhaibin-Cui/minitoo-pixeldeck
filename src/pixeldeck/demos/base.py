class Demo:
    """render must return an RGB 160x128 image and must not perform I/O.

    next_delay returns seconds until a meaningful time event, or None when idle.
    handle accepts button/tick/telemetry/notice events on one state-owner thread.
    """
    key = "custom"
    title = "Custom cartridge"
    description = "A user-defined demo."
    sources = ()
    source_interval = 1.0
    supports_reset = False
    def handle(self, event, now): pass
    def next_delay(self, now): return None
    def render(self, now): raise NotImplementedError

class Animation(Demo):
    def __init__(self):
        self.paused = False
        self.frozen = 0
        self.offset = 0

    def time(self, now):
        return self.frozen if self.paused else now-self.offset

    def handle(self, event, now):
        if event.get("type") == "button" and event.get("button") == "activate":
            if self.paused:
                self.offset = now-self.frozen
            else:
                self.frozen = now-self.offset
            self.paused = not self.paused

    def next_delay(self, now):
        return None if self.paused else 1/3
