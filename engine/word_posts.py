"""📃 Word list → still image posts: every page of words from the Excel sheet (word_import.read_words / plan) drawn as
one square 1080x1080 PNG (Instagram / Facebook feed post, carousel slide) instead of a video.

A page = dict(title, sub, words=[dict(en, ipa, ar), …]) with 1-6 words. `post(page, style, palette, handle, n, of)`
-> RGB Image; `STYLES` = the designs (one function each, `_draw_<style>`), colours = the Word list's two- / three-tone
sets (list_designs.DUOS). Every design gives all words of a page ONE size (and all meanings one size), like the video
designs: `_common` finds the largest size at which every row fits its box."""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import ROOT, text_img_in
from .list_designs import (ALEXANDRIA, DUOS, MONTSERRAT, NASKH, PLEX_B, POPPINS_B, POPPINS_K, TAJAWAL, _circle_mask,
                           _colored, _lum, _mix, _round_mask, _vis_w)
from .word_list import MESSIRI, PATRICK, PLAYFAIR, RUQAA

S = 1080  # square post
IPA_FONT = os.path.join(ROOT, "fonts", "NotoSans-Bold.ttf")

STYLES = [("Cards", "cards"), ("Flashcard grid", "grid"), ("Table", "table"), ("Notebook", "notebook"),
          ("Minimal", "minimal"), ("Chalkboard", "chalk"), ("Poster", "poster")]
DEFAULT_STYLE = "cards"
DEFAULT_PALETTE = "navy_juice"


# ---------------------------------------------------------------- text
def _t(font, txt, size, col, weight="Bold"):
    return text_img_in(font, str(txt), max(12, int(size)), tuple(col), weight, shadow=False)


def _ipa(txt, size, col):
    if not os.path.isfile(IPA_FONT):
        return _t(POPPINS_B, txt, size, col)
    return text_img_in(IPA_FONT, str(txt), max(12, int(size)), tuple(col), "Bold", shadow=False)


def _h(im):
    return im.height - 60


def _put(fr, im, x, y, anchor="l"):
    """Paste a text image by the visible box: x = left / centre / right edge (anchor l / c / r), y = vertical centre."""
    vw = _vis_w(im)
    left = x if anchor == "l" else x - vw / 2 if anchor == "c" else x - vw
    fr.alpha_composite(im, (int(round(left - 30)), int(round(y - im.height / 2))))


def _fit_one(make, size, max_w, min_size=18):
    """make(size) -> text image, shrunk until its visible width fits max_w."""
    im = make(size)
    while _vis_w(im) > max_w and size > min_size:
        size = max(min_size, int(size * max(0.6, max_w / max(1, _vis_w(im))) * 0.98))
        im = make(size)
    return im


def _common(words, make_row, k_max=1.0):
    """The largest k (<= k_max) at which make_row(word, k) -> (needed w / box w, needed h / box h) fits for every
    word: one size for the whole page."""
    k = k_max
    for w in words:
        for _ in range(10):
            r = max(make_row(w, k))
            if r <= 1:
                break
            k *= max(0.6, 1 / r) * 0.99
    return k


def _readable(bg):
    return (20, 20, 28) if _lum(bg) > 0.35 else (255, 255, 255)


def _tones(pal):
    t = DUOS.get(pal) or DUOS[DEFAULT_PALETTE]
    return t[0], t[1], (t[2] if len(t) > 2 else t[1])


def _gradient(c0, c1, size=(S, S), angle=0.0):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle)
    g = (xx / w - 0.5) * math.sin(a) + (yy / h - 0.5) * math.cos(a) + 0.5
    g = np.clip(g, 0, 1)[..., None]
    arr = np.array(c0, np.float32) * (1 - g) + np.array(c1, np.float32) * g
    return Image.fromarray(arr.astype(np.uint8)).convert("RGBA")


def _shadow(fr, mask, x, y, blur=18, alpha=0.28, dy=10):
    sh = Image.new("L", (mask.width + 80, mask.height + 80), 0)
    sh.paste(mask, (40, 40))
    sh = sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    fr.alpha_composite(_colored(sh, (0, 0, 0)), (int(x - 40), int(y - 40 + dy)))


def _card(fr, x, y, w, h, r, col, shadow=True, alpha=1.0):
    m = _round_mask(w, h, r)
    if shadow:
        _shadow(fr, m, x, y)
    fr.alpha_composite(_colored(m, col, alpha), (int(x), int(y)))


def _footer(fr, handle, n, of, col, y=S - 46, font=POPPINS_B):
    if handle:
        _put(fr, _t(font, handle, 30, col, "SemiBold"), 60, y)
    if of > 1:
        _put(fr, _t(font, f"{n} / {of}", 30, col, "SemiBold"), S - 60, y, "r")


def _header(fr, page, y, col_t, col_s, font_t, font_s, size_t=74, size_s=36, max_w=S - 140, weight_t="Bold"):
    """Title (+ subtitle) centred from y; returns the y under them."""
    if page.get("title"):
        im = _fit_one(lambda s: _t(font_t, page["title"], s, col_t, weight_t), size_t, max_w)
        _put(fr, im, S / 2, y + _h(im) / 2, "c")
        y += _h(im) + 22
    if page.get("sub"):
        im = _fit_one(lambda s: _t(font_s, page["sub"], s, col_s, "SemiBold"), size_s, max_w)
        _put(fr, im, S / 2, y + _h(im) / 2, "c")
        y += _h(im) + 18
    return y


def _rows(top, bottom, n, gap):
    """(y of each row, row height) splitting top..bottom into n rows with gaps."""
    rh = (bottom - top - gap * (n - 1)) / n
    return [top + i * (rh + gap) for i in range(n)], rh


def _row_texts(w, k, f_en, f_ar, c_en, c_ipa, c_ar, en=64, ipa=34, ar=58, w_en="Bold", w_ar="Bold"):
    e = _t(f_en, w["en"], en * k, c_en, w_en)
    i = _ipa(w["ipa"], ipa * k, c_ipa) if w.get("ipa") else None
    a = _t(f_ar, w["ar"], ar * k, c_ar, w_ar)
    return e, i, a


def _side_by_side(fr, e, i, a, xl, xr, cy, gap=8):
    """English (+ IPA under it) on the left, Arabic on the right, centred on cy."""
    if i is not None:
        hh = _h(e) + gap + _h(i)
        _put(fr, e, xl, cy - hh / 2 + _h(e) / 2)
        _put(fr, i, xl, cy + hh / 2 - _h(i) / 2)
    else:
        _put(fr, e, xl, cy)
    _put(fr, a, xr, cy, "r")


def _sbs_need(e, i, a, box_w, box_h, gap=8, mid=40):
    w = _vis_w(e) if i is None else max(_vis_w(e), _vis_w(i))
    h = max(_h(e) + (gap + _h(i) if i is not None else 0), _h(a))
    return (w + mid + _vis_w(a)) / box_w, h / box_h


# ---------------------------------------------------------------- designs
def _draw_cards(page, pal, handle, n, of):
    """Deep base colour, white rounded cards, an accent number badge; English left, Arabic right."""
    dk, ac, ac2 = _tones(pal)
    fr = _gradient(_mix(dk, (0, 0, 0), -0.0), _mix(dk, (0, 0, 0), 0.35), angle=20)
    d = ImageDraw.Draw(fr)
    for r_, a_ in ((420, 18), (260, 14)):  # soft rings in a corner
        d.ellipse([S - r_, -r_ * 0.6, S + r_, r_ * 1.4], outline=_mix(dk, ac, 0.18), width=a_)
    y = _header(fr, page, 70, ac, (235, 235, 245), POPPINS_K, PLEX_B, weight_t="Black")
    words = page["words"]
    ys, rh = _rows(max(y + 20, 200 if page.get("title") else 80), S - 100, len(words), 18)
    rh = min(rh, 200)
    total = len(words) * rh + 18 * (len(words) - 1)
    top = (max(y + 20, 200 if page.get("title") else 80) + S - 100) / 2 - total / 2
    badge = min(78, rh * 0.62)
    xl, xr = 60 + 30 + badge + 28, S - 60 - 36
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, POPPINS_B, PLEX_B, dk, (120, 120, 140), dk),
                                              xr - xl, rh * 0.78), k_max=1.15)
    for j, w in enumerate(words):
        yy = top + j * (rh + 18)
        _card(fr, 60, yy, S - 120, rh, min(36, rh / 2.6), (255, 255, 255))
        bm = _circle_mask(badge)
        fr.alpha_composite(_colored(bm, ac), (int(60 + 30), int(yy + rh / 2 - badge / 2)))
        _put(fr, _t(POPPINS_K, str(j + 1), badge * 0.5, _readable(ac), "Black"), 60 + 30 + badge / 2, yy + rh / 2,
             "c")
        _side_by_side(fr, *_row_texts(w, k, POPPINS_B, PLEX_B, dk, (120, 120, 140), dk), xl, xr, yy + rh / 2)
    _footer(fr, handle, n, of, _mix((255, 255, 255), dk, 0.25))
    return fr


def _grid_shape(n):
    return {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2)}.get(n, (2, 3))


def _draw_grid(page, pal, handle, n, of):
    """Flashcards in a grid (2 x 3 for 5-6 words): the word, its IPA, a line, the meaning."""
    dk, ac, ac2 = _tones(pal)
    fr = Image.new("RGBA", (S, S), _mix(ac, (255, 255, 255), 0.55) + (255,))
    d = ImageDraw.Draw(fr)
    for x in range(-S, S, 46):  # light diagonal stripes
        d.line([(x, S), (x + S, 0)], fill=_mix(ac, (255, 255, 255), 0.42), width=14)
    y = _header(fr, page, 64, dk, _mix(dk, (255, 255, 255), 0.25), POPPINS_K, PLEX_B, weight_t="Black")
    words = page["words"]
    cols, rows = _grid_shape(len(words))
    top, bot, m, g = max(y + 16, 70), S - 96, 60, 26
    cw = (S - 2 * m - g * (cols - 1)) / cols
    ch = min((bot - top - g * (rows - 1)) / rows, cw * 1.05)
    top = (top + bot) / 2 - (ch * rows + g * (rows - 1)) / 2

    def need(w, k):
        e, i, a = _row_texts(w, k, POPPINS_B, PLEX_B, dk, (110, 110, 130), dk, en=70, ipa=34, ar=62)
        h = _h(e) + 14 + (_h(i) + 14 if i is not None else 0) + 30 + _h(a)
        return max(_vis_w(e), _vis_w(i) if i is not None else 0, _vis_w(a)) / (cw - 50), h / (ch - 60)

    k = _common(words, need, k_max=1.4)
    for j, w in enumerate(words):
        r, c = divmod(j, cols)
        x0, y0 = m + c * (cw + g), top + r * (ch + g)
        _card(fr, x0, y0, cw, ch, 30, (255, 255, 255))
        strip = _round_mask(cw, ch, 30)  # the card's own top edge in the base colour
        strip.paste(0, (0, 16, strip.width, strip.height))
        fr.alpha_composite(_colored(strip, dk), (int(x0), int(y0)))
        e, i, a = _row_texts(w, k, POPPINS_B, PLEX_B, dk, (110, 110, 130), dk, en=70, ipa=34, ar=62)
        parts = [e] + ([i] if i is not None else []) + ["line", a]
        hh = _h(e) + 14 + (_h(i) + 14 if i is not None else 0) + 30 + _h(a)
        yy, cx = y0 + ch / 2 - hh / 2 + 6, x0 + cw / 2
        for p in parts:
            if p == "line":
                d.rounded_rectangle([cx - 36, yy + 8, cx + 36, yy + 14], 3, fill=ac2 if ac2 != ac else ac)
                yy += 30
                continue
            _put(fr, p, cx, yy + _h(p) / 2, "c")
            yy += _h(p) + 14
    _footer(fr, handle, n, of, dk)
    return fr


def _draw_table(page, pal, handle, n, of):
    """A clean two-column table: header band English | العربية, striped rows."""
    dk, ac, ac2 = _tones(pal)
    fr = Image.new("RGBA", (S, S), (246, 246, 250, 255))
    d = ImageDraw.Draw(fr)
    d.rectangle([0, 0, S, 250 if page.get("title") else 0], fill=dk)
    y = _header(fr, page, 64, (255, 255, 255), ac, POPPINS_K, PLEX_B, weight_t="Black") if page.get("title") else 40
    words = page["words"]
    x0, x1 = 60, S - 60
    top = max(y, 250) + 40 if page.get("title") else 60
    head = 76
    _card(fr, x0, top, x1 - x0, S - 110 - top, 26, (255, 255, 255))
    d.rounded_rectangle([x0, top, x1, top + head], 26, fill=ac)
    d.rectangle([x0, top + head - 26, x1, top + head], fill=ac)
    hc = _readable(ac)
    _put(fr, _t(POPPINS_B, "English", 34, hc), x0 + 40, top + head / 2)
    _put(fr, _t(PLEX_B, "العربية", 36, hc), x1 - 40, top + head / 2, "r")
    ys, rh = _rows(top + head, S - 110, len(words), 0)
    mid = (x0 + x1) / 2
    k = _common(words, lambda w, k: (
        lambda e, i, a: (max(_vis_w(e) + (_vis_w(i) + 18 if i is not None else 0), 1) / (mid - x0 - 60),
                         _vis_w(a) / (x1 - mid - 60), max(_h(e), _h(a)) / (rh * 0.62)))(
        *_row_texts(w, k, POPPINS_B, PLEX_B, dk, (120, 120, 140), dk, en=56, ipa=32, ar=54)), k_max=1.2)
    for j, (yy, w) in enumerate(zip(ys, words)):
        if j % 2:
            d.rectangle([x0, yy, x1, yy + rh], fill=_mix(ac, (255, 255, 255), 0.82))
        if j:
            d.line([(x0 + 24, yy), (x1 - 24, yy)], fill=(225, 225, 232), width=2)
        e, i, a = _row_texts(w, k, POPPINS_B, PLEX_B, dk, (120, 120, 140), dk, en=56, ipa=32, ar=54)
        _put(fr, e, x0 + 40, yy + rh / 2)
        if i is not None:
            _put(fr, i, x0 + 40 + _vis_w(e) + 18, yy + rh / 2 + (_h(e) - _h(i)) / 2 - 2)
        _put(fr, a, x1 - 40, yy + rh / 2, "r")
    d.line([(mid, top + head + 16), (mid, S - 126)], fill=(225, 225, 232), width=2)
    _footer(fr, handle, n, of, dk)
    return fr


def _draw_notebook(page, pal, handle, n, of):
    """A sheet of lined paper: red margin, hand-written words, a highlighter stroke on the title."""
    dk, ac, ac2 = _tones(pal)
    fr = Image.new("RGBA", (S, S), (253, 251, 243, 255))
    d = ImageDraw.Draw(fr)
    line = (190, 210, 235)
    for yy in range(120, S, 64):
        d.line([(0, yy), (S, yy)], fill=line, width=2)
    d.line([(118, 0), (118, S)], fill=(232, 120, 120), width=3)
    for yy in (180, S / 2, S - 180):  # punched holes
        d.ellipse([34, yy - 18, 70, yy + 18], fill=(225, 222, 212))
    ink, red = (30, 50, 110), (190, 40, 40)
    y = 60
    if page.get("title"):
        t = _fit_one(lambda s: _t(PATRICK, page["title"], s, ink, "Regular"), 88, S - 260)
        hl = Image.new("L", (_vis_w(t) + 40, int(_h(t) * 0.55)), 0)
        ImageDraw.Draw(hl).rounded_rectangle([0, 0, hl.width - 1, hl.height - 1], 18, fill=255)
        fr.alpha_composite(_colored(hl, ac, 0.75), (int(S / 2 + 30 - hl.width / 2), int(y + _h(t) * 0.45)))
        _put(fr, t, S / 2 + 30, y + _h(t) / 2, "c")
        y += _h(t) + 18
    if page.get("sub"):
        st = _fit_one(lambda s: _t(PATRICK, page["sub"], s, (90, 90, 110), "Regular"), 44, S - 260)
        _put(fr, st, S / 2 + 30, y + _h(st) / 2, "c")
        y += _h(st) + 16
    words = page["words"]
    xl, xr = 150, S - 70
    ys, rh = _rows(y + 24, S - 100, len(words), 10)
    rh = min(rh, 190)
    top = (y + 24 + S - 100) / 2 - (rh * len(words) + 10 * (len(words) - 1)) / 2
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, PATRICK, RUQAA, ink, red, red, en=78, ipa=32,
                                                          ar=66, w_en="Regular"), xr - xl - 60, rh * 0.85),
                k_max=1.1)
    for j, w in enumerate(words):
        cy = top + j * (rh + 10) + rh / 2
        num = _t(PATRICK, f"{j + 1}.", 52 * min(1, k + 0.1), (150, 150, 165), "Regular")
        _put(fr, num, xl, cy)
        e, i, a = _row_texts(w, k, PATRICK, RUQAA, ink, (110, 110, 130), red, en=78, ipa=32, ar=66, w_en="Regular")
        _side_by_side(fr, e, i, a, xl + 60, xr, cy)
        dash = xl + 60 + max(_vis_w(e), _vis_w(i) if i is not None else 0) + 26
        if dash < xr - _vis_w(a) - 40:
            for xx in range(int(dash), int(xr - _vis_w(a) - 26), 22):
                d.line([(xx, cy), (xx + 10, cy)], fill=(170, 170, 185), width=3)
    _footer(fr, handle, n, of, (110, 110, 130), font=PATRICK)
    return fr


def _draw_minimal(page, pal, handle, n, of):
    """Cream page, elegant serif words, thin rules, the meaning in a calm Arabic face."""
    dk, ac, ac2 = _tones(pal)
    bg = (247, 243, 236)
    fr = Image.new("RGBA", (S, S), bg + (255,))
    d = ImageDraw.Draw(fr)
    d.rectangle([28, 28, S - 28, S - 28], outline=_mix(dk, bg, 0.7), width=2)
    ink = _mix(dk, (0, 0, 0), 0.25) if _lum(dk) > 0.08 else dk
    y = 80
    if page.get("title"):
        t = _fit_one(lambda s: _t(PLAYFAIR, page["title"], s, ink, "Bold"), 80, S - 200)
        _put(fr, t, S / 2, y + _h(t) / 2, "c")
        y += _h(t) + 22
    if page.get("sub"):
        st = _fit_one(lambda s: _t(MESSIRI, page["sub"], s, _mix(ink, bg, 0.4), "Medium"), 38, S - 200)
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 16
    if page.get("title") or page.get("sub"):
        d.line([(S / 2 - 50, y + 6), (S / 2 + 50, y + 6)], fill=ac if _lum(ac) < 0.6 else _mix(ac, dk, 0.5),
               width=4)
        y += 30
    words = page["words"]
    xl, xr = 100, S - 100
    ys, rh = _rows(y + 10, S - 110, len(words), 0)
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, PLAYFAIR, MESSIRI, ink, _mix(ink, bg, 0.5), ink,
                                                          en=62, ipa=30, ar=56, w_ar="SemiBold"), xr - xl,
                                              rh * 0.72), k_max=1.15)
    for j, (yy, w) in enumerate(zip(ys, words)):
        if j:
            d.line([(xl, yy), (xr, yy)], fill=_mix(ink, bg, 0.82), width=2)
        _side_by_side(fr, *_row_texts(w, k, PLAYFAIR, MESSIRI, ink, _mix(ink, bg, 0.5), ink, en=62, ipa=30,
                                      ar=56, w_ar="SemiBold"), xl, xr, yy + rh / 2)
    _footer(fr, handle, n, of, _mix(ink, bg, 0.45), y=S - 66, font=PLAYFAIR)
    return fr


def _chalk(im, seed=3):
    """Chalk texture: holes in the letters."""
    a = np.array(im.split()[3], np.float32)
    rng = np.random.default_rng(seed)
    a *= np.clip(rng.normal(0.88, 0.22, a.shape), 0.25, 1.0)
    out = im.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8)))
    return out


def _draw_chalk(page, pal, handle, n, of):
    """A green chalkboard in a wooden frame; white chalk words, yellow Arabic, chalk tick boxes."""
    board, chalk, yel = (38, 66, 54), (246, 246, 238), (255, 222, 110)
    rng = np.random.default_rng(7)
    arr = np.full((S, S, 3), board, np.float32) + rng.normal(0, 5, (S, S, 1))
    fr = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    smudge = Image.new("L", (S, S), 0)
    ds = ImageDraw.Draw(smudge)
    for _ in range(9):
        x, y, r = rng.integers(0, S), rng.integers(0, S), rng.integers(120, 300)
        ds.ellipse([x - r, y - r * 0.4, x + r, y + r * 0.4], fill=int(rng.integers(10, 26)))
    fr.alpha_composite(_colored(smudge.filter(ImageFilter.GaussianBlur(40)), (255, 255, 255)))
    d = ImageDraw.Draw(fr)
    d.rectangle([0, 0, S - 1, S - 1], outline=(120, 80, 44), width=26)
    d.rectangle([26, 26, S - 27, S - 27], outline=(84, 54, 28), width=4)
    y = 70
    if page.get("title"):
        t = _chalk(_fit_one(lambda s: _t(PATRICK, page["title"], s, chalk, "Regular"), 92, S - 200))
        _put(fr, t, S / 2, y + _h(t) / 2, "c")
        y += _h(t) + 4
        d.line([(S / 2 - _vis_w(t) / 2, y), (S / 2 + _vis_w(t) / 2, y + 4)], fill=yel, width=5)
        y += 22
    if page.get("sub"):
        st = _chalk(_fit_one(lambda s: _t(PATRICK, page["sub"], s, (210, 220, 210), "Regular"), 44, S - 200))
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 14
    words = page["words"]
    xl, xr = 120, S - 90
    ys, rh = _rows(y + 16, S - 100, len(words), 8)
    rh = min(rh, 190)
    top = (y + 16 + S - 100) / 2 - (rh * len(words) + 8 * (len(words) - 1)) / 2
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, PATRICK, RUQAA, chalk, (190, 205, 195), yel,
                                                          en=80, ipa=32, ar=68, w_en="Regular"), xr - xl,
                                              rh * 0.85), k_max=1.1)
    for j, w in enumerate(words):
        cy = top + j * (rh + 8) + rh / 2
        bx = 66
        d.rectangle([bx, cy - 16, bx + 32, cy + 16], outline=(220, 225, 215), width=3)
        d.line([(bx + 6, cy), (bx + 14, cy + 10), (bx + 34, cy - 18)], fill=(160, 240, 170), width=5)
        e, i, a = _row_texts(w, k, PATRICK, RUQAA, chalk, (190, 205, 195), yel, en=80, ipa=32, ar=68,
                             w_en="Regular")
        _side_by_side(fr, _chalk(e, j), _chalk(i, j + 9) if i is not None else None, _chalk(a, j + 3), xl, xr, cy)
    _footer(fr, handle, n, of, (200, 210, 200), y=S - 62, font=PATRICK)
    return fr


def _draw_poster(page, pal, handle, n, of):
    """Bold and loud: a big title block in the accent, the words as stacked pills, meanings in accent bubbles."""
    dk, ac, ac2 = _tones(pal)
    fr = Image.new("RGBA", (S, S), dk + (255,))
    d = ImageDraw.Draw(fr)
    for r in range(0, S + 60, 60):  # dot grid
        for c in range(0, S + 60, 60):
            d.ellipse([c - 3, r - 3, c + 3, r + 3], fill=_mix(dk, (255, 255, 255), 0.08))
    y = 56
    if page.get("title"):
        t = _fit_one(lambda s: _t(POPPINS_K, page["title"].upper(), s, dk, "Black"), 82, S - 200)
        bw, bh = _vis_w(t) + 70, _h(t) + 44
        blk = _round_mask(bw, bh, 18)
        _shadow(fr, blk, S / 2 - bw / 2, y, blur=2, alpha=0.9, dy=10)
        fr.alpha_composite(_colored(blk, ac), (int(S / 2 - bw / 2), int(y)))
        _put(fr, t, S / 2, y + bh / 2, "c")
        y += bh + 22
    if page.get("sub"):
        st = _fit_one(lambda s: _t(TAJAWAL, page["sub"], s, (255, 255, 255), "Bold"), 40, S - 200)
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 12
    words = page["words"]
    x0, x1 = 60, S - 60
    ys, rh = _rows(y + 18, S - 96, len(words), 16)
    rh = min(rh, 170)
    top = (y + 18 + S - 96) / 2 - (rh * len(words) + 16 * (len(words) - 1)) / 2
    split = x0 + (x1 - x0) * 0.6

    def texts(w, k):
        return _row_texts(w, k, MONTSERRAT, ALEXANDRIA, (255, 255, 255), _mix(ac, (255, 255, 255), 0.4),
                          _readable(ac2), en=62, ipa=30, ar=56, w_en="ExtraBold", w_ar="Bold")

    k = _common(words, lambda w, k: (lambda e, i, a: (
        (max(_vis_w(e), _vis_w(i) if i is not None else 0)) / (split - x0 - 60), _vis_w(a) / (x1 - split - 50),
        (_h(e) + (_h(i) + 6 if i is not None else 0)) / (rh * 0.84)))(*texts(w, k)), k_max=1.2)
    for j, w in enumerate(words):
        yy = top + j * (rh + 16)
        pill = _round_mask(x1 - x0, rh, rh / 2)
        fr.alpha_composite(_colored(pill, _mix(dk, (255, 255, 255), 0.12)), (x0, int(yy)))
        bub = _round_mask(x1 - split, rh - 20, (rh - 20) / 2)
        fr.alpha_composite(_colored(bub, ac2), (int(split - 10), int(yy + 10)))
        e, i, a = texts(w, k)
        if i is not None:
            hh = _h(e) + 6 + _h(i)
            _put(fr, e, x0 + 44, yy + rh / 2 - hh / 2 + _h(e) / 2)
            _put(fr, i, x0 + 44, yy + rh / 2 + hh / 2 - _h(i) / 2)
        else:
            _put(fr, e, x0 + 44, yy + rh / 2)
        _put(fr, a, (split - 10 + x1) / 2, yy + rh / 2, "c")
    _footer(fr, handle, n, of, _mix((255, 255, 255), dk, 0.3))
    return fr


_DRAW = {"cards": _draw_cards, "grid": _draw_grid, "table": _draw_table, "notebook": _draw_notebook,
         "minimal": _draw_minimal, "chalk": _draw_chalk, "poster": _draw_poster}


def post(page, style=DEFAULT_STYLE, palette=DEFAULT_PALETTE, handle="", n=1, of=1):
    """One page of words as a square RGB image."""
    words = [dict(en=w["en"], ar=w["ar"], ipa=w.get("ipa", "")) for w in page.get("words", [])][:6]
    if not words:
        raise ValueError("a post needs at least one word")
    pg = dict(title=page.get("title", ""), sub=page.get("sub", ""), words=words)
    fn = _DRAW.get(style, _DRAW[DEFAULT_STYLE])
    return fn(pg, palette if palette in DUOS else DEFAULT_PALETTE, handle or "", n, of).convert("RGB")
