<p align="center"><img src="docs/assets/hero.gif" alt="MiniToo Pixeldeck: a pixel robot on an illustrated desktop device" width="1080"></p>

<p align="center"><strong>A tiny screen with a proper software stack.</strong><br>
Protocol tools · independent streams · seven original pixel cartridges<br>
Python 3.10+ · Windows hardware backend · MIT · v0.3.0</p>

MiniToo Pixeldeck is an independent, unofficial reverse-engineering toolkit for the **Divoom MiniToo**. Send images, build interactive pixel scenes, inspect the protocol, or use the display as a miniature system monitor. No firmware replacement. No cloud account. Importing the package never connects a device.

[Architecture](#architecture) · [Use it](#use-it) · [Cartridges](#insert-a-cartridge) · [Extend it](docs/extending.md) · [Protocol](docs/protocol.md) · [中文快速上手](docs/quickstart.zh-CN.md)

## Architecture

![The input, cartridge, frame mailbox and device pipeline](docs/assets/architecture.png)

```text
src/pixeldeck/
  protocol.py     Pure framing, incremental decode, image fitting, clip encoding
  driver.py       RFCOMM transactions, independent RX, deadlines and retransmission
  engine.py       One display writer, latest-frame mailbox, deduplication, reconnect
  inputs.py       WinRT callback stream and bounded JSONL notification input
  deck.py         Pure cartridge navigation; no GUI or Bluetooth dependency
  demos/          Stateful renderers with explicit time-event scheduling
  pixels.py       Original pixel lettering and drawing primitives
  telemetry.py    On-demand host CPU / memory measurements
  app.py          Desktop preview, input routing, lifecycle and local stop control
  native/         Rebuildable Windows media-event bridge
```

**Input is event-driven.** Windows media callbacks write directly into a pipe; the receiver blocks until data arrives. Notifications arrive as JSONL pushes. Neither path scans a file or periodically asks whether something changed.

**Animation uses deadlines.** A cartridge requests its next meaningful tick. Static screens request none. CPU sampling runs only while Pulse is visible and live. A paused scene cancels its timer.

**The screen keeps up with the present.** There is one frame in transit and at most one pending frame. A newer state replaces an obsolete pending frame. Identical pixels are not uploaded again. Input handling does not wait for image transmission; a frame already in transit must still finish or time out.

The hardware paths are different: image packets use **Classic Bluetooth RFCOMM channel 1**; supported physical inputs currently use a **Windows AVRCP media session**. Independent workers do not create independent radio bandwidth. The input session uses muted audio on the configured device endpoint and can receive system media keys.

| Layer | Extension seam | Hardware required? |
|---|---|---|
| Protocol | `packet`, `Decoder`, `jpeg_clip`, `upload` | No |
| Driver | `MiniToo(config, socket_factory=...)` | Only for a real socket |
| Output | `FramePump(sink_factory)`; sink implements `show` / `close` | No |
| Cartridge | `render`, `handle`, `next_delay` | No |
| Input | Push normalized events or newline-delimited notices | No |

See [design and resource bounds](docs/architecture.md), [API recipes](docs/extending.md), and the [capability-to-demo map](docs/capabilities.md).

## Use it

### 1. Preview first

From a source checkout:

```shell
python -m pip install -e .
pixeldeck doctor
pixeldeck list
pixeldeck run buddy
```

Or, with Pillow already installed, use `python run.py` instead of `pixeldeck`. The desktop preview needs Tkinter, normally included in python.org Windows installations. Protocol, encoding and headless GIF export do not need Tkinter.

**Left / Right** select a cartridge. **Enter / Space** activates it. The dropdown and buttons work too. A session defaults to ten minutes; close the window or run `pixeldeck stop`. `--duration 0` deliberately disables the time limit; long-term device stability has not been established.

### 2. Connect a MiniToo

Pair the device in Windows Bluetooth settings. Let the phone release its display-control connection. Replace the example address with your own paired device address:

```shell
pixeldeck configure --address AA:BB:CC:DD:EE:FF --endpoint MiniToo
pixeldeck run pulse --send
```

`configure` writes only to your local `~/.pixeldeck/device.json`. To isolate a session, set `PIXELDECK_HOME` to a private directory. The example configuration in this repository contains no device identity.

For the device's supported media buttons:

```shell
pixeldeck build-input
pixeldeck run buttons --send --media
```

The bridge is compiled locally from included C# source; it is not downloaded. It requires Windows PowerShell, the .NET Framework compiler and Windows WinMetadata. The configured endpoint must match exactly one speaker output. Left/right media actions select cartridges; Play and Pause both map to one activation. Joystick up/down/center and all other device keys are **not** exposed by this toolkit. Some native device modes consume buttons locally.

### 3. Send, export and push

```shell
pixeldeck image my-art.png --send
pixeldeck export orbit --output orbit.gif
pixeldeck run signal --stdin
```

Pipe a producer into Signal Inbox:

```shell
python examples/push_notice.py | pixeldeck run signal --stdin
```

Each incoming line is a small event: `{"type":"notice","text":"BUILD COMPLETE. TIME FOR TEA."}`. Only this schema is accepted; text is never executed. [Full CLI and configuration reference →](docs/usage.md)

## Insert a cartridge

These are **real program renders**, not concept art. Gallery GIFs are exported offline at 8 FPS. Device animation requests 3 FPS by default and is limited by actual Bluetooth throughput. Monitor values below are synthetic fixtures. The device illustration is original stylized artwork, not a product photo.

| Pulse | Bit Buddy | Neon Rain |
|:--:|:--:|:--:|
| ![CPU and memory waveform](docs/assets/pulse.gif) | ![Animated little CRT companion](docs/assets/buddy.gif) | ![Cyan and magenta code rain](docs/assets/rain.gif) |
| CPU waveform + memory bars.<br>Activate to freeze. | A little CRT with a soft spot.<br>Activate to send a heart. | Code becomes weather.<br>Activate to suspend the rain. |
| `pixeldeck run pulse` | `pixeldeck run buddy` | `pixeldeck run rain` |

| Orbital | Focus Foundry | Button Lab |
|:--:|:--:|:--:|
| ![Planet and satellite](docs/assets/orbit.gif) | ![Pixel hourglass timer](docs/assets/focus.gif) | ![Static single-press counter](docs/assets/buttons.gif) |
| A ringed planet, a tiny satellite.<br>Activate to suspend time. | One minute, one falling grain.<br>Activate to start / pause. | One press. One tick.<br>A deliberately static input diagnostic. |
| `pixeldeck run orbit` | `pixeldeck run focus` | `pixeldeck run buttons` |

### Signal Inbox — a message from the other side

<img src="docs/assets/signal.gif" alt="Event-driven notification inbox" width="320">

Build events, home automation, chat notices, creative experiments: bring your own producer. Signal keeps the last eight notices and updates only when an event arrives. Activate clears the inbox. It is a generic local interface with no service integration or embedded credentials.

## Build your own little world

A cartridge renders one `160 × 128` RGB image. It knows nothing about Bluetooth:

```python
from pixeldeck.demos import Demo
from pixeldeck.pixels import Canvas, CYAN

class Hello(Demo):
    key = "hello"
    def render(self, now):
        canvas = Canvas()
        canvas.text(80, 58, "HELLO, PIXELS", CYAN, center=True)
        return canvas.image
```

For an interactive version and registration, run [custom_cartridge.py](examples/custom_cartridge.py). For a headless encoding walkthrough, run [protocol_lab.py](examples/protocol_lab.py). Replace the output sink to stream into another device or your own test harness.

## Validation and boundaries

- **25 offline checks passed:** framing, fragmented input, ACK loss, retransmission, bounded heartbeats, queue replacement, idle reconnect, cartridge registration, pause/resume, notices, and hidden GUI shutdown.
- A preceding hardware session using the same media-command approach completed **401 acknowledged frames** over about ten minutes, with **296 ms median transfer time**, no logged transfer failures, and user-confirmed single-press counting and timer controls.
- The new 0.3.0 driver acknowledged **24 frames across all seven demo renderers**, with **390.5 ms median transfer time** and no retransmission requests. This short display-only check does not certify media input or long runs. ACK latency does not measure the instant pixels become visible. [Validation details →](docs/validation.md)
- Live uploads do not call gallery or firmware-write commands. Firmware-side memory/storage behavior, overnight endurance and simultaneous phone music remain unverified.
- Windows is the bundled hardware backend. Preview/rendering/protocol code is portable; Linux telemetry is implemented but has not been exercised on this Windows test host. macOS telemetry displays unavailable values.

## Development

```shell
python -m unittest discover -s tests -v
python tools/build_gallery.py
python tools/release.py
```

The release tool includes an explicit public file allowlist, checks relative Markdown links, scans for local paths/device identifiers/secrets, and writes a ZIP plus SHA-256 checksum. It does not publish anything. CI runs offline tests and builds a wheel on Windows and Linux.

## Credits

Protocol research: [bugzmanov/divoom-minitoo](https://github.com/bugzmanov/divoom-minitoo), [alvinunreal/divoom-minitoo-osx](https://github.com/alvinunreal/divoom-minitoo-osx), and [lewilou22/divoom-minitoo-tools](https://github.com/lewilou22/divoom-minitoo-tools). Visual inspiration: [RoboEyes](https://github.com/FluxGarage/RoboEyes), [PICO-8 particles](https://mboffin.itch.io/pico-8-particles), and the [MiniToo industrial design](https://divoom.com/products/minitoo/).

The protocol module is an independent implementation of documented fields and observed replies. Pixel lettering, sprites, animations and device illustrations are original procedural artwork. No third-party sprite pack or upstream source file is bundled. [Sources and attribution →](docs/sources.md)

MIT for this project's code and artwork. Divoom and MiniToo are their owners' marks. This is an unofficial community project.
