# Extension recipes

## A cartridge

Subclass `Demo`. `render(now)` produces RGB pixels, `handle(event, now)` mutates state, and `next_delay(now)` requests the next time event. Return `None` for a static or paused scene. Use monotonic elapsed time rather than counting frames. Keep network and device I/O outside the renderer.

Register the class with `pixeldeck.demos.register`, then create `Application(config, demo="your-key")`. [Complete example](../examples/custom_cartridge.py).

A data-backed cartridge can declare `sources = ("network",)` and `source_interval = 1.0`, then consume the corresponding `network` event in `handle`. Source reads happen in the host's worker, not the renderer. A cartridge with a `held` state can suspend its data requests while frozen. Keep sample history bounded and show unavailable values honestly.

Use `supports_reset = True` for a cartridge that handles the desktop button event `{"type":"button","button":"reset"}`. Distinguish that action from `activate`; do not increment a counter or toggle playback on every event whose type happens to be `button`.

For a nested interface, set `captures_navigation = True` and handle `previous`, `next` and `back` button events as well as `activate`. Dashboard shows this pattern: selection and detail state remain inside the cartridge. Return `"leave"` from `handle` to return to Bit Buddy, or `"exit"` after an explicit exit action to request host shutdown. Keep connection cleanup in the host.

## A direct image sender

```python
from PIL import Image
from pixeldeck import DeviceConfig, MiniToo
from pixeldeck.protocol import fit_image

config = DeviceConfig.load()  # Private local file
with Image.open("art.png") as source:
    picture = fit_image(source)
with MiniToo(config) as display:
    report = display.show(picture)
print(report)
```

This explicitly opens hardware. Library callers should acquire `pixeldeck.instance.InstanceLock` if they share a runtime with other senders; the CLI does this for you.

`DeviceConfig.codec` defaults to `jpeg`. With the optional `display` extra installed, `codec="zstd"` selects lossless RGB and `codec="auto"` chooses the smaller available encoding within the 16,000-byte limit. `pixeldeck.encoding.encode_frame(picture, codec="auto")` returns `(selected_codec, payload)` without hardware access. Selection happens before transmission; it does not negotiate device support or retry a failed transfer in another format. `show_clip()` remains JPEG.

## A headless event-fed display

```python
from pixeldeck import DeviceConfig, MiniToo, FramePump

config = DeviceConfig.load()
pump = FramePump(lambda: MiniToo(config), on_status=print)
try:
    # Call this from an actual application event, with a 160x128 PIL image:
    # pump.submit(picture, received_at=time.monotonic())
    pass
finally:
    pump.close()
```

To recover while idle, route the driver's `on_disconnect` callback to `pump.reconnect`, as the GUI host does. `submit` returns immediately after copying pixels. Its boolean return indicates whether a new frame was queued; identical or closed submissions return false. Status callbacks run on a worker thread. A sink's `show` returns a dictionary containing `transfer_ms`; fields such as codec, encoding time, bytes and chunks pass through. The pump adds `queue_ms` and `frame_age_ms`, measuring submission-to-send and submission-to-ACK respectively, not visible-pixel latency.

## A notification producer

Write one JSON object and a newline whenever the source event occurs. Flush the pipe. No file tailing is required. The bundled reader accepts a `notice` with string `text`, or a `build` event with bounded project/step text, a defined state and optional numeric progress. [One-shot notice example](../examples/push_notice.py).

```json
{"type":"build","project":"PIXEL PROJECT","state":"running","progress":64,"step":"RUNNING CHECKS"}
```

The producer owns the actual operation and decides when to send `passed` or `failed`. Pixeldeck does not infer success from a progress bar reaching 100, execute commands from events, or poll a directory for changes.

## A new transport

Keep the `protocol` layer unchanged when porting RFCOMM to another OS. Inject a socket factory into `MiniToo`. A receive call must block until data, disconnect or explicit shutdown. A close must release blocked calls. The deadline watchdog relies on shutdown being able to interrupt a stalled send.

For another kind of screen, bypass `MiniToo` and implement the small sink interface. The mailbox, coalescing, diagnostics and demos can remain the same.
