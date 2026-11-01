"""Real-Earth globe intro: an orthographic globe from NASA's Blue Marble image (public domain, data/earth.jpg),
lit, with an atmosphere glow; it rotates and zooms in to the compared countries, which light up."""
import math
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import countries as CT
from .core import H, ROOT, W, text_img

TEX_PATH = os.path.join(ROOT, "data", "earth.jpg")
SCALE = 0.5  # the globe is computed at half resolution (the texture is softer than the frame anyway)
_LIGHT = np.array([-0.45, 0.55, 0.70]) / np.linalg.norm([-0.45, 0.55, 0.70])
_tex = None


def available():
    return os.path.isfile(TEX_PATH)


def _texture():
    global _tex
    if _tex is None:
        _tex = np.asarray(Image.open(TEX_PATH).convert("RGB"))
    return _tex


@lru_cache(maxsize=1)
def _grid():
    w, h = int(W * SCALE), int(H * SCALE)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return xx, yy


@lru_cache(maxsize=1)
def stars():
    rng = np.random.default_rng(3)
    im = Image.new("RGBA", (W, H), (4, 6, 16, 255))
    d = ImageDraw.Draw(im)
    for _ in range(420):
        x, y, s = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.6, 2.2)
        b = int(rng.uniform(90, 255))
        d.ellipse([x - s, y - s, x + s, y + s], fill=(b, b, min(255, b + 25), 255))
    return im


def render(lon0, lat0, R, cy=960):
    """Full frame: stars + lit globe (radius R px, centred at (540, cy)) + atmosphere glow."""
    tex = _texture()
    th, tw = tex.shape[:2]
    xx, yy = _grid()
    r = R * SCALE
    xn = (xx - W * SCALE / 2) / r
    yn = -(yy - cy * SCALE) / r
    rho2 = xn * xn + yn * yn
    inside = rho2 <= 1.0
    z = np.sqrt(np.clip(1 - rho2, 0, 1))
    p0, l0 = math.radians(lat0), math.radians(lon0)
    lat = np.arcsin(np.clip(z * math.sin(p0) + yn * math.cos(p0), -1, 1))
    lon = l0 + np.arctan2(xn, z * math.cos(p0) - yn * math.sin(p0))
    u = ((np.degrees(lon) + 180.0) % 360.0) / 360.0 * tw - 0.5
    v = (90.0 - np.degrees(lat)) / 180.0 * th - 0.5
    u0 = np.floor(u).astype(np.int32)
    v0 = np.clip(np.floor(v).astype(np.int32), 0, th - 2)
    fu = (u - u0)[..., None]
    fv = (v - np.floor(v))[..., None]
    u0 %= tw
    u1 = (u0 + 1) % tw
    c = (tex[v0, u0] * (1 - fu) * (1 - fv) + tex[v0, u1] * fu * (1 - fv)
         + tex[v0 + 1, u0] * (1 - fu) * fv + tex[v0 + 1, u1] * fu * fv)
    lam = np.clip(xn * _LIGHT[0] + yn * _LIGHT[1] + z * _LIGHT[2], 0, 1)
    haze = ((1 - z) ** 3)[..., None]
    col = c * (0.28 + 0.85 * lam)[..., None] * (1 - 0.55 * haze) + np.array([90, 150, 255]) * 0.55 * haze
    rho = np.sqrt(rho2)
    glow = np.clip(1 - (rho - 1) / 0.09, 0, 1) ** 2 * (rho > 1)
    rgb = np.where(inside[..., None], col, glow[..., None] * np.array([70, 140, 255]) * 0.85)
    alpha = np.where(inside, 255, glow * 255)
    arr = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    g = Image.fromarray(arr, "RGBA").resize((W, H), Image.BICUBIC)
    frame = stars().copy()
    frame.alpha_composite(g)
    return frame


def to_screen(lon, lat, lon0, lat0, R, cy=960):
    """Arrays of lon/lat (degrees) -> screen x, y and visibility (front side of the globe)."""
    p0, l0 = math.radians(lat0), math.radians(lon0)
    p, lam = np.radians(lat), np.radians(lon)
    cosc = math.sin(p0) * np.sin(p) + math.cos(p0) * np.cos(p) * np.cos(lam - l0)
    x = R * np.cos(p) * np.sin(lam - l0)
    y = R * (math.cos(p0) * np.sin(p) - math.sin(p0) * np.cos(p) * np.cos(lam - l0))
    return 540 + x, cy - y, cosc > 0


@lru_cache(maxsize=32)
def geo_rings(code, outline=""):
    """Main-territory rings in lon/lat (same choice of parts as the true-size maps)."""
    if outline and os.path.isfile(outline):
        rings = CT._rings_from_geojson(outline)
    else:
        info = CT.info(code)
        if not info:
            return ()
        rings = info["rings"]
    rings = CT._main_part([[(float(x), float(y)) for x, y in r] for r in rings])
    return tuple(np.array([[x if x <= 180 else x - 360, y] for x, y in r], np.float64) for r in rings)


def plan(items):
    """items: [(code, outline)] -> (centre lon, centre lat, target radius px) so all of them fit on screen."""
    pts = [r for code, ol in items for r in geo_rings(code, ol)]
    if not pts:
        return None
    allp = np.vstack(pts)
    lon_c = math.degrees(math.atan2(np.mean(np.sin(np.radians(allp[:, 0]))), np.mean(np.cos(np.radians(allp[:, 0])))))
    lons = (allp[:, 0] - lon_c + 180) % 360 - 180
    lat_c = (allp[:, 1].min() + allp[:, 1].max()) / 2
    lon_c += (lons.min() + lons.max()) / 2
    span = max((lons.max() - lons.min()) * math.cos(math.radians(lat_c)), (allp[:, 1].max() - allp[:, 1].min()) * 0.8)
    ang = math.radians(max(span, 2.0) * 1.35)
    R = min(3200.0, max(520.0, 800.0 / ang))
    return lon_c, lat_c, R


def outlines(items, lon0, lat0, R, draw=1.0, fill=1.0, cy=960):
    """Glowing country borders on the globe. `draw` (0-1) traces the border on like a pen; `fill` fades in a soft
    colour fill. items: [(code, outline, colour)]."""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for code, ol, col in items:
        for ring in geo_rings(code, ol):
            x, y, vis = to_screen(ring[:, 0], ring[:, 1], lon0, lat0, R, cy)
            if not vis.all() or len(x) < 3:
                continue
            xy = list(zip(x.tolist(), y.tolist()))
            if fill > 0:
                d.polygon(xy, fill=tuple(col) + (int(80 * fill),))
            n = max(2, int(len(xy) * draw))
            d.line(xy[:n] + ([xy[0]] if draw >= 1 else []), fill=tuple(col) + (255,), width=6, joint="curve")
    return Image.alpha_composite(lay.filter(ImageFilter.GaussianBlur(10)), lay)


def label_points(items):
    """Label position (lon, lat) for each item: centre of its largest ring's bounding box."""
    out = []
    for code, ol in items:
        rings = geo_rings(code, ol)
        if not rings:
            out.append(None)
            continue
        big = max(rings, key=lambda r: (r[:, 0].max() - r[:, 0].min()) * (r[:, 1].max() - r[:, 1].min()))
        out.append(((big[:, 0].min() + big[:, 0].max()) / 2, (big[:, 1].min() + big[:, 1].max()) / 2))
    return out


@lru_cache(maxsize=32)
def tag(name, code, col, rtl=True):
    """Callout name tag: dark pill with a coloured border, round flag and name."""
    S = 2
    fl = CT.flag_round(code, 58) if code else None
    t = text_img(name, 46, (255, 255, 255), "Bold", shadow=False, max_w=420)
    w, h = t.width + (58 + 64 if fl else 56), 84
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], h * S // 2, fill=(10, 14, 30, 235),
                                         outline=tuple(col) + (255,), width=3 * S)
    im = im.resize((w, h), Image.LANCZOS)
    if fl and rtl:  # flag on the reading side
        im.alpha_composite(fl, (w - 58 - 14, (h - 58) // 2))
        im.alpha_composite(t, (w - 58 - 28 - t.width, (h - t.height) // 2))
    elif fl:
        im.alpha_composite(fl, (14, (h - 58) // 2))
        im.alpha_composite(t, (14 + 58 + 14, (h - t.height) // 2))
    else:
        im.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2))
    return im


@lru_cache(maxsize=1)
def hook_shade():
    """Soft, feathered dark shade behind the hook text at the top (no hard edges)."""
    sh = Image.new("RGBA", (W, H), (5, 8, 20, 0))
    a = np.clip(1 - np.abs(np.arange(H) - 360) / 300.0, 0, 1) ** 1.5 * 175
    sh.putalpha(Image.fromarray(a.astype(np.uint8)[:, None].repeat(W, 1), "L"))
    return sh


def callout_layout(anchors, tags, gap=22, max_w=1000.0):
    """Tags in one row away from the map, in the left-to-right order of their anchors (so leader lines never
    cross), packed by their real widths. anchors: [(x, y)]; returns ([(slot index -> tag x)], row y, scale)."""
    order = sorted(range(len(anchors)), key=lambda i: anchors[i][0])
    below = max(a[1] for a in anchors) + 230
    row_y = below if below < 1560 else min(a[1] for a in anchors) - 230
    total = sum(tags[i].width for i in order) + gap * (len(order) - 1)
    k = min(1.0, max_w / total)
    xs, x = {}, 540 - total * k / 2
    for i in order:
        xs[i] = x + tags[i].width * k / 2
        x += (tags[i].width + gap) * k
    return xs, row_y, k, order
