"""Compression must preserve the decoded display frame and baseline JPEG format."""
import io
import unittest

from PIL import Image
from pixeldeck.demos.audio_lab import AudioLab
from pixeldeck.protocol import jpeg_clip


class JpegEncodingTests(unittest.TestCase):
    def test_entropy_optimization_preserves_pixels(self):
        picture = AudioLab().render(0)
        reference = io.BytesIO()
        picture.save(reference, format='JPEG', quality=72, subsampling=0)
        encoded = jpeg_clip([picture])[11:]
        with Image.open(io.BytesIO(encoded)) as actual, Image.open(io.BytesIO(reference.getvalue())) as expected:
            self.assertEqual(actual.tobytes(), expected.tobytes())
            self.assertFalse(actual.info.get('progressive', False))
        self.assertLess(len(encoded), len(reference.getvalue()))
