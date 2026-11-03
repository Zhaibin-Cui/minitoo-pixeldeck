import argparse
import json
from pathlib import Path
import sys
from PIL import Image, ImageSequence
from . import __version__
from .config import DeviceConfig, home
from .demos import CATALOG, create
from .driver import MiniToo
from .instance import InstanceLock
from .protocol import fit_image, jpeg_clip, upload

def main():
    parser=argparse.ArgumentParser(prog='pixeldeck',description='MiniToo Pixeldeck / event-driven pixel playground')
    parser.add_argument('--version',action='version',version=__version__)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('list',help='List bundled cartridges')
    doctor=commands.add_parser('doctor',help='Inspect local dependencies and cached pairing without connecting')
    doctor.add_argument('--config')
    commands.add_parser('build-input',help='Compile the Windows media-event bridge')
    commands.add_parser('stop',help='Release the running session through local IPC')
    config=commands.add_parser('configure'); config.add_argument('--address',required=True); config.add_argument('--endpoint',default='MiniToo')
    config.add_argument('--output',type=Path)
    run=commands.add_parser('run'); run.add_argument('demo',nargs='?',choices=list(CATALOG),default='buddy')
    run.add_argument('--send',action='store_true'); run.add_argument('--media',action='store_true')
    run.add_argument('--stdin',action='store_true'); run.add_argument('--duration',type=int,default=600); run.add_argument('--config')
    show=commands.add_parser('image'); show.add_argument('path',type=Path); show.add_argument('--fit',choices=['contain','cover','stretch'],default='contain')
    show.add_argument('--send',action='store_true'); show.add_argument('--config')
    clip=commands.add_parser('clip',help='Experimental small multi-frame GIF upload; preview by default')
    clip.add_argument('path',type=Path); clip.add_argument('--frames',type=int,default=2); clip.add_argument('--period',type=int,default=250)
    clip.add_argument('--send',action='store_true'); clip.add_argument('--config')
    bright=commands.add_parser('brightness',help='Experimental brightness command; dry-run by default')
    bright.add_argument('level',type=int); bright.add_argument('--send',action='store_true'); bright.add_argument('--config')
    export=commands.add_parser('export',help='Render offline PNG/GIF demo previews')
    export.add_argument('demo',choices=list(CATALOG)); export.add_argument('--output',type=Path,required=True); export.add_argument('--seconds',type=int,default=4)
    args=parser.parse_args()
    if args.command=='list':
        for key,cls in CATALOG.items(): print(f'{key:9} {cls.title}\n          {cls.description}')
        return
    if args.command=='configure':
        print(DeviceConfig(address=args.address,endpoint=args.endpoint).save(args.output)); return
    if args.command=='doctor':
        import importlib.util
        import PIL
        from .diagnostics import report
        result=report(DeviceConfig.load(args.config))
        result.update({'version':__version__,'python':sys.version.split()[0],'pillow':PIL.__version__,
          'tkinter':importlib.util.find_spec('tkinter') is not None,
          'telemetry_extra':importlib.util.find_spec('psutil') is not None})
        print(json.dumps(result,indent=2)); return
    if args.command=='build-input':
        from .inputs import build_bridge
        print(build_bridge()); return
    if args.command=='stop':
        from .control import stop
        print('Stop acknowledged' if stop(home()) else 'No active session'); return
    if args.command=='export':
        from .export import export_demo
        if not 1<=args.seconds<=15: parser.error('seconds must be 1..15')
        export_demo(args.demo,args.output,args.seconds); print(args.output); return
    config=DeviceConfig.load(args.config)
    if args.command=='run':
        if not 0<=args.duration<=86400: parser.error('duration must be 0..86400; 0 means until closed')
        if args.media and not args.send: parser.error('--media requires --send')
        if args.send and not config.address:
            parser.error('No device configured. Run configure --address YOUR_ADDRESS or supply --config PRIVATE_FILE. Preview alone does not update the MiniToo.')
        from .app import Application
        Application(config,args.demo,args.send,args.media,args.stdin,args.duration).run(); return
    home().mkdir(parents=True,exist_ok=True)
    if args.command=='brightness':
        from .protocol import brightness_packet
        raw=brightness_packet(args.level)
        if not args.send: print('Experimental packet (not sent): '+raw.hex(' ')); return
        job=lambda device:device.brightness(args.level)
    elif args.command=='image':
        with Image.open(args.path) as source: picture=fit_image(source,args.fit)
        picture.save(home()/'image-preview.png')
        if not args.send: print(home()/'image-preview.png'); return
        job=lambda device:device.show(picture)
    else:
        if not 1<=args.frames<=8: parser.error('frames must be 1..8 within the 16 KB upload budget')
        with Image.open(args.path) as source:
            pictures=[]
            for index,image in enumerate(ImageSequence.Iterator(source)):
                if index>=args.frames: break
                pictures.append(fit_image(image))
        data=upload(jpeg_clip(pictures,args.period,config.quality))
        if not args.send:
            print(json.dumps({'experimental':True,'frames':len(pictures),'bytes':data.size,'chunks':len(data.chunks),'sent':False})); return
        job=lambda device:device.show_clip(pictures,args.period)
    lock=InstanceLock(home()/'instance.lock')
    try:
        with MiniToo(config) as device: print(json.dumps(job(device)))
    finally: lock.close()
