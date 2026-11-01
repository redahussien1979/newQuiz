"""Countries: names, flags and outlines, plus true-size map drawing.

Outlines come from Natural Earth (public domain), flags from flagcdn.com (public domain); both are bundled
in data/ by tools/build_countries.py, so everything works offline.
A user can replace any outline with their own GeoJSON file (e.g. different borders).
"""
import json
import math
import os
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .core import ROOT, WHITE, shade, text_img, to_rgb

DATA = os.path.join(ROOT, "data")
EARTH_R = 6371.0
_db = None


def _load():
    global _db
    if _db is None:
        try:
            with open(os.path.join(DATA, "countries.json"), encoding="utf-8") as f:
                _db = json.load(f)
        except OSError:
            _db = {}
    return _db


def choices():
    """Dropdown choices: ('مصر · Egypt', 'EGY'), sorted by Arabic name; first entry = no country."""
    db = _load()
    items = sorted(db.items(), key=lambda kv: kv[1]["ar"])
    return [("— none —", "")] + [(f"{v['ar']} · {v['en']}", k) for k, v in items]


def info(code):
    return _load().get(str(code or "").strip().upper()) if code else None


def name(code, lang="ar"):
    c = info(code)
    return (c["ar"] if lang == "ar" else c["en"]) if c else ""


def flag_path(code):
    c = info(code)
    if not c or not c["iso2"]:
        return ""
    p = os.path.join(DATA, "flags", c["iso2"] + ".png")
    return p if os.path.isfile(p) else ""


# ---------------------------------------------------------------- outlines
def _rings_from_geojson(path):
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    geoms = []
    if g.get("type") == "FeatureCollection":
        geoms = [ft.get("geometry") or {} for ft in g.get("features", [])]
    elif g.get("type") == "Feature":
        geoms = [g.get("geometry") or {}]
    else:
        geoms = [g]
    rings = []
    for geom in geoms:
        if geom.get("type") == "Polygon":
            rings.append(geom["coordinates"][0])
        elif geom.get("type") == "MultiPolygon":
            rings += [p[0] for p in geom["coordinates"]]
    if not rings:
        raise ValueError(f"No polygon found in the outline file {os.path.basename(path)}.")
    return rings


def _main_part(rings):
    """Drop far-away overseas parts (French Guiana for France, Galápagos for Ecuador…) and specks."""
    span = max(x for r in rings for x, _ in r) - min(x for r in rings for x, _ in r)
    if span > 180:  # crosses the 180° meridian (Russia, Fiji, USA's Aleutians)
        rings = [[(x + 360 if x < 0 else x, y) for x, y in r] for r in rings]
    boxes = []
    for r in rings:
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        lat = math.radians((min(ys) + max(ys)) / 2)
        area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))) / 2 * math.cos(lat)
        boxes.append((min(xs), max(xs), min(ys), max(ys), area))
    big = max(range(len(rings)), key=lambda i: boxes[i][4])
    b = boxes[big]
    ext = max((b[1] - b[0]) * 111 * math.cos(math.radians((b[2] + b[3]) / 2)), (b[3] - b[2]) * 111)
    reach = max(800.0, 0.5 * ext)  # km: islands closer than this to the kept group stay

    def gap(i, j):
        a, c = boxes[i], boxes[j]
        lat = math.radians((a[2] + a[3] + c[2] + c[3]) / 4)
        dx = max(0.0, c[0] - a[1], a[0] - c[1]) * 111 * math.cos(lat)
        dy = max(0.0, c[2] - a[3], a[2] - c[3]) * 111
        return math.hypot(dx, dy)

    keep, todo = {big}, [big]
    while todo:
        i = todo.pop()
        for j in range(len(rings)):
            if j not in keep and gap(i, j) <= reach:
                keep.add(j)
                todo.append(j)
    min_area = boxes[big][4] * 2e-4
    return [rings[i] for i in sorted(keep) if i == big or boxes[i][4] >= min_area]


@lru_cache(maxsize=64)
def projected(code, outline=""):
    """Rings in km on a Lambert azimuthal equal-area projection (true relative areas), centred on (0, 0).
    Returns (rings, width_km, height_km)."""
    if outline and os.path.isfile(outline):
        rings = _rings_from_geojson(outline)
    else:
        c = info(code)
        if not c:
            return None
        rings = c["rings"]
    rings = _main_part([[(float(x), float(y)) for x, y in r] for r in rings])
    lons = [x for r in rings for x, _ in r]
    lats = [y for r in rings for _, y in r]
    l0, p0 = math.radians((min(lons) + max(lons)) / 2), math.radians((min(lats) + max(lats)) / 2)
    out = []
    for r in rings:
        pts = []
        for lon, lat in r:
            lam, phi = math.radians(lon), math.radians(lat)
            cosc = math.sin(p0) * math.sin(phi) + math.cos(p0) * math.cos(phi) * math.cos(lam - l0)
            k = math.sqrt(2 / max(1e-9, 1 + cosc))
            x = EARTH_R * k * math.cos(phi) * math.sin(lam - l0)
            y = EARTH_R * k * (math.cos(p0) * math.sin(phi) - math.sin(p0) * math.cos(phi) * math.cos(lam - l0))
            pts.append((x, -y))
        out.append(pts)
    xs = [x for r in out for x, _ in r]
    ys = [y for r in out for _, y in r]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[(x - cx, y - cy) for x, y in r] for r in out], max(xs) - min(xs), max(ys) - min(ys)


def _mask(rings, km_px, pad):
    S = 3
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    w = max(1, int((max(xs) - min(xs)) * km_px)) + 2 * pad
    h = max(1, int((max(ys) - min(ys)) * km_px)) + 2 * pad
    m = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(m)
    for r in rings:
        pts = [((x * km_px + w / 2) * S, (y * km_px + h / 2) * S) for x, y in r]
        if len(pts) > 2:
            d.polygon(pts, fill=255)
    m = m.resize((w, h), Image.LANCZOS)
    if m.getbbox() is None:  # smaller than a pixel: show a dot so it can still be found
        ImageDraw.Draw(m).ellipse([w / 2 - 2, h / 2 - 2, w / 2 + 2, h / 2 + 2], fill=255)
    return m


def _face(w, h, pad, col, flag):
    """Country surface: its flag (or a colour gradient) with a light sheen and darker lower edge."""
    if flag:
        fl = ImageOps.fit(Image.open(flag).convert("RGBA"), (max(1, w - 2 * pad + 40), max(1, h - 2 * pad + 40)),
                          Image.LANCZOS, centering=(0.3, 0.5))  # keep the hoist side (emblems, bands)
        face = Image.new("RGBA", (w, h), shade(col, 0.5) + (255,))
        face.paste(fl, (pad - 20, pad - 20))
    else:
        g = Image.linear_gradient("L").resize((w, h))
        face = Image.composite(Image.new("RGBA", (w, h), shade(col, 0.55) + (255,)),
                               Image.new("RGBA", (w, h), col + (255,)), g)
    grad = Image.linear_gradient("L").rotate(45, expand=True).resize((w, h))
    light = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    light.putalpha(ImageOps.invert(grad).point(lambda v: int(max(0, v - 150) * 0.45)))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dark.putalpha(grad.point(lambda v: int(max(0, v - 120) * 0.55)))
    return Image.alpha_composite(Image.alpha_composite(face, light), dark)


@lru_cache(maxsize=48)
def map_tile(code, outline, km_px, col, depth=14, glow=True, fill_alpha=255, flag=True):
    """A country at `km_px` pixels per km: flag-filled, with 3D thickness, rim and glow.
    The image is centred on the country's bounding box (bottom margin includes the thickness)."""
    pr = projected(code, outline)
    if pr is None:
        return None
    col = to_rgb(col)
    pad = 60 + depth
    m = _mask(pr[0], km_px, pad)
    w, h = m.size
    out = Image.new("RGBA", (w, h + depth), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 200), (0, depth + 10), m)
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(18)))
    if glow:
        gm = m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.85))
        gl = Image.new("RGBA", out.size, (0, 0, 0, 0))
        gl.paste(col + (255,), (0, depth // 2), gm)
        out = Image.alpha_composite(out, gl)
    for k in range(depth, 0, -1):  # thickness
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        layer.paste(shade(col, 0.30 + 0.25 * (1 - k / depth)) + (255,), (0, k), m)
        out = Image.alpha_composite(out, layer)
    face = _face(w, h, pad, col, flag_path(code) if flag else "")
    inner = ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(15)).filter(ImageFilter.GaussianBlur(6)))
    ish = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ish.putalpha(inner.point(lambda v: int(v * 0.45)))
    face = Image.alpha_composite(face, ish)
    face.putalpha(ImageChops.multiply(face.getchannel("A"), m.point(lambda v: int(v * fill_alpha / 255))))
    top = Image.new("RGBA", out.size, (0, 0, 0, 0))
    top.paste(face, (0, 0))
    out = Image.alpha_composite(out, top)
    rim = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(5)), m.filter(ImageFilter.MinFilter(3)))
    rl = Image.new("RGBA", out.size, (0, 0, 0, 0))
    rl.paste(WHITE + (235,), (0, 0), rim)
    return Image.alpha_composite(out, rl)


@lru_cache(maxsize=32)
def map_icon(code, outline="", col=(245, 197, 66), size=400):
    """Square transparent icon of the country (flag-filled) for the event cards."""
    pr = projected(code, outline)
    if pr is None:
        return None
    km_px = size * 0.62 / max(pr[1], pr[2], 1e-6)
    t = map_tile(code, outline, km_px, tuple(col), depth=8, glow=False)
    t = t.copy()
    t.thumbnail((size, size), Image.LANCZOS)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.alpha_composite(t, ((size - t.width) // 2, (size - t.height) // 2))
    return im


@lru_cache(maxsize=32)
def flag_round(code, size=60):
    p = flag_path(code)
    if not p:
        return None
    S = 3
    f = ImageOps.fit(Image.open(p).convert("RGBA"), (size * S, size * S), Image.LANCZOS)
    m = Image.new("L", f.size, 0)
    ImageDraw.Draw(m).ellipse([0, 0, f.width - 1, f.height - 1], fill=255)
    f.putalpha(m)
    ImageDraw.Draw(f).ellipse([0, 0, f.width - 1, f.height - 1], outline=WHITE + (255,), width=3 * S)
    return f.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- map-scene widgets
def name_tag(title, value, col, code="", rtl=True, max_w=430):
    """Pill: round flag + name + value."""
    col = to_rgb(col)
    fl = flag_round(code, 66) if code else None
    fs = 66 if fl else 0
    t1 = text_img(title, 44, WHITE, "Bold", shadow=False, max_w=max_w - fs - 70)
    t2 = text_img(value, 36, col, "Black", shadow=False, max_w=max_w - fs - 70)
    tw = max(t1.width, t2.width)
    w, h = tw + fs + (90 if fl else 70), max(fs, t1.height + t2.height) + 36
    S = 2
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], h * S // 2, fill=(14, 20, 40, 225),
                                         outline=col + (200,), width=3 * S)
    im = im.resize((w, h), Image.LANCZOS)
    if rtl:
        fx, tx = w - fs - 18, lambda t: w - fs - (36 if fl else 35) - t.width
    else:
        fx, tx = 18, lambda t: fs + (36 if fl else 35)
    if fl:
        im.alpha_composite(fl, (fx, (h - fs) // 2))
    im.alpha_composite(t1, (int(tx(t1)), h // 2 - t1.height + 4))
    im.alpha_composite(t2, (int(tx(t2)), h // 2 - 2))
    return im


def badge(txt, col):
    """Glowing ratio badge (× 2.1)."""
    col = to_rgb(col)
    t = text_img(txt, 92, (20, 20, 30), "Black", shadow=False)
    w, h = t.width + 80, t.height + 40
    S = 2
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], h * S // 2, fill=col + (255,))
    im = im.resize((w, h), Image.LANCZOS)
    im.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2))
    g = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
    a = Image.new("L", g.size, 0)
    ImageDraw.Draw(a).rounded_rectangle([40, 40, 40 + w, 40 + h], h // 2, fill=200)
    gl = Image.new("RGBA", g.size, col + (0,))
    gl.putalpha(a.filter(ImageFilter.GaussianBlur(18)))
    g = Image.alpha_composite(g, gl)
    g.alpha_composite(im, (40, 40))
    return g


@lru_cache(maxsize=8)
def ring(col, r=62):
    """Highlight ring around a country too small to spot."""
    im = Image.new("RGBA", (2 * r + 60, 2 * r + 60), (0, 0, 0, 0))
    c = r + 30
    d = ImageDraw.Draw(im)
    d.ellipse([c - r, c - r, c + r, c + r], outline=col + (255,), width=6)
    g = im.filter(ImageFilter.GaussianBlur(10))
    g.alpha_composite(im)
    ImageDraw.Draw(g).ellipse([c - r - 18, c - r - 18, c + r + 18, c + r + 18], outline=col + (110,), width=3)
    return g


@lru_cache(maxsize=8)
def globe_grid(accent):
    """Faint meridians/parallels and a soft spotlight behind the maps (full-frame RGBA layer)."""
    from .core import H, W
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cx, cy, r = 540, 1000, 760
    for k in range(-5, 6):
        x = abs(r * math.sin(k * math.pi / 12))
        d.ellipse([cx - x, cy - r, cx + x, cy + r], outline=(120, 160, 230, 26), width=2)
        y = r * math.sin(k * math.pi / 12)
        hw = math.sqrt(max(0.0, r * r - y * y))
        d.line([(cx - hw, cy + y), (cx + hw, cy + y)], fill=(120, 160, 230, 26), width=2)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(120, 160, 230, 40), width=2)
    a = Image.new("L", (W, H), 0)
    ImageDraw.Draw(a).ellipse([90, 560, 990, 1440], fill=70)
    spot = Image.new("RGBA", (W, H), tuple(accent) + (0,))
    spot.putalpha(a.filter(ImageFilter.GaussianBlur(160)))
    return Image.alpha_composite(lay, spot)


# ---------------------------------------------------------------- tile fill / side by side / VS intro
@lru_cache(maxsize=16)
def flat_tile(code, outline, km_px, col):
    """Small flat silhouette (flag-filled when there is a flag) used to fill a bigger country."""
    pr = projected(code, outline)
    m = _mask(pr[0], km_px, 4)
    fp = flag_path(code)
    if fp:
        face = ImageOps.fit(Image.open(fp).convert("RGBA"), m.size, Image.LANCZOS, centering=(0.3, 0.5))
    else:
        face = Image.new("RGBA", m.size, tuple(col) + (255,))
    face.putalpha(m)
    rim = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(3)), m)
    rl = Image.new("RGBA", m.size, (0, 0, 0, 0))
    rl.paste(WHITE + (230,), (0, 0), rim)
    return Image.alpha_composite(face, rl)


@lru_cache(maxsize=16)
def fill_cells(big_code, big_outline, small_code, small_outline, km_px, pad):
    """Centres (in the big tile's mask coordinates) of a hexagonal grid whose cells each have the area of the
    small country, kept where they fall inside the big one; ordered from the middle outwards."""
    big = _mask(projected(big_code, big_outline)[0], km_px, pad)
    small = _mask(projected(small_code, small_outline)[0], km_px, 4)
    area = sum(k * n for k, n in enumerate(small.histogram())) / 255.0
    if area < 4:
        return ()
    d = math.sqrt(area / (math.sqrt(3) / 2))
    cells, row, y = [], 0, d / 2
    while y < big.height:
        x = (d / 2) * (row % 2) + d / 4
        while x < big.width:
            if big.getpixel((int(x), int(y))) > 128:
                cells.append((x, y))
            x += d
        y += d * math.sqrt(3) / 2
        row += 1
    bb = big.getbbox() or (0, 0, big.width, big.height)
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    cells.sort(key=lambda c: math.hypot(c[0] - cx, c[1] - cy))
    return tuple(cells)


@lru_cache(maxsize=8)
def podium(col, w=420):
    """Glowing elliptical platform under a country (side-by-side scene)."""
    S = 2
    im = Image.new("RGBA", ((w + 40) * S, 120 * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([20 * S, 20 * S, (w + 20) * S, 100 * S], fill=shade(col, 0.35) + (255,),
                               outline=tuple(col) + (255,), width=3 * S)
    g = im.filter(ImageFilter.GaussianBlur(14 * S))
    g.alpha_composite(im)
    return g.resize((w + 40, 120), Image.LANCZOS)


@lru_cache(maxsize=8)
def vs_panel(code, col, side):
    """Half-screen slanted panel for the VS intro: the flag (or a colour gradient), darker towards the middle."""
    from .core import H, W
    fp = flag_path(code)
    if fp:
        fl = ImageOps.fit(Image.open(fp).convert("RGBA"), (W, H), Image.LANCZOS)
    else:
        g = Image.linear_gradient("L").resize((W, H))
        fl = Image.composite(Image.new("RGBA", (W, H), shade(col, 0.35) + (255,)),
                             Image.new("RGBA", (W, H), tuple(col) + (255,)), g)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    if side == "right":
        d.polygon([(620, 0), (W, 0), (W, H), (460, H)], fill=255)
    else:
        d.polygon([(0, 0), (600, 0), (440, H), (0, H)], fill=255)
    shadow = Image.linear_gradient("L").rotate(90 if side == "right" else -90).resize((W, H))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(shadow.point(lambda v: int(v * 0.55)))
    fl = Image.alpha_composite(fl, dark)
    fl = Image.alpha_composite(fl, Image.new("RGBA", (W, H), (5, 8, 20, 120)))
    fl.putalpha(mask)
    return fl


@lru_cache(maxsize=4)
def vs_bolt(col):
    """Lightning along the diagonal split of the VS intro."""
    from .core import H, W
    pts, y, x = [], 0, 610
    while y < H:
        pts.append((x, y))
        y += 120
        x = 610 - (170 * y / H) + (40 if (y // 120) % 2 else -40)
    pts.append((450, H))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(im).line(pts, fill=(255, 255, 255, 255), width=10, joint="curve")
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).line(pts, fill=tuple(col) + (255,), width=40, joint="curve")
    return Image.alpha_composite(g.filter(ImageFilter.GaussianBlur(18)), im)
