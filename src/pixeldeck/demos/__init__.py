"""Each demo is a small cartridge: render(), handle(), next_delay()."""
from .cartridges import Pulse, Buddy, Rain, Orbit, Focus, Buttons, Signal
from .base import Demo
CATALOG = {demo.key: demo for demo in (Pulse, Buddy, Rain, Orbit, Focus, Buttons, Signal)}

def register(demo_class):
    if not isinstance(demo_class, type) or not issubclass(demo_class, Demo):
        raise TypeError("Cartridges must subclass Demo")
    if demo_class.key in CATALOG:
        raise ValueError("Cartridge key already registered")
    CATALOG[demo_class.key] = demo_class

def create(name):
    try:
        return CATALOG[name]()
    except KeyError:
        raise ValueError("Unknown demo: " + name) from None
