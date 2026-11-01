"""Built-in flat icons and the event card used by the timeline template."""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .core import WHITE, shade, text_img, to_rgb


def _pyramid(d, cx, cy, s, col):
    d.polygon([(cx, cy - 70 * s), (cx - 95 * s, cy + 55 * s), (cx, cy + 55 * s)], fill=shade(col, 1.08))
    d.polygon([(cx, cy - 70 * s), (cx + 95 * s, cy + 55 * s), (cx, cy + 55 * s)], fill=shade(col, 0.8))
    d.line([(cx - 120 * s, cy + 57 * s), (cx + 120 * s, cy + 57 * s)], fill=shade(col, 1.08), width=int(6 * s))


def _ankh(d, cx, cy, s, col):
    d.ellipse([cx - 32 * s, cy - 80 * s, cx + 32 * s, cy - 8 * s], outline=col, width=int(15 * s))
    d.rectangle([cx - 8 * s, cy - 14 * s, cx + 8 * s, cy + 80 * s], fill=col)
    d.rectangle([cx - 62 * s, cy - 8 * s, cx + 62 * s, cy + 8 * s], fill=col)


def _moon(d, cx, cy, s, col):
    d.ellipse([cx - 75 * s, cy - 60 * s, cx + 75 * s, cy + 90 * s], fill=(185, 200, 225))
    for ox, oy, r in [(-30, 0, 18), (25, 40, 14), (30, -20, 10), (-15, 55, 9)]:
        d.ellipse([cx + (ox - r) * s, cy + (oy - r) * s, cx + (ox + r) * s, cy + (oy + r) * s], fill=(150, 165, 195))
    d.rectangle([cx + 5 * s, cy - 115 * s, cx + 11 * s, cy - 40 * s], fill=WHITE)
    d.rectangle([cx + 11 * s, cy - 115 * s, cx + 65 * s, cy - 80 * s], fill=col)


def _book(d, cx, cy, s, col):
    d.polygon([(cx - 88 * s, cy - 40 * s), (cx, cy - 22 * s), (cx, cy + 62 * s), (cx - 88 * s, cy + 44 * s)], fill=col)
    d.polygon([(cx + 88 * s, cy - 40 * s), (cx, cy - 22 * s), (cx, cy + 62 * s), (cx + 88 * s, cy + 44 * s)], fill=col)
    d.polygon([(cx - 80 * s, cy - 50 * s), (cx - 4 * s, cy - 32 * s), (cx - 4 * s, cy + 50 * s), (cx - 80 * s, cy + 32 * s)], fill=WHITE)
    d.polygon([(cx + 80 * s, cy - 50 * s), (cx + 4 * s, cy - 32 * s), (cx + 4 * s, cy + 50 * s), (cx + 80 * s, cy + 32 * s)], fill=WHITE)
    for k in range(4):
        y = cy - 25 * s + k * 18 * s
        d.line([(cx - 68 * s, y - 8 * s), (cx - 16 * s, y + 4 * s)], fill=shade(col, 0.8), width=int(4 * s))
        d.line([(cx + 68 * s, y - 8 * s), (cx + 16 * s, y + 4 * s)], fill=shade(col, 0.8), width=int(4 * s))


def _crown(d, cx, cy, s, col):
    d.polygon([(cx - 75 * s, cy + 15 * s), (cx - 75 * s, cy - 45 * s), (cx - 38 * s, cy - 5 * s), (cx, cy - 65 * s),
               (cx + 38 * s, cy - 5 * s), (cx + 75 * s, cy - 45 * s), (cx + 75 * s, cy + 15 * s)], fill=col)
    d.rectangle([cx - 75 * s, cy + 22 * s, cx + 75 * s, cy + 50 * s], fill=shade(col, 0.8))
    for ox in (-40, 0, 40):
        d.ellipse([cx + (ox - 9) * s, cy + 27 * s, cx + (ox + 9) * s, cy + 45 * s], fill=WHITE)


def _globe(d, cx, cy, s, col):
    r = 78 * s
    w = int(7 * s)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)
    d.ellipse([cx - r * 0.45, cy - r, cx + r * 0.45, cy + r], outline=col, width=w)
    d.line([(cx, cy - r), (cx, cy + r)], fill=col, width=w)
    d.line([(cx - r, cy), (cx + r, cy)], fill=col, width=w)
    for f in (-0.5, 0.5):
        y = cy + f * r
        hw = r * 0.866
        d.line([(cx - hw, y), (cx + hw, y)], fill=col, width=w)


def _flask(d, cx, cy, s, col):
    d.rectangle([cx - 20 * s, cy - 80 * s, cx + 20 * s, cy - 20 * s], outline=WHITE, width=int(7 * s))
    d.polygon([(cx - 20 * s, cy - 22 * s), (cx + 20 * s, cy - 22 * s), (cx + 75 * s, cy + 70 * s), (cx - 75 * s, cy + 70 * s)], fill=WHITE)
    d.polygon([(cx - 45 * s, cy + 20 * s), (cx + 45 * s, cy + 20 * s), (cx + 66 * s, cy + 62 * s), (cx - 66 * s, cy + 62 * s)], fill=col)
    d.rectangle([cx - 32 * s, cy - 92 * s, cx + 32 * s, cy - 78 * s], fill=WHITE)


def _star(d, cx, cy, s, col):
    import math
    pts = []
    for k in range(10):
        r = (85 if k % 2 == 0 else 36) * s
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=col)


def _dome(d, cx, cy, s, col):
    d.pieslice([cx - 62 * s, cy - 60 * s, cx + 42 * s, cy + 44 * s], 180, 360, fill=col)
    d.rectangle([cx - 66 * s, cy - 8 * s, cx + 46 * s, cy + 70 * s], fill=shade(col, 0.85))
    d.rectangle([cx - 22 * s, cy + 22 * s, cx + 2 * s, cy + 70 * s], fill=shade(col, 0.45))
    d.rectangle([cx + 56 * s, cy - 70 * s, cx + 76 * s, cy + 70 * s], fill=shade(col, 0.95))
    d.polygon([(cx + 52 * s, cy - 70 * s), (cx + 80 * s, cy - 70 * s), (cx + 66 * s, cy - 98 * s)], fill=col)
    d.line([(cx - 10 * s, cy - 60 * s), (cx - 10 * s, cy - 88 * s)], fill=col, width=int(5 * s))
    d.ellipse([cx - 18 * s, cy - 104 * s, cx - 2 * s, cy - 88 * s], fill=col)


def _tree(d, cx, cy, s, col):
    d.rectangle([cx - 12 * s, cy + 10 * s, cx + 12 * s, cy + 85 * s], fill=(140, 95, 60))
    for ox, oy, r in [(0, -35, 50), (-42, 0, 38), (42, 0, 38), (0, 15, 40)]:
        d.ellipse([cx + (ox - r) * s, cy + (oy - r) * s, cx + (ox + r) * s, cy + (oy + r) * s], fill=col)


def _fin(d, cx, cy, s, col):
    d.polygon([(cx - 60 * s, cy + 30 * s), (cx + 10 * s, cy - 80 * s), (cx + 50 * s, cy + 30 * s)], fill=(160, 175, 195))
    for k in range(3):
        y = cy + (40 + k * 20) * s
        d.arc([cx - 95 * s, y - 15 * s, cx - 5 * s, y + 15 * s], 0, 180, fill=col, width=int(7 * s))
        d.arc([cx - 5 * s, y - 15 * s, cx + 85 * s, y + 15 * s], 0, 180, fill=col, width=int(7 * s))


def _rocket(d, cx, cy, s, col):
    d.polygon([(cx, cy - 90 * s), (cx - 28 * s, cy - 40 * s), (cx + 28 * s, cy - 40 * s)], fill=col)
    d.rectangle([cx - 28 * s, cy - 40 * s, cx + 28 * s, cy + 45 * s], fill=WHITE)
    d.ellipse([cx - 14 * s, cy - 22 * s, cx + 14 * s, cy + 6 * s], fill=col)
    d.polygon([(cx - 28 * s, cy + 10 * s), (cx - 55 * s, cy + 55 * s), (cx - 28 * s, cy + 45 * s)], fill=col)
    d.polygon([(cx + 28 * s, cy + 10 * s), (cx + 55 * s, cy + 55 * s), (cx + 28 * s, cy + 45 * s)], fill=col)
    d.polygon([(cx - 18 * s, cy + 48 * s), (cx + 18 * s, cy + 48 * s), (cx, cy + 92 * s)], fill=(255, 150, 60))


def _hourglass(d, cx, cy, s, col):
    d.rectangle([cx - 60 * s, cy - 85 * s, cx + 60 * s, cy - 72 * s], fill=col)
    d.rectangle([cx - 60 * s, cy + 72 * s, cx + 60 * s, cy + 85 * s], fill=col)
    d.polygon([(cx - 48 * s, cy - 72 * s), (cx + 48 * s, cy - 72 * s), (cx + 6 * s, cy), (cx - 6 * s, cy)], fill=WHITE)
    d.polygon([(cx - 6 * s, cy), (cx + 6 * s, cy), (cx + 48 * s, cy + 72 * s), (cx - 48 * s, cy + 72 * s)], fill=WHITE)
    d.polygon([(cx - 30 * s, cy + 72 * s), (cx + 30 * s, cy + 72 * s), (cx, cy + 35 * s)], fill=col)


ICONS = {"none": None, "pyramid": _pyramid, "ankh": _ankh, "moon": _moon, "book": _book, "crown": _crown,
         "globe": _globe, "flask": _flask, "star": _star, "dome": _dome, "tree": _tree, "fin": _fin,
         "rocket": _rocket, "hourglass": _hourglass}
ICON_NAMES = list(ICONS)


def _transparent_edges(im):
    """True when the picture is a cut-out (transparent corners), e.g. a map or logo PNG."""
    a = im.getchannel("A")
    w, h = im.size
    return all(a.getpixel(p) < 16 for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))


def circle_image(path, diameter):
    """Round picture for a card. `path` may be a file or a PIL image; cut-outs are fitted whole, photos are cropped."""
    src = (path if isinstance(path, Image.Image) else Image.open(path)).convert("RGBA")
    if _transparent_edges(src):
        inner = ImageOps.contain(src, (int(diameter * 0.84), int(diameter * 0.84)), Image.LANCZOS)
        im = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        im.alpha_composite(inner, ((diameter - inner.width) // 2, (diameter - inner.height) // 2))
    else:
        im = ImageOps.fit(src, (diameter, diameter), Image.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter - 1, diameter - 1], fill=255)
    im.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    return im


def make_card(title, subtitle, color, icon="none", image=None, card_bg=(18, 26, 48)):
    """Event card (500x470 visible + 40px shadow margin) at scale 1."""
    S = 2
    color = to_rgb(color)
    cw, ch, m = 500, 470, 40
    im = Image.new("RGBA", ((cw + 2 * m) * S, (ch + 2 * m) * S), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([m * S, (m + 14) * S, (m + cw) * S, (m + ch + 14) * S], 40 * S, fill=(0, 0, 0, 170))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(18 * S)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([m * S, m * S, (m + cw) * S, (m + ch) * S], 40 * S, fill=tuple(card_bg) + (245,),
                        outline=color + (255,), width=4 * S)
    cx, cy = (m + cw / 2) * S, (m + 130) * S
    d.ellipse([cx - 95 * S, cy - 95 * S, cx + 95 * S, cy + 95 * S], fill=shade(color, 0.22) + (255,))
    if isinstance(image, Image.Image) or (image and os.path.isfile(str(image))):
        ph = circle_image(image, 184 * S)
        im.alpha_composite(ph, (int(cx - ph.width / 2), int(cy - ph.height / 2)))
        d.ellipse([cx - 95 * S, cy - 95 * S, cx + 95 * S, cy + 95 * S], outline=color + (255,), width=4 * S)
    elif ICONS.get(icon):
        ICONS[icon](d, cx, cy, S * 0.95, color)
    im = im.resize((cw + 2 * m, ch + 2 * m), Image.LANCZOS)
    t1 = text_img(title, 50, WHITE, "Bold", shadow=False, max_w=440)
    t2 = text_img(subtitle, 62, color, "Black", shadow=False, max_w=450) if subtitle else None
    im.alpha_composite(t1, (int(m + cw / 2 - t1.width / 2), int(m + 300 - t1.height / 2)))
    if t2:
        im.alpha_composite(t2, (int(m + cw / 2 - t2.width / 2), int(m + 385 - t2.height / 2)))
    return im
