"""Fancy question header for the Multiple Choice video: "Question i of n" glass pill + segmented progress bar.

    0.00  the pill pops in (overshoot), side ornaments draw outwards
    0.25  a light sweep runs across the pill
    ...   the current progress segment fills with the question's time; finished segments stay lit
    end   everything fades with the question card

Everything depends only on (i, u) (frames are rendered on several processes)."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import clamp, ease_out_back, paste, prog, shade, text_img, to_rgb

SS = 3  # supersampling for smooth edges


def _ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def _colorize(alpha, col, a=255):
    im = Image.new("RGBA", alpha.size, tuple(col) + (0,))
    im.putalpha(alpha.point(lambda v: v * a // 255))
    return im


def _vgrad(w, h, top, bot):
    """Vertical colour gradient (RGB image)."""
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t
    return Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8), "RGB")


class QuestionHeader:
    def __init__(self, accent, ink, light=False, rtl=True, y=285, bar_y=378):
        self.accent = to_rgb(accent)
        self.ink = to_rgb(ink)
        self.light = light
        self.rtl = rtl
        self.y, self.bar_y = y, bar_y
        self._pills = {}

    # ------------------------------------------------------------ assets
    def _text(self, txt):
        """Header text with a soft vertical gradient face (brighter at the top)."""
        if self.light:
            col = shade(self.accent, 0.42)
        else:
            col = tuple(min(255, int(v * 0.35 + 255 * 0.65)) for v in self.accent)  # pale accent, reads on dark glass
        t = text_img(txt, 48, col, "Black", shadow=False)
        arr = np.asarray(t, np.float32).copy()
        yy = np.linspace(0, 1, t.height, dtype=np.float32)[:, None]
        hi, lo = (1.0, 0.82) if self.light else (1.12, 0.86)
        arr[..., :3] = np.clip(arr[..., :3] * (hi + (lo - hi) * yy)[..., None], 0, 255)
        return Image.fromarray(arr.astype(np.uint8), "RGBA")

    def _pill(self, txt):
        """Glass pill: outer glow, gradient rim, gradient body, top gloss, text with a soft drop shadow."""
        if txt in self._pills:
            return self._pills[txt]
        t = self._text(txt)
        pad, h = 48, 92
        w = t.width + 2 * pad
        m = 40  # room for the glow
        W_, H_ = w + 2 * m, h + 2 * m
        im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))

        # outer glow
        g = Image.new("L", (W_, H_), 0)
        ImageDraw.Draw(g).rounded_rectangle([m, m, m + w, m + h], h // 2, fill=255)
        im.alpha_composite(_colorize(g.filter(ImageFilter.GaussianBlur(18)), self.accent, 70 if self.light else 120))
        # drop shadow
        im.alpha_composite(_colorize(g.filter(ImageFilter.GaussianBlur(8)), (0, 0, 0), 40 if self.light else 110), (0, 8))

        # body built at SS x, then scaled down
        sw, sh = w * SS, h * SS
        r = sh // 2
        rim_w = 4 * SS
        shape = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(shape).rounded_rectangle([0, 0, sw - 1, sh - 1], r, fill=255)
        inner = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(inner).rounded_rectangle([rim_w, rim_w, sw - 1 - rim_w, sh - 1 - rim_w], r - rim_w, fill=255)

        if self.light:
            rim = _vgrad(sw, sh, shade(self.accent, 1.1), shade(self.accent, 0.62))
            body = _vgrad(sw, sh, (255, 255, 255), shade((255, 250, 238), 0.97))
        else:
            rim = _vgrad(sw, sh, tuple(min(255, int(v * 0.5 + 127)) for v in self.accent), shade(self.accent, 0.55))
            body = _vgrad(sw, sh, shade(self.accent, 0.26), shade(self.accent, 0.07))
        card = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        card.paste(rim, (0, 0), shape)
        card.paste(body, (0, 0), inner)

        # top gloss (clipped to the inner shape)
        gl = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(gl).rounded_rectangle([rim_w + 18 * SS, rim_w + 4 * SS, sw - rim_w - 18 * SS, sh * 0.42],
                                             (sh * 0.42) // 2, fill=34 if not self.light else 140)
        gl = Image.fromarray(np.minimum(np.asarray(gl), np.asarray(inner)))
        card.alpha_composite(_colorize(gl.filter(ImageFilter.GaussianBlur(3 * SS)), (255, 255, 255)))
        card = card.resize((w, h), Image.LANCZOS)
        im.alpha_composite(card, (m, m))

        # text + subtle shadow
        tx, ty = m + (w - t.width) // 2, m + (h - t.height) // 2 + 2
        im.alpha_composite(_colorize(t.getchannel("A").filter(ImageFilter.GaussianBlur(3)), (0, 0, 0),
                                     60 if self.light else 150), (tx, ty + 3))
        im.alpha_composite(t, (tx, ty))
        mask = np.asarray(shape.resize((w, h), Image.LANCZOS), np.float32) / 255.0
        self._pills[txt] = (im, mask, m)
        return self._pills[txt]

    def _shine(self, pill, mask, m, p):
        """Pill with a diagonal light band at position p (0..1), clipped to the body."""
        h, w = mask.shape
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        if self.rtl:
            xx = w - xx
        pos = -0.25 * w + p * 1.5 * w
        band = np.exp(-(((xx + yy * 0.6) - pos) / 26.0) ** 2) * mask * (0.45 if not self.light else 0.6)
        layer = np.zeros((h, w, 4), np.uint8)
        layer[..., :3] = 255
        layer[..., 3] = (band * 255).astype(np.uint8)
        im = pill.copy()
        im.alpha_composite(Image.fromarray(layer, "RGBA"), (m, m))
        return im

    # ------------------------------------------------------------ frame
    def draw(self, frame, txt, i, n, u, D, alpha):
        if alpha <= 0.01:
            return
        pill, mask, m = self._pill(txt)
        pin = prog(u, 0.0, 0.4)
        sp = prog(u, 0.3, 1.0)
        img = self._shine(pill, mask, m, sp) if 0 < sp < 1 else pill
        scale = 0.6 + 0.4 * ease_out_back(pin)
        paste(frame, img, 540, self.y, scale, alpha * min(1, pin * 2))
        self._ornaments(frame, (pill.width - 2 * m) * scale / 2, prog(u, 0.15, 0.6), alpha)
        self._progress(frame, i, n, u, D, alpha)

    def _ornaments(self, frame, half_w, p, alpha):
        """Thin tapered lines with a diamond, drawn outwards from both sides of the pill."""
        if p <= 0:
            return
        e = _ease_out(p)
        L = 96 * e
        if L < 2:
            return
        lw, lh = 200, 30
        s = SS
        im = Image.new("RGBA", (lw * s, lh * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        col = shade(self.accent, 0.8) if self.light else self.accent
        cy = lh * s // 2
        steps = 24
        for k in range(steps):  # tapered line: faint + thin at the pill, solid + thicker at the diamond
            f0, f1 = k / steps, (k + 1) / steps
            a = int(255 * f1 ** 1.2)
            th = max(1, int((0.8 + 2.6 * f1) * s / 2))
            d.rectangle([f0 * L * s, cy - th, f1 * L * s + 1, cy + th], fill=col + (a,))
        dx = (L + 12) * s  # diamond at the outer end
        r = 9 * s * e
        d.polygon([(dx - r, cy), (dx, cy - r), (dx + r, cy), (dx, cy + r)], fill=col + (int(230 * e),))
        im = im.resize((lw, lh), Image.LANCZOS)
        gap = 16
        al = alpha * min(1, p * 2)
        paste(frame, im, 540 + half_w + gap + lw / 2, self.y, 1.0, al)
        paste(frame, im.transpose(Image.FLIP_LEFT_RIGHT), 540 - half_w - gap - lw / 2, self.y, 1.0, al)

    def _progress(self, frame, i, n, u, D, alpha):
        """Segmented bar: finished segments lit, the current one fills over the question, the rest dim tracks."""
        if n < 1:
            return
        gap = 10 if n <= 12 else 6
        total = min(620, max(240, n * 110))
        seg = (total - gap * (n - 1)) / n
        bh = 14
        m = 22  # glow room
        lw, lh = int(total + 2 * m), bh + 2 * m
        s = SS
        base = Image.new("RGBA", (lw * s, lh * s), (0, 0, 0, 0))
        glow = Image.new("L", (lw, lh), 0)
        d, dg = ImageDraw.Draw(base), ImageDraw.Draw(glow)
        track = (40, 30, 20, 45) if self.light else (255, 255, 255, 38)
        done_col = shade(self.accent, 0.8) if self.light else shade(self.accent, 0.78)
        lit = shade(self.accent, 1.15)
        fill_p = _ease_out(prog(u, 0.35, max(0.4, D - 0.35)))
        y0, y1 = m, m + bh
        head = None
        for k in range(n):
            slot = (n - 1 - k) if self.rtl else k
            x0 = m + slot * (seg + gap)
            x1 = x0 + seg
            rr = bh / 2 * s
            d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], rr, fill=track)
            if k < i:
                d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], rr, fill=done_col + (255,))
            elif k == i:
                fw = max(bh, seg * (0.08 + 0.92 * fill_p))
                fx0, fx1 = (x1 - fw, x1) if self.rtl else (x0, x0 + fw)
                d.rounded_rectangle([fx0 * s, y0 * s, fx1 * s, y1 * s], rr, fill=lit + (255,))
                d.rounded_rectangle([fx0 * s + 3 * s, y0 * s + 2 * s, fx1 * s - 3 * s, y0 * s + bh * 0.42 * s],
                                    rr * 0.5, fill=(255, 255, 255, 110))  # gloss strip
                dg.rounded_rectangle([fx0, y0, fx1, y1], bh / 2, fill=255)
                head = fx0 if self.rtl else fx1
        im = base.resize((lw, lh), Image.LANCZOS)
        out = _colorize(glow.filter(ImageFilter.GaussianBlur(8)), self.accent, 150 if not self.light else 90)
        if head is not None:  # bright pulsing spark at the leading edge of the fill
            pulse = 0.75 + 0.25 * math.sin(u * 7)
            sp = Image.new("L", (lw, lh), 0)
            r = 9
            ImageDraw.Draw(sp).ellipse([head - r, lh / 2 - r, head + r, lh / 2 + r], fill=int(255 * pulse))
            out.alpha_composite(_colorize(sp.filter(ImageFilter.GaussianBlur(6)), (255, 255, 255), 230))
        out.alpha_composite(im)
        p = prog(u, 0.1, 0.5)
        paste(frame, out, 540, self.bar_y, 0.85 + 0.15 * _ease_out(p), alpha * p)
