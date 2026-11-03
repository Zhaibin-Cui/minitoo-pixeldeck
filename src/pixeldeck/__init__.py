"""MiniToo Pixeldeck. Importing this package never opens a device."""
__version__ = "0.4.0"
from .config import DeviceConfig
from .driver import MiniToo
from .engine import FramePump
__all__ = ["DeviceConfig", "MiniToo", "FramePump"]
