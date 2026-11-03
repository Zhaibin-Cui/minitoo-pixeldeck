"""Repeatable gallery rendering with explicitly synthetic telemetry fixtures."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from PIL import Image
from .demos import create

def specimen(name, now=0):
    demo=create(name)
    if name=='pulse':
        for i in range(61): demo.handle({'type':'telemetry','cpu':22+(i*7)%48,'memory':43},i)
    if name=='focus': demo.handle({'type':'button','button':'activate'},0)
    if name=='signal': demo.handle({'type':'notice','text':'HELLO FROM THE OTHER SIDE'},0)
    if name=='buttons':
        for i in range(12): demo.handle({'type':'button','raw':'PLAY / PAUSE'},i)
    if name=='buddy': demo.handle({'type':'button'},0)
    if name=='clock':
        demo.handle({'type':'wallclock','local':'2026-11-03T20:18:35+08:00','utc':'2026-11-03T12:18:35+00:00'},0)
    if name in ('stopwatch','pomodoro','breathe'):
        start={'stopwatch':-123.25,'pomodoro':-810,'breathe':-2}[name]
        demo.handle({'type':'button','button':'activate'},start)
    if name=='network':
        for i in range(61):
            demo.handle({'type':'network','available':True,'rx_bps':350000+(i*79000)%1800000,'tx_bps':60000+(i*11000)%260000},i)
    if name=='storage':
        demo.handle({'type':'storage','available':True,'volumes':[
            {'label':'SYSTEM','total':512*2**30,'free':184*2**30},
            {'label':'ARCHIVE','total':2*2**40,'free':int(1.2*2**40)}]},0)
    if name=='power':
        demo.handle({'type':'power','available':True,'present':True,'percent':67,'plugged':False,'seconds_left':9060},0)
    if name=='build':
        demo.handle({'type':'build','project':'PIXEL ENGINE','state':'running','progress':64,'step':'COMPILE SHADERS'},0)
    return demo

def frames(name,seconds=4,fps=8):
    demo=specimen(name)
    for index in range(seconds*fps):
        now=index/fps
        if name=='pulse': demo.handle({'type':'telemetry','cpu':25+(index*3)%42,'memory':43},now)
        if name=='clock':
            utc=datetime(2026,11,3,12,18,35,tzinfo=timezone.utc)+timedelta(seconds=now)
            demo.handle({'type':'wallclock','local':utc.astimezone(timezone(timedelta(hours=8))).isoformat(),'utc':utc.isoformat()},now)
        if name=='network':
            demo.handle({'type':'network','available':True,'rx_bps':600000+(index*120000)%1300000,'tx_bps':100000+(index*17000)%250000},now)
        if name=='build':
            progress=min(100,64+index*2)
            demo.handle({'type':'build','project':'PIXEL ENGINE','state':'passed' if progress==100 else 'running','progress':progress,
                         'step':'CHECKS COMPLETE' if progress==100 else 'COMPILE SHADERS'},now)
        if name=='storage' and index==16: demo.handle({'type':'button','button':'activate'},now)
        if name=='power' and index==16: demo.handle({'type':'button','button':'activate'},now)
        demo.handle({'type':'tick'},now)
        yield demo.render(now)

def export_demo(name,path,seconds=4):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.suffix.lower()=='.png': specimen(name).render(1).save(path); return
    if path.suffix.lower()!='.gif': raise ValueError('Output must be PNG or GIF')
    pictures=[frame.resize((320,256),Image.Resampling.NEAREST) for frame in frames(name,seconds)]
    pictures[0].save(path,save_all=True,append_images=pictures[1:],duration=125,loop=0,optimize=False,disposal=2)
