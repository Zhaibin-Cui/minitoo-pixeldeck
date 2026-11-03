"""Wire-format implementation from documented fields and observed responses.

Only live display (0x8B) and an opt-in brightness command are exposed.
No gallery, firmware, reset, or persistent-face command is implemented.
"""
from dataclasses import dataclass
import io
from itertools import islice
import struct
from PIL import Image, ImageOps

SIZE = (160, 128)
LIVE = 0x8B
MAX_BLOB = 16000
ZSTD_MAX_FRAMES = 4
ZSTD_WINDOW_LOG = 17
READY = bytes.fromhex("01 07 00 04 8b 55 00 01 ec 00 02")
DONE = bytes.fromhex("01 09 00 04 bd 55 13 01 05 00 38 01 02")
HEARTBEAT_PREFIX = bytes.fromhex("04 f7 55")

def packet(opcode, body=b""):
    if not 0 <= opcode <= 255 or len(body) > 65532:
        raise ValueError("Packet fields exceed wire limits")
    content = struct.pack("<HB", len(body) + 3, opcode) + bytes(body)
    return b"\x01" + content + struct.pack("<H", sum(content) & 65535) + b"\x02"

def valid(raw):
    return (len(raw) >= 7 and raw[0] == 1 and raw[-1] == 2
            and int.from_bytes(raw[1:3], "little") == len(raw) - 4
            and (sum(raw[1:-3]) & 65535) == int.from_bytes(raw[-3:-1], "little"))

class Decoder:
    """Incremental decoder with bounded memory; corrupt complete frames fail closed."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        if len(self.buffer) > 65536:
            raise ValueError("Receive buffer limit exceeded")
        result = []
        while self.buffer:
            if self.buffer[0] != 1:
                del self.buffer[0]
                continue
            if len(self.buffer) < 3:
                break
            count = int.from_bytes(self.buffer[1:3], "little")
            if count < 3 or count + 4 > 65536:
                raise ValueError("Invalid packet length")
            if len(self.buffer) < count + 4:
                break
            raw = bytes(self.buffer[:count + 4])
            del self.buffer[:count + 4]
            if not valid(raw):
                raise ValueError("Invalid packet checksum or delimiter")
            result.append(raw)
        return result

def response(raw):
    if raw[3] != 4 or len(raw) < 9 or raw[5] != 0x55:
        return None, b""
    return raw[4], raw[6:-3]

def fit_image(image, mode="contain"):
    rgba = ImageOps.exif_transpose(image).convert("RGBA")
    flat = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    flat.alpha_composite(rgba)
    rgb = flat.convert("RGB")
    if mode == "cover":
        return ImageOps.fit(rgb, SIZE, Image.Resampling.NEAREST)
    if mode == "stretch":
        return rgb.resize(SIZE, Image.Resampling.NEAREST)
    if mode != "contain":
        raise ValueError("fit must be contain, cover, or stretch")
    scaled = ImageOps.contain(rgb, SIZE, Image.Resampling.NEAREST)
    out = Image.new("RGB", SIZE)
    out.paste(scaled, ((SIZE[0]-scaled.width)//2, (SIZE[1]-scaled.height)//2))
    return out

def jpeg_clip(images, period_ms=1000, quality=72):
    """Encode 0x23 JPEG frames. Multi-frame playback is experimental on this host."""
    images = list(islice(images, 256))
    if not 1 <= len(images) <= 255 or type(period_ms) is not int or not 1 <= period_ms <= 65535:
        raise ValueError("Clip needs 1..255 frames and a uint16 period")
    out = bytearray(struct.pack(">BBHBB", 0x23, len(images), period_ms, 8, 10))
    for image in images:
        if image.size != SIZE:
            raise ValueError("Frame must be 160 x 128")
        data = io.BytesIO()
        image.convert("RGB").save(data, format="JPEG", quality=quality, subsampling=0, optimize=True)
        encoded = data.getvalue()
        out.extend(b"\x01" + struct.pack(">I", len(encoded)) + encoded)
        if len(out) > MAX_BLOB:
            raise ValueError("Upload exceeds 16 KB budget; stream separate frames instead")
    return bytes(out)


def zstd_clip(images, period_ms=1000, level=9):
    """Encode lossless 0x25 RGB frames with a 128 KiB decompression window.

    At most four frames keep raw input bounded to 245760 bytes. Requires the
    optional zstandard package; no dependency is loaded by the JPEG path.
    """
    if type(period_ms) is not int or not 1 <= period_ms <= 65535:
        raise ValueError("period_ms must be an integer in 1..65535")
    if type(level) is not int or not 1 <= level <= 17:
        raise ValueError("level must be an integer in 1..17")
    images = list(islice(images, ZSTD_MAX_FRAMES + 1))
    if not 1 <= len(images) <= ZSTD_MAX_FRAMES:
        raise ValueError("Zstandard clips need 1..4 frames")
    if any(not isinstance(image, Image.Image) or image.size != SIZE for image in images):
        raise ValueError("Every frame must be a 160 x 128 Pillow image")
    try:
        import zstandard as zstd
    except (ImportError, OSError) as exc:
        raise RuntimeError("Zstandard display encoding requires the optional zstandard package") from exc

    raw = b"".join(image.convert("RGB").tobytes() for image in images)
    params = zstd.ZstdCompressionParameters.from_level(
        level, source_size=len(raw), window_log=ZSTD_WINDOW_LOG,
        write_content_size=True, write_checksum=False, write_dict_id=False,
        threads=0,
    )
    compressed = zstd.ZstdCompressor(compression_params=params).compress(raw)
    info = zstd.get_frame_parameters(compressed)
    if (compressed[:4] != b"\x28\xb5\x2f\xfd" or info.content_size != len(raw)
            or info.window_size > 1 << ZSTD_WINDOW_LOG or info.has_checksum or info.dict_id):
        raise ValueError("Unexpected Zstandard frame parameters")
    if len(compressed) + 10 > MAX_BLOB:
        raise ValueError("Upload exceeds 16 KB budget; stream separate frames instead")
    return struct.pack(">BBHBBI", 0x25, len(images), period_ms, 8, 10, len(compressed)) + compressed


@dataclass(frozen=True)
class Upload:
    announce: bytes
    chunks: tuple
    size: int

def upload(blob):
    if not 0 < len(blob) <= MAX_BLOB:
        raise ValueError("Payload exceeds live upload budget")
    total = struct.pack("<I", len(blob))
    chunks = tuple(packet(LIVE, b"\x01" + total + struct.pack("<H", index//256) + blob[index:index+256])
                   for index in range(0, len(blob), 256))
    return Upload(packet(LIVE, b"\x00" + total), chunks, len(blob))

def brightness_packet(level):
    if type(level) is not int or not 0 <= level <= 100:
        raise ValueError("Brightness must be an integer in 0..100")
    return packet(0x32, bytes([level]))
