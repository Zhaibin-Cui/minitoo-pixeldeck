"""Codec choice must be bounded and separate from argument or encoder errors."""
import random
import sys
import unittest
from unittest.mock import patch

from PIL import Image

from pixeldeck.encoding import encode_frame
from pixeldeck.protocol import jpeg_clip, zstd_clip

try:
    import zstandard as zstd
except (ImportError, OSError):
    zstd = None


class EncodingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new('RGB', (160, 128), (20, 120, 80))

    def test_default_jpeg_does_not_load_optional_codec(self):
        with patch.dict(sys.modules, {'zstandard': None}):
            self.assertEqual(encode_frame(self.image), ('jpeg', jpeg_clip([self.image])))

    def test_missing_optional_package_falls_back_only_in_auto(self):
        with patch.dict(sys.modules, {'zstandard': None}):
            self.assertEqual(encode_frame(self.image, codec='auto'),
                             ('jpeg', jpeg_clip([self.image])))
            with self.assertRaisesRegex(RuntimeError, 'optional zstandard package'):
                encode_frame(self.image, codec='zstd')

    def test_optional_binary_load_failure_allows_auto_jpeg(self):
        def unavailable(*args, **kwargs):
            raise RuntimeError('Optional codec unavailable') from OSError('Native library unavailable')
        with patch('pixeldeck.encoding.zstd_clip', side_effect=unavailable):
            self.assertEqual(encode_frame(self.image, codec='auto')[0], 'jpeg')

    def test_invalid_arguments_never_enter_codec_fallback(self):
        with patch('pixeldeck.encoding.jpeg_clip') as jpeg, patch('pixeldeck.encoding.zstd_clip') as zstd:
            for kwargs in ({'codec':None}, {'codec':[]}, {'codec':'JPEG'}, {'quality':True},
                           {'quality':29}, {'quality':96}, {'quality':72.5}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    encode_frame(self.image, **kwargs)
            for image in (None, object(), Image.new('RGB', (128, 128))):
                with self.subTest(image=type(image).__name__), self.assertRaises(ValueError):
                    encode_frame(image, codec='auto')
            jpeg.assert_not_called()
            zstd.assert_not_called()

    def test_unexpected_encoder_errors_are_not_hidden(self):
        for error in (RuntimeError('Compressor failed'), ValueError('Unexpected frame parameters')):
            with self.subTest(error=type(error).__name__), patch('pixeldeck.encoding.zstd_clip', side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    encode_frame(self.image, codec='auto')
                self.assertIs(raised.exception, error)

    def test_missing_zstd_cannot_rescue_oversize_jpeg(self):
        with patch.dict(sys.modules, {'zstandard': None}), patch(
                'pixeldeck.encoding.jpeg_clip', side_effect=ValueError('Upload exceeds 16 KB budget')):
            with self.assertRaisesRegex(ValueError, 'No available frame encoding fits'):
                encode_frame(self.image, codec='auto')


@unittest.skipIf(zstd is None, 'Optional zstandard package is not installed')
class AvailableCodecTests(unittest.TestCase):
    def test_auto_chooses_smaller_lossless_payload_without_mutating_image(self):
        image = Image.new('RGBA', (160, 128), (10, 20, 30, 40))
        image.putpixel((0, 0), (255, 64, 16, 0))
        before = image.tobytes()
        codec, blob = encode_frame(image, codec='auto')
        self.assertEqual(codec, 'zstd')
        self.assertEqual(blob, zstd_clip([image]))
        self.assertLess(len(blob), len(jpeg_clip([image])))
        self.assertEqual(zstd.ZstdDecompressor().decompress(blob[10:]), image.convert('RGB').tobytes())
        self.assertEqual(image.tobytes(), before)

    def test_noise_uses_jpeg_when_lossless_payload_exceeds_budget(self):
        image = Image.frombytes('RGB', (160, 128), random.Random(17).randbytes(160*128*3))
        with self.assertRaisesRegex(ValueError, '16 KB budget'):
            zstd_clip([image])
        self.assertEqual(encode_frame(image, quality=30, codec='auto'),
                         ('jpeg', jpeg_clip([image], quality=30)))

    def test_palette_noise_can_fit_lossless_when_jpeg_exceeds_budget(self):
        random_source = random.Random(18)
        colors = (b'\x00\x00\x00', b'\xff\x00\x00', b'\x00\xff\x00', b'\x00\x00\xff')
        image = Image.frombytes('RGB', (160, 128),
                                b''.join(random_source.choice(colors) for _ in range(160*128)))
        with self.assertRaisesRegex(ValueError, '16 KB budget'):
            jpeg_clip([image], quality=95)
        self.assertEqual(encode_frame(image, quality=95, codec='auto'), ('zstd', zstd_clip([image])))

    def test_both_oversized_encodings_fail_before_transport(self):
        image = Image.frombytes('RGB', (160, 128), random.Random(19).randbytes(160*128*3))
        with self.assertRaisesRegex(ValueError, 'No available frame encoding fits'):
            encode_frame(image, quality=95, codec='auto')


if __name__ == '__main__':
    unittest.main()
