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
from ..core import (DEFAULT_FONT, H, ROOT, W, draw_ending, ease_io, ease_out_back, get_font, global_fade,
                    parse_lines, prog, text_img_in)

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
BANDS = {"teal": (15, 110, 116), "navy": (30, 52, 98), "maroon": (128, 34, 46), "forest": (34, 96, 62),
         "plum": (88, 54, 128), "slate": (52, 64, 78)}
BAND_CHOICES = [("Teal", "teal"), ("Navy", "navy"), ("Maroon", "maroon"), ("Forest green", "forest"),
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
TURN = 0.6                  # page turn
FLY = 0.85                  # word flight
REVEAL = 0.6                # Arabic writes in
ENDING_LEN = 4.5

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
        "band": "teal",
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
    im = text_img_in(font, txt, int(size), col, "Bold", shadow=False)
    box = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
    return im.crop((max(0, box[0] - 4), 0, min(im.width, box[2] + 4), im.height))


def _ar_fit(txt, size, col, font, max_w, min_size=24):
    im = _ar_img(txt, size, col, font)
    if im.width > max_w:
        im = _ar_img(txt, max(min_size, int(size * max_w / im.width)), col, font)
    return im


def _ar_wrap(txt, size, col, font, max_w):
    """Arabic paragraph -> line images (right-to-left, greedy by width)."""
    lines, cur = [], ""
    for w in txt.split():
        test = (cur + " " + w).strip()
        if cur and _ar_img(test, size, col, font).width > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return [_ar_img(ln, size, col, font) for ln in lines]


def _marker(w, h, col, seed):
    """A highlighter stroke: slightly uneven edges, rounded ends."""
    rng = np.random.default_rng(seed)
    S = 2
    im = Image.new("RGBA", (int(w * S), int(h * S)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = [(x, rng.uniform(0, h * 0.10) * S) for x in np.linspace(0, w * S, 7)]
    bot = [(x, h * S - rng.uniform(0, h * 0.12) * S) for x in np.linspace(w * S, 0, 7)]
    d.polygon(top + bot, fill=tuple(col) + (232,))
    d.ellipse([-h * 0.25 * S, 0, h * 0.25 * S, h * S], fill=tuple(col) + (232,))
    d.ellipse([w * S - h * 0.25 * S, 0, w * S + h * 0.25 * S, h * S], fill=tuple(col) + (232,))
    return im.resize((int(w), int(h)), Image.LANCZOS)


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


def make_video(project):
    """The video object for the project's design (`text.style`)."""
    style = (project.get("text", {}) or {}).get("style") or "textbook"
    return {"studio": StudioVideo, "exam": ExamVideo, "notebook": NotebookVideo}.get(style, TextVideo)(project)


# ================================================================== the reading engine (+ the Textbook design)
class TextVideo:
    BODY = SERIF                # paragraph font, its weights for plain / highlighted words
    W_REG, W_KEY = "Regular", "SemiBold"
    LINE = 1.66                 # line height / text size
    MARK_ON_TOP = False         # the word mark is drawn over the ink (pen) or under it (highlighter, glow)
    FINISH_EXTRA = 0.0          # extra time after the ticks for a design's last flourish
    TURN_STYLE = "slide"
    MIN_SIZE = 44               # smallest comfortable reading size on a phone (longer texts get more pages)
    GAP_MAX = 2.0               # widest justified word gap (in spaces) before a page takes a smaller size

    def __init__(self, project):
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
        self._wcache, self._brk = {}, {}
        self._fly_imgs, self._misc = {}, {}

        self._style(d)
        self.width = self.x1 - self.x0
        self._header()
        self._paginate()
        self._timeline()
        self.bg = self._background()
        self.line_base = [0]
        for idx, z in zip(self.page_words, self.page_size):
            self.line_base.append(self.line_base[-1] + len(self._break(idx, z)))
        self.key_line = {}
        self.pages = [self._build_page(k) for k in range(len(self.page_words))]
        if self.recap:
            self.pages.append(self._build_recap())
        self.tr = self._build_translation() if self.translation else None

        ending_q = parse_lines(e.get("question", ""), ["white", "gold"])
        self.has_ending = bool(e.get("intro") or ending_q or e.get("cta"))
        self.ending = (e.get("intro", ""), ending_q, e.get("cta", ""), s.get("handle", ""))
        dur = self.E + (ENDING_LEN if self.has_ending else 0.5)
        if self.audio:
            try:
                last = self.lead + audio_length(self.audio) + self.shifts[-1] + 0.3
                dur = max(dur, last + (ENDING_LEN if self.has_ending else 0.5))
            except Exception:
                pass
        self.base_duration = self.dur = dur
        self.silences = []
        self.cover_time = min(self.done, self.E - 0.2)

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

    def _background(self):
        return _noise_bg(_vgrad(PAPER_TOP, PAPER_BOT))

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
        lines, size = self._fit_title(SERIF, "ExtraBold", 66, 48, 56)
        self.title_imgs = [_Txt(ln, size, (255, 255, 255), "ExtraBold") for ln in lines]
        self.sub_y = 182
        y = self.sub_y + (84 if (self.sub_img or self.level) else 30)
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.18)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 56
        self.badge = self._badge((255, 255, 255), self.band)
        self.tag_img = _ar_img(self.tag, 36, light) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h + 34
        self.p_top = self.band_h + 92

    def _drop_tag_if_crowded(self):
        used = (self.sub_img.w if self.sub_img else 0) + (self.badge.width + 24 if self.badge is not None else 0)
        if self.tag_img and used + self.tag_img.width + 40 > self.width:
            self.tag_img = None

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
        d.rectangle([0, 0, W, self.band_h], fill=self.band + (255,))
        sh = Image.new("RGBA", (W, 26), (0, 0, 0, 0))  # soft shadow under the band
        sd = ImageDraw.Draw(sh)
        for y in range(26):
            sd.line([(0, y), (W, y)], fill=(0, 0, 0, int(34 * (1 - y / 26) ** 2)))
        img.alpha_composite(sh, (0, self.band_h))
        self._put_sub_line(img, self.sub_y)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        d.rounded_rectangle([self.x0, self.bar_y, self.x1, self.bar_y + 8], 4, fill=(228, 231, 226, 255))

    def _draw_progress(self, frame, p):
        if p > 0:
            ImageDraw.Draw(frame).rounded_rectangle([self.x0, self.bar_y, self.x0 + max(8, self.width * p),
                                                     self.bar_y + 8], 4, fill=self.band + (255,))

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
        mx, my, im = mk
        w = max(1, int(im.width * ease_io(q)))
        _comp(frame, im.crop((0, 0, w, im.height)), mx, my)

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
        k = (i, size)
        if k not in self._wcache:
            self._wcache[k] = _font(size, self._wweight(i), self.BODY).getlength(self.words[i]["w"])
        return self._wcache[k]

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

    def _pw(self, i, a, b, hyph, size):
        """Width of the piece w[a:b] (+ '-') of word i."""
        k = (i, a, b, hyph, size)
        if k not in self._wcache:
            w = self.words[i]["w"]
            self._wcache[k] = _font(size, self._wweight(i), self.BODY).getlength(w[a:b] + ("-" if hyph else ""))
        return self._wcache[k]

    def _break(self, idx, size):
        """Lines of word pieces (i, a, b, hyphen?) with the fewest lines and then the most even right edge (sum of
        squared gaps), like book typesetting. A word may be split at a line end (hyphenation, which costs a little,
        so whole words are preferred); the last line may be short but not a lone short word."""
        key = (tuple(idx), size)
        if key in self._brk:
            return self._brk[key]
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        width = self.width
        n = len(idx)
        pts = []  # breakpoints: (word position, char offset, hyphen) ; offset 0 = before the word
        for p, i in enumerate(idx):
            pts.append((p, 0, False))
            pts += [(p, c, h) for c, h in self._splits(i)]
        pts.append((n, 0, False))
        best = [math.inf] * len(pts)
        prev = [0] * len(pts)
        best[0] = 0.0
        for bj in range(1, len(pts)):
            pj, cj, hj = pts[bj]
            for bi in range(bj - 1, -1, -1):
                pi, ci, _ = pts[bi]
                if best[bi] == math.inf or (pi == pj):
                    continue
                # pieces: rest of word pi from ci, whole words between, the start of word pj up to cj
                lw = self._pw(idx[pi], ci, len(self.words[idx[pi]]["w"]), False, size)
                for p in range(pi + 1, min(pj, n)):
                    lw += sp + self._ww(idx[p], size)
                if cj and pj < n:
                    lw += sp + self._pw(idx[pj], 0, cj, hj, size)
                count = (pj - pi) + (1 if cj else 0)
                if lw > width:
                    if count > 1:
                        break
                last = bj == len(pts) - 1
                if last:
                    bad = 0.0 if (count > 1 or lw > width * 0.35 or n == 1) else 4000.0
                elif count == 1:
                    bad = 30000.0
                else:  # extra space per gap, in spaces, squared (TeX-like): even lines, no rivers
                    r = max(0.0, width - lw) / (count - 1) / sp
                    bad = 100.0 * r * r + (260.0 if cj else 0.0)  # a broken word costs a little
                c = best[bi] + bad + 100000.0
                if c < best[bj]:
                    best[bj], prev[bj] = c, bi
        lines, bj = [], len(pts) - 1
        while bj > 0:
            bi = prev[bj]
            (pi, ci, _), (pj, cj, hj) = pts[bi], pts[bj]
            line = [(idx[pi], ci, len(self.words[idx[pi]]["w"]), False)]
            line += [(idx[p], 0, len(self.words[idx[p]]["w"]), False) for p in range(pi + 1, min(pj, n))]
            if cj and pj < n:
                line.append((idx[pj], 0, cj, hj))
            lines.append(line)
            bj = bi
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

    def _pack(self, size):
        pages, cur = [], []
        for sent in self._units():
            if self._fits(cur + sent, size):
                cur = cur + sent
                continue
            if cur:
                pages.append(cur)
                cur = []
            if self._fits(sent, size):
                cur = list(sent)
                continue
            for atom in self._atoms(sent):  # a sentence longer than a page: split it between words
                if self._fits(cur + atom, size):
                    cur = cur + atom
                else:
                    if cur:
                        pages.append(cur)
                    cur = list(atom)
        return pages + ([cur] if cur else [])

    def _paginate(self):
        best = None
        for size in [z for z in SIZES if z >= self.MIN_SIZE] or [SIZES[-1]]:
            pages = self._pack(size)
            if best is None or len(pages) < len(best[1]):
                best = (size, pages)
        self.size, self.page_words = best
        # each page then takes the biggest size that fits it (at most 15 % bigger, so the pages still match) and
        # whose justified lines keep tight word gaps (a book page, not rivers of white)
        self.page_size = [self._page_size(idx) for idx in self.page_words]
        self.gsize = {}
        for idx, z in zip(self.page_words, self.page_size):
            for gi in self._keys_in(idx):
                self.gsize[gi] = z
        avail = SAFE_BOTTOM - self.p_top  # leftover space: half above the text (a calmer, centred page)
        self.page_off = [min(230, max(0, (avail - self._need(idx, z)) // 2))
                         for idx, z in zip(self.page_words, self.page_size)]
        self.recap = len(self.page_words) > 1 and len(self.groups) > 0

    TRACK_MAX = 0.035           # letter-spacing a justified line may add, x text size

    def _justify(self, line, size, last):
        """(gap, tracking) of a line: slack goes first into a little letter-spacing (at most TRACK_MAX of the
        size, at most half the slack), the rest into the word gaps."""
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        if last or len(line) < 2:
            return sp, 0.0
        widths = sum(self._pw(*pc, size) for pc in line)
        slack = max(0.0, self.width - widths - sp * (len(line) - 1))
        chars = sum(max(0, b - a + (1 if h else 0) - 1) for _, a, b, h in line)
        track = min(self.TRACK_MAX * size, slack * 0.5 / chars) if chars else 0.0
        return sp + (slack - track * chars) / (len(line) - 1), track

    def _gap_ratio(self, idx, size):
        """The widest justified word gap of a page, in spaces."""
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        lines = self._break(idx, size)
        return max([1.0] + [self._justify(ln, size, False)[0] / sp for ln in lines[:-1] if len(ln) > 1])

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
                self.fly0[gi] = max(self.ve[g["i1"]], self.vs[g["i0"]] + 0.3) + 0.05
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
        idx = self.page_words[k]
        size = self.page_size[k]
        lh = int(size * self.LINE)
        base = self.bg.copy()
        self._band_layer(base)
        ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd, di = ImageDraw.Draw(base), ImageDraw.Draw(ink)
        lines = self._break(idx, size)
        top = self.p_top + self.page_off[k]
        sp = _font(size, self.W_REG, self.BODY).getlength(" ")
        boxes, pieces, spans, baselines = {}, [], [], []
        for li, line in enumerate(lines):
            gap, track = self._justify(line, size, li == len(lines) - 1)  # justified: every line but the last
            widths = [self._pw(i, a, b, h, size) + track * max(0, b - a + (1 if h else 0) - 1) for i, a, b, h in line]
            x = float(self.x0)
            yb = top + li * lh + int(size * 1.05)
            baselines.append(yb)
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
                box = (int(x) - 2, int(yb - asc - 4), int(math.ceil(x + w)) + 2, int(yb + desc + 4))
                boxes.setdefault(i, box)  # the flight starts from the word's first piece
                f0, f1 = a / len(word), (b / len(word) if b < len(word) else 1.0)
                pieces.append(dict(i=i, box=box, f0=f0, f1=f1))
                if key:
                    self._decor(dd, x, yb, w, size)
                    gi = self.key_of[i]
                    self.key_line.setdefault(gi, self.line_base[k] + li + 1)
                    if spans and spans[-1]["gi"] == gi and spans[-1]["li"] == li:
                        spans[-1].update(i1=i, f1=f1, x2=x + w)  # a phrase on one line = one mark
                    else:
                        spans.append(dict(gi=gi, li=li, i0=i, i1=i, f0=f0, f1=f1, x=x, x2=x + w, yb=yb, size=size))
                x += w + gap
        for s in spans:
            s["mk"] = self._make_mark(s)
        self._page_decor(base, k, baselines, lh, size)
        para_box = (self.x0 - 16, top, self.x1 + 16, top + len(lines) * lh + 12)
        keys = self._keys_in(idx)
        slots = self._bank_rows(base, keys, para_box[3] + 52, size=size) if keys else []
        ink_c = ink.crop(para_box)
        return dict(kind="text", k=k, idx=idx, base=base, ink_rgb=ink_c.convert("RGB"), ink_a=ink_c.getchannel("A"),
                    box=para_box, boxes=boxes, pieces=pieces, spans=spans, slots=slots, keys=keys, size=size)

    def _build_recap(self):
        base = self.bg.copy()
        self._band_layer(base)
        keys = list(range(len(self.groups)))
        n = len(keys)
        slots = self._bank_rows(base, keys, self.p_top + 10, avail=SAFE_BOTTOM - self.p_top - 10,
                                label=f"{self.bank_label} · {n}")
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
            num = _Txt(str(j + 1), max(26, int(en_size * 0.6)), self.bank_col, "Bold", LABEL)
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
        pop = 1.0 if recap else 1 + 0.12 * (1 - ease_out_back(prog(t, t_land, t_land + 0.3)))
        if abs(pop - 1) > 0.005:
            im = s["en"].im.resize((int(s["en"].im.width * pop), int(s["en"].im.height * pop)), Image.BILINEAR)
            _comp(frame, im, int(s["en_x"] - s["en"].pad * pop), int(s["base"] - s["en"].base * pop))
        else:
            s["en"].put(frame, s["en_x"], s["base"], prog(t, t_land, t_land + 0.25) if recap else 1.0)

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
            t = _Txt(g["text"], z * S, self.en_col, self.W_KEY, self.BODY)
            t.pad += pad  # room around the text for the shadow / glow
            big = Image.new("RGBA", (t.im.width + 2 * pad, t.im.height + 2 * pad), (0, 0, 0, 0))
            big.alpha_composite(t.im, (pad, pad))
            t.im, t.base = big, t.base + pad
            back = self._fly_back(t, z, S)
            self._fly_imgs[gi] = (back, t.im, (t.pad, t.base), S)
        return self._fly_imgs[gi]

    def _draw_flight(self, frame, pg, gi, u):
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
        if pa > 0.01:
            lay = Image.alpha_composite(_fade(back.resize(size, Image.BILINEAR), pa), lay)
        ox, oy = ax * k, ay * k
        if abs(rot) > 0.2:
            cx, cy = lay.width / 2, lay.height / 2
            lay = lay.rotate(rot, Image.BICUBIC, expand=True)
            a = math.radians(rot)
            dx, dy = ox - cx, oy - cy
            ox = lay.width / 2 + dx * math.cos(a) + dy * math.sin(a)
            oy = lay.height / 2 - dx * math.sin(a) + dy * math.cos(a)
        _comp(frame, lay, int(round(x - ox)), int(round(y - oy)))

    # -------------------------------------------------------------- translation of the whole paragraph
    def _build_translation(self):
        p = self.panel
        top, bottom = self.p_top - 10, SAFE_BOTTOM - 20
        x0, x1 = self.x0 - 16, self.x1 + 16
        size = 52
        while True:
            lines = _ar_wrap(self.translation, size, p["text"], p["font"], x1 - x0 - 72)
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
            frame = self._turn(a, b, ease_io(prog(t, self.turns[k], self.turns[k] + TURN)))
        else:
            frame = self._draw_page(k, t)
        if t < 0.9:
            frame = self._intro(frame, t)
        if self.tr is not None and t >= self.tr0:
            self._draw_translation(frame, t)
        if self.has_ending:
            draw_ending(frame, t, self.E, *self.ending, self.accent)
        global_fade(frame, t, self.dur, fade_in=False)
        return frame.convert("RGB")

    def _turn(self, a, b, e):
        """Page turn: the old page slides away to the left, the new one comes in from the right."""
        cut = self.bar_y + 20  # the header stays; the page below it slides
        if self.TURN_STYLE == "fade":  # the old page fades out, then the new one fades in (never both at once)
            frame = (b if e >= 0.5 else a).copy()
            frame.paste(self.bg.crop((0, cut, W, H)), (0, cut))
            if e < 0.5:
                _comp(frame, _fade(a.crop((0, cut, W, H)), 1 - 2 * e), 0, cut - int(30 * 2 * e))
            else:
                _comp(frame, _fade(b.crop((0, cut, W, H)), 2 * e - 1), 0, cut + int(30 * (2 - 2 * e)))
            return frame
        frame = b.copy()
        frame.paste(self.bg.crop((0, cut, W, H)), (0, cut))
        off = int(round(e * W))
        frame.alpha_composite(a.crop((off, cut, W, H)), (0, cut))
        if off > 0:
            shade = Image.new("RGBA", (40, H - cut), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shade)
            for x in range(40):
                sd.line([(x, 0), (x, H)], fill=(0, 0, 0, int(60 * (x / 40) ** 2)))
            bx = W - off
            frame.alpha_composite(b.crop((bx, cut, W, H)), (bx, cut))
            _comp(frame, shade, bx - 40, cut)
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
        if not self.MARK_ON_TOP:
            for sp in pg["spans"]:
                q = self._span_q(sp, t)
                if q > 0:
                    self._draw_mark(frame, sp["mk"], q)
        # read-along ink: every spoken word, the current one wiping in left to right
        bx0, by0, bx1, by1 = pg["box"]
        mask = Image.new("L", (bx1 - bx0, by1 - by0), 0)
        md = ImageDraw.Draw(mask)
        any_ink = False
        for pc in pg["pieces"]:
            i = pc["i"]
            if t < self.vs[i]:
                break
            x0, y0, x1, y1 = pc["box"]
            q = prog(t, self._wt(i, pc["f0"]), self._wt(i, pc["f1"]))
            if q <= 0:
                break
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
            any_ink = True
        if any_ink:
            frame.paste(pg["ink_rgb"], (bx0, by0), ImageChops.multiply(mask, pg["ink_a"]))
        if self.MARK_ON_TOP:
            for sp in pg["spans"]:
                q = self._span_q(sp, t)
                if q > 0:
                    self._draw_mark(frame, sp["mk"], q)
        for s in pg["slots"]:
            t_land = self.fly0[s["gi"]] + FLY
            if t >= t_land:
                self._draw_slot(frame, s, t, t_land, False)
        for gi in pg["keys"]:
            u = prog(t, self.fly0[gi], self.fly0[gi] + FLY)
            if 0 < u < 1:
                self._draw_flight(frame, pg, gi, u)
        if not self.recap and k == len(self.page_words) - 1:
            self._draw_final(frame, pg, t)
        return frame

    def _slot_of(self, pg, gi):
        return next(s for s in pg["slots"] if s["gi"] == gi)

    # -------------------------------------------------------------- sound (shared)
    def _mark_sound(self, mx, t):
        pass

    def sound(self, mx):
        mx.intro(0.05)
        mx.add(0.05, mx.paper(), 0.45)
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
    BODY = LABEL
    MIN_SIZE = 40               # a sans-serif reads bigger
    W_REG, W_KEY = "Medium", "Bold"
    LINE = 1.7
    GOLD, BLUE = (246, 197, 96), (122, 162, 255)

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
        lines, size = self._fit_title(DISPLAY, "Regular", 78, 52, 62)
        self.title_imgs = [_Txt(ln, size, (255, 255, 255), "Regular", DISPLAY) for ln in lines]
        self.sub_y = 186
        y = self.sub_y + (92 if (self.sub_img or self.level) else 40)
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.2)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 36
        self.badge = self._badge(self.GOLD, (12, 16, 36))
        self.tag_img = _ar_img(self.tag, 36, (142, 166, 255), DEFAULT_FONT) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h + 24
        self.p_top = self.band_h + 84

    def _band_layer(self, img):
        self._put_sub_line(img, self.sub_y)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle([self.x0, self.bar_y, self.x1, self.bar_y + 6], 3, fill=(255, 255, 255, 34))
        img.alpha_composite(ov)

    def _draw_progress(self, frame, p):
        if p <= 0:
            return
        if "grad" not in self._misc:
            g = np.linspace(0, 1, self.width)[None, :, None]
            arr = np.array(self.BLUE, np.float32) * (1 - g) + np.array(self.GOLD, np.float32) * g
            self._misc["grad"] = Image.fromarray(np.repeat(arr, 6, axis=0).astype(np.uint8)).convert("RGBA")
        w = max(6, int(self.width * p))
        _comp(frame, self._misc["grad"].crop((0, 0, w, 6)), self.x0, self.bar_y)

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
        ar = _ar_img(self.bank_label_ar, 34, self.bank_col, DEFAULT_FONT)
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
            ar_im = _ar_fit(g["ar"], en_size + 2, self.GOLD, DEFAULT_FONT, w - 56) if g["ar"] else None
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
    BODY = SERIF
    W_REG, W_KEY = "Regular", "Bold"
    LINE = 1.62
    MARK_ON_TOP = True
    FINISH_EXTRA = 0.7
    TURN_STYLE = "fade"
    RED, BLUE = (200, 38, 28), (31, 79, 163)
    SHEET = (36, 40, 1044, 1700)

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
        lines, size = self._fit_title(SERIF, "Bold", 60, 44, 50)
        self.title_imgs = [_Txt(ln, size, (17, 17, 17), "Bold") for ln in lines]
        self.sub_y = 150
        y = self.sub_y + 76
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.18)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 34
        self.badge = self._badge((30, 30, 30), (255, 255, 255), 24)
        self.tag_img = _ar_img(self.tag, 32, (110, 110, 110), PLEX_AR) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h
        self.p_top = self.band_h + 60

    def _band_layer(self, img):
        self._put_sub_line(img, self.sub_y)
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, self.x0, y)
        ImageDraw.Draw(img).rectangle([self.x0, self.bar_y, self.x1, self.bar_y + 4], fill=(222, 219, 212, 255))

    def _draw_progress(self, frame, p):
        if p > 0:
            ImageDraw.Draw(frame).rectangle([self.x0, self.bar_y, self.x0 + max(4, self.width * p), self.bar_y + 4],
                                            fill=(22, 22, 22, 255))

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
    BODY = HAND
    MIN_SIZE = 52               # handwriting reads smaller than print
    W_REG, W_KEY = "Regular", "Regular"
    LINE = 1.5
    MARK_ON_TOP = True
    BLUE, RED = (31, 59, 115), (208, 52, 44)

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
        self.sub_img = _Txt(self.subtitle, 40, (123, 138, 153), "Regular", HAND) if self.subtitle else None
        lines, size = self._fit_title(HAND, "Regular", 88, 60, 70)
        self.title_imgs = [_Txt(ln, size, self.BLUE, "Regular", HAND) for ln in lines]
        self.sub_y = 160
        y = self.sub_y + (84 if (self.sub_img or self.level) else 30)
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.1)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 34
        self.badge = self._badge(self.RED, (255, 255, 255), 26)
        self.tag_img = _ar_img(self.tag, 40, (123, 138, 153), RUQAA) if self.tag else None
        self._drop_tag_if_crowded()
        self.bar_y = self.band_h + 18
        self.p_top = self.band_h + 64

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
        d.line([(self.x0, self.bar_y), (self.x1, self.bar_y)], fill=(222, 228, 236, 255), width=5)

    def _draw_progress(self, frame, p):
        if p > 0:
            ImageDraw.Draw(frame).line([(self.x0, self.bar_y), (self.x0 + max(5, self.width * p), self.bar_y)],
                                       fill=self.BLUE + (255,), width=5)

    def _decor(self, dd, x, yb, w, size):
        pass

    def _page_decor(self, base, k, baselines, lh, size):
        """Ruled lines under the text lines, all the way down the page."""
        d = ImageDraw.Draw(base)
        if not baselines:
            return
        y = baselines[0] + size * 0.16
        while y - lh > self.bar_y + 30:
            y -= lh
        while y < H:
            d.line([(0, y), (W, y)], fill=(198, 216, 236, 255), width=2)
            y += lh
        d.line([(62, self.bar_y + 10), (62, H)], fill=(240, 150, 150, 255), width=3)

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
        lab = _Txt((label or self.bank_label) + ":", 46, self.RED, "Regular", HAND)
        lab.put(img, self.x0, top + 40)
        ar = _ar_img(self.bank_label_ar, 40, self.RED, RUQAA)
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
            en = _Txt(g["text"], en_size, self.BLUE, "Regular", HAND)
            if en.w > nw - 24:
                en = _Txt(g["text"], max(24, int(en_size * (nw - 24) / en.w)), self.BLUE, "Regular", HAND)
            ar_im = _ar_fit(g["ar"], en_size + 2, self.RED, RUQAA, nw - 24) if g["ar"] else None
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
        x, y, nw, nh = s["note"]
        q = ease_io(prog(t, t_land + 0.12, t_land + 0.12 + REVEAL))
        c = self._check_at(s["gi"])
        im = self._note(s, q, c is not None and t >= c + 0.1)
        sc = ease_out_back(prog(t, t_land - 0.08, t_land + 0.3))
        if sc < 0.995:
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
        _comp(frame, _fade(im, min(1.0, prog(t, t_land - 0.08, t_land + 0.08))),
              int(x + nw / 2 - im.width / 2), int(y + nh / 2 - im.height / 2))

    def _mark_sound(self, mx, t):
        mx.add(t, mx.scribble(0.35), 0.05)
