"""Original 5x7 pixel lettering and a deliberately tiny drawing vocabulary."""
from PIL import Image, ImageDraw

INK = "#080d19"
PANEL = "#101b2f"
LINE = "#253554"
WHITE = "#e5f5ff"
CYAN = "#54edff"
PINK = "#ff73bc"
MINT = "#9affb3"
MUTED = "#7088ae"
GOLD = "#ffc875"
GLYPHS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", [
 [14,17,17,31,17,17,17],[30,17,17,30,17,17,30],[14,17,16,16,16,17,14],
 [30,17,17,17,17,17,30],[31,16,16,30,16,16,31],[31,16,16,30,16,16,16],
 [14,17,16,23,17,17,15],[17,17,17,31,17,17,17],[31,4,4,4,4,4,31],
 [7,2,2,2,18,18,12],[17,18,20,24,20,18,17],[16,16,16,16,16,16,31],
 [17,27,21,21,17,17,17],[17,25,21,19,17,17,17],[14,17,17,17,17,17,14],
 [30,17,17,30,16,16,16],[14,17,17,17,21,18,13],[30,17,17,30,20,18,17],
 [15,16,16,14,1,1,30],[31,4,4,4,4,4,4],[17,17,17,17,17,17,14],
 [17,17,17,17,17,10,4],[17,17,17,21,21,21,10],[17,17,10,4,10,17,17],
 [17,17,10,4,4,4,4],[31,1,2,4,8,16,31],
 [14,17,19,21,25,17,14],[4,12,4,4,4,4,14],[14,17,1,2,4,8,31],
 [30,1,1,14,1,1,30],[2,6,10,18,31,2,2],[31,16,16,30,1,1,30],
 [14,16,16,30,17,17,14],[31,1,2,4,8,8,8],[14,17,17,14,17,17,14],[14,17,17,15,1,1,14]
]))
GLYPHS.update({" ":[0]*7, ":":[0,4,4,0,4,4,0], ".":[0,0,0,0,0,6,6],
 "-": [0,0,0,31,0,0,0], "/":[1,2,2,4,8,8,16], "+":[0,4,4,31,4,4,0],
 "%":[17,18,2,4,8,9,17], "!": [4,4,4,4,4,0,4], "?": [14,17,1,2,4,0,4],
 "<":[2,4,8,16,8,4,2], ">":[8,4,2,1,2,4,8], "=": [0,0,31,0,31,0,0],
 "[": [14,8,8,8,8,8,14], "]":[14,2,2,2,2,2,14], "_": [0,0,0,0,0,0,31], ",":[0,0,0,0,0,4,8]})

class Canvas:
    def __init__(self, color=INK):
        self.image = Image.new("RGB", (160, 128), color)
        self.d = ImageDraw.Draw(self.image)

    def text(self, x, y, value, color=WHITE, size=1, center=False):
        value = str(value).upper()
        if center:
            x -= (len(value)*6-1)*size//2
        for char in value:
            for row, bits in enumerate(GLYPHS.get(char, GLYPHS["?"])):
                for col in range(5):
                    if bits & (1 << (4-col)):
                        self.d.rectangle((x+col*size, y+row*size, x+(col+1)*size-1, y+(row+1)*size-1), fill=color)
            x += 6*size

    def header(self, title, code, color=CYAN):
        self.d.rectangle((0, 0, 159, 20), fill=PANEL)
        self.d.rectangle((5, 6, 7, 12), fill=color)
        self.text(12, 6, title, color)
        self.text(136, 6, code, MUTED)
        self.d.line((0, 20, 159, 20), fill=LINE)

    def footer(self, value, color=MUTED):
        self.d.rectangle((0, 115, 159, 127), fill=INK)
        self.d.line((5, 114, 154, 114), fill=LINE)
        self.text(80, 119, value, color, center=True)

    def heart(self, x, y, color=PINK, size=1):
        for row, bits in enumerate([10,31,31,14,4]):
            for col in range(5):
                if bits & (1 << (4-col)):
                    self.d.rectangle((x+col*size,y+row*size,x+(col+1)*size-1,y+(row+1)*size-1),fill=color)

    def grid(self):
        for x in range(0,160,10): self.d.line((x,21,x,113),fill="#111b2d")
        for y in range(24,114,10): self.d.line((0,y,159,y),fill="#111b2d")
