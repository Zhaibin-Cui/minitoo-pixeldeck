# Architecture

<p align="center"><img src="assets/forest-divider.png" alt="" width="1080"></p>

![Runtime architecture](assets/architecture.png)

## Ownership

One UI thread owns cartridge state and renders pixels. External input threads push events and wake that thread with a Tk event. A bounded priority queue gives buttons precedence over ordinary telemetry and status events. Rendering never calls the Bluetooth driver.

The host keeps the requested PREVIEW / LIVE mode visible and reports display and input health separately. Display acknowledgments never replace an input failure message. Connecting is a startup choice, not a cartridge activation.

Most cartridges leave previous/next navigation to `Deck`. A cartridge with `captures_navigation = True` receives previous, next and back itself. Dashboard uses this for its grid and detail pages; it returns `leave` to select Bit Buddy or `exit` to request host shutdown. The renderer never closes hardware directly.

Host measurements belong to a separate source worker. A cartridge declares its data sources and sampling interval; the host requests measurements only while that cartridge is visible and unfrozen. Source results become typed events. Reading a disk or a network counter is not performed inside `render()` or a button callback.

The worker holds at most one pending source request. Results carry the subscription generation, so an in-flight read from a page that has since changed or frozen is discarded instead of overwriting the new page's state.

`FramePump` owns the output worker and sink. A producer copies a frame into a one-item mailbox; the worker blocks until that mailbox changes. The sink does complete transactions. `MiniToo` has a separate reader that blocks on `recv()` even while the display is idle, consuming heartbeats and collecting transaction responses.

`encoding.encode_frame()` selects a payload before the transaction. `DeviceConfig.codec` defaults to `jpeg`; opt-in `zstd` uses lossless RGB, while `auto` compares available JPEG/Zstandard results within the 16,000-byte budget. It keeps no frame history and does not negotiate device support. Missing optional Zstandard support or an oversized result can select JPEG locally; transport failures never switch format. Native clip uploads remain JPEG. Reports include `codec` and `encode_ms` separately from the existing acknowledged transfer stages.

Input selection is `auto`, `winrt` or `legacy`. Auto uses the Python WinRT receiver when its Windows/Python/dependency checks pass, otherwise legacy C#. A runtime failure stays on the selected backend and is reported; it does not trigger silent fallback. Both receivers push JSON lines and the host blocks on stdout. The supervisor allows two retries and enforces a readiness deadline.

Next/Previous pass through directly. Play/Pause map to activation: the first callback is delivered immediately, then further activation callbacks within 250 ms of that accepted callback are coalesced. This bounds a burst without delaying the first action, but deliberately fast taps may merge. Exact one-action-per-press behavior remains unverified. Normal WinRT input follows playback state; unchanged playback is an experimental diagnostic option only.

## Scheduling

There is no fixed render loop for static screens. `next_delay(now)` returns a deadline or `None`. Animated cartridges request roughly three ticks per second. Source sampling has its own cadence: CPU and network once per second, power every five seconds, storage every ten seconds, and the wall clock once per second in their individual cartridges. Dashboard requests its combined sources once per second. Button Lab and Signal request no idle timer. Pausing Rain or Orbital cancels animation scheduling; freezing a source-backed monitor also stops its sampling requests.

Focus, Stopwatch and Pomodoro use monotonic elapsed time rather than rendered-frame counts. Leaving a running timer stops its visual work; elapsed time still counts, and the state is reconciled when visible again. A clock cartridge instead consumes wall-time events so a timezone change or system clock adjustment does not corrupt a duration timer. There is currently no hidden-page completion notification.

Build Beacon consumes producer events and keeps only the latest build state. A running build may animate a small indicator, but that animation never queries a build system. Finished and idle builds have no animation deadline. Signal Inbox remains a bounded push-only notice buffer.

Link Lab observes transfer and input events without requesting redraws. Activate explicitly freezes a snapshot for rendering. This prevents an ACK display from causing another upload and another ACK indefinitely; the snapshot cannot include acknowledgment of its own frame.

Audio Lab is a callback-fed renderer with no idle timer. Entering its page opens no audio device. The host requires `--audio` and explicit endpoint indices, then starts a five-second stream only on an activation request. Input levels and a bounded waveform become events; the cartridge performs no audio I/O. Speaker output is an independent test tone, never microphone loopback. Leaving the page cancels the stream.

The audio callback copies PCM into four preallocated 50 ms slots sized for the selected sample rate and channel count. It never waits for the metering worker; contention or a full buffer increments `dropped_frames`. The worker measures every retained window, including the final partial window after stream closure. Live reports are limited to twenty per second, with at most 32 signed peak-bin points for the waveform. Session RMS is sample-weighted across all measured PCM, and session peak is its largest absolute sample. `metered_frames` and `dropped_frames` count audio frames, not channel samples; PortAudio `xruns` report separate host disruptions whose lost-frame count is unknown.

Ready MIC/DUPLEX sessions with known RMS use a compact live view: an instantaneous RMS value rounded to integer dBFS and a large -60..0 dBFS bar. That bar has no peak hold. The cartridge continues collecting full statistics and history; SPEAKER retains the full waveform view and one-second peak hold. Missing microphone levels retain the full waiting view. After stopping, SESSION displays session RMS/peak and the last 20 reported window peaks. An explicit stop preserves the active job's terminal summary; a new request advances the generation so events from the superseded job are discarded.

Output packet pacing, one-shot transmission deadlines and bounded reconnect backoff are intentional waits. They do not poll for button events. The general packet-pacing default remains 10 ms. Separate audio and display workers still share host, radio and device resources.

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
| Link Lab latency history | 24 samples |
| Audio Lab waveform | 32 signed peak-bin points |
| Audio PCM buffer | 4 × 50 ms slots at the selected sample rate and channel count, int16 |
| Audio Lab peak history | 20 reported window peaks |
| Full-view live peak hold | 1 second of reported stream time; compact RMS bar is instantaneous |
| Audio level reports | At most 20 per second; independent of display upload rate |
| Pending audio job | 1 |
| Audio job duration | At most 10 seconds through the API; 5 seconds in Audio Lab |
| Live encoded payload | 16,000 bytes |
| Low-level Zstandard clip input | 4 RGB frames, 245,760 bytes |
| Zstandard decoder window | At most 128 KiB |
| Local logs | 1 MB current + 2 backups |

An event queue overflow is logged and that new event is rejected; this is not a lossless distributed broker. Producers should honor the boolean result of `Application.post`. The current CLI producer has no replay protocol. The latest-frame mailbox deliberately coalesces pictures, never application button state.

## Connection lifecycle

The device name is checked against the configured paired address before the built-in Windows backend connects. A file lock prevents concurrent Pixeldeck senders that share the same runtime directory. Other software or a differently configured runtime directory can still compete for the device.

Each upload waits for READY, sends 256-byte chunks, handles chunk requests and waits for completion. A transaction watchdog closes a blocked connection. `FramePump` retries a finite number of times, chooses the latest state after a failure and pauses output when the budget is exhausted. Idle disconnection wakes the pump through the reader callback.

Stopping closes the output socket, stops the media bridge through stdin, releases local control IPC, joins the workers and releases the instance lock. Dashboard's EXIT tile uses the same path as the desktop Exit control. The last displayed frame remains on the device; no gallery save or native-menu restoration is sent on exit.

## Porting

The default JPEG protocol path and cartridges depend only on Python and Pillow. The optional `display` extra supplies the lazily loaded Zstandard encoder. Optional psutil-backed sources supply network and battery observations; unsupported or missing observations stay unavailable. Clock and storage sources use the standard library. Storage covers at most eight local fixed volumes on Windows and the root filesystem on POSIX hosts. Source dependencies do not enter renderer modules.

The optional audio backend uses sounddevice/PortAudio outside the cartridge. It opens only the explicitly selected input/output directions and records no audio files. Streams request `latency='low'` with native block sizing (`blocksize=0`). Event fields `input_latency_ms` and `output_latency_ms` contain the opened streams' host-reported estimates, or `None` when unavailable; they are not measurements of acoustic-to-visible latency. Its local display snapshot is an image of the last rendered state, not a sound recording. Short hardware trials confirmed speaker, microphone and duplex operation on the tested setup, with noticeable device display delay during capture. Meter report cadence does not guarantee the same physical display rate; see the [audio evidence](validation.md#audio-lab--2026-11-03).

`audio.py` implements endpoint queries and stream I/O; `audio_worker.py` owns cancellable jobs and generation-tagged events. Inject a `backend_factory` into `AudioWorker` to replace the audio implementation. Its backend provides `run(mode, seconds, stop_event, callback)` and must honor cancellation; the cartridge remains independent of PortAudio.

On Windows, the audio caller initializes COM before querying or opening streams, then balances the references it acquired on that same thread after stream cleanup. This ownership is separate from the display codec and media-input backend.

Implement a socket-like object with `connect`, `settimeout`, `sendall`, `recv`, `shutdown`, and `close`, and inject its factory into `MiniToo`. A different display can instead implement `show(image)` returning a report containing `transfer_ms`, `close()`, and an optional `healthy` property, then use `FramePump` directly. GUI and WinRT code do not belong in either adapter.
