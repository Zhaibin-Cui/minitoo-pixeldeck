# Capability map / every layer has a playground

| Implemented capability | Demo / recipe | Verification |
|---|---|---|
| Still RGB image upload | `image`, Button Lab | Protocol simulation; predecessor live session |
| Repeated live frames | Pulse, Bit Buddy, Neon Rain, Orbital | Latest-frame pipeline tests; new runtime status in validation |
| Static-frame suppression | Button Lab, paused Rain | Automatic check |
| Input while frames transmit | Every interactive cartridge | Blocked-sink concurrency test; predecessor media-input session |
| Next / Previous / Play / Pause | Navigation + Button Lab + Focus | User-confirmed predecessor session; new binary compiles |
| Monotonic time events | Focus Foundry | Elapsed-time and pause/resume checks |
| CPU and memory | Pulse | Windows provider; Linux implementation not host-tested |
| Bounded JSONL push input | Signal Inbox, `push_notice.py` | Schema and queue-limit checks |
| Frame fitting / alpha | `image` | Automated alpha-compositing check |
| JPEG multi-frame encoding | `clip`, `protocol_lab.py` | Encoding and bounds checks; device playback experimental |
| Packet framing / fragmentation | `protocol_lab.py` | Golden bytes and corrupted packet tests |
| ACK, resend and timeout | Driver tests | Fragmented READY, resend and absent completion cases |
| Idle heartbeat draining | Driver tests | 1,000 simulated packets, bounded trace |
| Replaceable output sink | `FramePump` API | Slow-sink burst test |
| Brightness command | `brightness` | Simulated matching ACK; physical effect unverified |
| Stop and release | Window close / `stop` | Hidden GUI and local IPC integration check |
| Offline art export | `export`, `build_gallery.py` | Generated gallery inspected locally |

Not implemented: firmware flashing, factory reset, persistent photo storage, custom watchface installation, audio playback control as a public API, BLE, arbitrary joystick events, undocumented raw command execution, automatic device discovery, or cloud services. The scope is explicit so an extension can be assessed without guessing which hardware behavior is supported.
