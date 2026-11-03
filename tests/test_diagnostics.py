from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from pixeldeck.config import DeviceConfig
from pixeldeck.diagnostics import report


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.config = DeviceConfig(address="AA:BB:CC:DD:EE:FF", endpoint="private-endpoint-value")
        self.registry = MagicMock()
        self.registry.QueryValueEx.return_value = (b"Divoom MiniToo-Audio\0", 3)

    def inspect(self, windows=True, constants=None, files=True, configured=None):
        constants = constants if constants is not None else SimpleNamespace(
            AF_BLUETOOTH=32, BTPROTO_RFCOMM=3, SOCK_STREAM=1)
        with ExitStack() as stack:
            stack.enter_context(patch("pixeldeck.diagnostics._windows", return_value=windows))
            stack.enter_context(patch("pixeldeck.diagnostics.socket", constants))
            stack.enter_context(patch("pixeldeck.diagnostics.home", return_value=Path("private-runtime")))
            stack.enter_context(patch("pixeldeck.diagnostics._is_file", return_value=files))
            stack.enter_context(patch("pixeldeck.diagnostics.shutil.which", return_value="private-powershell-path"))
            stack.enter_context(patch.dict("os.environ", {"WINDIR": "private-system-directory"}))
            # An accidental device connection or broad process probe fails immediately.
            connect = stack.enter_context(patch("socket.socket", side_effect=AssertionError("Socket opened")))
            subprocess = stack.enter_context(patch("subprocess.run", side_effect=AssertionError("Process started")))
            stack.enter_context(patch("pixeldeck.diagnostics.importlib.import_module", return_value=self.registry))
            result = report(self.config if configured is None else configured)
            connect.assert_not_called()
            subprocess.assert_not_called()
            return result

    def test_cached_pairing_match_and_prerequisites(self):
        result = self.inspect()
        self.assertTrue(result["windows_backend_supported"])
        self.assertTrue(result["python_rfcomm"]["available"])
        self.assertEqual(result["pairing"], {"status": "matched", "name_matches": True})
        self.assertTrue(result["media_input"]["bridge_built"])
        self.assertTrue(result["media_input"]["build_prerequisites"]["available"])
        self.assertFalse(result["hardware_accessed"])
        self.assertFalse(result["media_input"]["endpoint_verified"])
        self.assertFalse(result["radio_and_profiles_verified"])
        self.assertFalse(result["live_connection_tested"])
        key = self.registry.OpenKey.call_args.args[1]
        self.assertTrue(key.endswith("aabbccddeeff"))

    def test_missing_pairing_record(self):
        self.registry.OpenKey.side_effect = FileNotFoundError("private registry path")
        self.assertEqual(self.inspect()["pairing"]["status"], "not_found")

    def test_mismatched_pairing_is_not_a_match(self):
        self.registry.QueryValueEx.return_value = ("Some Other Device", 1)
        self.assertEqual(self.inspect()["pairing"], {"status": "name_mismatch", "name_matches": False})

    def test_unsupported_backend_does_not_read_registry(self):
        result = self.inspect(windows=False)
        self.assertFalse(result["windows_backend_supported"])
        self.assertEqual(result["pairing"]["status"], "unsupported_backend")
        self.assertFalse(result["media_input"]["build_prerequisites"]["available"])
        self.registry.OpenKey.assert_not_called()

    def test_unconfigured_device_does_not_read_registry(self):
        result = self.inspect(configured=DeviceConfig())
        self.assertFalse(result["device_configured"])
        self.assertEqual(result["pairing"]["status"], "not_configured")
        self.registry.OpenKey.assert_not_called()

    def test_missing_python_rfcomm_constant_is_reported(self):
        result = self.inspect(constants=SimpleNamespace(AF_BLUETOOTH=32, SOCK_STREAM=1))
        self.assertFalse(result["python_rfcomm"]["BTPROTO_RFCOMM"])
        self.assertFalse(result["python_rfcomm"]["available"])

    def test_permission_error_is_reported_without_raw_exception(self):
        self.registry.OpenKey.side_effect = PermissionError("private registry identity")
        result = self.inspect(files=False)
        self.assertEqual(result["pairing"]["status"], "access_denied")
        self.assertFalse(result["media_input"]["bridge_built"])
        self.assertFalse(result["media_input"]["build_prerequisites"]["available"])
        self.assertNotIn("private registry identity", json.dumps(result))

    def test_report_does_not_echo_identifiers_or_local_paths(self):
        encoded = json.dumps(self.inspect())
        for private in (self.config.address, self.config.endpoint, "aabbccddeeff",
                        "private-runtime", "private-system-directory", "private-powershell-path"):
            self.assertNotIn(private, encoded)
        self.assertIn("Bluetooth version alone does not establish compatibility.", encoded)


if __name__ == "__main__":
    unittest.main()
