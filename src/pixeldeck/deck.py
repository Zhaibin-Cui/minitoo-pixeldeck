"""Pure navigation and cartridge ownership; no GUI or platform imports."""
from .demos import CATALOG, create

class Deck:
    def __init__(self, selected='buddy'):
        self.demos={key:create(key) for key in CATALOG}
        self.keys=list(self.demos)
        self.index=self.keys.index(selected)
    @property
    def active(self): return self.demos[self.keys[self.index]]
    def handle(self,event,now):
        if event['type']=='button' and event['button']=='reset' and not self.active.supports_reset:
            return
        if event['type']=='button' and event['button'] in ('next','previous'):
            self.index=(self.index+(1 if event['button']=='next' else -1))%len(self.keys)
        elif event['type']=='select': self.index=self.keys.index(event['demo'])
        elif event['type']=='notice': self.demos['signal'].handle(event,now)
        elif event['type']=='build': self.demos['build'].handle(event,now)
        else: self.active.handle(event,now)
