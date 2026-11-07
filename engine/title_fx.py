"""Animated opening title for the Multiple Choice video ("Fancy" intro).

Timeline (seconds, the opening sound's impact lands at ~0.47 s with "Swoosh + impact"):
    0.10  light streaks rush in, the ? badge pops in
    0.47  the 3D title slams down: flash, shockwave ring, spark burst, small shake
    0.70  accent bar grows under the title, subtitle pill slides up
    1.05  a light sweep runs across the title
    ...   idle: badge floats, title breathes, sparkles twinkle
    t_out everything zooms toward the viewer and fades (the first question whooshes in)

Everything depends only on t (frames are rendered on several processes)."""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import H, W, clamp, ease_io, ease_out_back, paste, prog, shade, text_img, to_rgb

IMPACT = 0.47


def _ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def _glow_disc(r, col, alpha=200, blur=None):
    """Soft round glow. The mask is blurred, not the colour, so the edge never darkens on light pages."""
    mask = Image.new("L", (4 * r, 4 * r), 0)
    ImageDraw.Draw(mask).ellipse([r, r, 3 * r, 3 * r], fill=alpha)
    return _colorize(mask.filter(ImageFilter.GaussianBlur(blur or r * 0.45)), col)


def _colorize(alpha, col, a=255):
    im = Image.new("RGBA", alpha.size, tuple(col) + (0,))
    im.putalpha(alpha.point(lambda v: v * a // 255))
    return im


class TitleIntro:
    def __init__(self, lines, subtitle, sub_col, ink, accent, light=False, rtl=True, t_in=0.1, t_out=2.4,
                 title_y=720, max_w=940):
        self.max_w = max_w  # widest a title line may be (long lines shrink to fit)
        self.t_in, self.t_out = t_in, t_out
        self.accent = to_rgb(accent)
        self.light = light
        self.ink = to_rgb(ink)
        self.hit = t_in + IMPACT - 0.1
        self.title = self._title_block(lines)
        self.cy = sum(y for *_, y in lines) / len(lines) if lines else title_y  # centre of the title block
        self.badge = self._badge("؟" if rtl else "?")
        box = self.title.getchannel("A").point(lambda v: 255 if v > 140 else 0).getbbox() or (0, 0, 1, 1)
        top = self.cy - self.title.height / 2 + box[1]  # visible text edges (the image has glow padding)
        bottom = self.cy - self.title.height / 2 + box[3]
        self.text_w = box[2] - box[0]
        self.badge_y = top - 140
        self.bar_y = bottom + 40
        self.sub = self._pill(subtitle, to_rgb(sub_col)) if subtitle else None
        self.sub_y = self.bar_y + 100
        self.flash = _glow_disc(300, (255, 255, 255) if not light else self.accent, 150, 160)
        self.halo = _glow_disc(170, self.accent, 170, 90)
        self.alpha = np.asarray(self.title.getchannel("A"), np.float32) / 255.0
        rng = random.Random(7)
        self.sparks = [(rng.uniform(0, 2 * math.pi), rng.uniform(380, 820), rng.uniform(5, 11),
                        rng.choice([self.accent, (255, 255, 255), shade(self.accent, 1.3)])) for _ in range(46)]
        self.twinkles = [(rng.uniform(80, W - 80), rng.uniform(250, 1500), rng.uniform(0, 6.28), rng.uniform(4, 9))
                         for _ in range(22)]
        self.streaks = [(rng.uniform(-1, 1) * 760, rng.choice([-1, 1]), rng.uniform(0.0, 0.12), rng.uniform(260, 520))
                        for _ in range(14)]

    # ------------------------------------------------------------ assets
    def _title_block(self, lines):
        """All title lines on one image: accent glow, 3D extrusion, gradient face."""
        imgs = [text_img(txt, size, col, shadow=False, max_w=self.max_w) for txt, size, col, _ in lines]
        if not imgs:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        pitch = [int(size * 1.28) for _, size, _, _ in lines]
        depth, pad = 12, 60
        w = max(i.width for i in imgs) + 2 * pad
        h = sum(pitch[:-1]) + imgs[-1].height + 2 * pad + depth
        face = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        y = pad
        for im, p in zip(imgs, pitch):
            face.alpha_composite(im, ((w - im.width) // 2, y))
            y += p
        a = face.getchannel("A")
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        glow_col = self.accent
        out.alpha_composite(_colorize(a.filter(ImageFilter.GaussianBlur(26)), glow_col, 150 if not self.light else 70))
        ext = shade(self.accent, 0.38 if not self.light else 0.7)
        for k in range(depth, 0, -1):  # extrusion: stacked darker copies below the face
            out.alpha_composite(_colorize(a, shade(ext, 0.75 + 0.25 * (1 - k / depth))), (0, k))
        out.alpha_composite(_colorize(a.filter(ImageFilter.GaussianBlur(3)), (0, 0, 0), 120), (0, depth + 4))
        # gradient face: line colours, brighter at the top, a touch of accent at the bottom
        arr = np.asarray(face, np.float32)
        yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        top, bot = 1.08, 0.88
        tint = np.array(self.accent, np.float32)[None, None, :]
        rgb = arr[..., :3] * (top + (bot - top) * yy)
        rgb = rgb * 0.9 + tint * 0.1 * yy
        arr[..., :3] = np.clip(rgb, 0, 255)
        out.alpha_composite(Image.fromarray(arr.astype(np.uint8), "RGBA"))
        return out

    def _badge(self, mark):
        s = 2  # supersampled for smooth edges
        r = 92
        size = 2 * (r + 50)
        im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = size * s // 2
        R = r * s
        d.ellipse([c - R - 10 * s, c - R - 10 * s, c + R + 10 * s, c + R + 10 * s], fill=(255, 255, 255, 235))
        for k in range(R, 0, -2):  # radial gradient disc
            f = k / R
            col = shade(self.accent, 1.15 - 0.45 * f)
            d.ellipse([c - k, c - k, c + k, c + k], fill=tuple(col) + (255,))
        gloss = Image.new("RGBA", im.size, (0, 0, 0, 0))  # soft highlight, blended (not painted over)
        ImageDraw.Draw(gloss).ellipse([c - R * 0.6, c - R * 0.88, c + R * 0.6, c - R * 0.22], fill=(255, 255, 255, 70))
        im.alpha_composite(gloss.filter(ImageFilter.GaussianBlur(6 * s)))
        im = im.resize((size, size), Image.LANCZOS)
        q = text_img(mark, 130, (255, 255, 255), "Black", shadow=True)
        im.alpha_composite(q, ((size - q.width) // 2, (size - q.height) // 2 + 4))
        return im

    def _pill(self, txt, col):
        t = text_img(txt, 52, col, shadow=False, max_w=self.max_w - 60)
        w, h = t.width + 30, 108
        s = 2
        im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fill = (255, 255, 255, 215) if self.light else (8, 12, 24, 170)
        d.rounded_rectangle([3 * s, 3 * s, (w - 3) * s, (h - 3) * s], h * s // 2, fill=fill,
                            outline=tuple(col) + (255,), width=4 * s)
        im = im.resize((w, h), Image.LANCZOS)
        im.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2 + 2))
        return im

    # ------------------------------------------------------------ frame
    def draw(self, frame, t):
        if not (self.t_in - 0.02 <= t <= self.t_out + 0.3):
            return
        hit = self.hit
        out = ease_io(prog(t, self.t_out, self.t_out + 0.28))  # exit: zoom toward the viewer + fade
        vis = 1 - out
        zoom = 1 + 0.35 * out
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)

        # light streaks rushing toward the title before the impact
        for x0, side, delay, ln in self.streaks:
            p = prog(t, self.t_in + delay, hit)
            if 0 < p < 1:
                e = _ease_out(p)
                x = 540 + x0 * (1 - e)
                y = self.cy + side * (1100 * (1 - e) + 40)
                a = int(200 * math.sin(p * math.pi))
                d.line([(x, y), (x, y + side * ln * (1 - e) + side * 10)], fill=self.accent + (a,), width=5)

        # badge: pops in, floats, glows
        pb = prog(t, self.t_in + 0.05, self.t_in + 0.45)
        if pb > 0:
            fl = math.sin(t * 2.6) * 10
            sc = (0.2 + 0.8 * ease_out_back(pb)) * zoom
            wob = math.sin(t * 3.1) * 6 * pb
            halo = 0.55 + 0.25 * math.sin(t * 4)
            paste(ov, self.halo, 540, self.badge_y + fl, sc * (1 + 0.08 * math.sin(t * 4)), halo * pb * vis)
            b = self.badge.rotate(wob, Image.BICUBIC) if abs(wob) > 0.3 else self.badge
            paste(ov, b, 540, self.badge_y + fl - 260 * out, sc, min(1, pb * 2) * vis)

        # flash + shockwave at the impact
        pf = prog(t, hit, hit + 0.35)
        if 0 < pf < 1:
            paste(ov, self.flash, 540, self.cy, 0.6 + 1.2 * pf, (1 - pf) ** 2)
            r = 120 + 720 * _ease_out(pf)
            wd = max(2, int(26 * (1 - pf)))
            d.ellipse([540 - r, self.cy - r * 0.55, 540 + r, self.cy + r * 0.55], outline=self.accent + (int(230 * (1 - pf)),),
                      width=wd)
            r2 = 80 + 480 * _ease_out(prog(t, hit + 0.06, hit + 0.4))
            d.ellipse([540 - r2, self.cy - r2 * 0.55, 540 + r2, self.cy + r2 * 0.55],
                      outline=(255, 255, 255, int(160 * (1 - pf))), width=max(2, wd // 2))

        # spark burst
        ps = prog(t, hit, hit + 0.9)
        if 0 < ps < 1:
            e = _ease_out(ps)
            for ang, dist, rad, col in self.sparks:
                x = 540 + math.cos(ang) * dist * e
                y = self.cy + math.sin(ang) * dist * e * 0.75 + 140 * ps * ps
                rr = rad * (1 - ps * 0.7)
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=tuple(col) + (int(255 * (1 - ps)),))

        # twinkles after the impact
        if t > hit:
            k = prog(t, hit, hit + 0.5) * vis
            for x, y, ph, sz in self.twinkles:
                a = max(0.0, math.sin(t * 3.2 + ph)) ** 3 * k
                if a > 0.05:
                    s = sz * (0.6 + 0.6 * a)
                    c = (255, 255, 255, int(220 * a))
                    d.line([(x - s * 2, y), (x + s * 2, y)], fill=c, width=3)
                    d.line([(x, y - s * 2), (x, y + s * 2)], fill=c, width=3)
        frame.alpha_composite(ov)

        # title: slams in from big + blurry-ish to its place, small shake, then breathes
        pt = prog(t, self.t_in + 0.12, hit)
        if pt > 0:
            sc = 2.3 - 1.3 * ease_io(pt) if t < hit else 1 + 0.06 * math.exp(-(t - hit) * 9) * math.cos((t - hit) * 30)
            sc *= 1 + 0.012 * math.sin(max(0, t - hit) * 2.2)
            shake = 0 if t < hit else 12 * math.exp(-(t - hit) * 10) * math.sin((t - hit) * 70)
            img = self.title
            if self.t_in + 0.9 < t < self.t_in + 1.5 and not self.light:
                img = self._shine(prog(t, self.t_in + 0.95, self.t_in + 1.45))
            paste(frame, img, 540 + shake, self.cy + shake * 0.4 - 40 * out, sc * zoom, min(1, pt * 1.6) * vis)

        # accent bar under the title
        pbar = ease_io(prog(t, hit + 0.15, hit + 0.45))
        if pbar > 0:
            bw = int(min(330, self.text_w * 0.38) * pbar)
            bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bar)
            bd.rounded_rectangle([540 - bw, self.bar_y - 5, 540 + bw, self.bar_y + 5], 5,
                                 fill=self.accent + (int(255 * vis),))
            dot = 9 * pbar
            for sx in (-1, 1):
                x = 540 + sx * (bw + 22)
                bd.ellipse([x - dot, self.bar_y - dot, x + dot, self.bar_y + dot], fill=self.accent + (int(255 * vis),))
            frame.alpha_composite(bar)

        # subtitle pill slides up
        if self.sub is not None:
            pp = prog(t, hit + 0.25, hit + 0.6)
            if pp > 0:
                y = self.sub_y + 60 * (1 - _ease_out(pp)) + 120 * out
                pulse = 1 + 0.02 * math.sin(max(0, t - hit) * 5)
                paste(frame, self.sub, 540, y, (0.9 + 0.1 * ease_out_back(pp)) * pulse * zoom, min(1, pp * 1.5) * vis)

    def _shine(self, p):
        """The title with a diagonal light band at position p (0..1)."""
        h, w = self.alpha.shape
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        pos = -0.2 * w + p * 1.5 * w
        band = np.exp(-(((xx + yy * 0.45) - pos) / 38.0) ** 2) * self.alpha * 0.85
        layer = np.zeros((h, w, 4), np.uint8)
        layer[..., :3] = 255
        layer[..., 3] = (band * 255).astype(np.uint8)
        im = self.title.copy()
        im.alpha_composite(Image.fromarray(layer, "RGBA"))
        return im
