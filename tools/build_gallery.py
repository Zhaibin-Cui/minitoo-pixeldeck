"""Regenerate every repository image from the demo renderers and original art."""
from pathlib import Path
import math
import random
import sys
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pixeldeck.demos import CATALOG, create
from pixeldeck.export import export_demo, specimen
from pixeldeck.pixels import Canvas, INK, PANEL, LINE, WHITE, CYAN, PINK, MINT, MUTED, GOLD
OUT=ROOT/'docs/assets'; OUT.mkdir(parents=True,exist_ok=True)
USEFUL=('dashboard','network','storage','power','clock','stopwatch','pomodoro','breathe','build')
FOREST={'night':'#071519','far':'#102b31','pine':'#143d36','leaf':'#275b43',
        'moss':'#43856a','light':'#91c6a0','bark':'#203038','rock':'#172536',
        'shade':'#111b2c','glow':'#e7d59a','flower':'#c89cae'}

def text(image,x,y,value,color=WHITE,size=1,center=False):
    c=Canvas(); c.image=image; c.d=ImageDraw.Draw(image); c.text(x,y,value,color,size,center)

def device(screen,scale=2,transparent=False):
    """Stylized front view, not a product photo or a dimensional CAD drawing."""
    base=Image.new('RGBA' if transparent else 'RGB',(206,206),(0,0,0,0) if transparent else INK)
    d=ImageDraw.Draw(base)
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

def _leaf(draw,x,y,color,flip=False,scale=1):
    """A compact pointed leaf sprite, shared by canopy, vines and page edges."""
    rows=('0001100','0011110','0111110','1111100','0110000')
    for row,bits in enumerate(rows):
        for col,bit in enumerate(bits):
            if bit=='1':
                px=x+(6-col if flip else col)*scale
                draw.rectangle((px,y+row*scale,px+scale-1,y+(row+1)*scale-1),fill=color)

def _foliage(draw,x,y,radius,seed,color=None):
    rng=random.Random(seed)
    color=color or FOREST['pine']
    for index in range(7):
        px=x+rng.randint(-radius,radius); py=y+rng.randint(-radius//3,radius//3)
        size=rng.randint(max(3,radius//3),max(4,radius*2//3))
        draw.ellipse((px-size,py-size//2,px+size,py+size),fill=color)
    for index in range(max(5,radius//2)):
        px=x+rng.randint(-radius,radius); py=y+rng.randint(-radius//2,radius//2)
        _leaf(draw,px,py,FOREST['leaf'] if index%3 else FOREST['moss'],index%2)

def _vine(draw,x,y,length,seed,t=0):
    phase=seed*.7
    points=[(x+round(math.sin(step/12+phase+t*math.tau/4)*2),y+step)
            for step in range(length)]
    if points:
        draw.line(points,fill=FOREST['leaf'],width=1)
    for step in range(6,length,9):
        px,py=points[step]
        flip=(step//9+seed)%2==0
        _leaf(draw,px-6 if flip else px,py,FOREST['moss'] if step%3 else FOREST['leaf'],flip)

def _tree(draw,x,base,height,seed,color):
    """Layered broadleaf silhouette; far trees stay quiet behind the foreground."""
    rng=random.Random(seed)
    draw.rectangle((x-2,base-height//2,x+2,base),fill=color)
    for index in range(5):
        y=base-height+index*height//7
        radius=max(4,(index+2)*height//15)
        offset=rng.randint(-height//12,height//12)
        draw.polygon([(x+offset,y-4),(x+offset+radius,y+radius//3),
                      (x+offset+radius,y+radius//2),(x-radius+offset,y+radius//2),
                      (x-radius+offset,y+radius//3)],fill=color)

def _island(draw,x,y,width,depth,seed,t=0):
    rng=random.Random(seed); left=x-width//2; right=x+width//2
    draw.polygon([(left,y),(right,y),(right-7,y+depth//3),(x+width//5,y+depth),
                  (x,y+depth-7),(x-width//4,y+depth*3//4),(left+9,y+depth//3)],fill=FOREST['rock'])
    for offset in range(5,width-8,12):
        top=y+3; end=y+rng.randint(max(4,depth//3),max(5,depth-2))
        draw.polygon([(left+offset,top),(left+offset+8,top),(left+offset+3,end)],fill=FOREST['shade'])
    draw.ellipse((left-2,y-5,right+2,y+5),fill=FOREST['leaf'])
    draw.line((left+8,y-3,right-7,y-3),fill=FOREST['moss'],width=2)
    for index in range(max(4,width//8)):
        px=rng.randint(left+3,right-3)
        draw.line((px,y-2,px-2,y-rng.randint(4,8)),fill=FOREST['moss'])
        if index%5==0:
            draw.rectangle((px-2,y-9,px,y-7),fill=FOREST['flower'])
    for index in range(3):
        _vine(draw,left+width*(index+1)//4,y+4,depth+6+index*2,seed+index,t)

def _forest_world(width,height,t=0):
    """Half-resolution scenery enlarged with nearest-neighbor pixels."""
    scene=Image.new('RGB',(width,height),FOREST['night']); d=ImageDraw.Draw(scene)
    for y in range(height):
        fraction=y/max(1,height-1)
        d.line((0,y,width,y),fill=(8+round(4*fraction),20+round(17*fraction),29+round(13*fraction)))
    moon=(round(width*.82),round(height*.25)); radius=max(10,min(29,height//5))
    for extra,color in ((10,'#132b35'),(5,'#19363e'),(0,'#658989')):
        r=radius+extra
        d.ellipse((moon[0]-r,moon[1]-r,moon[0]+r,moon[1]+r),fill=color)
    d.ellipse((moon[0]-radius+5,moon[1]-radius+3,moon[0]+radius-3,moon[1]+radius-4),fill='#92aaa0')
    horizon=round(height*.81)
    for layer,color in ((0,'#15313a'),(1,'#143c3e'),(2,'#17433d')):
        points=[(0,height)]
        for x in range(-20,width+40,20):
            y=horizon+layer*12+round(math.sin(x/59+layer)*9)
            points.append((x,y))
        points.append((width,height)); d.polygon(points,fill=color)
    for index in range(width//24+1):
        x=index*25+(index%3)*3
        _tree(d,x,horizon+18,35+(index*17)%54,index,FOREST['far'])
    return scene

def _forest_frame(scene,t=0):
    d=ImageDraw.Draw(scene); width,height=scene.size
    for x in range(-10,width+25,27):
        _foliage(d,x,1,22,200+x)
    for side in (0,width-1):
        d.rectangle((side-5,0,side+5,height),fill=FOREST['bark'])
        for y in range(25,height,38):
            _foliage(d,side,y,13,y+side)
    for x,length in ((19,57),(48,31),(width-24,73),(width-58,39),(width//2+18,24)):
        _vine(d,x,12,length,x,t)
    for x in range(-10,width+20,23):
        _foliage(d,x,height+2,17,500+x)
    return scene

def _fireflies(scene,t=0,quiet_left=False):
    d=ImageDraw.Draw(scene); width,height=scene.size
    for index in range(19):
        x=(index*71+37)%width; y=(index*43+31)%height
        if quiet_left and x<width*.52 and 28<y<height-22:
            continue
        phase=t*math.tau/4+index*.9
        x+=round(3*math.sin(phase)); y+=round(2*math.cos(phase))
        if math.sin(phase)>.15:
            d.rectangle((x-2,y-2,x+2,y+2),fill='#304936')
            d.rectangle((x,y,x+1,y+1),fill=FOREST['glow'])
    for index in range(5):
        phase=t*math.tau/4+index*1.4
        x=round(width*.54)+index*37+round(3*math.sin(phase))
        y=29+index*37+round(4*math.cos(phase))
        if y<height-18:
            _leaf(d,x,y,FOREST['moss'],index%2)
    if quiet_left:
        for index,(x,y) in enumerate(((286,57),(296,186),(522,129),(284,247),(451,37))):
            phase=t*math.tau/4+index*1.1
            x+=round(2*math.sin(phase)); y+=round(2*math.cos(phase))
            d.rectangle((x-2,y-2,x+2,y+2),fill='#304936')
            d.rectangle((x,y,x+1,y+1),fill=FOREST['glow'] if math.sin(phase)>-.3 else '#8b9a68')

def forest_corners(image):
    """Decorate only the outer 16 pixels; content and status colors stay intact."""
    d=ImageDraw.Draw(image); width,height=image.size
    for x,flip in ((3,False),(width-10,True)):
        d.line((x+3,3,x+3,49),fill=FOREST['leaf'])
        for y in (5,20,35):
            _leaf(d,x,y,FOREST['moss'] if y==20 else FOREST['leaf'],flip)
        for offset in (3,15,27):
            px=offset if not flip else width-offset-7
            _leaf(d,px,3,FOREST['leaf'],flip)
            _leaf(d,px,height-8,FOREST['moss'] if offset==15 else FOREST['leaf'],not flip)
    return image

def forest_banner(height=144):
    """A static, text-free forest panorama for documentation chapter openings."""
    scene=_forest_world(540,height//2); d=ImageDraw.Draw(scene)
    for x,y,width,depth,seed in ((98,height//3,94,14,12),(292,height//3+10,76,12,23),
                                 (459,height//3-5,108,18,34)):
        _island(d,x,y,width,depth,seed)
        _tree(d,x-12,y-4,28,seed,FOREST['leaf'])
    _forest_frame(scene); _fireflies(scene)
    return scene.resize((1080,height),Image.Resampling.NEAREST)

def forest_divider():
    return forest_banner(88)

def hero(t=0):
    scene=_forest_world(540,270,t); world=ImageDraw.Draw(scene)
    _island(world,292,160,51,24,13,t)
    _tree(world,291,155,29,13,FOREST['moss'])
    _island(world,503,92,67,27,24,t)
    _tree(world,502,87,35,24,FOREST['leaf'])
    _island(world,409,244,223,37,35,t)
    _forest_frame(scene,t); _fireflies(scene,t,quiet_left=True)
    out=scene.resize((1080,540),Image.Resampling.NEAREST)
    veil=Image.new('RGBA',out.size,(0,0,0,0)); v=ImageDraw.Draw(veil)
    v.rectangle((36,48,572,478),fill=(6,15,25,225))
    out=Image.alpha_composite(out.convert('RGBA'),veil).convert('RGB'); d=ImageDraw.Draw(out)
    d.line((35,49,35,477),fill='#356453',width=2)
    d.line((36,478,572,478),fill='#274c45',width=2)
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
    illustration=device(screen,transparent=True)
    out.paste(illustration,(610,78),illustration)
    text(out,817,509,'ORIGINAL RENDER / DEVICE ILLUSTRATION','#91b8a7',1,True)
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
        d.line((x+325,y+307,x+311,y+288),fill=FOREST['leaf'],width=2)
        _leaf(d,x+305,y+293,FOREST['moss'],scale=2)
        _leaf(d,x+315,y+287,FOREST['leaf'],True,scale=2)
    footer=105+rows*330
    d.line((24,footer,1055,footer),fill=LINE,width=2)
    text(out,26,footer+20,f'{len(names):02} CARTRIDGES / ONE RENDERING API',PINK,2)
    text(out,26,footer+48,'RENDER / HANDLE / NEXT_DELAY / OPTIONAL DATA SOURCES',MUTED,2)
    return forest_corners(out)

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
    return forest_corners(out)

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
    return forest_corners(out)

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
    return forest_corners(out)

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
    forest_divider().save(OUT/'forest-divider.png')
    forest_banner().save(OUT/'forest-banner.png')
    device(specimen('orbit').render(1)).save(OUT/'device-orbit.png')
    print('Generated original gallery assets.')
