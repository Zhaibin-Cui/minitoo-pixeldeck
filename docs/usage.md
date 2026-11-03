# Usage / from preview to pixels

Install from this repository with `python -m pip install -e .`. Nothing is fetched from a device during installation. The package is not claimed to be published on PyPI.

## Commands

| Command | Effect |
|---|---|
| `pixeldeck doctor` | Inspect versions and local configuration, no device access |
| `pixeldeck list` | List cartridge descriptions |
| `pixeldeck run [demo]` | Desktop-only preview |
| `pixeldeck run pulse --send` | Opt into live display output |
| `pixeldeck run buttons --send --media` | Opt into display plus muted media input session |
| `pixeldeck run signal --stdin` | Read newline-delimited notification events |
| `pixeldeck stop` | One local IPC stop request |
| `pixeldeck configure --address ADDRESS` | Write private local device settings |
| `pixeldeck build-input` | Compile the included Windows bridge into the runtime directory |
| `pixeldeck image file.png [--fit contain]` | Fit an image and save one preview; `--send` sends it |
| `pixeldeck export orbit --output orbit.gif` | Offline animation export |
| `pixeldeck clip file.gif --frames 2` | Encode a bounded clip and report sizes; `--send` is experimental |
| `pixeldeck brightness 50` | Print a brightness packet; `--send` is experimental |

`--duration 600` is the run default. `--duration 0` runs until closed. Image fit modes: contain, cover, stretch. Alpha is composited over black. `clip` accepts up to eight source frames but still enforces the 16 KB payload budget. Use separate streamed frames for larger scenes.

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
- Exhausted reconnect budget: close and restart the session after restoring the device connection.
- Sharing a bug report: summarize logs and remove local addresses, endpoint identifiers and absolute paths. The public validation record intentionally contains aggregates only.
