# Capability map

| Implemented capability | Demo / recipe | Verification |
|---|---|---|
| Still RGB image upload | `image`, Button Lab | Protocol simulation; predecessor live session |
| Repeated live frames | Pulse, Bit Buddy, Neon Rain, Orbital | Latest-frame pipeline tests; new runtime status in validation |
| Static-frame suppression | Button Lab, paused Rain | Automatic check |
| Input while frames transmit | Every interactive cartridge | Blocked-sink concurrency test; predecessor media-input session |
| Next / Previous / Play / Pause | Navigation + Button Lab + Focus | User-confirmed predecessor session; new binary compiles |
| Contextual selection, detail and return | Dashboard | Grid/detail state tests; three normalized media actions |
| Explicit session exit | Dashboard EXIT, desktop Exit / Ctrl+Q | Host cleanup path; last device frame remains |
| Separate mode and connection status | Desktop host | Preview/live startup checks; independent display/input status |
| Monotonic time events | Focus Foundry | Elapsed-time and pause/resume checks |
| CPU and memory | Pulse | Windows provider; Linux implementation not host-tested |
| Passive network counters | Net Scope | Optional source, bounded history and freeze behavior checks |
| Volume capacity | Volume Vault | Host source plus pure-renderer fixture checks |
| Battery and external power | Power Cell | Optional source; unavailable/no-battery states are explicit |
| Local / UTC wall clock | Neon Clock | Typed wall-clock events; renderer does not read the system clock |
| Start / pause / reset timing | Stopwatch | Monotonic elapsed-time checks |
| Focus / break cycle | Pomodoro | Pause/resume and phase-boundary checks |
| Four-phase pacing | Breath Loop | Deterministic phase and paused-state checks |
| Visible-source subscriptions | Monitoring cartridges | Sampling runs outside rendering and ends when no longer needed |
| Bounded JSONL push input | Signal Inbox, Build Beacon | Notice/build schema checks; no execution path |
| Frame fitting / alpha | `image` | Automated alpha-compositing check |
| JPEG multi-frame encoding | `clip`, `protocol_lab.py` | Encoding and bounds checks; device playback experimental |
| Packet framing / fragmentation | `protocol_lab.py` | Golden bytes and corrupted packet tests |
| ACK, resend and timeout | Driver tests | Fragmented READY, resend and absent completion cases |
| Idle heartbeat draining | Driver tests | 1,000 simulated packets, bounded trace |
| Replaceable output sink | `FramePump` API | Slow-sink burst test |
| Brightness command | `brightness` | Simulated matching ACK; physical effect unverified |
| Stop and release | Window close / `stop` | Hidden GUI and local IPC integration check |
| Offline art export | `export`, `build_gallery.py` | Generated gallery inspected locally |

Dashboard and the eight 0.4.0 utility cartridges have separate validation from the earlier seven-cartridge hardware run. See [validation](validation.md) for test results, device evidence and platform coverage.

Not implemented: firmware flashing, factory reset, persistent photo storage, custom watchface installation, audio playback control as a public API, BLE, arbitrary joystick events, undocumented raw command execution, automatic device discovery, or cloud services.
