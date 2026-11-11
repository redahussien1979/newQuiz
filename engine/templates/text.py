"""English Texts: a paragraph read aloud (your recording, e.g. from ElevenLabs). The text inks in word by word exactly
as it is spoken; each highlighted word is marked, then flies down into the word bank, where its Arabic meaning writes
itself in from right to left.

Words box (the project's `text.words`, same columns as the Excel tabs B-F, see engine/text_batch.py):
    word | start | end | highlighted | arabic
one spoken word per line, times in seconds in the recording. A line with something in `highlighted` flies into the
word bank (the highlighted text is what the bank shows; `*` = the word itself). Neighbouring lines with the same
several-word highlighted text (e.g. "chase away" on both lines) fly together as one phrase. Missing times are
estimated (then the words just follow a steady reading pace).

Designs (`text.style`) — one reading engine (timing, pages, flights, recording cuts) in TextVideo, each design
only supplies its look (background, header, word mark, word bank, finish):
    textbook   school-book page: colour band, highlighter swipe, ruled Word Bank            (TextVideo)
    studio     dark premium: words glow gold, glass cards                                    (StudioVideo)
    exam       IELTS-style passage on a desk: line numbers, red-pen boxes, Key Vocabulary   (ExamVideo)
               with the line of each word, a "LEARNED" stamp at the end
    notebook   handwriting on lined paper: red pen circles, sticky notes                     (NotebookVideo)

Lines are broken for the most even right edge (fewest lines first) and justified (all but the last line). Long
paragraphs are split into pages at sentence ends (the page turns, and the recording waits for it); with more than
one page a recap of all the words closes the reading. Optional: a level badge (`level`, A1-C2) and the Arabic
translation of the whole paragraph (`translation`), shown after the reading. Everything is laid out inside the
Shorts safe area (above y 1536, right edge 918). render(t) depends only on t (frames are drawn on several processes).
"""
import math
import os
import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..audio import SR, audio_length, load_audio
from ..core import (DEFAULT_FONT, H, ROOT, W, ease_io, ease_out_back, get_font, global_fade, prog,
                    text_img_in)

NAME = "English Texts"

_LIB = os.path.join(ROOT, "fonts", "library")


def _lib(*parts):
    path = os.path.join(_LIB, *parts)
    return path if os.path.isfile(path) else DEFAULT_FONT


SERIF = _lib("Literata", "Literata[opsz,wght].ttf")
AR_FONT = _lib("Amiri", "Amiri-Bold.ttf")
LABEL = _lib("Montserrat", "Montserrat[wght].ttf")
DISPLAY = _lib("PlayfairDisplay", "PlayfairDisplay[wght].ttf")
HAND = _lib("PatrickHand", "PatrickHand-Regular.ttf")
RUQAA = _lib("ArefRuqaa", "ArefRuqaa-Bold.ttf")
PLEX_AR = _lib("IBMPlexSansArabic", "IBMPlexSansArabic-SemiBold.ttf")

STYLE_CHOICES = [("📘 Textbook page", "textbook"), ("🌙 Night studio", "studio"), ("📝 Exam passage", "exam"),
                 ("📒 Notebook", "notebook")]
LEVEL_CHOICES = [("None", ""), ("A1", "A1"), ("A2", "A2"), ("B1", "B1"), ("B2", "B2"), ("C1", "C1"), ("C2", "C2")]
BANDS = {"brand": (140, 14, 26), "teal": (15, 110, 116), "navy": (30, 52, 98), "maroon": (128, 34, 46), "forest": (34, 96, 62),
         "plum": (88, 54, 128), "slate": (52, 64, 78)}
BAND_CHOICES = [("Logolept red", "brand"), ("Teal", "teal"), ("Navy", "navy"), ("Maroon", "maroon"), ("Forest green", "forest"),
                ("Plum", "plum"), ("Slate", "slate")]
MARKERS = {"yellow": (255, 224, 102), "green": (178, 236, 140), "pink": (255, 176, 204), "blue": (160, 214, 255),
           "orange": (255, 198, 124)}
MARKER_CHOICES = [("Yellow", "yellow"), ("Green", "green"), ("Pink", "pink"), ("Blue", "blue"), ("Orange", "orange")]

PAPER_TOP, PAPER_BOT = (252, 251, 247), (244, 242, 235)
INK = (29, 35, 39)
FADED = (184, 189, 191)
AR_COL = (161, 54, 31)
RULE = (226, 228, 223)

SAFE_BOTTOM = 1536          # the bottom 20 % is covered by the caption / channel name
SAFE_RIGHT = 918            # the Shorts buttons sit right of this
SIZES = tuple(range(74, 35, -2))
TURN = 0.85                 # page turn (a real page curl)
FLY = 0.85                  # word flight
REVEAL = 0.6                # Arabic writes in
ENDING_LEN = 4.5
END_LOGO = 0.42             # when the logo pops onto the ending card (s after it starts)
STING = 0.9                 # the logo opening (when switched on)
LOGO = 118                  # the logo in the header, px
DEFAULT_LOGO = os.path.join(ROOT, "projects", "brand", "logolept_logo.png")
LOGO_SHAPES = [("Circle", "circle"), ("As it is", "plain")]

try:  # syllable hyphenation for justified lines (optional: without it words split only at their own hyphens)
    import pyphen
    _HYPH = pyphen.Pyphen(lang="en_US", left=3, right=3)
except Exception:
    _HYPH = None

_MARKER_ONLY = {"*", "x", "y", "yes", "1", "true", "✓", "✔", "+", "•"}
_EDGE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)
_SENT_END = re.compile(r"[.!?…][\"'”’)\]]*$")

EXAMPLE = {
    "template": "text",
    "settings": {"theme": "Night Sky", "language": "en", "fps": 30, "music": "Lo-fi Chill", "music_gain": 0.6,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": "", "intro_sound": "None", "tick_sound": "Classic",
                 "tick_gain": 1.0},
    "ending": {"intro": "Next reading:", "question": "Sleep and Memory", "cta": "Follow for a new reading every day"},
    "text": {
        "title": "Move Your Body, Lift Your Mood",
        "subtitle": "UNIT 3 · READING",
        "tag": "اقرأ واستمع",
        "level": "B1",
        "words": "\n".join([
            "Physical | 0.3 | 0.6 | Physical activity | النشاط البدني",
            "activity | 0.68 | 1.08 | Physical activity",
            "floods | 1.22 | 1.48", "the | 1.52 | 1.58", "brain | 1.64 | 1.86", "with | 1.9 | 2",
            "mood-lifting | 2.1 | 2.54 | mood-lifting | مُحسِّنة للمزاج",
            "chemicals, | 2.62 | 3.16", "and | 3.28 | 3.4", "studies | 3.46 | 3.7", "show | 3.78 | 4.019",
            "even | 4.08 | 4.24", "a | 4.28 | 4.4", "brisk | 4.44 | 4.78 | brisk | سريع / نشيط",
            "ten-minute | 4.88 | 5.28", "walk | 5.36 | 5.58", "can | 5.66 | 5.78",
            "chase | 5.84 | 6.04 | chase away | تطرد / تُبعد",
            "away | 6.08 | 6.28 | chase away",
            "stress | 6.36 | 6.66", "and | 6.72 | 6.84", "sharpen | 6.94 | 7.22", "your | 7.26 | 7.34",
            "focus. | 7.42 | 7.82 | focus | التركيز"]),
        "translation": "النشاط البدني يغمر الدماغ بمواد كيميائية تُحسّن المزاج، وتُظهر الدراسات أن مجرد مشي سريع "
                       "لعشر دقائق يمكن أن يطرد التوتر ويزيد تركيزك.",
        "reading_audio": "",
        "audio_gain": 1.0,
        "lead": 1.0,
        "style": "textbook",
        "read_style": "clear",
        "text_size": "normal",
        "brand_name": "LOGOLEPT",  # "logo" missing = the bundled Logolept logo (DEFAULT_LOGO)
        "logo_shape": "circle",
        "logo_intro": False,
        "logo_end": True,
        "ending_on": True,
        "band": "brand",
        "marker": "yellow",
    },
}


# ------------------------------------------------------------------ parsing
def _num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_words(text):
    """Words box -> [dict(w, s, e, mark, ar)] with every time filled in (estimated where missing)."""
    out = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in (line.split("|") if "|" in line else line.split("\t"))]
        # a row pasted from Excel with the index column first: 1 | Physical | 0.3 | 0.6 ...
        if len(parts) >= 4 and parts[0].isdigit() and _num(parts[1]) is None and _num(parts[2]) is not None:
            parts = parts[1:]
        if len(parts) == 1:  # a plain paragraph line: every word of it, no times
            out += [dict(w=w, s=None, e=None, mark="", ar="") for w in parts[0].split()]
            continue
        parts += [""] * (5 - len(parts))
        w = parts[0]
        if not w:
            continue
        out.append(dict(w=w, s=_num(parts[1]), e=_num(parts[2]), mark=parts[3], ar=parts[4]))
    _fill_times(out)
    return out


def _fill_times(words):
    prev_end = 0.0
    for i, w in enumerate(words):
        if w["s"] is None:
            w["s"] = prev_end + (0.08 if i else 0.0)
        w["s"] = max(w["s"], prev_end - 0.02)
        if w["e"] is None or w["e"] <= w["s"]:
            nxt = next((x["s"] for x in words[i + 1:] if x["s"] is not None), None)
            guess = w["s"] + 0.14 + 0.055 * len(w["w"])
            w["e"] = min(guess, nxt - 0.03) if nxt is not None and nxt - 0.03 > w["s"] + 0.05 else guess
        prev_end = w["e"]
        if _SENT_END.search(w["w"]) and i + 1 < len(words) and words[i + 1]["s"] is None:
            prev_end += 0.3  # estimated pause after a sentence


def _clean(txt):
    return _EDGE.sub("", str(txt or "").strip())


def _groups(words):
    """[dict(i0, i1, text, ar)] — the highlighted words / phrases in reading order."""
    out = []
    i = 0
    while i < len(words):
        mark = str(words[i].get("mark") or "").strip()
        if not mark:
            i += 1
            continue
        j = i
        if " " in mark.strip():
            while j + 1 < len(words) and str(words[j + 1].get("mark") or "").strip().lower() == mark.lower():
                j += 1
        if mark.lower() in _MARKER_ONLY:
            text = " ".join(_clean(words[k]["w"]) for k in range(i, j + 1))
        else:
            text = _clean(mark) or _clean(words[i]["w"])
        ar = next((str(words[k].get("ar") or "").strip() for k in range(i, j + 1)
                   if str(words[k].get("ar") or "").strip()), "")
        out.append(dict(i0=i, i1=j, text=text, ar=ar))
        i = j + 1
    return out


def group_keys(words):
    """[(text, arabic)] of the highlighted words / phrases (used by the Excel summary)."""
    return [(g["text"], g["ar"]) for g in _groups(words)]


def words_report(text, audio=None):
    """Short status line for the editor."""
    try:
        words = parse_words(text)
    except Exception as e:
        return f"⚠️ {e}"
    if not words:
        return "Add the paragraph: one word per line (`word | start | end | highlighted | arabic`)."
    gs = _groups(words)
    bits = [f"**{len(words)} words**", f"**{len(gs)} highlighted**",
            f"reading {words[-1]['e']:.1f} s"]
    no_ar = [g["text"] for g in gs if not g["ar"]]
    if no_ar:
        bits.append("⚠️ no Arabic for: " + ", ".join(no_ar[:5]))
    if not audio:
        bits.append("🔇 no recording yet (the words follow their times silently)")
    return " · ".join(bits)


# ------------------------------------------------------------------ drawing helpers
def _mix(a, b, k):
    return tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b))


def _font(size, weight="Regular", path=SERIF):
    return get_font(int(size), weight, path)


class _Txt:
    """One line of Latin text: RGBA image + where its baseline / left edge are inside the image."""

    def __init__(self, txt, size, col, weight="Regular", path=SERIF, track=0.0):
        f = _font(size, weight, path)
        asc, desc = f.getmetrics()
        pad = 8
        if track:
            widths = [f.getlength(c) + size * track for c in txt]
            w = int(sum(widths) - size * track) if widths else 1
        else:
            w = int(math.ceil(f.getlength(txt)))
        self.im = Image.new("RGBA", (max(1, w) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(self.im)
        if track:
            x = pad
            for c, cw in zip(txt, widths):
                d.text((x, pad + asc), c, font=f, fill=tuple(col) + (255,), anchor="ls")
                x += cw
        else:
            d.text((pad, pad + asc), txt, font=f, fill=tuple(col) + (255,), anchor="ls")
        self.pad, self.base, self.w, self.size = pad, pad + asc, w, size

    def put(self, frame, x, baseline, alpha=1.0):
        im = self.im if alpha >= 0.999 else _fade(self.im, alpha)
        _comp(frame, im, int(round(x - self.pad)), int(round(baseline - self.base)))


def _fade(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def _comp(frame, im, x, y):
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.width, x + im.width), min(frame.height, y + im.height)
    if x1 > x0 and y1 > y0:
        frame.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def _ar_img(txt, size, col=AR_COL, font=AR_FONT):
    """Arabic text (shaped, right-to-left), cropped to its ink left and right."""
    im = text_img_in(_ar_font_for(font, txt), txt, int(size), col, "Bold", shadow=False)
    box = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
    return im.crop((max(0, box[0] - 4), 0, min(im.width, box[2] + 4), im.height))


def _ar_fit(txt, size, col, font, max_w, min_size=24):
    im = _ar_img(txt, size, col, font)
    if im.width > max_w:
        im = _ar_img(txt, max(min_size, int(size * max_w / im.width)), col, font)
    return im


def _ar_wrap(txt, size, col, font, max_w):
    """Arabic paragraph -> line texts (greedy by width)."""
    lines, cur = [], ""
    for w in txt.split():
        test = (cur + " " + w).strip()
        if cur and _ar_line(test, size, col, font).width - 2 * _AR_PAD > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


# Arabic justification with kashida (tatweel ـ), as Arabic books do: a join is drawn longer instead of the spaces
# growing. A kashida goes after a letter that connects to the next one (never after ا د ذ ر ز و ة ى ء, never inside
# لا), after that letter's diacritics, and preferably at the word's last join.
TATWEEL = "\u0640"
_AR_MARKS = set(chr(c) for c in list(range(0x064B, 0x0660)) + [0x0670])
_JOIN_NEXT = set("بتثجحخسشصضطظعغفقكلمنهيئپچگکی")
_AR_LETTER = re.compile("[\u0621-\u064A\u0671-\u06D3]")


def _kashida_points(word):
    """Where a tatweel may go in a word (character positions), the last join first."""
    pts = []
    for k, ch in enumerate(word):
        if ch not in _JOIN_NEXT:
            continue
        j = k + 1
        while j < len(word) and word[j] in _AR_MARKS:
            j += 1
        if j < len(word) and _AR_LETTER.match(word[j]) and word[j] != "ء" and not (ch == "ل" and word[j] in "اأإآ"):
            pts.append(j)
    return pts[::-1]


def _has_tatweel(font):
    from ..core import _font_cmap
    cmap = _font_cmap(font)
    return cmap is None or 0x0640 in cmap


_AR_PAD = 8  # air left and right of an Arabic word / line image (marks and kashidas may reach a little past it)


def _joins_ok(font, txt):
    """Without RAQM, Arabic is drawn with ready-made joined letter shapes: does `font` have every beginning / middle /
    end shape this text needs? (A missing isolated shape is fine: the plain letter looks the same.)"""
    from ..core import HAS_RAQM, _font_cmap, _reshape
    if HAS_RAQM or not _reshape:
        return True
    cmap = _font_cmap(font)
    if cmap is None:
        return True
    import unicodedata
    for c in _reshape(txt):
        if 0xFB50 <= ord(c) <= 0xFEFF and ord(c) not in cmap and not unicodedata.decomposition(c).startswith("<isolated>"):
            return False
    return True


def _ar_font_for(font, txt):
    """`font`, or (without RAQM, when it lacks joined shapes) Amiri, else Cairo — so Arabic is always joined."""
    for f in (font, AR_FONT, DEFAULT_FONT):
        if _joins_ok(f, txt):
            return f
    return DEFAULT_FONT


def _prep_in(font, txt):
    """core._prep (Arabic shaping / direction) as it would be with `font` chosen (its missing-form fixes use it)."""
    from ..core import _prep, _state
    old = _state["font"]
    _state["font"] = font
    try:
        return _prep(txt)
    finally:
        _state["font"] = old


def _ar_line(txt, size, col, font):
    """Arabic text on a FIXED baseline: every image of the same font and size has the same height and its baseline at
    the same y (the font's ascent), so words and lines drawn separately still sit on one baseline. Shaped right to
    left by the app's engine (RAQM, or arabic-reshaper + python-bidi without it). Width = advance + _AR_PAD each side."""
    font = _ar_font_for(font, txt)
    t2, kw = _prep_in(font, txt)
    f = get_font(int(size), "Bold", font)
    asc, desc = f.getmetrics()
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(math.ceil(d0.textlength(t2, font=f, **kw)))
    py = int(size * 0.25)  # room for marks above / below the font's own ascent and descent
    im = Image.new("RGBA", (w + 2 * _AR_PAD, asc + desc + 2 * py), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((_AR_PAD, py + asc), t2, font=f, fill=tuple(col) + (255,), anchor="ls", **kw)
    return im


def _ar_justified(lines, size, col, font, width):
    """Line images exactly `width` wide (the last line: natural width), words placed right to left on one baseline.
    Slack goes into kashidas first (at most 2 per word, the longest words first, one round at a time so they spread
    over the line), the rest evenly into the spaces."""
    out = []
    adv = lambda t: _ar_line(t, size, col, font).width - 2 * _AR_PAD
    space = max(4, adv("ب ب") - 2 * adv("ب"))
    tw = max(1, adv("بـب") - adv("بب"))
    kashida = _has_tatweel(font)
    for n, line in enumerate(lines):
        words = line.split()
        if n == len(lines) - 1 or len(words) < 2:
            out.append(_ar_line(line, size, col, font))
            continue
        imgs = [_ar_line(w, size, col, font) for w in words]
        slack = width - sum(im.width - 2 * _AR_PAD for im in imgs) - space * (len(words) - 1)
        if kashida and slack > 0:
            pts = [_kashida_points(w) for w in words]
            count = [0] * len(words)
            room = slack - space * 0.5 * (len(words) - 1)  # the spaces may grow a little too
            order = sorted(range(len(words)), key=lambda k: -len(words[k]))
            changed = True
            while room >= tw and changed:
                changed = False
                for k in order:
                    if pts[k] and count[k] < 2 and room >= tw:
                        count[k] += 1
                        room -= tw
                        changed = True
            for k, c in enumerate(count):
                if c:
                    j = pts[k][0]
                    imgs[k] = _ar_line(words[k][:j] + TATWEEL * c + words[k][j:], size, col, font)
        inner = [im.width - 2 * _AR_PAD for im in imgs]
        gap = (width - sum(inner)) / (len(words) - 1)
        line_im = Image.new("RGBA", (width + 2 * _AR_PAD, imgs[0].height), (0, 0, 0, 0))
        x = float(width + _AR_PAD)
        for im, w in zip(imgs, inner):  # right to left, every word on the same baseline (same image height)
            x -= w
            _comp(line_im, im, int(round(x - _AR_PAD)), 0)
            x -= gap
        out.append(line_im)
    return out


def _marker(w, h, col, seed):
    """A felt-tip highlighter stroke: uneven edges, slanted chisel ends, streaks along the stroke (the felt runs a
    little dry in places) and more ink where the pen starts and stops."""
    rng = np.random.default_rng(seed)
    S = 2
    W2, H2 = max(2, int(w * S)), max(2, int(h * S))
    shape = Image.new("L", (W2, H2), 0)
    d = ImageDraw.Draw(shape)
    sl = h * 0.22 * S  # chisel slant
    top = [(x, rng.uniform(0, h * 0.09) * S) for x in np.linspace(sl, W2, 8)]
    bot = [(x, H2 - rng.uniform(0, h * 0.11) * S) for x in np.linspace(W2 - sl, 0, 8)]
    d.polygon(top + bot, fill=255)
    a = np.asarray(shape, np.float32) / 255.0
    rows = 0.80 + 0.20 * rng.random(H2)                               # streaks along the stroke
    rows = np.convolve(rows, np.ones(5) / 5, mode="same")[:, None]
    along = 0.93 + 0.07 * np.sin(np.linspace(0, rng.uniform(3, 7), W2) + rng.uniform(0, 6))[None, :]
    grain = 0.94 + 0.06 * rng.random((H2, W2))
    x = np.linspace(0, 1, W2)[None, :]
    ends = 1 + 0.16 * (np.exp(-x / 0.035) + np.exp(-(1 - x) / 0.035))  # pooled ink at both ends
    a = np.clip(a * rows * along * grain * ends * 0.78, 0, 1)
    arr = np.zeros((H2, W2, 4), np.uint8)
    arr[..., :3] = col
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr).resize((int(w), int(h)), Image.LANCZOS)


def _check(r, col, tick=(255, 255, 255)):
    S = 3
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 2 * r * S - 1, 2 * r * S - 1], fill=tuple(col) + (255,))
    pts = [(0.52 * r * S, 1.02 * r * S), (0.86 * r * S, 1.38 * r * S), (1.5 * r * S, 0.66 * r * S)]
    d.line(pts, fill=tuple(tick) + (255,), width=int(0.22 * r * S), joint="curve")
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def _pen_tick(r, col, width=5):
    """A hand-drawn tick (no circle)."""
    S = 3
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    pts = [(0.25 * r * S, 1.05 * r * S), (0.75 * r * S, 1.6 * r * S), (1.8 * r * S, 0.3 * r * S)]
    ImageDraw.Draw(im).line(pts, fill=tuple(col) + (255,), width=width * S, joint="curve")
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def _partial(pts, p):
    """The first fraction p (by length) of a polyline."""
    if p >= 1 or len(pts) < 2:
        return list(pts)
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    goal, out = sum(seg) * max(0.0, p), [pts[0]]
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if goal <= L:
            k = goal / L if L else 0
            out.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
            return out
        out.append(b)
        goal -= L
    return out


def _noise_bg(arr, sigma=1.6, seed=4):
    rng = np.random.default_rng(seed)
    arr = arr + rng.normal(0, sigma, (H, W, 1)).astype(np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def _vgrad(c0, c1):
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr = np.array(c0, np.float32) * (1 - y) + np.array(c1, np.float32) * y
    return np.repeat(arr, W, axis=1)


def _bezier(p0, p1, p2, p3, u):
    a = (1 - u) ** 3
    b = 3 * (1 - u) ** 2 * u
    c = 3 * (1 - u) * u ** 2
    d = u ** 3
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _shadow_box(size, box, r, blur, alpha, dy):
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([box[0], box[1] + dy, box[2], box[3] + dy], r, fill=(0, 0, 0, alpha))
    return sh.filter(ImageFilter.GaussianBlur(blur))


def _multiply(frame, im, x, y):
    """Lay a coloured RGBA image on the frame like ink on paper (multiply blend): the paper grain shows through."""
    x, y = int(x), int(y)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.width, x + im.width), min(frame.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    reg = np.asarray(frame.crop((x0, y0, x1, y1)), np.float32)
    src = np.asarray(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), np.float32)
    a = src[..., 3:4] / 255.0
    out = reg.copy()
    out[..., :3] = reg[..., :3] * (1 - a + a * src[..., :3] / 255.0)
    frame.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), (x0, y0))


def _spring(tau):
    """A damped spring after a landing: 1 at the hit, then a few quick, fading swings."""
    return math.exp(-7.0 * tau) * math.cos(17.0 * tau) if tau >= 0 else 0.0


def _ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _sparkle(r, col):
    """A four-point star with a soft glow."""
    S = 4
    n = 2 * r * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n / 2
    pts = []
    for k in range(8):
        a = math.pi / 4 * k
        rr = c * (1.0 if k % 2 == 0 else 0.22)
        pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
    d.polygon(pts, fill=tuple(col) + (255,))
    glow = im.filter(ImageFilter.GaussianBlur(n / 9))
    return Image.alpha_composite(glow, im).resize((2 * r, 2 * r), Image.LANCZOS)


class _Brand:
    """The brand row at the top of every page: [logo]  NAME / small line + level badge. put(img, x, y) with y = the
    row's anchor (the name sits just above it, the small line just below)."""

    def __init__(self, logo, name, sub, badge):
        self.logo, self.name, self.sub, self.badge = logo, name, sub, badge
        self.gap = 24
        tw = max(name.w if name else 0, (sub.w if sub else 0) + (badge.width + 20 if badge is not None else 0))
        self.w = logo.width + self.gap + tw
        self.top, self.below = -int(logo.height * 0.56), int(logo.height * 0.44)

    def put(self, img, x, y):
        _comp(img, self.logo, int(x), int(y + self.top))
        tx = x + self.logo.width + self.gap
        if self.name:
            self.name.put(img, tx, y - 4 if self.sub or self.badge is not None else y + 14)
        sx = tx
        if self.sub:
            self.sub.put(img, sx, y + 40)
            sx += self.sub.w + 20
        if self.badge is not None:
            _comp(img, self.badge, int(sx), int(y + 40 - self.badge.height * 0.78))


def logo_badge(path, size, shape="circle"):
    """The logo as shown in the video: a circle (cropped to fill it) with a white rim and a soft shadow, or the image
    as it is (fitted). None when there is no usable image."""
    if not path or not os.path.isfile(str(path)):
        return None
    try:
        src = Image.open(path).convert("RGBA")
    except Exception:
        return None
    pad = max(8, size // 10)
    out = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    S = 3
    if shape == "circle":
        n = size * S
        side = min(src.size)
        sq = src.crop(((src.width - side) // 2, (src.height - side) // 2, (src.width + side) // 2,
                       (src.height + side) // 2)).resize((n, n), Image.LANCZOS)
        disc = Image.new("RGBA", (n, n), (255, 255, 255, 255))  # a see-through logo sits on white
        disc.alpha_composite(sq)
        m = Image.new("L", (n, n), 0)
        ImageDraw.Draw(m).ellipse([0, 0, n - 1, n - 1], fill=255)
        disc.putalpha(m)
        rim = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        ImageDraw.Draw(rim).ellipse([0, 0, n - 1, n - 1], outline=(255, 255, 255, 255), width=int(n * 0.035))
        disc.alpha_composite(rim)
        im = disc.resize((size, size), Image.LANCZOS)
        out.alpha_composite(_shadow_box(out.size, (pad, pad + 3, pad + size, pad + size + 3), size // 2, pad * 0.6,
                                        90, 0))
    else:
        k = size / max(src.size)
        im = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
        sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
        sh.paste((0, 0, 0, 70), (pad + (size - im.width) // 2, pad + (size - im.height) // 2 + 4), im.getchannel("A"))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(pad * 0.5)))
    out.alpha_composite(im, (pad + (size - im.width) // 2, pad + (size - im.height) // 2))
    return out


def make_video(project, layout_only=False):
    """The video object for the project's design (`text.style`). layout_only: stop after the page layout (fast:
    how many pages and at what size, nothing drawn)."""
    style = (project.get("text", {}) or {}).get("style") or "textbook"
    cls = {"studio": StudioVideo, "exam": ExamVideo, "notebook": NotebookVideo}.get(style, TextVideo)
    return cls(project, layout_only=layout_only)


# ================================================================== the reading engine (+ the Textbook design)
class TextVideo:
    TITLE, TITLE_W = SERIF, "ExtraBold"  # the design's own title font (replaced by a font chosen in the app)
    BODY = SERIF                # paragraph font, its weights for plain / highlighted words
    W_REG, W_KEY = "Regular", "SemiBold"
    LINE = 1.66                 # line height / text size
    MARK_ON_TOP = False         # the word mark is drawn over the ink (pen) or under it (highlighter, glow)
    FINISH_EXTRA = 0.0          # extra time after the ticks for a design's last flourish
    SUP = True                  # footnote numbers after the highlighted words (= their Word Bank number)
    DROPCAP = True              # the first letter of the text set big over two lines
    TAB = True                  # the VOCABULARY index tab on the page edge (Textbook)
    DIM = 0.34                  # how much the lines not being read fade back while the voice reads
    BREATH = 0.055              # the word being spoken grows this much and settles
    WAVE_H = 15                 # half height of the waveform progress bar
    STYLE_LIGHT = True          # a light page (the logo opening writes the name in colour, not white)
    MIN_SIZE = 44               # smallest comfortable reading size on a phone (longer texts get more pages)
    GAP_MAX = 2.0               # widest justified word gap (in spaces) before a page takes a smaller size

    def __init__(self, project, layout_only=False):
        s = project.get("settings", {})
        d = project.get("text", {})
        e = project.get("ending", {})
        self.fps = int(s.get("fps", 30))
        self.words = parse_words(d.get("words", ""))
        if not self.words:
            raise ValueError("Add the paragraph: one word per line — word | start | end | highlighted | arabic.")
        self.groups = _groups(self.words)
        self.key_of = {}
        for gi, g in enumerate(self.groups):
            for i in range(g["i0"], g["i1"] + 1):
                self.key_of[i] = gi
        self.lead = max(0.2, float(d.get("lead") or 1.0))
        self.audio = d.get("reading_audio") or ""
        if self.audio and not os.path.isfile(self.audio):
            self.audio = ""
        self.audio_gain = float(d.get("audio_gain") if d.get("audio_gain") is not None else 1.0)
        self.title = str(d.get("title") or "").strip()
        self.subtitle = str(d.get("subtitle") or "").strip()
        self.tag = str(d.get("tag") or "").strip()
        self.level = str(d.get("level") or "").strip().upper()[:3]
        self.translation = " ".join(str(d.get("translation") or "").split())
        self.logo_path = d.get("logo") if d.get("logo") is not None else DEFAULT_LOGO
        self.brand_name = str(d.get("brand_name") if d.get("brand_name") is not None else "LOGOLEPT").strip()
        self.logo_shape = d.get("logo_shape") or "circle"
        self.logo_img = logo_badge(self.logo_path, LOGO, self.logo_shape)
        self.sting = STING if (d.get("logo_intro") and self.logo_img is not None) else 0.0
        self.end_logo = bool(d.get("logo_end", True)) and self.logo_img is not None
        self.lead = self.lead + self.sting  # the reading starts after the logo opening
        self._wcache, self._brk = {}, {}
        self._fly_imgs, self._misc = {}, {}

        self._style(d)
        self._apply_font(s.get("font_file"))
        # "clear": all text dark from the start, a soft marker glides behind the word being read (default);
        # "ink": the classic read-along (words start faded and ink in as they are spoken)
        self.clear = (d.get("read_style") or "clear") == "clear"
        # Text size: bigger = a higher smallest size, so the same text simply takes more pages
        self.MIN_SIZE = min(70, self.MIN_SIZE + {"large": 8, "xlarge": 16}.get(d.get("text_size") or "normal", 0))
        if self.clear:
            self.faded, self.faded_key = self.ink, self.key_ink
            self.DIM = 0.0
        self.width = self.x1 - self.x0
        self._header()
        self._paginate()
        if layout_only:
            return
        self._timeline()
        self._build_wave()
        self.bg = self._background()
        self.line_base = [0]
        for idx, z in zip(self.page_words, self.page_size):
            self.line_base.append(self.line_base[-1] + len(self._break(idx, z)))
        self.key_line = {}
        self.pages = [self._build_page(k) for k in range(len(self.page_words))]
        if self.recap:
            self.pages.append(self._build_recap())
        self.tr = self._build_translation() if self.translation else None

        ending_q = [ln.strip() for ln in str(e.get("question", "") or "").splitlines() if ln.strip()]
        self.has_ending = bool(d.get("ending_on", True)) and bool(e.get("intro") or ending_q or e.get("cta"))
        self.ending = (str(e.get("intro", "") or "").strip(), ending_q, str(e.get("cta", "") or "").strip(),
                       str(s.get("handle", "") or "").strip())
        if self.has_ending:
            self._layout_end()
        dur = self.E + (ENDING_LEN if self.has_ending else 0.5)
        if self.audio:
            try:
                last = self.lead + audio_length(self.audio) + self.shifts[-1] + 0.3
                dur = max(dur, last + (ENDING_LEN if self.has_ending else 0.5))
            except Exception:
                pass
        self.base_duration = self.dur = dur
        self.silences = []
        self.cover_time = min(self.done, self.E - 0.2)  # the cover (thumbnail) shows the full page with the logo

    # -------------------------------------------------------------- design: colours / geometry (Textbook)
    def _style(self, d):
        self.band = BANDS.get(d.get("band") or "teal", BANDS["teal"])
        self.accent = self.band
        self.marker_col = MARKERS.get(d.get("marker") or "yellow", MARKERS["yellow"])
        self.x0, self.x1 = 72, SAFE_RIGHT
        self.ink, self.key_ink = INK, INK
        self.faded = FADED
        self.faded_key = _mix(self.band, PAPER_TOP, 0.45)
        self.en_col = INK
        self.ar_col, self.ar_font = AR_COL, AR_FONT
        self.bank_label, self.bank_label_ar = "WORD BANK", "بنك الكلمات"
        self.bank_col = self.band
        self.rule_col = RULE
        self.leader_col = (196, 200, 196)
        self.flash_col = self.marker_col
        self.panel = dict(bg=(255, 255, 255), border=self.band, text=AR_COL, label=self.band, font=AR_FONT)
        self.wave_cols = ((212, 217, 213), self.band)
        self.wave_grad = (self.band, self.band)
        self.focus_col = _mix(self.band, (255, 255, 255), 0.88) + (255,)
        self.page_back = (240, 238, 230)
        self.burst_col = self.marker_col

    def _apply_font(self, value):
        """The font picked in 🎨 Style & sound (a library family name or a .ttf / .otf file) replaces the design's fonts:
        title, paragraph, flying words, word bank. If it also writes Arabic it is used for the meanings and the
        translation too; otherwise the design's Arabic font stays. No font picked = the design's own fonts."""
        if not value:
            return
        path = str(value)
        if not os.path.isfile(path):
            try:
                from ..fonts import resolve
                path = resolve(value)
            except Exception:
                return
        if not path or not os.path.isfile(path) or path == DEFAULT_FONT and str(value) != DEFAULT_FONT:
            return
        from ..core import _font_cmap
        cmap = _font_cmap(path)
        if cmap is None or ord("a") in cmap:  # it writes English
            self.BODY = self.TITLE = path
            self.TITLE_W = "Bold"
            if self.W_KEY == self.W_REG:
                self.W_KEY = "Bold"  # highlighted words stand out in a print font (Notebook's hand font had one weight)
        if cmap is None or 0x0644 in cmap:  # it writes Arabic too
            self.ar_font = path
            self.panel = dict(self.panel, font=path)

    def _background(self):
        """The page, and at the right edge the edges of the pages under it (a real book)."""
        img = _noise_bg(_vgrad(PAPER_TOP, PAPER_BOT))
        edge = W - 22
        strip = np.repeat(np.linspace(0, 1, 22, dtype=np.float32)[None, :], H, axis=0)
        desk = Image.fromarray((np.array((206, 200, 188), np.float32) * (0.82 + 0.18 * strip[..., None])
                                ).astype(np.uint8)).convert("RGBA")
        img.paste(desk, (edge, 0))
        d = ImageDraw.Draw(img)
        for k, x in enumerate(range(edge + 1, W - 3, 4)):  # the stacked page edges
            d.line([(x, 0), (x, H)], fill=(250, 248, 241, 255) if k % 2 == 0 else (214, 209, 198, 255), width=2)
        sh = Image.new("RGBA", (16, H), (0, 0, 0, 0))  # the top page's soft shadow on the stack
        sd = ImageDraw.Draw(sh)
        for x in range(16):
            sd.line([(x, 0), (x, H)], fill=(0, 0, 0, int(46 * (1 - x / 16) ** 2)))
        img.alpha_composite(sh, (edge, 0))
        return img

    def _fit_title(self, path, weight, big, small, two_lines_size):
        lines, size = [self.title], big
        if self.title:
            while size > small and _font(size, weight, path).getlength(self.title) > self.width:
                size -= 2
            if _font(size, weight, path).getlength(self.title) > self.width:
                size = two_lines_size
                lines = self._wrap_plain(self.title, size, weight, self.width, path)[:2]
        return [ln for ln in lines if ln], size

    def _badge(self, bg, fg, size=28):
        """The level pill (A1-C2)."""
        if not self.level:
            return None
        t = _Txt(self.level, size, fg, "Bold", LABEL, track=0.08)
        h = int(size * 1.6)
        im = Image.new("RGBA", (t.w + int(size * 1.3), h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, im.width - 1, h - 1], h // 2, fill=tuple(bg) + (255,))
        t.put(im, (im.width - t.w) / 2, h / 2 + size * 0.36)
        return im

    def _header(self):
        """The coloured band: small line, title (1-2 lines), level badge and the Arabic tag; sets self.band_h."""
        light = _mix(self.band, (255, 255, 255), 0.72)
        self.sub_img = _Txt(self.subtitle.upper(), 30, light, "Bold", LABEL, track=0.16) if self.subtitle else None
        lines, size = self._fit_title(self.TITLE, self.TITLE_W, 66, 48, 56)
        self.title_imgs = [_Txt(ln, size, (255, 255, 255), self.TITLE_W, self.TITLE) for ln in lines]
        self.sub_y = 182
        y = self.sub_y + (84 if (self.sub_img or self.level) else 30)
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.18)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 56
        self.badge = self._badge((255, 255, 255), self.band)
        self.tag_img = _ar_img(self.tag, 36, light, self.ar_font) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h + 34
        self.wave_y = self.bar_y + 4
        self.p_top = self.band_h + 76
        self._apply_brand((255, 255, 255), light, 26)

    def _drop_tag_if_crowded(self):
        used = (self.sub_img.w if self.sub_img else 0) + (self.badge.width + 24 if self.badge is not None else 0)
        if self.tag_img and used + self.tag_img.width + 40 > self.width:
            self.tag_img = None

    def _apply_brand(self, name_col, sub_col, sub_size):
        """With a logo: the small line becomes the brand row ([logo] NAME / small line + badge) and everything
        below moves down to make room for it."""
        if self.logo_img is None:
            return
        name = _Txt(self.brand_name.upper(), 40, name_col, "ExtraBold", LABEL, track=0.1) if self.brand_name else None
        sub = _Txt(self.subtitle.upper(), sub_size, sub_col, "Bold", LABEL, track=0.16) if self.subtitle else None
        self.sub_img = _Brand(self.logo_img, name, sub, self.badge)
        self.badge = None
        self.sub_y += 26
        bottom = self.sub_y + self.sub_img.below
        if self.title_imgs:
            cap_top = self.title_ys[0] - self.title_imgs[0].size * 0.74
            delta = max(0, int(bottom + 22 - cap_top))
        else:
            delta = max(0, int(bottom + 30 - self.band_h))
        self.title_ys = [y + delta for y in self.title_ys]
        self.band_h += delta
        self.bar_y += delta
        self.wave_y += delta
        self.p_top += delta
        self._drop_tag_if_crowded()

    def _put_sub_line(self, img, y):
        """Subtitle, level badge after it, Arabic tag on the right (all on one line at baseline y)."""
        x = self.x0
        if self.sub_img:
            self.sub_img.put(img, x, y)
            x += self.sub_img.w + 24
        if self.badge is not None:
            _comp(img, self.badge, int(x), int(y - self.badge.height * 0.78))
        if self.tag_img:
            _comp(img, self.tag_img, self.x1 - self.tag_img.width, int(y - self.tag_img.height * 0.64))

    def _band_layer(self, img):
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W - 23, self.band_h], fill=self.band + (255,))  # printed on the top page
        sh = Image.new("RGBA", (W - 22, 26), (0, 0, 0, 0))  # soft shadow under the band
        sd = ImageDraw.Draw(sh)
        for y in range(26):
            sd.line([(0, y), (W - 22, y)], fill=(0, 0, 0, int(34 * (1 - y / 26) ** 2)))
        img.alpha_composite(sh, (0, self.band_h))
        self._put_sub_line(img, self.sub_y)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        self._wave_track(img)

    def _audio_t(self, tv):
        """The recording's time at video time tv (None in the pause of a page turn)."""
        for k in range(len(self.page_words) - 1, -1, -1):
            ta = tv - self.lead - self.shifts[k]
            if ta >= self.cuts[k]:
                nxt = self.cuts[k + 1] if k + 1 < len(self.cuts) else math.inf
                return ta if ta < nxt else None
        return None

    def _build_wave(self):
        """Bar heights of the waveform under the title: the real loudness of the recording over the reading (or,
        without a recording, a voice-like shape made from the word timings)."""
        n = max(20, int(self.width // 7))
        t0, t1 = self.first_t, max(self.first_t + 0.5, self.last_t)
        times = [t0 + (t1 - t0) * (k + 0.5) / n for k in range(n)]
        half = (t1 - t0) / n / 2
        amps = None
        if self.audio:
            try:
                a = np.abs(load_audio(self.audio)).mean(axis=1)
                vals = []
                for tv in times:
                    ta = self._audio_t(tv)
                    if ta is None:
                        vals.append(0.0)
                        continue
                    i0, i1 = int(max(0, ta - half) * SR), int((ta + half) * SR)
                    seg = a[i0:max(i1, i0 + 1)]
                    vals.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
                amps = np.array(vals)
            except Exception:
                amps = None
        if amps is None or amps.max() <= 0:
            rng = np.random.default_rng(21)
            vals = []
            for tv in times:
                on = any(self.vs[i] - 0.03 <= tv <= self.ve[i] + 0.03 for i in range(len(self.words)))
                vals.append((0.55 + 0.45 * rng.random()) if on else 0.06 + 0.06 * rng.random())
            amps = np.convolve(np.array(vals), [0.25, 0.5, 0.25], mode="same")
        ref = np.percentile(amps, 92) or 1.0
        self.wave = np.clip(np.sqrt(np.clip(amps / ref, 0, 1)), 0.1, 1.0)

    def _wave_img(self, fill):
        """Rounded bars; fill = a colour, or 'grad' (blue -> gold)."""
        hh = self.WAVE_H
        im = Image.new("RGBA", (self.width + 4, 2 * hh + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        n = len(self.wave)
        step = self.width / n
        for k, a in enumerate(self.wave):
            x = 2 + k * step
            h = max(2.5, a * hh)
            d.rounded_rectangle([x, hh + 2 - h, x + 4, hh + 2 + h], 2, fill=(255, 255, 255, 255))
        if fill == "grad":
            g = np.linspace(0, 1, im.width)[None, :, None]
            arr = np.array(self.wave_grad[0], np.float32) * (1 - g) + np.array(self.wave_grad[1], np.float32) * g
            col = Image.fromarray(np.repeat(arr, im.height, axis=0).astype(np.uint8)).convert("RGBA")
        else:
            col = Image.new("RGBA", im.size, tuple(fill[:3]) + (255,))
        a = im.getchannel("A")
        if fill != "grad" and len(fill) == 4:
            a = a.point(lambda v: v * fill[3] // 255)
        col.putalpha(a)
        return col

    def _wave_track(self, img):
        """The waiting (unplayed) waveform, drawn on the page."""
        if "wave_track" not in self._misc:
            self._misc["wave_track"] = self._wave_img(self.wave_cols[0])
            self._misc["wave_fill"] = self._wave_img(self.wave_cols[1])
        _comp(img, self._misc["wave_track"], self.x0 - 2, self.wave_y - self.WAVE_H - 2)

    def _draw_progress(self, frame, p):
        """The played part of the waveform, with a playhead."""
        if p <= 0 or "wave_fill" not in self._misc:
            return
        im = self._misc["wave_fill"]
        w = max(1, int(2 + self.width * p))
        _comp(frame, im.crop((0, 0, min(im.width, w), im.height)), self.x0 - 2, self.wave_y - self.WAVE_H - 2)
        if p < 1:
            col = self.wave_grad[1] if self.wave_cols[1] == "grad" else self.wave_cols[1][:3]
            x = self.x0 + self.width * p
            d = ImageDraw.Draw(frame)
            d.ellipse([x - 7, self.wave_y - 7, x + 7, self.wave_y + 7], fill=tuple(col) + (255,))
            d.ellipse([x - 3, self.wave_y - 3, x + 3, self.wave_y + 3], fill=(255, 255, 255, 255))

    def _decor(self, dd, x, yb, w, size):
        """Faded layer: a dotted underline under the words that will fly."""
        for dx in range(0, int(w), 9):
            dd.ellipse([x + dx, yb + size * 0.2, x + dx + 3.4, yb + size * 0.2 + 3.4], fill=self.band + (255,))

    def _page_decor(self, base, k, baselines, lh, size):
        pass

    def _make_mark(self, sp):
        h = int(sp["size"] * 0.86)
        return (int(sp["x"] - 7), int(sp["yb"] - sp["size"] * 0.66),
                _marker(sp["x2"] - sp["x"] + 14, h, self.marker_col, sp["i0"]))

    def _draw_mark(self, frame, mk, q):
        """The highlighter swipes along the word, its ink multiplied into the paper."""
        mx, my, im = mk
        w = max(1, int(im.width * ease_io(q)))
        _multiply(frame, im.crop((0, 0, w, im.height)), mx, my)

    # -------------------------------------------------------------- line breaking + pages (shared)
    @staticmethod
    def _wrap_plain(txt, size, weight, width, path=SERIF):
        f = _font(size, weight, path)
        lines, cur = [], ""
        for w in txt.split():
            test = (cur + " " + w).strip()
            if cur and f.getlength(test) > width:
                lines.append(cur)
                cur = w
            else:
                cur = test
        return lines + ([cur] if cur else [])

    def _units(self):
        """Sentences as lists of word indices (a highlighted phrase is never split between two sentences)."""
        sents, cur = [], []
        for i, w in enumerate(self.words):
            cur.append(i)
            inside = i in self.key_of and self.groups[self.key_of[i]]["i1"] > i
            if _SENT_END.search(w["w"]) and not inside:
                sents.append(cur)
                cur = []
        return sents + ([cur] if cur else [])

    def _atoms(self, idx):
        """Word indices grouped so a highlighted phrase stays together."""
        out, i = [], 0
        while i < len(idx):
            k = idx[i]
            if k in self.key_of:
                g = self.groups[self.key_of[k]]
                run = [x for x in idx[i:] if g["i0"] <= x <= g["i1"]]
                out.append(run)
                i += len(run)
            else:
                out.append([k])
                i += 1
        return out

    def _wweight(self, i):
        return self.W_KEY if i in self.key_of else self.W_REG

    def _ww(self, i, size):
        return self._pw(i, 0, len(self.words[i]["w"]), False, size)

    def _splits(self, i):
        """Where word i may be broken at a line end: [(char offset, add a hyphen?)] — after its own hyphens, and
        between syllables (pyphen) for plain words of 7+ letters."""
        if i in self._wcache.get("splits", {}):
            return self._wcache["splits"][i]
        w = self.words[i]["w"]
        out = [(k + 1, False) for k, c in enumerate(w) if c == "-" and 2 <= k + 1 <= len(w) - 3]
        core = _clean(w)
        if _HYPH is not None and "-" not in w and core.isalpha() and len(core) >= 7:
            lead = w.find(core)
            out += [(lead + k, True) for k in _HYPH.positions(core)]
        self._wcache.setdefault("splits", {})[i] = out
        return out

    def _sup_txt(self, i, b):
        """The footnote number after the last piece of a highlighted word / phrase (Textbook)."""
        if not self.SUP or i not in self.key_of:
            return None
        g = self.groups[self.key_of[i]]
        if i != g["i1"] or b < len(self.words[i]["w"]):
            return None
        return str(self.key_of[i] + 1)

    def _sup_font(self, size):
        return _font(max(16, int(size * 0.46)), "Bold", LABEL)

    def _pw(self, i, a, b, hyph, size):
        """Width of the piece w[a:b] (+ '-') of word i (+ its footnote number)."""
        k = (i, a, b, hyph, size)
        if k not in self._wcache:
            w = self.words[i]["w"]
            width = _font(size, self._wweight(i), self.BODY).getlength(w[a:b] + ("-" if hyph else ""))
            sup = self._sup_txt(i, b)
            if sup:
                width += 3 + self._sup_font(size).getlength(sup)
            self._wcache[k] = width
        return self._wcache[k]

    def _dropcap(self, idx, size):
        """The big first letter (Textbook, first page): letter, size, indent of the first two lines."""
        if not self.DROPCAP or not idx or idx[0] != 0:
            return None
        w = self.words[0]["w"]
        if len(w) < 2 or not w[0].isalpha():
            return None
        key = ("dc", size)
        if key not in self._wcache:
            lh = int(size * self.LINE)
            cap_h = -_font(size, self.W_REG, self.BODY).getbbox("H", anchor="ls")[1]
            ref = 200
            ch = -_font(ref, "Bold", self.BODY).getbbox(w[0], anchor="ls")[1]
            dsz = max(size + 2, int(ref * (lh + cap_h) / max(1, ch)))  # caps top of line 1 -> baseline of line 2
            bb = _font(dsz, "Bold", self.BODY).getbbox(w[0], anchor="ls")
            self._wcache[key] = dict(letter=w[0], size=dsz, left=bb[0], top=bb[1],
                                     indent=int(bb[2] - bb[0] + size * 0.32))
        return self._wcache[key]

    def _line_w(self, idx, size, li):
        dc = self._dropcap(idx, size)
        return self.width - (dc["indent"] if dc and li < 2 else 0)

    def _break(self, idx, size):
        """Lines of word pieces (i, a, b, hyphen?) with the fewest lines and then the most even right edge (sum of
        squared extra space per gap), like book typesetting. A word may be split at a line end (hyphenation, which
        costs a little, so whole words are preferred); the last line may be short but not a lone short word. With a
        drop cap the first two lines are shorter (the line count is part of the search)."""
        key = (tuple(idx), size)
        if key in self._brk:
            return self._brk[key]
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        n = len(idx)
        dc = self._dropcap(idx, size)
        short = [self.width - dc["indent"]] * 2 if dc else []
        nl = len(short) + 1  # line-number states: 0, 1, 2+ (only the first lines differ)
        pts = []  # breakpoints: (word position, char offset, hyphen) ; offset 0 = before the word
        for p, i in enumerate(idx):
            first = 1 if (dc and p == 0) else 0
            pts.append((p, first, False))
            pts += [(p, c, h) for c, h in self._splits(i) if c > first]
        pts.append((n, 0, False))
        best = [[math.inf] * nl for _ in pts]
        prev = [[None] * nl for _ in pts]
        best[0][0] = 0.0
        for bj in range(1, len(pts)):
            pj, cj, hj = pts[bj]
            last = bj == len(pts) - 1
            for bi in range(bj - 1, -1, -1):
                pi, ci, _ = pts[bi]
                if pi == pj:
                    continue
                lw = self._pw(idx[pi], ci, len(self.words[idx[pi]]["w"]), False, size)
                for p in range(pi + 1, min(pj, n)):
                    lw += sp + self._ww(idx[p], size)
                if cj and pj < n:
                    lw += sp + self._pw(idx[pj], 0, cj, hj, size)
                count = (pj - pi) + (1 if cj else 0)
                if lw > self.width and count > 1:
                    break
                for L in range(nl):
                    if best[bi][L] == math.inf:
                        continue
                    width = short[L] if L < len(short) else self.width
                    if lw > width and count > 1:
                        continue
                    if last:
                        bad = 0.0 if (count > 1 or lw > width * 0.35 or n == 1) else 4000.0
                    elif count == 1:
                        bad = 30000.0
                    else:  # extra space per gap, in spaces, squared (TeX-like): even lines, no rivers
                        r = max(0.0, width - lw) / (count - 1) / sp
                        bad = 100.0 * r * r + (260.0 if cj else 0.0)  # a broken word costs a little
                    c = best[bi][L] + bad + 100000.0
                    L2 = min(L + 1, nl - 1)
                    if c < best[bj][L2]:
                        best[bj][L2], prev[bj][L2] = c, (bi, L)
        bj = len(pts) - 1
        L = min(range(nl), key=lambda x: best[bj][x])
        lines = []
        while bj > 0:
            bi, Lp = prev[bj][L]
            (pi, ci, _), (pj, cj, hj) = pts[bi], pts[bj]
            line = [(idx[pi], ci, len(self.words[idx[pi]]["w"]), False)]
            line += [(idx[p], 0, len(self.words[idx[p]]["w"]), False) for p in range(pi + 1, min(pj, n))]
            if cj and pj < n:
                line.append((idx[pj], 0, cj, hj))
            lines.append(line)
            bj, L = bi, Lp
        self._brk[key] = lines[::-1]
        return self._brk[key]

    def _row_h(self, n, size=None):
        cap = 108 if n <= 4 else 96 if n <= 6 else 80 if n <= 8 else 64
        return max(58, min(cap, int((size or self.size) * 1.6)))

    def _bank_h(self, n, size=None):
        return 0 if n == 0 else 64 + 82 + n * self._row_h(n, size)  # gap + header + rows

    def _need(self, idx, size):
        return len(self._break(idx, size)) * int(size * self.LINE) + self._bank_h(len(self._keys_in(idx)), size)

    def _keys_in(self, idx):
        s = set(idx)
        return [gi for gi, g in enumerate(self.groups) if g["i0"] in s]

    def _fits(self, idx, size):
        return self._need(idx, size) <= SAFE_BOTTOM - self.p_top and len(self._keys_in(idx)) <= 10

    _CLAUSE_END = re.compile(r"[,;:\u2014\u2013\u060C\u061B][\"'\u201d\u2019)\]]*$")

    def _clauses(self, sent):
        """A sentence cut into clauses (after , ; : or a dash), each a list of word indices; phrases stay whole."""
        out, cur = [], []
        for atom in self._atoms(sent):
            cur += atom
            if self._CLAUSE_END.search(self.words[atom[-1]]["w"]):
                out.append(cur)
                cur = []
        return out + ([cur] if cur else [])

    def _pack(self, size):
        """Pages at this size, filled sentence by sentence, + how rough their breaks are: 0 = every page ends at a
        sentence end; a sentence longer than a page is cut at a clause end (+1 each) and only when a clause alone is
        too long, between words (+4 each). The recording is cut where the page breaks, so a clean break also
        means the voice waits for the page turn in a natural pause."""
        pages, cur, rough = [], [], 0

        def close():
            nonlocal cur
            if cur:
                pages.append(cur)
                cur = []

        for sent in self._units():
            if self._fits(cur + sent, size):
                cur = cur + sent
                continue
            close()
            if self._fits(sent, size):
                cur = list(sent)
                continue
            for clause in self._clauses(sent):  # a sentence longer than a page
                if self._fits(cur + clause, size):
                    cur = cur + clause
                    continue
                if cur:
                    close()
                    rough += 1
                if self._fits(clause, size):
                    cur = list(clause)
                    continue
                for atom in self._atoms(clause):  # a clause longer than a page: between words, last resort
                    if self._fits(cur + atom, size):
                        cur = cur + atom
                    else:
                        if cur:
                            close()
                            rough += 4
                        cur = list(atom)
        close()
        return pages, rough

    def _paginate(self):
        best = None  # cleanest page breaks first, then fewest pages, then the biggest text
        for size in [z for z in SIZES if z >= self.MIN_SIZE] or [SIZES[-1]]:
            pages, rough = self._pack(size)
            if best is None or (rough, len(pages)) < best[0]:
                best = ((rough, len(pages)), size, pages)
        _, self.size, self.page_words = best
        # each page then takes the biggest size that fits it (at most 15 % bigger, so the pages still match) and
        # whose justified lines keep tight word gaps (a book page, not rivers of white)
        self.page_size = [self._common_size(self.page_words)] * len(self.page_words)  # one size, like a book
        self.gsize = {}
        for idx, z in zip(self.page_words, self.page_size):
            for gi in self._keys_in(idx):
                self.gsize[gi] = z
        avail = SAFE_BOTTOM - self.p_top  # the text sits under the waveform; spare room stays at the bottom
        self.page_off = [min(24, max(0, (avail - self._need(idx, z)) // 8))
                         for idx, z in zip(self.page_words, self.page_size)]
        self.recap = len(self.page_words) > 1 and len(self.groups) > 0

    TRACK_MAX = 0.035           # letter-spacing a justified line may add, x text size

    def _justify(self, line, size, last, width=None):
        """(gap, tracking) of a line: slack goes first into a little letter-spacing (at most TRACK_MAX of the
        size, at most half the slack), the rest into the word gaps."""
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        if last or len(line) < 2:
            return sp, 0.0
        widths = sum(self._pw(*pc, size) for pc in line)
        slack = max(0.0, (width or self.width) - widths - sp * (len(line) - 1))
        chars = sum(max(0, b - a + (1 if h else 0) - 1) for _, a, b, h in line)
        track = min(self.TRACK_MAX * size, slack * 0.5 / chars) if chars else 0.0
        return sp + (slack - track * chars) / (len(line) - 1), track

    def _gap_ratio(self, idx, size):
        """The widest justified word gap of a page, in spaces."""
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        lines = self._break(idx, size)
        return max([1.0] + [self._justify(ln, size, False, self._line_w(idx, size, li))[0] / sp
                            for li, ln in enumerate(lines[:-1]) if len(ln) > 1])

    def _common_size(self, pages):
        """One text size for every page: the biggest that fits them all (at most 15 % over the base size), traded
        against the widest justified word gap on any of them (each space over GAP_MAX costs 5 px of size)."""
        fit = [z for z in SIZES if z <= self.size * 1.15 and all(self._fits(idx, z) for idx in pages)] or [self.size]
        floor = max(self.MIN_SIZE - 4, fit[0] * 0.8)
        return max((z for z in fit if z >= floor),
                   key=lambda z: z - 5 * max(0.0, max(self._gap_ratio(idx, z) for idx in pages) - self.GAP_MAX),
                   default=fit[0])

    def _page_size(self, idx):
        sizes = [z for z in SIZES if z <= self.size * 1.15 and self._fits(idx, z)] or [self.size]
        floor = max(self.MIN_SIZE - 4, sizes[0] * 0.8)
        # bigger text wins, unless its justified word gaps get wide (each space over GAP_MAX costs 5 px of size)
        return max((z for z in sizes if z >= floor),
                   key=lambda z: z - 5 * max(0.0, self._gap_ratio(idx, z) - self.GAP_MAX), default=sizes[0])

    # -------------------------------------------------------------- timing (shared)
    def _timeline(self):
        """Video times of every word / flight / page turn. A page turn waits for the last flight of the page before;
        the recording is cut between the pages and the later part starts later (self.shifts)."""
        self.shifts, self.turns, self.cuts = [], [0.0], [0.0]
        self.vs, self.ve = [0.0] * len(self.words), [0.0] * len(self.words)
        self.fly0 = [0.0] * len(self.groups)
        shift, prev_end = 0.0, None
        for k, idx in enumerate(self.page_words):
            if k:
                first = self.lead + self.words[idx[0]]["s"] + shift
                turn = prev_end + 0.35
                shift += max(0.0, turn + TURN + 0.3 - first)
                self.turns.append(turn)
                last_prev = self.words[self.page_words[k - 1][-1]]["e"]
                self.cuts.append((last_prev + self.words[idx[0]]["s"]) / 2)
            self.shifts.append(shift)
            for i in idx:
                self.vs[i] = self.lead + self.words[i]["s"] + shift
                self.ve[i] = self.lead + self.words[i]["e"] + shift
            end = self.ve[idx[-1]] + 0.4
            for gi in self._keys_in(idx):
                g = self.groups[gi]
                self.fly0[gi] = self.vs[g["i1"]] + 0.06  # takes off as the word (a phrase: its last word) is spoken
                end = max(end, self.fly0[gi] + FLY + 0.12 + REVEAL)
            prev_end = end
        self.reading_end = prev_end
        n = len(self.groups)
        if self.recap:
            self.recap_t = self.reading_end + 0.5
            self.turns.append(self.recap_t)
            rows_in = self.recap_t + TURN
            self.recap_row = [rows_in + 0.09 * j for j in range(n)]
            c0 = rows_in + 0.09 * n + REVEAL + 0.3
        else:
            c0 = self.reading_end + 0.3
        self.checks = [c0 + 0.2 * j for j in range(n)]
        self.finish_t = (self.checks[-1] + 0.35) if n else self.reading_end + 0.2
        self.done = self.finish_t + (self.FINISH_EXTRA if n else 0.0) + (0.05 if n else 0.0)
        self.first_t = self.vs[0]
        self.last_t = self.ve[-1]
        if self.translation:
            self.tr0 = self.done + 0.5
            self.tr1 = self.tr0 + max(4.0, min(11.0, 1.8 + 0.42 * len(self.translation.split())))
            self.E = self.tr1 + 0.6
        else:
            self.tr0 = self.tr1 = None
            self.E = self.done + 1.8

    # -------------------------------------------------------------- pre-rendered pages (shared)
    def _build_page(self, k):
        """A page = the still parts (background, header, word bank) + the paragraph as two layers: faded text and
        ink (the ink is revealed word by word as it is read). Also: word pieces, marks and line positions."""
        idx = self.page_words[k]
        size = self.page_size[k]
        lh = int(size * self.LINE)
        base = self.bg.copy()
        self._band_layer(base)
        faded = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd, di = ImageDraw.Draw(faded), ImageDraw.Draw(ink)
        lines = self._break(idx, size)
        top = self.p_top + self.page_off[k]
        dc = self._dropcap(idx, size)
        boxes, pieces, spans, baselines, line_info = {}, [], [], [], []
        sup_f = self._sup_font(size)
        for li, line in enumerate(lines):
            lw = self._line_w(idx, size, li)
            gap, track = self._justify(line, size, li == len(lines) - 1, lw)  # justified: every line but the last
            widths = [self._pw(i, a, b, h, size) + track * max(0, b - a + (1 if h else 0) - 1) for i, a, b, h in line]
            x = float(self.x1 - lw)
            yb = top + li * lh + int(size * 1.05)
            baselines.append(yb)
            first_piece = len(pieces)
            for (i, a, b, hyph), w in zip(line, widths):
                f = _font(size, self._wweight(i), self.BODY)
                asc, desc = f.getmetrics()
                key = i in self.key_of
                word = self.words[i]["w"]
                txt = word[a:b] + ("-" if hyph else "")
                fcol = (self.faded_key if key else self.faded) + (255,)
                icol = (self.key_ink if key else self.ink) + (255,)
                if track > 0.3:  # letter-spaced: each letter where the font puts it (kerning kept) + the tracking
                    for n_, ch in enumerate(txt):
                        cx = x + f.getlength(txt[:n_]) + track * n_
                        dd.text((cx, yb), ch, font=f, fill=fcol, anchor="ls")
                        di.text((cx, yb), ch, font=f, fill=icol, anchor="ls")
                else:
                    dd.text((x, yb), txt, font=f, fill=fcol, anchor="ls")
                    di.text((x, yb), txt, font=f, fill=icol, anchor="ls")
                sup = self._sup_txt(i, b)
                if sup:  # footnote number = the word's Word Bank number
                    sx = x + w - sup_f.getlength(sup)
                    dd.text((sx, yb - size * 0.42), sup, font=sup_f, fill=self.faded_key + (255,), anchor="ls")
                    di.text((sx, yb - size * 0.42), sup, font=sup_f, fill=self.accent + (255,), anchor="ls")
                box = (int(x) - 2, int(yb - asc - 4), int(math.ceil(x + w)) + 2, int(yb + desc + 4))
                boxes.setdefault(i, box)  # the flight starts from the word's first piece
                f0, f1 = a / len(word), (b / len(word) if b < len(word) else 1.0)
                pieces.append(dict(i=i, box=box, f0=f0, f1=f1, yb=yb))
                if key:
                    tw = w - (3 + sup_f.getlength(sup) if sup else 0)
                    self._decor(dd, x, yb, tw, size)
                    gi = self.key_of[i]
                    self.key_line.setdefault(gi, self.line_base[k] + li + 1)
                    if spans and spans[-1]["gi"] == gi and spans[-1]["li"] == li:
                        spans[-1].update(i1=i, f1=f1, x2=x + tw)  # a phrase on one line = one mark
                    else:
                        spans.append(dict(gi=gi, li=li, i0=i, i1=i, f0=f0, f1=f1, x=x, x2=x + tw, yb=yb, size=size))
                x += w + gap
            fp, lp = pieces[first_piece], pieces[-1]
            line_info.append(dict(yb=yb, y=yb - size * 0.33, t0=self._wt(fp["i"], fp["f0"]),
                                  t1=self._wt(lp["i"], lp["f1"])))
        if dc:  # the drop cap: inks with the first letters of the first word
            f = _font(dc["size"], "Bold", self.BODY)
            yb = baselines[1] if len(baselines) > 1 else baselines[0]
            x = self.x0 - dc["left"]
            dd.text((x, yb), dc["letter"], font=f, fill=self.faded_key + (255,), anchor="ls")
            di.text((x, yb), dc["letter"], font=f, fill=self.accent + (255,), anchor="ls")
            bb = f.getbbox(dc["letter"], anchor="ls")
            box = (int(x + bb[0]) - 4, int(yb + bb[1]) - 4, int(x + bb[2]) + 4, int(yb + bb[3]) + 4)
            pieces.insert(0, dict(i=0, box=box, f0=0.0, f1=1.0 / len(self.words[0]["w"]), dc=True))
        for sp_ in spans:
            sp_["mk"] = self._make_mark(sp_)
        self._page_decor(base, k, baselines, lh, size)
        y0 = min([top] + [p["box"][1] for p in pieces])
        para_box = (self.x0 - 16, int(y0) - 6, self.x1 + 16, top + len(lines) * lh + 12)
        keys = self._keys_in(idx)
        slots = self._bank_rows(base, keys, para_box[3] + 52, size=size) if keys else []
        self._page_extras(base, slots)
        ink_c = ink.crop(para_box)
        return dict(kind="text", k=k, idx=idx, base=base, faded=faded.crop(para_box), clean=base.crop(para_box),
                    ink_rgb=ink_c.convert("RGB"), ink_a=ink_c.getchannel("A"), box=para_box, boxes=boxes,
                    pieces=pieces, spans=spans, slots=slots, keys=keys, size=size, lines=line_info, lh=lh)

    def _page_extras(self, base, slots):
        """A design's touches that depend on where the word bank is (Textbook: a VOCABULARY index tab on the page
        edge, level with the Word Bank)."""
        if not slots or not self.TAB:
            return
        top = slots[0]["y"] - 82
        bottom = min(slots[-1]["y"] + slots[-1]["h"], top + 420)
        h = int(bottom - top)
        if h < 150:
            return
        lab = _Txt("VOCABULARY", 20, (255, 255, 255), "Bold", LABEL, track=0.22)
        tab = Image.new("RGBA", (h, 44), (0, 0, 0, 0))
        ImageDraw.Draw(tab).rounded_rectangle([0, 0, h - 1, 43 + 14], 14, fill=self.band + (255,))
        lab.put(tab, (h - lab.w) / 2, 22 + 7)
        tab = tab.rotate(90, expand=True)  # reads bottom to top, along the page edge
        base.alpha_composite(_shadow_box(base.size, (0, top, 44, top + h), 10, 8, 60, 3))
        base.alpha_composite(tab, (0, int(top)))

    def _build_recap(self):
        base = self.bg.copy()
        self._band_layer(base)
        keys = list(range(len(self.groups)))
        n = len(keys)
        slots = self._bank_rows(base, keys, self.p_top + 10, avail=SAFE_BOTTOM - self.p_top - 10,
                                label=f"{self.bank_label} · {n}")
        self._page_extras(base, slots)
        return dict(kind="recap", k=len(self.page_words), base=base, slots=slots, keys=keys, size=self.size)

    # -------------------------------------------------------------- word bank (Textbook: ruled rows)
    def _bank_header(self, img, top, label, ls):
        ar = _ar_img(self.bank_label_ar, int(ls * 1.35), self.bank_col, self.ar_font)
        lab = _Txt(label, ls, self.bank_col, "Bold", LABEL, track=0.18)
        while ls > 22 and lab.w + ar.width + 36 > self.width:  # a long label: smaller, so it never meets the Arabic
            ls -= 2
            lab = _Txt(label, ls, self.bank_col, "Bold", LABEL, track=0.18)
        lab.put(img, self.x0, top + 52)
        if lab.w + ar.width + 36 <= self.width:
            _comp(img, ar, self.x1 - ar.width, top + 52 - int(ar.height * 0.64))

    def _bank_rows(self, img, keys, top, size=None, avail=None, label=None):
        """Word bank header + empty numbered rows; returns the slot geometry of each key."""
        d = ImageDraw.Draw(img)
        n = len(keys)
        row_h = max(58, min(108, (avail - 82) // max(1, n))) if avail else self._row_h(n, size)
        d.rectangle([self.x0, top, self.x1, top + 4], fill=self.bank_col + (255,))
        self._bank_header(img, top, label or self.bank_label, max(26, min(34, int(row_h * 0.34))))
        en_size = int(min(48, row_h * 0.6))
        slots = []
        y = top + 82
        for j, gi in enumerate(keys):
            g = self.groups[gi]
            base = y + int(row_h * 0.66)
            num = _Txt(str(gi + 1) if self.SUP else str(j + 1), max(26, int(en_size * 0.6)), self.bank_col, "Bold",
                       LABEL)  # Textbook: the same number as the footnote in the text
            num.put(img, self.x0, base)
            d.line([(self.x0, y + row_h - 1), (self.x1, y + row_h - 1)], fill=self.rule_col + (255,), width=2)
            en = _Txt(g["text"], en_size, self.en_col, self.W_KEY, self.BODY)
            en_x = self.x0 + int(en_size * 1.15)
            ref = None
            if self.show_line_ref() and gi in self.key_line:
                ref = _Txt(f"(line {self.key_line[gi]})", max(20, int(en_size * 0.5)), (150, 150, 150), "Medium", LABEL)
            used = en_x - self.x0 + en.w + (ref.w + 14 if ref else 0) + 60
            ar_im = _ar_fit(g["ar"], en_size + 6, self.ar_col, self.ar_font, self.width - used) if g["ar"] else None
            slots.append(dict(gi=gi, num_x=self.x0 + 15, y=y, h=row_h, base=base, en=en, en_x=en_x, en_size=en_size,
                              ref=ref, ar=ar_im, ar_x=self.x1 - (ar_im.width if ar_im is not None else 0),
                              ar_y=base - int(ar_im.height * 0.64) if ar_im is not None else 0))
            y += row_h
        return slots

    def show_line_ref(self):
        return False

    def _draw_slot(self, frame, s, t, t_land, recap):
        fl = 1 - prog(t, t_land, t_land + 0.7)
        if fl > 0 and not recap:  # a soft flash of the row when the word lands
            ov = Image.new("RGBA", (self.width + 24, s["h"] - 6), self.flash_col + (int(110 * fl),))
            _comp(frame, ov, self.x0 - 12, s["y"] + 2)
        self._put_en(frame, s, t, t_land, recap)
        x_after = s["en_x"] + s["en"].w + 14
        if s.get("ref") is not None:
            s["ref"].put(frame, x_after, s["base"], prog(t, t_land + 0.2, t_land + 0.5))
            x_after += s["ref"].w + 4
        q = ease_io(prog(t, t_land + 0.12, t_land + 0.12 + REVEAL))
        if s["ar"] is not None and q > 0:
            lead_x0, lead_x1 = x_after + 4, s["ar_x"] - 14
            d = ImageDraw.Draw(frame)
            for x in range(int(lead_x0), int(lead_x0 + (lead_x1 - lead_x0) * q), 12):
                d.ellipse([x, s["base"] - 3, x + 3, s["base"]], fill=self.leader_col + (255,))
            self._put_ar(frame, s["ar"], s["ar_x"], s["ar_y"], q)
        self._draw_check(frame, s, t)

    def _put_en(self, frame, s, t, t_land, recap):
        """The word in its slot; on landing it squashes and springs back (anchored on its baseline)."""
        if recap:
            s["en"].put(frame, s["en_x"], s["base"], prog(t, t_land, t_land + 0.25))
            return
        d = _spring(t - t_land) if t - t_land < 0.9 else 0.0
        if abs(d) < 0.01:
            s["en"].put(frame, s["en_x"], s["base"])
            return
        sx, sy = 1 + 0.16 * d, 1 - 0.14 * d
        im = s["en"].im
        im = im.resize((max(1, int(im.width * sx)), max(1, int(im.height * sy))), Image.BILINEAR)
        cx = s["en_x"] + s["en"].w / 2
        _comp(frame, im, int(cx - im.width / 2), int(s["base"] - s["en"].base * sy))

    @staticmethod
    def _put_ar(frame, ar, x, y, q):
        """The Arabic writes in from the right."""
        w = max(1, int(ar.width * q))
        _comp(frame, ar.crop((ar.width - w, 0, ar.width, ar.height)), x + ar.width - w, y)

    def _check_at(self, gi):
        return self.checks[gi] if gi < len(self.checks) else None

    def _draw_check(self, frame, s, t):
        c = self._check_at(s["gi"])
        if c is None or t < c:
            return
        sc = ease_out_back(prog(t, c, c + 0.3))
        if sc > 0.02:
            rad = max(16, int(s["en_size"] * 0.42))
            key = ("check", rad)
            if key not in self._misc:
                self._misc[key] = _check(rad, self.bank_col)
            r = self._misc[key]
            im = r.resize((max(1, int(r.width * sc)), max(1, int(r.height * sc))), Image.LANCZOS)
            _comp(frame, im, int(s["num_x"] - im.width / 2), int(s["base"] - s["en_size"] * 0.34 - im.height / 2))

    def _draw_final(self, frame, pg, t):
        pass

    # -------------------------------------------------------------- the flying word
    def _fly_back(self, t, z, S):
        """Behind the flying text (same size as t.im): Textbook = the highlighter pill + a shadow."""
        bx = (t.pad - 10 * S, t.base - int(z * 0.86 * S), t.pad + t.w + 10 * S, t.base + int(z * 0.3 * S))
        sh = _shadow_box(t.im.size, bx, 10 * S, 14 * S, 90, 14 * S)
        pill = Image.new("RGBA", t.im.size, (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle(bx, 8 * S, fill=self.marker_col + (255,))
        return Image.alpha_composite(sh, pill)

    def _fly(self, gi):
        if gi not in self._fly_imgs:
            g = self.groups[gi]
            S = 2
            z = self.gsize[gi]
            pad = 40 * S
            # the words as the text writes them (the Word Bank may show a dictionary form: go by the board)
            said = " ".join(_clean(self.words[k]["w"]) for k in range(g["i0"], g["i1"] + 1))
            t = _Txt(said, z * S, self.en_col, self.W_KEY, self.BODY)
            t.pad += pad  # room around the text for the shadow / glow
            big = Image.new("RGBA", (t.im.width + 2 * pad, t.im.height + 2 * pad), (0, 0, 0, 0))
            big.alpha_composite(t.im, (pad, pad))
            t.im, t.base = big, t.base + pad
            back = self._fly_back(t, z, S)
            self._fly_imgs[gi] = (back, t.im, (t.pad, t.base), S)
        return self._fly_imgs[gi]

    def _flight_layer(self, pg, gi, u, ghost=False):
        back, txt, (ax, ay), S = self._fly(gi)
        g = self.groups[gi]
        x0, y0, x1, y1 = pg["boxes"][g["i0"]]
        start = (x0 + 2, y1 - 4 - _font(self.gsize[gi], self.W_KEY, self.BODY).getmetrics()[1])  # baseline-left
        s = self._slot_of(pg, gi)
        end = (s["en_x"], s["base"])
        v = ease_io(u)
        p1 = (start[0] + (end[0] - start[0]) * 0.1, start[1] - 170)
        p2 = (end[0], end[1] - 260)
        x, y = _bezier(start, p1, p2, end, v)
        s_end = s["en_size"] / self.gsize[gi]
        sc = 1 + 0.45 * ease_io(prog(u, 0, 0.3)) if u < 0.3 else 1.45 + (s_end - 1.45) * ease_io(prog(u, 0.3, 1))
        rot = -6 * math.sin(math.pi * u)
        k = sc / S
        size = (max(1, int(txt.width * k)), max(1, int(txt.height * k)))
        lay = txt.resize(size, Image.BILINEAR)
        pa = 1 - prog(u, 0.72, 1.0)
        if pa > 0.01 and not ghost:
            lay = Image.alpha_composite(_fade(back.resize(size, Image.BILINEAR), pa), lay)
        ox, oy = ax * k, ay * k
        if abs(rot) > 0.2:
            cx, cy = lay.width / 2, lay.height / 2
            lay = lay.rotate(rot, Image.BICUBIC, expand=True)
            a = math.radians(rot)
            dx, dy = ox - cx, oy - cy
            ox = lay.width / 2 + dx * math.cos(a) + dy * math.sin(a)
            oy = lay.height / 2 - dx * math.sin(a) + dy * math.cos(a)
        return lay, int(round(x - ox)), int(round(y - oy))

    def _draw_flight(self, frame, pg, gi, u):
        """The flying word, with a short fading trail of where it just was."""
        for j, a in ((3, 0.07), (2, 0.13), (1, 0.22)):
            ug = u - 0.045 * j
            if 0.05 < ug < 0.9:
                lay, x, y = self._flight_layer(pg, gi, ug, ghost=True)
                _comp(frame, _fade(lay, a * (1 - prog(u, 0.8, 1.0))), x, y)
        lay, x, y = self._flight_layer(pg, gi, u)
        _comp(frame, lay, x, y)

    def _burst(self, frame, s, tau):
        """The landing flourish (Textbook: a puff of highlighter dust)."""
        cx, cy = s["en_x"] + s["en"].w / 2, s["base"] - s["en_size"] * 0.35
        rng = np.random.default_rng(s["gi"] * 7 + 3)
        p = _ease_out(tau / 0.75)
        fade_ = 1 - prog(tau, 0.25, 0.75)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for _ in range(16):
            ang = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(40, 130) * p
            r = rng.uniform(4, 10) * (1 - 0.4 * p)
            x = cx + math.cos(ang) * (dist + s["en"].w * 0.35)
            y = cy + math.sin(ang) * dist * 0.55
            d.ellipse([x - r, y - r, x + r, y + r], fill=self.burst_col + (int(200 * fade_),))
        frame.alpha_composite(ov.filter(ImageFilter.GaussianBlur(1.2)))

    # -------------------------------------------------------------- translation of the whole paragraph
    def _build_translation(self):
        p = self.panel
        top, bottom = self.p_top - 10, SAFE_BOTTOM - 20
        x0, x1 = self.x0 - 16, self.x1 + 16
        size = 52
        while True:
            lines = _ar_justified(_ar_wrap(self.translation, size, p["text"], p["font"], x1 - x0 - 72), size,
                                  p["text"], p["font"], x1 - x0 - 72)
            pitch = int(size * 1.75)
            if 160 + (len(lines) - 1) * pitch + lines[-1].height <= bottom - top or size <= 30:
                break
            size -= 2
        lab_h = _ar_img("الترجمة", 40, p["label"], p["font"]).height
        h = min(bottom - top, 60 + lab_h + (len(lines) - 1) * pitch + lines[-1].height + 10)
        im = Image.new("RGBA", (x1 - x0 + 80, h + 80), (0, 0, 0, 0))
        box = (40, 40, 40 + x1 - x0, 40 + h)
        im = Image.alpha_composite(im, _shadow_box(im.size, box, 30, 18, 70, 12))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle(box, 30, fill=p["bg"] + (255,), outline=p["border"] + (255,), width=4)
        lab = _ar_img("الترجمة", 40, p["label"], p["font"])
        _comp(im, lab, box[2] - 36 - lab.width, box[1] + 26)
        en = _Txt("TRANSLATION", 24, p["label"], "Bold", LABEL, track=0.18)
        en.put(im, box[0] + 36, box[1] + 26 + lab.height * 0.62)
        d.line([(box[0] + 36, box[1] + 30 + lab.height), (box[2] - 36, box[1] + 30 + lab.height)],
               fill=_mix(p["border"], p["bg"], 0.6) + (255,), width=2)
        y = box[1] + 60 + lab.height
        for ln in lines:
            _comp(im, ln, box[2] - 36 - ln.width, int(y))
            y += pitch
        return dict(im=im, x=x0 - 40, y=top - 40)

    def _draw_translation(self, frame, t):
        a = prog(t, self.tr0, self.tr0 + 0.45)
        if a <= 0:
            return
        e = ease_io(a)
        out = 1 - prog(t, self.tr1, self.tr1 + 0.4) if t < self.E else 0.0
        frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(70 * e * out))))
        im = self.tr["im"] if e * out >= 0.999 else _fade(self.tr["im"], e * out)
        _comp(frame, im, self.tr["x"], int(self.tr["y"] + 120 * (1 - e)))

    # -------------------------------------------------------------- render (shared)
    def _page_at(self, t):
        k = 0
        for j, tt in enumerate(self.turns):
            if t >= tt:
                k = j
        return k

    def render(self, t):
        k = self._page_at(t)
        if k > 0 and t < self.turns[k] + TURN:
            a = self._draw_page(k - 1, self.turns[k])
            b = self._draw_page(k, t)
            frame = self._turn(a, b, prog(t, self.turns[k], self.turns[k] + TURN))
        else:
            frame = self._draw_page(k, t)
        if t < self.sting:
            return self._sting(t).convert("RGB")
        if t < self.sting + 0.9:
            frame = self._intro(frame, t - self.sting)
        frame = self._camera(frame, t)
        if self.tr is not None and t >= self.tr0:
            self._draw_translation(frame, t)
        if self.has_ending and t >= self.E:
            frame = self._draw_end(frame, t)
        global_fade(frame, t, self.dur, fade_in=False)
        return frame.convert("RGB")

    def _camera(self, frame, t):
        """A slow push-in while the text is read, and a small nudge each time a word takes off."""
        s = 1 + 0.024 * ease_io(prog(t, self.first_t - 0.4, self.reading_end))
        for f0 in self.fly0:
            x = t - f0
            if 0 < x < 0.55:
                s += 0.0075 * math.sin(math.pi * x / 0.55)
        if s < 1.0008:
            return frame
        cx, cy = W / 2, 880.0
        box = (cx - cx / s, cy - cy / s, cx + (W - cx) / s, cy + (H - cy) / s)
        return frame.resize((W, H), Image.BICUBIC, box=box)

    def _turn(self, a, b, e):
        """A real page turn: the old page bends round a cylinder from its right edge and is carried over to the left,
        showing its back; the new page lies underneath, in the shadow of the turning sheet. The fold is slanted (the
        bottom corner leads)."""
        cut = self.wave_y + self.WAVE_H + 10  # the header stays; the page below it turns
        A = np.asarray(a.crop((0, cut, W, H)).convert("RGB"), np.float32)
        B = np.asarray(b.crop((0, cut, W, H)).convert("RGB"), np.float32)
        h, w = A.shape[:2]
        R_ = 72.0
        e = ease_io(e)
        X = np.arange(w, dtype=np.float32)[None, :]
        ys = np.arange(h, dtype=np.float32)[:, None]
        F = (w + 230.0) + (-3.4 * R_ - (w + 230.0)) * e
        fy = F - 230.0 * (ys / h)                      # fold position per row
        rows = np.arange(h)[:, None]
        back_col = np.array(self.page_back, np.float32)

        def take(xsrc):
            return A[rows, np.clip(xsrc, 0, w - 1).astype(np.int32)]

        out = B.copy()
        d = X - (fy + R_)  # the turning sheet throws a soft shadow on the new page
        out *= np.where(d > 0, 1 - 0.38 * np.exp(-np.clip(d, 0, None) / 55.0), 0.62)[..., None]
        flat = X < fy
        out = np.where(flat[..., None], A, out)
        # the turned-over part lying flat on top (its back, mirrored, a little see-through)
        xs_back = fy + math.pi * R_ + (fy - X)
        back = flat & (xs_back < w)
        light = 0.97 - 0.10 * np.exp(-np.clip(fy - X, 0, None) / 70.0)
        backside = (back_col * 0.92 + take(xs_back) * 0.08) * light[..., None]
        edge = 2 * fy - w + math.pi * R_  # its left edge: a shadow on the old page just beyond it
        sh = np.where((X < edge) & flat, 1 - 0.22 * np.exp(-np.clip(edge - X, 0, None) / 26.0), 1.0)
        out = np.where(flat[..., None] & ~back[..., None], out * sh[..., None], out)
        out = np.where(back[..., None], backside, out)
        # the curl itself
        rel = np.clip((X - fy) / R_, 0, 1)
        in_cyl = (X >= fy) & (X < fy + R_)
        th_b = math.pi - np.arcsin(rel)
        xs_cb = fy + R_ * th_b
        cyl_back = in_cyl & (xs_cb < w)
        lit = 0.80 + 0.32 * np.sin(th_b - math.pi / 2 + 0.6)  # a bright line along the top of the curl
        curl_back = (back_col * 0.92 + take(xs_cb) * 0.08) * np.clip(lit, 0.7, 1.12)[..., None]
        out = np.where(cyl_back[..., None], curl_back, out)
        th_f = np.arcsin(rel)
        xs_cf = fy + R_ * th_f
        cyl_front = in_cyl & ~cyl_back & (xs_cf < w)
        out = np.where(cyl_front[..., None], take(xs_cf) * (0.62 + 0.38 * np.cos(th_f))[..., None], out)
        frame = b.copy()
        frame.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA"), (0, cut))
        return frame

    def _intro(self, frame, t):
        """The header drops in, then the page fades up."""
        out = self.bg.copy()
        e = 1 - (1 - prog(t, 0.0, 0.55)) ** 3
        a = prog(t, 0.25, 0.8)
        body = frame.crop((0, self.band_h, W, H))
        _comp(out, _fade(body, a), 0, self.band_h + int(30 * (1 - a)))
        band = frame.crop((0, 0, W, self.band_h + 26))
        _comp(out, band, 0, int(-(self.band_h + 26) * (1 - e)))
        return out

    def _big_logo(self, size):
        key = ("biglogo", size)
        if key not in self._misc:
            self._misc[key] = logo_badge(self.logo_path, size, self.logo_shape)
        return self._misc[key]

    def _sting(self, t):
        """The logo opening: the logo springs up on the page's background, then flies to its place in the header."""
        out = self.bg.copy()
        big = self._big_logo(460)
        pop = ease_out_back(prog(t, 0.0, 0.35))
        fly = ease_io(prog(t, 0.5, self.sting))
        hx = self.x0 + self.logo_img.width / 2  # where the logo sits in the header
        hy = self.sub_y + self.sub_img.top + self.logo_img.height / 2
        cx, cy = 540 + (hx - 540) * fly, 860 + (hy - 860) * fly
        sc = (0.55 + 0.45 * pop) * (1 + (self.logo_img.width / big.width - 1) * fly)
        im = big.resize((max(1, int(big.width * sc)), max(1, int(big.height * sc))), Image.LANCZOS)
        _comp(out, _fade(im, min(1.0, prog(t, 0.0, 0.12))), int(cx - im.width / 2), int(cy - im.height / 2))
        if self.brand_name:
            nm = _Txt(self.brand_name.upper(), 64, self.accent if self.STYLE_LIGHT else (255, 255, 255), "ExtraBold",
                      LABEL, track=0.12)
            a = prog(t, 0.15, 0.35) * (1 - prog(t, 0.45, 0.6))
            if a > 0:
                nm.put(out, 540 - nm.w / 2, 860 + big.height * 0.55 * sc + 70, a)
        return out

    def _end_logo(self, frame, t):
        big = self._big_logo(190)
        sc = ease_out_back(prog(t, self.E + 0.1, self.E + 0.45))
        if sc <= 0.02:
            return
        im = big.resize((max(1, int(big.width * sc)), max(1, int(big.height * sc))), Image.LANCZOS)
        _comp(frame, im, int(540 - im.width / 2), int(470 - im.height / 2))

    # -------------------------------------------------------------- the ending card
    def _end_look(self):
        """Colours / fonts of the ending card; each design overrides the parts that differ."""
        return dict(card=(255, 255, 255, 255), rim=None, strip=self.band, title=INK, label=self.band,
                    muted=(118, 124, 130), btn=self.band, btn_txt=(255, 255, 255), veil=(18, 22, 28, 70), radius=44,
                    label_font=LABEL, label_w="ExtraBold", track=0.22, tilt=0.0, tape=False, rules=False,
                    hl=self.marker_col)

    def _end_lines(self, lines, max_w, size):
        """The question's lines wrapped to max_w at a size: [(kind, items, width)] where kind 'en' items = word _Txts
        and kind 'ar' items = one Arabic line image."""
        lk = self._end_l
        out = []
        for ln in lines:
            col = lk["title"]
            m = re.match(r"^\[([^\]]+)\]\s*(.*)$", ln)
            if m:  # a "[gold] ..." line: in the card's accent colour (a named colour may not read on every card)
                ln, col = m.group(2).strip(), lk["label"]
            if not ln:
                continue
            if re.search("[\u0600-\u06FF]", ln):
                im = _ar_fit(ln, size * 0.92, col, self.ar_font, max_w)
                out.append(("ar", [im], im.width))
                continue
            row, w = [], 0.0
            for word in ln.split():
                tx = _Txt(word, size, col, self.TITLE_W, self.TITLE)
                sp = size * 0.28
                if row and w + sp + tx.w > max_w:
                    out.append(("en", row, w))
                    row, w = [], 0.0
                w += (sp if row else 0) + tx.w
                row.append(tx)
            if row:
                out.append(("en", row, w))
        return out

    def _layout_end(self):
        """Lays the ending card out once (sizes and places); _draw_end animates it. The card: logo on its top edge,
        — NEXT READING — label, the question in the design's title font (one size, up to 4 lines), a call-to-action
        button that gets tapped, the handle."""
        lk = self._end_l = self._end_look()
        intro, q, cta, handle = self.ending
        CW = 900
        inner = CW - 130
        top_pad = 128 if self.end_logo else 76
        y = top_pad
        self.end_label = None
        if intro:
            txt = intro.rstrip(":：").strip()
            if not re.search("[\u0600-\u06FF]", txt):
                txt = txt.upper() if lk["track"] else txt
                self.end_label = _Txt(txt, 34 if lk["track"] else 50, lk["label"], lk["label_w"], lk["label_font"],
                                      track=lk["track"])
            else:
                self.end_label = _ar_fit(txt, 46, lk["label"], self.ar_font, inner)
            self.end_label_y = y + 40
            y += 40 + 62
        self.end_q = []
        if q:
            for size in range(86, 50, -4):
                rows = self._end_lines(q, inner, size)
                if len(rows) <= 4 and all(w <= inner for _, _, w in rows):
                    break
            pitch = int(size * 1.24)
            y += int(size * 0.95)
            k = 0
            for kind, items, w in rows:
                x = (CW - w) / 2
                if kind == "ar":
                    self.end_q.append(("ar", items[0], x, y, k))
                    k += 1
                else:
                    for tx in items:
                        self.end_q.append(("en", tx, x, y, k))
                        x += tx.w + size * 0.28
                        k += 1
                y += pitch
            y -= int(size * 0.2)
        self.end_btn = None
        if cta:
            y += 30
            room = CW - 80 - 160  # the text beside the (+), inside a pill at most the card width - 80
            rows = [_Txt(cta, 40, lk["btn_txt"], "Bold", LABEL)]
            if rows[0].w > room:
                fz = int(40 * room / rows[0].w)
                if fz >= 34:
                    rows = [_Txt(cta, fz, lk["btn_txt"], "Bold", LABEL)]
                else:  # a long call to action: two balanced lines
                    ws = cta.split()
                    parts = [cta]
                    if len(ws) > 1:
                        k = min(range(1, len(ws)), key=lambda j: abs(len(" ".join(ws[:j])) - len(" ".join(ws[j:]))))
                        parts = [" ".join(ws[:k]), " ".join(ws[k:])]
                    fz = 36
                    while fz > 22 and max(_font(fz, "Bold", LABEL).getlength(x) for x in parts) > room:
                        fz -= 2
                    rows = [_Txt(x, fz, lk["btn_txt"], "Bold", LABEL) for x in parts]
            tw = max(r.w for r in rows)
            bh = 108 if len(rows) == 1 else 150
            bw = tw + 96 + 64
            self.end_btn = dict(txt=rows, box=((CW - bw) / 2, y, (CW + bw) / 2, y + bh))
            y += bh
        self.end_handle = None
        if handle:
            y += 64
            self.end_handle = _Txt(handle, 34, lk["muted"], "SemiBold", LABEL)
            self.end_handle_y = y
            y += 10
        CH = int(y + 70)
        self.end_size = (CW, CH)
        # timings (seconds after E)
        n = max([it[4] for it in self.end_q] + [-1]) + 1
        self.end_q_t = 0.8
        q_end = self.end_q_t + 0.075 * n + 0.3
        self.end_btn_t = q_end + 0.1
        self.end_press = self.E + max(2.5, self.end_btn_t + 0.75)
        # the static card (shadow, paper, strip / tape / rules), with a margin for the logo and the shadow
        M = 120
        base = Image.new("RGBA", (CW + 2 * M, CH + 2 * M), (0, 0, 0, 0))
        r = lk["radius"]
        box = (M, M, M + CW, M + CH)
        base.alpha_composite(_shadow_box(base.size, box, r, 30, 120 if lk["card"][3] > 200 else 160, 18))
        d = ImageDraw.Draw(base)
        d.rounded_rectangle(box, r, fill=lk["card"])
        if lk["rim"]:
            d.rounded_rectangle(box, r, outline=lk["rim"], width=3)
        if lk["strip"]:
            m = Image.new("L", base.size, 0)
            ImageDraw.Draw(m).rounded_rectangle(box, r, fill=255)
            st = Image.new("RGBA", base.size, (0, 0, 0, 0))
            ImageDraw.Draw(st).rectangle([box[0], box[1], box[2], box[1] + 14], fill=tuple(lk["strip"]) + (255,))
            st.putalpha(ImageChops.multiply(st.getchannel("A"), m))
            base.alpha_composite(st)
        if lk["rules"]:
            for yy in (box[1] + 26, box[3] - 26):
                d.line([(box[0] + 40, yy), (box[2] - 40, yy)], fill=(40, 40, 40, 255), width=3)
                d.line([(box[0] + 40, yy + (8 if yy < box[3] - 30 else -8)),
                        (box[2] - 40, yy + (8 if yy < box[3] - 30 else -8))], fill=(40, 40, 40, 255), width=1)
        if lk["tape"]:
            tp = Image.new("RGBA", (260, 70), (236, 228, 200, 170))
            td = ImageDraw.Draw(tp)
            for x in range(0, 260, 9):
                td.line([(x, 0), (x, 70)], fill=(255, 255, 255, 26), width=3)
            tp = tp.rotate(-4, expand=True, resample=Image.BICUBIC)
            base.alpha_composite(tp, (int(M + CW * 0.68 - tp.width / 2), int(M - tp.height / 2 + 4)))
            if not self.end_logo:
                base.alpha_composite(tp.transpose(Image.FLIP_LEFT_RIGHT), (int(M + CW * 0.24 - tp.width / 2),
                                                                          int(M - tp.height / 2 + 4)))
        self.end_base, self.end_M = base, M
        self.end_y = max(250, int(900 - CH / 2))
        if self.end_y + CH > 1500:
            self.end_y = max(200, 1500 - CH)

    def _draw_end(self, frame, t):
        lk = self._end_l
        rel = t - self.E
        a = ease_io(prog(rel, 0.0, 0.55))
        if a > 0.001:  # the page goes soft and steps back
            small = frame.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5))
            blur = small.resize((W, H), Image.BILINEAR)
            frame = Image.blend(frame, blur, a)
            v = lk["veil"]
            frame.alpha_composite(Image.new("RGBA", (W, H), v[:3] + (int(v[3] * a),)))
        p = prog(rel, 0.12, 0.72)
        if p <= 0:
            return frame
        CW, CH = self.end_size
        M = self.end_M
        card = self.end_base.copy()
        # logo on the top edge
        if self.end_logo:
            big = self._big_logo(196)
            sc = ease_out_back(prog(rel, END_LOGO, END_LOGO + 0.4))
            if sc > 0.02:
                im = big.resize((max(1, int(big.width * sc)), max(1, int(big.height * sc))), Image.LANCZOS)
                _comp(card, im, int(M + CW / 2 - im.width / 2), int(M - im.height / 2 + 6))
        # — LABEL —
        if self.end_label is not None:
            lp = ease_io(prog(rel, 0.55, 1.0))
            if lp > 0:
                lab = self.end_label
                lw = lab.w if isinstance(lab, _Txt) else lab.width
                cx, ly = M + CW / 2, M + self.end_label_y
                if isinstance(lab, _Txt):
                    lab.put(card, cx - lw / 2, ly, lp)
                    mid = ly - lab.size * 0.36
                else:
                    _comp(card, _fade(lab, lp), int(cx - lw / 2), int(ly - lab.height * 0.7))
                    mid = ly - lab.height * 0.2
                L = 70 * lp
                dd = ImageDraw.Draw(card)
                c = tuple(lk["label"]) + (255,)
                dd.line([(cx - lw / 2 - 24 - L, mid), (cx - lw / 2 - 24, mid)], fill=c, width=4)
                dd.line([(cx + lw / 2 + 24, mid), (cx + lw / 2 + 24 + L, mid)], fill=c, width=4)
        # the question, word by word
        for kind, im, x, y, k in self.end_q:
            t0 = self.end_q_t + 0.075 * k
            wp = prog(rel, t0, t0 + 0.32)
            if wp <= 0:
                continue
            dy = 22 * (1 - ease_io(wp))
            if kind == "en":
                im.put(card, M + x, M + y + dy, min(1.0, wp * 1.4))
            else:
                _comp(card, _fade(im, min(1.0, wp * 1.4)), int(M + x), int(M + y + dy - im.height * 0.72))
        # the button: springs in, gets a shine, is tapped (press + ripple)
        if self.end_btn is not None:
            bp = prog(rel, self.end_btn_t, self.end_btn_t + 0.45)
            if bp > 0:
                card = self._draw_end_btn(card, M, rel, bp)
        if self.end_handle is not None:
            hp = prog(rel, self.end_btn_t + 0.35, self.end_btn_t + 0.7)
            if hp > 0:
                self.end_handle.put(card, M + CW / 2 - self.end_handle.w / 2, M + self.end_handle_y, hp)
        # the card rises with a spring (and a notebook note sits a little crooked)
        e = ease_out_back(p)
        sc = 0.9 + 0.1 * e
        if lk["tilt"]:
            card = card.rotate(lk["tilt"] * (0.4 + 0.6 * e), resample=Image.BICUBIC, expand=False)
        if sc < 0.999:
            card = card.resize((max(1, int(card.width * sc)), max(1, int(card.height * sc))), Image.BICUBIC)
        card = _fade(card, min(1.0, p * 2.2))
        cx, cy = W / 2, self.end_y + CH / 2 + 160 * (1 - e)
        _comp(frame, card, int(cx - card.width / 2), int(cy - card.height / 2))
        return frame

    def _draw_end_btn(self, card, M, rel, bp):
        lk = self._end_l
        b = self.end_btn
        x0, y0, x1, y1 = b["box"]
        x0, y0, x1, y1 = x0 + M, y0 + M, x1 + M, y1 + M
        bw, bh = x1 - x0, y1 - y0
        S = 2
        im = Image.new("RGBA", (int(bw + 80) * S, int(bh + 80) * S), (0, 0, 0, 0))
        ox = oy = 40
        pr = rel + self.E - self.end_press
        # tapped: ripple ring out of the button
        if 0 <= pr < 0.8:
            q = pr / 0.8
            g = 30 * ease_io(q)
            ImageDraw.Draw(im).rounded_rectangle([(ox - g) * S, (oy - g) * S, (ox + bw + g) * S, (oy + bh + g) * S],
                                                 int((bh / 2 + g) * S), outline=tuple(lk["btn"]) + (int(150 * (1 - q)),),
                                                 width=5 * S)
        sh = _shadow_box(im.size, (ox * S, (oy + 4) * S, (ox + bw) * S, (oy + bh + 4) * S), bh / 2 * S, 10 * S, 90, 0)
        im.alpha_composite(sh)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([ox * S, oy * S, (ox + bw) * S, (oy + bh) * S], int(bh / 2 * S),
                            fill=tuple(lk["btn"]) + (255,))
        # the "+" in a ring at the left (follow)
        cx, cy, r = (ox + 30 + 28) * S, (oy + bh / 2) * S, 26 * S
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=tuple(lk["btn_txt"]) + (255,), width=4 * S)
        L = 12 * S
        d.line([(cx - L, cy), (cx + L, cy)], fill=tuple(lk["btn_txt"]) + (255,), width=5 * S)
        d.line([(cx, cy - L), (cx, cy + L)], fill=tuple(lk["btn_txt"]) + (255,), width=5 * S)
        im = im.resize((int(bw + 80), int(bh + 80)), Image.LANCZOS)
        rows = b["txt"]
        pitch = rows[0].size * 1.25
        for j, r in enumerate(rows):
            r.put(im, ox + 96, oy + bh / 2 + r.size * 0.36 + (j - (len(rows) - 1) / 2) * pitch)
        # a shine sweeps across every 1.6 s
        sp = (rel - self.end_btn_t - 0.5) % 1.6
        if sp < 0.6 and rel > self.end_btn_t + 0.5:
            m = Image.new("L", im.size, 0)
            ImageDraw.Draw(m).rounded_rectangle([ox, oy, ox + bw, oy + bh], int(bh / 2), fill=255)
            gl = Image.new("L", im.size, 0)
            gx = ox - 80 + (bw + 160) * sp / 0.6
            ImageDraw.Draw(gl).polygon([(gx, oy), (gx + 46, oy), (gx + 16, oy + bh), (gx - 30, oy + bh)], fill=70)
            gl = ImageChops.multiply(gl.filter(ImageFilter.GaussianBlur(6)), m)
            im.alpha_composite(Image.merge("RGBA", (*[Image.new("L", im.size, 255)] * 3, gl)))
        # spring in, then the tap squeezes it
        sc = 0.6 + 0.4 * ease_out_back(bp)
        if 0 <= pr < 0.3:
            sc *= 1 - 0.07 * math.sin(math.pi * pr / 0.3)
        if abs(sc - 1) > 0.002:
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BICUBIC)
        _comp(card, _fade(im, min(1.0, bp * 2)), int((x0 + x1) / 2 - im.width / 2), int((y0 + y1) / 2 - im.height / 2))
        return card

    def _wt(self, i, f):
        """The moment the reading reaches fraction f of word i."""
        return self.vs[i] + f * max(0.12, self.ve[i] - self.vs[i])

    def _span_q(self, sp, t):
        t0 = self._wt(sp["i0"], sp["f0"])
        return prog(t, t0, max(t0 + 0.28, self._wt(sp["i1"], sp["f1"])))

    def _draw_page(self, k, t):
        pg = self.pages[k]
        frame = pg["base"].copy()
        self._draw_progress(frame, prog(t, self.first_t, self.last_t))
        if pg["kind"] == "recap":
            for j, s in enumerate(pg["slots"]):
                if t >= self.recap_row[j]:
                    self._draw_slot(frame, s, t, self.recap_row[j], True)
            self._draw_final(frame, pg, t)
            return frame
        bx0, by0, bx1, by1 = pg["box"]
        focus = self._focus(pg, t)
        if focus:
            self._draw_focus_band(frame, pg, *focus)
        if self.clear:
            self._draw_reader(frame, pg, t)
        if not self.MARK_ON_TOP:
            for sp in pg["spans"]:
                q = self._span_q(sp, t)
                if q > 0:
                    self._draw_mark(frame, sp["mk"], q)
        # the paragraph: faded text + the ink of every spoken word, the current one wiping in left to right
        mask = Image.new("L", (bx1 - bx0, by1 - by0), 0)
        md = ImageDraw.Draw(mask)
        active = []
        for pc in pg["pieces"]:
            i = pc["i"]
            if t < self.vs[i]:
                break
            x0, y0, x1, y1 = pc["box"]
            t0, t1 = self._wt(i, pc["f0"]), self._wt(i, pc["f1"])
            q = prog(t, t0, t1)
            if q <= 0:
                break
            if t < t1 + 0.2 and not pc.get("dc"):
                active.append((pc, prog(t, t0, t1 + 0.2)))
            xr = x0 + (x1 - x0) * q
            if q >= 1:
                md.rectangle([x0 - bx0, y0 - by0, x1 - bx0, y1 - by0], fill=255)
            else:
                edge = 22
                if xr - edge > x0:
                    md.rectangle([x0 - bx0, y0 - by0, xr - edge - bx0, y1 - by0], fill=255)
                for s in range(edge):
                    xs = xr - edge + s - bx0
                    if xs >= x0 - bx0:
                        md.line([(xs, y0 - by0), (xs, y1 - by0)], fill=int(255 * (1 - s / edge)))
        text = pg["faded"].copy()
        ink = Image.new("RGBA", text.size, (0, 0, 0, 0))
        ink.paste(pg["ink_rgb"], (0, 0), ImageChops.multiply(mask, pg["ink_a"]))
        text.alpha_composite(ink)
        for pc, p in active:  # the word being spoken breathes: grows a touch, lifts, settles
            self._breathe(text, pc["box"], (bx0, by0), p)
        frame.alpha_composite(text, (bx0, by0))
        if focus:
            self._dim(frame, pg, *focus)
        if self.MARK_ON_TOP:
            for sp in pg["spans"]:
                q = self._span_q(sp, t)
                if q > 0:
                    self._draw_mark(frame, sp["mk"], q)
        for s in pg["slots"]:
            t_land = self.fly0[s["gi"]] + FLY
            if t >= t_land:
                self._draw_slot(frame, s, t, t_land, False)
                if t < t_land + 0.8:
                    self._burst(frame, s, t - t_land)
        for gi in pg["keys"]:
            u = prog(t, self.fly0[gi], self.fly0[gi] + FLY)
            if 0 < u < 1:
                self._draw_flight(frame, pg, gi, u)
        if not self.recap and k == len(self.page_words) - 1:
            self._draw_final(frame, pg, t)
        return frame

    def _breathe(self, text, box, origin, p):
        x0, y0, x1, y1 = (box[0] - origin[0], box[1] - origin[1], box[2] - origin[0], box[3] - origin[1])
        k = math.sin(math.pi * p)
        sc = 1 + self.BREATH * k
        if k < 0.02:
            return
        word = text.crop((x0, y0, x1, y1))
        text.paste((0, 0, 0, 0), (x0, y0, x1, y1))
        big = word.resize((max(1, int(word.width * sc)), max(1, int(word.height * sc))), Image.BICUBIC)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 3 * k
        text.alpha_composite(big, (int(round(cx - big.width / 2)), int(round(cy - big.height / 2))))

    def _focus(self, pg, t):
        """(y of the focus band, strength 0-1) while the voice reads this page, else None."""
        lines = pg["lines"]
        if not lines:
            return None
        a = prog(t, lines[0]["t0"] - 0.45, lines[0]["t0"] + 0.05) * (1 - prog(t, lines[-1]["t1"] + 0.25,
                                                                                lines[-1]["t1"] + 0.8))
        if a <= 0.01:
            return None
        c = 0
        for j, ln in enumerate(lines):
            if t >= ln["t0"] - 0.12:
                c = j
        y = lines[c]["y"]
        if c > 0:  # glide from the line before
            e = ease_io(prog(t, lines[c]["t0"] - 0.2, lines[c]["t0"] + 0.12))
            y = lines[c - 1]["y"] + (y - lines[c - 1]["y"]) * e
        return y, a

    def _reader_col(self):
        """The reading marker's colour: a soft tint of the design's colour (RGBA)."""
        return getattr(self, "reader_col", None) or (_mix(self.accent, PAPER_TOP, 0.74) + (255,))

    def _draw_reader(self, frame, pg, t):
        """Clear text: a soft rounded marker behind the word being read, gliding from word to word on a line."""
        lines = pg["lines"]
        if not lines or t < lines[0]["t0"] - 0.05:
            return
        a = 1 - prog(t, lines[-1]["t1"] + 0.1, lines[-1]["t1"] + 0.45)
        if a <= 0.01:
            return
        cur = prev = None
        for pc in pg["pieces"]:
            if pc.get("dc"):
                continue
            t0 = self._wt(pc["i"], pc["f0"])
            if t0 <= t:
                prev, cur = cur, (pc, t0)
            else:
                break
        if cur is None:
            return
        pc, t0 = cur
        size = pg["size"]
        x0, _, x1, _ = pc["box"]
        yb = pc["yb"]
        if prev is not None and abs(prev[0]["yb"] - yb) < 2:  # glide from the word before on the same line
            e = ease_io(prog(t, t0, t0 + 0.16))
            px0, _, px1, _ = prev[0]["box"]
            x0, x1 = px0 + (x0 - px0) * e, px1 + (x1 - px1) * e
        else:  # a new line: it grows in
            e = 1 - (1 - prog(t, t0, t0 + 0.14)) ** 3
            cx, hw = (x0 + x1) / 2, (x1 - x0) / 2 * (0.6 + 0.4 * e)
            x0, x1 = cx - hw, cx + hw
        y0, y1 = yb - size * 0.84, yb + size * 0.30
        w, h = int(x1 - x0 + 20), int(y1 - y0)
        col = self._reader_col()
        im = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], int(h * 0.32),
                                             fill=col[:3] + (int(col[3] * a),))
        _comp(frame, im, int(x0 - 10), int(y0))

    def _draw_focus_band(self, frame, pg, y, a):
        size = pg["size"]
        key = ("band", size)
        if key not in self._misc:
            bh = int(size * 1.34)
            im = Image.new("RGBA", (self.width + 44, bh), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle([0, 0, im.width - 1, bh - 1], int(bh * 0.3), fill=self.focus_col)
            self._misc[key] = im
        im = self._misc[key]
        _comp(frame, _fade(im, a), self.x0 - 22, int(round(y - im.height / 2)))

    def _dim(self, frame, pg, y, a):
        """The lines not being read fade back a little toward the page (the read line stays sharp)."""
        bx0, by0, bx1, by1 = pg["box"]
        lh = pg["lh"]
        key = ("hole", bx1 - bx0, lh)
        if key not in self._misc:
            hh = int(lh * 1.5)
            v = np.linspace(-1, 1, hh)
            prof = np.clip((1 - np.abs(v)) / 0.42, 0, 1)  # flat in the middle, soft edges
            self._misc[key] = Image.fromarray((np.repeat(prof[:, None], bx1 - bx0, axis=1) * 255).astype(np.uint8))
        hole = self._misc[key]
        m = Image.new("L", (bx1 - bx0, by1 - by0), 0)
        m.paste(hole, (0, int(round(y - by0 - hole.height / 2))))
        k = self.DIM * a
        m = m.point([int(255 * k * (255 - v) / 255) for v in range(256)])
        frame.paste(pg["clean"], (bx0, by0), m)

    def _slot_of(self, pg, gi):
        return next(s for s in pg["slots"] if s["gi"] == gi)

    # -------------------------------------------------------------- sound (shared)
    def _mark_sound(self, mx, t):
        pass

    def sound(self, mx):
        if self.sting:
            sig, pan = mx.whoosh(0.6)
            mx.add(0.02, sig, 0.12, pan)
            mx.add(0.3, mx.chime(), 0.16)
            mx.add(self.sting - 0.35, mx.whoosh(0.5)[0], 0.08)
        mx.intro(0.05 + self.sting)
        mx.add(0.05 + self.sting, mx.paper(), 0.45)
        if self.audio:
            self._place_voice(mx)
        for k in range(1, len(self.turns)):
            mx.add(self.turns[k], mx.paper(), 0.5)
        for pg in self.pages:
            for sp in pg.get("spans", []):
                self._mark_sound(mx, self._wt(sp["i0"], sp["f0"]))
        for gi in range(len(self.groups)):
            sig, pan = mx.whoosh(0.7)
            mx.add(self.fly0[gi], sig, 0.09, pan)
            mx.add(self.fly0[gi] + FLY - 0.04, mx.pop(), 0.12)
            if self.groups[gi]["ar"]:
                mx.add(self.fly0[gi] + FLY + 0.1, mx.scribble(0.5), 0.05)
        if self.recap:
            for t in self.recap_row:
                mx.add(t, mx.pop(), 0.08)
        for c in self.checks:
            mx.add(c, mx.click(), 0.22)
        self._final_sound(mx)
        if self.tr0 is not None:
            mx.add(self.tr0, mx.paper(), 0.4)
        if self.has_ending:
            mx.add(self.E, mx.chime(), 0.18)
            if self.end_logo:
                mx.add(self.E + END_LOGO, mx.pop(), 0.07)
            if self.end_btn is not None:
                mx.add(self.end_press, mx.click(), 0.2)

    def _final_sound(self, mx):
        pass

    def _place_voice(self, mx):
        """The recording, cut between the pages: each later page's part starts when its page is on screen."""
        try:
            a = load_audio(self.audio)
        except Exception:
            return
        a = a / (np.abs(a).max() + 1e-9) * 0.9 * self.audio_gain
        cuts = self.cuts + [len(a) / SR + 1.0]
        for k in range(len(self.page_words)):
            i0, i1 = int(cuts[k] * SR), min(len(a), int(cuts[k + 1] * SR))
            if i1 <= i0:
                continue
            seg = a[i0:i1].copy()
            f = min(len(seg) // 4, int(0.012 * SR))
            if f > 1 and len(self.page_words) > 1:
                ramp = np.linspace(0, 1, f)[:, None]
                if k:
                    seg[:f] *= ramp
                if k < len(self.page_words) - 1:
                    seg[-f:] *= ramp[::-1]
            at = int((self.lead + cuts[k] + self.shifts[k]) * SR)
            n = min(len(seg), mx.n - at)
            if n > 0 and at >= 0:
                mx.voice[at:at + n] += seg[:n]
                mx.has_voice = True


# ================================================================== Night studio
class StudioVideo(TextVideo):
    TITLE, TITLE_W = DISPLAY, "Regular"
    SUP = DROPCAP = TAB = False
    STYLE_LIGHT = False
    BODY = LABEL
    MIN_SIZE = 40               # a sans-serif reads bigger
    W_REG, W_KEY = "Medium", "Bold"
    LINE = 1.7
    GOLD, BLUE = (246, 197, 96), (122, 162, 255)

    def _end_look(self):
        return dict(super()._end_look(), card=(16, 22, 46, 236), rim=(246, 197, 96, 150), strip=None,
                    title=(255, 255, 255), label=self.GOLD, muted=(150, 160, 196), btn=self.GOLD, btn_txt=(16, 20, 40),
                    veil=(4, 6, 16, 150))

    def _style(self, d):
        super()._style(d)
        self.accent = self.GOLD
        self.x0, self.x1 = 72, SAFE_RIGHT
        self.ink, self.key_ink = (240, 243, 255), self.GOLD
        self.faded, self.faded_key = (66, 74, 100), (118, 101, 66)
        self.en_col = (255, 255, 255)
        self.ar_col, self.ar_font = self.GOLD, DEFAULT_FONT
        self.bank_label, self.bank_label_ar = "KEY WORDS", "كلمات مهمة"
        self.bank_col = (142, 166, 255)
        self.panel = dict(bg=(20, 26, 52), border=self.GOLD, text=self.GOLD, label=(142, 166, 255), font=DEFAULT_FONT)
        self.wave_cols = ((255, 255, 255, 46), "grad")
        self.wave_grad = (self.BLUE, self.GOLD)
        self.focus_col = (255, 255, 255, 15)
        self.reader_col = (255, 255, 255, 40)
        self.page_back = (26, 34, 66)

    def _background(self):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - 540) / 900) ** 2 + ((yy - 520) / 1150) ** 2)
        c0, c1, c2 = (np.array(c, np.float32) for c in ((31, 45, 94), (12, 17, 42), (5, 7, 15)))
        k1 = np.clip(r / 0.6, 0, 1)[..., None]
        k2 = np.clip((r - 0.6) / 0.6, 0, 1)[..., None]
        arr = np.where(r[..., None] < 0.6, c0 * (1 - k1) + c1 * k1, c1 * (1 - k2) + c2 * k2)
        g = np.exp(-(((xx - 200) / 520) ** 2 + ((yy - 1500) / 420) ** 2))[..., None]
        arr = arr + g * np.array((70, 110, 255), np.float32) * 0.16
        img = _noise_bg(arr, 2.0, 9)
        dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # a few soft out-of-focus lights
        dd = ImageDraw.Draw(dots)
        rng = np.random.default_rng(12)
        for _ in range(16):
            x, y, rr = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(18, 60)
            dd.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(140, 170, 255, int(rng.uniform(8, 22))))
        return Image.alpha_composite(img, dots.filter(ImageFilter.GaussianBlur(10)))

    def _header(self):
        self.sub_img = _Txt(self.subtitle.upper(), 28, (142, 166, 255), "Bold", LABEL, track=0.2) \
            if self.subtitle else None
        lines, size = self._fit_title(self.TITLE, self.TITLE_W, 78, 52, 62)
        self.title_imgs = [_Txt(ln, size, (255, 255, 255), self.TITLE_W, self.TITLE) for ln in lines]
        self.sub_y = 186
        y = self.sub_y + (92 if (self.sub_img or self.level) else 40)
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.2)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 36
        self.badge = self._badge(self.GOLD, (12, 16, 36))
        self.tag_img = _ar_img(self.tag, 36, (142, 166, 255), self.ar_font) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h + 24
        self.wave_y = self.bar_y + 4
        self.p_top = self.band_h + 70
        self._apply_brand((255, 255, 255), (142, 166, 255), 24)

    def _band_layer(self, img):
        self._put_sub_line(img, self.sub_y)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        self._wave_track(img)

    def _decor(self, dd, x, yb, w, size):
        pass

    def _make_mark(self, sp):
        """A soft gold glow behind the words."""
        size = sp["size"]
        txt = " ".join(self.words[i]["w"] for i in range(sp["i0"], sp["i1"] + 1))
        t = _Txt(txt, size, self.GOLD, self.W_KEY, self.BODY)
        pad = 40
        im = Image.new("RGBA", (t.im.width + 2 * pad, t.im.height + 2 * pad), (0, 0, 0, 0))
        im.alpha_composite(t.im, (pad, pad))
        glow = im.filter(ImageFilter.GaussianBlur(14))
        glow = Image.alpha_composite(glow, glow)
        return (int(sp["x"] - t.pad - pad), int(sp["yb"] - t.base - pad), glow)

    def _draw_mark(self, frame, mk, q):
        x, y, im = mk
        a = ease_io(min(1.0, q * 1.6))
        _comp(frame, _fade(im, 0.55 + 0.45 * a if q < 1 else 0.7), x, y)

    def _fly_back(self, t, z, S):
        glow = t.im.copy()
        glow = Image.composite(Image.new("RGBA", glow.size, self.GOLD + (255,)), glow, glow.getchannel("A"))
        glow = glow.filter(ImageFilter.GaussianBlur(12 * S))
        return Image.alpha_composite(glow, glow)

    # glass cards, two columns
    def _burst(self, frame, s, tau):
        """Gold sparkles bursting from the card."""
        cx, cy = s["en_x"] + s["en"].w / 2, s["base"] - s["en_size"] * 0.35
        rng = np.random.default_rng(s["gi"] * 5 + 1)
        p = _ease_out(tau / 0.8)
        fade_ = 1 - prog(tau, 0.3, 0.8)
        for _ in range(11):
            ang = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(50, 150) * p
            r = int(rng.uniform(9, 17) * (1 - 0.3 * p))
            key = ("spark", r)
            if key not in self._misc:
                self._misc[key] = _sparkle(r, (255, 226, 150))
            sp = self._misc[key]
            x = cx + math.cos(ang) * (dist + s["en"].w * 0.3)
            y = cy + math.sin(ang) * dist * 0.6
            _comp(frame, _fade(sp, fade_ * rng.uniform(0.6, 1.0)), int(x - r), int(y - r))

    def _card_h(self, n, size):
        return max(132, min(184, int(size * 3.0) - (14 if n > 6 else 0)))

    def _bank_h(self, n, size=None):
        if n == 0:
            return 0
        rows = (n + 1) // 2
        return 56 + 66 + rows * self._card_h(n, size or self.size) + (rows - 1) * 20

    def _bank_rows(self, img, keys, top, size=None, avail=None, label=None):
        n = len(keys)
        rows = (n + 1) // 2
        ch = self._card_h(n, size or self.size)
        if avail:
            ch = max(110, min(190, (avail - 66 - (rows - 1) * 20) // max(1, rows)))
        top -= 8
        lab = _Txt(label or self.bank_label, 26, self.bank_col, "Bold", LABEL, track=0.22)
        lab.put(img, self.x0, top + 36)
        ar = _ar_img(self.bank_label_ar, 34, self.bank_col, self.ar_font)
        if lab.w + ar.width + 40 < self.width:
            _comp(img, ar, self.x1 - ar.width, top + 36 - int(ar.height * 0.64))
        gap = 20
        cw = (self.width - gap) // 2
        en_size = int(min(48, ch * 0.29))
        slots = []
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for j, gi in enumerate(keys):
            g = self.groups[gi]
            r, c = divmod(j, 2)
            wide = (j == n - 1 and n % 2 == 1)
            x = self.x0 + (0 if wide else c * (cw + gap))
            w = self.width if wide else cw
            y = top + 66 + r * (ch + gap)
            d.rounded_rectangle([x, y, x + w, y + ch], 22, fill=(255, 255, 255, 9), outline=(255, 255, 255, 26),
                                width=2)
            en = _Txt(g["text"], en_size, self.en_col, self.W_KEY, self.BODY)
            if en.w > w - 100:  # room for the tick in the corner
                en = _Txt(g["text"], max(22, int(en_size * (w - 100) / en.w)), self.en_col, self.W_KEY, self.BODY)
            base = y + int(ch * 0.4)
            ar_im = _ar_fit(g["ar"], en_size + 2, self.GOLD, self.ar_font, w - 56) if g["ar"] else None
            slots.append(dict(gi=gi, card=(x, y, x + w, y + ch), y=y, h=ch, base=base, en=en, en_x=x + 28,
                              en_size=en.size, num_x=x + w - 30,
                              ar=ar_im, ar_x=x + w - 28 - (ar_im.width if ar_im is not None else 0),
                              ar_y=int(y + ch * 0.71 - ar_im.height / 2) if ar_im is not None else 0))
        img.alpha_composite(ov)
        return slots

    def _draw_slot(self, frame, s, t, t_land, recap):
        x0, y0, x1, y1 = s["card"]
        a = prog(t, t_land, t_land + 0.4)
        key = ("card", x1 - x0, y1 - y0)
        if key not in self._misc:
            im = Image.new("RGBA", (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0, 0))
            dd = ImageDraw.Draw(im)
            dd.rounded_rectangle([0, 0, im.width - 1, im.height - 1], 22, fill=(255, 255, 255, 30),
                                 outline=self.GOLD + (130,), width=2)
            dd.rounded_rectangle([2, 2, im.width - 3, im.height // 2], 20, fill=(255, 255, 255, 14))
            self._misc[key] = im
        _comp(frame, _fade(self._misc[key], a), x0, y0)
        self._put_en(frame, s, t, t_land, recap)
        q = ease_io(prog(t, t_land + 0.12, t_land + 0.12 + REVEAL))
        if s["ar"] is not None and q > 0:
            self._put_ar(frame, s["ar"], s["ar_x"], s["ar_y"], q)
        self._draw_check(frame, s, t)

    def _draw_check(self, frame, s, t):
        c = self._check_at(s["gi"])
        if c is None or t < c:
            return
        sc = ease_out_back(prog(t, c, c + 0.3))
        if sc > 0.02:
            key = ("check", 17)
            if key not in self._misc:
                self._misc[key] = _check(17, self.GOLD, (12, 16, 36))
            r = self._misc[key]
            im = r.resize((max(1, int(r.width * sc)), max(1, int(r.height * sc))), Image.LANCZOS)
            _comp(frame, im, int(s["card"][2] - 30 - im.width / 2), int(s["card"][1] + 30 - im.height / 2))

    def _mark_sound(self, mx, t):
        mx.add(t, mx.chime(), 0.035)


# ================================================================== Exam passage
class ExamVideo(TextVideo):
    TITLE, TITLE_W = SERIF, "Bold"
    SUP = DROPCAP = TAB = False
    BODY = SERIF
    W_REG, W_KEY = "Regular", "Bold"
    LINE = 1.62
    MARK_ON_TOP = True
    FINISH_EXTRA = 0.7
    RED, BLUE = (200, 38, 28), (31, 79, 163)
    SHEET = (36, 40, 1044, 1700)

    def _end_look(self):
        return dict(super()._end_look(), card=(255, 254, 250, 255), strip=None, rules=True, radius=6,
                    title=(22, 22, 22), label=self.RED, btn=self.RED, veil=(20, 20, 20, 80))

    def _style(self, d):
        super()._style(d)
        self.accent = self.RED
        self.x0, self.x1 = 128, SAFE_RIGHT
        self.ink, self.key_ink = (22, 22, 22), (22, 22, 22)
        self.faded, self.faded_key = (172, 169, 163), (150, 140, 136)
        self.en_col = (22, 22, 22)
        self.ar_col, self.ar_font = self.BLUE, PLEX_AR
        self.bank_label, self.bank_label_ar = "KEY VOCABULARY", "مفردات مهمة"
        self.bank_col = self.RED
        self.rule_col = (236, 233, 226)
        self.leader_col = (205, 202, 196)
        self.flash_col = (255, 236, 232)
        self.panel = dict(bg=(255, 254, 250), border=(40, 40, 40), text=self.BLUE, label=self.RED, font=PLEX_AR)
        self.wave_cols = ((216, 212, 204), (22, 22, 22))
        self.wave_grad = ((22, 22, 22), (22, 22, 22))
        self.focus_col = (234, 240, 250, 255)
        self.reader_col = (212, 224, 246, 255)
        self.page_back = (246, 244, 238)

    def show_line_ref(self):
        return True

    def _bank_h(self, n, size=None):
        return 0 if n == 0 else super()._bank_h(n, size) + 96  # + the LEARNED stamp

    def _background(self):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        arr = np.repeat(np.array((214, 210, 201), np.float32)[None, None, :], H, 0).repeat(W, 1)
        v = 1.05 - 0.22 * (((xx - 540) / 760) ** 2 + ((yy - 900) / 1200) ** 2)
        img = _noise_bg(arr * v[..., None], 2.2, 5)
        x0, y0, x1, y1 = self.SHEET
        img.alpha_composite(_shadow_box((W, H), (x0, y0, x1, y1), 4, 16, 90, 10))
        ImageDraw.Draw(img).rectangle([x0, y0, x1, y1], fill=(255, 254, 250, 255))
        return img

    def _header(self):
        self.sub_img = _Txt((self.subtitle or "Reading passage").upper(), 26, (90, 90, 90), "Bold", LABEL,
                            track=0.2)
        lines, size = self._fit_title(self.TITLE, self.TITLE_W, 60, 44, 50)
        self.title_imgs = [_Txt(ln, size, (17, 17, 17), self.TITLE_W, self.TITLE) for ln in lines]
        self.sub_y = 150
        y = self.sub_y + 76
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.18)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 34
        self.badge = self._badge((30, 30, 30), (255, 255, 255), 24)
        self.tag_img = _ar_img(self.tag, 32, (110, 110, 110), self.ar_font) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h
        self.wave_y = self.band_h + 32
        self.p_top = self.band_h + 68
        self._apply_brand((17, 17, 17), (90, 90, 90), 22)

    def _band_layer(self, img):
        self._put_sub_line(img, self.sub_y)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        ImageDraw.Draw(img).rectangle([self.x0, self.bar_y, self.x1, self.bar_y + 3], fill=(30, 30, 30, 255))
        self._wave_track(img)

    def _decor(self, dd, x, yb, w, size):
        pass

    def _page_decor(self, base, k, baselines, lh, size):
        """Line numbers in the margin (1, 5, 10 …, counted through the whole passage)."""
        for li, yb in enumerate(baselines):
            n = self.line_base[k] + li + 1
            if n == 1 or n % 5 == 0:
                t = _Txt(str(n), max(20, int(size * 0.46)), (150, 146, 140), "SemiBold", LABEL)
                t.put(base, self.x0 - 26 - t.w, yb)

    def _make_mark(self, sp):
        size = sp["size"]
        x0, x1 = sp["x"] - 7, sp["x2"] + 7
        y0, y1 = sp["yb"] - size * 0.86, sp["yb"] + size * 0.3
        rng = np.random.default_rng(sp["i0"] + 3)
        j = lambda: rng.uniform(-2.5, 2.5)
        pts = [(x0 + j(), y0 + j()), (x1 + j(), y0 + j()), (x1 + j(), y1 + j()), (x0 + j(), y1 + j()),
               (x0 + j(), y0 - 3)]
        return pts

    def _draw_mark(self, frame, pts, q):
        part = _partial(pts, ease_io(min(1.0, q * 1.3)))
        if len(part) > 1:
            ImageDraw.Draw(frame).line(part, fill=self.RED + (255,), width=4, joint="curve")

    def _fly_back(self, t, z, S):
        bx = (t.pad - 10 * S, t.base - int(z * 0.9 * S), t.pad + t.w + 10 * S, t.base + int(z * 0.32 * S))
        sh = _shadow_box(t.im.size, bx, 4 * S, 12 * S, 80, 12 * S)
        pill = Image.new("RGBA", t.im.size, (0, 0, 0, 0))
        ImageDraw.Draw(pill).rectangle(bx, fill=(255, 254, 250, 255), outline=self.RED + (255,), width=4 * S)
        return Image.alpha_composite(sh, pill)

    def _burst(self, frame, s, tau):
        """Red ink droplets flicked from the pen."""
        cx, cy = s["en_x"] + s["en"].w + 10, s["base"] - s["en_size"] * 0.4
        rng = np.random.default_rng(s["gi"] * 3 + 9)
        p = _ease_out(tau / 0.55)
        fade_ = 1 - prog(tau, 0.35, 0.8)
        d = ImageDraw.Draw(frame)
        for _ in range(9):
            ang = rng.uniform(-1.2, 1.2)
            dist = rng.uniform(26, 90) * p
            r = rng.uniform(2.5, 6.5)
            x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist * 0.8
            col = _mix(self.RED, (255, 254, 250), 1 - fade_)
            d.ellipse([x - r * 1.25, y - r, x + r * 1.25, y + r], fill=col + (255,))

    def _draw_check(self, frame, s, t):
        c = self._check_at(s["gi"])
        if c is None or t < c:
            return
        p = prog(t, c, c + 0.25)
        key = ("tick", s["en_size"])
        if key not in self._misc:
            self._misc[key] = _pen_tick(max(16, int(s["en_size"] * 0.45)), self.RED)
        im = self._misc[key]
        w = max(1, int(im.width * p))
        _comp(frame, im.crop((0, 0, w, im.height)), int(s["num_x"] - im.width / 2 + 6),
              int(s["base"] - s["en_size"] * 0.4 - im.height / 2))

    def _stamp(self):
        if "stamp" not in self._misc:
            n = len(self.groups)
            t = _Txt(f"{n}/{n} LEARNED", 40, self.RED, "ExtraBold", LABEL, track=0.12)
            w, h = t.w + 56, 80
            im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle([10, 10, 10 + w, 10 + h], 8, outline=self.RED + (255,), width=5)
            t.put(im, 10 + 28, 10 + h / 2 + 15)
            rng = np.random.default_rng(2)  # worn ink
            a = np.asarray(im.getchannel("A"), np.float32) * rng.uniform(0.72, 1.0, (im.height, im.width))
            im.putalpha(Image.fromarray(a.astype(np.uint8)))
            self._misc["stamp"] = im.rotate(8, Image.BICUBIC, expand=True)
        return self._misc["stamp"]

    def _draw_final(self, frame, pg, t):
        if not self.groups or t < self.finish_t or not pg["slots"]:
            return
        e = ease_out_back(prog(t, self.finish_t, self.finish_t + 0.35))
        st = self._stamp()
        sc = 1.8 - 0.8 * e
        im = st.resize((max(1, int(st.width * sc)), max(1, int(st.height * sc))), Image.BILINEAR)
        last = pg["slots"][-1]
        cy = min(SAFE_BOTTOM - st.height / 2 - 6, last["y"] + last["h"] + st.height / 2 + 14)
        cx = self.x1 - st.width / 2
        _comp(frame, _fade(im, min(1.0, prog(t, self.finish_t, self.finish_t + 0.15)) * 0.9),
              int(cx - im.width / 2), int(cy - im.height / 2))

    def _mark_sound(self, mx, t):
        mx.add(t, mx.scribble(0.3), 0.05)

    def _final_sound(self, mx):
        if self.groups:
            mx.add(self.finish_t + 0.12, mx.stamp(), 0.45)


# ================================================================== Notebook
NOTE_COLS = [(255, 243, 161), (255, 209, 220), (201, 236, 255), (214, 245, 200), (255, 224, 184)]
NOTE_ROT = [-3.0, 2.2, -1.5, 2.6, -2.2, 1.6, -2.8, 2.0, -1.2, 2.4]


class NotebookVideo(TextVideo):
    TITLE, TITLE_W = HAND, "Regular"
    SUP = DROPCAP = TAB = False
    BODY = HAND
    MIN_SIZE = 52               # handwriting reads smaller than print
    W_REG, W_KEY = "Regular", "Regular"
    LINE = 1.5
    MARK_ON_TOP = True
    BLUE, RED = (31, 59, 115), (208, 52, 44)

    def _end_look(self):
        return dict(super()._end_look(), card=(255, 241, 158, 255), strip=None, radius=8, tilt=-1.6, tape=True,
                    title=self.BLUE, label=self.RED, muted=(120, 110, 70), btn=self.BLUE, label_font=HAND,
                    label_w="Regular", track=0.0, veil=(30, 34, 44, 70))

    def _style(self, d):
        super()._style(d)
        self.accent = self.RED
        self.x0, self.x1 = 92, SAFE_RIGHT
        self.ink, self.key_ink = self.BLUE, self.RED
        self.faded, self.faded_key = (180, 190, 204), (226, 170, 166)
        self.en_col = self.BLUE
        self.ar_col, self.ar_font = self.RED, RUQAA
        self.bank_label, self.bank_label_ar = "My new words", "كلماتي الجديدة"
        self.bank_col = self.RED
        self.panel = dict(bg=(255, 246, 196), border=(226, 200, 96), text=self.RED, label=self.BLUE, font=RUQAA)
        self.wave_cols = ((202, 214, 230), self.BLUE)
        self.wave_grad = (self.BLUE, self.BLUE)
        self.focus_col = (255, 244, 160, 120)
        self.reader_col = (255, 232, 130, 170)
        self.page_back = (243, 240, 229)

    def _background(self):
        img = _noise_bg(_vgrad((249, 247, 240), (244, 241, 232)), 1.8, 7)
        d = ImageDraw.Draw(img)
        d.line([(62, 0), (62, H)], fill=(240, 150, 150, 255), width=3)
        for k in range(9):  # binding holes along the top
            x = 90 + k * 112
            d.ellipse([x - 13, 40, x + 13, 66], fill=(222, 216, 204, 255))
            d.ellipse([x - 9, 44, x + 9, 62], fill=(190, 184, 172, 255))
        return img

    def _header(self):
        self.sub_img = _Txt(self.subtitle, 40, (123, 138, 153), "Regular", self.TITLE) if self.subtitle else None
        lines, size = self._fit_title(self.TITLE, self.TITLE_W, 88, 60, 70)
        self.title_imgs = [_Txt(ln, size, self.BLUE, self.TITLE_W, self.TITLE) for ln in lines]
        self.sub_y = 160
        y = self.sub_y + (84 if (self.sub_img or self.level) else 30)
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.1)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 34
        self.badge = self._badge(self.RED, (255, 255, 255), 26)
        self.tag_img = _ar_img(self.tag, 40, (123, 138, 153), self.ar_font) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h + 18
        self.wave_y = self.bar_y + 6
        self.p_top = self.band_h + 64
        self._apply_brand(self.BLUE, (123, 138, 153), 24)

    def _band_layer(self, img):
        self._put_sub_line(img, self.sub_y)
        d = ImageDraw.Draw(img)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        if self.title_imgs:  # a red pen underline under the title
            y = self.title_ys[-1] + 16
            w = min(self.width, self.title_imgs[-1].w + 20)
            pts = [(self.x0 + x, y + 4 * math.sin(x / 38)) for x in range(0, int(w), 6)]
            d.line(pts, fill=self.RED + (255,), width=4, joint="curve")
        self._wave_track(img)

    def _decor(self, dd, x, yb, w, size):
        pass

    def _page_decor(self, base, k, baselines, lh, size):
        """Ruled lines under the text lines, all the way down the page."""
        d = ImageDraw.Draw(base)
        if not baselines:
            return
        y = baselines[0] + size * 0.16
        while y - lh > self.wave_y + self.WAVE_H + 14:
            y -= lh
        while y < H:
            d.line([(0, y), (W, y)], fill=(198, 216, 236, 255), width=2)
            y += lh
        d.line([(62, self.wave_y + self.WAVE_H + 4), (62, H)], fill=(240, 150, 150, 255), width=3)

    def _make_mark(self, sp):
        """A hand-drawn red ring around the words (drawn as it is read)."""
        size = sp["size"]
        cx, cy = (sp["x"] + sp["x2"]) / 2, sp["yb"] - size * 0.28
        rx, ry = (sp["x2"] - sp["x"]) / 2 + 14, size * 0.62
        rng = np.random.default_rng(sp["i0"] + 11)
        a0 = -2.4
        pts = []
        for k in range(46):
            a = a0 + (2 * math.pi + 0.5) * k / 45
            wob = 1 + rng.uniform(-0.03, 0.03)
            pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a) + (k / 45) * 4))
        return pts

    def _draw_mark(self, frame, pts, q):
        part = _partial(pts, ease_io(min(1.0, q * 1.25)))
        if len(part) > 1:
            ImageDraw.Draw(frame).line(part, fill=self.RED + (255,), width=4, joint="curve")

    def _fly_back(self, t, z, S):
        a = t.im.getchannel("A")
        sh = Image.new("RGBA", t.im.size, (0, 0, 0, 0))
        sh.paste((0, 0, 0, 70), (0, 10 * S), a)
        return sh.filter(ImageFilter.GaussianBlur(6 * S))

    # sticky notes, three columns
    def _burst(self, frame, s, tau):
        """Pen doodles round the note: little strokes shooting out, and two stars."""
        x, y, nw, nh = s["note"]
        cx, cy = x + nw / 2, y + nh / 2
        p = _ease_out(tau / 0.45)
        fade_ = 1 - prog(tau, 0.45, 0.8)
        if fade_ <= 0:
            return
        col = self.RED + (int(255 * fade_),)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        rx, ry = nw / 2 + 18, nh / 2 + 16
        for k in range(8):  # strokes from the note's edge outward
            a = 2 * math.pi * k / 8 + 0.3
            ex, ey = math.cos(a), math.sin(a)
            r0 = 1.0 + 0.08 * p
            r1 = r0 + 0.32 * p
            d.line([(cx + ex * rx * r0, cy + ey * ry * r0), (cx + ex * rx * r1, cy + ey * ry * r1)], fill=col,
                   width=4)
        for k, (sx, sy) in enumerate(((x - 14, y + 6), (x + nw + 12, y + nh - 10))):  # two outline stars
            r = 14 * p
            pts = []
            for j in range(11):
                a = -math.pi / 2 + j * math.pi / 5
                rr = r if j % 2 == 0 else r * 0.45
                pts.append((sx + rr * math.cos(a), sy + rr * math.sin(a)))
            d.line(pts, fill=col, width=3, joint="curve")
        frame.alpha_composite(ov)

    def _note_h(self, n, size):
        return max(128, min(186, int(size * 2.9)))

    def _bank_h(self, n, size=None):
        if n == 0:
            return 0
        rows = (n + 2) // 3
        return 52 + 70 + rows * self._note_h(n, size or self.size) + (rows - 1) * 22

    def _bank_rows(self, img, keys, top, size=None, avail=None, label=None):
        n = len(keys)
        rows = (n + 2) // 3
        nh = self._note_h(n, size or self.size)
        if avail:
            nh = max(120, min(220, (avail - 70 - (rows - 1) * 22) // max(1, rows)))
        lab = _Txt((label or self.bank_label) + ":", 46, self.RED, self.TITLE_W, self.TITLE)
        lab.put(img, self.x0, top + 40)
        ar = _ar_img(self.bank_label_ar, 40, self.RED, self.ar_font)
        if lab.w + ar.width + 40 < self.width:
            _comp(img, ar, self.x1 - ar.width, top + 40 - int(ar.height * 0.64))
        gap = 22
        nw = (self.width - 2 * gap) // 3
        slots = []
        for j, gi in enumerate(keys):
            g = self.groups[gi]
            r, c = divmod(j, 3)
            x = self.x0 + c * (nw + gap)
            y = top + 70 + r * (nh + gap)
            en_size = int(min(54, nh * 0.3))
            en = _Txt(g["text"], en_size, self.BLUE, self.W_KEY, self.BODY)
            if en.w > nw - 24:
                en = _Txt(g["text"], max(24, int(en_size * (nw - 24) / en.w)), self.BLUE, self.W_KEY, self.BODY)
            ar_im = _ar_fit(g["ar"], en_size + 2, self.RED, self.ar_font, nw - 24) if g["ar"] else None
            base = y + int(nh * 0.42)
            slots.append(dict(gi=gi, j=j, note=(x, y, nw, nh), y=y, h=nh, base=base, en=en,
                              en_x=x + (nw - en.w) / 2, en_size=en.size, num_x=x + nw - 22,
                              ar=ar_im, ar_x=x + (nw - (ar_im.width if ar_im is not None else 0)) / 2,
                              ar_y=y + int(nh * 0.5)))
        return slots

    def _note(self, s, q, check):
        """The sticky note with its word, the Arabic revealed q, a tick when checked (then rotated)."""
        x, y, nw, nh = s["note"]
        key = ("note", s["gi"], round(q, 2), check, s["y"])
        if key in self._misc:
            return self._misc[key]
        pad = 24
        im = Image.new("RGBA", (nw + 2 * pad, nh + 2 * pad), (0, 0, 0, 0))
        im = Image.alpha_composite(im, _shadow_box(im.size, (pad + 4, pad + 6, pad + nw - 2, pad + nh), 3, 9, 80, 6))
        d = ImageDraw.Draw(im)
        col = NOTE_COLS[s["j"] % len(NOTE_COLS)]
        d.rectangle([pad, pad, pad + nw, pad + nh], fill=col + (255,))
        d.rectangle([pad, pad, pad + nw, pad + 18], fill=_mix(col, (0, 0, 0), 0.06) + (255,))  # glue strip
        s["en"].put(im, pad + s["en_x"] - x, pad + s["base"] - y)
        if s["ar"] is not None and q > 0:
            self._put_ar(im, s["ar"], int(pad + s["ar_x"] - x), int(pad + s["ar_y"] - y), q)
        if check:
            tk = _pen_tick(22, self.RED, 4)
            _comp(im, tk, pad + nw - tk.width - 6, pad + 6)
        im = im.rotate(NOTE_ROT[s["j"] % len(NOTE_ROT)], Image.BICUBIC, expand=False)
        if q in (0.0, 1.0):
            self._misc[key] = im
        return im

    def _draw_slot(self, frame, s, t, t_land, recap):
        """The sticky note slaps on: pops in, squashes against the page, springs back."""
        x, y, nw, nh = s["note"]
        q = ease_io(prog(t, t_land + 0.12, t_land + 0.12 + REVEAL))
        c = self._check_at(s["gi"])
        im = self._note(s, q, c is not None and t >= c + 0.1)
        if recap:
            sx = sy = ease_out_back(prog(t, t_land - 0.08, t_land + 0.3))
        else:
            sc = _ease_out(prog(t, t_land - 0.1, t_land + 0.05)) * 0.12 + 0.88
            d = _spring(t - t_land) if t - t_land < 0.9 else 0.0
            sx, sy = sc * (1 + 0.10 * d), sc * (1 - 0.09 * d)
        if abs(sx - 1) > 0.004 or abs(sy - 1) > 0.004:
            im = im.resize((max(1, int(im.width * sx)), max(1, int(im.height * sy))), Image.BILINEAR)
        _comp(frame, _fade(im, min(1.0, prog(t, t_land - 0.1, t_land + 0.05))),
              int(x + nw / 2 - im.width / 2), int(y + nh / 2 - im.height / 2))

    def _mark_sound(self, mx, t):
        mx.add(t, mx.scribble(0.35), 0.05)
