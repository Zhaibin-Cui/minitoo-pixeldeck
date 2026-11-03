# Usage

Install from a source checkout with `python -m pip install -e .`.

Install `python -m pip install -e ".[telemetry]"` for the optional psutil-backed network and battery sources. Preview, image transfer, clocks, timers, storage, and the existing CPU/memory providers do not require that extra. A missing source is displayed as unavailable; gallery fixtures never become fallback live measurements.

## Commands

| Command | Effect |
|---|---|
| `pixeldeck doctor` | Inspect versions and local configuration, no device access |
| `pixeldeck doctor --config private.json` | Inspect an alternate configuration with redacted static checks |
| `pixeldeck list` | List cartridge descriptions |
| `pixeldeck run [demo]` | Desktop-only preview |
| `pixeldeck run dashboard --send --media` | Multi-monitor grid with Bluetooth output and supported media input |
| `pixeldeck run pulse --send` | Opt into live display output |
| `pixeldeck run buttons --send --media` | Opt into display plus muted media input session |
| `pixeldeck run signal --stdin` | Read newline-delimited notification events |
| `pixeldeck run build --stdin` | Receive pushed build status and progress without running commands |
| `pixeldeck run network` | Preview aggregate interface receive/transmit rates |
| `pixeldeck run storage` | Preview free/total capacity of available volumes |
| `pixeldeck run power` | Preview battery and external-power information when reported by the OS |
| `pixeldeck stop` | One local IPC stop request |
| `pixeldeck configure --address ADDRESS` | Write private local device settings |
| `pixeldeck build-input` | Compile the included Windows bridge into the runtime directory |
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

`Preview` uses desktop controls only. `Display` adds Bluetooth frame output. `Interactive` adds the media-input bridge and compiles it if missing. Preview and Dashboard are the defaults. The launcher looks for `.venv`, then `py` or `python`; it does not install dependencies.

Optional arguments are `-Python FULL_PYTHON_EXE`, `-Config PRIVATE_DEVICE_JSON`, `-RuntimeDirectory PRIVATE_FOLDER` and `-Duration 600`. A duration of `0` runs until closed. `-Check` runs redacted static diagnostics without connecting in any mode.

## Controls and useful cartridges

The persistent **PREVIEW / LIVE** label identifies the requested output mode. `run dashboard` is desktop-only; add `--send` to transmit frames, and `--media` to receive supported device media actions. Activate never enables either connection. Display and input status are independent: a frame ACK cannot confirm input readiness.

Left / Right navigate; Enter / Space activate. Desktop **Esc / Back** returns from a nested page, and **Ctrl+Q / Exit** closes the application. Desktop **R** resets Stopwatch, Pomodoro and Breath Loop. These desktop shortcuts do not imply matching physical device keys.

Dashboard has six tiles: CPU, MEMORY, NETWORK, STORAGE, POWER and EXIT. Left / Right wraps through the grid; Activate opens a metric. Detail view uses Left / Right to cycle through the five metrics, and Activate or desktop Back / Esc to return to the grid. Desktop Back from the grid leaves Dashboard for Bit Buddy. Activating EXIT closes the host application and releases its connections, leaving the last frame on the device.

The media bridge exposes **previous, next and activate**. Both Play and Pause normalize to activate. It does not expose arbitrary joystick movement or a hardware Back action. The same activate action returns from Dashboard detail, so its normal select/open/return flow works with these three actions.

| Cartridge | Useful for | Activate |
|---|---|---|
| `dashboard` | CPU, memory, network, storage and power overview | Open selected metric; detail returns to grid; EXIT closes |
| `clock` | Local or UTC wall time | Switch local / UTC |
| `stopwatch` | Timing a task or experiment | Start / pause; R resets |
| `pomodoro` | 25-minute focus / 5-minute break sessions | Start / pause; R resets |
| `breathe` | A 4–4–4–4 pacing animation | Start / pause; R resets |
| `network` | Aggregate RX/TX byte rates | Freeze / resume |
| `storage` | Free space across volumes | Select next volume |
| `power` | Reported battery and charging state | Change detail view |
| `build` | Progress from a local event producer | Change detail view |

Network sampling is passive: it reads interface counters, sends no probes, and does not measure Internet bandwidth or server reachability. Storage shows capacity, not disk throughput. A desktop without a battery shows an explicit empty state. Breath Loop provides a visual pace.

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
- Activate works only on the computer: `--send` enables display output; `--media` additionally enables supported physical input. Check the separate input status, then use `buttons` to verify one action per press.
- Ambiguous audio endpoint: configure an exact endpoint-ID substring. Do not select an unrelated speaker just to get a match.
- Original device menu appears: the current native device mode may consume the joystick. Up/down/center are not mapped as app input.
- Missing native bridge: run `build-input`; check the compiler and WinMetadata prerequisites in its error output.
- Slower animation: fewer real frames may be delivered than requested. The app skips obsolete pictures while maintaining state. Lower-detail frames generally cost less bandwidth.
- Unavailable network or battery values: install the telemetry extra and check whether the operating system exposes the measurement. A missing battery is normal on many desktop computers.
- Exhausted reconnect budget: close and restart the session after restoring the device connection.
- Sharing a bug report: summarize logs and remove local addresses, endpoint identifiers and absolute paths. The public validation record intentionally contains aggregates only.
