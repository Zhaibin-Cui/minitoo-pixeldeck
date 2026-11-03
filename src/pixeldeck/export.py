"""Repeatable gallery rendering with explicitly synthetic telemetry fixtures."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import math
from PIL import Image
from .demos import create

def specimen(name, now=0):
    demo=create(name)
    if name in ('pulse','dashboard'):
        for i in range(61): demo.handle({'type':'telemetry','cpu':22+(i*7)%48,'memory':43,'sampled_at':i-60},i-60)
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
    if name in ('network','dashboard'):
        for i in range(61):
            demo.handle({'type':'network','available':True,'rx_bps':350000+(i*79000)%1800000,'tx_bps':60000+(i*11000)%260000},i)
    if name in ('storage','dashboard'):
        demo.handle({'type':'storage','available':True,'volumes':[
            {'label':'SYSTEM','total':512*2**30,'free':184*2**30},
            {'label':'ARCHIVE','total':2*2**40,'free':int(1.2*2**40)}]},0)
    if name in ('power','dashboard'):
        demo.handle({'type':'power','available':True,'present':True,'percent':67,'plugged':False,'seconds_left':9060},0)
    if name=='build':
        demo.handle({'type':'build','project':'PIXEL ENGINE','state':'running','progress':64,'step':'COMPILE SHADERS'},0)
    if name=='link':
        for i in range(24):
            demo.observe({'type':'frame.ack','sequence':i+1,'transfer_ms':260+(i*17)%170,
                          'bytes':4096+i*32,'chunks':16+i//8,'retransmissions':int(i%7==0),
                          'replaced':3,'input_to_ack_ms':440+i},i-24)
        demo.observe({'type':'input.status','kind':'ready'},0)
        demo.observe({'type':'button','button':'activate','source':'media','raw':'Pause'},0)
        demo.observe({'type':'button','button':'activate','source':'desktop','raw':'KEYBOARD'},0)
        demo.observe({'type':'input.coalesced'},0)
        demo.handle({'type':'button','button':'activate'},0)
        demo.handle({'type':'button','button':'back'},0)
    if name=='audio':
        demo.handle({'type':'audio.status','state':'ready','mode':'duplex'},0)
        demo.handle({'type':'audio.level','mode':'duplex','elapsed':2.4,'rms':.34,'peak':.78,
                     'waveform':[.65*math.sin(i*.55) for i in range(32)]},0)
    return demo

def frames(name,seconds=4,fps=8):
    if type(seconds) is not int or not 1 <= seconds <= 15 or type(fps) is not int or not 1 <= fps <= 30:
        raise ValueError('Preview duration must be 1..15 seconds and frame rate 1..30')
    demo=create(name) if name=='audio' else specimen(name)
    for index in range(seconds*fps):
        now=index/fps
        if name in ('pulse','dashboard'):
            demo.handle({'type':'telemetry','cpu':25+(index*3)%42,'memory':43+index//8,'sampled_at':now},now)
        if name=='clock':
            utc=datetime(2026,11,3,12,18,35,tzinfo=timezone.utc)+timedelta(seconds=now)
            demo.handle({'type':'wallclock','local':utc.astimezone(timezone(timedelta(hours=8))).isoformat(),'utc':utc.isoformat()},now)
        if name in ('network','dashboard'):
            demo.handle({'type':'network','available':True,'rx_bps':600000+(index*120000)%1300000,'tx_bps':100000+(index*17000)%250000},now)
        if name=='build':
            progress=min(100,64+index*2)
            demo.handle({'type':'build','project':'PIXEL ENGINE','state':'passed' if progress==100 else 'running','progress':progress,
                         'step':'CHECKS COMPLETE' if progress==100 else 'COMPILE SHADERS'},now)
        if name=='storage' and index==16: demo.handle({'type':'button','button':'activate'},now)
        if name=='power' and index==16: demo.handle({'type':'button','button':'activate'},now)
        if name=='dashboard' and index in (8,16,24):
            demo.handle({'type':'button','button':{8:'activate',16:'next',24:'back'}[index]},now)
        if name=='link' and index in (8,16,24,27,30):
            demo.handle({'type':'button','button':'next' if index in (16,24) else 'activate'},now)
        if name=='audio':
            span=max(1,seconds*fps//3)
            mode_index=min(2,index//span)
            mode=('speaker','microphone','duplex')[mode_index]
            if demo.mode != mode:
                demo=create(name)
            amplitude=.35+.25*(.5+.5*math.sin(now*3))
            demo.handle({'type':'audio.status','state':'ready','mode':mode},now)
            demo.handle({'type':'audio.level','mode':mode,'elapsed':(index-mode_index*span)/fps,
                         'rms':amplitude/math.sqrt(2),'peak':amplitude,
                         'waveform':[amplitude*math.sin(i*.55+now*4) for i in range(32)]},now)
        demo.handle({'type':'tick'},now)
        yield demo.render(now)

def export_demo(name,path,seconds=4):
    if type(seconds) is not int or not 1 <= seconds <= 15:
        raise ValueError('Preview duration must be 1..15 seconds')
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.suffix.lower()=='.png': specimen(name).render(1).save(path); return
    if path.suffix.lower()!='.gif': raise ValueError('Output must be PNG or GIF')
    pictures=[frame.resize((320,256),Image.Resampling.NEAREST) for frame in frames(name,seconds)]
    pictures[0].save(path,save_all=True,append_images=pictures[1:],duration=125,loop=0,optimize=False,disposal=2)
