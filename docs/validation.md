# Validation / evidence before promises

## Offline checks

On the Windows development host: Python 3.12.14, Pillow 12.3.0, Tk 8.6. The suite contains 25 checks, including a hidden preview window that handles twenty activations, acknowledges a local stop request and releases the instance lock. The packaged result is recorded in `offline-checks.json`.

Protocol checks cover partial reads, complete checksums, JPEG payloads, missing READY, missing completion, chunk retransmission, brightness acknowledgments and 1,000 idle heartbeats. A blocked-sink test submits one hundred new frames while the first is held; only the first and final images are delivered. Static images are deduplicated.

All seven renderers produce 160 × 128 RGB frames within the configured upload budget. Gallery PNGs and GIFs are generated from the code and visually inspected. The C# bridge compiles and its format-only self-test emits Next, Play and Pause without opening a player.

## Preceding hardware session — 2026-11-03

The implementation that preceded this repository completed a ten-minute Windows session:

| Observation | Result |
|---|---:|
| Acknowledged live frames | 401 |
| Median single-frame transfer | 296 ms |
| Logged transfer failures | 0 |
| Pause callbacks | 11 |
| Play callbacks | 10 |
| Previous callbacks | 2 |
| Clean shutdown recorded | Yes |

The operator confirmed counting, navigation and focus controls behaved normally. The first isolated counter sample contained seventeen button events with 250–360 ms from application receipt to device acknowledgment. This is not a measured physical-button-to-visible-pixel benchmark and is not a guarantee for other firmware or radios.

## New 0.3.0 driver — separate display-only check

All seven renderers were sent through the new protocol and driver, ending with Bit Buddy. The device acknowledged 24 frames in 9.36 seconds: median transfer 390.5 ms, maximum 437 ms, zero retransmission requests. The connection was closed afterwards. [Machine-readable summary](hardware-smoke.json).

These are device acknowledgments, not visual confirmation of each new scene or validation of the new GUI media path. Physical single-press regression, phone music coexistence, sleep/resume, all reconnect scenarios, and overnight endurance remain separate acceptance items.

## Storage and long runs

Only live-display commands are sent by ordinary demos. No gallery-save or firmware command exists in the public API. Host buffers and logs are bounded. The device's internal RAM and flash management have not been fully characterized; absence of a gallery command does not prove an indefinitely safe duty cycle.

## Reproduce

```shell
python -m unittest discover -s tests -v
python examples/protocol_lab.py
python tools/build_gallery.py
```

Tests inject fake sockets and never connect Bluetooth. The Windows GUI integration uses a hidden window and local IPC. Run it in a normal desktop session; restricted Windows sandboxes can deny access to Python temporary directories. CI configuration is included, but no hosted CI run is claimed before publication.
