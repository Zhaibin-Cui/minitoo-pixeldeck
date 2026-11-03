# Validation

## Offline checks

The current offline suite passed 247 tests in 19.833 seconds on Windows with Python 3.12.14, Pillow 12.3.0 and Tk 8.6. Hidden preview tests cover twenty activations, local stop, Dashboard selection/detail/back/exit, audio activation and cancellation, stale-event rejection, and release of the instance lock and workers. Window resources are released on the UI thread after the shutdown worker completes. The completed result is recorded in [offline-checks.json](offline-checks.json).

Protocol checks cover partial reads, complete checksums, JPEG payloads, missing READY, missing completion, chunk retransmission, brightness acknowledgments and 1,000 idle heartbeats. A blocked-sink test submits one hundred new frames while the first is held; only the first and final images are delivered. Static images are deduplicated.

All eighteen renderers produce 160 × 128 RGB frames within the configured upload budget. Gallery PNGs and GIFs are generated from the code and visually inspected. The tests also cover pause/resume timing, large timer gaps, bounded network history, missing metrics, malformed push events, coalesced source requests, source-worker failures, separate display/input status and redacted pairing checks.

Read-only measurements on the development host confirmed working network rates, a battery API response, two fixed-disk capacity readings and local/UTC time. Network and battery checks used psutil 7.2.2. This checks the host data sources; it does not verify the new cartridges on a physical MiniToo. Gallery data is synthetic.

The C# bridge's earlier format-only self-test emitted Next, Play and Pause without opening a player. Subsequent native startup failures are described below; a formatting check does not establish runtime reliability.

## 0.5.0 dashboard — live session snapshot

The Dashboard completed a ten-minute Windows session with an Intel Bluetooth adapter, the paired MiniToo, live frame output and the media-input bridge. It received 583 frame acknowledgments with a 469 ms median transfer time, two retransmission requests and no logged link or source errors. Eight media actions were received; application-receipt-to-ACK times ranged from 469 to 860 ms. The host closed cleanly at the session limit. [Hardware record](hardware-dashboard.json).

The operator attempted the original Back key, which is not mapped by the current media bridge; detail return uses Play/Pause. Up/down also have no implemented mapping. This is a limitation of the current access path, not an established limit of the device. The record distinguishes received callbacks from visual confirmation and does not measure physical-button-to-visible-pixel latency. Other adapters, Windows installations, device firmware and overnight runs remain untested. The eight utility renderers introduced in 0.4.0 have not each had a separate physical-device check.

## Subsequent input investigation

A source-checkout launcher exposed a separate startup defect: its parent adjusted `sys.path`, but the media child inherited no package path. The child could not import `pixeldeck`, and locale-encoded startup errors then failed UTF-8 decoding. Version 0.6.1 passes an explicit package path and UTF-8 environment. A regression launches the real format-only child from an unrelated directory with no inherited package path; a subsequent live production receiver reached media-opened-and-playing readiness and released its worker cleanly. No physical button was pressed in that startup check, so physical input acceptance remains separate.

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

## Lossless display — 2026-11-03

With a MiniToo WASAPI microphone capture active, a fixed full Audio Lab source image was transmitted twice per codec, reversing the candidate order in the second run. Both used 2 ms packet pacing, the same RFCOMM connection and normal completion acknowledgments. JPEG quality 72 produced 7,589 bytes and took 906/922 ms; lossless RGB/Zstandard level 9 produced 1,319 bytes and took 219/235 ms. No image retransmission requests occurred. The two capture runs metered 163,584 and 151,488 audio frames with zero reported software-meter drops or native xruns. The display data in this controlled comparison was synthetic; capture supplied the actual audio load.

The same Zstandard frame with a 50 ms playback period took 343/328 ms. There is no evidence in this small sample that shortening that field improves single-frame uploads, so the still-frame period remains 1,000 ms. JPEG and 10 ms packet pacing remain public defaults. The new `auto` option is a local payload choice, not a device-capability negotiation or a transport retry policy. [Machine-readable comparison](hardware-display-codecs.json).

During setup, capture startup reproducibly failed with PortAudio `-9999`. A worker without a COM apartment failed before receiving audio; a fresh worker explicitly initialized as MTA then captured 63,360 frames in a bounded two-second job with zero reported drops/xruns. The fix initializes the calling audio thread and balances only the COM references it owns after all stream cleanup. This test supports the initialization fix on this host; it does not classify every future audio-start failure as the same cause.

The operator confirmed normal pixels in the microphone-only test but still found the full meter view slow, particularly when speech began. Across five short sessions its median transfer time was 328–359 ms and median submitted-frame age 359–437 ms.

The compact live RMS view and 50 ms measurement windows were then used in three microphone sessions. Frames were 363–577 bytes; per-session median transfer times were 203, 218 and 234.5 ms, with median submitted-frame ages of 219, 266 and 289.5 ms. No image retransmissions or native xruns were reported. The first session's meter dropped 1,056 of 207,936 delivered audio frames; the other two reported no meter drops. The full SESSION results remain available after capture.

The compact view reduced measured transfer time; acceptable sound-to-screen synchronization has not been established. `frame_age_ms` starts when a rendered frame is submitted to the writer and includes queueing, encoding and transport; it is not an acoustic-to-visible latency measurement. All live test sessions were closed after the investigation.

## Audio Lab — 2026-11-03

On one Windows host with explicit MiniToo WASAPI endpoints, the operator confirmed clearly audible repeated speaker tones. Physical Right selected MIC, and Play/Pause started bounded microphone sessions. With continuous metering, speech produced visible levels; a 250 ms-window trial measured a session RMS of 0.00741 and peak of 0.09531 over 205,056 audio frames, with zero reported meter drops or native xruns.

The subsequent 100 ms-window version delivered 41 and 45 live level events in two sessions. The host reported an input stream latency of 26.375 ms; this is an API estimate, not a measured acoustic delay. The operator found the computer preview responsive, while the MiniToo screen remained noticeably delayed. Individual image transfers during capture took roughly 0.9–1.2 seconds at 10 ms packet pacing. Zero meter drops does not establish the absence of losses inside the Bluetooth or OS audio path.

The display pump kept the newest pending frame and replaced older pending frames. Its queue did not accumulate a replay history. Audio and display workers remain independent, but share the host and Bluetooth resources. A display-only comparison sent two frames at each pacing setting: 10 ms gave 328/454 ms, 2 ms gave 188/156 ms, and 0 ms gave 281/234 ms, with no retransmission requests. This small sample is not an adapter compatibility test; the public 10 ms default is unchanged.

The operator reported audible prompts and a responding computer meter in DUPLEX. The fresh instrumented duplex trial at 2 ms pacing measured a session RMS of 0.00615 and peak of 0.20218 over 207,360 audio frames, with zero reported meter drops or native xruns. Both streams reported 26.375 ms latency. Live transfers still took 922–1172 ms; handing chunks to the socket took 62–78 ms, followed by 750–984 ms waiting for completion. That wait includes downstream Bluetooth buffering and device work; it does not isolate firmware processing time. The operator still found the device screen noticeably slow. [Audio record](hardware-audio.json).

Speaker, microphone and concurrent operation worked in these short trials. They do not establish general music playback, speech recognition, overnight stability or exact one-action-per-press behavior. Ordinary launch settings remain unchanged after the pacing experiment.

## Storage and long runs

Only live-display commands are sent by ordinary demos. No gallery-save or firmware command exists in the public API. Host buffers and logs are bounded. The device's internal RAM and flash management have not been fully characterized; absence of a gallery command does not prove an indefinitely safe duty cycle.

## Reproduce

### Remaining hardware acceptance

These checks await the operator's final session in confirmed Bluetooth Music mode. Offline checks do not establish that repeated or missing Play/Pause actions are fixed.

- [ ] **Button Lab:** perform 20 single Play/Pause taps, at least one second apart; verify exactly one accepted application action per tap.
- [ ] **Focus:** repeatedly start and pause; verify each tap changes state once and the displayed timer follows it.
- [ ] **Fast taps:** compare pairs inside and outside the 250 ms guard using receiver timestamps. Inside the window, one action is expected; outside it, two. Deliberately fast physical taps may merge.
- [ ] **Disconnect / reconnect:** check display recovery, input readiness, visible failure reporting and clean exit.
- [ ] **Dashboard:** select a metric, open detail, return with Play/Pause, test desktop Back/Esc, and activate EXIT. The original device Back key has no application mapping.
- [ ] **Link Lab:** inspect LINK, INPUT and PATTERN; confirm explicit snapshot refresh, numbered pattern changes and no ACK-triggered upload loop.
- [x] **Audio Lab basic I/O:** audible repeated speaker tones, visible microphone levels and concurrent duplex operation were observed on the tested setup. Device display latency remains noticeable during capture.
- [ ] **Audio Lab lifecycle:** check physical manual stop, page-leave cancellation and error handling for a missing direction. Offline cancellation checks do not replace hardware lifecycle acceptance.

Record observed counts and failures before changing any item to passed.

### Offline reproduction

```shell
python -m unittest discover -s tests -v
python examples/protocol_lab.py
python tools/build_gallery.py
```

Tests inject fake sockets and never connect Bluetooth. The Windows GUI integration uses a hidden window and local IPC. Run it in a normal desktop session; restricted Windows sandboxes can deny access to Python temporary directories. CI configuration is included, but no hosted CI run is claimed before publication.
