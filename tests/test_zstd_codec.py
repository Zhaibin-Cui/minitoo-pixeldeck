import builtins
import random
import struct
import sys
import unittest
from unittest.mock import patch

from PIL import Image

from pixeldeck.protocol import jpeg_clip, upload, valid, zstd_clip

try:
    import zstandard as zstd
except ImportError:
    zstd = None


class ZstdValidationTests(unittest.TestCase):
    def test_native_dependency_load_failure_is_reported_as_unavailable(self):
        original_import = builtins.__import__

        def load(name, *args, **kwargs):
            if name == 'zstandard':
                raise OSError('Native module unavailable')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=load):
            with self.assertRaisesRegex(RuntimeError, 'optional zstandard package') as caught:
                zstd_clip([Image.new('RGB', (160, 128))])
        self.assertIsInstance(caught.exception.__cause__, OSError)

    def test_missing_optional_dependency_is_clear_and_jpeg_still_works(self):
        frame = Image.new("RGB", (160, 128), "red")
        with patch.dict(sys.modules, {"zstandard": None}):
            with self.assertRaisesRegex(RuntimeError, "optional zstandard package"):
                zstd_clip([frame])
            self.assertEqual(jpeg_clip([frame])[0], 0x23)

    def test_invalid_parameters_are_rejected_before_loading_dependency(self):
        frame = Image.new("RGB", (160, 128))
        with patch.dict(sys.modules, {"zstandard": None}):
            for period in (0, 65536, True, 1.5):
                with self.subTest(period=period), self.assertRaises(ValueError):
                    zstd_clip([frame], period)
            for level in (0, 18, True, 1.5):
                with self.subTest(level=level), self.assertRaises(ValueError):
                    zstd_clip([frame], level=level)
            for frames in ([], [Image.new("RGB", (128, 128))], [object()]):
                with self.subTest(frames=frames), self.assertRaises(ValueError):
                    zstd_clip(frames)

    def test_infinite_frame_iterable_is_rejected_after_five_reads(self):
        consumed = []

        def frames():
            while True:
                consumed.append(1)
                if len(consumed) > 5:
                    raise AssertionError("Unbounded frame consumption")
                yield None

        with self.assertRaises(ValueError):
            zstd_clip(frames())
        self.assertEqual(len(consumed), 5)


@unittest.skipIf(zstd is None, "Optional zstandard package is not installed")
class ZstdCodecTests(unittest.TestCase):
    def test_lossless_pixels_metadata_and_existing_upload_packets(self):
        frame = Image.new("RGB", (160, 128), (11, 23, 37))
        frame.putpixel((159, 127), (255, 128, 0))
        original = frame.tobytes()
        blob = zstd_clip([frame], 40)
        marker, count, period, rows, columns, length = struct.unpack(">BBHBBI", blob[:10])
        self.assertEqual((marker, count, period, rows, columns), (0x25, 1, 40, 8, 10))
        self.assertEqual(length, len(blob)-10)
        self.assertEqual(blob[10:14], bytes.fromhex("28 b5 2f fd"))
        metadata = zstd.get_frame_parameters(blob[10:])
        self.assertEqual(metadata.content_size, len(original))
        self.assertLessEqual(metadata.window_size, 131072)
        self.assertFalse(metadata.has_checksum)
        self.assertEqual(metadata.dict_id, 0)
        self.assertEqual(zstd.ZstdDecompressor().decompress(blob[10:]), original)
        self.assertEqual(frame.tobytes(), original)
        job = upload(blob)
        self.assertTrue(all(valid(packet) for packet in (job.announce, *job.chunks)))
        self.assertEqual(b"".join(packet[11:-3] for packet in job.chunks), blob)

    def test_four_frames_keep_order_and_decoder_window_bound(self):
        frames = [Image.new("RGB", (160, 128), (i*60, 23, 37)) for i in range(4)]
        for i, frame in enumerate(frames):
            frame.putpixel((i, i), (255, 128, 0))
        blob = zstd_clip(frames, 65535)
        metadata = zstd.get_frame_parameters(blob[10:])
        self.assertEqual(blob[1], 4)
        self.assertEqual(metadata.content_size, 245760)
        self.assertLessEqual(metadata.window_size, 131072)
        self.assertEqual(zstd.ZstdDecompressor().decompress(blob[10:]),
                         b"".join(frame.tobytes() for frame in frames))

    def test_image_modes_convert_to_rgb_without_mutating_input(self):
        for mode, color in (("RGBA", (255, 64, 32, 0)), ("L", 41), ("P", 3)):
            with self.subTest(mode=mode):
                frame = Image.new(mode, (160, 128), color)
                original = frame.tobytes()
                blob = zstd_clip([frame])
                self.assertEqual(zstd.ZstdDecompressor().decompress(blob[10:]),
                                 frame.convert("RGB").tobytes())
                self.assertEqual(frame.mode, mode)
                self.assertEqual(frame.tobytes(), original)

    def test_incompressible_pixels_cannot_exceed_live_upload_budget(self):
        raw = random.Random(17).randbytes(160*128*3)
        frame = Image.frombytes("RGB", (160, 128), raw)
        with self.assertRaisesRegex(ValueError, "16 KB budget"):
            zstd_clip([frame])


if __name__ == "__main__":
    unittest.main()
