"""Preview the three public device writes; --send explicitly performs them.

Examples:
  python examples/device_lab.py
  python examples/device_lab.py --operation still --send --config device.json
  python examples/device_lab.py --operation clip --send --period 500
  python examples/device_lab.py --operation brightness --level 50 --send

Clip playback and brightness are experimental. The original brightness cannot be
read, so this example does not invent an automatic restoration value.
"""
import argparse
import json

from pixeldeck import DeviceConfig, MiniToo
from pixeldeck.config import home
from pixeldeck.instance import InstanceLock
from pixeldeck.pixels import Canvas, CYAN, MINT, LINE
from pixeldeck.protocol import MAX_BLOB, brightness_packet, jpeg_clip, upload


def pictures():
    frames = []
    for index, color in enumerate((CYAN, MINT), start=1):
        canvas = Canvas()
        canvas.header('LAB', f'{index:02}', color)
        canvas.d.rectangle((16, 29, 143, 101), outline=color, width=2)
        canvas.text(80, 42, f'{index:02}', color, 2, center=True)
        canvas.d.rectangle((27, 69, 132, 78), fill=LINE)
        canvas.d.rectangle((27, 69, 27+index*50, 78), fill=color)
        frames.append(canvas.image)
    return frames


def plan(operations, frames, level, period, quality=72):
    result = []
    for operation in operations:
        if operation == 'brightness':
            result.append({'operation': operation, 'experimental': True, 'level': level,
                           'packet_hex': brightness_packet(level).hex(' '),
                           'original_level_known': False, 'automatic_restore': False})
        else:
            selected = frames[:1] if operation == 'still' else frames
            frame_period = 1000 if operation == 'still' else period
            job = upload(jpeg_clip(selected, frame_period, quality))
            result.append({'operation': operation, 'experimental': operation == 'clip',
                           'frames': len(selected), 'period_ms': frame_period,
                           'bytes': job.size, 'chunks': len(job.chunks),
                           'within_upload_budget': job.size <= MAX_BLOB})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', choices=('still', 'clip', 'brightness', 'all'), default='all')
    parser.add_argument('--level', type=int, default=50)
    parser.add_argument('--period', type=int, default=250)
    parser.add_argument('--config')
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args(argv)
    if not 0 <= args.level <= 100:
        parser.error('level must be within 0..100')
    if not 1 <= args.period <= 65535:
        parser.error('period must be within 1..65535 milliseconds')
    operations = ('still', 'clip', 'brightness') if args.operation == 'all' else (args.operation,)
    frames = pictures()
    if not args.send:
        print(json.dumps({'mode': 'dry_run', 'hardware_accessed': False, 'sent': False,
                          'upload_budget_bytes': MAX_BLOB,
                          'operations': plan(operations, frames, args.level, args.period)}))
        return 0
    config = DeviceConfig.load(args.config)
    if not config.address:
        parser.error('Configure a paired device or supply --config before --send')
    # Encoding and bounds checks complete before the device is opened.
    prepared = plan(operations, frames, args.level, args.period, config.quality)
    runtime = home()
    runtime.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(runtime / 'instance.lock')
    try:
        with MiniToo(config) as device:
            for entry in prepared:
                operation = entry['operation']
                if operation == 'still':
                    result = device.show(frames[0])
                elif operation == 'clip':
                    result = device.show_clip(frames, args.period)
                else:
                    result = {'acknowledged_level': device.brightness(args.level)}
                print(json.dumps({'mode': 'live', 'operation': operation, 'sent': True,
                                  'experimental': entry['experimental'], 'result': result,
                                  'physical_effect_verified': False}), flush=True)
    finally:
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
