"""Extra animations for the Multiple Choice video (mcq.fx), plus the per-question difficulty badge.

    lockin    options flash twice just before the reveal; a green check draws itself on the right answer,
              the wrong ones shake and get a red cross
    confetti  confetti bursts from the right answer and a light sweep runs across it
    wipe      a diagonal accent band sweeps across the screen between questions (and into the ending)
    final     "Final question!" ribbon before the last question, then a red heartbeat glow during it
    levels    ending with score levels (Beginner / Expert / Genius) lighting up and a subscribe-button tap
    difficulty badge (Easy / Medium / Hard + 1-3 stars): shown for every question that has a level

Everything depends only on the time it is given (frames are rendered on several processes)."""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import H, W, clamp, ease_out_back, paste, prog, shade, text_img

FX_OPTIONS = [("Lock-in flash + ✔/✖ stamps", "lockin"), ("Confetti on the right answer", "confetti"),
              ("Wipe between questions", "wipe"), ("“Final question” banner", "final"),
              ("Score-levels ending + subscribe tap", "levels")]
FX_KEYS = [k for _, k in FX_OPTIONS]
FINAL_LEN = 1.3  # seconds the "Final question" ribbon plays before the last question
LEVELS_END = 5.0  # ending length with the score-levels ending (the classic one is 4 s)
WIPE_HALF = 0.42  # the wipe band covers the screen at the boundary, +- this many seconds

GREEN = (70, 215, 120)
RED = (255, 90, 90)
DIFF_COLORS = {"easy": ((70, 200, 110), 1), "medium": ((255, 165, 40), 2), "hard": ((240, 70, 80), 3)}
SS = 3  # supersampling for smooth edges


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def colorize(alpha, col, a=255):
    im = Image.new("RGBA", alpha.size, tuple(col) + (0,))
    im.putalpha(alpha.point(lambda v: v * a // 255))
    return im


def glow_disc(r, col, alpha=200, blur=None):
    mask = Image.new("L", (4 * r, 4 * r), 0)
    ImageDraw.Draw(mask).ellipse([r, r, 3 * r, 3 * r], fill=alpha)
    return colorize(mask.filter(ImageFilter.GaussianBlur(blur or r * 0.45)), col)


def shine(im, p, strength=0.55, width=40, rtl=True):
    """im with a diagonal light band at position p (0..1) over its opaque part."""
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


def star_pts(cx, cy, R, n=5, rot=-math.pi / 2):
    r = R * 0.45
    return [(cx + (R if k % 2 == 0 else r) * math.cos(rot + k * math.pi / n),
             cy + (R if k % 2 == 0 else r) * math.sin(rot + k * math.pi / n)) for k in range(2 * n)]


def heartbeat(t):
    """Two beats per second ("lub-dub"), peaks at t = 0 and 0.2 (mod 1)."""
    ph = (t + 0.08) % 1.0
    return math.exp(-((ph - 0.08) / 0.05) ** 2) + 0.6 * math.exp(-((ph - 0.28) / 0.06) ** 2)


def score_levels(n):
    """[(range text, level index 0-2)] for a quiz of n questions: Beginner / Expert / Genius."""
    hi = max(1, math.ceil(n * 0.6))  # first "Expert" score
    out = []

    def rng(a, b):
        return str(a) if a == b else f"{a}-{b}"
    if hi - 1 >= 0 and n > 1:
        out.append((rng(0, hi - 1), 0))
    if hi <= n - 1:
        out.append((rng(hi, n - 1), 1))
    out.append((str(n), 2))
    return out


class QuizFX:
    def __init__(self, accent, ink, L, rtl=True, light=False):
        self.accent, self.ink, self.L, self.rtl, self.light = tuple(accent), tuple(ink), L, rtl, light
        self._vig = None
        self._flash = None
        self._marks = {}

    # ------------------------------------------------------------ shared assets
    @property
    def vig(self):
        if self._vig is None:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            dist = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
            self._vig = Image.fromarray((np.clip((dist - 0.45) / 0.6, 0, 1) ** 1.6 * 255).astype(np.uint8), "L")
        return self._vig

    @property
    def flash(self):
        if self._flash is None:
            w, h, m = 920, 112, 30
            g = Image.new("L", (w + 2 * m, h + 2 * m), 0)
            ImageDraw.Draw(g).rounded_rectangle([m, m, m + w, m + h], 30, fill=255)
            self._flash = colorize(g.filter(ImageFilter.GaussianBlur(6)), (255, 255, 255))
        return self._flash

    def badge_x(self):
        """x of the options' letter badge (options are 920 wide, centred, badge 70 px in)."""
        return 930 if self.rtl else 150

    # ------------------------------------------------------------ lock-in
    def lock_flash(self, frame, x, y, lock, alpha):
        """Two quick white flashes over an option while lock goes 0 -> 1."""
        f = max(0.0, math.sin(lock * math.pi * 2)) ** 2
        if f > 0.01:
            paste(frame, self.flash, x, y, 1.0, 0.45 * f * alpha)

    def mark(self, ok, p):
        """Round green check / red cross badge; p = stroke progress 0..1."""
        key = (ok, round(p, 2))
        if key in self._marks:
            return self._marks[key]
        R, s = 44, SS
        size = 2 * R + 20
        im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = size * s / 2
        d.ellipse([c - (R + 4) * s, c - (R + 4) * s, c + (R + 4) * s, c + (R + 4) * s], fill=(255, 255, 255, 255))
        d.ellipse([c - R * s, c - R * s, c + R * s, c + R * s], fill=(GREEN if ok else RED) + (255,))
        lw, white = 9 * s, (255, 255, 255, 255)
        if ok:
            pts = [(c - 20 * s, c + 1 * s), (c - 5 * s, c + 16 * s), (c + 22 * s, c - 14 * s)]
            l1, l2 = math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])
            L = (l1 + l2) * ease_out(p)
            if L > 0:
                f = min(1, L / l1)
                d.line([pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * f, pts[0][1] + (pts[1][1] - pts[0][1]) * f)],
                       fill=white, width=lw)
            if L > l1:
                f = (L - l1) / l2
                d.line([pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * f, pts[1][1] + (pts[2][1] - pts[1][1]) * f)],
                       fill=white, width=lw)
                d.ellipse([pts[1][0] - lw / 2, pts[1][1] - lw / 2, pts[1][0] + lw / 2, pts[1][1] + lw / 2], fill=white)
        else:
            k = 16 * s * ease_out(p)
            d.line([(c - k, c - k), (c + k, c + k)], fill=white, width=lw)
            d.line([(c - k, c + k), (c + k, c - k)], fill=white, width=lw)
        im = im.resize((size, size), Image.LANCZOS)
        if len(self._marks) < 300:
            self._marks[key] = im
        return im

    # ------------------------------------------------------------ confetti
    def confetti(self, frame, y0, v, seed):
        """Burst from the right answer (centre y0), v seconds after the reveal."""
        if v < 0 or v > 1.9:
            return
        rng = random.Random(seed)
        cols = [self.accent, GREEN, (90, 170, 255), (255, 110, 160),
                shade(self.accent, 0.6) if self.light else (255, 255, 255)]
        layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))  # drawn apart so the fade-out blends
        d = ImageDraw.Draw(layer)
        fade = 1 - prog(v, 1.3, 1.9)
        drag = (1 - math.exp(-v * 1.2)) / 1.2
        for _ in range(110):
            dirx, spd, rot0, spin = rng.uniform(-1, 1), rng.uniform(0.45, 1.0), rng.uniform(0, 6.28), rng.uniform(-14, 14)
            col, sz = rng.choice(cols), rng.uniform(9, 16)
            x = 540 + dirx * 300 + dirx * 950 * drag
            y = y0 - 1500 * spd * v + 1300 * v * v
            if y > H + 40:
                continue
            a = rot0 + spin * v
            w, h = sz, sz * 0.45 * (0.4 + 0.6 * abs(math.cos(a * 1.7)))
            ca, sa = math.cos(a), math.sin(a)
            pts = [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in ((-w, -h), (w, -h), (w, h), (-w, h))]
            d.polygon(pts, fill=tuple(col) + (int(255 * fade),))
        frame.alpha_composite(layer)

    # ------------------------------------------------------------ wipe
    def wipe(self, frame, t, times):
        """Diagonal band crossing the screen; fully covering it at each time in `times`."""
        for tb in times:
            v = prog(t, tb - WIPE_HALF, tb + WIPE_HALF)
            if not 0 < v < 1:
                continue
            e = v * v * (3 - 2 * v)
            pos = -1500 + e * (W + 3000)
            d = ImageDraw.Draw(frame, "RGBA")
            sk = 700
            for off, width, col in ((-260, 120, shade(self.accent, 0.55)), (0, 1300, shade(self.accent, 0.22)),
                                    (1300, 70, self.accent)):
                x0, x1 = pos + off, pos + off + width
                if self.rtl:  # sweeps right -> left, like the reading direction
                    x0, x1 = W - x0, W - x1
                    d.polygon([(x0, 0), (x1, 0), (x1 + sk, H), (x0 + sk, H)], fill=tuple(col) + (255,))
                else:
                    d.polygon([(x0, 0), (x1, 0), (x1 - sk, H), (x0 - sk, H)], fill=tuple(col) + (255,))

    # ------------------------------------------------------------ final question
    def final_tint(self, frame, u):
        """Red heartbeat glow at the screen edges (u = seconds into the last question's countdown)."""
        hb = heartbeat(u)
        frame.alpha_composite(colorize(self.vig, (200, 20, 40), int(150 * (0.45 + 0.55 * min(1, hb)))))

    def final_banner(self, frame, v):
        """Tilted red ribbon sliding through the screen during the first FINAL_LEN seconds."""
        if not 0 <= v < FINAL_LEN + 0.05:
            return
        p_in, p_out = ease_out(prog(v, 0.0, 0.35)), ease_out(prog(v, 1.0, FINAL_LEN))
        frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(120 * (1 - p_out) * min(1, v * 4)))))
        bw, bh = 1400, 190
        band = Image.new("RGBA", (bw, bh + 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(band)
        d.rectangle([0, 30, bw, 30 + bh], fill=(200, 30, 45, 255))
        d.rectangle([0, 30, bw, 42], fill=(255, 210, 90, 255))
        d.rectangle([0, 30 + bh - 12, bw, 30 + bh], fill=(255, 210, 90, 255))
        t = text_img(self.L["final"], 100, (255, 255, 255), "Black", shadow=True, max_w=1000)
        band.alpha_composite(t, ((bw - t.width) // 2, 30 + (bh - t.height) // 2))
        band = band.rotate(-6 if self.rtl else 6, expand=True, resample=Image.BICUBIC)
        side = 1400 if self.rtl else -1400
        x = 540 + (1 - p_in) * side - p_out * side
        paste(frame, band, x, 900, 1 + 0.05 * heartbeat(v - 0.35), 1.0)

    # ------------------------------------------------------------ difficulty
    def difficulty(self, frame, level, u, vis, y0=175):
        if level not in DIFF_COLORS or vis <= 0.01:
            return
        col, nstar = DIFF_COLORS[level]
        t = text_img(self.L["levels"][level], 36, (255, 255, 255), "Black", shadow=False)
        sw = 3 * 40
        w, h = t.width + sw + 70, 60
        im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], h * SS // 2, fill=shade(col, 0.35) + (235,),
                                             outline=col + (255,), width=3 * SS)
        im = im.resize((w, h), Image.LANCZOS)
        im.alpha_composite(t, (w - 28 - t.width if self.rtl else 28, (h - t.height) // 2 + 1))
        p = prog(u, 0.2, 0.55)
        if p <= 0:
            return
        paste(frame, im, 540, y0, 0.7 + 0.3 * ease_out_back(p), min(1, p * 2) * vis)
        stars = Image.new("RGBA", (sw + 20, 60), (0, 0, 0, 0))  # drawn apart so faded stars blend
        d = ImageDraw.Draw(stars)
        for k in range(3):  # stars pop in one by one, in reading order
            ps = prog(u, 0.45 + 0.12 * k, 0.7 + 0.12 * k)
            if ps <= 0:
                continue
            idx = (2 - k) if self.rtl else k
            filled = k < nstar
            c = ((255, 210, 60) if filled else (255, 255, 255)) + (int(255 * vis * (1 if filled else 0.35)),)
            d.polygon(star_pts(30 + idx * 40, 30, 16 * ease_out_back(ps)), fill=c)
        sx0 = 540 - w / 2 + (28 if self.rtl else w - 28 - sw)
        frame.alpha_composite(stars, (int(sx0 - 10), int(y0 - 30)))
    # ------------------------------------------------------------ ending
    def _pill(self, txt, size, fg, bg, padx=70, h=110):
        t = text_img(txt, size, fg, "Black", shadow=False)
        w = t.width + 2 * padx
        im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], h * SS // 2, fill=tuple(bg) + (255,))
        im = im.resize((w, h), Image.LANCZOS)
        im.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2 + 2))
        return im

    def _level_card(self, rng_txt, name, col, lit):
        w, h = 820, 130
        card = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], 60, fill=shade(col, 0.22 + 0.25 * lit) + (240,),
                                               outline=col + (255,), width=6)
        card = card.resize((w, h), Image.LANCZOS)
        medal = Image.new("RGBA", (96 * SS, 96 * SS), (0, 0, 0, 0))
        dm = ImageDraw.Draw(medal)
        dm.ellipse([0, 0, 96 * SS - 1, 96 * SS - 1], fill=shade(col, 0.7) + (255,))
        dm.ellipse([7 * SS, 7 * SS, 89 * SS, 89 * SS], fill=col + (255,))
        dm.polygon(star_pts(48 * SS, 50 * SS, 26 * SS), fill=(255, 255, 255, 230))
        medal = medal.resize((96, 96), Image.LANCZOS)
        mx = w - 20 - 96 if self.rtl else 20
        card.alpha_composite(medal, (mx, (h - 96) // 2))
        lab = text_img(name, 58, (255, 255, 255), "Black", shadow=False, max_w=480)
        rn = text_img(rng_txt, 58, col, "Black", shadow=False)
        if self.rtl:
            card.alpha_composite(lab, (mx - 30 - lab.width, (h - lab.height) // 2))
            card.alpha_composite(rn, (40, (h - rn.height) // 2))
        else:
            card.alpha_composite(lab, (mx + 126, (h - lab.height) // 2))
            card.alpha_composite(rn, (w - 40 - rn.width, (h - rn.height) // 2))
        if 0 < lit < 1:
            card = shine(card, lit, 0.6, 50, self.rtl)
        return card

    def levels_ending(self, frame, t, t0, n, qlines, cta, handle):
        """Score levels + subscribe tap. qlines = [(text, colour)] title lines (the ending question)."""
        if t < t0:
            return
        v = t - t0
        frame.alpha_composite(Image.new("RGBA", (W, H), (4, 6, 16, int(215 * ease_out(prog(v, 0, 0.5))))))
        lines = qlines or [(self.L["score_q"], (255, 255, 255))]
        size, pitch = (80, 98) if len(lines) > 1 else (92, 110)
        y_title = 420 - (len(lines) - 1) * pitch / 2
        for k, (txt, col) in enumerate(lines[:2]):
            p = prog(v, 0.15 + 0.12 * k, 0.5 + 0.12 * k)
            if p > 0:
                paste(frame, text_img(txt, size, col, max_w=960), 540, y_title + k * pitch,
                      0.8 + 0.2 * ease_out_back(p), min(1, p * 1.5))
        names = self.L["score_levels"]
        medal_cols = [(205, 127, 50), (200, 205, 215), (255, 205, 60)]
        rows = score_levels(n)
        for k, (rng_txt, lv) in enumerate(rows):
            y = 640 + k * 165
            pk = prog(v, 0.4 + 0.15 * k, 0.75 + 0.15 * k)
            if pk <= 0:
                continue
            lit = prog(v, 1.2 + 0.35 * k, 1.45 + 0.35 * k)
            col = medal_cols[lv]
            dx = (1 - ease_out_back(pk)) * (500 if k % 2 else -500)
            if lit > 0:
                paste(frame, glow_disc(200, col, 120, 90), 540 + dx, y, 1.0, 0.5 * lit)
            paste(frame, self._level_card(rng_txt, names[lv], col, lit), 540 + dx, y,
                  1 + 0.05 * math.sin(math.pi * lit), min(1, pk * 2))
        # subscribe button: a finger-tap glides in, presses it, it turns grey
        by = 640 + len(rows) * 165 + 90
        pb = prog(v, 2.3, 2.6)
        if pb > 0:
            press = prog(v, 3.05, 3.2) - prog(v, 3.25, 3.4)
            done = v >= 3.25
            btn = self._pill(self.L["subscribed"] if done else self.L["subscribe"], 56, (255, 255, 255),
                             (90, 90, 100) if done else (230, 30, 40))
            paste(frame, btn, 540, by, (0.8 + 0.2 * ease_out_back(pb)) * (1 - 0.08 * press), min(1, pb * 2))
            pc = ease_out(prog(v, 2.6, 3.05))
            cx, cy = 600 + 300 * (1 - pc), by + 30 + 260 * (1 - pc)
            if v < 3.9:
                dot = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
                ImageDraw.Draw(dot).ellipse([30, 30, 90, 90], fill=(255, 255, 255, 200), outline=(0, 0, 0, 90), width=3)
                paste(frame, dot, cx, cy, 1 - 0.2 * press, pc * (1 - prog(v, 3.6, 3.9)))
            rp = prog(v, 3.15, 3.6)
            if 0 < rp < 1:
                R = int(30 + 110 * ease_out(rp))
                rim = Image.new("RGBA", (2 * R + 10, 2 * R + 10), (0, 0, 0, 0))
                ImageDraw.Draw(rim).ellipse([5, 5, 2 * R + 5, 2 * R + 5], outline=(255, 255, 255, 255), width=6)
                paste(frame, rim, cx, cy, 1, 1 - rp)
        for k, (txt, sz, col, ti) in enumerate([(cta, 50, (255, 255, 255), 3.4), (handle, 44, (190, 190, 200), 3.6)]):
            p = prog(v, ti, ti + 0.35)
            if txt and p > 0:
                paste(frame, text_img(txt, sz, col, max_w=960), 540, by + 150 + k * 85, 0.8 + 0.2 * ease_out_back(p),
                      min(1, p * 1.5))
