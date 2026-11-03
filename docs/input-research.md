# Input investigation

The normal input adapter handles Previous, Next, Play and Pause through Windows media events. Version 0.6 adds `auto`, `winrt` and `legacy` backend selection plus an activation-burst guard. Up, Down, joystick-center and the original Back key are **not implemented**. This describes the current adapter, not a proven hardware limit.

## What is known

| Path | Evidence on the test device | Status |
|---|---|---|
| RFCOMM channel 1 | Fresh SDP identifies a standard `JL_SPP` service; image uploads work; a 180-second passive capture received zero bytes | Normal display transport; raw key reporting remains unverified |
| RFCOMM channel 10 | Fresh SDP identifies a second `JL_SPP` service with a vendor UUID; the confirmed music-mode capture received zero bytes over 564.9 seconds | No passive input signal observed in that capture; service purpose remains unverified |
| Windows media events | Physical Previous, Next, Play and Pause callbacks received in confirmed Bluetooth Music mode | Observed input path; tap-to-callback behavior is not yet reliable |
| Endpoint volume | Volume + / − produced two actual level changes and two unchanged notifications | Observable volume state, not a general key-event interface |
| HID | A fresh `1124` service query found no HID record; no target HID interface was bound in Windows | No usable HID interface in the tested device state |

The experimental media receiver also enables Stop, Record, Rewind, FastForward and ChannelUp/ChannelDown, and records playback/property changes. Enabling an event in Windows does not mean the MiniToo sends it. Synthetic JSON self-tests only validate formatting.

## Confirmed music-mode observations

The latest capture lasted 564.9 seconds, using a Python CommandManager receiver with `MediaPlaybackItem`, `StorageFile` and a muted MediaPlayer whose playback state stayed unchanged. Raw SMTC observation, CoreAudio endpoint-volume observation and receive-only RFCOMM channel 10 ran alongside it. Bluetooth Music mode was confirmed, and physical Left/Right provided positive controls. The operator clarified that **only the final Back press opened Menu**; earlier actions remained in music context. All receivers exited with code 0.

| Physical action | Observation |
|---|---|
| Left once / Right once | One Previous and one Next callback |
| Three requested Play/Pause taps | Two Pause callbacks; one-callback-per-tap behavior remains unverified |
| Up three times / Down three times | No observed callbacks |
| Original Back once, last | No observed callback; the device opened its native Menu |
| Volume + once / − once | Four notifications: two unchanged repeats and two level changes, approximately `0.504 → 0.567 → 0.504` |

No additional raw SMTC button, property or seek events were observed, and channel 10 received zero bytes. These results describe the tested mode and receivers; they do not establish a hardware impossibility or validate mappings for the missing keys. Joystick-center was not retested in this round.

An earlier confirmed music-mode capture lasted 208 seconds with a receiver that followed playback-state changes. It received Previous and Next; one reported physical tap produced Pause and Play callbacks 137 ms apart. The unchanged-playback experiment above is not a demonstrated fix for this behavior.

Software-generated controls were tested in separate marked intervals. In the follow-state setup, Next, Previous, Pause and Play each produced a callback. With playback held steady, a synthetic Pause produced one callback; synthetic Play was accepted but produced no Play callback while already playing. These are software-path checks, not physical button counts.

Earlier captures without a working positive control, or with a failed receiver startup, remain inconclusive. They are not evidence against the Python path or the unobserved keys.

Device context matters: Divoom's [control walkthrough](https://divoom.com/en-au/blogs/divoom-reviews/minitoo-deep-review-darren-yeo-offline-controls-sounds-games) distinguishes joystick menu navigation from track control during playback. The same physical movement is not a reliable media-input test in an unconfirmed mode.

## Receiver reliability

Following a ten-minute Dashboard session with 583 acknowledged frames, later C# media receiver launches intermittently failed with `0xC0000005`. A minimal .NET HelloWorld program also failed before output in no-hardware tests. The cause has not been identified.

The normal adapter reports startup/exit failures, waits up to 30 seconds for readiness per attempt, and permits two retries. Auto now selects Python WinRT when the required Windows/Python/dependency metadata is present, otherwise legacy C#. Runtime failure does not silently change that choice. The production WinRT receiver follows playback state; `--keep-playing` remains a diagnostic experiment.

The application delivers the first Play/Pause activation immediately and coalesces further activation callbacks within 250 ms of it. Deliberate fast taps may merge. This is a software mitigation; the new backend and guard still need physical Button Lab, Focus and Dashboard acceptance tests. A usable physical test must record ready and working positive controls in the same capture window.

For the Python/PyWinRT receiver, loading audio through `StorageFile` passed a ten-second ready/clean-shutdown baseline after the file-URL source had failed with `SOURCE_NOT_SUPPORTED` (`0x80070003`). The earlier failure was handled, with no native crash. Later music-mode captures established physical callbacks, with the unresolved paired/missing-tap behavior recorded above.

Protocol direction matters. The documented `0x17` game commands are **host-to-device** key presses; device game reports are not documented as raw key identities. `0x09` describes volume state, and `0xBD` wraps several unrelated operations, including display acknowledgments. None is mapped to a physical key without repeatable evidence. See the [game protocol mirror](https://github.com/ztomer/divoom_control/blob/main/docs/divoom_docs/game.md), [volume protocol](https://github.com/ztomer/divoom_control/blob/main/docs/divoom_docs/music_play.md) and [MiniToo findings](https://github.com/bugzmanov/divoom-minitoo/blob/main/FINDINGS.md).

## Experimental tools

Production display/input code stays in `driver.py` and `inputs.py`. Capture tooling lives in `pixeldeck.experimental`; the separate native `InputProbe.cs` is built only when requested. No raw packet is silently promoted to an application button.

Close the display session before starting a capture:

```powershell
python -m pixeldeck.experimental.input_probe --config private.json --channel 1 --seconds 180
python -m pixeldeck.experimental.input_probe --config private.json --channel 10 --seconds 180
```

The probe receives only. It sends no image, subscription, firmware or other device command. Channel 1 records recv chunks before decoding and complete packets before heartbeat filtering. Channel 10 uses raw capture so unknown framing does not end the session. `--raw-only` selects the same behavior on channel 1.

During capture, type `mark UP`, `mark DOWN`, `mark BACK` or another short action label. Markers record what the operator did; they are not recognized device events. Enter the exact command `stop` to finish early: the probe releases its connection, drains queued records and writes a summary with `reason="stopped"`. Stdin EOF alone does not stop the capture.

Logs default to the private runtime's `probes` directory, have a 4 MiB limit, and cannot be written into the source checkout. The packet mailbox is bounded and reports dropped records. The existing receive thread remains the only socket reader.

The native media probe is built separately:

```powershell
$runtime = Join-Path $env:USERPROFILE '.pixeldeck'
$output = Join-Path $runtime 'probes\native'
powershell -NoProfile -ExecutionPolicy Bypass -File src/pixeldeck/native/build.ps1 -BridgeName InputProbe -OutputDirectory $output
```

`InputProbe.exe ENDPOINT_HINT SILENCE_WAV SECONDS` opens a muted session on the selected endpoint and prints raw JSONL events. It does not change the default speaker or system volume. Its endpoint hint and capture output belong in the private runtime, alongside device configuration.

The optional Python media probe requires **Windows and Python 3.11+**. Install its dependencies from this checkout:

```powershell
python -m pip install -e ".[windows-input]"
python -m pixeldeck.experimental.media_probe --self-test-json
python -m pixeldeck.experimental.media_probe --config private.json --receiver commands --playback-item --keep-playing --seconds 600
```

`--self-test-json` checks formatting without hardware or WinRT; it does not test media callbacks. The live command opens a muted session on the configured endpoint and reports ready only after MediaOpened and actual Playing state. It emits JSONL to stdout; keep redirected output outside the repository. Type `mark LABEL` to mark an interval or `stop` to close the session.

Without explicit options, the probe uses the normal runtime configuration, bundled silent WAV, manual receiver and a ten-second duration. `--endpoint-hint` and `--wave` override the endpoint and audio file; `--ready-timeout` defaults to 30 seconds. Duration is bounded to 1–600 seconds and readiness timeout to 1–60 seconds. `--keep-playing` observes commands without changing the muted playback state; it is not a validated fix for paired or missing callbacks. Raw SMTC observations use `raw_button`, separate from command `button` events. Probe flags do not change the normal application's selected backend.

After the receiver above reports ready, verify software callbacks from another terminal:

```powershell
python -m pixeldeck.experimental.media_send
python -m pixeldeck.experimental.media_send --send --actions next previous
```

The first command only discovers the test session. Sending requires `--send`, one exact match for the media probe's shared title, and an unchanged session identity before every action. The sender accepts at most four actions per run within a 25-second deadline; `pause` and `play` are also available. `--self-test-json` performs only an offline formatting check.

Compare the sender's marked interval with separate `button` or `raw_button` records in the receiver output. `accepted=true` means the request was accepted; it is **not proof of a callback**. Keep this software-check interval separate from physical presses, and do not count synthetic requests as hardware positive controls.

## Test method

First verify the receiver's software callback path with the `media_send` procedure above; a JSON formatting self-test is insufficient. Do not request further physical presses until that check passes. Keep streamed images off and have the operator confirm the **Bluetooth Music playback screen**, rather than a clock face or native navigation menu. Record that context and wait for receiver readiness.

Then record a quiet baseline and test Left/Right as positive controls. Proceed to repeated Up/Down actions, Play/Pause, center and Back only after the control callbacks are captured. Keep Back last because it may change the device's mode. If the controls only navigate local pages, stop and re-establish music playback context. Repeat on each observed transport and compare the marked intervals; missing controls leave the round inconclusive.

A quiet capture only establishes that no signal was received under those conditions. Other firmware, modes, profiles or a required subscription remain separate questions. Unknown commands are not brute-forced. Raw captures, crash reports and device identifiers stay outside the repository; public evidence contains counts and conclusions only.
