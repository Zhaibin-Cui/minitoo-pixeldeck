"""Driver tests reconstruct actual transmitted bytes through the ACK path."""
import math
import sys
import unittest
from unittest.mock import patch

from PIL import Image

from pixeldeck.config import DeviceConfig
from pixeldeck.driver import MiniToo
from pixeldeck.encoding import encode_frame
from pixeldeck.protocol import jpeg_clip, zstd_clip, upload, valid
from test_core import FakeSocket

try:
    import zstandard as zstd
except (ImportError, OSError):
    zstd = None


class CodecDriverTests(unittest.TestCase):
    def device(self, codec='jpeg', **kwargs):
        fake = FakeSocket(**kwargs)
        config = DeviceConfig(address=':'.join(('00',)*6), codec=codec, chunk_delay_ms=0, timeout=.1)
        device = MiniToo(config, socket_factory=lambda:fake)
        self.addCleanup(device.close)
        return device, fake

    def assert_transmitted(self, fake, expected, report, codec):
        self.assertTrue(all(valid(raw) for raw in fake.sent))
        self.assertEqual(fake.sent[0], upload(expected).announce)
        self.assertEqual(b''.join(raw[11:-3] for raw in fake.sent[1:]), expected)
        self.assertEqual(report['bytes'], len(expected))
        self.assertEqual(report['codec'], codec)
        self.assertTrue(math.isfinite(report['encode_ms']) and report['encode_ms'] >= 0)
        self.assertAlmostEqual(sum(report[key] for key in ('announce_ms','send_ms','completion_ms')),
                               report['transfer_ms'], delta=.03)

    def test_default_jpeg_wire_bytes_and_timing_fields(self):
        image = Image.new('RGB', (160, 128), 'red')
        device, fake = self.device()
        report = device.show(image)
        self.assert_transmitted(fake, jpeg_clip([image]), report, 'jpeg')

    def test_clip_stays_jpeg_even_when_config_requests_zstd(self):
        images = [Image.new('RGB', (160, 128), color) for color in ('red','blue')]
        device, fake = self.device('zstd')
        with patch('pixeldeck.driver.encode_frame', side_effect=AssertionError('Clip must remain JPEG')):
            report = device.show_clip(images, period_ms=300)
        self.assert_transmitted(fake, jpeg_clip(images, period_ms=300), report, 'jpeg')

    def test_explicit_unavailable_codec_sends_nothing(self):
        device, fake = self.device('zstd')
        with patch.dict(sys.modules, {'zstandard':None}):
            with self.assertRaisesRegex(RuntimeError, 'optional zstandard package'):
                device.show(Image.new('RGB', (160, 128)))
        self.assertEqual(fake.sent, [])

    @unittest.skipIf(zstd is None, 'Optional zstandard package is not installed')
    def test_explicit_and_auto_zstd_transmit_exact_lossless_blob(self):
        image = Image.new('RGB', (160, 128), (13, 42, 77))
        for codec in ('zstd','auto'):
            with self.subTest(codec=codec):
                device, fake = self.device(codec)
                report = device.show(image)
                self.assert_transmitted(fake, zstd_clip([image]), report, 'zstd')

    @unittest.skipIf(zstd is None, 'Optional zstandard package is not installed')
    def test_auto_transport_timeout_never_reencodes_or_reannounces(self):
        image = Image.new('RGB', (160, 128), 'black')
        device, fake = self.device('auto', done=False)
        with patch('pixeldeck.driver.encode_frame', wraps=encode_frame) as encode:
            with self.assertRaises(TimeoutError):
                device.show(image)
            encode.assert_called_once()
        self.assertEqual(sum(raw[4] == 0 for raw in fake.sent), 1)
        self.assertEqual(b''.join(raw[11:-3] for raw in fake.sent[1:]), zstd_clip([image]))

    @unittest.skipIf(zstd is None, 'Optional zstandard package is not installed')
    def test_zstd_obeys_ready_gate_and_retransmits_requested_chunk(self):
        image = Image.new('RGB', (160, 128), 'black')
        device, fake = self.device('zstd', ready=False)
        with self.assertRaises(TimeoutError):
            device.show(image)
        self.assertEqual(len(fake.sent), 1)
        device, fake = self.device('auto', retransmit=True)
        report = device.show(image)
        self.assertEqual(report['codec'], 'zstd')
        self.assertEqual(report['retransmissions'], 1)
        self.assertEqual(fake.sent[-1], upload(zstd_clip([image])).chunks[0])


if __name__ == '__main__':
    unittest.main()
