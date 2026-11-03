# Usage

Install from a source checkout with `python -m pip install -e .`.

Install `python -m pip install -e ".[telemetry]"` for the optional psutil-backed network and battery sources. Preview, image transfer, clocks, timers, storage, and the existing CPU/memory providers do not require that extra. A missing source is displayed as unavailable; gallery fixtures never become fallback live measurements.

## Commands

| Command | Effect |
|---|---|
| `pixeldeck doctor` | Inspect versions and local configuration, no device access |
| `pixeldeck list` | List cartridge descriptions |
| `pixeldeck run [demo]` | Desktop-only preview |
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

## Controls and useful cartridges

Left / Right navigate; Enter / Space activate. Desktop **R** resets cartridges that expose a reset action, currently Stopwatch, Pomodoro and Breath Loop. It is not mapped to a physical device key.

| Cartridge | Useful for | Activate |
|---|---|---|
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

## Troubleshooting

- No display: verify the address, paired name and phone ownership of the control connection. The bundled backend requires Windows Classic Bluetooth, not BLE.
- Ambiguous audio endpoint: configure an exact endpoint-ID substring. Do not select an unrelated speaker just to get a match.
- Original device menu appears: the current native device mode may consume the joystick. Up/down/center are not mapped as app input.
- Missing native bridge: run `build-input`; check the compiler and WinMetadata prerequisites in its error output.
- Slower animation: fewer real frames may be delivered than requested. The app skips obsolete pictures while maintaining state. Lower-detail frames generally cost less bandwidth.
- Unavailable network or battery values: install the telemetry extra and check whether the operating system exposes the measurement. A missing battery is normal on many desktop computers.
- Exhausted reconnect budget: close and restart the session after restoring the device connection.
- Sharing a bug report: summarize logs and remove local addresses, endpoint identifiers and absolute paths. The public validation record intentionally contains aggregates only.
