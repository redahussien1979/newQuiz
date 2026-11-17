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
from .list_designs import (ALEXANDRIA, BALOO, DMSANS, DUOS, FREDOKA, INTER, LALEZAR, LITERATA, LOBSTER, MONTSERRAT,
                           PLEX_B, POPPINS_B, POPPINS_K, RUBIK, TAJAWAL, VAZIR, _circle_mask, _colored, _font,
                           _grad_text, _lum, _mix, _round_mask, _vis_w)
from .word_list import MESSIRI, PATRICK, PLAYFAIR, RUQAA

S = 1080  # square post
IPA_FONT = os.path.join(ROOT, "fonts", "NotoSans-Bold.ttf")
AMIRI = _font("Amiri", "Amiri-Bold.ttf")

STYLES = [("Cards", "cards"), ("Flashcard grid", "grid"), ("Table", "table"), ("Notebook", "notebook"),
          ("Minimal", "minimal"), ("Chalkboard", "chalk"), ("Poster", "poster"), ("Glass", "glass"),
          ("Bento", "bento"), ("Swiss", "swiss"), ("Dictionary", "dictionary"), ("Chat", "chat"),
          ("Sticky notes", "sticky"), ("Neo-brutal", "brutal"), ("Aurora", "aurora"),
          ("Highlighter", "highlighter"), ("Brush strokes", "brush")]
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


DEF_WRAP = 600   # px (x k): the width an English meaning wraps at
DEF_SIZE = 0.55  # its size against the word's
DEF_MIN = 30     # px: its smallest size (while the page is not too crowded)
_ONE_WEIGHT = {PATRICK}  # fonts with a single weight


def _wrap(words, fits):
    """Greedy lines of `words` that fit, then evened out: the narrowest width with the same number of lines."""
    def greedy(limit):
        lines, cur = [], []
        for wd in words:
            if cur and not fits(" ".join(cur + [wd]), limit):
                lines.append(" ".join(cur))
                cur = [wd]
            else:
                cur.append(wd)
        return lines + ([" ".join(cur)] if cur else [])
    return greedy, greedy(1.0)


def _join(parts, gap, align):
    """One text image (30 px margin, like text_img) of text images stacked with `gap`, aligned l / c / r."""
    w = max(_vis_w(p) for p in parts)
    h = sum(_h(p) for p in parts) + gap * (len(parts) - 1)
    out = Image.new("RGBA", (int(w) + 60, int(h) + 60), (0, 0, 0, 0))
    y = 30
    for p in parts:
        x = 30 if align == "l" else 30 + (w - _vis_w(p)) / 2 if align == "c" else 30 + w - _vis_w(p)
        out.alpha_composite(p, (int(round(x - 30)), int(round(y - 30))))
        y += _h(p) + gap
    return out


def _beside(a, b, gap):
    """Two text images on one line, bottoms level (the word and its IPA)."""
    h = max(_h(a), _h(b))
    out = Image.new("RGBA", (_vis_w(a) + gap + _vis_w(b) + 60, int(h) + 60), (0, 0, 0, 0))
    out.alpha_composite(a, (0, int(h - _h(a))))
    out.alpha_composite(b, (_vis_w(a) + gap, int(h - _h(b) - 2)))
    return out


def _entry(w, k, f_en, c_en, c_ipa, en=64, ipa=34, w_en="Bold", align="l", wrap=None, f_def=None):
    """(word image, IPA image or None). A word / idiom with an English meaning (`def`) becomes ONE block: the word
    with its IPA beside it, then the meaning wrapped in a few even lines (the IPA is then None). `wrap` = the width
    the design has for it (px); without it the meaning wraps at DEF_WRAP x k."""
    e = _t(f_en, w["en"], en * k, c_en, w_en)
    i = _ipa(w["ipa"], ipa * k, c_ipa) if w.get("ipa") else None
    if not w.get("def"):
        return e, i
    # readable on a phone (DEF_MIN), unless the page is crowded; always clearly smaller than the word itself
    size = min(max(en * k * DEF_SIZE, DEF_MIN * min(1.0, k / 0.55)), en * k * 0.75)
    f_def = f_def or f_en  # a script word font gets a plain font for its meaning
    weight = "Regular" if f_def in _ONE_WEIGHT else "Medium"
    limit = wrap or DEF_WRAP * k

    def img(s):
        return _t(f_def, s, size, c_ipa, weight)

    greedy, lines = _wrap(w["def"].split(), lambda s, f: _vis_w(img(s)) <= limit * f)
    for f in (0.95, 0.9, 0.85, 0.8, 0.75, 0.7):  # even lines: as narrow as possible with no extra line
        narrower = greedy(f)
        if len(lines) < 2 or len(narrower) != len(lines):
            break
        lines = narrower
    head = e
    if i is not None:
        head = _beside(e, i, int(14 * k)) if _vis_w(e) + _vis_w(i) <= limit * 1.1 else _join([e, i], 6, align)
    return _join([head] + [img(s) for s in lines], int(max(6, 12 * k)), align), None


def _row_texts(w, k, f_en, f_ar, c_en, c_ipa, c_ar, en=64, ipa=34, ar=58, w_en="Bold", w_ar="Bold", align="l",
               wrap=None, f_def=None):
    e, i = _entry(w, k, f_en, c_en, c_ipa, en, ipa, w_en, align, wrap, f_def)
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
        e, i, a = _row_texts(w, k, POPPINS_B, PLEX_B, dk, (110, 110, 130), dk, en=70, ipa=34, ar=62, align="c",
                             wrap=cw - 50)
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
        e, i, a = _row_texts(w, k, POPPINS_B, PLEX_B, dk, (110, 110, 130), dk, en=70, ipa=34, ar=62, align="c",
                             wrap=cw - 50)
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
                         _vis_w(a) / (x1 - mid - 60), max(_h(e), _h(a)) / (rh * (0.84 if w.get("def") else 0.62))))(
        *_row_texts(w, k, POPPINS_B, PLEX_B, dk, (120, 120, 140), dk, en=56, ipa=32, ar=54,
                     wrap=mid - x0 - 60)), k_max=1.2)
    for j, (yy, w) in enumerate(zip(ys, words)):
        if j % 2:
            d.rectangle([x0, yy, x1, yy + rh], fill=_mix(ac, (255, 255, 255), 0.82))
        if j:
            d.line([(x0 + 24, yy), (x1 - 24, yy)], fill=(225, 225, 232), width=2)
        e, i, a = _row_texts(w, k, POPPINS_B, PLEX_B, dk, (120, 120, 140), dk, en=56, ipa=32, ar=54,
                     wrap=mid - x0 - 60)
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


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _blob_bg(base, blobs, blur=110):
    """A base colour with big soft colour blobs [(x, y, r, colour, strength)] (drawn at 1/4 size: fast and smooth)."""
    q = 4
    im = Image.new("RGBA", (S // q, S // q), tuple(base) + (255,))
    for x, y, r, col, k in blobs:
        m = Image.new("L", im.size, 0)
        ImageDraw.Draw(m).ellipse([(x - r) / q, (y - r) / q, (x + r) / q, (y + r) / q], fill=int(255 * k))
        im.alpha_composite(_colored(m.filter(ImageFilter.GaussianBlur(blur / q)), col))
    return im.resize((S, S), Image.BICUBIC)


def _grain(im, sigma=6, seed=11):
    arr = np.array(im.convert("RGB"), np.float32)
    arr += np.random.default_rng(seed).normal(0, sigma, (S, S, 1))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def _hard_shadow(fr, mask, x, y, d=10, col=(0, 0, 0)):
    fr.alpha_composite(_colored(mask, col), (int(x + d), int(y + d)))


def _box(fr, x, y, w, h, r, fill, border=5, shadow=10):
    """Neo-brutal box: flat fill, thick black border, hard offset shadow."""
    m = _round_mask(w, h, r)
    if shadow:
        _hard_shadow(fr, m, x, y, shadow)
    fr.alpha_composite(_colored(m, (0, 0, 0)), (int(x), int(y)))
    fr.alpha_composite(_colored(_round_mask(w - 2 * border, h - 2 * border, max(1, r - border)), fill),
                       (int(x + border), int(y + border)))


def _stack(fr, parts, cx, top, gap, anchor="c"):
    """Text images one under the other from `top` (x = left / centre / right per anchor)."""
    y = top
    for p in parts:
        _put(fr, p, cx, y + _h(p) / 2, anchor)
        y += _h(p) + gap
    return y


def _draw_glass(page, pal, handle, n, of):
    """iOS-style glass: a soft colour mesh, frosted rounded panes with a fine light edge, white type."""
    dk, ac, ac2 = _tones(pal)
    fr = _blob_bg(_mix(dk, (0, 0, 0), 0.25), [(120, 120, 460, _mix(dk, (255, 255, 255), 0.4), 0.9),
                                              (1020, 360, 300, ac, 0.45), (960, 1060, 420, ac2, 0.35),
                                              (160, 980, 420, _mix(dk, (255, 255, 255), 0.22), 0.9)])
    fr = _grain(fr, 3)
    soft = fr.filter(ImageFilter.GaussianBlur(26))
    white = (255, 255, 255)
    y = _header(fr, page, 70, white, _mix(white, ac, 0.35), INTER, VAZIR, weight_t="ExtraBold")
    words = page["words"]
    top0 = max(y + 22, 80)
    ys, rh = _rows(top0, S - 100, len(words), 16)
    rh = min(rh, 190)
    top = (top0 + S - 100) / 2 - (rh * len(words) + 16 * (len(words) - 1)) / 2
    xl, xr = 60 + 100, S - 60 - 40
    ipa_c = _mix(white, dk, 0.3)
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, INTER, VAZIR, white, ipa_c, white, w_en="SemiBold"),
                                              xr - xl, rh * 0.74), k_max=1.15)
    for j, w in enumerate(words):
        yy = int(top + j * (rh + 16))
        m = _round_mask(S - 120, rh, min(40, rh / 2.4))
        _shadow(fr, m, 60, yy, blur=24, alpha=0.22, dy=12)
        pane = soft.crop((60, yy, S - 60, yy + int(rh)))
        pane.alpha_composite(Image.new("RGBA", pane.size, _mix(dk, (0, 0, 0), 0.2) + (70,)))
        pane.alpha_composite(Image.new("RGBA", pane.size, (255, 255, 255, 34)))
        pane.putalpha(m)
        fr.alpha_composite(pane, (60, yy))
        fr.alpha_composite(_colored(_round_mask(S - 120, rh, min(40, rh / 2.4), outline=2), white, 0.45), (60, yy))
        d = min(64, rh * 0.5)
        fr.alpha_composite(_colored(_circle_mask(d), white, 0.22), (int(60 + 30), int(yy + rh / 2 - d / 2)))
        _put(fr, _t(INTER, str(j + 1), d * 0.46, white, "Bold"), 60 + 30 + d / 2, yy + rh / 2, "c")
        _side_by_side(fr, *_row_texts(w, k, INTER, VAZIR, white, ipa_c, white, w_en="SemiBold"), xl, xr,
                      yy + rh / 2)
    _footer(fr, handle, n, of, _mix(white, dk, 0.25), font=INTER)
    return fr


def _bento_tiles(n, top, bottom, m=60, g=18):
    """Tile rectangles (x, y, w, h) for n words: rows of two with alternating wide / narrow tiles, an odd last one
    full width."""
    rows = (n + 1) // 2
    th = (bottom - top - g * (rows - 1)) / rows
    out, inner = [], S - 2 * m - g
    for r in range(rows):
        y = top + r * (th + g)
        if r == rows - 1 and n % 2:
            out.append((m, y, S - 2 * m, th))
            continue
        a = 0.58 if r % 2 == 0 else 0.42
        out += [(m, y, inner * a, th), (m + inner * a + g, y, inner * (1 - a), th)]
    return out


def _draw_bento(page, pal, handle, n, of):
    """Apple-keynote bento grid: a title tile and word tiles of mixed widths and colours."""
    dk, ac, ac2 = _tones(pal)
    bg = (240, 240, 244)
    fr = Image.new("RGBA", (S, S), bg + (255,))
    words = page["words"]
    top = 60
    if page.get("title") or page.get("sub"):
        th = 170 if page.get("sub") and page.get("title") else 130
        _card(fr, 60, top, S - 120, th, 34, dk, shadow=False)
        y = top + 34
        if page.get("title"):
            t = _fit_one(lambda s: _t(INTER, page["title"], s, ac, "ExtraBold"), 70, S - 220)
            _put(fr, t, 100, y + _h(t) / 2)
            y += _h(t) + 18
        if page.get("sub"):
            st = _fit_one(lambda s: _t(VAZIR, page["sub"], s, (255, 255, 255), "Medium"), 36, S - 220)
            _put(fr, st, 100, y + _h(st) / 2)
        top += th + 18
    tiles = _bento_tiles(len(words), top, S - 96)
    fills = [(255, 255, 255), ac, _mix(dk, (255, 255, 255), 0.12), _mix(ac2 if ac2 != ac else ac, (255, 255, 255),
                                                                          0.7)]
    order = [0, 1, 2, 3, 3, 0] if len(words) > 3 else [0, 1, 2]

    def texts(w, k, fill, tw):
        c = _readable(fill)
        sub = _mix(c, fill, 0.45)
        return _row_texts(w, k, INTER, VAZIR, c, sub, c, en=66, ipa=32, ar=60, w_en="Bold", wrap=tw - 64), sub

    def need(item, k):
        (w, (x, y, tw, th), fill) = item
        (e, i, a), _ = texts(w, k, fill, tw)
        h = 40 + _h(e) + (8 + _h(i) if i is not None else 0) + 24 + _h(a)
        return max(_vis_w(e), _vis_w(i) if i is not None else 0, _vis_w(a)) / (tw - 64), h / (th - 40)

    items = [(w, tiles[j], fills[order[j % len(order)]]) for j, w in enumerate(words)]
    k = _common(items, need, k_max=1.3)
    for j, (w, (x, y, tw, th), fill) in enumerate(items):
        _card(fr, x, y, tw, th, 30, fill, shadow=fill == (255, 255, 255))
        (e, i, a), sub = texts(w, k, fill, tw)
        _put(fr, _t(INTER, f"{j + 1:02d}", 24, sub, "SemiBold"), x + 32, y + 36)
        _stack(fr, [e] + ([i] if i is not None else []), x + 32, y + 62, 8, "l")
        _put(fr, a, x + tw - 32, y + th - 28 - _h(a) / 2, "r")
    _footer(fr, handle, n, of, _mix(dk, bg, 0.3), font=INTER)
    return fr


def _draw_swiss(page, pal, handle, n, of):
    """International typographic style: off-white, a strict grid, huge flush-left title, big numbers, one accent."""
    dk, ac, ac2 = _tones(pal)
    bg, ink = (243, 241, 236), (17, 17, 17)
    red = next((c for c in (ac2, ac, dk) if _contrast(c, bg) >= 3), dk)
    fr = Image.new("RGBA", (S, S), bg + (255,))
    d = ImageDraw.Draw(fr)
    words = page["words"]
    _put(fr, _t(INTER, "VOCABULARY", 22, ink, "Bold"), 60, 66)
    _put(fr, _t(INTER, f"{len(words):02d} WORDS", 22, ink, "Bold"), S - 60, 66, "r")
    d.line([(60, 90), (S - 60, 90)], fill=ink, width=2)
    y = 116
    if page.get("title"):
        t = _fit_one(lambda s: _t(INTER, page["title"], s, ink, "Black"), 112, S - 120)
        _put(fr, t, 60, y + _h(t) / 2)
        y += _h(t) + 18
    if page.get("sub"):
        st = _fit_one(lambda s: _t(VAZIR, page["sub"], s, red, "Bold"), 38, S - 120)
        _put(fr, st, 60, y + _h(st) / 2)
        y += _h(st) + 14
    d.rectangle([60, y + 8, S - 60, y + 14], fill=ink)
    top = y + 14
    ys, rh = _rows(top, S - 100, len(words), 0)
    xl, xr = 170, S - 60
    grey = (120, 120, 120)
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, INTER, VAZIR, ink, grey, ink, w_en="Bold",
                                                          w_ar="Bold"), xr - xl, rh * 0.72), k_max=1.15)
    for j, (yy, w) in enumerate(zip(ys, words)):
        if j:
            d.line([(60, yy), (S - 60, yy)], fill=(190, 188, 182), width=2)
        num = _t(INTER, f"{j + 1:02d}", min(56, rh * 0.42), red, "Black")
        _put(fr, num, 60, yy + rh / 2)
        _side_by_side(fr, *_row_texts(w, k, INTER, VAZIR, ink, grey, ink, w_en="Bold", w_ar="Bold"), xl, xr,
                      yy + rh / 2)
    d.line([(60, S - 92), (S - 60, S - 92)], fill=ink, width=2)
    _footer(fr, handle, n, of, ink, y=S - 60, font=INTER)
    return fr


def _draw_dictionary(page, pal, handle, n, of):
    """A bilingual dictionary page: guide words in the header, a double rule, entries (headword, IPA, meaning), a
    thumb-index tab with the first letter."""
    dk, ac, ac2 = _tones(pal)
    bg, ink, grey = (251, 248, 240), (28, 26, 24), (125, 118, 108)
    fr = Image.new("RGBA", (S, S), bg + (255,))
    d = ImageDraw.Draw(fr)
    words = page["words"]
    letter = (words[0]["en"][:1] or "A").upper()
    d.rounded_rectangle([S - 70, 300, S + 40, 430], 18, fill=dk)  # thumb tab
    _put(fr, _t(LITERATA, letter, 64, (255, 255, 255), "Bold"), S - 38, 365, "c")
    _put(fr, _t(LITERATA, words[0]["en"], 28, ink, "Bold"), 70, 70)
    if len(words) > 1:
        _put(fr, _t(LITERATA, words[-1]["en"], 28, ink, "Bold"), S - 70, 70, "r")
    y = 64
    if page.get("title"):
        t = _fit_one(lambda s: _t(LITERATA, page["title"], s, ink, "SemiBold"), 44, S - 520)
        _put(fr, t, S / 2, y + 6, "c")
    y = 108
    d.line([(70, y), (S - 70, y)], fill=ink, width=3)
    d.line([(70, y + 8), (S - 70, y + 8)], fill=ink, width=1)
    y += 30
    if page.get("sub"):
        st = _fit_one(lambda s: _t(AMIRI, page["sub"], s, dk, "Bold"), 40, S - 200)
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 14
    xl, xr = 90, S - 110
    ys, rh = _rows(y + 6, S - 100, len(words), 0)

    def texts(w, k):
        e, i = _entry(w, k, LITERATA, ink, grey, en=58, ipa=32, wrap=xr - xl - 40)
        a = _t(AMIRI, w["ar"], 64 * k, dk, "Bold")
        return e, i, a

    k = _common(words, lambda w, k: (lambda e, i, a: (
        (_vis_w(e) + (_vis_w(i) + 20 if i is not None else 0)) / (xr - xl - 40), _vis_w(a) / (xr - xl - 120),
        (_h(e) + 10 + _h(a)) / (rh * 0.86)))(*texts(w, k)), k_max=1.1)
    for j, (yy, w) in enumerate(zip(ys, words)):
        e, i, a = texts(w, k)
        hh = _h(e) + 10 + _h(a)
        y0 = yy + rh / 2 - hh / 2
        _put(fr, e, xl, y0 + _h(e) / 2)
        if i is not None:
            _put(fr, i, xl + _vis_w(e) + 20, y0 + _h(e) - _h(i) / 2 - 2)
        sense = _t(LITERATA, f"{j + 1}.", 30 * k + 4, grey, "SemiBold")
        ya = y0 + _h(e) + 10 + _h(a) / 2
        _put(fr, sense, xl + 34, ya)
        _put(fr, a, xl + 34 + _vis_w(sense) + 16, ya)  # "1. meaning", as in a bilingual dictionary
        if j < len(words) - 1:
            for xx in range(xl, xr, 14):
                d.ellipse([xx, yy + rh - 2, xx + 3, yy + rh + 1], fill=(205, 198, 186))
    _footer(fr, handle, n, of, grey, y=S - 56, font=LITERATA)
    return fr


def _tail(d, x, y, col, right):
    s = 1 if right else -1
    d.polygon([(x, y), (x + s * 22, y), (x, y + 22)], fill=col)


def _draw_chat(page, pal, handle, n, of):
    """A messaging-app screen: the title as the chat name, each word asked in a bubble, the meaning answered."""
    dk, ac, ac2 = _tones(pal)
    bg = _mix(dk, (255, 255, 255), 0.9)
    fr = Image.new("RGBA", (S, S), bg + (255,))
    d = ImageDraw.Draw(fr)
    for r in range(150, S, 70):  # wallpaper doodles
        for c in range((r // 70) % 2 * 35, S, 70):
            d.ellipse([c - 4, r - 4, c + 4, r + 4], outline=_mix(dk, bg, 0.82), width=2)
    d.rectangle([0, 0, S, 130], fill=dk)
    av = 78
    fr.alpha_composite(_colored(_circle_mask(av), ac), (52, 26))
    name = page.get("title") or "Vocabulary"
    _put(fr, _t(INTER, name[:1].upper(), 40, _readable(ac), "ExtraBold"), 52 + av / 2, 65, "c")
    nm = _fit_one(lambda s: _t(INTER, name, s, (255, 255, 255), "Bold"), 38, S - 330)
    stx = page.get("sub") or "online"
    st = _fit_one(lambda s: _t(VAZIR, stx, s, _mix(ac, (255, 255, 255), 0.3), "Medium"), 26, S - 330)
    _put(fr, nm, 152, 50)
    _put(fr, st, 152, 92)
    words = page["words"]
    me = ac if _lum(ac) > 0.35 else _mix(ac, (255, 255, 255), 0.6)
    me_ink = _readable(me)
    top, bot, gap, pad = 158, S - 92, 12, 18

    def bubbles(k):
        out = []
        for w in words:
            e, i = _entry(w, k, INTER, (25, 25, 30), (110, 110, 120), en=48, ipa=27, w_en="SemiBold",
                          wrap=S * 0.5)
            a = _t(VAZIR, w["ar"], 46 * k, me_ink, "Bold")
            lw = max(_vis_w(e), _vis_w(i) if i is not None else 0) + 2 * pad + 10
            lh = _h(e) + (_h(i) + 6 if i is not None else 0) + 2 * pad
            rw, rh = _vis_w(a) + 2 * pad + 96, _h(a) + 2 * pad
            out.append((e, i, a, lw, lh, rw, rh))
        return out

    # the answer comes in a little lower than the question (a chat, but each word takes ~1.5 bubbles of height)
    def row_h(b):
        return max(b[4], b[4] * 0.5 + b[6]) + gap

    k = 1.35
    for _ in range(40):
        bs = bubbles(k)
        hh = sum(row_h(b) for b in bs) - gap
        if hh <= bot - top and all(b[3] + b[5] + 30 <= S - 120 for b in bs):
            break
        k *= 0.96
    y = top + max(0, (bot - top - hh) / 2)
    for j, b in enumerate(bs):
        e, i, a, lw, lh, rw, rh = b
        _card(fr, 60, y, lw, lh, 24, (255, 255, 255), shadow=False)
        _tail(d, 60, y, (255, 255, 255), False)
        _stack(fr, [e] + ([i] if i is not None else []), 60 + pad + 4, y + pad, 6, "l")
        x, yr = S - 60 - rw, y + lh * 0.5
        _card(fr, x, yr, rw, rh, 24, me, shadow=False)
        _tail(d, S - 60, yr, me, True)
        _put(fr, a, S - 60 - pad - 4, yr + rh / 2, "r")
        tc = _mix(me_ink, me, 0.45)
        _put(fr, _t(INTER, f"10:{j * 3 + 2:02d}", 18, tc, "Medium"), x + pad, yr + rh - 20)
        tx, ty = x + pad + 52, yr + rh - 20
        for o in (0, 8):  # read ticks
            d.line([(tx + o, ty), (tx + o + 4, ty + 5), (tx + o + 12, ty - 6)], fill=tc, width=3)
        y += row_h(b)
    _footer(fr, handle, n, of, _mix(dk, bg, 0.35), font=INTER)
    return fr


_NOTE_COLS = [(255, 233, 120), (255, 186, 196), (170, 222, 255), (186, 240, 196), (220, 200, 255), (255, 206, 150)]
_TILT = [-3.0, 2.2, -1.6, 2.8, -2.4, 1.4]


def _draw_sticky(page, pal, handle, n, of):
    """Sticky notes taped to a deep wall, a little tilted; the title on a paper strip."""
    dk, ac, ac2 = _tones(pal)
    fr = _grain(_gradient(_mix(dk, (255, 255, 255), 0.06), _mix(dk, (0, 0, 0), 0.3), angle=30), 4)
    words = page["words"]
    y = 50
    if page.get("title") or page.get("sub"):
        parts = []
        if page.get("title"):
            parts.append(_fit_one(lambda s: _t(FREDOKA, page["title"], s, (30, 30, 36), "Bold"), 66, S - 300))
        if page.get("sub"):
            parts.append(_fit_one(lambda s: _t(BALOO, page["sub"], s, dk, "Bold"), 36, S - 300))
        bw = max(_vis_w(p) for p in parts) + 90
        bh = sum(_h(p) for p in parts) + 12 * (len(parts) - 1) + 50
        strip = Image.new("RGBA", (int(bw), int(bh)), (252, 250, 244, 255))
        _stack(strip, parts, bw / 2, 25, 12)
        rot = strip.rotate(-1.5, Image.BICUBIC, expand=True)
        _shadow(fr, rot.split()[3], S / 2 - rot.width / 2, y, blur=10, alpha=0.4, dy=8)
        fr.alpha_composite(rot, (int(S / 2 - rot.width / 2), int(y)))
        tape = Image.new("RGBA", (130, 40), (255, 255, 255, 120)).rotate(-6, Image.BICUBIC, expand=True)
        fr.alpha_composite(tape, (int(S / 2 - 65), int(y - 14)))
        y += rot.height + 20
    cols, rows = _grid_shape(len(words))
    top, bot, m, g = max(y, 60), S - 90, 70, 36
    side = min((S - 2 * m - g * (cols - 1)) / cols, (bot - top - g * (rows - 1)) / rows)
    gx = (S - (side * cols + g * (cols - 1))) / 2
    top = (top + bot) / 2 - (side * rows + g * (rows - 1)) / 2
    ink = (34, 34, 40)

    def texts(w, k):
        e, i = _entry(w, k, FREDOKA, ink, (80, 80, 90), en=64, ipa=30, w_en="SemiBold", align="c",
                      wrap=side - 50)
        a = _t(BALOO, w["ar"], 60 * k, dk, "Bold")
        return e, i, a

    def need(w, k):
        e, i, a = texts(w, k)
        h = _h(e) + (10 + _h(i) if i is not None else 0) + 26 + _h(a)
        return max(_vis_w(e), _vis_w(i) if i is not None else 0, _vis_w(a)) / (side - 50), h / (side - 70)

    k = _common(words, need, k_max=1.5)
    palette = [_mix(ac, (255, 255, 255), 0.35)] + _NOTE_COLS
    for j, w in enumerate(words):
        r, c = divmod(j, cols)
        note = Image.new("RGBA", (int(side), int(side)), palette[j % len(palette)] + (255,))
        nd = ImageDraw.Draw(note)
        nd.polygon([(side, side - 40), (side, side), (side - 40, side)], fill=_mix(palette[j % len(palette)],
                                                                                   (0, 0, 0), 0.12))
        e, i, a = texts(w, k)
        hh = _h(e) + (10 + _h(i) if i is not None else 0) + 26 + _h(a)
        _stack(note, [e] + ([i] if i is not None else []), side / 2, side / 2 - hh / 2, 10)
        _put(note, a, side / 2, side / 2 + hh / 2 - _h(a) / 2, "c")
        rot = note.rotate(_TILT[j % len(_TILT)], Image.BICUBIC, expand=True)
        cx, cy = gx + c * (side + g) + side / 2, top + r * (side + g) + side / 2
        _shadow(fr, rot.split()[3], cx - rot.width / 2, cy - rot.height / 2, blur=12, alpha=0.45, dy=12)
        fr.alpha_composite(rot, (int(cx - rot.width / 2), int(cy - rot.height / 2)))
        tape = Image.new("RGBA", (110, 34), (255, 255, 255, 110)).rotate(_TILT[j % len(_TILT)] * 2, Image.BICUBIC,
                                                                          expand=True)
        fr.alpha_composite(tape, (int(cx - tape.width / 2), int(cy - side / 2 - 18)))
    _footer(fr, handle, n, of, _mix((255, 255, 255), dk, 0.25), font=FREDOKA)
    return fr


def _draw_brutal(page, pal, handle, n, of):
    """Neo-brutalism: a flat bright background, thick black outlines, hard offset shadows, chunky type."""
    dk, ac, ac2 = _tones(pal)
    bg = ac if _lum(ac) > 0.3 else _mix(ac, (255, 255, 255), 0.5)
    tag = ac2 if ac2 != ac and _contrast(ac2, bg) > 1.3 else (255, 255, 255)
    black = (0, 0, 0)
    fr = Image.new("RGBA", (S, S), bg + (255,))
    d = ImageDraw.Draw(fr)
    for r in range(0, S, 36):
        for c in range(0, S, 36):
            d.point([(c, r), (c + 1, r), (c, r + 1), (c + 1, r + 1)], fill=_mix(bg, black, 0.25))
    y = 54
    if page.get("title"):
        t = _fit_one(lambda s: _t(RUBIK, page["title"].upper(), s, (255, 255, 255), "Black"), 76, S - 240)
        bw, bh = _vis_w(t) + 70, _h(t) + 46
        blk = Image.new("RGBA", (int(bw) + 20, int(bh) + 20), (0, 0, 0, 0))
        _box(blk, 0, 0, bw, bh, 14, black, border=0, shadow=0)
        _put(blk, t, bw / 2, bh / 2, "c")
        rot = blk.rotate(1.6, Image.BICUBIC, expand=True)
        fr.alpha_composite(_colored(rot.split()[3], tag), (int(S / 2 - rot.width / 2 + 10), int(y + 10)))
        fr.alpha_composite(rot, (int(S / 2 - rot.width / 2), int(y)))
        y += rot.height + 12
    if page.get("sub"):
        st = _fit_one(lambda s: _t(TAJAWAL, page["sub"], s, black, "Bold"), 40, S - 200)
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 10
    words = page["words"]
    top0 = y + 18
    ys, rh = _rows(top0, S - 100, len(words), 20)
    rh = min(rh, 170)
    top = (top0 + S - 100) / 2 - (rh * len(words) + 20 * (len(words) - 1)) / 2
    x0, x1 = 56, S - 66
    sq = min(76, rh - 40)
    xl = x0 + 26 + sq + 26

    def texts(w, k):
        return _row_texts(w, k, RUBIK, TAJAWAL, black, (70, 70, 70), _readable(tag), en=60, ipa=30, ar=52,
                          w_en="ExtraBold", w_ar="Black")

    k = _common(words, lambda w, k: (lambda e, i, a: (
        (max(_vis_w(e), _vis_w(i) if i is not None else 0) + _vis_w(a) + 100) / (x1 - xl - 30),
        max(_h(e) + (_h(i) + 6 if i is not None else 0), _h(a) + 36) / (rh * 0.86)))(*texts(w, k)), k_max=1.2)
    for j, w in enumerate(words):
        yy = top + j * (rh + 20)
        _box(fr, x0, yy, x1 - x0, rh, 18, (255, 255, 255))
        _box(fr, x0 + 26, yy + rh / 2 - sq / 2, sq, sq, 10, black, border=0, shadow=0)
        _put(fr, _t(RUBIK, str(j + 1), sq * 0.55, bg, "Black"), x0 + 26 + sq / 2, yy + rh / 2, "c")
        e, i, a = texts(w, k)
        if i is not None:
            hh = _h(e) + 6 + _h(i)
            _put(fr, e, xl, yy + rh / 2 - hh / 2 + _h(e) / 2)
            _put(fr, i, xl, yy + rh / 2 + hh / 2 - _h(i) / 2)
        else:
            _put(fr, e, xl, yy + rh / 2)
        pw, ph = _vis_w(a) + 52, _h(a) + 30
        _box(fr, x1 - 24 - pw, yy + rh / 2 - ph / 2, pw, ph, ph / 2, tag, border=4, shadow=5)
        _put(fr, a, x1 - 24 - pw / 2, yy + rh / 2, "c")
    _footer(fr, handle, n, of, black, font=RUBIK)
    return fr


def _draw_aurora(page, pal, handle, n, of):
    """Dark mode with an aurora glow and film grain: gradient title, quiet rows, meanings in gradient ink."""
    dk, ac, ac2 = _tones(pal)
    base = _mix(dk, (0, 0, 0), 0.72)
    c2 = ac2 if ac2 != ac else _mix(ac, (255, 255, 255), 0.55)
    fr = _blob_bg(base, [(200, -60, 520, ac, 0.55), (900, 60, 420, c2, 0.45), (540, 1180, 520,
                                                                                _mix(dk, (255, 255, 255), 0.25), 0.7)],
                  blur=170)
    fr = _grain(fr, 7)
    white = (250, 250, 252)
    y = 74
    if page.get("title"):
        t = _fit_one(lambda s: _t(DMSANS, page["title"], s, white, "Bold"), 92, S - 140)
        _put(fr, _grad_text(t, ac, c2), S / 2, y + _h(t) / 2, "c")
        y += _h(t) + 18
    if page.get("sub"):
        st = _fit_one(lambda s: _t(VAZIR, page["sub"], s, _mix(white, base, 0.35), "Medium"), 36, S - 140)
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 14
    words = page["words"]
    top0 = y + 24
    ys, rh = _rows(top0, S - 100, len(words), 0)
    xl, xr = 150, S - 80
    dim = _mix(white, base, 0.5)
    k = _common(words, lambda w, k: _sbs_need(*_row_texts(w, k, DMSANS, VAZIR, white, dim, white, w_en="SemiBold"),
                                              xr - xl, rh * 0.72), k_max=1.15)
    line = Image.new("RGBA", (S - 160, 2), (255, 255, 255, 30))
    for j, (yy, w) in enumerate(zip(ys, words)):
        if j:
            fr.alpha_composite(line, (80, int(yy)))
        _put(fr, _t(DMSANS, f"{j + 1:02d}", 30, dim, "Medium"), 80, yy + rh / 2)
        e, i, a = _row_texts(w, k, DMSANS, VAZIR, white, dim, white, w_en="SemiBold")
        _side_by_side(fr, e, i, _grad_text(a, c2, ac), xl, xr, yy + rh / 2)
    _footer(fr, handle, n, of, dim, font=DMSANS)
    return fr


# ---------------------------------------------------------------- hand-made marks (highlighter, red pen, brush)
RED_PEN = (214, 40, 40)
MARKER = (255, 214, 10)
_NEWS = ("market council weather report minister city budget school league museum harbour station festival "
         "science record election island energy village history garden railway theatre summer winter "
         "national local daily morning evening review").split()


def _smooth_noise(n, rng, scale, octaves=((24, 1.0), (7, 0.35))):
    """1-D value noise of length n (smooth bumps every `period` samples), amplitude `scale`."""
    out = np.zeros(n, np.float32)
    for period, amp in octaves:
        k = max(2, n // period + 2)
        pts = rng.uniform(-1, 1, k)
        out += np.interp(np.arange(n) / max(1, period), np.arange(k), pts) * amp
    return out * scale


def _marker_band(w, h, col=MARKER, seed=1, alpha=0.88):
    """A highlighter stroke: flat ink with slightly wavy edges, slanted chisel ends and faint streaks."""
    rng = np.random.default_rng(seed)
    w, h = int(w), int(h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    top = 2 + _smooth_noise(w, rng, 2.5)
    bot = h - 3 + _smooth_noise(w, rng, 2.5)
    slant = h * 0.35
    left = 4 + (yy / h) * slant * 0.5 + rng.uniform(0, 4)
    right = w - 6 - (1 - yy / h) * slant * 0.5 - rng.uniform(0, 4)
    m = (yy >= top[None, :]) & (yy <= bot[None, :]) & (xx >= left) & (xx <= right)
    streak = 0.86 + 0.14 * np.repeat(rng.uniform(0, 1, (h, 1)), w, axis=1)
    a = Image.fromarray((m * streak * alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    return _colored(a, col)


def _pen_path(pts, width, col, size, s=3):
    """A pen stroke through `pts` with a width that swells in the middle and thins at both ends."""
    big = Image.new("L", (int(size[0] * s), int(size[1] * s)), 0)
    d = ImageDraw.Draw(big)
    n = len(pts)
    for j in range(n - 1):
        t = j / max(1, n - 2)
        wd = width * (0.45 + 0.55 * math.sin(math.pi * min(1, max(0, t))) ** 0.5)
        (x0, y0), (x1, y1) = pts[j], pts[j + 1]
        d.line([(x0 * s, y0 * s), (x1 * s, y1 * s)], fill=255, width=max(1, int(wd * s)))
        r = wd * s / 2
        d.ellipse([x1 * s - r, y1 * s - r, x1 * s + r, y1 * s + r], fill=255)
    return _colored(big.resize((int(size[0]), int(size[1])), Image.LANCZOS), col)


def _pen_circle(w, h, col=RED_PEN, width=6, seed=2):
    """A hand-drawn loop around a w x h box: a little more than one turn, wobbling, ends overlapping."""
    rng = np.random.default_rng(seed)
    pad = width * 2 + 10
    W_, H_ = w + 2 * pad, h + 2 * pad
    cx, cy = W_ / 2, H_ / 2
    a0 = math.radians(rng.uniform(150, 210))
    turns = 1.12
    ph = rng.uniform(0, 6.3, 2)
    pts = []
    for j in range(140):
        t = j / 139
        a = a0 + t * turns * 2 * math.pi
        grow = 1 + 0.06 * t  # the second pass runs a bit wider, as a real hand does
        rx = w / 2 * grow * (1 + 0.03 * math.sin(3 * a + ph[0]))
        ry = h / 2 * grow * (1 + 0.05 * math.sin(2 * a + ph[1]))
        pts.append((cx + rx * math.cos(a) + t * 6, cy + ry * math.sin(a) - t * 3))
    return _pen_path(pts, width, col, (W_, H_)), pad


def _pen_underline(w, col=RED_PEN, width=5, seed=3):
    """Two quick pen strokes under a word, the second slightly shorter and tilted."""
    rng = np.random.default_rng(seed)
    H_ = 34
    im = Image.new("RGBA", (int(w) + 20, H_), (0, 0, 0, 0))
    for k, (x0, x1, y0, y1) in enumerate(((4, w + 8, 10, 14), (w * 0.12, w + 2, 22, 19))):
        bow = rng.uniform(-3, 3)
        pts = [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + bow * math.sin(math.pi * t)) for t in np.linspace(0, 1, 40)]
        im.alpha_composite(_pen_path(pts, width * (1 - 0.15 * k), col, im.size))
    return im


def _newsprint(seed=5):
    """Old newspaper paper: warm off-white, blurred columns of print and headlines, grain and a soft vignette."""
    rng = np.random.default_rng(seed)
    fr = Image.new("RGBA", (S, S), (236, 230, 216, 255))
    ink = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    y = -20
    while y < S:
        if rng.uniform() < 0.25:  # a headline
            txt = " ".join(rng.choice(_NEWS, 2)).title()
            im = _t(LITERATA, txt, int(rng.integers(48, 70)), (40, 36, 30), "Bold")
            ink.alpha_composite(im, (int(rng.integers(-60, S // 2)), int(y)))
            y += im.height - 20
            continue
        for c in range(4):  # body text in columns
            line = " ".join(rng.choice(_NEWS, 4))
            im = _t(LITERATA, line, 26, (60, 55, 46), "Regular")
            ink.alpha_composite(im.crop((0, 0, min(im.width, 280), im.height)), (c * 280 - 10, int(y)))
        y += 34
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    centre = np.clip(((xx - S / 2) / (S * 0.52)) ** 2 + ((yy - S / 2) / (S * 0.56)) ** 2, 0, 1)
    a = np.array(ink.split()[3], np.float32) * (0.06 + 0.22 * centre)  # the print fades out behind the words
    ink.putalpha(Image.fromarray(a.astype(np.uint8)))
    fr.alpha_composite(ink.filter(ImageFilter.GaussianBlur(3.2)))
    v = 1 - 0.28 * np.clip(((xx - S / 2) / (S * 0.75)) ** 2 + ((yy - S / 2) / (S * 0.75)) ** 2, 0, 1)
    arr = np.array(fr.convert("RGB"), np.float32) * v[..., None]
    arr += rng.normal(0, 5, (S, S, 1))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def _draw_highlighter(page, pal, handle, n, of):
    """Newspaper paper; the title and every word under a yellow highlighter, the last title word and the numbers
    circled in red pen, the meanings underlined in red pen."""
    dk, ac, ac2 = _tones(pal)
    fr = _newsprint()
    ink, grey = (22, 20, 18), (88, 82, 72)
    marker = MARKER if _lum(ac) < 0.45 or _contrast(ac, (236, 230, 216)) < 1.15 else ac
    y = 56
    if page.get("title"):
        words_t = page["title"].split()
        t = _fit_one(lambda s_: _t(PLAYFAIR, page["title"], s_, ink, "Bold"), 104, S - 220)
        x0 = S / 2 - _vis_w(t) / 2
        lit = t
        if len(words_t) > 1:  # highlight the first words, circle the last one
            px = _font_px(t, page["title"])
            lit = _t(PLAYFAIR, " ".join(words_t[:-1]), px, ink, "Bold")
            last = _t(PLAYFAIR, words_t[-1], px, ink, "Bold")
            circ, pad = _pen_circle(_vis_w(last) + 34, _h(t) + 26, RED_PEN, 6, seed=4)
            lx = x0 + _vis_w(t) - _vis_w(last)
            fr.alpha_composite(circ, (int(lx - 17 - pad), int(y - 13 - pad)))
        band = _marker_band(_vis_w(lit) + 40, _h(t) * 0.62, marker, seed=7)
        fr.alpha_composite(band, (int(x0 - 20), int(y + _h(t) * 0.42)))
        _put(fr, t, S / 2, y + _h(t) / 2, "c")
        y += _h(t) + 34
    d = ImageDraw.Draw(fr)
    if page.get("sub"):
        st = _fit_one(lambda s_: _t(VAZIR, page["sub"], s_, ink, "Medium"), 34, S - 260)
        d.line([(120, y), (S - 120, y)], fill=ink, width=2)
        _put(fr, st, S / 2, y + 14 + _h(st) / 2, "c")
        y += _h(st) + 28
        d.line([(120, y), (S - 120, y)], fill=ink, width=2)
        y += 10
    words = page["words"]
    xl, xr = 150, S - 80
    top0 = y + 18
    ys, rh = _rows(top0, S - 96, len(words), 0)
    rh = min(rh, 200)
    top = (top0 + S - 96) / 2 - rh * len(words) / 2

    def texts(w, k):
        return _row_texts(w, k, PLAYFAIR, AMIRI, ink, grey, ink, en=66, ipa=32, ar=62)

    k = _common(words, lambda w, k: _sbs_need(*texts(w, k), xr - xl, rh * 0.8), k_max=1.15)
    for j, w in enumerate(words):
        cy = top + j * rh + rh / 2
        e, i, a = texts(w, k)
        word = _t(PLAYFAIR, w["en"], 66 * k, ink, "Bold")
        hh = _h(e) + (8 + _h(i) if i is not None else 0)
        ytop = cy - hh / 2
        band = _marker_band(_vis_w(word) + 26, _h(word) * 0.66, marker, seed=20 + j)
        fr.alpha_composite(band, (int(xl - 13), int(ytop + _h(word) * 0.4)))
        _side_by_side(fr, e, i, a, xl, xr, cy)
        ul = _pen_underline(_vis_w(a), RED_PEN, 4, seed=40 + j)
        fr.alpha_composite(ul, (int(xr - _vis_w(a) - 6), int(cy + _h(a) / 2 - 4)))
        num = _t(PLAYFAIR, str(j + 1), 40, ink, "Bold")
        circ, pad = _pen_circle(58, 58, RED_PEN, 4, seed=60 + j)
        fr.alpha_composite(circ, (int(84 - 29 - pad), int(cy - 29 - pad)))
        _put(fr, num, 84, cy, "c")
    _footer(fr, handle, n, of, grey, font=PLAYFAIR)
    return fr


def _font_px(im, txt):
    """The font size a fitted text image was drawn at (its height ratio to the text drawn at 100 px)."""
    ref = _t(PLAYFAIR, txt, 100, (0, 0, 0), "Bold")
    return max(12, int(round(100 * _h(im) / max(1, _h(ref)))))


_WATER = [(250, 168, 20), (240, 82, 110), (86, 70, 64), (12, 140, 236), (34, 170, 120), (130, 90, 220)]


def _brush_stroke(w, h, col, seed=1):
    """A dry-brush watercolour stroke: bristle tracks with ragged, frayed ends, wavy edges, pale streaks and
    darker pooled edges."""
    rng = np.random.default_rng(seed)
    w, h = int(w), int(h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    top = h * 0.08 + _smooth_noise(w, rng, h * 0.05, ((60, 1.0), (9, 0.4)))
    bot = h * 0.92 + _smooth_noise(w, rng, h * 0.05, ((60, 1.0), (9, 0.4)))
    # bristles: every 2 px row starts / ends at its own place (frayed ends), a few strands reach much further
    rows = np.arange(h)
    s0 = w * 0.05 + np.abs(_smooth_noise(h, rng, w * 0.035, ((14, 1.0), (3, 0.6))))
    e0 = w * 0.95 - np.abs(_smooth_noise(h, rng, w * 0.04, ((14, 1.0), (3, 0.6))))
    long_ = rng.uniform(0, 1, h) < 0.08
    s0[long_] -= rng.uniform(0, w * 0.04, long_.sum())
    e0[long_] += rng.uniform(0, w * 0.04, long_.sum())
    m = ((xx >= s0[rows][:, None]) & (xx <= e0[rows][:, None]) &
         (yy >= top[None, :]) & (yy <= bot[None, :])).astype(np.float32)
    # dry-brush gaps: thin pale streaks that start near the ends of the stroke
    for _ in range(int(h / 22)):
        r = int(rng.integers(int(h * 0.15), int(h * 0.85)))
        th = int(rng.integers(1, 3))
        fade = rng.uniform(0.35, 0.7)
        if rng.uniform() < 0.5:
            m[r:r + th, :int(rng.uniform(w * 0.08, w * 0.18))] *= fade
        else:
            m[r:r + th, int(rng.uniform(w * 0.84, w * 0.93)):] *= fade
    a = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8))
    da = ImageDraw.Draw(a)
    for _ in range(10):  # paint specks flicked off near both ends
        x = rng.uniform(0, w * 0.06) if rng.uniform() < 0.5 else rng.uniform(w * 0.94, w)
        y, r = rng.uniform(h * 0.15, h * 0.85), rng.uniform(1.2, 3.2)
        da.ellipse([x - r, y - r, x + r, y + r], fill=230)
    a = a.filter(ImageFilter.GaussianBlur(0.9))
    am = np.array(a, np.float32) / 255
    edge = np.clip(am - np.array(a.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255, 0, 1)
    tex = 0.95 + 0.05 * _smooth_noise(w, rng, 1.0, ((150, 1.0),))[None, :] * np.ones((h, 1))  # gentle wash
    rgb = np.array(col, np.float32)[None, None, :] * (tex[..., None] * (1 - 0.35 * edge[..., None]))
    out = np.dstack([np.clip(rgb, 0, 255), (am * 255)[..., None]]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _soft_shadow_text(fr, im, x, y, anchor="l"):
    sh = _colored(im.split()[3].filter(ImageFilter.GaussianBlur(4)), (0, 0, 0), 0.35)
    _put(fr, sh, x + 2, y + 3, anchor)
    _put(fr, im, x, y, anchor)


def _draw_brush(page, pal, handle, n, of):
    """Watercolour brush strokes on paper, one colour per word; a script title, white type on the strokes."""
    dk, ac, ac2 = _tones(pal)
    rng = np.random.default_rng(9)
    arr = np.full((S, S, 3), (250, 248, 243), np.float32) + rng.normal(0, 3, (S, S, 1))
    fr = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    y = 46
    if page.get("title"):
        t = _fit_one(lambda s_: _t(LOBSTER, page["title"], s_, dk, "Regular"), 100, S - 180)
        _put(fr, t, S / 2, y + _h(t) / 2, "c")
        y += _h(t) + 16
    if page.get("sub"):
        st = _fit_one(lambda s_: _t(ALEXANDRIA, page["sub"], s_, _mix(dk, (255, 255, 255), 0.3), "SemiBold"), 36,
                      S - 200)
        _put(fr, st, S / 2, y + _h(st) / 2, "c")
        y += _h(st) + 12
    words = page["words"]
    top0 = y + 14
    gap = 12
    ys, rh = _rows(top0, S - 92, len(words), gap)
    rh = min(rh, 175)
    top = (top0 + S - 92) / 2 - (rh * len(words) + gap * (len(words) - 1)) / 2
    x0, x1 = 34, S - 34
    xl, xr = x0 + (x1 - x0) * 0.1, x1 - (x1 - x0) * 0.1
    white = (255, 255, 255)
    soft = (255, 255, 255)

    def texts(w, k):
        return _row_texts(w, k, LOBSTER, LALEZAR, white, soft, white, en=70, ipa=30, ar=62, w_en="Regular",
                          w_ar="Regular", f_def=MONTSERRAT)

    k = _common(words, lambda w, k: _sbs_need(*texts(w, k), xr - xl, rh * 0.74), k_max=1.15)
    for j, w in enumerate(words):
        yy = top + j * (rh + gap)
        col = _WATER[j % len(_WATER)]
        stroke = _brush_stroke(x1 - x0, rh, col, seed=100 + j)
        fr.alpha_composite(stroke, (int(x0), int(yy)))
        e, i, a = texts(w, k)
        cy = yy + rh / 2
        if i is not None:
            hh = _h(e) + 6 + _h(i)
            _soft_shadow_text(fr, e, xl, cy - hh / 2 + _h(e) / 2)
            _soft_shadow_text(fr, i, xl, cy + hh / 2 - _h(i) / 2)
        else:
            _soft_shadow_text(fr, e, xl, cy)
        _soft_shadow_text(fr, a, xr, cy, "r")
    _footer(fr, handle, n, of, _mix(dk, (255, 255, 255), 0.35), font=ALEXANDRIA)
    return fr


_DRAW = {"cards": _draw_cards, "grid": _draw_grid, "table": _draw_table, "notebook": _draw_notebook,
         "minimal": _draw_minimal, "chalk": _draw_chalk, "poster": _draw_poster, "glass": _draw_glass,
         "bento": _draw_bento, "swiss": _draw_swiss, "dictionary": _draw_dictionary, "chat": _draw_chat,
         "sticky": _draw_sticky, "brutal": _draw_brutal, "aurora": _draw_aurora,
         "highlighter": _draw_highlighter, "brush": _draw_brush}


def post(page, style=DEFAULT_STYLE, palette=DEFAULT_PALETTE, handle="", n=1, of=1):
    """One page of words as a square RGB image."""
    words = [dict(en=w["en"], ar=w["ar"], ipa=w.get("ipa", ""), **({"def": w["def"]} if w.get("def") else {}))
             for w in page.get("words", [])][:6]
    if not words:
        raise ValueError("a post needs at least one word")
    pg = dict(title=page.get("title", ""), sub=page.get("sub", ""), words=words)
    fn = _DRAW.get(style, _DRAW[DEFAULT_STYLE])
    return fn(pg, palette if palette in DUOS else DEFAULT_PALETTE, handle or "", n, of).convert("RGB")
