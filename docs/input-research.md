# Input investigation

The normal input adapter handles Previous, Next, Play and Pause through Windows media events. Up, Down, joystick-center and the original Back key are **not implemented**. This describes the current adapter, not a proven hardware limit.

## What is known

| Path | Evidence on the test device | Status |
|---|---|---|
| RFCOMM channel 1 | Fresh SDP identifies a standard `JL_SPP` service; image uploads work; a 180-second passive capture received zero bytes | Normal display transport; raw key reporting remains unverified |
| RFCOMM channel 10 | Fresh SDP identifies a second `JL_SPP` service with a vendor UUID; a six-second receive-only baseline connected and received zero bytes | Purpose and input behavior unverified |
| Windows media events | Previous, Next, Play and Pause callbacks received during physical tests | Observed input path; native receiver startup is currently intermittent |
| HID | A fresh `1124` service query found no HID record; no target HID interface was bound in Windows | No usable HID interface in the tested device state |

The experimental media receiver also enables Stop, Record, Rewind, FastForward and ChannelUp/ChannelDown, and records playback/property changes. Enabling an event in Windows does not mean the MiniToo sends it. Synthetic JSON self-tests only validate formatting.

In the first physical round, Previous, Next and Pause provided working positive controls. Attempted Up, Down, joystick-center and original Back produced no callbacks through that receiver. Both advertised RFCOMM channels also passed separate six-second receive-only connection baselines with zero bytes; these quiet baselines do not establish how either channel reports keys.

The second physical round is inconclusive. The first native receiver attempt crashed. A retry reached ready, but no positive-control button callbacks were recorded during its capture window. The operator later reported completing the actions, without a captured control to establish timing. Neither attempt is evidence that channel 10 or another interface cannot report the missing keys.

Two private Python receiver configurations initialized and closed cleanly: window-owned SMTC without audio (162 seconds), and manually controlled SMTC with a muted MediaPlayer (about 140 seconds). Each ran alongside CoreAudio endpoint-volume notifications and raw RFCOMM channel 10. In each window the operator confirmed one Left and one Right press; neither capture received media callbacks, volume changes or raw bytes, and all processes exited with code 0. These configurations did not deliver the positive controls. Up, Down and Back were not pressed in either round, so neither adds evidence about those keys.

## Receiver reliability

Following a ten-minute Dashboard session with 583 acknowledged frames, later C# media receiver launches intermittently failed with `0xC0000005`. A minimal .NET HelloWorld program also failed before output in no-hardware tests. The cause has not been identified.

The normal adapter now reports startup/exit failures, waits up to 30 seconds for readiness per attempt, and permits two retries. This is bounded recovery, not a crash fix. A private Python/PyWinRT prototype is being evaluated as an alternative; it is not yet an implemented, validated public backend. A usable physical test must record ready and working positive controls in the same capture window.

For the Python/PyWinRT prototype, loading audio through `StorageFile` passed a ten-second ready/clean-shutdown baseline after the file-URL source had failed with `SOURCE_NOT_SUPPORTED` (`0x80070003`). The earlier failure was handled, with no native crash. Initialization alone has not established working input; comparison of the CommandManager route and actual Playing readiness is still in progress.

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

## Test method

Start in a known native device mode and keep streamed images off so they cannot hide the device's menus. Wait for the receiver's ready status. Record a quiet baseline, then test Left/Right as positive controls, repeated Up/Down actions, Play/Pause, center and Back. Keep Back last because it may change the device's internal mode. Check that positive controls were captured; otherwise classify the round as inconclusive. Repeat on each observed transport and compare the marked intervals.

A quiet capture only establishes that no signal was received under those conditions. Other firmware, modes, profiles or a required subscription remain separate questions. Unknown commands are not brute-forced. Raw captures, crash reports and device identifiers stay outside the repository; public evidence contains counts and conclusions only.
