"""Regenerate every repository image from the demo renderers and original art."""
from pathlib import Path
import math
import sys
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pixeldeck.demos import CATALOG, create
from pixeldeck.export import export_demo, specimen
from pixeldeck.pixels import Canvas, INK, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD
OUT=ROOT/'docs/assets'; OUT.mkdir(parents=True,exist_ok=True)
USEFUL=('dashboard','network','storage','power','clock','stopwatch','pomodoro','breathe','build')

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
    for i,(label,color) in enumerate([('EVENT DRIVEN',CYAN),(f'{len(CATALOG)} CARTRIDGES',PINK),('160 X 128',MINT)]):
        x=50+i*157; d.rectangle((x,430,x+143,462),fill=PANEL,outline=LINE)
        text(out,x+72,442,label,color,1,True)
    buddy=specimen('buddy'); screen=buddy.render(t)
    out.paste(device(screen),(610,78))
    text(out,817,501,'ORIGINAL RENDER / DEVICE ILLUSTRATION',MUTED,1,True)
    return out

def audio_gallery():
    """Synthetic 48 kHz mono windows, then a retained five-second summary."""
    demo=create('audio'); pictures=[]; squares=0; peak=0
    demo.handle({'type':'audio.status','state':'ready','mode':'microphone','elapsed':0},0)
    for index in range(50):
        elapsed=(index+1)/10
        amplitude=.012+.032*(.5+.5*math.sin(elapsed*2.7))
        samples=[amplitude*math.sin(i*math.tau/16+elapsed*3) for i in range(64)]
        window_squares=sum(value*value for value in samples)
        window_peak=max(abs(value) for value in samples)
        squares+=window_squares; peak=max(peak,window_peak)
        summary={'session_rms':math.sqrt(squares/((index+1)*64)),
                 'session_peak':peak,'metered_frames':(index+1)*4800,'dropped_frames':0}
        demo.handle({'type':'audio.level','mode':'microphone','elapsed':elapsed,
                     'rms':math.sqrt(window_squares/64),'peak':window_peak,
                     'waveform':[max(samples[i:i+2],key=abs) for i in range(0,64,2)],
                     **summary},elapsed)
        pictures.append(demo.render(elapsed))
    demo.handle({'type':'audio.status','state':'stopped','mode':'microphone',
                 'elapsed':5,**summary},5)
    pictures.extend(demo.render(5) for _ in range(10))
    return demo,pictures

def gallery_specimen(name):
    return audio_gallery()[0] if name=='audio' else specimen(name)

def overview(names=None,title='THE CARTRIDGE COLLECTION'):
    names=list(CATALOG if names is None else names)
    rows=math.ceil(len(names)/3)
    height=105+rows*330+82
    out=Image.new('RGB',(1080,height),INK); d=ImageDraw.Draw(out)
    text(out,24,24,title,CYAN,4)
    text(out,26,64,'ACTUAL RENDERS / SYNTHETIC DATA / NO DEVICE REQUIRED',MUTED,2)
    for index,name in enumerate(names):
        x=24+(index%3)*352; y=105+(index//3)*330
        d.rectangle((x,y,x+331,y+309),fill=PANEL,outline=LINE)
        out.paste(gallery_specimen(name).render(1).resize((320,256),Image.Resampling.NEAREST),(x+6,y+6))
        text(out,x+12,y+277,name,CYAN,2)
    footer=105+rows*330
    d.line((24,footer,1055,footer),fill=LINE,width=2)
    text(out,26,footer+20,f'{len(names):02} CARTRIDGES / ONE RENDERING API',PINK,2)
    text(out,26,footer+48,'RENDER / HANDLE / NEXT_DELAY / OPTIONAL DATA SOURCES',MUTED,2)
    return out

def architecture():
    out=Image.new('RGB',(1080,370),INK); d=ImageDraw.Draw(out)
    text(out,24,22,'THE PIXEL PIPELINE',CYAN,3)
    labels=[('INPUTS','CALLBACK / SOURCES'),('CARTRIDGE','STATE / RENDER'),('LATEST FRAME','ONE PENDING SLOT'),('DEVICE','ACK / RETRY')]
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

def controls():
    out=Image.new('RGB',(1080,218),INK); d=ImageDraw.Draw(out)
    text(out,24,12,'DESKTOP CONTROLS / CHECK PREVIEW OR LIVE MODE',MUTED,2)
    keys=[('LEFT / RIGHT','SELECT CARTRIDGE OR TILE',CYAN),('ENTER / SPACE','OPEN / ACTIVATE',PINK),
          ('ESC','BACK',MINT),('R','RESET SUPPORTED TIMERS',GOLD),
          ('CTRL + Q','EXIT SESSION',PINK),('PREVIEW / LIVE','OUTPUT MODE IN STATUS',CYAN)]
    for i,(key,action,color) in enumerate(keys):
        x=24+(i%3)*352; y=46+(i//3)*82
        d.rectangle((x,y,x+331,y+69),fill=PANEL,outline=LINE,width=2)
        text(out,x+166,y+16,key,color,2,True)
        text(out,x+166,y+48,action,MUTED,1,True)
    return out

def io_map():
    out=Image.new('RGB',(1080,670),INK); d=ImageDraw.Draw(out)
    text(out,24,22,'READ / WRITE / INPUT',CYAN,3)
    text(out,24,66,'PUBLIC API SURFACES / EXPERIMENTS ARE EXPLICIT',MUTED,2)
    columns=[
        ('READ',CYAN,[
            ('HOST METRICS','CPU / RAM / NET / DISK / POWER','LOCAL API CHECKS',MINT),
            ('DEVICE REPLIES','READY / DONE / RESEND','LIVE TRANSFERS OBSERVED',MINT),
            ('RX BYTES','RAW CHUNKS + DECODED PACKETS','EXPERIMENTAL CAPTURE',GOLD),
            ('MIC INPUT','LIVE RMS / SESSION RMS + PEAK','SHORT CAPTURE CHECKED',MINT)]),
        ('WRITE',PINK,[
            ('LIVE FRAMES','160 X 128 RGB','HARDWARE CHECKED',MINT),
            ('JPEG CLIPS','BOUNDED MULTI-FRAME ENCODING','PLAYBACK EXPERIMENTAL',GOLD),
            ('BRIGHTNESS','EXPLICIT COMMAND / DRY RUN FIRST','PHYSICAL EFFECT UNVERIFIED',GOLD),
            ('AUDIO OUTPUT','TEST TONE / SELECTED ENDPOINT','SHORT PLAYBACK CHECKED',MINT)]),
        ('INPUT',MINT,[
            ('DESKTOP + JSONL','KEYS / NOTICE / BUILD','APP EVENTS TESTED',MINT),
            ('MEDIA CALLBACKS','PREVIOUS / NEXT / PLAY / PAUSE','OBSERVED / TAP COUNTS OPEN',GOLD),
            ('RAW INPUT RESEARCH','PASSIVE CAPTURE / SOFTWARE PROBES','NO UP/DOWN/BACK MAPPING',PINK),
            ('AUDIO CONTROLS','ACTIVATE STARTS / BACK STOPS','FIVE SECONDS / OFF BY DEFAULT',GOLD)])]
    for i,(label,color,rows) in enumerate(columns):
        x=24+i*352
        d.rectangle((x,112,x+331,598),fill=PANEL,outline=LINE,width=2)
        text(out,x+16,130,label,color,3)
        d.line((x+16,162,x+315,162),fill=LINE)
        for j,(title,detail,state,state_color) in enumerate(rows):
            y=184+j*104
            text(out,x+16,y,title,WHITE,2)
            text(out,x+16,y+29,detail,MUTED)
            d.rectangle((x+16,y+51,x+20,y+58),fill=state_color)
            text(out,x+29,y+52,state,state_color)
    text(out,24,624,'HARDWARE RESULTS APPLY TO THE TESTED HOST AND DEVICE.',MUTED,2)
    text(out,24,652,'SEE THE CAPABILITY MAP FOR RUNNABLE EXAMPLES AND VERIFICATION.',MUTED)
    return out

if __name__=='__main__':
    for name in CATALOG:
        if name=='audio':
            demo,pictures=audio_gallery()
            demo.render(5).save(OUT/'audio.png')
            pictures=[frame.resize((320,256),Image.Resampling.NEAREST) for frame in pictures]
            pictures[0].save(OUT/'audio.gif',save_all=True,append_images=pictures[1:],
                             duration=100,loop=0,optimize=False,disposal=2)
        else:
            export_demo(name,OUT/(name+'.gif'))
            export_demo(name,OUT/(name+'.png'))
    hero().save(OUT/'hero.png')
    shots=[hero(i/3) for i in range(12)]
    shots[0].save(OUT/'hero.gif',save_all=True,append_images=shots[1:],duration=333,loop=0,optimize=False)
    overview().save(OUT/'gallery.png')
    overview([name for name in USEFUL if name in CATALOG],title='SMALL TOOLS. REAL PURPOSE.').save(OUT/'useful-demos.png')
    architecture().save(OUT/'architecture.png')
    controls().save(OUT/'controls.png')
    io_map().save(OUT/'io-map.png')
    device(specimen('orbit').render(1)).save(OUT/'device-orbit.png')
    print('Generated original gallery assets.')
