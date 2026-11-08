"""English Texts: a textbook paragraph read aloud (your recording, e.g. from ElevenLabs). The text inks in word by
word exactly as it is spoken; each highlighted word gets a marker swipe, then flies down into the Word Bank, where
its Arabic meaning writes itself in from right to left.

Words box (the project's `text.words`, same columns as the Excel tabs B-F, see engine/text_batch.py):
    word | start | end | highlighted | arabic
one spoken word per line, times in seconds in the recording. A line with something in `highlighted` flies into the
Word Bank (the highlighted text is what the bank shows; `*` = the word itself). Neighbouring lines with the same
several-word highlighted text (e.g. "chase away" on both lines) fly together as one phrase. Missing times are
estimated (then the words just follow a steady reading pace).

Long paragraphs are split into pages at sentence ends (the page turns, and the recording waits for it); with more
than one page a Word Bank recap of all the words closes the reading. Everything is laid out inside the Shorts safe
area (x 72-918, above y 1536). render(t) depends only on t (frames are drawn on several processes)."""
import math
import os
import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..audio import SR, audio_length, load_audio
from ..core import (H, ROOT, W, draw_ending, ease_io, ease_out_back, get_font, global_fade, parse_lines, prog,
                    text_img_in)

NAME = "English Texts"

_LIB = os.path.join(ROOT, "fonts", "library")


def _lib(*parts):
    path = os.path.join(_LIB, *parts)
    return path if os.path.isfile(path) else os.path.join(ROOT, "fonts", "Cairo.ttf")


SERIF = _lib("Literata", "Literata[opsz,wght].ttf")
AR_FONT = _lib("Amiri", "Amiri-Bold.ttf")
LABEL = _lib("Montserrat", "Montserrat[wght].ttf")

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

X0, X1 = 72, 918            # text column (clear of the Shorts buttons on the right)
WIDTH = X1 - X0
SAFE_BOTTOM = 1536          # the bottom 20 % is covered by the caption / channel name
SIZES = tuple(range(74, 35, -2))
LINE = 1.66                # line height / text size
TURN = 0.6                  # page turn
FLY = 0.85                  # word flight
REVEAL = 0.6                # Arabic writes in
ENDING_LEN = 4.5

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
        "reading_audio": "",
        "audio_gain": 1.0,
        "lead": 1.0,
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
        self.pad, self.base, self.w = pad, pad + asc, w

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


def _ar_img(txt, size, col=AR_COL):
    im = text_img_in(AR_FONT, txt, int(size), col, "Bold", shadow=False)
    box = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
    return im.crop((max(0, box[0] - 4), 0, min(im.width, box[2] + 4), im.height))


def _marker(w, h, col, seed):
    """A highlighter stroke: slightly uneven edges, rounded ends, a touch darker where it starts and ends."""
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


def _check(r, col):
    S = 3
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 2 * r * S - 1, 2 * r * S - 1], fill=tuple(col) + (255,))
    pts = [(0.52 * r * S, 1.02 * r * S), (0.86 * r * S, 1.38 * r * S), (1.5 * r * S, 0.66 * r * S)]
    d.line(pts, fill=(255, 255, 255, 255), width=int(0.22 * r * S), joint="curve")
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def _paper():
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr = np.array(PAPER_TOP, np.float32) * (1 - y) + np.array(PAPER_BOT, np.float32) * y
    arr = np.repeat(arr, W, axis=1)
    rng = np.random.default_rng(4)
    arr += rng.normal(0, 1.6, (H, W, 1)).astype(np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def _bezier(p0, p1, p2, p3, u):
    a = (1 - u) ** 3
    b = 3 * (1 - u) ** 2 * u
    c = 3 * (1 - u) * u ** 2
    d = u ** 3
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


# ------------------------------------------------------------------ the video
class TextVideo:
    def __init__(self, project):
        s = project.get("settings", {})
        d = project.get("text", {})
        e = project.get("ending", {})
        self.fps = int(s.get("fps", 30))
        self.band = BANDS.get(d.get("band") or "teal", BANDS["teal"])
        self.marker_col = MARKERS.get(d.get("marker") or "yellow", MARKERS["yellow"])
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

        self._header()
        self._paginate()
        self._timeline()
        self.paper = _paper()
        self.pages = [self._build_page(k) for k in range(len(self.page_words))]
        if self.recap:
            self.pages.append(self._build_recap())
        self._fly_imgs = {}
        self._check_imgs = {}

        ending_q = parse_lines(e.get("question", ""), ["white", "gold"])
        self.has_ending = bool(e.get("intro") or ending_q or e.get("cta"))
        self.ending = (e.get("intro", ""), ending_q, e.get("cta", ""), s.get("handle", ""))
        self.E = self.done + 1.8
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

    # -------------------------------------------------------------- layout
    def _header(self):
        """The coloured band: small line, title (1-2 lines) and the Arabic tag; sets self.band_h."""
        self.sub_img = _Txt(self.subtitle.upper(), 30, _mix(self.band, (255, 255, 255), 0.72), "Bold", LABEL,
                            track=0.16) if self.subtitle else None
        lines, size = [self.title], 66
        if self.title:
            while size > 48 and _font(size, "ExtraBold").getlength(self.title) > WIDTH:
                size -= 2
            if _font(size, "ExtraBold").getlength(self.title) > WIDTH:
                size = 56
                lines = self._wrap_plain(self.title, size, "ExtraBold", WIDTH)[:2]
        self.title_imgs = [_Txt(ln, size, (255, 255, 255), "ExtraBold") for ln in lines if ln]
        y = 182
        self.sub_y = y
        if self.title_imgs:
            y += 84 if self.sub_img else 30
        self.title_ys = []
        for _ in self.title_imgs:
            self.title_ys.append(y)
            y += int(size * 1.18)
        self.band_h = (self.title_ys[-1] if self.title_ys else y) + 56
        self.tag_img = _ar_img(self.tag, 36, _mix(self.band, (255, 255, 255), 0.72)) if self.tag else None
        if self.tag_img and self.sub_img and self.sub_img.w + self.tag_img.width + 40 > WIDTH:
            self.tag_img = None
        self.bar_y = self.band_h + 34
        self.p_top = self.band_h + 92

    @staticmethod
    def _wrap_plain(txt, size, weight, width):
        f = _font(size, weight)
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
        return "SemiBold" if i in self.key_of else "Regular"

    def _break(self, idx, size):
        """Greedy line breaking -> list of lines (lists of word indices)."""
        sp = _font(size).getlength(" ")
        lines, cur, x = [], [], 0.0
        for i in idx:
            w = _font(size, self._wweight(i)).getlength(self.words[i]["w"])
            if cur and x + sp + w > WIDTH:
                lines.append(cur)
                cur, x = [i], w
            else:
                x += (sp if cur else 0) + w
                cur.append(i)
        return lines + ([cur] if cur else [])

    def _row_h(self, n, size=None):
        cap = 108 if n <= 4 else 96 if n <= 6 else 80 if n <= 8 else 64
        return max(58, min(cap, int((size or self.size) * 1.6)))

    def _bank_h(self, n, size=None):
        return 0 if n == 0 else 64 + 82 + n * self._row_h(n, size)  # gap + header + rows

    def _need(self, idx, size):
        return len(self._break(idx, size)) * int(size * LINE) + self._bank_h(len(self._keys_in(idx)), size)

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
        for size in SIZES:
            pages = self._pack(size)
            if best is None or len(pages) < len(best[1]):
                best = (size, pages)
        self.size, self.page_words = best
        # each page then takes the biggest size that fits it (at most 15 % bigger, so the pages still match)
        self.page_size = [next((z for z in SIZES if z <= self.size * 1.15 and self._fits(idx, z)), self.size)
                          for idx in self.page_words]
        self.gsize = {}
        for idx, z in zip(self.page_words, self.page_size):
            for gi in self._keys_in(idx):
                self.gsize[gi] = z
        avail = SAFE_BOTTOM - self.p_top  # leftover space: half above the text (a calmer, centred page)
        self.page_off = [min(150, max(0, (avail - self._need(idx, z)) // 2))
                         for idx, z in zip(self.page_words, self.page_size)]
        self.recap = len(self.page_words) > 1 and len(self.groups) > 0

    # -------------------------------------------------------------- timing
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
                extra = max(0.0, turn + TURN + 0.3 - first)
                shift += extra
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
        self.done = (self.checks[-1] + 0.4) if n else self.reading_end
        self.first_t = self.vs[0]
        self.last_t = self.ve[-1]

    # -------------------------------------------------------------- pre-rendered pages
    def _band_layer(self, img):
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, self.band_h], fill=self.band + (255,))
        sh = Image.new("RGBA", (W, 26), (0, 0, 0, 0))  # soft shadow under the band
        sd = ImageDraw.Draw(sh)
        for y in range(26):
            sd.line([(0, y), (W, y)], fill=(0, 0, 0, int(34 * (1 - y / 26) ** 2)))
        img.alpha_composite(sh, (0, self.band_h))
        if self.sub_img:
            self.sub_img.put(img, X0, self.sub_y)
        if self.tag_img:
            _comp(img, self.tag_img, X1 - self.tag_img.width, int(self.sub_y - self.tag_img.height * 0.64))
        for im, y in zip(self.title_imgs, self.title_ys):
            im.put(img, X0, y)
        d.rounded_rectangle([X0, self.bar_y, X1, self.bar_y + 8], 4, fill=(228, 231, 226, 255))

    def _bank_rows(self, img, keys, top, rows_area=None, size=None, label="WORD BANK"):
        """Word Bank header + empty numbered rows; returns the slot geometry of each key."""
        d = ImageDraw.Draw(img)
        n = len(keys)
        row_h = rows_area or self._row_h(n, size)
        d.rectangle([X0, top, X1, top + 4], fill=self.band + (255,))
        ls = max(26, min(34, int(row_h * 0.34)))
        ar = _ar_img("بنك الكلمات", int(ls * 1.35), self.band)
        lab = _Txt(label, ls, self.band, "Bold", LABEL, track=0.18)
        while ls > 22 and lab.w + ar.width + 36 > WIDTH:  # a long label: smaller, so it never meets the Arabic
            ls -= 2
            lab = _Txt(label, ls, self.band, "Bold", LABEL, track=0.18)
        lab.put(img, X0, top + 52)
        if lab.w + ar.width + 36 <= WIDTH:
            _comp(img, ar, X1 - ar.width, top + 52 - int(ar.height * 0.64))
        en_size = int(min(48, row_h * 0.6))
        slots = []
        y = top + 82
        for j, gi in enumerate(keys):
            g = self.groups[gi]
            base = y + int(row_h * 0.66)
            num = _Txt(str(j + 1), max(26, int(en_size * 0.6)), self.band, "Bold", LABEL)
            num.put(img, X0, base)
            d.line([(X0, y + row_h - 1), (X1, y + row_h - 1)], fill=RULE + (255,), width=2)
            en = _Txt(g["text"], en_size, INK, "SemiBold")
            ar_im = _ar_img(g["ar"], en_size + 6) if g["ar"] else None
            if ar_im is not None and en.w + ar_im.width + 110 > WIDTH:
                ar_im = _ar_img(g["ar"], max(26, int((en_size + 6) * (WIDTH - 110 - en.w) / ar_im.width)))
            slots.append(dict(gi=gi, num_x=X0 + 15, y=y, h=row_h, base=base, en=en, en_x=X0 + int(en_size * 1.15), en_size=en_size,
                              ar=ar_im, ar_x=X1 - (ar_im.width if ar_im is not None else 0),
                              ar_y=base - int(ar_im.height * 0.64) if ar_im is not None else 0))
            y += row_h
        return slots

    def _build_page(self, k):
        idx = self.page_words[k]
        size = self.page_size[k]
        lh = int(size * LINE)
        base = self.paper.copy()
        self._band_layer(base)
        ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd, di = ImageDraw.Draw(base), ImageDraw.Draw(ink)
        faded_key = _mix(self.band, PAPER_TOP, 0.45)
        lines = self._break(idx, size)
        top = self.p_top + self.page_off[k]
        sp = _font(size).getlength(" ")
        boxes, marks = {}, {}
        for li, line in enumerate(lines):
            widths = [_font(size, self._wweight(i)).getlength(self.words[i]["w"]) for i in line]
            gap = sp
            last_line = li == len(lines) - 1
            if not last_line and len(line) > 1:
                extra = WIDTH - sum(widths) - sp * (len(line) - 1)
                if extra < WIDTH * 0.12:  # justified like a book page (not when it would leave big holes)
                    gap = sp + extra / (len(line) - 1)
            x = float(X0)
            yb = top + li * lh + int(size * 1.05)
            for j, (i, w) in enumerate(zip(line, widths)):
                f = _font(size, self._wweight(i))
                asc, desc = f.getmetrics()
                key = i in self.key_of
                dd.text((x, yb), self.words[i]["w"], font=f, fill=(faded_key if key else FADED) + (255,), anchor="ls")
                di.text((x, yb), self.words[i]["w"], font=f, fill=INK + (255,), anchor="ls")
                boxes[i] = (int(x) - 2, int(yb - asc - 4), int(math.ceil(x + w)) + 2, int(yb + desc + 4))
                if key:
                    for dx in range(0, int(w), 9):  # dotted underline: these words will fly
                        dd.ellipse([x + dx, yb + size * 0.2, x + dx + 3.4, yb + size * 0.2 + 3.4],
                                   fill=self.band + (255,))
                    g = self.groups[self.key_of[i]]
                    right = x + w
                    if i < g["i1"] and j + 1 < len(line):
                        right = x + w + gap  # a phrase: the marker runs on over the space
                    mh = int(size * 0.86)
                    marks[i] = (int(x - 7), int(yb - size * 0.66), _marker(right - x + 14, mh, self.marker_col, i))
                x += w + gap
        para_box = (X0 - 12, top, X1 + 12, top + len(lines) * lh + 12)
        keys = self._keys_in(idx)
        slots = self._bank_rows(base, keys, para_box[3] + 52, size=size) if keys else []
        ink_c = ink.crop(para_box)
        return dict(kind="text", idx=idx, base=base, ink_rgb=ink_c.convert("RGB"), ink_a=ink_c.getchannel("A"),
                    box=para_box, boxes=boxes, marks=marks, slots=slots, keys=keys)

    def _build_recap(self):
        base = self.paper.copy()
        self._band_layer(base)
        keys = list(range(len(self.groups)))
        n = len(keys)
        avail = SAFE_BOTTOM - self.p_top - 40 - 82
        row_h = max(58, min(108, avail // max(1, n)))
        slots = self._bank_rows(base, keys, self.p_top + 10, row_h,
                                label=f"WORD BANK · {n} NEW WORD{'S' if n != 1 else ''}")
        return dict(kind="recap", base=base, slots=slots, keys=keys)

    def _fly(self, gi):
        if gi not in self._fly_imgs:
            g = self.groups[gi]
            S = 2
            z = self.gsize[gi]
            t = _Txt(g["text"], z * S, INK, "SemiBold")
            pill = Image.new("RGBA", t.im.size, (0, 0, 0, 0))
            pd = ImageDraw.Draw(pill)
            bx = (t.pad - 10 * S, t.base - int(z * 0.86 * S), t.pad + t.w + 10 * S, t.base + int(z * 0.3 * S))
            pad = 40 * S
            big = Image.new("RGBA", (t.im.width + 2 * pad, t.im.height + 2 * pad), (0, 0, 0, 0))
            sh = Image.new("RGBA", big.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle([bx[0] + pad, bx[1] + pad + 14 * S, bx[2] + pad, bx[3] + pad + 14 * S],
                                                 10 * S, fill=(0, 0, 0, 90))
            sh = sh.filter(ImageFilter.GaussianBlur(14 * S))
            pd.rounded_rectangle(bx, 8 * S, fill=self.marker_col + (255,))
            pill_l = Image.new("RGBA", big.size, (0, 0, 0, 0))
            pill_l.alpha_composite(pill, (pad, pad))
            pill_l = Image.alpha_composite(sh, pill_l)
            txt_l = Image.new("RGBA", big.size, (0, 0, 0, 0))
            txt_l.alpha_composite(t.im, (pad, pad))
            # anchor = left end of the baseline, in the big image (S x)
            self._fly_imgs[gi] = (pill_l, txt_l, (pad + t.pad, pad + t.base), S)
        return self._fly_imgs[gi]

    # -------------------------------------------------------------- render
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
            e = ease_io(prog(t, self.turns[k], self.turns[k] + TURN))
            frame = b.copy()
            cut = self.bar_y + 20  # the band stays; the page below it slides
            frame.paste(self.paper.crop((0, cut, W, H)), (0, cut))
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
        else:
            frame = self._draw_page(k, t)
        if t < 0.9:
            frame = self._intro(frame, t)
        if self.has_ending:
            draw_ending(frame, t, self.E, *self.ending, self.band)
        global_fade(frame, t, self.dur, fade_in=False)
        return frame.convert("RGB")

    def _intro(self, frame, t):
        """The band drops in, then the page fades up."""
        out = self.paper.copy()
        e = 1 - (1 - prog(t, 0.0, 0.55)) ** 3
        a = prog(t, 0.25, 0.8)
        body = frame.crop((0, self.band_h, W, H))
        _comp(out, _fade(body, a), 0, self.band_h + int(30 * (1 - a)))
        band = frame.crop((0, 0, W, self.band_h + 26))
        _comp(out, band, 0, int(-(self.band_h + 26) * (1 - e)))
        return out

    def _draw_page(self, k, t):
        pg = self.pages[k]
        frame = pg["base"].copy()
        d = ImageDraw.Draw(frame)
        # progress of the reading
        p = prog(t, self.first_t, self.last_t)
        if p > 0:
            d.rounded_rectangle([X0, self.bar_y, X0 + max(8, WIDTH * p), self.bar_y + 8], 4, fill=self.band + (255,))
        if pg["kind"] == "recap":
            self._draw_recap(frame, pg, t)
            return frame
        # marker swipes (under the ink)
        for i, (mx, my, im) in pg["marks"].items():
            q = prog(t, self.vs[i], self.vs[i] + max(0.28, self.ve[i] - self.vs[i]))
            if q > 0:
                w = max(1, int(im.width * ease_io(q)))
                _comp(frame, im.crop((0, 0, w, im.height)), mx, my)
        # read-along ink: every spoken word, the current one wiping in left to right
        bx0, by0, bx1, by1 = pg["box"]
        mask = Image.new("L", (bx1 - bx0, by1 - by0), 0)
        md = ImageDraw.Draw(mask)
        any_ink = False
        for i in pg["idx"]:
            if t < self.vs[i]:
                break
            x0, y0, x1, y1 = pg["boxes"][i]
            q = prog(t, self.vs[i], self.vs[i] + max(0.12, self.ve[i] - self.vs[i]))
            xr = x0 + (x1 - x0) * q
            if q >= 1:
                md.rectangle([x0 - bx0, y0 - by0, x1 - bx0, y1 - by0], fill=255)
            else:
                edge = 22
                if xr - edge > x0:
                    md.rectangle([x0 - bx0, y0 - by0, xr - edge - bx0, y1 - by0], fill=255)
                for s in range(edge):
                    v = int(255 * (1 - s / edge))
                    xs = xr - edge + s - bx0
                    if xs >= x0 - bx0:
                        md.line([(xs, y0 - by0), (xs, y1 - by0)], fill=v)
            any_ink = True
        if any_ink:
            frame.paste(pg["ink_rgb"], (bx0, by0), ImageChops.multiply(mask, pg["ink_a"]))
        # word bank + flights
        self._draw_slots(frame, pg, t)
        for gi in pg["keys"]:
            u = prog(t, self.fly0[gi], self.fly0[gi] + FLY)
            if 0 < u < 1:
                self._draw_flight(frame, pg, gi, u)
        return frame

    def _slot_of(self, pg, gi):
        return next(s for s in pg["slots"] if s["gi"] == gi)

    def _draw_slots(self, frame, pg, t, landed_at=None):
        for j, s in enumerate(pg["slots"]):
            gi = s["gi"]
            t_land = landed_at[j] if landed_at else self.fly0[gi] + FLY
            if t < t_land:
                continue
            # a soft flash of the row when the word lands
            fl = 1 - prog(t, t_land, t_land + 0.7)
            if fl > 0 and not landed_at:
                ov = Image.new("RGBA", (WIDTH + 24, s["h"] - 6), self.marker_col + (int(110 * fl),))
                _comp(frame, ov, X0 - 12, s["y"] + 2)
            pop = 1 + 0.12 * (1 - ease_out_back(prog(t, t_land, t_land + 0.3))) if not landed_at else 1.0
            if abs(pop - 1) > 0.005:
                im = s["en"].im.resize((int(s["en"].im.width * pop), int(s["en"].im.height * pop)), Image.BILINEAR)
                _comp(frame, im, int(s["en_x"] - s["en"].pad * pop), int(s["base"] - s["en"].base * pop))
            else:
                a = prog(t, t_land, t_land + 0.25) if landed_at else 1.0
                s["en"].put(frame, s["en_x"], s["base"], a)
            ar = s["ar"]
            q = ease_io(prog(t, t_land + 0.12, t_land + 0.12 + REVEAL))
            if ar is not None and q > 0:  # the Arabic writes in from the right
                lead_x0 = s["en_x"] + s["en"].w + 18
                lead_x1 = s["ar_x"] - 14
                d = ImageDraw.Draw(frame)
                for x in range(int(lead_x0), int(lead_x0 + (lead_x1 - lead_x0) * q), 12):
                    d.ellipse([x, s["base"] - 3, x + 3, s["base"]], fill=(196, 200, 196, 255))
                w = max(1, int(ar.width * q))
                _comp(frame, ar.crop((ar.width - w, 0, ar.width, ar.height)), s["ar_x"] + ar.width - w, s["ar_y"])
            c = self.checks[gi] if gi < len(self.checks) else None
            if c is not None and t >= c:
                sc = ease_out_back(prog(t, c, c + 0.3))
                if sc > 0.02:
                    rad = max(16, int(s["en_size"] * 0.42))
                    if rad not in self._check_imgs:
                        self._check_imgs[rad] = _check(rad, self.band)
                    r = self._check_imgs[rad]
                    im = r.resize((max(1, int(r.width * sc)), max(1, int(r.height * sc))), Image.LANCZOS)
                    _comp(frame, im, int(s["num_x"] - im.width / 2), int(s["base"] - s["en_size"] * 0.34 - im.height / 2))

    def _draw_flight(self, frame, pg, gi, u):
        pill, txt, (ax, ay), S = self._fly(gi)
        g = self.groups[gi]
        x0, y0, x1, y1 = pg["boxes"][g["i0"]]
        start = (x0 + 2, y1 - 4 - _font(self.gsize[gi], "SemiBold").getmetrics()[1])  # baseline-left of the word
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
            lay = Image.alpha_composite(_fade(pill.resize(size, Image.BILINEAR), pa), lay)
        ox, oy = ax * k, ay * k
        if abs(rot) > 0.2:
            cx, cy = lay.width / 2, lay.height / 2
            lay = lay.rotate(rot, Image.BICUBIC, expand=True)
            a = math.radians(rot)
            dx, dy = ox - cx, oy - cy
            ox = lay.width / 2 + dx * math.cos(a) + dy * math.sin(a)
            oy = lay.height / 2 - dx * math.sin(a) + dy * math.cos(a)
        _comp(frame, lay, int(round(x - ox)), int(round(y - oy)))

    def _draw_recap(self, frame, pg, t):
        lands = [self.recap_row[j] for j in range(len(pg["slots"]))]
        self._draw_slots(frame, pg, t, landed_at=lands)

    # -------------------------------------------------------------- sound
    def sound(self, mx):
        mx.intro(0.05)
        mx.add(0.05, mx.paper(), 0.45)
        if self.audio:
            self._place_voice(mx)
        for k in range(1, len(self.turns)):
            mx.add(self.turns[k], mx.paper(), 0.5)
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
        if self.has_ending:
            mx.add(self.E, mx.chime(), 0.18)

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
