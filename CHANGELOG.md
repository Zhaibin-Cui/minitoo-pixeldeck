# Changelog

## 0.6.1

- Fix media input from source-checkout launchers: child processes inherit the package path and use UTF-8 output.
- Repeat the speaker motif throughout each bounded audio test.
- Display microphone levels in dBFS and label the waveform's x16 display gain; recorded sample values remain unchanged.
- Add license, Python, platform and offline-test badges to the README.

## 0.6.0

- Optional PyWinRT media input, with explicit backend selection and the legacy bridge retained.
- Immediate-first activation handling merges callbacks within 250 ms; physical tap reliability remains an acceptance test.
- Link Lab exposes transfer acknowledgments, input observations and numbered test patterns without an upload feedback loop.
- Audio Lab adds explicit, short speaker, microphone and duplex sessions through an optional portable audio backend.
- Runnable device, driver and pipeline labs cover read/write commands, resend handling, backpressure and recovery.
- Bounded clip/export inputs, final-preview saving on shutdown, clearer host structure and expanded pixel galleries.

## 0.5.0

- Interactive dashboard with five simultaneous host metrics, detail views, back navigation and an explicit exit tile.
- Persistent preview/live mode and separate display/input status; successful uploads no longer hide media-input errors.
- Contextual cartridge navigation, desktop Back/Escape and Exit controls.
- Windows launcher with preview, display and interactive modes, plus redacted pairing/backend diagnostics.
- Bluetooth compatibility notes distinguish Classic RFCOMM output from media-input support.
- Experimental receive-only captures for the two observed RFCOMM channels and a separate all-media-event probe.
- Media bridge startup deadlines, exit-code reporting and at most two retries after unexpected process exit.

## 0.4.0

- Eight practical cartridges: Net Scope, Volume Vault, Power Cell, Neon Clock, Stopwatch, Pomodoro, Breath Loop and Build Beacon.
- Visible-page data subscriptions, independent host sampling and explicit unavailable measurements.
- Optional network/battery telemetry, passive network byte rates and volume-capacity views.
- Generic pushed build status with progress and bounded text; no build execution or log watching.
- Desktop reset actions for timers, monotonic duration state and local/UTC wall-time display.
- Expanded source-generated galleries, task-oriented README and utility reference documentation.

## 0.3.0

- Independent package layout with protocol, transport, output, input and cartridge layers.
- Event-driven input, latest-frame backpressure, static-frame deduplication and bounded recovery.
- Seven original pixel cartridges, reusable pixel drawing primitives and offline GIF export.
- Windows media callback bridge, generic JSONL notifications and on-demand system metrics.
- Pure protocol encoding/decoding, small JPEG clips and experimental brightness requests.
- Illustrated architecture-first documentation, source examples, offline tests and public release tooling.

Hardware provenance and unverified features are recorded separately in `docs/validation.md`.
