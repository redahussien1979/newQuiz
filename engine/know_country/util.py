"""Drawing helpers for the Know a Country video: fonts, easing, outlined Arabic/English text, chips, pins."""

import math, os

import numpy as np

from PIL import Image, ImageDraw, ImageFont

from ..core import HAS_RAQM, _prep  # Arabic: RAQM when available, else arabic-reshaper + python-bidi



HERE = os.path.dirname(os.path.abspath(__file__))

DATA = os.path.join(HERE, "data")

FONT_PATH = os.path.normpath(os.path.join(HERE, "..", "..", "fonts", "Cairo.ttf"))

W, H = 1080, 1920



_fonts = {}

def font(size, weight=800, script=None):
    """Cairo variable font at a given weight (cached)."""
    key = (size, weight)
    if key not in _fonts:
        f = ImageFont.truetype(FONT_PATH, size,
                               layout_engine=ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC)
        try:
            f.set_variation_by_axes([weight, 0])  # axes: weight, slant
        except Exception:
            pass
        _fonts[key] = f
    return _fonts[key]


def is_ar(s):
    return any("؀" <= c <= "ۿ" for c in s)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def pop(x):
    """0..1 -> scale with a small overshoot."""
    x = min(max(x, 0.0), 1.0)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


SUBREGION_AR = {'Eastern Asia': 'شرق آسيا', 'South-Eastern Asia': 'جنوب شرق آسيا', 'Southern Asia': 'جنوب آسيا', 'Central Asia': 'آسيا الوسطى', 'Western Asia': 'غرب آسيا', 'Northern Europe': 'شمال أوروبا', 'Western Europe': 'غرب أوروبا', 'Southern Europe': 'جنوب أوروبا', 'Eastern Europe': 'شرق أوروبا', 'Central Europe': 'وسط أوروبا', 'Southeast Europe': 'جنوب شرق أوروبا', 'Northern Africa': 'شمال أفريقيا', 'Western Africa': 'غرب أفريقيا', 'Eastern Africa': 'شرق أفريقيا', 'Middle Africa': 'وسط أفريقيا', 'Southern Africa': 'جنوب أفريقيا', 'North America': 'أمريكا الشمالية', 'Central America': 'أمريكا الوسطى', 'Caribbean': 'منطقة الكاريبي', 'South America': 'أمريكا الجنوبية', 'Australia and New Zealand': 'أستراليا ونيوزيلندا', 'Melanesia': 'ميلانيزيا', 'Micronesia': 'ميكرونيزيا', 'Polynesia': 'بولينيزيا'}


_icons, _flags = {}, {}
def icon(name, size, color=(255, 255, 255)):
    """Icon from data/icons (white PNG), recoloured and resized."""
    k = (name, size, color)
    if k not in _icons:
        p = os.path.join(DATA, "icons", f"{name}.png")
        if not os.path.exists(p):
            p = os.path.join(DATA, "icons", "package.png")
        a = Image.open(p).convert("RGBA").getchannel("A").resize((size, size), Image.LANCZOS)
        im = Image.new("RGBA", (size, size), tuple(color) + (0,))
        im.putalpha(a)
        _icons[k] = im
    return _icons[k]

def flag(cca2, w):
    """Flag from data/flags (4:3 PNG) with rounded corners."""
    k = (cca2, w)
    if k not in _flags:
        h = int(w * 3 / 4)
        p = os.path.join(DATA, "flags", f"{cca2}.png")
        im = Image.open(p).convert("RGBA").resize((w, h), Image.LANCZOS) if os.path.exists(p) else Image.new("RGBA", (w, h), (90, 90, 90, 255))
        m = Image.new("L", (w * 2, h * 2), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), radius=w // 7, fill=255)
        im.putalpha(m.resize((w, h), Image.LANCZOS))
        _flags[k] = im
    return _flags[k]


def background():
    global _bg
    if _bg is None:
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((x - W / 2) / W) ** 2 + ((y - H * 0.42) / H) ** 2)
        t = np.clip(d / 0.75, 0, 1)[..., None]
        arr = np.array((20, 36, 66), np.float32) * (1 - t) + np.array((8, 14, 28), np.float32) * t
        rng = np.random.default_rng(7)
        for _ in range(260):
            sx, sy = rng.integers(0, W), rng.integers(0, H)
            b = rng.uniform(40, 140)
            arr[sy, sx] = np.minimum(arr[sy, sx] + b, 255)
        _bg = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    return _bg.copy()


_bg = None

WH, INK = (255, 255, 255), (10, 16, 34)

Y, CY, PK, GR, PU = (255, 214, 10), (64, 216, 255), (255, 77, 141), (46, 214, 120), (150, 112, 255)

CHIP_COLORS = [Y, CY, PK, GR]

_d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

def _f(s, size, weight):
    return font(size, weight, "ar" if is_ar(s) else "en")


def seg_w(t, size, weight):
    t2, kw = _prep(t)
    return _d0.textlength(t2, font=_f(t, size, weight), **kw)


def line(img, segs, size, cx, cy, align="c", alpha=1.0, scale=1.0, weight=800, stroke=INK, sw=None, max_w=960):
    """One line of coloured segments [(text, colour)], outlined; RTL order when Arabic."""
    if alpha <= 0.01 or scale <= 0.05 or not segs:
        return 0
    if isinstance(segs, str):
        segs = [(segs, WH)]
    size = max(8, int(size * scale))
    widths = [seg_w(t, size, weight) for t, _ in segs]
    total = sum(widths) + size * 0.25 * (len(segs) - 1)
    if max_w and total > max_w * scale:  # shrink to fit the frame
        size = max(8, int(size * max_w * scale / total))
        widths = [seg_w(t, size, weight) for t, _ in segs]
    sw = (max(2, round(size * 0.085)) if sw is None else sw) if stroke else 0
    rtl = any(is_ar(t) for t, _ in segs)
    space = size * 0.25
    total = sum(widths) + space * (len(segs) - 1)
    asc, desc = _f(segs[0][0], size, weight).getmetrics()
    pad = sw + 6
    layer = Image.new("RGBA", (int(total + 2 * pad) + 2, int(asc + desc + 2 * pad)), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    order = list(zip(segs, widths))[::-1] if rtl else list(zip(segs, widths))
    x = pad
    for (t, col), w in order:
        t2, kw = _prep(t)
        dr.text((x, pad), t2, font=_f(t, size, weight), fill=col + (255,), **kw,
                stroke_width=sw, stroke_fill=(stroke + (255,)) if stroke else None)
        x += w + space
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    x0 = cx - layer.width / 2 if align == "c" else (cx - layer.width + pad if align == "r" else cx - pad)
    img.alpha_composite(layer, (int(x0), int(cy - layer.height / 2)))
    return total


def rich_segs(s, base, accent):
    segs, hl = [], False
    for part in s.split("*"):
        if hl and part.strip():
            segs.append((part.strip(), accent))  # keep a highlighted phrase together on one line
        else:
            segs += [(w, base) for w in part.split()]
        hl = not hl
    return segs


def rich(img, s, size, cx, cy, max_w=940, base=WH, accent=Y, lh=1.35, **kw):
    segs = rich_segs(s, base, accent)
    weight = kw.get("weight", 800)
    lines, cur, cw = [], [], 0
    for sg in segs:
        w = seg_w(sg[0], size, weight) + size * 0.25
        if cur and cw + w > max_w:
            lines.append(cur); cur, cw = [], 0
        cur.append(sg); cw += w
    if cur:
        lines.append(cur)
    y0 = cy - size * lh * (len(lines) - 1) / 2
    for i, ln in enumerate(lines):
        line(img, ln, size, cx, y0 + i * size * lh, **kw)


def chip(img, text, size, cx, cy, bg, fg=INK, alpha=1.0, scale=1.0, icon_name=None, rich_text=False):
    if alpha <= 0.01 or scale <= 0.05:
        return None
    size_s = max(8, int(size * scale))
    segs = rich_segs(text, fg, WH if bg != WH else Y) if rich_text else [(text, fg)]
    tw = sum(seg_w(t, size_s, 800) for t, _ in segs) + size_s * 0.25 * (len(segs) - 1)
    ic = int(size_s * 1.05) if icon_name else 0
    gap = size_s * 0.35 if icon_name else 0
    px, h = size_s * 0.7, size_s * 1.75
    w = tw + ic + gap + 2 * px
    x0, y0 = cx - w / 2, cy - h / 2
    a = int(255 * alpha)
    lay = Image.new("RGBA", (int(w) + 12, int(h) + 12), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    dr.rounded_rectangle((8, 9, w + 8, h + 9), radius=h / 2, fill=(0, 0, 0, int(a * 0.45)))
    dr.rounded_rectangle((0, 0, w, h), radius=h / 2, fill=bg + (a,), outline=WH + (a,), width=max(2, size_s // 14))
    img.alpha_composite(lay, (int(x0), int(y0)))
    tx = x0 + px + tw / 2
    if icon_name:
        im = icon(icon_name, ic, fg)
        if alpha < 1:
            im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
        img.alpha_composite(im, (int(x0 + w - px - ic), int(cy - ic / 2)))
    line(img, segs, size_s, tx, cy - size_s * 0.06, alpha=alpha, stroke=None)
    return (x0, y0, x0 + w, y0 + h)


def leader(img, p0, p1, alpha=1.0, color=WH):
    if alpha <= 0.01:
        return
    dr = ImageDraw.Draw(img)
    a = int(255 * alpha)
    dr.line([p0, p1], fill=INK + (int(a * 0.6),), width=9)
    dr.line([p0, p1], fill=color + (a,), width=4)
    x, y = p1
    dr.ellipse((x - 11, y - 11, x + 11, y + 11), fill=color + (a,), outline=INK + (a,), width=3)


def pin(img, x, y, color, alpha=1.0, scale=1.0, inner=None, inner_size=44):
    if alpha <= 0.01 or scale <= 0.05:
        return
    s = scale
    a = int(255 * alpha)
    r = 46 * s
    hy = y - 92 * s
    dr = ImageDraw.Draw(img)
    dr.ellipse((x - 16 * s, y - 6 * s, x + 16 * s, y + 6 * s), fill=(0, 0, 0, int(a * 0.4)))
    dr.polygon([(x - r * 0.62, hy + r * 0.62), (x + r * 0.62, hy + r * 0.62), (x, y)], fill=color + (a,), outline=WH + (a,))
    dr.ellipse((x - r, hy - r, x + r, hy + r), fill=color + (a,), outline=WH + (a,), width=max(2, int(5 * s)))
    if inner:
        line(img, [(inner, INK)], inner_size, x, hy - 2, alpha=alpha, scale=s, stroke=None)
    else:
        dr.ellipse((x - r * 0.38, hy - r * 0.38, x + r * 0.38, hy + r * 0.38), fill=INK + (a,))


def ripples(img, x, y, t, color=Y, alpha=1.0):
    dr = ImageDraw.Draw(img)
    for k in range(3):
        tt = t - k * 0.5
        if tt <= 0:
            continue
        q = (tt % 1.5) / 1.5
        r = 12 + q * 110
        dr.ellipse((x - r, y - r * 0.5, x + r, y + r * 0.5), outline=color + (int(230 * (1 - q) * alpha),), width=5)


def flag_badge(cca2, w):
    fl = flag(cca2, w)
    b = 7
    out = Image.new("RGBA", (fl.width + 2 * b, fl.height + 2 * b), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, out.width - 1, out.height - 1), radius=w // 6, fill=WH + (255,))
    out.alpha_composite(fl, (b, b))
    return out


def paste(img, im, cx, cy, alpha=1.0, scale=1.0):
    if alpha <= 0.01 or scale <= 0.02:
        return
    if scale != 1:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 1:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def gradients():
    global _grad
    if _grad is None:
        a = np.zeros((H, W), np.float32)
        y = np.arange(H, dtype=np.float32)[:, None]
        a += np.clip(1 - y / 300, 0, 1) * 150
        a += np.clip((y - 1120) / 520, 0, 1) ** 1.3 * 225
        arr = np.zeros((H, W, 4), np.uint8)
        arr[..., :3] = INK
        arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
        _grad = Image.fromarray(arr, "RGBA")
    return _grad


def cam_mix(a, b, k):
    dl = (b[0] - a[0] + 180) % 360 - 180
    return (a[0] + dl * k, lerp(a[1], b[1], k), math.exp(lerp(math.log(a[2]), math.log(b[2]), k)))


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


_grad = None
