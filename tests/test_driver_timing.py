"""Timing fields must partition the existing acknowledged transaction."""
import math
import unittest

from PIL import Image

from pixeldeck.config import DeviceConfig
from pixeldeck.driver import MiniToo
from test_core import FakeSocket


class DriverTimingTests(unittest.TestCase):
    def test_stages_sum_to_transfer_including_a_chunk_retransmission(self):
        socket = FakeSocket(retransmit=True)
        config = DeviceConfig(address=':'.join(('00',)*6), chunk_delay_ms=0, timeout=1)
        with MiniToo(config, socket_factory=lambda: socket) as device:
            report = device.show(Image.new('RGB', (160, 128)))
        stages = [report[name] for name in ('announce_ms', 'send_ms', 'completion_ms')]
        self.assertTrue(all(math.isfinite(value) and value >= 0 for value in stages))
        self.assertAlmostEqual(sum(stages), report['transfer_ms'], delta=.03)
        self.assertEqual(report['retransmissions'], 1)


if __name__ == '__main__':
    unittest.main()
