"""Run after `pip install -e .`. Desktop preview only."""
from pixeldeck.config import DeviceConfig
from pixeldeck.demos import Demo, register
from pixeldeck.pixels import Canvas, CYAN

class Hello(Demo):
    key='hello'
    title='Hello cartridge'
    def __init__(self): self.count=0
    def handle(self,event,now):
        if event.get('type') == 'button' and event.get('button') == 'activate':
            self.count += 1
    def render(self,now):
        c=Canvas(); c.header('HELLO WORLD','08')
        c.text(80,56,f'{self.count:04}',CYAN,3,center=True)
        c.footer('ACTIVATE / MAKE A MARK')
        return c.image

if __name__=='__main__':
    register(Hello)
    from pixeldeck.app import Application
    Application(DeviceConfig(),demo='hello').run()
