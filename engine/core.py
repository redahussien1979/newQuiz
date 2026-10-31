"""Shared drawing, text, theme and encoding helpers used by every template."""
import math
import os
import re
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FONT = os.path.join(ROOT, "fonts", "Cairo.ttf")
W, H = 1080, 1920  # vertical Shorts / Reels / TikTok

# Arabic shaping: Pillow's RAQM engine when available, otherwise arabic-reshaper + python-bidi.
HAS_RAQM = features.check("raqm") and os.environ.get("VS_FORCE_BASIC") != "1"
_reshape = _bidi = None
if not HAS_RAQM:
    try:
        import arabic_reshaper
        _reshape = arabic_reshaper.reshape
        try:
            from bidi.algorithm import get_display as _bidi
        except ImportError:
            from bidi import get_display as _bidi
    except ImportError:
        pass

# ---------------------------------------------------------------- colors
COLORS = {
    "white": (245, 245, 250), "grey": (150, 160, 185), "sand": (226, 184, 102),
    "gold": (245, 197, 66), "blue": (90, 169, 255), "green": (80, 210, 140),
    "pink": (255, 110, 160), "red": (255, 90, 90), "purple": (170, 130, 255),
    "orange": (255, 150, 60), "cyan": (70, 220, 230),
}
COLOR_NAMES = list(COLORS)
WHITE, GREY = COLORS["white"], COLORS["grey"]


def to_rgb(c, default="white"):
    if c is None or (isinstance(c, str) and not c.strip()):
        return COLORS[default]
    if isinstance(c, (tuple, list)):
        return tuple(int(v) for v in c[:3])
    c = str(c).strip().lower()
    if c in COLORS:
        return COLORS[c]
    if re.fullmatch(r"#?[0-9a-f]{6}", c):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    nums = re.findall(r"[\d.]+", c)  # rgb(...) / rgba(...)
    if c.startswith("rgb") and len(nums) >= 3:
        return tuple(int(float(v)) for v in nums[:3])
    return COLORS[default]


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


# ---------------------------------------------------------------- themes
THEMES = {
    "Night Sky": dict(top=(8, 12, 30), mid=(18, 28, 60), bot=(5, 7, 18), card=(18, 26, 48), stars=True),
    "Desert Night": dict(top=(26, 14, 8), mid=(62, 36, 18), bot=(12, 7, 4), card=(42, 26, 16), stars=True),
    "Emerald": dict(top=(4, 22, 18), mid=(10, 52, 42), bot=(3, 12, 10), card=(10, 38, 32), stars=True),
    "Deep Purple": dict(top=(14, 8, 30), mid=(42, 22, 72), bot=(8, 5, 18), card=(30, 20, 52), stars=True),
    "Charcoal": dict(top=(14, 14, 16), mid=(32, 32, 36), bot=(8, 8, 9), card=(30, 30, 34), stars=False),
}
THEME_NAMES = list(THEMES)


def get_theme(name):
    return THEMES.get(name or "Night Sky", THEMES["Night Sky"])


_bg_cache = {}


def make_bg(theme):
    key = (theme["top"], theme["mid"], theme["bot"])
    if key in _bg_cache:
        return _bg_cache[key].copy()
    y = np.linspace(0, 1, H)[:, None]
    top, mid, bot = (np.array(theme[k], float) for k in ("top", "mid", "bot"))
    col = np.where(y < 0.55, top + (mid - top) * (y / 0.55), mid + (bot - mid) * ((y - 0.55) / 0.45))
    arr = np.repeat(col[:, None, :], W, axis=1)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - 540) / 700.0) ** 2 + ((yy - 1000) / 1150.0) ** 2)
    arr = arr * np.clip(1.15 - 0.55 * r ** 2, 0.35, 1.1)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    _bg_cache[key] = img
    return img.copy()


class Stars:
    def __init__(self, n=170, seed=7):
        rng = np.random.default_rng(seed)
        self.s = [(rng.uniform(0, W * 3), rng.uniform(0, H), rng.uniform(1, 3.2),
                   rng.uniform(0.15, 0.9), rng.uniform(0, 6.28)) for _ in range(n)]

    def draw(self, d, t, shift):
        for x0, y0, r, b, ph in self.s:
            x = (x0 - shift * 0.35 * r) % (W * 3) - W
            if 0 <= x <= W:
                c = int(255 * b * (0.7 + 0.3 * math.sin(t * 2 + ph)))
                d.ellipse([x - r / 2, y0 - r / 2, x + r / 2, y0 + r / 2], fill=(c, c, min(255, c + 20), 255))


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else float(t >= b)


def ease_io(x):
    x = clamp(x)
    return 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out_back(x):
    x = clamp(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def nice_step(x):
    if x <= 0:
        return 1.0
    k = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        if m * k >= x:
            return m * k
    return 10 * k


# ---------------------------------------------------------------- fonts & text
_state = {"font": DEFAULT_FONT}
_fonts, _tcache = {}, {}
ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def set_font(path):
    path = path if path and os.path.isfile(path) else DEFAULT_FONT
    if path != _state["font"]:
        _state["font"] = path
        _fonts.clear()
        _tcache.clear()


def get_font(size, weight="Black"):
    k = (_state["font"], size, weight)
    if k not in _fonts:
        eng = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC
        f = ImageFont.truetype(_state["font"], size, layout_engine=eng)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass  # static (non-variable) font
        _fonts[k] = f
    return _fonts[k]


def is_rtl(txt):
    return bool(ARABIC_RE.search(txt or ""))


_cmaps = {}


def _font_cmap():
    path = _state["font"]
    if path not in _cmaps:
        try:
            from fontTools.ttLib import TTFont
            _cmaps[path] = set(TTFont(path, lazy=True).getBestCmap())
        except Exception:
            _cmaps[path] = None
    return _cmaps[path]


def _fix_missing_forms(txt):
    """Many fonts (e.g. Cairo) lack isolated presentation forms; fall back to the base letter."""
    cmap = _font_cmap()
    if not cmap:
        return txt
    import unicodedata
    out = []
    for ch in txt:
        if ch in "\n" or ord(ch) in cmap or not (0xFB50 <= ord(ch) <= 0xFEFF):
            out.append(ch)
            continue
        dec = unicodedata.decomposition(ch).split()
        base = "".join(chr(int(h, 16)) for h in dec if not h.startswith("<") and h != "0020")
        out.append(base[::-1] if len(base) > 1 else (base or ch))
    return "".join(out)


def _prep(txt):
    rtl = is_rtl(txt)
    if HAS_RAQM:
        return txt, ({"direction": "rtl", "language": "ar"} if rtl else {"direction": "ltr"})
    if rtl and _reshape and _bidi:
        return _fix_missing_forms(_bidi(_reshape(txt))), {}
    return txt, {}


_measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def text_bbox(txt, size, weight="Black"):
    t2, kw = _prep(txt)
    return _measure.textbbox((0, 0), t2, font=get_font(size, weight), **kw)


def text_width(txt, size, weight="Black"):
    l, _, r, _ = text_bbox(txt, size, weight)
    return r - l


def fit_size(txt, size, weight, max_w):
    while max_w and size > 18 and text_width(txt, size, weight) > max_w:
        size = int(size * 0.93)
    return size


def text_img(txt, size, color, weight="Black", shadow=True, max_w=None):
    """Render one line of text to a transparent RGBA image (cached)."""
    color = to_rgb(color)
    size = fit_size(txt, size, weight, max_w)
    k = (_state["font"], txt, size, color, weight, shadow)
    if k in _tcache:
        return _tcache[k]
    t2, kw = _prep(txt)
    f = get_font(size, weight)
    l, t_, r, b = _measure.textbbox((0, 0), t2, font=f, **kw)
    pad = 30
    im = Image.new("RGBA", (max(1, r - l) + pad * 2, max(1, b - t_) + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - l, pad - t_ + 6), t2, font=f, fill=(0, 0, 0, 190), **kw)
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(im).text((pad - l, pad - t_), t2, font=f, fill=color + (255,), **kw)
    _tcache[k] = im
    return im


def wrap(txt, size, weight, max_w):
    lines = []
    for para in str(txt).split("\n"):
        cur = ""
        for w in para.split():
            test = (cur + " " + w).strip()
            if cur and text_width(test, size, weight) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur)
    return lines


def ellipsize(txt, size, weight, max_w):
    if text_width(txt, size, weight) <= max_w:
        return txt
    words = txt.split()
    while len(words) > 1 and text_width(" ".join(words) + "…", size, weight) > max_w:
        words.pop()
    return " ".join(words) + "…"


def parse_lines(text, default_colors):
    """'[gold] some text' sets a line color; otherwise colors cycle through default_colors."""
    out = []
    for i, line in enumerate(l for l in str(text or "").splitlines() if l.strip()):
        m = re.match(r"^\s*\[([^\]]+)\]\s*(.*)$", line)
        if m:
            out.append((m.group(2).strip(), to_rgb(m.group(1))))
        else:
            out.append((line.strip(), to_rgb(default_colors[i % len(default_colors)])))
    return out


# ---------------------------------------------------------------- compositing
def fade(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    lut = [int(v * a) for v in range(256)]
    im.putalpha(im.getchannel("A").point(lut))
    return im


def composite(frame, im, x, y):
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.width, x + im.width), min(frame.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    frame.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def paste(frame, im, cx, cy, scale=1.0, alpha=1.0, anchor="c"):
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.01:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    im = fade(im, alpha)
    x = cx - im.width / 2 if anchor == "c" else (cx if anchor == "l" else cx - im.width)
    composite(frame, im, int(round(x)), int(round(cy - im.height / 2)))


def draw_scene(frame, t, scene):
    """scene = dict(t_in, t_out, lines=[(text, size, color, y)], shake=bool)."""
    t_in, t_out = scene["t_in"], scene["t_out"]
    if not (t_in - 0.01 <= t <= t_out + 0.25):
        return
    for i, (txt, size, col, y) in enumerate(scene["lines"]):
        if not txt:
            continue
        p = prog(t, t_in + i * 0.12, t_in + i * 0.12 + 0.35)
        out = 1 - prog(t, t_out, t_out + 0.22)
        dx = 0
        if scene.get("shake") and i == 0 and t < t_in + 0.5:
            dx = math.sin(t * 90) * 14 * (1 - prog(t, t_in + 0.05, t_in + 0.5))
        img = text_img(txt, size, col, max_w=960)
        paste(frame, img, 540 + dx, y, 0.75 + 0.25 * ease_out_back(p), min(p * 1.4, 1) * out)


def stack_lines(parsed, y0, big, small, limit=3):
    """Lay out parsed (text, color) lines from y0, shrinking when there are many."""
    parsed = parsed[:limit + 1]
    size = big if len(parsed) <= 2 else small
    pitch = int(size * 1.28)
    return [(txt, size, col, y0 + i * pitch) for i, (txt, col) in enumerate(parsed)]


def draw_ending(frame, t, t0, intro, qlines, cta, handle, accent):
    if t < t0:
        return
    a = ease_io(prog(t, t0, t0 + 0.5))
    frame.alpha_composite(Image.new("RGBA", (W, H), (4, 6, 16, int(215 * a))))
    y = 640
    items = []
    if intro:
        items.append((intro, 56, GREY, y, t0 + 0.2))
        y += 130
    n = len(qlines)
    size, pitch = (96, 115) if n <= 2 else (80, 98)
    for i, (txt, col) in enumerate(qlines):
        items.append((txt, size, col, y + i * pitch, t0 + 0.35 + 0.15 * i))
    last = y + (n - 1) * pitch if n else y - 130
    arrow_y = last + 205
    if cta:
        items.append((cta, 52, WHITE, arrow_y + 160, t0 + 1.0))
    if handle:
        items.append((handle, 46, GREY, arrow_y + 330, t0 + 1.3))
    for txt, sz, col, yy, ti in items:
        p = prog(t, ti, ti + 0.35)
        paste(frame, text_img(txt, sz, col, max_w=960), 540, yy, 0.8 + 0.2 * ease_out_back(p), min(1, p * 1.5))
    p = prog(t, t0 + 0.8, t0 + 1.1)
    if p > 0 and (n or cta):
        ay = arrow_y + math.sin(t * 5) * 14
        d = ImageDraw.Draw(frame)
        c = to_rgb(accent) + (int(255 * p),)
        d.line([(540, ay - 55), (540, ay + 30)], fill=c, width=12)
        d.polygon([(502, ay + 15), (578, ay + 15), (540, ay + 62)], fill=c)


def global_fade(frame, t, dur):
    if t < 0.12 or t > dur - 0.25:
        k = prog(t, 0, 0.12) if t < 0.12 else 1 - prog(t, dur - 0.25, dur)
        frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - k)))))


def draw_safe_zone(frame):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, int(H * 0.8), W, H], fill=(255, 40, 40, 70))
    d.rectangle([930, 900, W, int(H * 0.8)], fill=(255, 40, 40, 70))
    d.rectangle([0, 0, W, 160], fill=(255, 40, 40, 45))
    frame.alpha_composite(ov)
    return frame


# ---------------------------------------------------------------- encoding
def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    raise RuntimeError("FFmpeg not found. Run: pip install imageio-ffmpeg")


def encode(render, n_frames, fps, wav_path, out_path, progress=None):
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", wav_path,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n_frames):
            ff.stdin.write(render(i / fps).tobytes())
            if progress and i % 10 == 0:
                progress(i / n_frames)
        ff.stdin.close()
    except BrokenPipeError:
        pass
    err = ff.stderr.read().decode(errors="ignore")
    if ff.wait() != 0:
        raise RuntimeError("FFmpeg failed: " + err[-800:])
