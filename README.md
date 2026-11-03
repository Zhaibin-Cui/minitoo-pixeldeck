<p align="center"><img src="docs/assets/hero.gif" alt="MiniToo Pixeldeck: a pixel robot on an illustrated desktop device" width="1080"></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-9affb3?style=flat-square&amp;labelColor=152440" alt="License: MIT"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python_core-3.10%2B-54edff?style=flat-square&amp;labelColor=152440" alt="Python core: 3.10+"></a>
  <a href="docs/usage.md#bluetooth-compatibility"><img src="https://img.shields.io/badge/live_backend-Windows-ff73bc?style=flat-square&amp;labelColor=152440" alt="Live backend: Windows"></a>
  <a href="docs/validation.md"><img src="https://img.shields.io/badge/0.6.2-205_offline_tests_passed-9affb3?style=flat-square&amp;labelColor=152440" alt="0.6.2: 205 offline tests passed"></a>
</p>

<p align="center"><strong>MiniToo protocol tools, live pixels and interactive demos.</strong><br>
Protocol tools · independent streams · eighteen original pixel cartridges<br>
Python 3.10+ core · Python 3.11+ WinRT input · MIT · v0.6.2</p>

MiniToo Pixeldeck is an independent, unofficial reverse-engineering toolkit for the **Divoom MiniToo**. Send images, build interactive pixel scenes, inspect the protocol, or use the display as a miniature system monitor. The software runs on your computer and leaves the device firmware unchanged. Importing the package never connects a device.

```text
PIXELDECK / DESK INSTRUMENTS
  CANVAS       160 x 128 RGB
  CARTRIDGES   18 demos
  INPUT        callbacks + local event streams
  OUTPUT       newest frame wins
  FIRST BOOT   preview / no device required
```

| 01 / ENGINE ROOM | 02 / POWER ON | 03 / CARTRIDGE SHELF |
|:--|:--|:--|
| [Architecture](#architecture) · [Protocol](docs/protocol.md) | [Use it](#use-it) · [中文上手](docs/quickstart.zh-CN.md) | [Live gallery](#insert-a-cartridge) · [Make your own](docs/extending.md) |

Watch network traffic, time a focus session, or follow a build from the desk. Each cartridge uses the same rendering and event APIs.

## Architecture

![Read, write and input interfaces with their verification status](docs/assets/io-map.png)

```text
src/pixeldeck/
  protocol.py     Pure framing, incremental decode, image fitting, clip encoding
  driver.py       RFCOMM transactions, independent RX, deadlines and retransmission
  engine.py       One display writer, latest-frame mailbox, deduplication, reconnect
  inputs.py       Input supervision, activation guard and bounded JSONL pushes
  input_backends.py  Dependency checks and backend selection
  windows_media.py  Python WinRT media-session entry point
  audio.py        Explicit-device audio I/O, levels and bounded PCM preview
  audio_worker.py  Cancellable audio jobs and generation-tagged events
  deck.py         Pure cartridge navigation; no GUI or Bluetooth dependency
  demos/          Stateful renderers with explicit time-event scheduling
  pixels.py       Original pixel lettering and drawing primitives
  telemetry.py    On-demand CPU / memory measurements
  sources.py      Visible-source subscriptions and isolated host measurement worker
  app.py          Desktop preview, input routing, lifecycle and local stop control
  native/         Rebuildable Windows media-event bridge
  experimental/   Opt-in raw capture and media-session diagnostics
```

**Input is event-driven.** Windows media callbacks write directly into a pipe; the receiver blocks until data arrives. Notifications arrive as JSONL pushes. Neither path scans a file or periodically asks whether something changed.

**Animation uses deadlines.** A cartridge requests its next meaningful tick. Static screens request none. Host measurements run in a separate worker only for the visible, unfrozen cartridge. A paused scene cancels its animation timer; data collection never lives inside a renderer.

**The screen keeps up with the present.** There is one frame in transit and at most one pending frame. A newer state replaces an obsolete pending frame. Identical pixels are not uploaded again. Input handling does not wait for image transmission; a frame already in transit must still finish or time out.

The hardware paths are different: image packets use **Classic Bluetooth RFCOMM channel 1**; supported physical inputs currently use a **Windows AVRCP media session**. Independent workers do not create independent radio bandwidth. The input session uses muted audio on the configured device endpoint and can receive system media keys.

| Layer | Extension seam | Hardware required? |
|---|---|---|
| Protocol | `packet`, `Decoder`, `jpeg_clip`, `upload` | No |
| Driver | `MiniToo(config, socket_factory=...)` | Only for a real socket |
| Output | `FramePump(sink_factory)`; sink implements `show` / `close` | No |
| Cartridge | `render`, `handle`, `next_delay` | No |
| Data source | Declare `sources` and `source_interval`; receive typed events | No |
| Input | Push normalized events, notices or build progress | No |
| Audio | `AudioWorker(callback, backend_factory=...)`; backend implements `run` | Only for real streams |

See the [runtime pipeline and resource bounds](docs/architecture.md), [API recipes](docs/extending.md), and [capability-to-demo map](docs/capabilities.md).

## Use it

### 1. Preview first

For the full Windows setup, use Python 3.11+ from a source checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[telemetry,windows-input,audio]"
.\.venv\Scripts\pixeldeck.exe doctor
.\.venv\Scripts\pixeldeck.exe run buddy
```

Examples below use `python` and `pixeldeck` for brevity. If the environment is not activated, use `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\pixeldeck.exe`; the Windows launcher finds `.venv` automatically. A minimal or non-Windows preview install needs Python 3.10+ and `python -m pip install -e .`.

With Pillow already installed, `python run.py` also works instead of `pixeldeck`. The desktop preview needs Tkinter, normally included in python.org Windows installations. Protocol, encoding and headless GIF export do not need Tkinter.

**Left / Right** select a cartridge, or a tile inside Dashboard. **Enter / Space** activates the current item. **Esc** goes back; **Ctrl+Q** exits. **R** resets Stopwatch, Pomodoro and Breath Loop. The dropdown and on-screen buttons work too. A session defaults to ten minutes; `--duration 0` disables the time limit.

The window always shows its **PREVIEW** or **LIVE** mode. Activate operates the selected demo; it does not enable Bluetooth output. Pairing the device in Windows also does not start frame transmission.

![Desktop preview controls](docs/assets/controls.png)

The full setup includes network and battery sources. Minimal installs can add them with:

```shell
python -m pip install -e ".[telemetry]"
pixeldeck run network
```

The clock and storage monitor use the standard library. Unavailable metrics are labeled unavailable; missing battery hardware is not replaced with a made-up percentage. Network figures are aggregate interface traffic, not an Internet speed test.

### 2. Connect a MiniToo

Pair the device in Windows Bluetooth settings. Let the phone release its display-control connection. Replace the example address with your own paired device address:

```shell
pixeldeck configure --address AA:BB:CC:DD:EE:FF --endpoint MiniToo
pixeldeck run dashboard --send
```

`configure` writes only to your local `~/.pixeldeck/device.json`. To isolate a session, set `PIXELDECK_HOME` to a private directory. The example configuration in this repository contains no device identity.

For the device's supported media buttons:

```shell
pixeldeck build-input
pixeldeck run dashboard --send --media
```

Input defaults to `--input-backend auto`: Windows/Python 3.11+ with the matching WinRT dependency family uses the Python receiver; otherwise it selects the legacy C# bridge. Use `--input-backend winrt` or `legacy` to select explicitly. `build-input` checks WinRT dependencies or compiles the legacy bridge. A runtime failure is reported and retried finitely; it does not silently switch backends.

The configured endpoint must match exactly one speaker output. Media callbacks map to previous, next and activate (both Play and Pause). The first activation is delivered immediately; further Play/Pause callbacks within 250 ms of it are coalesced. Deliberate fast taps can therefore merge. Joystick up/down/center and the original Back key have no application mapping.

The new backend and activation guard still need physical acceptance testing. Earlier sessions produced paired/missing Play/Pause callbacks and intermittent legacy startup failures. Before a device-input test, confirm the MiniToo's **Bluetooth Music playback screen** and verify Left/Right callbacks. Desktop controls remain available. [Input setup and evidence →](docs/input-research.md)

| Start mode | Display output | Input |
|---|---|---|
| `pixeldeck run dashboard` | Desktop preview only | Desktop controls |
| `pixeldeck run dashboard --send` | Desktop + Bluetooth display | Desktop controls |
| `pixeldeck run dashboard --send --media` | Desktop + Bluetooth display | Desktop + supported media actions |

Display and input have separate status lines. A successful frame upload does not confirm that the media input session is ready. Bluetooth compatibility depends on Classic RFCOMM and the Windows media-profile path, not the adapter's version label alone; see [compatibility and diagnostics](docs/usage.md#bluetooth-compatibility).

On Windows, [launch.ps1](launch.ps1) offers the same three modes. It defaults to Preview and does not install dependencies automatically:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1 -Mode Interactive -Demo dashboard
```

Use `-Mode Display` for output without device input, `-InputBackend WinRT` or `Legacy` to select input, or `-Check` for redacted diagnostics without connecting. [Launcher options →](docs/usage.md#windows-launcher)

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

Each incoming line is a small typed event. Use `{"type":"notice","text":"BUILD COMPLETE. TIME FOR TEA."}` for Signal, or feed Build Beacon an event such as:

```json
{"type":"build","project":"PIXEL PROJECT","state":"running","progress":64,"step":"RUNNING CHECKS"}
```

Run `pixeldeck run build --stdin` and let your own producer report state changes. Neither schema executes commands or integrates with a hosted service. [Full CLI and configuration reference →](docs/usage.md)

## Insert a cartridge

These are **real program renders**, not concept art. Gallery GIFs are exported offline at 8 FPS. Device animation requests 3 FPS by default and is limited by actual Bluetooth throughput. Metrics and audio waveforms below are synthetic fixtures. The device illustration is original stylized artwork, not a product photo.

| What belongs on your desk? | Start here |
|---|---|
| A small system instrument | `dashboard` · `pulse` · `network` · `storage` · `power` |
| Time with a physical presence | `clock` · `stopwatch` · `pomodoro` · `focus` · `breathe` |
| A glanceable event signal | `build` · `signal` |
| Animated pixel scenes | `buddy` · `rain` · `orbit` |
| Input and transport diagnostics | `buttons` · `link` |
| Speaker and microphone diagnostics | `audio` |

Every preview is reproducible: [cartridge registry](src/pixeldeck/demos/__init__.py) → [export code](src/pixeldeck/export.py) → [gallery builder](tools/build_gallery.py). [Full contact sheet →](docs/assets/gallery.png)

### Dashboard

<img src="docs/assets/dashboard.gif" alt="Dashboard grid, metric selection and enlarged CPU detail" width="480">

CPU, memory, network, storage and power share one overview, with a sixth **EXIT** tile. Left / Right moves the selection; Activate opens a metric. In detail view, Left / Right changes metrics and Activate or desktop Back / Esc returns to the grid. Received MiniToo Play/Pause callbacks map to Activate; the physical-input limitations above still apply. Desktop Back / Esc from the grid returns to Bit Buddy.

```shell
pixeldeck run dashboard --send --media
```

The EXIT tile, desktop Exit button or Ctrl+Q closes Pixeldeck and releases its connections. The device keeps the last displayed frame; exit does not restore its native menu. The demo also works in preview mode without either flag.

### Link Lab

<img src="docs/assets/link.gif" alt="Link Lab ACK, input and numbered test-pattern panels" width="480">

Inspect the last transfer, input counters and a numbered test pattern. Left / Right selects LINK, INPUT or PATTERN. Activate takes a snapshot, opens detail and advances the pattern; desktop Back returns to the overview, then Bit Buddy.

```shell
pixeldeck run link --send --media
```

ACKs and input observations accumulate without triggering a redraw or another upload. Activate refreshes the display, so the current frame's ACK appears in a later snapshot. These are host events and transfer timings, not raw key identities or visible-pixel latency.

### Audio Lab

<img src="docs/assets/audio.gif" alt="Synthetic Audio Lab speaker, microphone and duplex waveforms" width="480">

SPEAKER plays a test tone, MIC displays input levels and a waveform, and DUPLEX does both independently. There is no microphone-to-speaker loopback or audio-file recording. Audio stays off until explicitly enabled and activated.

```shell
pixeldeck audio-devices --match MiniToo
pixeldeck run audio --audio --audio-input INPUT_ID --audio-output OUTPUT_ID
```

Replace the IDs with endpoints reported by `audio-devices`. Left / Right chooses a mode while idle; Activate starts its five-second test. Activate or desktop Back stops an active test, and leaving the page stops audio. The final SESSION view retains measured RMS, peak and frame coverage. Add `--send` to display it on the MiniToo. Speaker, microphone and duplex operation have been checked on one Windows setup; device display updates slow down during capture. [Audio setup →](docs/usage.md#audio-lab) · [Observed results →](docs/validation.md#audio-lab--2026-11-03)

### System monitors and desk tools

Individual cartridges for monitoring, timing and pushed events. [View the utility collection together →](docs/assets/useful-demos.png)

| Net Scope | Volume Vault | Power Cell |
|:--:|:--:|:--:|
| ![Live network receive and transmit rates](docs/assets/network.gif) | ![Storage free-space meters](docs/assets/storage.gif) | ![Battery and external power display](docs/assets/power.gif) |
| Aggregate receive and transmit rates.<br>Activate freezes RX / TX. | Free space at a glance.<br>Activate selects another volume. | Battery level and power details.<br>Shows NO BATTERY when none is present. |
| `pixeldeck run network` | `pixeldeck run storage` | `pixeldeck run power` |

| Neon Clock | Stopwatch | Pomodoro |
|:--:|:--:|:--:|
| ![Local and UTC pixel clock](docs/assets/clock.gif) | ![Interactive elapsed-time stopwatch](docs/assets/stopwatch.gif) | ![Focus and break interval timer](docs/assets/pomodoro.gif) |
| Local time and UTC.<br>Activate switches the time basis. | Elapsed time for tasks and experiments.<br>Activate starts / pauses; desktop R resets. | 25 minutes of focus, 5 minutes of rest.<br>Activate starts / pauses; desktop R resets. |
| `pixeldeck run clock` | `pixeldeck run stopwatch` | `pixeldeck run pomodoro` |

| Breath Loop | Build Beacon |
|:--:|:--:|
| ![Four-phase animated pacing loop](docs/assets/breathe.gif) | ![Pushed build progress and result](docs/assets/build.gif) |
| A 4–4–4–4 pacing loop.<br>Activate starts / pauses; desktop R resets. | Build progress and results.<br>JSONL pushes progress; activate changes the view. |
| `pixeldeck run breathe` | `pixeldeck run build --stdin` |

<details>
<summary><strong>Three ways to use the desk tools</strong></summary>

**During a download:** open Net Scope, freeze a sample with Activate, then switch to Volume Vault to check capacity. Neither cartridge uploads host measurements or actively probes the network.

**During focused work:** start Pomodoro, switch away while it keeps elapsed time, and return to the current phase. Use Stopwatch for an open-ended task. Desktop R starts those timers over.

**During a build:** let your build script push `running`, progress and a final `passed` or `failed` event into Build Beacon. The screen reports what the producer sends; it never launches or cancels the build.

</details>

### Animated cartridges and input diagnostics

| Pulse | Bit Buddy | Neon Rain |
|:--:|:--:|:--:|
| ![CPU and memory waveform](docs/assets/pulse.gif) | ![Animated CRT companion](docs/assets/buddy.gif) | ![Cyan and magenta code rain](docs/assets/rain.gif) |
| CPU waveform + memory bars.<br>Activate to freeze. | An animated CRT companion.<br>Activate to send a heart. | Falling cyan and magenta characters.<br>Activate to suspend the rain. |
| `pixeldeck run pulse` | `pixeldeck run buddy` | `pixeldeck run rain` |

| Orbital | Focus Foundry | Button Lab |
|:--:|:--:|:--:|
| ![Planet and satellite](docs/assets/orbit.gif) | ![Pixel hourglass timer](docs/assets/focus.gif) | ![Static single-press counter](docs/assets/buttons.gif) |
| A ringed planet and orbiting satellite.<br>Activate to pause. | A one-minute pixel hourglass.<br>Activate to start / pause. | A counter for each activation.<br>A static input diagnostic. |
| `pixeldeck run orbit` | `pixeldeck run focus` | `pixeldeck run buttons` |

### Signal Inbox

<img src="docs/assets/signal.gif" alt="Event-driven notification inbox" width="320">

Build events, home automation, chat notices, creative experiments: bring your own producer. Signal keeps the last eight notices and updates only when an event arrives. Activate clears the inbox. It is a generic local interface with no service integration or embedded credentials.

## Write a cartridge

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

### Driver and pipeline labs

These examples finish on their own and work without a device:

```shell
python examples/device_lab.py
python examples/driver_lab.py
python examples/pipeline_lab.py
```

| Lab | What it demonstrates |
|---|---|
| [Device writes](examples/device_lab.py) | A dry-run plan for a generated still, a two-frame clip and brightness; no configuration or device access by default |
| [Driver](examples/driver_lab.py) | The real driver with a simulated socket: ACKs, resend, timeouts, heartbeat draining and raw receive observation |
| [Pipeline](examples/pipeline_lab.py) | The real frame pump with simulated sinks: newest-frame replacement, deduplication, idle reconnect and cleanup |

`device_lab.py --operation still --send` explicitly uploads its generated test frame. Clip playback and brightness remain experimental; [usage](docs/usage.md#device-write-lab) covers those options and their limits.

## Validation and boundaries

| Area | Current evidence |
|---|---|
| Live display | Dashboard completed ten minutes with **583 acknowledged frames**, **469 ms median transfer**, two retransmission requests and clean shutdown. ACK time is not visible-pixel latency. |
| Physical input | Previous/Next and Play/Pause callbacks were observed in Bluetooth Music mode. The new WinRT backend and 250 ms activation guard await physical acceptance testing. Up/Down/Back have no verified mapping. |
| Offline behavior | Tests cover framing, retransmission, deadlines, bounded queues, reconnect, state machines, sources, pushed events and GUI cleanup. Current counts are in [validation](docs/validation.md). |
| Portability | Rendering and protocol code are portable; the bundled Bluetooth backend is Windows. Host metrics depend on platform APIs and optional psutil support. |
| Audio | Explicit endpoint selection and short speaker/microphone/duplex tests are implemented. Physical playback/capture acceptance is pending. |
| Long runs | Live uploads use no gallery-save or firmware command. Device RAM/flash behavior, overnight endurance and simultaneous phone music remain unverified. |

Detailed sessions and earlier release checks are in [validation](docs/validation.md). Raw-input findings and the physical test procedure are in [input investigation](docs/input-research.md).

## Development

Protocol and transport recipes are listed in the [capability map](docs/capabilities.md). Experimental receivers and synthetic media commands live in `pixeldeck.experimental`; the [input guide](docs/input-research.md) covers their Windows/Python 3.11+ dependencies and verification steps. Normal demos use the selected WinRT or legacy backend.

```shell
python -m unittest discover -s tests -v
python tools/build_gallery.py
python tools/release.py
```

The release tool uses a public file allowlist, checks relative Markdown links, scans for local paths/device identifiers/secrets, and writes a ZIP plus SHA-256 checksum. It does not publish anything. The included CI workflow is configured for offline tests and wheel builds on Windows and Linux.

<details>
<summary><strong>Rebuild the visual documentation</strong></summary>

`tools/build_gallery.py` generates the hero, control strip, I/O map, runtime diagram, contact sheets and every cartridge PNG/GIF from source. The monitor fixtures are synthetic and carry no host identity. No image-generation service, paid font or downloaded sprite pack is needed to reproduce the gallery.

</details>

## Credits

Protocol research: [bugzmanov/divoom-minitoo](https://github.com/bugzmanov/divoom-minitoo), [alvinunreal/divoom-minitoo-osx](https://github.com/alvinunreal/divoom-minitoo-osx), and [lewilou22/divoom-minitoo-tools](https://github.com/lewilou22/divoom-minitoo-tools). Visual inspiration: [RoboEyes](https://github.com/FluxGarage/RoboEyes), [PICO-8 particles](https://mboffin.itch.io/pico-8-particles), and the [MiniToo industrial design](https://divoom.com/products/minitoo/).

The protocol module is an independent implementation of documented fields and observed replies. Pixel lettering, sprites, animations and device illustrations are original procedural artwork. No third-party sprite pack or upstream source file is bundled. [Sources and attribution →](docs/sources.md)

README layout references: [Gum](https://github.com/charmbracelet/gum), [VHS](https://github.com/charmbracelet/vhs), and [Starship](https://github.com/starship/starship). [Design notes →](docs/readme-design.md)

MIT for this project's code and artwork. Divoom and MiniToo are their owners' marks. This is an unofficial community project.
