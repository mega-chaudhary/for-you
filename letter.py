"""
letter.py  -  "For You"

An ASCII-art love letter that plays out in a tkinter window:
  1. a cream envelope with FOR YOU and a red wax-seal heart fades in
  2. it waits - your mouse / finger is a little purple flame;
     move it onto the beating heart and touch (click) it
  3. the wax seal catches fire and the paper burns away from it: a ragged
     glowing edge, scorch marks, charred curls, real flickering flames,
     embers, smoke and ash
  4. through the holes a red rose bud grows and opens
  5. stem and leaves appear, then blue light rays fan out

Run:   python letter.py
Move the purple flame (your mouse) onto the heart and click / touch it to open.
R = replay      Esc = quit

Only the Python standard library is used (tkinter ships with Python).
If something goes wrong, the error is written to letter_error.txt.
"""

import math
import os
import random
import sys
import time
import traceback
from functools import lru_cache

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
TITLE = "For You"
ENVELOPE_TEXT = "FOR YOU"     # letters drawn on the envelope (F O R Y U and space supported, see FONT)
COLS, ROWS = 104, 52          # character grid
ASP = 2.0                     # a character cell is ~2x taller than wide
FPS = 30
SEED = 7

# Timeline in seconds after the window opens
T_APPEAR0, T_APPEAR1 = 0.2, 1.0      # envelope fades in, then waits for your touch
T_COMET1, T_COMET2 = 2.0, 2.6         # internal: the story resumes at T_COMET2 when the seal is touched
T_BURST = 2.75                       # the seal catches fire
BURN_SPEED = 26.0                    # how fast the burning edge spreads (cells per second, roughly)
T_ROSE = 4.4                         # rose bud appears and opens
T_LEAVES = 5.3                       # stem and leaves appear (seen through the burnt holes)
T_RAYS = 6.8                         # light rays fan out
PROMPT = "touch the heart to open"

D2R = math.pi / 180.0
TAU = 2 * math.pi


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def clamp(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def smooth(a, b, x):
    t = clamp((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def mix(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t,
            c1[1] + (c2[1] - c1[1]) * t,
            c1[2] + (c2[2] - c1[2]) * t)


def scale(c, s):
    return (c[0] * s, c[1] * s, c[2] * s)


def gradient(stops, x):
    x = clamp(x)
    for j in range(len(stops) - 1):
        a, ca = stops[j]
        b, cb = stops[j + 1]
        if x <= b:
            return mix(ca, cb, (x - a) / (b - a))
    return stops[-1][1]


@lru_cache(maxsize=1 << 16)
def _hex(r, g, b):
    return "#%02x%02x%02x" % (r, g, b)


def to_hex(c):
    # quantised so the window only redraws cells whose colour really changed
    return _hex(int(clamp(c[0], 0, 255)) & 0xF8,
                int(clamp(c[1], 0, 255)) & 0xF8,
                int(clamp(c[2], 0, 255)) & 0xF8)


def hash01(i):
    i = (i * 2654435761) & 0xFFFFFFFF
    i ^= i >> 15
    i = (i * 2246822519) & 0xFFFFFFFF
    i ^= i >> 13
    return (i & 0xFFFF) / 65535.0


HEAT = [gradient([(0.0, (40, 0, 0)), (0.3, (170, 25, 10)), (0.55, (250, 100, 20)),
                  (0.78, (255, 200, 90)), (1.0, (255, 250, 230))], i / 63) for i in range(64)]

FLAME_CH = " .'^:*;%#@"          # flame characters, cool -> hot
FLAME = [gradient([(0.0, (110, 14, 0)), (0.25, (215, 45, 5)), (0.5, (255, 115, 15)),
                   (0.75, (255, 195, 60)), (1.0, (255, 250, 215))], i / 63) for i in range(64)]
EMBER = [gradient([(0.0, (255, 205, 90)), (0.35, (255, 120, 20)), (0.7, (215, 42, 10)),
                   (1.0, (105, 18, 8))], i / 63) for i in range(64)]


def vnoise(x, y):
    """Smooth value noise in [0, 1]."""
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)

    def h(a, b):
        return hash01((a * 7919 + b * 104729 + 1013) & 0xFFFFFFFF)
    top = h(xi, yi) + (h(xi + 1, yi) - h(xi, yi)) * u
    bot = h(xi, yi + 1) + (h(xi + 1, yi + 1) - h(xi, yi + 1)) * u
    return top + (bot - top) * v


def fbm(x, y):
    return 0.6 * vnoise(x, y) + 0.3 * vnoise(2 * x + 5.2, 2 * y + 1.3) + 0.1 * vnoise(4 * x + 9.1, 4 * y + 7.7)


FONT = {  # 5 x 6 block letters
    "F": ["#####", "#....", "####.", "#....", "#....", "#...."],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", ".###."],
    "R": ["####.", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "L": ["#....", "#....", "#....", "#....", "#....", "#####"],
    "V": ["#...#", "#...#", "#...#", ".#.#.", ".#.#.", "..#.."],
    "E": ["#####", "#....", "####.", "#....", "#....", "#####"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "#####"],
    " ": ["...", "...", "...", "...", "...", "..."],
}


def seg_dist(px, py, ax, ay, bx, by):
    """Distance from a cell to a segment, in aspect-corrected units."""
    ay *= ASP; by *= ASP; py *= ASP
    dx, dy = bx - ax, by - ay
    t = clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))
    return math.hypot(px - ax - dx * t, py - ay - dy * t)


# The rose, traced from a photo into characters. ROSE_ART holds the characters,
# ROSE_TINT the colour of each one (same layout).
ROSE_ORIGIN = (2, 26)   # (row, col) of the top-left of the art
ROSE_ART = [
    "                               .                     ",
    "                            -::::                    ",
    "           ..-==*8    &+%%&%*88&*8     :...          ",
    "           .:=++*%%8&&8$$@$$$$@$88&&+=:::..          ",
    "           .:*888$%$$&&%%*+==+&8$$$$$8%==-.          ",
    "          ..:&$&%-$$88$$$$$8+=*%&8$$@@@8*-:          ",
    "          ..-8@&$+@$8%&@$&%8$@8*&$@@$8$$88+          ",
    "...:-+*%::::+$&$&$$8+:*@%+=-=%@@**8@@$$$=+%&%*       ",
    "....:-+%-=--%=*$&$$%-:*@*$*==+%@8-+**$@@&+=**=       ",
    "  ..+%&&-+*=&:%$8$@=%*:-%8$=++*@$:-*=%@$$8$8%&%      ",
    "  ..-&$8-=8+*=8$@$$$&88=+&8*++*%+:-*&@@$+=%$$&%+%    ",
    "   ..*@&:-&&---=8@$$+$%%8$+====&--*$@@@%-=%$88&=++=  ",
    "    .:8%--+8%--::&@@*:%$%-*$@@$&%$$8$@@*-+8$$@%+==:..",
    "     .===-=$@$+::%@@@@%-=$88%8888%*8$@8==&$$$$%*%-:. ",
    "     ..:===&$@@+:-*&$@@@*=:=8$@@@8%%+=*$$$8$$&%*-:   ",
    "      ..-++%&$@@&-:::-%$@@@$$&&8$@@@$$&%*%$8*-.:     ",
    "       ..---=+*&@@$+----:::-+*+-::+&&&&%*+:-:.:      ",
    "        ....::--=*8@$8**8$@@@@@@@$@@@$$$$&+=-        ",
    "           ....::--+$$@8=-=+%&$@@%++==::-==          ",
    "              ....::=*%8&---:::=:-==+****=:          ",
    "                 ..:=%$$$$%**%88$88888&*==           ",
    "                    ..:=+&&&&&&++++***++--           ",
    "                       ..:=-:::..&&&######&&         ",
    "                       &x.::     &##&#########&&     ",
    "                        xx&&   &&       &&&&&%&&&    ",
    "                   &&&&&%x%  &.##&&                  ",
    "                  &  &&%%x%&&  &%%&&                 ",
    "                   &&  &%x%%    &%%&#&               ",
    "                 &%%  &xxx%&      &%&%               ",
    "               &%xx   xxxxxx&       &                ",
    "              &%%x&   x%%%xxx&                       ",
    "       &&&&&&&&%%%&%%%%%%%xx%%&                      ",
    "    &%xx%x&     &%%%xx%%%%xxx%%        &&%%%&        ",
    "   xxxxxx%      %xxxxxxx%%%xxx%     &%%%%xxx&        ",
    "  %xxxxx%&      &xxxxxxxx%%xxx%   &%%%%%%%x%%        ",
    " &xxxxx%&        &%xxxxxxxxxx%&   %%%x%%%x%%%        ",
    " %xxxx%             &%%xxxxxx&   %%x%%%%%%%%&        ",
    " xxxxx                 &x%&x%    %%%%%%&%%%&         ",
    " xxxx&                 &x%%%%&&&%&&%%&#&&&           ",
    "&xxx&                &%%xxx%%%%&                     ",
    "&xx&              &%%xxx%xxxx%&                      ",
    "&x&             &%xxxxxxxxxx%&                       ",
    "&               xxxxxxxxxxx%                         ",
    "               &xxxxxxxxx%&                          ",
    "               &&&&&&&& |||                          ",
    "                        ||                           ",
    "                        ||                           ",
    "                       |||                           ",
    "                       |||                           ",
    "                       |||                           ",
]
ROSE_TINT = [   # a-p: petal red (dark->light), A-P: leaf green (dark->light), S: stem
    "                               c                     ",
    "                            gffef                    ",
    "           ccghijm    ljkklkkmmljm     eccc          ",
    "           cehiijkkmllmoopppnopnmmlmjhgeeec          ",
    "           cejmmmnknollkkjihhilmnonnnmkihgd          ",
    "          ccflolkhoommnnnoomihjklmnopppmjhf          ",
    "          cegmpmnipomklpollmppmjloppnmnnmmj          ",
    "cccfgijkfgefjnlolnomiejpkihghkppjjmppooohiklkj       ",
    "cccdfhjkghghlijnlookgfjpjojihikpmgikjnpplihjjh       ",
    "  cdikllgijhlgknmophkjggkmohiijpnggjikponmnmklk      ",
    "  ccglomghmijhmopnoolnmhilnjijkkiggjlppoiilonlkjl    ",
    "   cdjplgglmhhghmponioklmniihhhlggknpppkghkonmlhiih  ",
    "    cfmkggimkhgfglppjglokhjnppolknnmoppkgimonpkihhfdc",
    "     cihighnpojgfkppppkghnmmkmmmmljmopmiilooookjkgec ",
    "     cdfiihlnppifgjmopppjhfhmnpppmlkihknoomoolkjgf   ",
    "      cdgiiklnpplhfffgkopppoomlmoppponlkkknmkhef     ",
    "       cdggghijmppoighggfffhijigfgillllljiggfeg      ",
    "        ccceffgghjmpomjjmppppppppopppooonljig        ",
    "           cccefgggjnopmhghiklnppkjiihgfghh          ",
    "              ccceefhjkmlggggfghgghijjjjjhf          ",
    "                 ccehknoonkjjkmmnmmmmmljhh           ",
    "                    cdeiilmlllliiiijkjiihh           ",
    "                       ccehgffedeKPPNMNPPPPP         ",
    "                       GEceg     MMNMMOPOPPPPPPP     ",
    "                        EEHO   JJ       GGKMJHHJK    ",
    "                   IJKKLFEG  JdONPP                  ",
    "                  H  NMIGEFIK  IIILL                 ",
    "                   IK  GFFFI    HIHKMK               ",
    "                 JGI  GFFEFH      HGJI               ",
    "               KHFF   FFFEFFG       G                ",
    "              IFFFG   EFGFFFFG                       ",
    "       GHJKJIIGFFIGFFFFGHGFFFFG                      ",
    "    FFEFFFH     GFGFEFFGHGFFFGH        JJHFFG        ",
    "   FEEEEFF      FFEEEEFFFGFFFFG     HHGHGFFFG        ",
    "  FEEEEFGH      GFEEEEFFFFFFFFG   IGFFFGFFFFF        ",
    " GEEEEFFJ        GFFEFEEFFFFFFH   FFFFFGFFFFG        ",
    " FEEEEF             GFFEEFFFFG   GFFFGGFFFFFG        ",
    " FEEEE                 FEGFFF    FGGHGHIHGFG         ",
    " EEEEF                 GFFFFFGHIIIIIHKMMHG           ",
    "HEFEF                HGFFFFFFFFI                     ",
    "FEEF              GGFEEFFFFFFFG                      ",
    "FFG             GFFFFFFFFFFFFG                       ",
    "I               FFFFFFFFEFFF                         ",
    "               GFFFFFFFFFFG                          ",
    "               GFFFFFGG SSS                          ",
    "                        SS                           ",
    "                        SS                           ",
    "                       SSS                           ",
    "                       SSS                           ",
    "                       SSS                           ",
]


def rose_tint(code):
    if code == "S":                                   # stem
        return (150, 70, 80)
    if code.islower():                                # petals: dark red -> red -> pink
        k = (ord(code) - 97) / 15.0
        if k < 0.7:
            return mix((120, 6, 22), (225, 30, 45), k / 0.7)
        return mix((225, 30, 45), (255, 150, 160), (k - 0.7) / 0.3)
    k = (ord(code) - 65) / 15.0                       # leaves: dark -> light green
    return mix((25, 85, 45), (150, 220, 150), k)


def ease_out_back(x):
    c1 = 1.4
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


# --------------------------------------------------------------------------
# Scene (pure Python - no GUI code in here)
# --------------------------------------------------------------------------
class Scene:
    def __init__(self, seed=SEED):
        self.N = COLS * ROWS
        self.rng = random.Random(seed)
        # envelope layout (cells)
        self.ex0, self.ex1, self.ey0, self.ey1 = 10, 93, 14, 44
        self.ecx = (self.ex0 + self.ex1) / 2.0
        self.tip_r = 30.0                        # flap tip row
        self.bot_r = 33.0                        # where the bottom folds meet
        self.hcx, self.hcy = self.ecx, 28.5      # wax-seal heart sits on the flap tip
        self._load_rose()                        # sets the rose head centre self.rx / self.ry
        self._build_envelope()
        self._build_rays()
        self._build_stars()
        # random tables for the flame simulation
        self.rnd_dx = [self.rng.choice((-1, 0, 0, 1)) for _ in range(4096)]
        self.rnd_decay = [0.03 + self.rng.random() * 0.17 for _ in range(4096)]
        self.reset()

    def reset(self):
        self.parts = []      # [x, y, vx, vy, life, max_life, kind]
        self.ignited = False
        self.heat = [0.0] * self.N
        self.fire_acc = 0.0
        self.rnd_i = 0
        self.spawn_acc = [0.0, 0.0, 0.0]
        self.opened_at = None        # real time the letter was touched open
        self.clock = 0.0             # real time since start (for idle effects)
        self.cursor = None           # (col, row) of the mouse / finger
        self.touch_at = None

    # The envelope fades in, then waits. Touching the heart calls open() and the
    # story jumps to: seal flares -> paper ignites at the seal -> burns away -> rose.
    def open(self, real_t):
        if self.opened_at is None:
            self.opened_at = max(real_t, T_APPEAR1)
            self.touch_at = self.cursor

    def story_time(self, real_t):
        if self.opened_at is None or real_t < self.opened_at:
            return min(real_t, T_APPEAR1)
        return T_COMET2 + (real_t - self.opened_at)

    def waiting(self, real_t):
        return self.opened_at is None and real_t >= T_APPEAR1 - 0.3

    def on_heart(self, c, r):
        hx = (c - self.hcx) / 11.5
        hy = -(r - self.hcy) / 6.2 + 0.2
        return (hx * hx + hy * hy - 1) ** 3 - hx * hx * hy ** 3 <= 0

    def set_cursor(self, cell):
        """cell = (col, row) of the mouse / finger, or None when it leaves the window."""
        self.cursor = cell

    def finished(self, real_t):
        return self.story_time(real_t) > T_RAYS + 2.0

    # ------------------------------------------------------------ envelope
    def _build_envelope(self):
        rng = self.rng
        ex0, ex1, ey0, ey1 = self.ex0, self.ex1, self.ey0, self.ey1
        cx, tip_r, bot_r = self.ecx, self.tip_r, self.bot_r
        half = cx - ex0

        # ink letters
        ink = set()
        glyphs = [FONT.get(ch.upper(), FONT[" "]) for ch in ENVELOPE_TEXT]
        widths = [len(g[0]) * 2 for g in glyphs]
        total = sum(widths) + 2 * (len(glyphs) - 1)
        c0 = int(round(cx - total / 2.0)) + 1
        r0 = 36 if ROWS > 40 else 30
        for g, w in zip(glyphs, widths):
            for gy, line in enumerate(g):
                for gx, px in enumerate(line):
                    if px == "#":
                        ink.add((r0 + gy, c0 + gx * 2))
                        ink.add((r0 + gy, c0 + gx * 2 + 1))
            c0 += w + 2

        folds = [((ex0 + 1, ey0 + 1), (cx, tip_r), "\\"),       # flap, left
                 ((ex1 - 1, ey0 + 1), (cx, tip_r), "/"),        # flap, right
                 ((ex0 + 1, ey1 - 1), (cx, bot_r), "/"),        # bottom fold, left
                 ((ex1 - 1, ey1 - 1), (cx, bot_r), "\\")]       # bottom fold, right

        PAPER = (242, 214, 168)
        self.env = []   # (idx, c, r, ch, rgb, kind, t_appear, t_burn, hash)

        def add(c, r, ch, col, kind):
            i = r * COLS + c
            h = hash01(i + 911)
            t_app = T_APPEAR0 + rng.random() * (T_APPEAR1 - T_APPEAR0 - 0.3)
            # burn front: spreads out from the seal, ragged, faster upwards
            d = math.hypot(c - self.hcx, (r - self.hcy) * ASP)
            ragged = fbm(c * 0.09, r * 0.18) * 0.9 + fbm(c * 0.3 + 40, r * 0.6) * 0.25
            t_burn = T_BURST + 0.1 + d / BURN_SPEED * (0.7 + ragged)
            t_burn -= max(0.0, self.hcy - r) * ASP * 0.010
            self.env.append((i, c, r, ch, col, kind, t_app, t_burn, h))

        for r in range(ey0, ey1 + 2):
            for c in range(ex0, ex1 + 2):
                # drop shadow (one cell right and below)
                if r == ey1 + 1 or c == ex1 + 1:
                    if r > ey0 and c > ex0:
                        add(c, r, ".", (55, 42, 34), "shadow")
                    continue
                k = 1 - abs(c - cx) / half
                flap_y = ey0 + (tip_r - ey0) * k
                bot_y = ey1 - (ey1 - bot_r) * k
                hx = (c - self.hcx) / 9.5
                hy = -(r - self.hcy) / 5.0 + 0.2
                heart = (hx * hx + hy * hy - 1) ** 3 - hx * hx * hy ** 3
                if heart <= 0:
                    # wax seal: highlight top-left, darker rim
                    rim = heart > -0.12
                    lit = (-hx - hy) > 0.5
                    col = (150, 12, 28) if rim else (255, 110, 125) if lit else (200, 22, 40)
                    add(c, r, "@" if rim else rng.choice("##@"), col, "seal")
                    continue
                if (r == ey0 or r == ey1) and ex0 <= c <= ex1:
                    ch = "." if c in (ex0, ex1) and r == ey0 else "'" if c in (ex0, ex1) else "-"
                    add(c, r, ch, (205, 165, 115), "edge")
                    continue
                if c in (ex0, ex1):
                    add(c, r, "|", (205, 165, 115), "edge")
                    continue
                fold = None
                for a, b, fch in folds:
                    if seg_dist(c, r, a[0], a[1], b[0], b[1]) < 0.62:
                        fold = fch
                        break
                if fold:
                    add(c, r, fold, (140, 92, 55), "fold")
                    continue
                if r < flap_y:
                    panel, shade, chars = "flap", 1.0 - 0.10 * (r - ey0) / (tip_r - ey0), "&&8&&8&"
                elif r > bot_y:
                    panel, shade, chars = "bottom", 0.78 - 0.08 * (r - bot_y) / (ey1 - bot_r), "&#&&#&8"
                else:
                    panel, shade, chars = "side", 0.86, "%&%%&%8"
                # shadow cast by the flap just under its edge
                if panel == "side" and r - flap_y < 1.6:
                    shade *= 0.72
                grain = 0.94 + 0.06 * fbm(c * 0.5, r * 0.9)
                col = scale(PAPER, shade * grain)
                if (r, c) in ink:
                    add(c, r, rng.choice("##@"), (70, 22, 18), "ink")
                else:
                    add(c, r, rng.choice(chars), col, panel)

    # ------------------------------------------------------------ rose, rays, stars
    def _load_rose(self):
        r0, c0 = ROSE_ORIGIN
        petals = []
        self.rose = []      # stem + leaves: (idx, ch, rgb, delay, is_green)
        for i, (line, tl) in enumerate(zip(ROSE_ART, ROSE_TINT)):
            for j, (ch, code) in enumerate(zip(line, tl)):
                r, c = r0 + i, c0 + j
                if ch == " " or not (0 <= r < ROWS and 0 <= c < COLS):
                    continue
                if code.islower():
                    petals.append((c, r, ch, rose_tint(code)))
                else:
                    self.rose.append((r * COLS + c, ch, rose_tint(code), 0.0, True))
        cs = [q[0] for q in petals]
        rs = [q[1] for q in petals]
        self.rx = int(round((min(cs) + max(cs)) / 2.0))
        self.ry = int(round((min(rs) + max(rs)) / 2.0))
        self.rose_R = (max(cs) - min(cs)) / 2.0
        self.head = {(c - self.rx, r - self.ry): (ch, col) for c, r, ch, col in petals}
        self.head_dc = (min(cs) - self.rx, max(cs) - self.rx)
        self.head_dr = (min(rs) - self.ry, max(rs) - self.ry)

    def _build_rays(self):
        cx, cy = self.rx, self.ry
        specs = [(-90, 4, 60, 1.0), (-62, 6, 75, 0.9), (-118, 6, 75, 0.9),
                 (-38, 7, 85, 0.85), (-142, 7, 85, 0.85), (-18, 5, 90, 0.7),
                 (-162, 5, 90, 0.7), (-3, 2.2, 105, 1.0), (177, 2.2, 105, 1.0),
                 (18, 5, 80, 0.5), (162, 5, 80, 0.5), (45, 6, 70, 0.4), (135, 6, 70, 0.4)]
        self.ray_specs = specs
        self.rho0 = self.rose_R * 0.92
        self.rays = []      # (idx, rho, k, axis, h)
        for r in range(ROWS):
            for c in range(COLS):
                X, Y = c - cx, (r - cy) * ASP
                rho = math.hypot(X, Y)
                if rho < self.rho0:
                    continue
                th = math.atan2(Y, X) / D2R
                for k, (a, hw, L, s) in enumerate(specs):
                    d = abs((th - a + 180) % 360 - 180)
                    if d >= hw or rho > L:
                        continue
                    axis = rho * d * D2R < 0.75
                    h = hash01(r * COLS + c + 31)
                    fall = 1 - (rho - self.rho0) / (L - self.rho0)
                    if axis or h < 0.06 + 0.34 * fall:
                        self.rays.append((r * COLS + c, rho, k, axis, h))
                    break

    def _build_stars(self):
        rng = self.rng
        self.stars = [(rng.randrange(self.N), rng.uniform(1.5, 4.0), rng.uniform(0, TAU))
                      for _ in range(80)]


    # ------------------------------------------------------------ particles helper
    def _emit(self, x, y, vx, vy, life, kind):
        self.parts.append([x, y, vx, vy, life, life, kind])



    # ------------------------------------------------------------ finger / cursor
    def comet_pos(self, t):
        """Where to draw the purple flame that marks your finger / mouse."""
        if self.opened_at is None:
            return self.cursor if t >= T_APPEAR1 - 0.3 else None
        if t < T_BURST:
            return self.touch_at       # stays where you touched while the seal flares
        return None

    # ------------------------------------------------------------ fire simulation
    def _step_flames(self, sources):
        """Classic cellular fire: heat rises one row per step, drifting and cooling."""
        heat = self.heat
        dxs, decs = self.rnd_dx, self.rnd_decay
        n = self.rnd_i
        c_lo, c_hi = max(1, self.ex0 - 6), min(COLS - 2, self.ex1 + 6)
        for r in range(0, self.ey1 + 2):
            base = r * COLS
            below = base + COLS
            for c in range(c_lo, c_hi + 1):
                n = (n + 1) & 4095
                v = heat[below + c + dxs[n]] - decs[n]
                heat[base + c] = v if v > 0 else 0.0
        self.rnd_i = n
        bottom = (self.ey1 + 2) * COLS
        for c in range(c_lo, c_hi + 1):
            heat[bottom + c] = 0.0
        rng = self.rng
        for i in sources:                      # only some cells feed the fire each step -> tongues
            if rng.random() < 0.38:
                v = 0.55 + 0.45 * rng.random()
                if v > heat[i]:
                    heat[i] = v

    # ------------------------------------------------------------ particles
    def _update_particles(self, t, dt, burning, charred):
        rng = self.rng
        if t >= T_BURST and not self.ignited:
            self.ignited = True
            for _ in range(45):        # sparks as the seal catches
                a = rng.uniform(0, TAU)
                sp = rng.uniform(6, 22)
                self._emit(self.hcx, self.hcy, math.cos(a) * sp, math.sin(a) * sp / ASP - 3,
                           rng.uniform(0.4, 1.0), 1)
        acc = self.spawn_acc
        if burning:
            acc[0] += dt * 55          # embers
            acc[1] += dt * 32          # smoke
            while acc[0] >= 1:
                acc[0] -= 1
                c, r = rng.choice(burning)
                self._emit(c, r, rng.uniform(-3, 3), rng.uniform(-13, -5), rng.uniform(0.4, 1.3), 1)
            while acc[1] >= 1:
                acc[1] -= 1
                c, r = rng.choice(burning)
                self._emit(c, r - 3, rng.uniform(-1.5, 1.5) + 0.8, rng.uniform(-6, -3),
                           rng.uniform(1.4, 2.8), 3)
        if charred:
            acc[2] += dt * 28          # ash flakes
            while acc[2] >= 1:
                acc[2] -= 1
                c, r = rng.choice(charred)
                self._emit(c, r, rng.uniform(-2, 2), rng.uniform(-5, -1.5), rng.uniform(1.0, 2.4), 4)
        cp = self.comet_pos(t)
        if cp and rng.random() < 0.5:
            self._emit(cp[0] + rng.uniform(-2, 2), cp[1] + rng.uniform(0, 9),
                       rng.uniform(-6, 6), rng.uniform(-3, 1), rng.uniform(0.2, 0.5), 2)
        alive = []
        for p in self.parts:
            p[4] -= dt
            if p[4] <= 0:
                continue
            kind = p[6]
            if kind == 1:                                   # ember: rises, wiggles
                p[2] += math.sin(t * 7 + p[1]) * 6 * dt
                p[3] -= 2.0 * dt
            elif kind == 3:                                 # smoke: slows and spreads
                p[3] *= 1 - 0.4 * dt
                p[2] += math.sin(t * 1.3 + p[1] * 0.4) * 1.5 * dt
            elif kind == 4:                                 # ash: flutters
                p[2] += math.sin(t * 3.0 + p[0] * 0.7) * 8 * dt
                p[3] += 1.2 * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            alive.append(p)
        self.parts = alive

    # ------------------------------------------------------------ frame
    def frame(self, real_t, dt):
        self.clock = real_t
        t = self.story_time(real_t)
        waiting = self.waiting(real_t)
        chars = [" "] * self.N
        cols = [None] * self.N
        tq = int(t * 12) / 12.0           # slow clock for flicker (keeps redraws light)

        def put(i, ch, rgb):
            chars[i] = ch
            cols[i] = to_hex(rgb)

        # stars
        sv = smooth(T_BURST + 1.0, T_BURST + 2.5, t)
        if sv > 0:
            for i, w, ph in self.stars:
                b = 0.5 + 0.5 * math.sin(tq * w + ph)
                put(i, "•" if b > 0.85 else ".", scale((240, 240, 255), (0.3 + 0.7 * b) * sv))

        # light rays
        if t > T_RAYS:
            grow = self.rho0 + (t - T_RAYS) * 70.0
            for i, rho, k, axis, h in self.rays:
                if rho > grow:
                    continue
                a, hw, L, s = self.ray_specs[k]
                fade = s * (1 - (rho - self.rho0) / (L - self.rho0)) ** 0.8
                tip = 1.0 + 1.5 * max(0.0, 1 - (grow - rho) / 6.0) if grow < L + 6 else 1.0
                if axis:
                    if ((rho - tq * 22 + k * 5) % 8) < 1.3:
                        put(i, "•", mix((170, 210, 255), (255, 255, 255), fade))
                    else:
                        put(i, "+" if k == 0 else "=",
                            scale(mix((50, 90, 200), (140, 190, 255), fade), min(1.6, tip)))
                else:
                    b = fade * (0.55 + 0.45 * math.sin(tq * 4 + h * 40)) * tip
                    if b < 0.08:
                        continue
                    put(i, "-" if h < 0.3 else "=", mix((20, 40, 120), (90, 150, 255), clamp(b)))

        # stem and leaves (paper still covers them until it burns away)
        if t > T_LEAVES:
            for i, ch, col, delay, green in self.rose:
                d = (i // COLS - self.ry) / ROWS * 0.6
                a = smooth(T_LEAVES + d, T_LEAVES + d + 0.5, t)
                if a < 0.08:
                    continue
                k = smooth(T_LEAVES + 0.5 + d, T_LEAVES + 1.1 + d, t)
                put(i, ch, scale(mix((255, 225, 140), col, k), a))

        # the letter, and the paper burning
        burning, charred = [], []
        if t < T_RAYS + 1.0:
            seal_glow = 1.0 if (waiting and self.cursor and self.on_heart(*self.cursor)) else 0.0
            flare = smooth(T_COMET2, T_BURST, t)
            for (i, c, r, ch, col, kind, t_app, tb, h) in self.env:
                a = smooth(t_app, t_app + 0.3, t)
                if a < 0.1:
                    continue
                cur, chh = col, ch
                if kind == "seal" and t < T_BURST + 0.2:
                    if waiting:   # heartbeat: two quick beats then rest
                        ph = (self.clock * 1.3) % 1.0
                        pulse = max(math.exp(-((ph - 0.1) / 0.06) ** 2),
                                    math.exp(-((ph - 0.32) / 0.06) ** 2))
                    else:
                        pulse = 0.0
                    cur = mix(cur, (255, 120, 150), pulse * 0.6 + seal_glow * 0.3)
                    cur = mix(cur, (255, 240, 200), flare)
                if t > T_BURST:
                    u = t - tb
                    if u >= 0.75:
                        continue                                  # burnt through
                    if u >= 0.26:                                 # charred, curling edge
                        k = (u - 0.26) / 0.49
                        if kind == "shadow":
                            continue
                        chh = "~^,.'"[min(4, int(k * 5 + h * 1.5))]
                        cur = mix((72, 42, 26), (28, 20, 16), k)
                        if hash01(i + int(t * 10) * 131) < 0.10 * (1 - k):
                            chh, cur = ".", (255, 95, 30)         # last embers
                        if h < 0.12:
                            charred.append((c, r))
                    elif u >= 0.06:                               # glowing embers
                        k = (u - 0.06) / 0.20
                        fl = hash01(i + int(t * 15) * 977)
                        cur = EMBER[int(clamp(k + 0.18 * (fl - 0.5)) * 63)]
                        chh = "&%*x#"[int(h * 5)]
                        burning.append(i)
                    elif u >= 0:                                  # the burning line itself
                        cur = (255, 246, 200) if h < 0.5 else (255, 215, 110)
                        chh = "#" if h < 0.35 else "*" if h < 0.7 else "%"
                        burning.append(i)
                    elif kind != "shadow":                        # paper browns ahead of it
                        sc = smooth(-0.9, 0.0, u)
                        if sc > 0:
                            cur = mix(cur, (150, 88, 40), sc * 0.85)
                            if sc > 0.6:
                                cur = mix(cur, (70, 30, 12), (sc - 0.6) / 0.4 * 0.8)
                put(i, chh, scale(cur, a))

        # flames rising off the burning edge
        if T_BURST < t < T_RAYS + 1.5:
            self.fire_acc += dt
            steps = 0
            while self.fire_acc >= 1.0 / 30 and steps < 3:
                self.fire_acc -= 1.0 / 30
                steps += 1
                self._step_flames(burning)
            heat = self.heat
            burning_set = set(burning)
            for r in range(0, self.ey1 + 2):
                base = r * COLS
                for c in range(max(0, self.ex0 - 6), min(COLS, self.ex1 + 7)):
                    v = heat[base + c]
                    if v > 0.1:
                        i = base + c
                        if v < 0.4 and chars[i] != " " and cols[i] is not None and i not in burning_set:
                            continue           # faint heat doesn't show over unburnt paper
                        put(i, FLAME_CH[min(9, int(v * 10))], FLAME[min(63, int(v * 60))])

        # rose: bud grows up from the stem and opens into the full bloom
        if t > T_ROSE:
            p = smooth(T_ROSE, T_ROSE + 2.2, t)
            e = ease_out_back(p)
            sx = 0.16 + 0.84 * e
            sy = 0.35 + 0.65 * e
            a = smooth(T_ROSE, T_ROSE + 0.25, t)
            glow = 1.0 + 0.3 * (1 - smooth(T_ROSE + 1.2, T_ROSE + 2.6, t))
            rx, ry = int(self.rx), int(self.ry)
            top, bot = self.head_dr
            for dr in range(top - 4, bot + 1):
                sdr = int(round(bot + (dr - bot) / sy))
                if sdr < top:
                    continue
                for dc in range(self.head_dc[0] - 5, self.head_dc[1] + 6):
                    cell = self.head.get((int(round(dc / sx)), sdr))
                    if cell is None:
                        continue
                    r, c = ry + dr, rx + dc
                    if 0 <= r < ROWS and 0 <= c < COLS:
                        put(r * COLS + c, cell[0], scale(cell[1], a * glow))

        # finger / cursor flame (pointer is at its top centre)
        cp = self.comet_pos(t)
        if cp:
            fx, fy = cp
            glow = smooth(T_COMET2, T_BURST, t)
            stops = [(0.0, (240, 110, 175)), (0.35, (165, 90, 235)),
                     (0.7, (100, 120, 255)), (1.0, (235, 235, 255))]
            for j in range(11):
                hwj = 3.6 * (1 - j / 11.0) ** 0.9 + 0.4
                r = int(round(fy)) + j
                if not 0 <= r < ROWS:
                    continue
                col = mix(gradient(stops, j / 10.0), (255, 255, 255), glow * 0.7)
                for c in range(int(math.floor(fx - hwj)), int(math.ceil(fx + hwj)) + 1):
                    if 0 <= c < COLS and abs(c - fx) <= hwj:
                        put(r * COLS + c, "=" if abs(c - fx) < hwj - 0.8 else "-", col)

        # particles: embers, smoke, ash, cursor sparkles
        self._update_particles(t, dt, [(i % COLS, i // COLS) for i in burning[::3]], charred)
        for x, y, vx, vy, life, ml, kind in self.parts:
            xi, yi = int(round(x)), int(round(y))
            if not (0 <= xi < COLS and 0 <= yi < ROWS):
                continue
            k = life / ml
            if kind == 1:
                ch = "*" if k > 0.65 else "'" if k > 0.35 else "."
                col = HEAT[int(20 + 43 * k)]
            elif kind == 3:
                if chars[yi * COLS + xi] != " ":
                    continue                     # smoke stays behind everything
                ch = "~" if k > 0.5 else "."
                col = scale((95, 92, 98), 0.25 + 0.6 * k * (1 - k) * 4 * 0.5)
            elif kind == 4:
                ch = "," if k > 0.6 else "'" if k > 0.3 else "."
                col = scale((130, 120, 112), 0.35 + 0.65 * k)
            else:
                ch = "."
                col = scale((190, 140, 255), 0.4 + 0.6 * k)
            put(yi * COLS + xi, ch, col)

        # "touch to open" prompt while the letter waits
        if waiting and PROMPT:
            k = 0.72 + 0.28 * math.sin(self.clock * 3.0)
            r = self.ey1 + 3
            c0 = (COLS - len(PROMPT)) // 2
            for j, chh in enumerate(PROMPT):
                if chh != " ":
                    put(r * COLS + c0 + j, chh, scale((255, 170, 205), k))
            for j, chh in ((-3, "<"), (-2, "3"), (len(PROMPT) + 1, "<"), (len(PROMPT) + 2, "3")):
                put(r * COLS + c0 + j, chh, scale((255, 90, 160), k))

        return chars, cols


# --------------------------------------------------------------------------
# tkinter window
# --------------------------------------------------------------------------
def main():
    import tkinter as tk
    import tkinter.font as tkfont

    if sys.platform.startswith("win"):
        try:  # crisp text on high-DPI Windows screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    root.title(TITLE)
    root.configure(bg="black")

    families = set(f.lower() for f in tkfont.families())
    family = "Courier"
    for f in ("Consolas", "Cascadia Mono", "Menlo", "Monaco", "DejaVu Sans Mono",
              "Liberation Mono", "Courier New"):
        if f.lower() in families:
            family = f
            break

    # biggest font that fits on screen
    sw = root.winfo_screenwidth() * 0.92
    sh = root.winfo_screenheight() * 0.86
    size = 14
    while True:
        font = tkfont.Font(family=family, size=-size, weight="bold")   # negative = pixels
        cw = max(1, font.measure("M"))
        ch = max(1, font.metrics("linespace"))
        if (cw * COLS <= sw and ch * ROWS <= sh) or size <= 6:
            break
        size -= 1

    canvas = tk.Canvas(root, width=cw * COLS, height=ch * ROWS, bg="black",
                       highlightthickness=0, bd=0)
    canvas.pack()

    def set_pointer(hidden):
        try:   # the purple flame replaces the mouse pointer while the letter waits
            canvas.configure(cursor="none" if hidden else "")
        except tk.TclError:
            pass
    items = [canvas.create_text(c * cw + cw // 2, r * ch + ch // 2, text="", fill="white",
                                font=font)
             for r in range(ROWS) for c in range(COLS)]

    scene = Scene()
    st = {"start": time.perf_counter(), "last": time.perf_counter(),
          "pch": [" "] * scene.N, "pcol": [None] * scene.N}

    def to_cell(e):
        return (min(COLS - 1, max(0, e.x // cw)), min(ROWS - 1, max(0, e.y // ch)))

    def replay(_=None):
        scene.reset()
        set_pointer(True)
        st["start"] = st["last"] = time.perf_counter()

    def move(e):
        scene.set_cursor(to_cell(e))

    def touch(e):
        real_t = time.perf_counter() - st["start"]
        cell = to_cell(e)
        scene.set_cursor(cell)
        if scene.finished(real_t):
            replay()
        elif scene.waiting(real_t) and scene.on_heart(*cell):
            scene.open(real_t)
            set_pointer(False)

    def key_open(_=None):
        real_t = time.perf_counter() - st["start"]
        if scene.finished(real_t):
            replay()
        elif scene.waiting(real_t):
            scene.set_cursor((int(scene.hcx), int(scene.hcy)))
            scene.open(real_t)
            set_pointer(False)

    set_pointer(True)
    root.bind("<Escape>", lambda e: root.destroy())
    canvas.bind("<Motion>", move)
    canvas.bind("<B1-Motion>", move)
    canvas.bind("<Leave>", lambda e: scene.set_cursor(None))
    canvas.bind("<Button-1>", touch)
    root.bind("<space>", key_open)
    root.bind("<Return>", key_open)
    root.bind("<KeyPress-r>", replay)
    root.bind("<KeyPress-R>", replay)

    cfg = canvas.itemconfigure

    def tick():
        now = time.perf_counter()
        dt = min(now - st["last"], 0.1)
        st["last"] = now
        t = now - st["start"]
        chars, cols = scene.frame(t, dt)
        pch, pcol = st["pch"], st["pcol"]
        for i in range(scene.N):
            c_ = chars[i]
            if c_ == " ":
                if pch[i] != " ":
                    cfg(items[i], text="")
                    pch[i] = " "
            elif c_ != pch[i] or cols[i] != pcol[i]:
                cfg(items[i], text=c_, fill=cols[i])
                pch[i], pcol[i] = c_, cols[i]
        spent = (time.perf_counter() - now) * 1000.0
        root.after(max(1, int(1000.0 / FPS - spent)), tick)

    def start():
        st["start"] = st["last"] = time.perf_counter()
        tick()

    root.after(200, start)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        print(msg, file=sys.stderr)
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "letter_error.txt"), "w") as fh:
                fh.write(msg)
        except Exception:
            pass
        try:
            input("\nSomething went wrong (details saved to letter_error.txt). Press Enter to close...")
        except Exception:
            pass
