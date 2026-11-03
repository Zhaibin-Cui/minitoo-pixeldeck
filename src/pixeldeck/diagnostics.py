"""Fast, read-only preflight checks without opening Bluetooth or audio sessions.

The report deliberately excludes addresses, endpoint values, host identities,
filesystem paths and raw exception text. Registry data is cached pairing evidence,
not proof that a device is connected or that its services are available now.
"""
import importlib
import os
from pathlib import Path
import shutil
import socket

from .config import home


def _windows():
    return os.name == "nt"


def _is_file(path):
    try:
        return Path(path).is_file()
    except OSError:
        return False


def _pairing(config, windows):
    if not windows:
        return {"status": "unsupported_backend", "name_matches": None}
    if not config.address:
        return {"status": "not_configured", "name_matches": None}
    try:
        registry = importlib.import_module("winreg")
    except ImportError:
        return {"status": "unavailable", "name_matches": None}
    key_path = "SYSTEM\\CurrentControlSet\\Services\\BTHPORT\\Parameters\\Devices\\" + config.address.replace(":", "").lower()
    try:
        # OpenKey defaults to KEY_READ; no registry value is changed.
        with registry.OpenKey(registry.HKEY_LOCAL_MACHINE, key_path) as key:
            name, _ = registry.QueryValueEx(key, "Name")
        if isinstance(name, bytes):
            name = name.split(b"\0", 1)[0].decode("utf-8")
        matched = str(name).strip().casefold() == config.name.casefold()
        return {"status": "matched" if matched else "name_mismatch", "name_matches": matched}
    except FileNotFoundError:
        return {"status": "not_found", "name_matches": None}
    except PermissionError:
        return {"status": "access_denied", "name_matches": None}
    except (OSError, UnicodeError, TypeError, ValueError):
        return {"status": "unavailable", "name_matches": None}


def _prerequisites(windows):
    result = {"compiler": False, "framework_references": False,
              "winmetadata": False, "powershell": False}
    if windows:
        directory = os.environ.get("WINDIR")
        if directory:
            root = Path(directory)
            framework = root / "Microsoft.NET" / "Framework64" / "v4.0.30319"
            result["compiler"] = _is_file(framework / "csc.exe")
            result["framework_references"] = all(_is_file(framework / name) for name in (
                "System.Runtime.WindowsRuntime.dll", "System.Runtime.dll",
                "System.Runtime.InteropServices.WindowsRuntime.dll"))
            result["winmetadata"] = all(_is_file(root / "System32" / "WinMetadata" / name) for name in (
                "Windows.Foundation.winmd", "Windows.Media.winmd", "Windows.Devices.winmd"))
        result["powershell"] = shutil.which("powershell.exe") is not None
    result["available"] = all(result.values())
    return result


def report(config):
    """Return privacy-preserving preflight facts; never creates a socket or player.

    Reads only Python/platform features, local file presence, PATH and the one
    configured cached pairing registry record. It does not invoke a subprocess,
    enumerate nearby devices, query audio endpoints, or certify radio capability.
    """
    windows = _windows()
    constants = {name: hasattr(socket, name) for name in (
        "AF_BLUETOOTH", "BTPROTO_RFCOMM", "SOCK_STREAM")}
    constants["available"] = all(constants.values())
    return {
        "hardware_accessed": False,
        "windows_backend_supported": windows,
        "python_rfcomm": constants,
        "device_configured": bool(config.address),
        "pairing": _pairing(config, windows),
        "media_input": {
            "bridge_built": _is_file(home() / "native" / "MediaBridge.exe"),
            "endpoint_configured": bool(config.endpoint.strip()),
            "endpoint_verified": False,
            "build_prerequisites": _prerequisites(windows),
        },
        "radio_and_profiles_verified": False,
        "live_connection_tested": False,
        "compatibility_note": "Bluetooth version alone does not establish compatibility.",
        "requirements": [
            "Display output needs Bluetooth Classic BR/EDR with RFCOMM/SPP support and working Windows drivers.",
            "The built-in driver requires a configured paired address whose cached device name matches.",
            "Optional media input additionally needs AVRCP routing and a uniquely matched Windows audio output endpoint.",
            "BLE or LE Audio support alone does not demonstrate the required Classic paths.",
            "A matching cached pairing record does not prove that the device is currently reachable.",
        ],
    }
