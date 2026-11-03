# Extension recipes

## A cartridge

Subclass `Demo`. `render(now)` produces RGB pixels, `handle(event, now)` mutates state, and `next_delay(now)` requests the next time event. Return `None` for a static or paused scene. Use monotonic elapsed time rather than counting frames. Keep network and device I/O outside the renderer.

Register the class with `pixeldeck.demos.register`, then create `Application(config, demo="your-key")`. [Complete example](../examples/custom_cartridge.py).

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

To recover while idle, route the driver's `on_disconnect` callback to `pump.reconnect`, as the GUI host does. `submit` returns immediately after copying pixels. Its boolean return indicates whether a new frame was queued; identical or closed submissions return false. Status callbacks run on a worker thread. A sink's `show` returns a dictionary containing `transfer_ms`; extra fields such as bytes and chunks pass through.

## A notification producer

Write one JSON object and a newline whenever the source event occurs. Flush the pipe. No file tailing is required. Only `type=notice` and a string `text` are accepted by the bundled reader. [One-shot example](../examples/push_notice.py).

## A new transport

Keep the `protocol` layer unchanged when porting RFCOMM to another OS. Inject a socket factory into `MiniToo`. A receive call must block until data, disconnect or explicit shutdown. A close must release blocked calls. The deadline watchdog relies on shutdown being able to interrupt a stalled send.

For another kind of screen, bypass `MiniToo` and implement the small sink interface. The mailbox, coalescing, diagnostics and demos can remain the same.
