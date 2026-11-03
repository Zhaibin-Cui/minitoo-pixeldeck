"""Portable configuration with no baked-in identity or device address."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re

def home():
    return Path(os.environ.get("PIXELDECK_HOME", Path.home() / ".pixeldeck"))

@dataclass(frozen=True)
class DeviceConfig:
    address: str = ""
    name: str = "Divoom MiniToo-Audio"
    endpoint: str = "MiniToo"
    chunk_delay_ms: float = 10
    quality: int = 72
    timeout: float = 5
    retries: int = 3

    def __post_init__(self):
        if not all(isinstance(v, str) for v in (self.address, self.name, self.endpoint)):
            raise ValueError("Device identifiers must be strings")
        if self.address and not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", self.address):
            raise ValueError("address must be a Bluetooth address")
        for key, low, high in (("chunk_delay_ms", 0, 100), ("quality", 30, 95), ("timeout", 0.05, 30), ("retries", 0, 5)):
            v = getattr(self, key)
            if type(v) not in (int, float) or not low <= v <= high:
                raise ValueError("Invalid " + key)
        if type(self.quality) is not int or type(self.retries) is not int:
            raise ValueError("quality and retries must be integers")

    @classmethod
    def load(cls, path=None):
        source = Path(path) if path else home() / "device.json"
        if not source.exists():
            if path:
                raise FileNotFoundError(source)
            return cls()
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object")
        return cls(**data)

    def save(self, path=None):
        target = Path(path) if path else home() / "device.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return target
