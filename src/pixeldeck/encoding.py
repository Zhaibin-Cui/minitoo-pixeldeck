"""Choose one bounded live-frame encoding before any transport operation."""
from PIL import Image

from .protocol import SIZE, jpeg_clip, zstd_clip


def _budget_rejection(error):
    return str(error).startswith("Upload exceeds 16 KB budget")


def encode_frame(image, quality=72, codec="jpeg"):
    """Return (selected codec, payload); auto prefers JPEG when sizes tie."""
    if not isinstance(codec, str) or codec not in ("jpeg", "zstd", "auto"):
        raise ValueError("codec must be jpeg, zstd or auto")
    if type(quality) is not int or not 30 <= quality <= 95:
        raise ValueError("quality must be an integer in 30..95")
    if not isinstance(image, Image.Image) or image.size != SIZE:
        raise ValueError("Frame must be a 160 x 128 Pillow image")
    image = image.convert("RGB")
    if codec == "jpeg":
        return "jpeg", jpeg_clip([image], quality=quality)
    if codec == "zstd":
        return "zstd", zstd_clip([image])

    candidates = []
    jpeg_error = None
    try:
        candidates.append(("jpeg", jpeg_clip([image], quality=quality)))
    except ValueError as exc:
        if not _budget_rejection(exc):
            raise
        jpeg_error = exc
    try:
        candidates.append(("zstd", zstd_clip([image])))
    except RuntimeError as exc:
        if not isinstance(exc.__cause__, (ImportError, OSError)):
            raise
    except ValueError as exc:
        if not _budget_rejection(exc):
            raise
    if not candidates:
        raise ValueError("No available frame encoding fits the 16 KB live upload budget") from jpeg_error
    return min(candidates, key=lambda candidate: len(candidate[1]))
