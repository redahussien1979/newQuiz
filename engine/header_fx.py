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


NUMBER_STYLES = [("Plain text", "plain"), ("Gold coin", "coin"), ("Two circles", "circles"),
                 ("Progress ring", "ring"), ("Hexagon gem", "gem"), ("Scoreboard", "score")]
NUMBER_KEYS = [k for _, k in NUMBER_STYLES]


class QuestionHeader:
    def __init__(self, accent, ink, light=False, rtl=True, y=285, bar_y=378, num_style="plain"):
        self.num_style = num_style if num_style in NUMBER_KEYS else "plain"
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

    # ------------------------------------------------------------ decorated numbers
    def _pale(self):
        return shade(self.accent, 0.42) if self.light else tuple(min(255, int(v * 0.35 + 255 * 0.65)) for v in self.accent)

    def _disc(self, size, top, bot):
        """Gradient disc mask-painted at SS x (RGBA, size*SS square)."""
        S = size * SS
        m = Image.new("L", (S, S), 0)
        ImageDraw.Draw(m).ellipse([0, 0, S - 1, S - 1], fill=255)
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        im.paste(_vgrad(S, S, top, bot), (0, 0), m)
        return im

    @staticmethod
    def _trim(im):
        """Cut the empty side margins of a text image (keeps its height so baselines line up)."""
        box = im.getchannel("A").getbbox()
        return im.crop((box[0], 0, box[2], im.height)) if box else im

    def _num(self, txt, size, col):
        return self._trim(text_img(str(txt), size, col, "Black", shadow=False))

    def _coin(self, num, d=74):
        """Glossy accent coin with a pale rim, an engraved inner ring and a dark number."""
        S = d * SS
        im = self._disc(d, tuple(min(255, int(v * 0.4 + 153)) for v in self.accent), shade(self.accent, 0.6))
        inner = self._disc(d - 10, shade(self.accent, 1.12), shade(self.accent, 0.72))
        im.alpha_composite(inner, (5 * SS, 5 * SS))
        dr = ImageDraw.Draw(im)
        k = 11 * SS
        dr.ellipse([k, k, S - 1 - k, S - 1 - k], outline=shade(self.accent, 0.55) + (150,), width=2 * SS)
        gl = Image.new("L", (S, S), 0)
        ImageDraw.Draw(gl).ellipse([S * 0.2, S * 0.08, S * 0.8, S * 0.45], fill=90)
        im.alpha_composite(_colorize(gl.filter(ImageFilter.GaussianBlur(4 * SS)), (255, 255, 255)))
        im = im.resize((d, d), Image.LANCZOS)
        t = self._num(num, int(d * 0.56), shade(self.accent, 0.22))
        im.alpha_composite(t, ((d - t.width) // 2, (d - t.height) // 2 + 2))
        return im

    def _outline_circle(self, num, d=64):
        S = d * SS
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        fill = (255, 255, 255, 255) if self.light else shade(self.accent, 0.12) + (255,)
        ImageDraw.Draw(im).ellipse([SS, SS, S - 1 - SS, S - 1 - SS], fill=fill, outline=self.accent + (255,), width=4 * SS)
        im = im.resize((d, d), Image.LANCZOS)
        t = self._num(num, int(d * 0.5), self._pale())
        im.alpha_composite(t, ((d - t.width) // 2, (d - t.height) // 2 + 2))
        return im

    def _ring(self, num, frac, d=76):
        """Dark disc with a faint track and an accent arc showing how far through the quiz we are."""
        S = d * SS
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        fill = (255, 255, 255, 255) if self.light else (12, 12, 20, 255)
        dr.ellipse([0, 0, S - 1, S - 1], fill=fill)
        w = 6 * SS
        box = [w / 2 + SS, w / 2 + SS, S - 1 - w / 2 - SS, S - 1 - w / 2 - SS]
        dr.ellipse(box, outline=(255, 255, 255, 45) if not self.light else (0, 0, 0, 35), width=w)
        if frac > 0:
            a0 = -90
            a1 = a0 + 360 * frac
            if self.rtl:  # fill counter-clockwise, like reading right to left
                a0, a1 = -90 - 360 * frac, -90
            dr.arc(box, a0, a1, fill=shade(self.accent, 1.1) + (255,), width=w)
        im = im.resize((d, d), Image.LANCZOS)
        glow = _colorize(im.getchannel("A").filter(ImageFilter.GaussianBlur(6)), self.accent, 90)
        out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        out.alpha_composite(glow)
        out.alpha_composite(im)
        t = self._num(num, int(d * 0.5), self._pale())
        out.alpha_composite(t, ((d - t.width) // 2, (d - t.height) // 2 + 2))
        return out

    def _gem(self, num, d=80):
        """Faceted hexagon: light facets on top, darker ones below, dark number."""
        S = d * SS
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        c, R = S / 2, S / 2 - SS
        pts = [(c + R * math.cos(math.radians(60 * k - 90)), c + R * math.sin(math.radians(60 * k - 90))) for k in range(6)]
        r2 = R * 0.62
        inner = [(c + r2 * math.cos(math.radians(60 * k - 90)), c + r2 * math.sin(math.radians(60 * k - 90))) for k in range(6)]
        dr.polygon(pts, fill=shade(self.accent, 0.5) + (255,))
        light = [1.25, 1.1, 0.8, 0.62, 0.75, 1.0]  # facet brightness, light from the top
        for k in range(6):
            dr.polygon([pts[k], pts[(k + 1) % 6], inner[(k + 1) % 6], inner[k]],
                       fill=tuple(min(255, int(v * light[k])) for v in self.accent) + (255,))
        dr.polygon(inner, fill=shade(self.accent, 1.05) + (255,))
        dr.polygon(pts, outline=tuple(min(255, int(v * 0.4 + 153)) for v in self.accent) + (255,), width=2 * SS)
        im = im.resize((d, d), Image.LANCZOS)
        t = self._num(num, int(d * 0.46), shade(self.accent, 0.2))
        im.alpha_composite(t, ((d - t.width) // 2, (d - t.height) // 2 + 2))
        return im

    def _segments(self, fmt, i, n):
        """Split 'السؤال {i} من {n}' into [('t', 'السؤال'), ('i',), ('t', 'من'), ('n',)] (reading order)."""
        out, rest = [], fmt
        while rest:
            a, b = rest.find("{i}"), rest.find("{n}")
            cands = [x for x in (a, b) if x >= 0]
            if not cands:
                out.append(("t", rest))
                break
            k = min(cands)
            if rest[:k].strip():
                out.append(("t", rest[:k]))
            out.append(("i",) if k == a else ("n",))
            rest = rest[k + 3:]
        return [o for o in out if o[0] != "t" or o[1].strip()]

    def _content(self, fmt, i, n):
        """The pill's inside for the chosen number style (the text itself for 'plain')."""
        style = self.num_style
        if style == "plain" or fmt is None:
            return None
        if style == "score":
            return self._scoreboard(fmt, i, n)
        pieces = []
        for seg in self._segments(fmt, i, n):
            if seg[0] == "t":
                pieces.append(self._trim(self._text(seg[1].strip())))
            elif seg[0] == "i":
                pieces.append({"coin": self._coin, "circles": self._coin, "gem": self._gem}.get(style, None)(i)
                              if style != "ring" else self._ring(i, i / max(1, n)))
            else:
                pieces.append(self._outline_circle(n) if style == "circles" else self._trim(self._text(str(n))))
        if self.rtl:
            pieces = pieces[::-1]
        gap = 18
        w = sum(p.width for p in pieces) + gap * (len(pieces) - 1)
        h = max(p.height for p in pieces)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = 0
        for p in pieces:
            im.alpha_composite(p, (x, (h - p.height) // 2))
            x += p.width + gap
        return im

    def _scoreboard(self, fmt, i, n):
        """Two-tone: the word on the pill, the numbers on a bright inset capsule ('3' big + '/ 3' small)."""
        word = " ".join(seg[1].strip() for seg in self._segments(fmt, i, n) if seg[0] == "t")
        word = word.split()[0] if word.split() else ""
        tw = self._trim(self._text(word))
        big = self._num(i, 54, shade(self.accent, 0.2))
        small = self._num(f"/{n}", 34, shade(self.accent, 0.35))
        cw, ch = big.width + small.width + 52, 70
        S = SS
        cap = Image.new("RGBA", (cw * S, ch * S), (0, 0, 0, 0))
        m = Image.new("L", cap.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, cw * S - 1, ch * S - 1], ch * S // 2, fill=255)
        cap.paste(_vgrad(cw * S, ch * S, tuple(min(255, int(v * 0.4 + 153)) for v in self.accent), shade(self.accent, 0.78)),
                  (0, 0), m)
        cap = cap.resize((cw, ch), Image.LANCZOS)
        x = (cw - big.width - small.width - 4) // 2
        cap.alpha_composite(big, (x, (ch - big.height) // 2 + 2))
        cap.alpha_composite(small, (x + big.width + 4, (ch - big.height) // 2 + 2 + big.height - small.height - 6))
        sp = Image.new("RGBA", (14, 1), (0, 0, 0, 0))  # extra room on the word's outer side
        pieces = [sp, tw, cap] if not self.rtl else [cap, tw, sp]
        gap = 22
        w = sum(p.width for p in pieces) + gap * 2
        h = max(p.height for p in pieces)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = 0
        for p in pieces:
            im.alpha_composite(p, (x, (h - p.height) // 2))
            x += p.width + gap
        return im

    def _pill(self, txt, fmt=None, i=0, n=0):
        """Glass pill: outer glow, gradient rim, gradient body, top gloss, text with a soft drop shadow."""
        key = (txt, self.num_style)
        if key in self._pills:
            return self._pills[key]
        content = self._content(fmt, i, n)
        t = content if content is not None else self._text(txt)
        pad, h = (48 if content is None else 26), 92
        if self.num_style == "score" and content is not None:
            pad = 11
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
        tx, ty = m + (w - t.width) // 2, m + (h - t.height) // 2 + (2 if content is None else 0)
        im.alpha_composite(_colorize(t.getchannel("A").filter(ImageFilter.GaussianBlur(3)), (0, 0, 0),
                                     60 if self.light else 150), (tx, ty + 3))
        im.alpha_composite(t, (tx, ty))
        mask = np.asarray(shape.resize((w, h), Image.LANCZOS), np.float32) / 255.0
        self._pills[key] = (im, mask, m)
        return self._pills[key]

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
    def draw(self, frame, txt, i, n, u, D, alpha, fmt=None):
        """txt = the formatted header; fmt = its template with {i} and {n} (needed for decorated numbers)."""
        if alpha <= 0.01:
            return
        pill, mask, m = self._pill(txt, fmt, i + 1, n)
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
