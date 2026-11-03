# Protocol notebook

This is an application-level transport implementation, not a kernel driver. The working device path is Bluetooth Classic RFCOMM channel 1. The screen canvas is 160 × 128 RGB pixels.

## Envelope

```text
01 | length:u16le | opcode:u8 | body | checksum:u16le | 02
length   = len(body) + 3
checksum = sum(length bytes + opcode + body) & 0xffff
```

The decoder accepts fragmented and concatenated frames, validates complete frames and bounds its pending buffer. Delimiters inside a payload are data, not extra frames.

## Live display

```text
announce:  8B  00  total:u32le
chunk:     8B  01  total:u32le  index:u16le  data[up to 256 bytes]
READY:     01 07 00 04 8b 55 00 01 ec 00 02
complete:  01 09 00 04 bd 55 13 01 05 00 38 01 02
```

JPEG payload:

```text
23 | count:u8 | period_ms:u16be | rows:08 | columns:0A
   | 01 | jpeg_size:u32be | JPEG bytes
   | ... repeated frame entries
```

Optional lossless RGB payload:

```text
25 | count:u8 | period_ms:u16be | rows:08 | columns:0A
   | 00 00 | zstd_size:u16be | Zstandard bytes
```

The Zstandard stream contains consecutive 160 × 128 RGB888 frames in row order. `zstd_clip()` lazily imports the optional `display` dependency and uses compression level 9 by default, a maximum 128 KiB decoder window (`window_log=17`), an explicit content size, no dictionary and no checksum. It accepts at most four raw frames (245,760 bytes). The two zero bytes and length occupy the same four bytes as a big-endian uint32 while the payload stays within this toolkit's budget.

Both formats use the same `0x8B` announce/chunk/READY/completion exchange. Pixeldeck caps each complete blob at 16,000 bytes. One-frame streaming is the default. `MiniToo.show()` uses `DeviceConfig.codec`, whose default is `jpeg`. `zstd` explicitly selects the optional lossless format; `auto` compares available encodings that fit the budget and chooses the smaller one, preferring JPEG on ties. This is local selection, not device capability negotiation. Encoding availability or size can select JPEG before sending; a transport failure never switches codecs.

Native `show_clip()` and the `clip` CLI retain JPEG encoding. The low-level Zstandard clip encoder is available for experiments; its frame cap does not establish persistent storage or unlimited playback. Install its dependency with `python -m pip install -e ".[display]"`.

Responses use outer opcode `04`, echoed operation, marker `55`, and response data. `8B / 01 / index:u16le` requests a chunk again. The driver allows three retries per requested chunk. `F7` heartbeats are drained while idle and are not interpreted as joystick events.

## Brightness

`32 / level:u8` is an upstream-documented command. Pixeldeck validates 0..100 and waits for a matching response. It is simulated in tests but its physical effect has not been checked on this project's device. No brightness change is sent by demos.

## Evidence and corrections

The checksum of `08 00 8b 00 a1 2e 00 00` is `0162`; the included golden test computes the correct packet even where an upstream example shows a different checksum. Protocol notes can contain mistakes, so tests use arithmetic, framing invariants and observed replies together.

Sources: [public protocol notes](https://github.com/alvinunreal/divoom-minitoo-osx/blob/main/PROTOCOL.md), [MiniToo findings](https://github.com/bugzmanov/divoom-minitoo/blob/main/FINDINGS.md), and [lewilou22's RGB/Zstandard live format](https://github.com/lewilou22/divoom-minitoo-tools/blob/main/minitoo_protocol.py). See [validation](validation.md) for the boundary between simulation and hardware evidence.
