"""Design styles for the Multiple Choice template: backgrounds, card shapes, borders, glow and text colours."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import H, W, Stars, get_theme, make_bg, shade, to_rgb

STYLE_NAMES = ["Classic", "Neon", "Glass", "Game Show", "Paper", "Sunset",
               "Minimal", "Luxury", "Clean Light", "Tech HUD", "Aurora", "Blueprint"]

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
    # --- professional looks
    "Minimal": dict(bg="minimal", ink=(240, 241, 245), card_text=(240, 241, 245), card=(30, 32, 38), card_alpha=255,
                    border=(64, 68, 78), bw=2, shape="card", glow=False, shadow="soft",
                    letters="outline", palette=[(210, 214, 222)] * 4, dim=0.35),
    "Luxury": dict(bg="luxury", ink=(246, 236, 214), card_text=(246, 236, 214), card=(16, 13, 10), card_alpha=245,
                   border=(212, 175, 96), bw=2, shape="cut", glow=False, shadow="soft",
                   letters="custom", badge=dict(fill=(16, 13, 10), line=(212, 175, 96), text=(232, 196, 110)),
                   palette=[(212, 175, 96)] * 4, dim=0.35),
    "Clean Light": dict(bg="clean", ink=(26, 32, 46), card_text=(26, 32, 46), card=(255, 255, 255), card_alpha=255,
                        border=(222, 227, 236), bw=2, shape="card", glow=False, shadow="soft",
                        letters="solid", palette=[(66, 133, 244), (16, 185, 129), (245, 158, 11), (139, 92, 246)],
                        dim=0.4, light=True),
    "Tech HUD": dict(bg="hud", ink=(220, 244, 255), card_text=(220, 244, 255), card=(6, 18, 32), card_alpha=225,
                     border=(0, 210, 255), bw=2, shape="cut", glow=True, shadow="none",
                     letters="outline", palette=[(0, 210, 255)] * 4, dim=0.3),
    "Aurora": dict(bg="aurora", ink=(255, 255, 255), card_text=(255, 255, 255), card=(8, 14, 28), card_alpha=190,
                   border=(255, 255, 255), border_alpha=70, bw=2, shape="card", glow=False, shadow="soft",
                   letters="glass", palette=["white"] * 4, dim=0.3),
    "Blueprint": dict(bg="blueprint", ink=(255, 255, 255), card_text=(255, 255, 255), card=(18, 54, 112),
                      card_alpha=240, border=(235, 244, 255), border_alpha=220, bw=2, shape="sharp", glow=False,
                      shadow="none", letters="outline", palette=[(235, 244, 255)] * 4, dim=0.3),
}

GREEN = (70, 215, 120)


def get_style(name):
    return STYLES.get(name or "Classic", STYLES["Classic"])


def with_theme_colors(st, theme_name):
    """Keep a style's shapes, borders, glow and badges, but take background and card colours from a theme."""
    if st["bg"] is None:  # Classic already uses the theme
        return st
    th = get_theme(theme_name)
    st = dict(st, theme_bg=True, ink=(245, 245, 250), card_text=(245, 245, 250), light=False, light_cards=False)
    if st["bg"] != "glass":  # glass keeps its see-through white cards
        st.update(card=th["card"], card_alpha=max(st["card_alpha"], 235))
    if st["border"] is not None and sum(to_rgb(st["border"])) < 200:  # dark ink border would vanish on a dark theme
        st.update(border=None, shadow="soft" if st["shadow"] == "hard" else st["shadow"])
    return st


# ------------------------------------------------------------------ shapes
def shape_box(d, box, shape, S2, **kw):
    x0, y0, x1, y1 = box
    h = y1 - y0
    if shape == "hex":
        c = min(h / 2, 46 * S2)
        d.polygon([(x0 + c, y0), (x1 - c, y0), (x1, y0 + h / 2), (x1 - c, y1), (x0 + c, y1), (x0, y0 + h / 2)], **kw)
    elif shape == "cut":  # chamfered corners
        c = min(h / 3, 22 * S2)
        d.polygon([(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1),
                   (x0, y1 - c), (x0, y0 + c)], **kw)
    else:
        r = {"pill": h / 2, "sharp": 10 * S2, "card": 20 * S2}.get(shape, 34 * S2)
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
    elif mode == "custom":
        bd = st["badge"]
        d.ellipse(box, fill=tuple(bd["fill"]) + (255,), outline=tuple(bd["line"]) + (255,), width=3 * S2)
        tcol = tuple(bd["text"])
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


def _img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def _tint(arr, color, gx, gy, rx, ry, k):
    """Blend a soft elliptical glow of `color` into an RGB float array (no hard edges)."""
    yy, xx = np.mgrid[0:H, 0:W]
    g = (np.exp(-(((xx - gx) / rx) ** 2 + ((yy - gy) / ry) ** 2) * 2.0) * k)[..., None]
    return arr * (1 - g) + np.array(color, np.float32) * g


def _ribbon(color, phase, alpha=130):
    """A soft, wavy band of light (aurora)."""
    w, h = W + 700, 900
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(x, h / 2 + math.sin(x / 260.0 + phase) * 120 + math.sin(x / 97.0 + phase * 2) * 30) for x in range(0, w + 20, 20)]
    d.line(pts, fill=color + (alpha,), width=110, joint="curve")
    return im.filter(ImageFilter.GaussianBlur(55))


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

    _cache = {}

    def __init__(self, st, theme_name, accent):
        kind = None if st.get("theme_bg") else st["bg"]
        key = (kind, theme_name if kind is None else None)
        if key not in Backdrop._cache:  # backgrounds are fixed per style/theme: build each once
            Backdrop._cache[key] = self._build(kind, theme_name)
        self.__dict__.update(Backdrop._cache[key])

    def _build(self, kind, theme_name):
        self.kind = kind
        self.stars = None
        self.extra = []
        self.dust = None
        self.scan = None
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
        elif self.kind == "minimal":
            arr = _vignette(_grad([(22, 23, 28), (17, 18, 22), (11, 12, 15)]), 0.25)
            arr += np.random.default_rng(4).normal(0, 2.2, (H, W, 1))  # fine film grain
            self.base = _img(arr)
        elif self.kind == "luxury":
            yy, xx = np.mgrid[0:H, 0:W]
            r = np.clip(np.sqrt(((xx - 540) / 820.0) ** 2 + ((yy - 720) / 1250.0) ** 2), 0, 1)[..., None]
            a, b = np.array((48, 37, 20), np.float32), np.array((6, 5, 4), np.float32)
            img = _img(a + (b - a) * r ** 0.8)
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for k in range(-H, W, 28):  # faint diagonal pinstripes
                d.line([(k, 0), (k + H, H)], fill=(212, 175, 96, 9), width=2)
            for inset, al in ((34, 150), (46, 70)):  # double frame with corner marks
                d.rectangle([inset, inset, W - inset, H - inset], outline=(212, 175, 96, al), width=2)
            for cx, cy in ((34, 34), (W - 34, 34), (34, H - 34), (W - 34, H - 34)):
                d.regular_polygon((cx, cy, 11), 4, rotation=45, fill=(212, 175, 96, 200))
            self.base = Image.alpha_composite(img, ov)
            rng = np.random.default_rng(12)
            self.dust = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(1.2, 3.4), rng.uniform(14, 40),
                          rng.uniform(0, 6.28)) for _ in range(70)]
        elif self.kind == "clean":
            arr = _grad([(248, 249, 252), (240, 243, 248), (231, 236, 244)])
            for col, gx, gy, rx, ry, k in (((90, 140, 255), 1000, 80, 620, 560, 0.20),
                                           ((60, 200, 190), 60, 1820, 600, 560, 0.16)):
                arr = _tint(arr, col, gx, gy, rx, ry, k)
            self.base = _img(arr)
        elif self.kind == "hud":
            img = _img(_vignette(_grad([(5, 10, 20), (8, 20, 36), (4, 9, 18)]), 0.35))
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for y in range(20, H, 40):
                for x in range(20, W, 40):
                    d.point((x, y), fill=(0, 210, 255, 60))
            for rr, al in ((300, 26), (430, 18), (560, 12)):
                d.ellipse([540 - rr, 700 - rr, 540 + rr, 700 + rr], outline=(0, 210, 255, al), width=2)
            L, m = 70, 40
            for cx, cy, sx, sy in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
                d.line([(cx, cy), (cx + sx * L, cy)], fill=(0, 210, 255, 170), width=4)
                d.line([(cx, cy), (cx, cy + sy * L)], fill=(0, 210, 255, 170), width=4)
            for k in range(24):  # ruler ticks on the left edge
                y = 300 + k * 55
                d.line([(m, y), (m + (22 if k % 4 == 0 else 10), y)], fill=(0, 210, 255, 90), width=2)
            self.base = Image.alpha_composite(img, ov)
            band = np.zeros((160, W, 4), np.uint8)
            band[..., :3] = (0, 210, 255)
            band[..., 3] = (np.sin(np.linspace(0, np.pi, 160)) ** 2 * 26).astype(np.uint8)[:, None]
            self.scan = Image.fromarray(band, "RGBA")
        elif self.kind == "aurora":
            self.base = _img(_vignette(_grad([(3, 8, 18), (5, 10, 26), (6, 6, 22)]), 0.3))
            self.stars = Stars(n=110, seed=5)
            self.extra = [(_ribbon((60, 230, 170), 0.0), 0.0), (_ribbon((90, 140, 255), 1.3), 2.1),
                          (_ribbon((190, 90, 255), 2.4), 4.0)]
        elif self.kind == "blueprint":
            img = _img(_vignette(_grad([(24, 68, 134), (18, 56, 116), (11, 38, 88)]), 0.3))
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for k in range(0, max(W, H) + 1, 30):
                al = 40 if k % 150 == 0 else 14
                if k <= W:
                    d.line([(k, 0), (k, H)], fill=(255, 255, 255, al), width=1)
                d.line([(0, k), (W, k)], fill=(255, 255, 255, al), width=1)
            for rr in (150, 210):  # drafting circle + crosshair, bottom corner
                d.ellipse([W - 230 - rr, H - 330 - rr, W - 230 + rr, H - 330 + rr], outline=(255, 255, 255, 40), width=2)
            d.line([(W - 470, H - 330), (W + 10, H - 330)], fill=(255, 255, 255, 40), width=2)
            d.line([(W - 230, H - 570), (W - 230, H - 90)], fill=(255, 255, 255, 40), width=2)
            self.base = Image.alpha_composite(img, ov)
        return dict(self.__dict__)

    def draw(self, t):
        frame = self.base.copy()
        if self.stars:
            self.stars.draw(ImageDraw.Draw(frame), t, t * 20)
        if self.kind == "aurora":
            for k, (b, ph) in enumerate(self.extra):
                x = 540 + math.sin(t * 0.18 + ph) * 220
                y = 520 + k * 260 + math.sin(t * 0.3 + ph * 1.7) * 60
                self._paste_clip(frame, b, x, y)
        elif self.kind == "luxury":
            d = ImageDraw.Draw(frame)
            for x0, y0, r, sp, ph in self.dust:  # slow rising gold dust
                y = (y0 - t * sp) % H
                x = x0 + math.sin(t * 0.6 + ph) * 12
                b = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2.2 + ph))
                c = (int(90 + 150 * b), int(70 + 120 * b), int(30 + 60 * b), 255)
                d.ellipse([x - r / 2, y - r / 2, x + r / 2, y + r / 2], fill=c)
        elif self.kind == "hud":
            self._paste_clip(frame, self.scan, 540, (t * 260) % (H + 400) - 200)
        elif self.kind in ("glass", "neon"):
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
