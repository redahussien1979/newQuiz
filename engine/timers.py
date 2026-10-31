"""Countdown timer designs. Each draws centred at (cx, cy) on an RGBA frame.

rem       fraction of time remaining (1 -> 0)
left      whole seconds remaining (shown as a number)
total     total whole seconds
col       current colour (turns red near the end)
ink       text colour that reads on the background
u         seconds since the countdown started (for small animations)
"""
import math

from PIL import Image, ImageDraw, ImageFilter

from .core import paste, shade, text_img

TIMER_NAMES = ["Ring", "Pie", "Bar", "Hourglass", "Digital", "Segments", "Fuse"]


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


DRAW = {"Ring": ring, "Pie": pie, "Bar": bar, "Hourglass": hourglass, "Digital": digital,
        "Segments": segments, "Fuse": fuse}


def draw_timer(kind, *args):
    DRAW.get(kind, ring)(*args)
