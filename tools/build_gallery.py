"""Regenerate every repository image from the demo renderers and original art."""
from pathlib import Path
import math
import sys
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pixeldeck.demos import CATALOG
from pixeldeck.export import export_demo, specimen
from pixeldeck.pixels import Canvas, INK, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD
OUT=ROOT/'docs/assets'; OUT.mkdir(parents=True,exist_ok=True)

def text(image,x,y,value,color=WHITE,size=1,center=False):
    c=Canvas(); c.image=image; c.d=ImageDraw.Draw(image); c.text(x,y,value,color,size,center)

def device(screen,scale=2):
    """Stylized front view, not a product photo or a dimensional CAD drawing."""
    base=Image.new('RGB',(206,206),INK); d=ImageDraw.Draw(base)
    d.rectangle((17,11,191,164),fill='#918e91')
    d.rectangle((12,8,187,162),fill='#d6d1c4')
    d.rectangle((17,13,182,157),fill='#b0adab')
    d.rectangle((20,16,179,143),fill=INK)
    base.paste(screen,(20,16))
    d.rectangle((5,163,196,194),fill='#8f909a')
    d.rectangle((8,159,193,189),fill='#d6d1c4')
    for x in range(20,116,12):
        d.rectangle((x,169,x+8,178),fill='#727b8b')
        d.line((x,169,x+8,169),fill='#e8e3d5')
    d.rectangle((20,169,28,178),fill='#fa9a61')
    d.ellipse((148,168,174,181),fill='#777e8b')
    d.rectangle((158,153,163,173),fill='#798293')
    d.ellipse((150,146,171,164),fill='#f6a568',outline='#ad7051')
    d.rectangle((23,190,39,197),fill=LINE); d.rectangle((160,190,177,197),fill=LINE)
    return base.resize((206*scale,206*scale),Image.Resampling.NEAREST)

def hero(t=0):
    out=Image.new('RGB',(1080,540),INK); d=ImageDraw.Draw(out)
    for y in range(540): d.line((0,y,1079,y),fill=(8+int(y/90),13+int(y/70),25+int(y/42)))
    for x in range(0,1080,24): d.line((x,0,x,539),fill='#172035')
    for y in range(0,540,24): d.line((0,y,1079,y),fill='#172035')
    d.rectangle((24,24,1055,515),outline=LINE,width=2)
    d.rectangle((48,56,52,81),fill=CYAN)
    text(out,64,63,'MINITOO / OPEN PIXEL PLAYGROUND',CYAN,2)
    text(out,48,120,'PIXEL',WHITE,9)
    text(out,48,194,'DECK',CYAN,9)
    text(out,50,290,'SMALL SCREEN.',WHITE,3)
    text(out,50,322,'BIG PERSONALITY.',PINK,3)
    text(out,50,382,'PROTOCOL  >  STREAMS  >  CARTRIDGES',MUTED,2)
    for i,(label,color) in enumerate([('EVENT DRIVEN',CYAN),('7 DEMOS',PINK),('160 X 128',MINT)]):
        x=50+i*157; d.rectangle((x,430,x+143,462),fill=PANEL,outline=LINE)
        text(out,x+72,442,label,color,1,True)
    buddy=specimen('buddy'); screen=buddy.render(t)
    out.paste(device(screen),(610,78))
    text(out,817,501,'ORIGINAL RENDER / DEVICE ILLUSTRATION',MUTED,1,True)
    return out

def overview():
    out=Image.new('RGB',(1080,1110),INK); d=ImageDraw.Draw(out)
    text(out,24,24,'INSERT A LITTLE PERSONALITY.',CYAN,4)
    text(out,26,64,'ACTUAL DEMO RENDERS / SYNTHETIC MONITOR DATA',MUTED,2)
    for index,name in enumerate(CATALOG):
        x=24+(index%3)*352; y=105+(index//3)*330
        d.rectangle((x,y,x+331,y+309),fill=PANEL,outline=LINE)
        out.paste(specimen(name).render(1).resize((320,256),Image.Resampling.NEAREST),(x+6,y+6))
        text(out,x+12,y+277,name,CYAN,2)
    text(out,400,805,'ONE TINY API.',PINK,3)
    text(out,400,852,'ENDLESS LITTLE WORLDS.',WHITE,3)
    text(out,400,914,'RENDER / HANDLE / NEXT_DELAY',MUTED,2)
    text(out,400,947,'PREVIEW FIRST. DEVICE OPTIONAL.',MUTED,2)
    return out

def architecture():
    out=Image.new('RGB',(1080,370),INK); d=ImageDraw.Draw(out)
    text(out,24,22,'THE PIXEL PIPELINE',CYAN,3)
    labels=[('INPUTS','CALLBACK / JSONL'),('CARTRIDGE','STATE / RENDER'),('LATEST FRAME','ONE PENDING SLOT'),('DEVICE','ACK / RETRY')]
    for i,(title,subtitle) in enumerate(labels):
        x=24+i*266
        d.rectangle((x,95,x+233,220),fill=PANEL,outline=LINE,width=2)
        text(out,x+117,120,title,CYAN if i%2==0 else PINK,2,True)
        text(out,x+117,169,subtitle,MUTED,1,True)
        if i<3:
            d.line((x+237,157,x+261,157),fill=CYAN,width=2)
            d.polygon([(x+261,157),(x+254,151),(x+254,163)],fill=CYAN)
    text(out,540,268,'RECEIVE AND TRANSMIT HAVE INDEPENDENT WORKERS.',WHITE,2,True)
    text(out,540,310,'STATIC SCREENS SLEEP. OBSOLETE FRAMES DISAPPEAR.',MUTED,2,True)
    return out

if __name__=='__main__':
    for name in CATALOG:
        export_demo(name,OUT/(name+'.gif'))
        export_demo(name,OUT/(name+'.png'))
    hero().save(OUT/'hero.png')
    shots=[hero(i/3) for i in range(12)]
    shots[0].save(OUT/'hero.gif',save_all=True,append_images=shots[1:],duration=333,loop=0,optimize=False)
    overview().save(OUT/'gallery.png'); architecture().save(OUT/'architecture.png')
    device(specimen('orbit').render(1)).save(OUT/'device-orbit.png')
    print('Generated original gallery assets.')
