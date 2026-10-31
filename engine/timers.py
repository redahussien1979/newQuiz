"""Countdown timer designs. Each draws centred at (cx, cy) on an RGBA frame.

rem       fraction of time remaining (1 -> 0)
left      whole seconds remaining (shown as a number)
total     total whole seconds
col       current colour (turns red near the end)
ink       text colour that reads on the background
u         seconds since the countdown started (for small animations)
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import H, W, paste, shade, text_img

TIMER_NAMES = ["Ring", "Pie", "Bar", "Hourglass", "Digital", "Segments", "Fuse",
               "Neon Ring", "Dots", "Flip Clock", "Stopwatch", "Liquid", "Big Number"]
# effects that can be layered on any timer while it ticks: (label, key)
TIMER_FX = [("Pulse on every tick", "pulse"), ("Glow", "glow"), ("Ripple wave", "ripple"),
            ("Shake in the last 3 s", "shake"), ("Red flash in the last 3 s", "flash")]


def _num(left, size, color, stroke=True):
    return text_img(str(left), size, color, "Black", shadow=stroke)


def ring(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2, r = 2, 58
    size = (r * 2 + 20) * S2
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = [10 * S2, 10 * S2, size - 10 * S2, size - 10 * S2]
    d.ellipse(box, fill=(10, 14, 28, 200), outline=(70, 80, 105, 255), width=12 * S2)
    if rem > 0.002:
        d.arc(box, -90, -90 + 360 * rem, fill=col + (255,), width=12 * S2)
    im = im.resize((size // S2, size // S2), Image.LANCZOS)
    num = _num(left, 54, (255, 255, 255), False)
    im.alpha_composite(num, (im.width // 2 - num.width // 2, im.height // 2 - num.height // 2))
    paste(frame, im, cx, cy, 1.0, a)


def pie(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2, r = 2, 62
    size = (r * 2 + 16) * S2
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = [8 * S2, 8 * S2, size - 8 * S2, size - 8 * S2]
    d.ellipse(box, fill=(10, 14, 28, 210))
    if rem > 0.002:
        d.pieslice(box, -90, -90 + 360 * rem, fill=col + (255,))
    d.ellipse(box, outline=(255, 255, 255, 230), width=5 * S2)
    im = im.resize((size // S2, size // S2), Image.LANCZOS)
    num = _num(left, 58, (255, 255, 255), True)
    im.alpha_composite(num, (im.width // 2 - num.width // 2, im.height // 2 - num.height // 2))
    paste(frame, im, cx, cy, 1.0, a)


def bar(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    w, h = 820, 30
    shake = math.sin(u * 60) * 4 if left <= 2 and rem > 0 else 0
    im = Image.new("RGBA", (w + 200, h + 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = 100, 80
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], h // 2, fill=(20, 24, 40, 220), outline=(255, 255, 255, 90), width=2)
    fw = w * rem
    if fw > h:
        fx = x0 + w - fw if rtl else x0
        d.rounded_rectangle([fx, y0, fx + fw, y0 + h], h // 2, fill=col + (255,))
        d.rounded_rectangle([fx + 6, y0 + 5, fx + fw - 6, y0 + 11], 3, fill=(255, 255, 255, 90))
    num = _num(left, 56, ink, True)
    im.alpha_composite(num, (im.width // 2 - num.width // 2, 40 - num.height // 2))
    paste(frame, im, cx + shake, cy - 20, 1.0, a)


def hourglass(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2 = 2
    W_, H_ = 120, 170
    im = Image.new("RGBA", (W_ * S2, H_ * S2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = S2
    frame_col = (230, 200, 140, 255)
    glass = (255, 255, 255, 60)
    top, bot, mid, L, R = 18, 152, 85, 18, 102
    d.polygon([(L * s, top * s), (R * s, top * s), (64 * s, mid * s), (56 * s, mid * s)], fill=glass)
    d.polygon([(56 * s, mid * s), (64 * s, mid * s), (R * s, bot * s), (L * s, bot * s)], fill=glass)
    sand = col + (255,)
    # top sand: an inverted triangle whose height shrinks with rem
    ht = (mid - top - 6) * rem
    if ht > 1:
        yt = mid - 4 - ht
        half = (R - L) / 2 * (ht / (mid - top)) + 4
        d.polygon([((60 - half) * s, yt * s), ((60 + half) * s, yt * s), (60 * s, (mid - 4) * s)], fill=sand)
    # bottom pile grows
    hb = (bot - mid - 8) * (1 - rem)
    if hb > 1:
        half = (R - L) / 2 * (hb / (bot - mid)) + 6
        d.polygon([((60 - half) * s, (bot - 4) * s), ((60 + half) * s, (bot - 4) * s), (60 * s, (bot - 4 - hb) * s)], fill=sand)
    if 0.01 < rem < 0.995:  # falling stream
        d.line([(60 * s, mid * s), (60 * s, (bot - 4 - hb) * s)], fill=sand, width=3 * s)
    d.rectangle([6 * s, 6 * s, 114 * s, 20 * s], fill=frame_col)
    d.rectangle([6 * s, 150 * s, 114 * s, 164 * s], fill=frame_col)
    d.line([(L * s, top * s), (56 * s, mid * s), (L * s, bot * s)], fill=(255, 255, 255, 170), width=3 * s)
    d.line([(R * s, top * s), (64 * s, mid * s), (R * s, bot * s)], fill=(255, 255, 255, 170), width=3 * s)
    im = im.resize((W_, H_), Image.LANCZOS)
    tilt = math.sin(u * 3) * 4 if rem > 0 else 0
    im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
    paste(frame, im, cx - 70, cy, 0.85, a)
    paste(frame, _num(left, 70, ink, True), cx + 60, cy, 1.0, a)


def digital(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    frac = u - math.floor(u)
    pulse = 1 + 0.18 * max(0, 1 - frac * 4) if rem > 0 else 1
    panel = Image.new("RGBA", (300, 130), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle([0, 0, 299, 129], 28, fill=(8, 10, 20, 225), outline=col + (255,), width=4)
    txt = text_img(f"00:{left:02d}", 74, col, "Black", shadow=False)
    glow = txt.filter(ImageFilter.GaussianBlur(8))
    panel.alpha_composite(glow, (150 - glow.width // 2, 65 - glow.height // 2))
    panel.alpha_composite(txt, (150 - txt.width // 2, 65 - txt.height // 2))
    paste(frame, panel, cx, cy, pulse, a)


def segments(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    n = max(1, total)
    sw, gap = min(90, (820 - (n - 1) * 12) / n), 12
    total_w = n * sw + (n - 1) * gap
    im = Image.new("RGBA", (int(total_w) + 40, 90), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rem_s = rem * n
    for k in range(n):
        idx = (n - 1 - k) if rtl else k
        x = 20 + idx * (sw + gap)
        d.rounded_rectangle([x, 20, x + sw, 70], 12, fill=(30, 34, 52, 220), outline=(255, 255, 255, 60), width=2)
        lit = max(0.0, min(1.0, rem_s - k))
        if lit > 0:
            c = shade(col, 0.45 + 0.55 * lit)
            d.rounded_rectangle([x + 5, 25, x + sw - 5, 65], 9, fill=c + (int(255 * (0.35 + 0.65 * lit)),))
    paste(frame, im, cx, cy, 1.0, a)


def fuse(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    W_, H_ = 1000, 170
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bx = 110 if rtl else W_ - 110
    by = 95
    start = W_ - 60 if rtl else 60
    end = bx + (70 if rtl else -70)
    tip = end + (start - end) * rem
    pts = []
    lo, hi = sorted((end, tip))
    x = lo
    while x <= hi:
        pts.append((x, by - 52 + math.sin(x / 38.0) * 10))
        x += 6
    if len(pts) > 1:
        d.line(pts, fill=(196, 160, 110, 255), width=8)
        d.line(pts, fill=(120, 90, 55, 255), width=3)
    # bomb
    d.ellipse([bx - 62, by - 52, bx + 62, by + 72], fill=(25, 25, 32, 255), outline=(90, 90, 110, 255), width=3)
    d.rectangle([bx - 16, by - 66, bx + 16, by - 48], fill=(70, 70, 85, 255))
    d.ellipse([bx - 36, by - 30, bx - 14, by - 8], fill=(255, 255, 255, 90))
    num = _num(left, 58, col if left <= 2 else (255, 255, 255), False)
    im.alpha_composite(num, (int(bx - num.width / 2), int(by + 10 - num.height / 2)))
    # spark
    if rem > 0.002:
        sy = by - 52 + math.sin(tip / 38.0) * 10
        g = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse([30, 30, 90, 90], fill=(255, 190, 60, 255))
        g = g.filter(ImageFilter.GaussianBlur(14))
        im.alpha_composite(g, (int(tip - 60), int(sy - 60)))
        for k in range(8):
            ang = u * 13 + k * 0.8
            rr = 10 + (k * 7 + u * 90) % 26
            px, py = tip + math.cos(ang) * rr, sy + math.sin(ang) * rr
            d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(255, 240, 160, 255))
        d.ellipse([tip - 8, sy - 8, tip + 8, sy + 8], fill=(255, 255, 230, 255))
    paste(frame, im, cx, cy - 10, 1.0, a)


# ------------------------------------------------------------------ newer designs
def neon_ring(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2, r = 2, 62
    size = (r * 2 + 60) * S2
    c = size // 2
    arc = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(arc)
    box = [c - r * S2, c - r * S2, c + r * S2, c + r * S2]
    d.ellipse(box, outline=col + (45,), width=5 * S2)
    end = -90 + 360 * rem
    if rem > 0.002:
        d.arc(box, -90, end, fill=col + (255,), width=9 * S2)
        tx, ty = c + r * S2 * math.cos(math.radians(end)), c + r * S2 * math.sin(math.radians(end))
        d.ellipse([tx - 9 * S2, ty - 9 * S2, tx + 9 * S2, ty + 9 * S2], fill=(255, 255, 255, 255))
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([c - (r - 8) * S2, c - (r - 8) * S2, c + (r - 8) * S2, c + (r - 8) * S2],
                               fill=(6, 8, 18, 210))
    im.alpha_composite(arc.filter(ImageFilter.GaussianBlur(9 * S2)))
    im.alpha_composite(arc)
    im = im.resize((size // S2, size // S2), Image.LANCZOS)
    num = text_img(str(left), 56, (255, 255, 255), "Black", shadow=False)
    halo = text_img(str(left), 56, col, "Black", shadow=False).filter(ImageFilter.GaussianBlur(7))
    for t_ in (halo, num):
        im.alpha_composite(t_, (im.width // 2 - t_.width // 2, im.height // 2 - t_.height // 2))
    paste(frame, im, cx, cy, 1.0, a)


def dots(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2, R, n = 2, 64, 12
    size = (R * 2 + 40) * S2
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    d.ellipse([c - (R - 18) * S2, c - (R - 18) * S2, c + (R - 18) * S2, c + (R - 18) * S2], fill=(10, 14, 28, 200))
    lit = rem * n
    for k in range(n):
        ang = math.radians(-90 + (k if not rtl else -k) * 360 / n)
        x, y = c + R * S2 * math.cos(ang), c + R * S2 * math.sin(ang)
        v = max(0.0, min(1.0, lit - k))
        rr = (6 + 3 * v) * S2
        fill = tuple(int(o + (cc - o) * v) for o, cc in zip((60, 68, 92), col)) + (255,)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)
    im = im.resize((int(size // S2), int(size // S2)), Image.LANCZOS)
    num = _num(left, 54, (255, 255, 255), False)
    im.alpha_composite(num, (im.width // 2 - num.width // 2, im.height // 2 - num.height // 2))
    paste(frame, im, cx, cy, 1.0, a)


def _flip_card(ch, red):
    w, h = 96, 132
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 14, fill=(28, 30, 40, 255))
    d.rounded_rectangle([0, 0, w - 1, h // 2], 14, fill=(36, 38, 50, 255))
    d.rectangle([0, h // 2 - 14, w - 1, h // 2], fill=(36, 38, 50, 255))
    t = text_img(ch, 92, (255, 96, 96) if red else (245, 245, 250), "Black", shadow=False)
    im.alpha_composite(t, (w // 2 - t.width // 2, h // 2 - t.height // 2))
    d.line([(0, h // 2), (w, h // 2)], fill=(8, 8, 12, 255), width=3)
    return im


def flip_clock(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    red = col[0] > 200 and col[1] < 120  # the template switches to red near the end
    cur = f"{max(0, left):02d}"
    prev = f"{min(99, left + 1):02d}"
    f = u - math.floor(u)
    flipping = rem > 0 and u >= 1 and f < 0.3
    gap, w, h = 12, 96, 132
    im = Image.new("RGBA", (2 * w + gap + 24, h + 24), (0, 0, 0, 0))
    for i in range(2):
        x = 12 + i * (w + gap)
        new = _flip_card(cur[i], red)
        if not flipping or cur[i] == prev[i]:
            im.alpha_composite(new, (x, 12))
            continue
        old = _flip_card(prev[i], red)
        im.alpha_composite(new.crop((0, 0, w, h // 2)), (x, 12))  # new top already revealed behind
        im.alpha_composite(old.crop((0, h // 2, w, h)), (x, 12 + h // 2))  # old bottom still showing
        if f < 0.15:  # old top falls towards the hinge
            k = max(0.02, 1 - f / 0.15)
            flap = old.crop((0, 0, w, h // 2)).resize((w, max(1, int(h // 2 * k))))
            im.alpha_composite(flap, (x, 12 + h // 2 - flap.height))
        else:  # new bottom unfolds from the hinge
            k = max(0.02, (f - 0.15) / 0.15)
            flap = new.crop((0, h // 2, w, h)).resize((w, max(1, int(h // 2 * k))))
            im.alpha_composite(flap, (x, 12 + h // 2))
    paste(frame, im, cx, cy, 1.0, a)


def stopwatch(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2, R = 2, 64
    size = (R * 2 + 50) * S2
    im = Image.new("RGBA", (size, size + 30 * S2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, cyy = size / 2, size / 2 + 22 * S2
    d.rounded_rectangle([c - 14 * S2, cyy - (R + 28) * S2, c + 14 * S2, cyy - (R - 2) * S2], 5 * S2, fill=(200, 205, 215, 255))
    d.rounded_rectangle([c - 22 * S2, cyy - (R + 36) * S2, c + 22 * S2, cyy - (R + 24) * S2], 5 * S2, fill=(230, 232, 240, 255))
    bx, by = c + R * 0.78 * S2, cyy - R * 0.78 * S2
    d.line([(bx, by), (bx + 14 * S2, by - 14 * S2)], fill=(200, 205, 215, 255), width=9 * S2)
    d.ellipse([c - R * S2, cyy - R * S2, c + R * S2, cyy + R * S2], fill=(244, 245, 250, 255), outline=col + (255,), width=8 * S2)
    if rem > 0.002:  # time still left, shaded
        d.pieslice([c - (R - 12) * S2, cyy - (R - 12) * S2, c + (R - 12) * S2, cyy + (R - 12) * S2],
                   -90 + 360 * (1 - rem), 270, fill=col + (60,))
    for k in range(12):
        ang = math.radians(k * 30)
        r0, r1 = (R - 14) * S2, (R - (24 if k % 3 == 0 else 19)) * S2
        d.line([(c + r0 * math.sin(ang), cyy - r0 * math.cos(ang)), (c + r1 * math.sin(ang), cyy - r1 * math.cos(ang))],
               fill=(60, 64, 80, 255), width=3 * S2)
    ang = math.radians(360 * (1 - rem))
    hl = (R - 18) * S2
    d.line([(c, cyy), (c + hl * math.sin(ang), cyy - hl * math.cos(ang))], fill=(220, 40, 50, 255), width=4 * S2)
    d.ellipse([c - 6 * S2, cyy - 6 * S2, c + 6 * S2, cyy + 6 * S2], fill=(40, 42, 54, 255))
    im = im.resize((im.width // S2, im.height // S2), Image.LANCZOS)
    paste(frame, im, cx - 70, cy - 8, 0.95, a)
    paste(frame, _num(left, 70, ink, True), cx + 70, cy, 1.0, a)


def liquid(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    S2, R = 2, 66
    size = (R * 2 + 16) * S2
    c = size / 2
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([c - R * S2, c - R * S2, c + R * S2, c + R * S2], fill=255)
    fluid = Image.new("RGBA", (size, size), (10, 14, 28, 210))
    d = ImageDraw.Draw(fluid)
    level = c + R * S2 - 2 * R * S2 * rem
    amp = 5 * S2 * (1 if 0.02 < rem < 0.98 else 0.4)
    for layer, (shift, colr) in enumerate(((1.3, shade(col, 0.65)), (0.0, col))):
        pts = [(x, level + math.sin(x / (18.0 * S2) + u * 4 + shift) * amp) for x in range(0, size + 8, 8)]
        d.polygon(pts + [(size, size), (0, size)], fill=colr + (255,))
    for k in range(5):  # rising bubbles
        bx = c + math.sin(k * 2.1) * R * 0.55 * S2
        by = c + R * S2 - ((u * 40 + k * 37) % (2 * R)) * S2
        if by > level + 8 * S2:
            d.ellipse([bx - 4 * S2, by - 4 * S2, bx + 4 * S2, by + 4 * S2], fill=(255, 255, 255, 110))
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.paste(fluid, (0, 0), mask)
    ImageDraw.Draw(im).ellipse([c - R * S2, c - R * S2, c + R * S2, c + R * S2], outline=(255, 255, 255, 220), width=5 * S2)
    ImageDraw.Draw(im).arc([c - (R - 14) * S2, c - (R - 14) * S2, c + (R - 14) * S2, c + (R - 14) * S2], 200, 250,
                           fill=(255, 255, 255, 120), width=5 * S2)
    im = im.resize((size // S2, size // S2), Image.LANCZOS)
    num = _num(left, 58, (255, 255, 255), True)
    im.alpha_composite(num, (im.width // 2 - num.width // 2, im.height // 2 - num.height // 2))
    paste(frame, im, cx, cy, 1.0, a)


def big_number(frame, cx, cy, rem, left, total, col, ink, u, a, rtl):
    f = u - math.floor(u)
    pop = max(0.0, 1 - f / 0.3) if rem > 0 else 0.0  # each new number lands from slightly bigger
    num = text_img(str(left), 150, col if left <= 2 and rem > 0 else ink, "Black", shadow=True)
    paste(frame, num, cx, cy - 18, 1 + 0.35 * pop ** 2, a * (1 - 0.6 * pop ** 2))
    w = 300
    im = Image.new("RGBA", (w + 8, 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([4, 3, w + 4, 11], 4, fill=(255, 255, 255, 50))
    if rem > 0.004:
        fw = w * rem
        x0 = 4 + (w - fw) / 2
        d.rounded_rectangle([x0, 3, x0 + fw, 11], 4, fill=col + (255,))
    paste(frame, im, cx, cy + 72, 1.0, a)


DRAW = {"Ring": ring, "Pie": pie, "Bar": bar, "Hourglass": hourglass, "Digital": digital,
        "Segments": segments, "Fuse": fuse, "Neon Ring": neon_ring, "Dots": dots, "Flip Clock": flip_clock,
        "Stopwatch": stopwatch, "Liquid": liquid, "Big Number": big_number}

# rough footprint of each design (w, h), so glow and ripples match its shape
FOOTPRINT = {"Bar": (840, 64), "Segments": (840, 64), "Fuse": (940, 120), "Digital": (300, 130),
             "Flip Clock": (216, 140), "Hourglass": (250, 150), "Stopwatch": (260, 150), "Big Number": (220, 170)}


# ------------------------------------------------------------------ ticking effects
_fx_cache = {}


def _halo(kind, col):
    key = ("halo", kind, col)
    if key not in _fx_cache:
        w, h = FOOTPRINT.get(kind, (140, 140))
        m = 90
        im = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([m, m, m + w, m + h], min(w, h) // 2, fill=col + (200,))
        _fx_cache[key] = im.filter(ImageFilter.GaussianBlur(34))
    return _fx_cache[key]


def _red_edges():
    if "edges" not in _fx_cache:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
        al = (np.clip((r - 0.45) / 0.55, 0, 1) ** 1.6 * 210).astype(np.uint8)
        arr = np.zeros((H, W, 4), np.uint8)
        arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3] = 255, 30, 40, al
        _fx_cache["edges"] = Image.fromarray(arr, "RGBA")
    return _fx_cache["edges"]


def draw_timer(kind, frame, cx, cy, rem, left, total, col, ink, u, a, rtl, fx=()):
    """Draw a timer; `fx` is a list of effect keys from TIMER_FX applied while it ticks."""
    fn = DRAW.get(kind, ring)
    fx = set(fx or ())
    if not fx:
        fn(frame, cx, cy, rem, left, total, col, ink, u, a, rtl)
        return
    running = rem > 0.0005 and a > 0.01
    f = u - math.floor(u)
    beat = max(0.0, 1 - f / 0.25) if running and u > 0 else 0.0  # flares on every tick, fades in 0.25 s
    final = running and u > 0 and left <= 3
    if "flash" in fx and final and beat > 0:
        paste(frame, _red_edges(), W / 2, H / 2, 1.0, 0.75 * beat * a)
    if "glow" in fx and running:
        w, h = FOOTPRINT.get(kind, (140, 140))
        soft = min(1.0, math.sqrt(140 * 140 / (w * h)) * 1.4)  # wide timers: a gentler glow
        paste(frame, _halo(kind, col), cx, cy, 1 + 0.12 * beat, a * (0.35 + 0.45 * beat) * soft)
    if "ripple" in fx and running and u > 0:
        w, h = FOOTPRINT.get(kind, (140, 140))
        grow = (6 + 54 * (1 - (1 - f) ** 2)) * (0.5 if w > 400 else 1.0)  # wide timers: a tighter wave
        al = int(200 * a * (1 - f) ** 1.5)
        if al > 4:
            rw, rh = int(w + 2 * grow), int(h + 2 * grow)
            ov = Image.new("RGBA", (rw + 12, rh + 12), (0, 0, 0, 0))
            ImageDraw.Draw(ov).rounded_rectangle([6, 6, rw + 6, rh + 6], min(rw, rh) // 2, outline=col + (al,), width=5)
            paste(frame, ov, cx, cy, 1.0, 1.0)
    scale = 1 + ((0.07 + (0.07 if final else 0)) * beat if "pulse" in fx else 0)
    dx = math.sin(u * 80) * 8 * (0.5 + 0.5 * beat) if "shake" in fx and final else 0
    if abs(scale - 1) < 0.004 and abs(dx) < 0.5:
        fn(frame, cx, cy, rem, left, total, col, ink, u, a, rtl)
        return
    lw, lh = W, 440  # draw on a transparent layer, then place it scaled / shaken
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    fn(layer, lw / 2, lh / 2, rem, left, total, col, ink, u, a, rtl)
    paste(frame, layer, cx + dx, cy, scale, 1.0)
