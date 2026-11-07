"""Alternative screen layouts for the Multiple Choice video (mcq.layout).

    Standard     the classic cards (engine/templates/mcq.py draws it; nothing here)
    Exam paper   a ruled exam sheet on a wooden desk: questions printed on the sheet, a red pen circles the right
                 answer, crosses the others and writes the explanation; "Excellent!" stamp on the last question;
                 each question is a new sheet sliding in
    Islamic      emerald and gold: 8-fold star pattern, ornamental frame, pointed-arch (mihrab) question card,
                 star medallions for the letters, gold light sweep on the right answer

A layout draws the background and the question (timer included); mcq.py adds the overlays shared by all layouts
(difficulty badge, confetti, "Final question" ribbon, wipe, title, ending).
Everything depends only on the time it is given (frames are rendered on several processes)."""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import H, W, clamp, ease_out_back, paste, prog, shade, text_img, wrap
from .timers import draw_timer

LAYOUT_NAMES = ["Standard", "Exam paper", "Islamic"]
SS = 2
RED_TIMER = (255, 90, 90)


# ---------------------------------------------------------------- helpers
def eo(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def trim(im):
    """Cut the empty side margins of a text image (keeps its height)."""
    box = im.getchannel("A").getbbox()
    return im.crop((box[0], 0, box[2], im.height)) if box else im


def T(txt, size, col, weight="Black", max_w=None, shadow=False):
    return trim(text_img(txt, size, col, weight, shadow=shadow, max_w=max_w))


def vgrad(w, h, top, bot):
    t = np.linspace(0, 1, max(1, h), dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t
    return Image.fromarray(np.repeat(arr, max(1, w), axis=1).astype(np.uint8), "RGB")


def colorize(alpha, col, a=255):
    im = Image.new("RGBA", alpha.size, tuple(col) + (0,))
    im.putalpha(alpha.point(lambda v: v * a // 255))
    return im


def paint(mask, top, bot=None):
    """A gradient clipped to a mask (L image)."""
    im = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    im.paste(vgrad(mask.width, mask.height, top, bot or top), (0, 0), mask)
    return im


def soft_shadow(im, blur=16, alpha=120, col=(0, 0, 0)):
    """(shadow image, padding) — the shadow is im's silhouette, blurred; paste it at im's position - padding."""
    m = 2 * blur
    a = Image.new("L", (im.width + 2 * m, im.height + 2 * m), 0)
    a.paste(im.getchannel("A"), (m, m))
    return colorize(a.filter(ImageFilter.GaussianBlur(blur)), col, alpha), m


def with_glow(im, col, blur=18, alpha=150):
    m = 2 * blur
    out = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    a = Image.new("L", out.size, 0)
    a.paste(im.getchannel("A"), (m, m))
    out.alpha_composite(colorize(a.filter(ImageFilter.GaussianBlur(blur)), col, alpha))
    out.alpha_composite(im, (m, m))
    return out


def sweep(im, p, strength=0.6, width=45, rtl=True):
    """im with a diagonal light band at position p (0..1)."""
    a = np.asarray(im.getchannel("A"), np.float32) / 255.0
    h, w = a.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if rtl:
        xx = w - xx
    pos = -0.2 * w + p * 1.4 * w
    band = np.exp(-(((xx + yy * 0.5) - pos) / width) ** 2) * a * strength
    layer = np.zeros((h, w, 4), np.uint8)
    layer[..., :3] = 255
    layer[..., 3] = (band * 255).astype(np.uint8)
    out = im.copy()
    out.alpha_composite(Image.fromarray(layer, "RGBA"))
    return out


def rr_mask(w, h, r):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], r * SS, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def poly_mask(w, h, pts):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).polygon([(x * SS, y * SS) for x, y in pts], fill=255)
    return m.resize((w, h), Image.LANCZOS)


def star8(cx, cy, R, rot=0.0):
    """Points of an 8-pointed star (two overlapping squares) as one outline polygon."""
    r = R * 0.7654  # where the two squares' edges cross
    pts = []
    for k in range(16):
        a = rot - math.pi / 2 + k * math.pi / 8
        rad = R if k % 2 == 0 else r
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def squares8(cx, cy, R, rot=0.0):
    """The two squares of an 8-pointed star (for outline drawing)."""
    out = []
    for base in (0, math.pi / 4):
        out.append([(cx + R * math.cos(rot + base + k * math.pi / 2), cy + R * math.sin(rot + base + k * math.pi / 2))
                    for k in range(4)])
    return out


class Layout:
    diff_y = 175  # where the difficulty badge goes

    def __init__(self, v):
        self.v = v
        self.rtl = v.rtl
        self.L = v.L
        self._cache = {}

    def background(self, t):
        raise NotImplementedError

    def question(self, frame, i, u, out):
        raise NotImplementedError

    def answer_pos(self, i):
        return 540, 900

    def min_reveal(self, q):
        """Shortest time (s) the answer must stay on screen for this layout's reveal animation."""
        return 0.0

    def sound(self, mx, i, t0):
        """Extra sounds for question i (t0 = its question time 0)."""

    def timer(self, frame, cx, cy, q, u, col, ink, alpha=1.0):
        """The project's own timer type and effects, in this layout's colours."""
        ts, r, think = q["ts"], q["r"], self.v.T
        if not ts - 0.3 <= u < r + 0.2:
            return
        rem = 1 - prog(u, ts, r)
        left = max(0, math.ceil(r - u)) if u >= ts else int(think)
        c = RED_TIMER if (r - u) <= 2 and u >= ts else col
        a = prog(u, ts - 0.3, ts) * (1 - prog(u, r, r + 0.2)) * alpha
        total = int(math.ceil(think))
        draw_timer(self.v.timer, frame, cx, cy, rem, min(total, left), total, c, ink, max(0.0, u - ts), a, self.rtl,
                   self.v.timer_fx)


# =====================================================================================================
# Exam paper
# =====================================================================================================
PW, PH = 900, 1560  # sheet size
PCX, PCY = 540, 1000  # sheet centre on screen
RULE0, PITCH = 250, 64  # first ruled line, line spacing
INK = (28, 36, 78)  # printed text
PEN = (205, 28, 40)  # red pen
PAPER = (252, 250, 241)
_DESK = {}


def _desk():
    """Wooden desk (planks with grain), built once per process."""
    if "img" in _DESK:
        return _DESK["img"]
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    plank_w = 270
    plank = (xx // plank_w).astype(np.int32)
    tint = rng.uniform(0.9, 1.08, plank.max() + 2)[plank]
    phase = rng.uniform(0, 100, plank.max() + 2)[plank]

    def smooth_noise(n, k):
        a = rng.normal(0, 1, n + k)
        return np.convolve(a, np.ones(k) / k, mode="same")[:n]
    wob = np.stack([smooth_noise(H, 90) for _ in range(plank.max() + 2)])  # per-plank waviness along y
    wy = wob[plank, yy.astype(np.int32)] * 40
    grain = np.sin((xx % plank_w + wy + phase) * 0.11) * 0.5 + np.sin((xx % plank_w + wy * 1.7) * 0.37 + phase) * 0.25
    fine = rng.normal(0, 1, (H, W)).astype(np.float32)
    fine = np.asarray(Image.fromarray(((fine * 18) + 128).clip(0, 255).astype(np.uint8)).filter(
        ImageFilter.BoxBlur(1)), np.float32) - 128
    base = np.array([138, 88, 52], np.float32)
    v = (1 + 0.10 * grain)[..., None] * tint[..., None] * base + fine[..., None] * 0.25
    seam = (xx % plank_w) < 3
    v[seam] *= 0.55
    # warm lamp light in the middle, darker edges
    dist = np.sqrt(((xx - W * 0.5) / (W * 0.8)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)
    v *= (1.12 - 0.55 * np.clip(dist, 0, 1) ** 1.5)[..., None]
    img = Image.fromarray(np.clip(v, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    _DESK["img"] = img
    return img


def _pencil():
    """A yellow pencil, lying on the desk (with its shadow)."""
    L_, h = 560, 46
    s = SS
    im = Image.new("RGBA", (L_ * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    body0, body1 = 110, 470
    for k, col in enumerate([(255, 214, 80), (248, 190, 40), (214, 150, 20)]):  # three hexagon faces
        d.rectangle([body0 * s, (k * h / 3) * s, body1 * s, ((k + 1) * h / 3) * s], fill=col)
    d.polygon([(body0 * s, 0), (body0 * s, h * s), (18 * s, h / 2 * s)], fill=(236, 200, 150))  # sharpened wood
    d.polygon([(46 * s, (h / 2 - 9) * s), (46 * s, (h / 2 + 9) * s), (16 * s, h / 2 * s)], fill=(50, 50, 55))  # lead
    d.rectangle([body1 * s, 0, 505 * s, h * s], fill=(190, 192, 198))  # metal ferrule
    for x in range(476, 505, 7):
        d.line([(x * s, 0), (x * s, h * s)], fill=(150, 152, 160), width=2 * s)
    d.rounded_rectangle([500 * s, 0, L_ * s - 1, h * s - 1], 12 * s, fill=(240, 130, 140))  # eraser
    d.rectangle([500 * s, 0, 508 * s, h * s], fill=(190, 192, 198))
    im = im.resize((L_, h), Image.LANCZOS)
    hl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).rectangle([body0, 3, body1, 7], fill=(255, 255, 255, 90))
    im.alpha_composite(hl)
    im = im.rotate(32, expand=True, resample=Image.BICUBIC)
    sh, m = soft_shadow(im, 8, 110)
    out = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (10, 14))
    out.alpha_composite(im, (m, m))
    return out


def _red_pen():
    """A red marker pen pointing down-left; returns (image, tip offset in the image)."""
    L_, h = 330, 30
    s = SS
    im = Image.new("RGBA", (L_ * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(0, h / 2 * s), (26 * s, 6 * s), (26 * s, (h - 6) * s)], fill=(60, 60, 66))  # nib
    d.rectangle([26 * s, 3 * s, 70 * s, (h - 3) * s], fill=(205, 205, 212))  # grip
    d.rounded_rectangle([70 * s, 0, 300 * s, h * s - 1], 6 * s, fill=(200, 30, 42))
    d.rectangle([70 * s, 0, 300 * s, 9 * s], fill=(240, 80, 90))
    d.rounded_rectangle([290 * s, 1 * s, L_ * s - 1, (h - 1) * s], 10 * s, fill=(30, 30, 34))  # end cap
    im = im.resize((L_, h), Image.LANCZOS)
    ang = 35
    rot = im.rotate(ang, expand=True, resample=Image.BICUBIC)  # counter-clockwise: nib towards the bottom-left
    a = math.radians(ang)
    tip = (rot.width / 2 - (L_ / 2) * math.cos(a), rot.height / 2 + (L_ / 2) * math.sin(a))
    sh, m = soft_shadow(rot, 6, 90)
    out = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (14, 22))
    out.alpha_composite(rot, (m, m))
    return out, (tip[0] + m, tip[1] + m)


def _stamp(txt):
    w, h = 560, 230
    s = SS
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8 * s, 8 * s, (w - 8) * s, (h - 8) * s], 30 * s, outline=PEN + (255,), width=12 * s)
    d.rounded_rectangle([28 * s, 28 * s, (w - 28) * s, (h - 28) * s], 18 * s, outline=PEN + (255,), width=4 * s)
    im = im.resize((w, h), Image.LANCZOS)
    t = T(txt, 92, PEN, max_w=w - 90)
    im.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2))
    a = np.asarray(im.getchannel("A"), np.float32)  # worn ink: speckles where the stamp did not touch
    noise = np.random.default_rng(3).random(a.shape)
    a = a * np.where(noise < 0.12, 0.25, 1.0) * 0.92
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return im.rotate(12, expand=True, resample=Image.BICUBIC)


class ExamLayout(Layout):
    diff_y = 135

    def __init__(self, v):
        super().__init__(v)
        self.margin = PW - 110 if self.rtl else 110  # red margin line
        self.edge = 1 if self.rtl else -1  # +1: text is right-aligned

    # ------------------------------------------------------------ static
    def _static(self):
        if "static" in self._cache:
            return self._cache["static"]
        bg = _desk().copy()
        for ang, dx, dy in ((2.6, 16, 18), (-1.8, -12, 10)):  # the stack of sheets underneath
            sheet = Image.new("RGBA", (PW, PH), PAPER + (255,))
            ImageDraw.Draw(sheet).rectangle([0, 0, PW - 1, PH - 1], outline=(225, 220, 205), width=2)
            sheet = sheet.rotate(ang, expand=True, resample=Image.BICUBIC)
            sh, m = soft_shadow(sheet, 16, 110)
            bg.alpha_composite(sh, (int(PCX - sheet.width / 2 - m + dx + 6), int(PCY - sheet.height / 2 - m + dy + 12)))
            bg.alpha_composite(sheet, (int(PCX - sheet.width / 2 + dx), int(PCY - sheet.height / 2 + dy)))
        pen, tip = _red_pen()
        self._cache.update(static=bg, pencil=_pencil(), pen=pen, pen_tip=tip,
                           stamp=_stamp(self.L.get("excellent", "Excellent!")))
        return bg

    def _x(self, x_from_edge, width=0):
        """x of something placed x_from_edge inside the margin side (right side in RTL)."""
        return PW - x_from_edge - width if self.rtl else x_from_edge

    def _sheet(self, i):
        """The printed sheet for question i (without options) and the positions of its parts."""
        key = ("sheet", i)
        if key in self._cache:
            return self._cache[key]
        q, n = self.v.qs[i], len(self.v.qs)
        im = _paper_texture().copy()
        d = ImageDraw.Draw(im)
        for y in range(RULE0, PH - 30, PITCH):
            d.line([(0, y), (PW, y)], fill=(176, 204, 232), width=2)
        d.line([(self.margin, 0), (self.margin, PH)], fill=(236, 128, 128), width=3)
        hx = 42 if self.rtl else PW - 42  # punched holes on the other side
        for y in (330, PH // 2, PH - 330):
            d.ellipse([hx - 20, y - 20, hx + 20, y + 20], fill=(150, 104, 66))
            d.ellipse([hx - 20, y - 20, hx + 20, y - 8], fill=(120, 80, 50))
        # header: exam title, question i of n
        title = T(self.v.exam_title, 56, INK, max_w=PW - 230)
        im.alpha_composite(title, (self._x(130, title.width), 50))
        tag_txt = T(self.L["question"].format(i=i + 1, n=n), 34, (100, 104, 128), "Bold")
        tag = Image.new("RGBA", (tag_txt.width + 40, 58), (0, 0, 0, 0))
        ImageDraw.Draw(tag).rounded_rectangle([0, 0, tag.width - 1, 57], 14, outline=(150, 154, 175), width=3)
        tag.alpha_composite(tag_txt, (20, (58 - tag_txt.height) // 2))
        im.alpha_composite(tag, (PW - 90 - tag.width if not self.rtl else 90, 144))
        # question number in a hand-drawn red circle in the margin, then the question on the ruled lines
        badge_x = PW - 55 if self.rtl else 55
        lines = wrap(q["q"], 52, "Black", PW - 290)[:3]
        rule = 1
        first_y = RULE0 + rule * PITCH
        for k, line in enumerate(lines):
            li = T(line, 52, INK, max_w=PW - 290)
            y = RULE0 + (rule + k) * PITCH
            im.alpha_composite(li, (self._x(140, li.width), y - li.height + 14))
        num = T(str(i + 1), 46, PEN)
        im.alpha_composite(num, (int(badge_x - num.width / 2), first_y - num.height + 12))
        ny = first_y - num.height + 12 + num.height / 2  # hand-drawn red circle around the number
        ring = Image.new("RGBA", (90 * SS, 90 * SS), (0, 0, 0, 0))
        pts = [(45 * SS + 33 * SS * (1 + 0.05 * math.sin(3 * a)) * math.cos(a),
                45 * SS + 31 * SS * math.sin(a)) for a in np.linspace(-1.2, 2 * math.pi - 0.9, 70)]
        ImageDraw.Draw(ring).line(pts, fill=PEN + (220,), width=4 * SS, joint="curve")
        im.alpha_composite(ring.resize((90, 90), Image.LANCZOS), (int(badge_x - 45), int(ny - 45)))
        rule += len(lines) + 1
        opts = []
        for k, o in enumerate(q["opts"]):
            y = RULE0 + rule * PITCH  # the option sits on this ruled line
            row, n_lines = self._option_row(k, o)
            bx = PW - 170 if self.rtl else 170  # answer bubble
            x0 = bx - 42 if self.rtl else bx + 42
            ox = x0 - row.width if self.rtl else x0
            extra = (n_lines - 1) * PITCH  # a wrapped option takes one more ruled line
            opts.append(dict(img=row, pos=(int(ox), y + extra - row.height + 16), bubble=(bx, y - 34),
                             text_x0=ox, text_x1=ox + row.width, y=y - 34 + extra / 2, ry=54 + extra / 2))
            rule += 2 + (n_lines - 1)
        expl_y = RULE0 + rule * PITCH
        info = dict(img=im, opts=opts, badge=(badge_x, first_y - 22), expl_y=expl_y,
                    timer_y=min(PH - 200, expl_y + 210),
                    angle=random.Random(i * 7 + 3).uniform(-1.6, 1.4))
        self._cache[key] = info
        return info

    def _option_row(self, k, txt):
        """'أ)  text' printed (the answer bubble is drawn separately). Every option uses the same font size: a long
        one wraps onto a second ruled line (only text too long even for two lines is made smaller).
        Returns (image, number of lines)."""
        let = T(self.L["letters"][k] + ")", 50, INK)
        gap = 22
        avail = PW - 300 - let.width - gap  # from the letter to the far side of the sheet
        lines = wrap(txt, 50, "Bold", avail)
        if len(lines) > 2:
            lines = [lines[0], " ".join(lines[1:])]  # the rest shares the second line (shrinks to fit)
        imgs = [T(l, 50, INK, "Bold", max_w=avail) for l in lines]
        lh = max([let.height] + [im.height for im in imgs])
        w = let.width + gap + max(im.width for im in imgs)
        h = lh + (len(imgs) - 1) * PITCH
        row = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for j, im in enumerate(imgs):  # each line sits on its own ruled line
            y = j * PITCH + lh - im.height
            row.alpha_composite(im, (w - let.width - gap - im.width, y) if self.rtl else (let.width + gap, y))
        row.alpha_composite(let, (w - let.width, lh - let.height) if self.rtl else (0, lh - let.height))
        return row, len(imgs)

    # ------------------------------------------------------------ frame
    def background(self, t):
        return self._static().copy()

    def _pose(self, i, u, out):
        """Sheet offset (dx, dy) and angle: slides in from below, is tossed away at the end."""
        info = self._sheet(i)
        p = eo(prog(u, 0.0, 0.5))
        dx, dy = 0.0, (1 - p) * 1400
        ang = info["angle"] + (1 - p) * 7 * (1 if i % 2 else -1)
        if out > 0:
            o = out * out
            dx += (-1 if self.rtl else 1) * 1300 * o
            dy -= 220 * o
            ang += 10 * o * (1 if self.rtl else -1)
        return dx, dy, ang

    def _to_screen(self, px, py, dx, dy, ang):
        """Point on the sheet -> point on screen (PIL rotates counter-clockwise for a positive angle)."""
        a = math.radians(ang)
        x, y = px - PW / 2, py - PH / 2
        return (PCX + dx + x * math.cos(a) + y * math.sin(a), PCY + dy - x * math.sin(a) + y * math.cos(a))

    def answer_pos(self, i):
        info = self._sheet(i)
        o = info["opts"][self.v.qs[i]["correct"]]
        return self._to_screen(PW / 2, o["y"], 0, 0, info["angle"])

    def question(self, frame, i, u, out):
        q = self.v.qs[i]
        info = self._sheet(i)
        r = q["r"]
        sheet = info["img"].copy()
        d = ImageDraw.Draw(sheet)
        fx = self.v.fx
        pen_at = None  # where the red pen's nib is (sheet coords)
        # options are printed as they are read
        for k, o in enumerate(info["opts"]):
            pk = prog(u, q["opt_t"][k], q["opt_t"][k] + 0.3)
            if pk <= 0:
                continue
            bx, by = o["bubble"]
            ink = INK + (int(255 * pk),)
            d.ellipse([bx - 19, by - 19, bx + 19, by + 19], outline=ink, width=4)
            row = o["img"] if pk >= 1 else _fade(o["img"], pk)
            sheet.alpha_composite(row, o["pos"])
            if "lockin" in fx and r - 0.55 <= u < r:  # pencil shading over the bubbles = "answers locked"
                f = max(0.0, math.sin(prog(u, r - 0.55, r) * math.pi * 2)) ** 2
                d.ellipse([bx - 13, by - 13, bx + 13, by + 13], fill=(120, 120, 130, int(150 * f)))
        if u >= r:
            c = q["correct"]
            o = info["opts"][c]
            bx, by = o["bubble"]
            d.ellipse([bx - 14, by - 14, bx + 14, by + 14], fill=INK + (int(255 * prog(u, r, r + 0.12)),))
            pc = prog(u, r, r + 0.55)  # red circle around the right answer
            if pc > 0:
                cx = (min(o["text_x0"], bx - 22) + max(o["text_x1"], bx + 22)) / 2
                rx = (max(o["text_x1"], bx + 22) - min(o["text_x0"], bx - 22)) / 2 + 34
                pen_at = self._ink_ellipse(sheet, cx, o["y"], rx, o["ry"], eo(pc))
            for k, ok in enumerate(info["opts"]):  # small crosses on the wrong bubbles
                if k == c:
                    continue
                pk = prog(u, r + 0.55 + 0.1 * k, r + 0.65 + 0.1 * k)
                if pk > 0:
                    xb, yb = ok["bubble"]
                    pen_at = self._ink_cross(sheet, xb, yb, 20, pk)  # the pen rests where its last stroke ended
            pt = prog(u, r + 0.25, r + 0.5)  # tick next to the question number
            if pt > 0:
                bxq, byq = info["badge"]
                self._ink_tick(sheet, bxq, byq + 52, 30, pt)
            n0, nd = self.note_time(q)
            pn = prog(u, r + n0, r + n0 + nd)  # the explanation, hand-written in red
            if pn > 0 and q["expl"]:
                pen_at = self._ink_note(sheet, q["expl"], info["expl_y"], pn) or pen_at
        dx, dy, ang = self._pose(i, u, out)
        rot = sheet.rotate(ang, expand=True, resample=Image.BICUBIC)
        sh_key = ("shadow", i)
        if sh_key not in self._cache:  # from the resting angle, so every process builds the same one
            self._cache[sh_key] = soft_shadow(info["img"].rotate(info["angle"], expand=True), 18, 140)
        sh, m = self._cache[sh_key]
        x0, y0 = PCX + dx - rot.width / 2, PCY + dy - rot.height / 2
        frame.alpha_composite(sh, (int(x0 - m + 8), int(y0 - m + 16)))
        frame.alpha_composite(rot, (int(x0), int(y0)))
        # timer on the sheet, then the pencil and the red pen on top
        tx, ty = self._to_screen(PW / 2, info["timer_y"], dx, dy, ang)
        self.timer(frame, tx, ty, q, u, (205, 60, 50), (40, 40, 60), 1 - out)
        pencil = self._cache["pencil"]
        frame.alpha_composite(pencil, (int(-60), int(H - pencil.height + 40)))
        if pen_at is not None and out < 0.5:  # the red pen; lifts off the sheet when the marking is done
            n0, nd = self.note_time(q)
            lift = prog(u, r + (n0 + nd if q["expl"] else 1.0) + 0.1, r + (n0 + nd if q["expl"] else 1.0) + 0.45)
            if lift < 1:
                sx, sy = self._to_screen(pen_at[0], pen_at[1], dx, dy, ang)
                pen, tip = self._cache["pen"], self._cache["pen_tip"]
                e = eo(lift)
                paste(frame, pen, sx - tip[0] + pen.width / 2 + 160 * e, sy - tip[1] + pen.height / 2 - 220 * e, 1, 1 - e)
        st = r + self.stamp_time(q)
        if i == len(self.v.qs) - 1 and u >= st:  # "Excellent!" stamp on the last sheet
            ps = prog(u, st, st + 0.2)
            sx, sy = self._to_screen(PW * (0.3 if self.rtl else 0.7), PH - 230, dx, dy, ang)
            paste(frame, self._cache["stamp"], sx, sy, 2.0 - 1.0 * eo(ps), min(1, ps * 3) * (1 - out))

    # ------------------------------------------------------------ red-pen marks (anti-aliased, drawn on the sheet)
    def _layer(self, sheet, x0, y0, x1, y1, draw):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        lay = Image.new("RGBA", ((x1 - x0) * SS, (y1 - y0) * SS), (0, 0, 0, 0))
        draw(ImageDraw.Draw(lay), lambda x, y: ((x - x0) * SS, (y - y0) * SS))
        sheet.alpha_composite(lay.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))

    def _ink_ellipse(self, sheet, cx, cy, rx, ry, p):
        n = max(2, int(90 * p))
        start = -math.pi / 2 + (0.3 if self.rtl else -0.3)
        pts = []
        for k in range(n + 1):
            a = start + (k / 90) * 2.12 * math.pi * (1 if self.rtl else -1)
            wob = 1 + 0.035 * math.sin(a * 3 + 1) + 0.02 * (k / 90)
            pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))

        def draw(d, tr):
            d.line([tr(x, y) for x, y in pts], fill=PEN + (235,), width=6 * SS, joint="curve")
        self._layer(sheet, cx - rx - 30, cy - ry - 30, cx + rx + 30, cy + ry + 30, draw)
        return pts[-1]

    def _ink_cross(self, sheet, cx, cy, s, p):
        def draw(d, tr):
            p1 = min(1, p * 2)
            d.line([tr(cx - s, cy - s), tr(cx - s + 2 * s * p1, cy - s + 2 * s * p1)], fill=PEN + (230,), width=5 * SS)
            if p > 0.5:
                p2 = (p - 0.5) * 2
                d.line([tr(cx + s, cy - s), tr(cx + s - 2 * s * p2, cy - s + 2 * s * p2)], fill=PEN + (230,), width=5 * SS)
        self._layer(sheet, cx - s - 10, cy - s - 10, cx + s + 10, cy + s + 10, draw)
        p1, p2 = min(1, p * 2), max(0, (p - 0.5) * 2)
        if p2 > 0:
            return cx + s - 2 * s * p2, cy - s + 2 * s * p2
        return cx - s + 2 * s * p1, cy - s + 2 * s * p1

    def _ink_tick(self, sheet, cx, cy, s, p):
        pts = [(cx - 0.5 * s, cy), (cx - 0.1 * s, cy + 0.45 * s), (cx + 0.6 * s, cy - 0.55 * s)]
        l1, l2 = math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])
        L_ = (l1 + l2) * eo(p)

        def draw(d, tr):
            f = min(1, L_ / l1)
            d.line([tr(*pts[0]), tr(pts[0][0] + (pts[1][0] - pts[0][0]) * f, pts[0][1] + (pts[1][1] - pts[0][1]) * f)],
                   fill=PEN + (235,), width=6 * SS)
            if L_ > l1:
                f = (L_ - l1) / l2
                d.line([tr(*pts[1]), tr(pts[1][0] + (pts[2][0] - pts[1][0]) * f, pts[1][1] + (pts[2][1] - pts[1][1]) * f)],
                       fill=PEN + (235,), width=6 * SS)
        self._layer(sheet, cx - s, cy - s, cx + s, cy + s, draw)

    def _ink_note(self, sheet, txt, y, p):
        """Red note on the next ruled lines, written in reading direction; returns the pen position."""
        key = ("note", txt)
        if key not in self._cache:
            lines = wrap(txt, 42, "Bold", PW - 270)
            if len(lines) > 3:  # very long: the rest shares the third line (shrinks to fit)
                lines = lines[:2] + [" ".join(lines[2:])]
            self._cache[key] = [T(l, 42, PEN, "Bold", max_w=PW - 270) for l in lines]
        imgs = self._cache[key]
        total = sum(im.width for im in imgs)
        done = total * p
        pen = None
        for k, im in enumerate(imgs):
            if done <= 0:
                break
            w = int(min(im.width, done))
            done -= im.width
            yy = y + k * PITCH - im.height + 14
            if self.rtl:
                x_right = PW - 150
                crop = im.crop((im.width - w, 0, im.width, im.height))
                sheet.alpha_composite(crop, (x_right - w, yy))
                pen = (x_right - w, yy + im.height - 12)
            else:
                crop = im.crop((0, 0, w, im.height))
                sheet.alpha_composite(crop, (150, yy))
                pen = (150 + w, yy + im.height - 12)
        return pen

    def sound(self, mx, i, t0):
        q = self.v.qs[i]
        r = t0 + q["r"]
        mx.add(t0 - 0.02, mx.paper(), 0.3)
        mx.add(r, mx.scribble(0.55), 0.22)
        n_wrong = len(q["opts"]) - 1
        for k in range(n_wrong):
            mx.add(r + 0.6 + 0.1 * k, mx.scribble(0.1), 0.18)
        if q["expl"]:
            n0, nd = self.note_time(q)
            mx.add(r + n0, mx.scribble(nd), 0.12)
        if i == len(self.v.qs) - 1:
            mx.add(r + self.stamp_time(q) + 0.15, mx.stamp(), 0.55)

    # ------------------------------------------------------------ timing (seconds after the reveal)
    @staticmethod
    def note_time(q):
        """When the explanation note starts and how long the pen takes: about 30 characters a second."""
        return 0.95, min(3.2, max(1.3, len(q["expl"] or "") / 30))

    def stamp_time(self, q):
        n0, nd = self.note_time(q)
        return n0 + nd + 0.1 if q["expl"] else 1.1

    def min_reveal(self, q):
        """The answer stays on screen until the pen has finished (and the last sheet's stamp has landed)."""
        return self.stamp_time(q) + 1.0


def _paper_texture():
    """Cream paper with a faint fibre grain and slightly darker edges (built once per process)."""
    if "paper" not in _DESK:
        rng = np.random.default_rng(8)
        n = rng.normal(0, 1, (PH, PW)).astype(np.float32)
        n = np.asarray(Image.fromarray(((n * 30) + 128).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)),
                       np.float32) - 128
        yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
        edge = np.minimum(np.minimum(xx, PW - xx), np.minimum(yy, PH - yy))
        shade_ = 1 - 0.05 * np.clip(1 - edge / 60, 0, 1)
        rgb = (np.array(PAPER, np.float32) + n[..., None] * 0.12) * shade_[..., None]
        img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        _DESK["paper"] = img
    return _DESK["paper"]


def _fade(im, a):
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return out


# =====================================================================================================
# Islamic ornament
# =====================================================================================================
GOLD = (214, 178, 94)
GOLD_HI = (250, 226, 152)
GOLD_LO = (166, 126, 56)
EM_HI = (22, 82, 70)
EM_LO = (6, 36, 32)
CREAM = (250, 238, 205)
_ISL = {}


def _islamic_bg():
    if "img" in _ISL:
        return _ISL["img"]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.42) / (H * 0.6)) ** 2)
    k = np.clip(dist, 0, 1)[..., None]
    rgb = np.array([20, 88, 74], np.float32) * (1 - k) + np.array([3, 22, 22], np.float32) * k
    bg = Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")
    # 8-fold star tiling: stars on a grid, small diamonds between them, linked by lines
    pat = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(pat)
    g = GOLD + (34,)
    step = 150
    for row, cy in enumerate(range(-step, H + step, step)):
        for cx in range(-step, W + step, step):
            for sq in squares8(cx, cy, 52):
                d.polygon([(x * SS, y * SS) for x, y in sq], outline=g, width=2 * SS)
            d.ellipse([(cx - 12) * SS, (cy - 12) * SS, (cx + 12) * SS, (cy + 12) * SS], outline=g, width=2 * SS)
            mx_, my_ = cx + step / 2, cy + step / 2
            d.polygon([((mx_) * SS, (my_ - 26) * SS), ((mx_ + 26) * SS, my_ * SS), (mx_ * SS, (my_ + 26) * SS),
                       ((mx_ - 26) * SS, my_ * SS)], outline=g, width=2 * SS)
            d.line([((cx + 52) * SS, cy * SS), ((cx + step - 52) * SS, cy * SS)], fill=g, width=2 * SS)
            d.line([(cx * SS, (cy + 52) * SS), (cx * SS, (cy + step - 52) * SS)], fill=g, width=2 * SS)
    bg.alpha_composite(pat.resize((W, H), Image.LANCZOS))
    # vignette
    vg = np.clip((dist - 0.55) / 0.6, 0, 1) ** 1.4
    dark = np.zeros((H, W, 4), np.uint8)
    dark[..., 3] = (vg * 210).astype(np.uint8)
    bg.alpha_composite(Image.fromarray(dark, "RGBA"))
    # ornamental frame
    fr = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(fr)

    def S(v):
        return v * SS
    d.rectangle([S(34), S(34), S(W - 34), S(H - 34)], outline=GOLD + (255,), width=S(5))
    d.rectangle([S(48), S(48), S(W - 48), S(H - 48)], outline=GOLD_LO + (255,), width=S(2))
    d.rectangle([S(56), S(56), S(W - 56), S(H - 56)], outline=GOLD + (120,), width=S(1))
    for cx, cy in [(41, 41), (W - 41, 41), (41, H - 41), (W - 41, H - 41)]:
        pts = star8(cx, cy, 44)
        d.polygon([(S(x), S(y)) for x, y in pts], fill=(10, 52, 46, 255), outline=GOLD + (255,))
        d.line([(S(x), S(y)) for x, y in pts + [pts[0]]], fill=GOLD + (255,), width=S(4))
        d.ellipse([S(cx - 16), S(cy - 16), S(cx + 16), S(cy + 16)], outline=GOLD + (255,), width=S(3))
        d.ellipse([S(cx - 6), S(cy - 6), S(cx + 6), S(cy + 6)], fill=GOLD + (255,))
    for cx, cy in [(W / 2, 41), (W / 2, H - 41), (41, H / 2), (W - 41, H / 2)]:
        d.polygon([(S(cx), S(cy - 16)), (S(cx + 16), S(cy)), (S(cx), S(cy + 16)), (S(cx - 16), S(cy))],
                  fill=GOLD + (255,))
    bg.alpha_composite(fr.resize((W, H), Image.LANCZOS))
    _ISL["img"] = bg
    return bg


def arch_points(w, h, ha, n=48):
    """Pointed (mihrab) arch: straight sides rising vertically into two curves that meet in a point at the top
    centre (each curve a cubic Bezier: vertical at the shoulder, shallow at the apex)."""
    p0, p1, p2, p3 = (0, ha), (0, ha * 0.38), (w * 0.27, ha * 0.24), (w / 2, 0)
    left = []
    for t in np.linspace(0, 1, n):
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        left.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    right = [(w - x, y) for x, y in reversed(left)]
    return [(0, h)] + left + right[1:] + [(w, h)]


def _gold_star(R, filled=True, letter=None, dark_letter=False):
    s = SS
    size = int(2 * R + 8)
    im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    c = size * s / 2
    pts = star8(c, c, R * s)
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    if filled:
        im.paste(vgrad(im.width, im.height, GOLD_HI, GOLD_LO), (0, 0), m)
    else:
        im.paste(vgrad(im.width, im.height, EM_HI, EM_LO), (0, 0), m)
    ImageDraw.Draw(im).line(pts + [pts[0]], fill=(GOLD_HI if filled else GOLD) + (255,), width=3 * s)
    im = im.resize((size, size), Image.LANCZOS)
    if letter:
        t = T(letter, int(R * 0.95), (40, 28, 8) if dark_letter else GOLD_HI)
        im.alpha_composite(t, ((size - t.width) // 2, (size - t.height) // 2))
    return im


class IslamicLayout(Layout):
    diff_y = 108

    def __init__(self, v):
        super().__init__(v)
        rng = random.Random(21)
        self.dust = [(rng.uniform(80, W - 80), rng.uniform(100, H - 100), rng.uniform(2, 5), rng.uniform(8, 22),
                      rng.uniform(0, 6.28)) for _ in range(34)]

    def background(self, t):
        f = _islamic_bg().copy()
        if "rosette" not in self._cache:  # large faint rosette that turns slowly behind the card
            ro = Image.new("RGBA", (760 * SS, 760 * SS), (0, 0, 0, 0))
            d = ImageDraw.Draw(ro)
            c = 380 * SS
            for R, a in ((360, 40), (250, 30), (150, 26)):
                for sq in squares8(c, c, R * SS):
                    d.polygon(sq, outline=GOLD + (a,), width=3 * SS)
                d.ellipse([c - R * 0.76 * SS, c - R * 0.76 * SS, c + R * 0.76 * SS, c + R * 0.76 * SS],
                          outline=GOLD + (a // 2,), width=2 * SS)
            self._cache["rosette"] = ro.resize((760, 760), Image.LANCZOS)
        paste(f, self._cache["rosette"].rotate(t * 6, resample=Image.BICUBIC), 540, 640, 1, 1)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # gold dust drifting up
        d = ImageDraw.Draw(layer)
        for x, y0, r, sp, ph in self.dust:
            y = (y0 - t * sp) % (H - 200) + 100
            a = int(150 * (0.5 + 0.5 * math.sin(t * 1.7 + ph)))
            d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD_HI + (a,))
        f.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2)))
        return f

    # ------------------------------------------------------------ assets
    def _cartouche(self, i, n):
        key = ("cart", i)
        if key not in self._cache:
            txt = T(self.L["question"].format(i=i + 1, n=n), 44, GOLD_HI)
            w, h = txt.width + 150, 96
            pts = [(0, h / 2), (46, 0), (w - 46, 0), (w, h / 2), (w - 46, h), (46, h)]
            outer = poly_mask(w, h, pts)
            inner_pts = [(8, h / 2), (50, 6), (w - 50, 6), (w - 8, h / 2), (w - 50, h - 6), (50, h - 6)]
            inner = poly_mask(w, h, inner_pts)
            im = paint(outer, GOLD_HI, GOLD_LO)
            im.alpha_composite(paint(inner, EM_HI, EM_LO))
            d = ImageDraw.Draw(im)
            for x in (30, w - 30):
                d.polygon([(x, h / 2 - 9), (x + 9, h / 2), (x, h / 2 + 9), (x - 9, h / 2)], fill=GOLD)
            im.alpha_composite(txt, ((w - txt.width) // 2, (h - txt.height) // 2))
            self._cache[key] = with_glow(im, GOLD, 16, 70)
        return self._cache[key]

    def _card(self, i):
        key = ("card", i)
        if key in self._cache:
            return self._cache[key]
        q = self.v.qs[i]
        w, ha = 900, 210
        lines = wrap(q["q"], 60, "Black", 740)
        size = 60 if len(lines) <= 3 else 50
        lines = wrap(q["q"], size, "Black", 760)[:4]
        pitch = int(size * 1.42)
        h = ha + 20 + pitch * len(lines) + 56
        outer = poly_mask(w, h, arch_points(w, h, ha))
        b = 11
        inner = poly_mask(w, h, [(b + x * (w - 2 * b) / w, b + y * (h - 2 * b) / h) for x, y in arch_points(w, h, ha)])
        im = paint(outer, GOLD_HI, GOLD_LO)
        im.alpha_composite(paint(inner, EM_HI, EM_LO))
        line = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))  # fine inner gold line
        b2 = 24
        pts = [((b2 + x * (w - 2 * b2) / w) * SS, (b2 + y * (h - 2 * b2) / h) * SS) for x, y in arch_points(w, h, ha)]
        ImageDraw.Draw(line).line(pts + [pts[0]], fill=GOLD + (200,), width=2 * SS)
        im.alpha_composite(line.resize((w, h), Image.LANCZOS))
        im.alpha_composite(_gold_star(22), (w // 2 - 26, 74))  # ornament under the apex
        y = ha + 20
        for k, l in enumerate(lines):
            li = T(l, size, CREAM, max_w=780)
            im.alpha_composite(li, ((w - li.width) // 2, y + k * pitch + (pitch - li.height) // 2 - 6))
        fin = Image.new("RGBA", (40 * SS, 64 * SS), (0, 0, 0, 0))  # small gold finial on the apex
        df = ImageDraw.Draw(fin)
        df.polygon([(20 * SS, 0), (27 * SS, 22 * SS), (20 * SS, 30 * SS), (13 * SS, 22 * SS)], fill=GOLD_HI + (255,))
        df.ellipse([12 * SS, 30 * SS, 28 * SS, 46 * SS], fill=GOLD + (255,))
        df.rectangle([17 * SS, 44 * SS, 23 * SS, 64 * SS], fill=GOLD + (255,))
        fin = fin.resize((40, 64), Image.LANCZOS)
        full = Image.new("RGBA", (w, h + 56), (0, 0, 0, 0))
        full.alpha_composite(fin, (w // 2 - 20, 0))
        full.alpha_composite(im, (0, 56))
        info = dict(img=with_glow(full, GOLD, 26, 60), h=h + 56)
        self._cache[key] = info
        return info

    def _opt(self, i, k, ok):
        key = ("opt", i, k, ok)
        if key in self._cache:
            return self._cache[key]
        q = self.v.qs[i]
        w, h = 860, 112
        outer = rr_mask(w, h, 24)
        inner = rr_mask(w - 6, h - 6, 21)
        im = paint(outer, GOLD_HI, GOLD_LO)
        body = paint(inner, (246, 216, 140) if ok else EM_HI, (196, 150, 66) if ok else EM_LO)
        im.alpha_composite(body, (3, 3))
        star = _gold_star(40, filled=not ok, letter=self.L["letters"][k], dark_letter=not ok)
        sx = w - 30 - star.width if self.rtl else 30
        im.alpha_composite(star, (sx, (h - star.height) // 2))
        t = T(q["opts"][k], 50, (46, 32, 8) if ok else CREAM, "Bold", max_w=w - 220)
        tx = sx - 34 - t.width if self.rtl else sx + star.width + 34
        im.alpha_composite(t, (tx, (h - t.height) // 2 - 2))
        self._cache[key] = im
        return im

    def _layout(self, i):
        key = ("lay", i)
        if key not in self._cache:
            card = self._card(i)
            top = 312
            y0 = top + card["h"] + 92
            ys = [y0 + k * 138 for k in range(len(self.v.qs[i]["opts"]))]
            self._cache[key] = dict(card_cy=top + card["h"] / 2, ys=ys, timer_y=min(1560, ys[-1] + 175))
        return self._cache[key]

    def answer_pos(self, i):
        lay = self._layout(i)
        return 540, lay["ys"][self.v.qs[i]["correct"]]

    # ------------------------------------------------------------ frame
    def question(self, frame, i, u, out):
        q, n = self.v.qs[i], len(self.v.qs)
        r = q["r"]
        lay = self._layout(i)
        vis = 1 - out
        lift = -40 * out
        # header cartouche + progress stars
        p = prog(u, 0.0, 0.4)
        paste(frame, self._cartouche(i, n), 540, 196 + lift, 0.85 + 0.15 * ease_out_back(p), min(1, p * 2) * vis)
        gap = 42
        x0 = 540 + (n - 1) * gap / 2 * (1 if self.rtl else -1)
        for k in range(n):
            ps = prog(u, 0.15 + 0.04 * k, 0.4 + 0.04 * k)
            if ps <= 0:
                continue
            x = x0 - k * gap * (1 if self.rtl else -1)
            st = _cached_star(self._cache, 13 if k != i else 16, filled=k <= i)
            if k == i:
                st = with_glow(st, GOLD_HI, 8, int(120 + 80 * math.sin(u * 4)))
            paste(frame, st, x, 278 + lift, ease_out_back(ps), vis)
        # arch card
        card = self._card(i)
        pc = prog(u, 0.08, 0.55)
        paste(frame, card["img"], 540, lay["card_cy"] + lift + 30 * (1 - eo(pc)), 0.94 + 0.06 * eo(pc), min(1, pc * 1.6) * vis)
        # options
        lock = prog(u, r - 0.55, r) if "lockin" in self.v.fx else 0
        for k, y in enumerate(lay["ys"]):
            pk = prog(u, q["opt_t"][k], q["opt_t"][k] + 0.4)
            if pk <= 0:
                continue
            dx = (1 - eo(pk)) * (140 if self.rtl else -140)
            a = min(1, pk * 1.8) * vis
            img = self._opt(i, k, False)
            if u >= r and k == q["correct"]:
                pr = prog(u, r, r + 0.3)
                pulse = 1 + 0.05 * math.sin(math.pi * prog(u, r, r + 0.5))
                okimg = self._opt(i, k, True)
                ps = prog(u, r + 0.15, r + 0.9)
                if 0 < ps < 1:
                    okimg = sweep(okimg, ps, 0.7, 50, self.rtl)
                paste(frame, with_glow(okimg, GOLD_HI, 22, int(190 * pr)), 540, y + lift, pulse, a * pr)
                paste(frame, img, 540, y + lift, pulse, a * (1 - pr))
                self._twinkles(frame, y + lift, u - r, vis)
                continue
            if u >= r:
                a *= 1 - 0.6 * prog(u, r, r + 0.35)
            paste(frame, img, 540 + dx, y + lift, 1, a)
            if lock > 0 and u < r:
                f = max(0.0, math.sin(lock * math.pi * 2)) ** 2
                if f > 0.02:
                    paste(frame, sweep(img, lock, 0.5, 60, self.rtl), 540 + dx, y + lift, 1, a * f)
        # timer, then the explanation under a gold divider
        ty = lay["timer_y"]
        self.timer(frame, 540, ty + lift, q, u, GOLD, CREAM, vis)
        if u >= r + 0.25:
            pe = prog(u, r + 0.25, r + 0.65)
            self._divider(frame, ty - 70 + lift, pe * vis)
            if q["expl"]:
                key = ("expl", i)
                if key not in self._cache:
                    lines = wrap(q["expl"], 42, "Bold", 900)[:2]
                    imgs = [T(l, 42, GOLD_HI, "Bold", max_w=920) for l in lines]
                    hh = 60 * (len(imgs) - 1) + imgs[-1].height
                    ex = Image.new("RGBA", (max(im.width for im in imgs), hh), (0, 0, 0, 0))
                    for j, im in enumerate(imgs):
                        ex.alpha_composite(im, ((ex.width - im.width) // 2, j * 60))
                    self._cache[key] = ex
                paste(frame, self._cache[key], 540, ty + 10 + lift, 0.94 + 0.06 * pe, pe * vis)

    def _divider(self, frame, y, a):
        if a <= 0.01:
            return
        if "div" not in self._cache:
            w, h = 620, 40
            im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            for k in range(60):  # lines fading towards the ends
                f0, f1 = k / 60, (k + 1) / 60
                al = int(255 * (1 - f0) ** 1.3)
                for side in (1, -1):
                    xa = w / 2 + side * (30 + f0 * (w / 2 - 40))
                    xb = w / 2 + side * (30 + f1 * (w / 2 - 40))
                    d.line([(xa * SS, h / 2 * SS), (xb * SS, h / 2 * SS)], fill=GOLD + (al,), width=3 * SS)
            im = im.resize((w, h), Image.LANCZOS)
            im.alpha_composite(_gold_star(14), (w // 2 - 18, h // 2 - 18))
            self._cache["div"] = im
        paste(frame, self._cache["div"], 540, y, 0.6 + 0.4 * eo(a), a)

    def _twinkles(self, frame, y, v, vis):
        """Four-point gold sparkles around the right answer after the reveal."""
        if not 0 <= v < 1.6:
            return
        layer = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        rng = random.Random(int(y))
        for k in range(9):
            x = rng.uniform(140, W - 140)
            yy = rng.uniform(40, 220)
            ph = prog(v, 0.1 + 0.08 * k, 0.6 + 0.08 * k)
            s = 22 * math.sin(math.pi * ph)
            if s <= 1:
                continue
            d.polygon([(x, yy - s), (x + s * 0.22, yy - s * 0.22), (x + s, yy), (x + s * 0.22, yy + s * 0.22), (x, yy + s),
                       (x - s * 0.22, yy + s * 0.22), (x - s, yy), (x - s * 0.22, yy - s * 0.22)],
                      fill=GOLD_HI + (int(240 * vis),))
        frame.alpha_composite(layer, (0, int(y - 130)))

    def sound(self, mx, i, t0):
        q = self.v.qs[i]
        mx.add(t0 + q["r"] + 0.05, mx.sparkle(), 0.16)


def _cached_star(cache, R, filled):
    key = ("pstar", R, filled)
    if key not in cache:
        cache[key] = _gold_star(R, filled=filled)
    return cache[key]


def make_layout(name, video):
    if name == "Exam paper":
        return ExamLayout(video)
    if name == "Islamic":
        return IslamicLayout(video)
    return None
