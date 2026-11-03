"""Repeatable gallery rendering with explicitly synthetic telemetry fixtures."""
from pathlib import Path
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
    return demo

def frames(name,seconds=4,fps=8):
    demo=specimen(name)
    for index in range(seconds*fps):
        now=index/fps
        if name=='pulse': demo.handle({'type':'telemetry','cpu':25+(index*3)%42,'memory':43},now)
        demo.handle({'type':'tick'},now)
        yield demo.render(now)

def export_demo(name,path,seconds=4):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.suffix.lower()=='.png': specimen(name).render(1).save(path); return
    if path.suffix.lower()!='.gif': raise ValueError('Output must be PNG or GIF')
    pictures=[frame.resize((320,256),Image.Resampling.NEAREST) for frame in frames(name,seconds)]
    pictures[0].save(path,save_all=True,append_images=pictures[1:],duration=125,loop=0,optimize=False,disposal=2)
