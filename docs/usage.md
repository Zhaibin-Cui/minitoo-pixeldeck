# Usage

Install from a source checkout with `python -m pip install -e .`.

For the full Windows setup, use Python 3.11+ in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[telemetry,windows-input,audio]"
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1 -Mode Preview -Demo dashboard
```

The launcher finds `.venv`. In the other examples, use `.\.venv\Scripts\python.exe` or `.\.venv\Scripts\pixeldeck.exe` if you have not activated that environment.

Install `python -m pip install -e ".[telemetry]"` for the optional psutil-backed network and battery sources. Preview, image transfer, clocks, timers, storage, and the existing CPU/memory providers do not require that extra. A missing source is displayed as unavailable; gallery fixtures never become fallback live measurements.

## Commands

| Command | Effect |
|---|---|
| `pixeldeck doctor` | Inspect versions and local configuration, no device access |
| `pixeldeck doctor --config private.json` | Inspect an alternate configuration with redacted static checks |
| `pixeldeck list` | List cartridge descriptions |
| `pixeldeck run [demo]` | Desktop-only preview |
| `pixeldeck run dashboard --send --media` | Multi-monitor grid with Bluetooth output and supported media input |
| `pixeldeck run link --send --media` | Frozen transfer/input snapshots and an explicit test pattern |
| `pixeldeck audio-devices [--match MiniToo]` | List audio endpoint indices without opening streams |
| `pixeldeck run audio` | Audio Lab UI with hardware audio disabled |
| `pixeldeck run pulse --send` | Opt into live display output |
| `pixeldeck run buttons --send --media` | Opt into display plus muted media input session |
| `pixeldeck run signal --stdin` | Read newline-delimited notification events |
| `pixeldeck run build --stdin` | Receive pushed build status and progress without running commands |
| `pixeldeck run network` | Preview aggregate interface receive/transmit rates |
| `pixeldeck run storage` | Preview free/total capacity of available volumes |
| `pixeldeck run power` | Preview battery and external-power information when reported by the OS |
| `pixeldeck stop` | One local IPC stop request |
| `pixeldeck configure --address ADDRESS` | Write private local device settings |
| `pixeldeck build-input [--backend auto\|winrt\|legacy]` | Check WinRT dependencies or compile the legacy C# bridge |
| `pixeldeck image file.png [--fit contain]` | Fit an image and save one preview; `--send` sends it |
| `pixeldeck export orbit --output orbit.gif` | Offline animation export |
| `pixeldeck clip file.gif --frames 2` | Encode a bounded clip and report sizes; `--send` is experimental |
| `pixeldeck brightness 50` | Print a brightness packet; `--send` is experimental |

`--duration 600` is the run default. `--duration 0` runs until closed. Image fit modes: contain, cover, stretch. Alpha is composited over black. `clip` accepts up to eight source frames but still enforces the 16 KB payload budget. Use separate streamed frames for larger scenes.

## Windows launcher

From the repository directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1 -Mode Preview -Demo dashboard
```

`Preview` uses desktop controls only. `Display` adds Bluetooth frame output. `Interactive` adds media input, checks WinRT dependencies or builds the selected legacy bridge if missing. Preview and Dashboard are the defaults. The launcher looks for `.venv`, then `py` or `python`; it does not install dependencies.

Optional arguments are `-Python FULL_PYTHON_EXE`, `-Config PRIVATE_DEVICE_JSON`, `-RuntimeDirectory PRIVATE_FOLDER`, `-InputBackend Auto|WinRT|Legacy` and `-Duration 600`. Audio Lab accepts `-Audio` with `-AudioInput ID` and/or `-AudioOutput ID`. A duration of `0` runs until closed. `-Check` runs redacted static diagnostics without connecting in any mode.

## Input backends

`pixeldeck run ... --send --media --input-backend auto` is the default selection. Auto uses Python WinRT on Windows/Python 3.11+ when the matching family-4 dependency metadata is installed; otherwise it selects legacy C#. Choose `--input-backend winrt` to require WinRT or `--input-backend legacy` for the explicit fallback. Runtime failure does not trigger a silent backend switch; the selected receiver gets at most two restarts.

`pixeldeck build-input --backend winrt` checks dependencies without opening a session. `--backend legacy` compiles the included C# source and requires Windows PowerShell, the .NET Framework compiler and Windows WinMetadata. The WinRT receiver follows playback state; the experimental `--keep-playing` mode is not used by normal demos.

## Controls and useful cartridges

The persistent **PREVIEW / LIVE** label identifies the requested output mode. `run dashboard` is desktop-only; add `--send` to transmit frames, and `--media` to receive supported device media actions. Activate never enables either connection. Display and input status are independent: a frame ACK cannot confirm input readiness.

Left / Right navigate; Enter / Space activate. Desktop **Esc / Back** returns from a nested page, and **Ctrl+Q / Exit** closes the application. Desktop **R** resets Stopwatch, Pomodoro and Breath Loop. These desktop shortcuts do not imply matching physical device keys.

Dashboard has six tiles: CPU, MEMORY, NETWORK, STORAGE, POWER and EXIT. Left / Right wraps through the grid; Activate opens a metric. Detail view uses Left / Right to cycle through the five metrics, and Activate or desktop Back / Esc to return to the grid. Desktop Back from the grid leaves Dashboard for Bit Buddy. Activating EXIT closes the host application and releases its connections, leaving the last frame on the device.

The input adapter maps callbacks to **previous, next and activate**. Both Play and Pause normalize to activate. The first activation is delivered immediately; further Play/Pause callbacks within 250 ms of it are coalesced. This adds no wait to the first action, but can merge deliberate fast taps. Previous/Next are not coalesced. The new handling still needs physical acceptance testing; see [input evidence and diagnostics](input-research.md).

Activate returns from Dashboard detail. Arbitrary joystick movement and the original hardware Back key have no application mapping.

| Cartridge | Useful for | Activate |
|---|---|---|
| `dashboard` | CPU, memory, network, storage and power overview | Open selected metric; detail returns to grid; EXIT closes |
| `link` | Transfer metrics, host-input counts and test patterns | Refresh snapshot, open detail and advance pattern |
| `audio` | Short speaker, microphone and duplex tests | Start a five-second test; while active, request stop |
| `clock` | Local or UTC wall time | Switch local / UTC |
| `stopwatch` | Timing a task or experiment | Start / pause; R resets |
| `pomodoro` | 25-minute focus / 5-minute break sessions | Start / pause; R resets |
| `breathe` | A 4–4–4–4 pacing animation | Start / pause; R resets |
| `network` | Aggregate RX/TX byte rates | Freeze / resume |
| `storage` | Free space across volumes | Select next volume |
| `power` | Reported battery and charging state | Change detail view |
| `build` | Progress from a local event producer | Change detail view |

Network sampling is passive: it reads interface counters, sends no probes, and does not measure Internet bandwidth or server reachability. Storage shows capacity, not disk throughput. A desktop without a battery shows an explicit empty state. Breath Loop provides a visual pace.

Link Lab uses Left / Right to select LINK, INPUT or PATTERN. Activate copies the latest observations into a frozen snapshot and opens detail. Desktop Back returns to its overview, then Bit Buddy. Observations are collected while hidden, but ACK/status updates never request a frame: the current upload's result appears only after a later snapshot. Input counts describe host events, including separately counted coalesced/unmapped observations, not physical presses.

## Audio Lab

Install `python -m pip install -e ".[audio]"` in the selected environment if the audio extra is absent. It uses sounddevice/PortAudio; Linux may also need the system PortAudio library.

```shell
pixeldeck audio-devices --match MiniToo
pixeldeck run audio --audio --audio-input INPUT_ID --audio-output OUTPUT_ID
```

Replace the IDs with the integer indices returned by `audio-devices`; run it without `--match` to list all endpoints. `--audio` requires at least one explicit index. The default `run audio` leaves hardware audio off, and an enabled session stays idle until Activate.

| Mode | Required endpoint | Effect |
|---|---|---|
| SPEAKER | `--audio-output OUTPUT_ID` | Quiet three-note motif repeated during the five-second test |
| MIC | `--audio-input INPUT_ID` | RMS/peak in dBFS and a bounded waveform with labeled x16 display gain |
| DUPLEX | Both | Independent tone output and microphone observation; no mic-to-speaker echo |

While idle, Left / Right selects the mode. Activate starts the test; Activate or desktop Back stops it. Back while idle leaves Audio Lab, and choosing another cartridge cancels an active test. A missing input/output direction produces a visible error instead of selecting a different device. Add `--send` for MiniToo display output; audio output itself does not require that flag.

Live meters show each reported 100 ms window in dBFS, with a one-second peak hold and a bar spanning -60 to 0 dBFS. Reports arrive at most ten times per second; Bluetooth display uploads can be slower. The WAVE X16 scope magnifies only its plotted peak-bin preview, not the microphone signal or system recording gain. Zero is shown as -INF, and missing data as --. Speaker mode measures generated output PCM; MIC and DUPLEX measure microphone PCM.

After completion or manual stop, SESSION retains the sample-weighted RMS and highest peak across all measured windows, including the final partial window. Its graph shows the last 20 reported window peaks. FRAMES counts metered audio frames; DROP counts frames the software meter could not retain. These counts are separate from PortAudio `xruns`, whose lost-frame count is unknown. A new test clears the previous result.

No audio file is recorded. On shutdown, the host's `latest.png` stores only its last display image, which may include the level graph. Short physical checks confirmed repeated speaker tones, visible microphone levels and concurrent duplex operation on the tested setup. The computer preview remained responsive, while the device screen was noticeably slow; pending pictures were replaced rather than replayed later.

In the instrumented duplex trial, experimental 2 ms packet pacing took 62–78 ms to hand image chunks to the socket, followed by 750–984 ms waiting for completion; total transfers were 922–1172 ms. The completion wait includes downstream buffering and device work. The general 10 ms pacing default remains unchanged. Audio and display workers share radio and device resources; the reported 26.375 ms native stream estimates do not measure acoustic-to-visible latency. See the [audio evidence and remaining lifecycle checks](validation.md#audio-lab--2026-11-03).

## Device write lab

```shell
python examples/device_lab.py
python examples/device_lab.py --operation still --send --config private.json
```

The default is a dry-run plan for all three public writes: a generated still, a two-frame clip and brightness. It does not read device configuration or connect. Select `--operation still`, `clip`, `brightness` or `all`; only `--send` performs writes. `--period` sets the clip period in milliseconds (default 250), and `--level` sets brightness from 0 to 100 (default 50).

Clip playback and brightness are experimental. The device's original brightness cannot be read, so the lab does not restore it automatically. An ACK alone does not confirm the physical effect. Avoid `--operation all --send` when you only intend to test a still frame.

`python examples/driver_lab.py` and `python examples/pipeline_lab.py` are finite offline simulations with asserted JSON results. They have no hardware mode. See the [capability map](capabilities.md) for their coverage.

## Pushed events

Use `--stdin` with a producer that writes and flushes one JSON object per line. The two accepted event types are:

```json
{"type":"notice","text":"TIME FOR TEA."}
{"type":"build","project":"PIXEL PROJECT","state":"running","progress":64,"step":"RUNNING CHECKS"}
```

Build states are `idle`, `running`, `passed`, and `failed`. Progress is a number from 0 to 100 or `null` when unknown. Project and step text have bounded display lengths. An event changes display state only: no command execution, log scanning, automatic build discovery, or service login occurs.

Try a one-shot build result with the [example producer](../examples/build_event.py):

```shell
python examples/build_event.py --state passed --progress 100 | pixeldeck run build --stdin
```

Signal and Build Beacon can receive their own events while another cartridge is visible. Select the relevant cartridge to inspect the latest state. The pipe is not a durable queue: there is no replay or cross-process delivery guarantee.

## Private runtime

The default directory is `~/.pixeldeck`. Override it with `PIXELDECK_HOME`. It contains device settings, an OS-held instance lock, local stop credentials, rebuilt native binaries, rolling logs and the latest preview image. These files do not belong in a public repository.

Device settings:

| Field | Default | Meaning |
|---|---|---|
| address | empty | Paired device address; required only for output |
| name | Divoom MiniToo-Audio | Expected paired device name |
| endpoint | MiniToo | Unique speaker name or endpoint-ID substring |
| chunk_delay_ms | 10 | Delay between outgoing 256-byte chunks |
| quality | 72 | JPEG quality |
| timeout | 5 | READY / final response timeout in seconds |
| retries | 3 | Reconnect attempts after the first failure |

An alternate settings file can be selected with `--config file.json` on hardware commands. No command changes the Windows default speaker or system volume. The explicit `--media` option creates muted playback on the selected MiniToo output. Concurrent phone music is a separate, unverified scenario.

## Bluetooth compatibility

Image transfer uses Windows **Classic Bluetooth RFCOMM**, not BLE. Device input uses the Windows Classic Audio / AVRCP media path and a selected speaker endpoint. Microsoft documents [RFCOMM support](https://learn.microsoft.com/en-us/windows/win32/bluetooth/about-bluetooth), the [Bluetooth driver stack](https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/bluetooth-driver-stack), and [Classic Audio profiles](https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/bluetooth-classic-audio).

For this toolkit, the practical requirement is working profiles and drivers; a Bluetooth 4.x / 5.x version label alone cannot establish compatibility. This is an inference from those separate profile requirements. Only the host/device combination described in [validation](validation.md) has hardware evidence. Windows support also varies by [OS version and profile](https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/general-bluetooth-support-in-windows).

`pixeldeck doctor` reports dependencies and redacted configuration checks. It does not connect to the device or certify RFCOMM, audio routing or physical input. Confirm those separately with a live display session and Button Lab.

## Troubleshooting

- No device animation: check that the mode is LIVE and the command includes `--send`. Windows pairing alone does not upload frames. Then check the display status, configured address, paired name and phone ownership of the control connection.
- Activate works only on the computer: `--send` enables display output; `--media` additionally enables the media-input session. Confirm Bluetooth Music mode, check the separate input status, then use `buttons` to measure the received actions. Input readiness alone does not prove one action per press.
- Unexpected Play/Pause counts: the 250 ms guard merges short bursts, including deliberately fast taps. Use Button Lab to verify ordinary presses; the new backend/guard still needs physical acceptance testing.
- Input startup errors: inspect the selected backend in `doctor` and the input status. WinRT needs the matching optional dependencies; legacy has known intermittent native startup faults. Follow the separate [input test procedure](input-research.md#test-method).
- Ambiguous audio endpoint: configure an exact endpoint-ID substring. Do not select an unrelated speaker just to get a match.
- Original device menu appears: the current native device mode may consume the joystick. Up/down/center are not mapped as app input.
- Missing legacy bridge: run `build-input --backend legacy`; check the compiler and WinMetadata prerequisites in its error output.
- Slower animation: fewer real frames may be delivered than requested. The app skips obsolete pictures while maintaining state. Lower-detail frames generally cost less bandwidth.
- Unavailable network or battery values: install the telemetry extra and check whether the operating system exposes the measurement. A missing battery is normal on many desktop computers.
- Audio unavailable: inspect `audio-devices`, select the direction needed by the chosen mode, and check the audio extra and OS audio permissions. An advertised output does not establish that the MiniToo exposes a usable microphone input.
- Exhausted reconnect budget: close and restart the session after restoring the device connection.
- Sharing a bug report: summarize logs and remove local addresses, endpoint identifiers and absolute paths. The public validation record intentionally contains aggregates only.
