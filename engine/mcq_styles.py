"""Design styles for the Multiple Choice template: backgrounds, card shapes, borders, glow and text colours."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import H, W, Stars, get_theme, make_bg, shade, to_rgb

STYLE_NAMES = ["Classic", "Neon", "Glass", "Game Show", "Paper", "Sunset"]

STYLES = {
    # bg: None = use the selected colour theme
    "Classic": dict(bg=None, ink=(245, 245, 250), card_text=(245, 245, 250), card=None, card_alpha=240,
                    border=None, bw=3, shape="round", glow=False, shadow="soft",
                    letters="solid", palette=["gold", "blue", "pink", "purple"], dim=0.35),
    "Neon": dict(bg="neon", ink=(240, 245, 255), card_text=(240, 245, 255), card=(8, 8, 20), card_alpha=235,
                 border=None, bw=3, shape="round", glow=True, shadow="none",
                 letters="outline", palette=["cyan", "pink", "green", "orange"], dim=0.28),
    "Glass": dict(bg="glass", ink=(255, 255, 255), card_text=(255, 255, 255), card=(255, 255, 255), card_alpha=38,
                  border=(255, 255, 255), border_alpha=120, bw=2, shape="pill", glow=False, shadow="soft",
                  letters="glass", palette=["white", "white", "white", "white"], dim=0.3),
    "Game Show": dict(bg="gameshow", ink=(255, 255, 255), card_text=(255, 255, 255), card=(12, 22, 78), card_alpha=245,
                      border=(240, 196, 80), bw=4, shape="hex", glow=True, shadow="soft",
                      letters="gold", palette=["gold", "gold", "gold", "gold"], dim=0.3, rail=True),
    "Paper": dict(bg="paper", ink=(32, 30, 40), card_text=(32, 30, 40), card=(255, 255, 255), card_alpha=255,
                  border=(32, 30, 40), bw=4, shape="sharp", glow=False, shadow="hard",
                  letters="solid", palette=["gold", "blue", "pink", "green"], dim=0.4, light=True),
    "Sunset": dict(bg="sunset", ink=(255, 255, 255), card_text=(40, 24, 60), card=(255, 255, 255), card_alpha=238,
                   border=(255, 255, 255), bw=0, shape="pill", glow=False, shadow="soft",
                   letters="solid", palette=["orange", "pink", "purple", "blue"], dim=0.45, light_cards=True),
}

GREEN = (70, 215, 120)


def get_style(name):
    return STYLES.get(name or "Classic", STYLES["Classic"])


# ------------------------------------------------------------------ shapes
def shape_box(d, box, shape, S2, **kw):
    x0, y0, x1, y1 = box
    h = y1 - y0
    if shape == "hex":
        c = min(h / 2, 46 * S2)
        d.polygon([(x0 + c, y0), (x1 - c, y0), (x1, y0 + h / 2), (x1 - c, y1), (x0 + c, y1), (x0, y0 + h / 2)], **kw)
    else:
        r = {"pill": h / 2, "sharp": 10 * S2}.get(shape, 34 * S2)
        d.rounded_rectangle(box, r, **kw)


def build_box(w, h, m, st, accent, correct=False, card=False):
    """Background shape for a card/option at scale 1, size (w+2m, h+2m)."""
    S2 = 2
    shape = st["shape"]
    if card and shape == "hex":
        shape = "round"
    if card and shape == "pill":
        shape = "round"
    border = to_rgb(st["border"]) if st["border"] is not None else accent
    if correct:
        border = GREEN
    fill = to_rgb(st["card"]) if st["card"] is not None else None
    im = Image.new("RGBA", ((w + 2 * m) * S2, (h + 2 * m) * S2), (0, 0, 0, 0))
    box = [m * S2, m * S2, (m + w) * S2, (m + h) * S2]
    if st["shadow"] == "soft":
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        shape_box(ImageDraw.Draw(sh), [box[0], box[1] + 14 * S2, box[2], box[3] + 14 * S2], shape, S2, fill=(0, 0, 0, 150))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(16 * S2)))
    elif st["shadow"] == "hard":
        shape_box(ImageDraw.Draw(im), [box[0] + 9 * S2, box[1] + 9 * S2, box[2] + 9 * S2, box[3] + 9 * S2], shape, S2,
                  fill=(32, 30, 40, 255))
    if st["glow"]:
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        shape_box(ImageDraw.Draw(g), box, shape, S2, outline=border + (255,), width=10 * S2)
        im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(10 * S2)))
    d = ImageDraw.Draw(im)
    if correct:
        f = (150, 232, 170) if (st.get("light") or st.get("light_cards")) else shade(GREEN, 0.3)
        fa = 255
    else:
        f = fill if fill is not None else (18, 26, 48)
        fa = st["card_alpha"]
    kw = dict(fill=f + (fa,))
    if st["bw"] or correct:
        kw.update(outline=border + (st.get("border_alpha", 255),), width=max(st["bw"], 4) * S2 if correct else st["bw"] * S2)
    shape_box(d, box, shape, S2, **kw)
    if st["bg"] == "glass" and not correct:  # top highlight
        hl = Image.new("RGBA", im.size, (0, 0, 0, 0))
        shape_box(ImageDraw.Draw(hl), [box[0] + 6 * S2, box[1] + 4 * S2, box[2] - 6 * S2, box[1] + (h * 0.45) * S2],
                  shape, S2, fill=(255, 255, 255, 22))
        im = Image.alpha_composite(im, hl)
    return im.resize((w + 2 * m, h + 2 * m), Image.LANCZOS)


def letter_badge(im, cx, cy, letter_img_fn, letter, col, st, correct):
    """Draw the A/B/C/D badge onto an option image (scale 1)."""
    S2 = 2
    b = Image.new("RGBA", (80 * S2, 80 * S2), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    box = [4 * S2, 4 * S2, 76 * S2, 76 * S2]
    mode = st["letters"]
    if correct:
        d.ellipse(box, fill=GREEN + (255,))
        d.line([(23 * S2, 41 * S2), (36 * S2, 54 * S2), (59 * S2, 27 * S2)], fill=(255, 255, 255, 255), width=9 * S2,
               joint="curve")
        b = b.resize((80, 80), Image.LANCZOS)
        im.alpha_composite(b, (int(cx - 40), int(cy - 40)))
        return
    if mode == "solid":
        d.ellipse(box, fill=col + (255,))
        tcol = (20, 20, 30)
    elif mode == "outline":
        d.ellipse(box, outline=col + (255,), width=5 * S2)
        tcol = col
    elif mode == "glass":
        d.ellipse(box, fill=(255, 255, 255, 60), outline=(255, 255, 255, 160), width=3 * S2)
        tcol = (255, 255, 255)
    else:  # gold
        d.ellipse(box, fill=(12, 22, 78, 255), outline=(240, 196, 80, 255), width=4 * S2)
        tcol = (240, 196, 80)
    b = b.resize((80, 80), Image.LANCZOS)
    im.alpha_composite(b, (int(cx - 40), int(cy - 40)))
    t = letter_img_fn(letter, 40, tcol)
    im.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))


# ------------------------------------------------------------------ backgrounds
def _grad(stops, diagonal=False):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    f = ((xx / W) * 0.45 + (yy / H) * 0.55) if diagonal else yy / H
    f = f[..., None]
    (a, b, c) = [np.array(s, np.float32) for s in stops]
    arr = np.where(f < 0.5, a + (b - a) * (f / 0.5), b + (c - b) * ((f - 0.5) / 0.5))
    return arr


def _vignette(arr, strength=0.5):
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - 540) / 700.0) ** 2 + ((yy - 960) / 1150.0) ** 2)
    return arr * np.clip(1.12 - strength * r ** 2, 0.3, 1.1)[..., None]


def _blob(radius, color, alpha=170):
    size = radius * 2 + 240
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([120, 120, 120 + radius * 2, 120 + radius * 2], fill=color + (alpha,))
    return im.filter(ImageFilter.GaussianBlur(radius * 0.45))


class Backdrop:
    """Static base image + per-frame animated layer for a style."""

    def __init__(self, st, theme_name, accent):
        self.kind = st["bg"]
        self.stars = None
        self.extra = []
        if self.kind is None:
            theme = get_theme(theme_name)
            self.base = make_bg(theme)
            self.stars = Stars(seed=21) if theme["stars"] else None
        elif self.kind == "neon":
            arr = _vignette(np.full((H, W, 3), (6, 6, 16), np.float32), 0.4)
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
            grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grid)
            for x in range(0, W + 1, 90):
                gd.line([(x, 0), (x, H)], fill=(255, 60, 200, 28), width=2)
            for y in range(0, H + 1, 90):
                gd.line([(0, y), (W, y)], fill=(60, 200, 255, 28), width=2)
            self.base = Image.alpha_composite(img, grid)
            self.extra = [(_blob(260, (255, 40, 180), 60), 0.0), (_blob(300, (40, 200, 255), 55), 2.0)]
        elif self.kind == "glass":
            arr = _grad([(22, 10, 48), (42, 16, 78), (10, 22, 60)])
            self.base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
            self.extra = [(_blob(330, (255, 80, 170)), 0.0), (_blob(300, (60, 200, 255)), 1.7),
                          (_blob(280, (160, 90, 255)), 3.1), (_blob(260, (255, 170, 60), 140), 4.4)]
        elif self.kind == "gameshow":
            yy, xx = np.mgrid[0:H, 0:W]
            r = np.clip(np.sqrt(((xx - 540) / 900.0) ** 2 + ((yy - 620) / 1300.0) ** 2), 0, 1)[..., None]
            a, b = np.array((50, 36, 140), np.float32), np.array((4, 4, 26), np.float32)
            arr = a + (b - a) * r
            self.base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
        elif self.kind == "paper":
            img = Image.new("RGBA", (W, H), (246, 240, 226, 255))
            d = ImageDraw.Draw(img)
            for y in range(20, H, 46):
                for x in range(20, W, 46):
                    d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(222, 212, 190, 255))
            self.base = img
        elif self.kind == "sunset":
            arr = _vignette(_grad([(255, 140, 80), (226, 66, 128), (92, 40, 168)], diagonal=True), 0.25)
            self.base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
            self.extra = [(_blob(90, (255, 255, 255), 50), k * 0.9) for k in range(8)]

    def draw(self, t):
        frame = self.base.copy()
        if self.stars:
            self.stars.draw(ImageDraw.Draw(frame), t, t * 20)
        if self.kind in ("glass", "neon"):
            for k, (b, ph) in enumerate(self.extra):
                x = 540 + math.sin(t * 0.35 + ph) * 380 + math.cos(t * 0.21 + ph * 2) * 120
                y = 960 + math.cos(t * 0.28 + ph * 1.3) * 700
                self._paste_clip(frame, b, x, y)
        elif self.kind == "sunset":
            for k, (b, ph) in enumerate(self.extra):
                x = (k * 157 + t * 18) % (W + 300) - 150
                y = (H + 200) - ((k * 263 + t * 40) % (H + 400))
                self._paste_clip(frame, b, x, y)
        elif self.kind == "gameshow":
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            cx, cy, R = 540, 620, 2400
            n = 18
            rot = t * 0.12
            for k in range(n):
                a0 = rot + k * 2 * math.pi / n
                a1 = a0 + math.pi / n
                d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)),
                           (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=(255, 255, 255, 14))
            frame.alpha_composite(ov)
        return frame

    @staticmethod
    def _paste_clip(frame, b, x, y):
        x, y = int(x - b.width / 2), int(y - b.height / 2)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + b.width), min(H, y + b.height)
        if x1 > x0 and y1 > y0:
            frame.alpha_composite(b.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))
