# Validation

## Offline checks

The current offline suite passed 178 tests in 20.819 seconds on Windows with Python 3.12.14, Pillow 12.3.0 and Tk 8.6. Hidden preview tests cover twenty activations, local stop, Dashboard selection/detail/back/exit, audio activation and cancellation, stale-event rejection, and release of the instance lock and workers. Window resources are released on the UI thread after the shutdown worker completes. The completed result is recorded in [offline-checks.json](offline-checks.json).

Protocol checks cover partial reads, complete checksums, JPEG payloads, missing READY, missing completion, chunk retransmission, brightness acknowledgments and 1,000 idle heartbeats. A blocked-sink test submits one hundred new frames while the first is held; only the first and final images are delivered. Static images are deduplicated.

All eighteen renderers produce 160 × 128 RGB frames within the configured upload budget. Gallery PNGs and GIFs are generated from the code and visually inspected. The tests also cover pause/resume timing, large timer gaps, bounded network history, missing metrics, malformed push events, coalesced source requests, source-worker failures, separate display/input status and redacted pairing checks.

Read-only measurements on the development host confirmed working network rates, a battery API response, two fixed-disk capacity readings and local/UTC time. Network and battery checks used psutil 7.2.2. This checks the host data sources; it does not verify the new cartridges on a physical MiniToo. Gallery data is synthetic.

The C# bridge's earlier format-only self-test emitted Next, Play and Pause without opening a player. Subsequent native startup failures are described below; a formatting check does not establish runtime reliability.

## 0.5.0 dashboard — live session snapshot

The Dashboard completed a ten-minute Windows session with an Intel Bluetooth adapter, the paired MiniToo, live frame output and the media-input bridge. It received 583 frame acknowledgments with a 469 ms median transfer time, two retransmission requests and no logged link or source errors. Eight media actions were received; application-receipt-to-ACK times ranged from 469 to 860 ms. The host closed cleanly at the session limit. [Hardware record](hardware-dashboard.json).

The operator attempted the original Back key, which is not mapped by the current media bridge; detail return uses Play/Pause. Up/down also have no implemented mapping. This is a limitation of the current access path, not an established limit of the device. The record distinguishes received callbacks from visual confirmation and does not measure physical-button-to-visible-pixel latency. Other adapters, Windows installations, device firmware and overnight runs remain untested. The eight utility renderers introduced in 0.4.0 have not each had a separate physical-device check.

## Subsequent input investigation

After that successful session, the C# media receiver intermittently failed during startup with `0xC0000005`. A minimal .NET HelloWorld program also failed before producing output in tests that used no Bluetooth hardware. The root cause remains unknown; no particular OS, runtime component or device command has been identified as the cause.

`MediaInput` reports failed child processes, allows at most two retries after the initial launch, and enforces a 30-second readiness deadline per attempt. Version 0.6 selects Python WinRT in auto mode when its prerequisites are available, otherwise legacy C#; runtime errors do not silently switch backends. The normal application now delivers the first activation immediately and coalesces further Play/Pause callbacks within 250 ms. This mitigation and the production WinRT path still need physical Button Lab, Focus and Dashboard acceptance tests. Deliberate fast taps can merge, and the legacy native crash is not claimed fixed.

A Python/PyWinRT MediaPlayer baseline subsequently reached ready and closed cleanly after switching from file-URL loading to `StorageFile`. The earlier media-source failure was handled without a native crash. Later captures below used confirmed Bluetooth Music context and working Left/Right controls.

| Capture | Observation | What it establishes |
|---|---|---|
| Earlier physical media round, all available SMTC actions enabled | Previous, Next and Pause were received; no callbacks for attempted Up, Down, center or original Back | Positive controls worked in this round; the extra keys were not observed through this media path |
| First RFCOMM channel 1 capture | Zero received bytes over 180 seconds | No passive signal was observed on that connection during the capture |
| Fresh SDP and passive connection checks | Advertised channels 1 and 10 each connected; six-second baselines received zero bytes | Both advertised channels accept a connection; a quiet baseline does not test key reporting |
| HID check | Fresh service query for `1124` returned no record; no target HID interface was bound in Windows | No usable HID path was found in the tested state |
| Python follow-state receiver, confirmed music mode, 208 seconds | Physical Previous/Next received; one reported tap produced Pause then Play 137 ms apart. Volume observer and raw channel 10 saw no changes/bytes; all exited with code 0 | Physical media input reached Python; tap-to-callback correspondence needs work |
| Python steady-playback receiver, confirmed music mode, 564.9 seconds | Previous 1, Next 1, Pause 2 from three requested taps. Up ×3, Down ×3 and final Back ×1 produced no observed callbacks. Only final Back opened Menu. No additional raw SMTC button/property/seek events or channel 10 bytes; all receivers exited with code 0 | This is a valid extra-key trial with working positive controls. The missing callbacks apply to this setup; steady playback is not a proven tap-handling fix |
| Endpoint volume during the 564.9-second capture | Volume + / − once each produced four notifications: two unchanged repeats and two changes, approximately `0.504 → 0.567 → 0.504` | Volume state is observable; duplicate snapshots must not be counted as additional presses |

Separate software-generated tests delivered Next, Previous, Pause and Play callbacks in the follow-state setup. With playback held steady, synthetic Pause produced one callback; an accepted Play request produced no Play callback while already playing. These checks are separate from physical counts. Earlier captures with failed startup or no positive controls remain inconclusive. See [input investigation](input-research.md) for the device-context reference, tools and test method.

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

### Pending 0.6.0 hardware acceptance

These checks await the operator's final session in confirmed Bluetooth Music mode. Offline checks do not establish that repeated or missing Play/Pause actions are fixed.

- [ ] **Button Lab:** perform 20 single Play/Pause taps, at least one second apart; verify exactly one accepted application action per tap.
- [ ] **Focus:** repeatedly start and pause; verify each tap changes state once and the displayed timer follows it.
- [ ] **Fast taps:** compare pairs inside and outside the 250 ms guard using receiver timestamps. Inside the window, one action is expected; outside it, two. Deliberately fast physical taps may merge.
- [ ] **Disconnect / reconnect:** check display recovery, input readiness, visible failure reporting and clean exit.
- [ ] **Dashboard:** select a metric, open detail, return with Play/Pause, test desktop Back/Esc, and activate EXIT. The original device Back key has no application mapping.
- [ ] **Link Lab:** inspect LINK, INPUT and PATTERN; confirm explicit snapshot refresh, numbered pattern changes and no ACK-triggered upload loop.
- [ ] **Audio Lab:** verify a five-second speaker tone on the chosen output, microphone levels on the chosen input, and independent duplex operation. Check stop, page-leave cancellation and error handling for a missing direction. Endpoint enumeration is not a playback/capture test.

Record observed counts and failures before changing any item to passed.

### Offline reproduction

```shell
python -m unittest discover -s tests -v
python examples/protocol_lab.py
python tools/build_gallery.py
```

Tests inject fake sockets and never connect Bluetooth. The Windows GUI integration uses a hidden window and local IPC. Run it in a normal desktop session; restricted Windows sandboxes can deny access to Python temporary directories. CI configuration is included, but no hosted CI run is claimed before publication.
