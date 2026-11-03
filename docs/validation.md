# Validation

## Offline checks

The current offline suite passed 96 tests in 8.976 seconds on Windows with Python 3.12.14, Pillow 12.3.0 and Tk 8.6. Hidden preview tests cover twenty activations, local stop, Dashboard selection/detail/back/exit, and release of the instance lock and source worker. The completed result is recorded in [offline-checks.json](offline-checks.json).

Protocol checks cover partial reads, complete checksums, JPEG payloads, missing READY, missing completion, chunk retransmission, brightness acknowledgments and 1,000 idle heartbeats. A blocked-sink test submits one hundred new frames while the first is held; only the first and final images are delivered. Static images are deduplicated.

All sixteen renderers produce 160 × 128 RGB frames within the configured upload budget. Gallery PNGs and GIFs are generated from the code and visually inspected. The tests also cover pause/resume timing, large timer gaps, bounded network history, missing metrics, malformed push events, coalesced source requests, source-worker failures, separate display/input status and redacted pairing checks.

Read-only measurements on the development host confirmed working network rates, a battery API response, two fixed-disk capacity readings and local/UTC time. Network and battery checks used psutil 7.2.2. This checks the host data sources; it does not verify the new cartridges on a physical MiniToo. Gallery data is synthetic.

The C# bridge's earlier format-only self-test emitted Next, Play and Pause without opening a player. Subsequent native startup failures are described below; a formatting check does not establish runtime reliability.

## 0.5.0 dashboard — live session snapshot

The Dashboard completed a ten-minute Windows session with an Intel Bluetooth adapter, the paired MiniToo, live frame output and the media-input bridge. It received 583 frame acknowledgments with a 469 ms median transfer time, two retransmission requests and no logged link or source errors. Eight media actions were received; application-receipt-to-ACK times ranged from 469 to 860 ms. The host closed cleanly at the session limit. [Hardware record](hardware-dashboard.json).

The operator attempted the original Back key, which is not mapped by the current media bridge; detail return uses Play/Pause. Up/down also have no implemented mapping. This is a limitation of the current access path, not an established limit of the device. The record distinguishes received callbacks from visual confirmation and does not measure physical-button-to-visible-pixel latency. Other adapters, Windows installations, device firmware and overnight runs remain untested. The eight utility renderers introduced in 0.4.0 have not each had a separate physical-device check.

## Subsequent input investigation

After that successful session, the C# media receiver intermittently failed during startup with `0xC0000005`. A minimal .NET HelloWorld program also failed before producing output in tests that used no Bluetooth hardware. The root cause remains unknown; no particular OS, runtime component or device command has been identified as the cause.

`MediaInput` now reports failed child processes, allows at most two retries after the initial launch, and enforces a 30-second readiness deadline per attempt. These bound and expose failures; they do not fix the underlying crash. An alternative Python/PyWinRT receiver is under private evaluation and is not yet a validated public backend.

A Python/PyWinRT MediaPlayer baseline subsequently reached ready and closed cleanly after switching from file-URL loading to `StorageFile`. The earlier media-source failure was handled without a native crash. This prototype remains under investigation; initialization does not establish working input.

| Capture | Observation | What it establishes |
|---|---|---|
| First physical media round, all available SMTC actions enabled | Previous, Next and Pause were received; no callbacks for attempted Up, Down, center or original Back | Positive controls worked in this round; the extra keys were not observed through this media path |
| First RFCOMM channel 1 capture | Zero received bytes over 180 seconds | No passive signal was observed on that connection during the capture |
| Fresh SDP and passive connection checks | Advertised channels 1 and 10 each connected; six-second baselines received zero bytes | Both advertised channels accept a connection; a quiet baseline does not test key reporting |
| HID check | Fresh service query for `1124` returned no record; no target HID interface was bound in Windows | No usable HID path was found in the tested state |
| Second physical round / channel 10 | The first native receiver crashed; a retry reached ready, but no positive-control button callbacks were recorded in the capture window | Inconclusive; neither attempt supports a negative finding for Up, Down or Back |
| Private Python receivers, with volume notifications and channel 10 | No-audio SMTC (162 seconds) and manual SMTC with muted MediaPlayer (about 140 seconds) initialized cleanly. Each included confirmed Left/Right presses, zero media callbacks, volume changes or raw bytes, and exit code 0 for all processes | Neither setup delivered the positive controls. Up, Down and Back were not pressed in either round |

The operator reported completing the second round later, but that report alone cannot establish that the receiver covered the physical presses. Further input claims require a capture with working positive controls. See [input investigation](input-research.md) for the receive-only tools and test method.

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
