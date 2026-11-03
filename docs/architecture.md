# Architecture

![Runtime architecture](assets/architecture.png)

## Ownership

One UI thread owns cartridge state and renders pixels. External input threads push events and wake that thread with a Tk event. A bounded priority queue gives buttons precedence over ordinary telemetry and status events. Rendering never calls the Bluetooth driver.

The host keeps the requested PREVIEW / LIVE mode visible and reports display and input health separately. Display acknowledgments never replace an input failure message. Connecting is a startup choice, not a cartridge activation.

Most cartridges leave previous/next navigation to `Deck`. A cartridge with `captures_navigation = True` receives previous, next and back itself. Dashboard uses this for its grid and detail pages; it returns `leave` to select Bit Buddy or `exit` to request host shutdown. The renderer never closes hardware directly.

Host measurements belong to a separate source worker. A cartridge declares its data sources and sampling interval; the host requests measurements only while that cartridge is visible and unfrozen. Source results become typed events. Reading a disk or a network counter is not performed inside `render()` or a button callback.

The worker holds at most one pending source request. Results carry the subscription generation, so an in-flight read from a page that has since changed or frozen is discarded instead of overwriting the new page's state.

`FramePump` owns the output worker and sink. A producer copies a frame into a one-item mailbox; the worker blocks until that mailbox changes. The sink does complete transactions. `MiniToo` has a separate reader that blocks on `recv()` even while the display is idle, consuming heartbeats and collecting transaction responses.

The Windows bridge receives Next/Previous/Play/Pause through WinRT callbacks and writes JSON lines immediately. Its reader blocks on stdout. Explicit media Play/Pause state changes preserve alternating remote commands; each callback produces one activation.

## Scheduling

There is no fixed render loop for static screens. `next_delay(now)` returns a deadline or `None`. Animated cartridges request roughly three ticks per second. Source sampling has its own cadence: CPU and network once per second, power every five seconds, storage every ten seconds, and the wall clock once per second in their individual cartridges. Dashboard requests its combined sources once per second. Button Lab and Signal request no idle timer. Pausing Rain or Orbital cancels animation scheduling; freezing a source-backed monitor also stops its sampling requests.

Focus, Stopwatch and Pomodoro use monotonic elapsed time rather than rendered-frame counts. Leaving a running timer stops its visual work; elapsed time still counts, and the state is reconciled when visible again. A clock cartridge instead consumes wall-time events so a timezone change or system clock adjustment does not corrupt a duration timer. There is currently no hidden-page completion notification.

Build Beacon consumes producer events and keeps only the latest build state. A running build may animate a small indicator, but that animation never queries a build system. Finished and idle builds have no animation deadline. Signal Inbox remains a bounded push-only notice buffer.

Output packet pacing, one-shot transmission deadlines and bounded reconnect backoff are intentional waits. They do not poll for button events. Multiple Bluetooth profiles still share hardware resources.

## Bounds

| Resource | Limit |
|---|---:|
| Pending image | 1, replaced by the newest state |
| In-flight image | 1 |
| Button queue | 32 |
| Other event queue | 128 |
| Pending source request | 1 |
| CPU history | 61 samples |
| Notifications | 8 × 80 characters |
| Build state | Latest bounded project / step / status event |
| JSONL line | 4 KB characters |
| Receive buffer | 64 KB |
| Active response queue | 64 packets |
| Diagnostic packet trace | 32 packets |
| Timing window | 256 completed sends |
| Live encoded payload | 16,000 bytes |
| Local logs | 1 MB current + 2 backups |

An event queue overflow is logged and that new event is rejected; this is not a lossless distributed broker. Producers should honor the boolean result of `Application.post`. The current CLI producer has no replay protocol. The latest-frame mailbox deliberately coalesces pictures, never application button state.

## Connection lifecycle

The device name is checked against the configured paired address before the built-in Windows backend connects. A file lock prevents concurrent Pixeldeck senders that share the same runtime directory. Other software or a differently configured runtime directory can still compete for the device.

Each upload waits for READY, sends 256-byte chunks, handles chunk requests and waits for completion. A transaction watchdog closes a blocked connection. `FramePump` retries a finite number of times, chooses the latest state after a failure and pauses output when the budget is exhausted. Idle disconnection wakes the pump through the reader callback.

Stopping closes the output socket, stops the media bridge through stdin, releases local control IPC, joins the workers and releases the instance lock. Dashboard's EXIT tile uses the same path as the desktop Exit control. The last displayed frame remains on the device; no gallery save or native-menu restoration is sent on exit.

## Porting

The protocol and cartridges depend only on Python and Pillow. Optional psutil-backed sources supply network and battery observations; unsupported or missing observations stay unavailable. Clock and storage sources use the standard library. Storage covers at most eight local fixed volumes on Windows and the root filesystem on POSIX hosts. Source dependencies do not enter renderer modules.

Implement a socket-like object with `connect`, `settimeout`, `sendall`, `recv`, `shutdown`, and `close`, and inject its factory into `MiniToo`. A different display can instead implement `show(image)` returning a report containing `transfer_ms`, `close()`, and an optional `healthy` property, then use `FramePump` directly. GUI and WinRT code do not belong in either adapter.
