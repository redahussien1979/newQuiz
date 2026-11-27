"""📄 Torn pad (English Words → 📄 Torn pad): one word per sheet of torn coloured paper, like a tear-off pad. On every
sheet the English word rises in letter by letter while Voice 1 says it, a red pen circles it while Voice 2 says it,
the Arabic meaning wipes in right to left (several meanings split by red bars), then the example sentence appears word
by word as it is read (the word itself gets a yellow marker swipe), its Arabic translation wipes in, a second reading
is followed by a soft pill, and the sheet is ripped off to show the next one. The shared 🔚 Ending is the last sheet.

`tornpad.words` = one sheet per line: `English | Arabic meaning | English sentence | Arabic sentence`; the parts after
the English are told apart by their language and place (`parse_words`): Arabic before the English sentence = the
meaning(s) (` / ` between two meanings), Arabic after it = the sentence's translation. *stars* in the sentence mark
the highlighted words (else the word is found in it, also inflected: tragedy -> tragedies).

Voices (`tornpad.word_by` / `sent_by`: "12" = Voice 1 then Voice 2, "21", "1", "2"): clips `w<k>` / `w<k>e` (Voice
1: word k / its sentence) and `w<k>_v2` / `w<k>e_v2` (Voice 2), `clip_key`. Every step waits for its clip; a missing
clip keeps its place at a reading pace (silent). The sentence words follow the exact ElevenLabs timings
(`words_video.clip_word_times`). Every frame depends only on t (frames are drawn on several processes)."""
import math
import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..audio import SR, _lowpass, audio_length
from ..core import ARABIC_RE, H, ROOT, W, _state, get_font, global_fade, parse_lines, text_img_in, to_rgb
from ..list_designs import _colored
from ..paragraphs import find_phrase
from ..word_posts import _marker_band, _smooth_noise

NAME = "Torn Pad"

PLAYFAIR = os.path.join(ROOT, "fonts", "library", "PlayfairDisplay", "PlayfairDisplay[wght].ttf")
MONTSERRAT = os.path.join(ROOT, "fonts", "library", "Montserrat", "Montserrat[wght].ttf")
INTER = os.path.join(ROOT, "fonts", "library", "Inter", "Inter[opsz,wght].ttf")
LOGO = os.path.join(ROOT, "projects", "brand", "logolept_logo.png")
AR_DEFAULT = "Tajawal"

# sheet colours (the paper of the pad); "cycle" = a different one on every sheet
LOOKS = {"sage": (192, 211, 182), "sky": (196, 218, 234), "sand": (234, 220, 190), "blush": (240, 208, 202),
         "lavender": (216, 210, 236), "mint": (196, 230, 214)}
LOOK_CHOICES = [("Sage green (default)", "sage"), ("Sky blue", "sky"), ("Sand", "sand"), ("Blush pink", "blush"),
                ("Lavender", "lavender"), ("Mint", "mint"), ("A different colour on every sheet", "cycle")]
CYCLE = ("sage", "sky", "sand", "blush", "lavender", "mint")
# who reads: "12" = Voice 1 then Voice 2 …
READERS = [("Voice 1, then Voice 2", "12"), ("Voice 2, then Voice 1", "21"), ("Voice 1 only", "1"),
           ("Voice 2 only", "2")]

INK_WORD = (26, 30, 68)
PEN = (208, 38, 46)
INK = (28, 33, 30)
MARK = (255, 212, 40)
TEAR = 0.75      # the sheet is ripped off in the last TEAR s of its time
ENTER = 0.7      # the first sheet slides up
SHEET_Y, SHEET_H = 330, 1180
TEXT_W = 880
END_LEN = 4.4
WORD_PACE = 0.9   # a word without a clip
SENT_PACE = 0.32  # s per sentence word without a clip


# ------------------------------------------------------------------ text in / out
def _clean(s):
    return " ".join(str(s or "").split())


def sort_parts(en, parts):
    """dict(en, ar=[meanings], ex, ex_ar): Arabic before the English sentence = the meanings (` / ` or `|` splits
    them), Arabic after it = the sentence's translation."""
    ar, ex, ex_ar = [], "", []
    for p in (_clean(x) for x in parts):
        if not p:
            continue
        if ARABIC_RE.search(p):
            (ex_ar if ex else ar).append(p)
        elif not ex:
            ex = p
        else:
            ex += " " + p
    means = [m.strip() for a in ar for m in re.split(r"\s+/\s+|\|", a) if m.strip()]
    return dict(en=_clean(en), ar=means, ex=ex, ex_ar=" ".join(ex_ar))


def parse_words(text):
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if not parts[0].strip():
            continue
        out.append(sort_parts(parts[0], parts[1:]))
    return out


def words_text(items):
    """The editor's lines from item dicts (en, ar list or text, ex, ex_ar)."""
    lines = []
    for it in items:
        ar = it.get("ar") or []
        ar = " / ".join(ar) if isinstance(ar, (list, tuple)) else _clean(ar).replace("|", " / ")
        cells = [_clean(it.get("en")).replace("|", "/"), ar, _clean(it.get("ex")).replace("|", "/"),
                 _clean(it.get("ex_ar")).replace("|", "/")]
        lines.append(" | ".join([cells[0]] + [c for c in cells[1:] if c]))
    return "\n".join(lines)


def spoken(sentence):
    """The sentence as the voice reads it (no *stars*)."""
    return _clean(str(sentence or "").replace("*", ""))


_HEAD = {"ex_ar": ("arabic sentence", "sentence arabic", "translation", "ترجمة الجملة", "الجملة بالعربي",
                   "ترجمة المثال", "الترجمة"),
         "ex": ("sentence", "example", "sample sentence", "english sentence", "الجملة", "المثال"),
         "en": ("english", "word", "الكلمة", "الإنجليزي", "الانجليزي"),
         "ar": ("arabic", "meaning", "arabic meaning", "المعنى", "عربي", "العربي"),
         "title": ("title", "العنوان"), "sub": ("subtitle", "sub title", "العنوان الفرعي")}


def read_sheet(path, sheet=None):
    """([dict(en, ar, ex, ex_ar, title, sub)], [problems]) from an Excel / CSV sheet: English | Arabic | Sentence |
    Arabic sentence (+ optional Title, Subtitle; a title goes on until the next one), with or without a header row.
    Several Arabic meanings in one cell: split them with |."""
    from ..batch import read_table
    rows = read_table(path, sheet)
    cols, start = None, 0
    for i, row in enumerate(rows[:10]):
        found = {}
        for j, cell in enumerate(row):
            c = " ".join(str(cell or "").lower().split())
            # longer names first ("arabic sentence" before "arabic", "subtitle" before "title")
            for key in ("sub", "title", "ex_ar", "ex", "en", "ar"):
                if key not in found and c and any(c == h or c.startswith(h) for h in _HEAD[key]):
                    found[key] = j
                    break
        if "en" in found and "ar" in found:
            cols, start = found, i + 1
            break
    if cols is None:
        cols = {"en": 0, "ar": 1, "ex": 2, "ex_ar": 3}
    items, problems = [], []
    title = sub = ""
    for r, row in enumerate(rows[start:], start + 1):
        cell = lambda k: _clean(row[cols[k]]) if k in cols and cols[k] < len(row) and row[cols[k]] is not None \
            else ""  # noqa: E731
        if cell("title"):
            title, sub = cell("title"), cell("sub")
        elif cell("sub"):
            sub = cell("sub")
        en, ar = cell("en"), cell("ar")
        if not en and not ar:
            continue
        if not en:
            problems.append(f"row {r}: the English word is empty — left out")
            continue
        if not ar:
            problems.append(f"row {r}: no Arabic meaning for “{en}” — left out")
            continue
        it = dict(en=en, ar=[m.strip() for m in ar.split("|") if m.strip()], ex=cell("ex").replace("|", "/"),
                  ex_ar=cell("ex_ar").replace("|", "/"), title=title, sub=sub)
        items.append(it)
    return items, problems


TEMPLATE_ROWS = [
    ("English", "Arabic meaning (several: split by |)", "English sentence", "Arabic sentence", "Title", "Subtitle"),
    ("Retrospect", "استرجاع الماضي | نظرة إلى الوراء",
     "In retrospect, the decision to expand too rapidly proved to be a critical mistake.",
     "بالنظر إلى الوراء، تبيّن أن قرار التوسع السريع كان خطأً جسيماً.", "{count} Words to Sound Smarter",
     "كلمات إنجليزية راقية"),
    ("Sanity", "السلامة العقلية | العقلانية",
     "Amid the daily pressures, he relied on meditation to preserve his sanity.",
     "وسط الضغوط اليومية، اعتمد على التأمل للحفاظ على صحته العقلية.", "", ""),
    ("Solitude", "العزلة | الانفراد بالنفس",
     "The writer retreated to a mountain cabin, seeking solitude for creative inspiration.",
     "انسحب الكاتب إلى كوخ جبلي، باحثاً عن العزلة للإلهام الإبداعي.", "", ""),
    ("Specter", "الشبح | الطيف", "The specter of inflation continues to haunt the global economy.",
     "يواصل شبح التضخم تهديد الاقتصاد العالمي.", "", ""),
    ("Tragedy", "المأساة", "The collapse of the bridge was one of the greatest tragedies in the city's history.",
     "كان انهيار الجسر من أفجع المآسي في تاريخ المدينة.", "", ""),
]


def write_template(path):
    """projects/torn_pad_template.xlsx: English | Arabic meaning | English sentence | Arabic sentence | Title |
    Subtitle."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Words"
    for row in TEMPLATE_ROWS:
        ws.append(list(row))
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4A6248")
    for col, w in zip("ABCDEF", (20, 36, 70, 60, 32, 30)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in (row[1], row[3], row[5]):
            c.alignment = Alignment(horizontal="right", readingOrder=2)
    ws.freeze_panes = "A2"
    wb.save(path)


# ------------------------------------------------------------------ voice clips
_CLIP = re.compile(r"^(?:w|word)?[\s_.\-]*0*(\d{1,3})(e|ex|example)?(?:[\s_.\-]*v([12]))?$", re.I)
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".opus", ".wma", ".webm"}


def clip_key(path):
    """'w3' -> (3, 'w', 1); 'w3e' -> (3, 'e', 1); 'w3_v2' -> (3, 'w', 2); 'w3e_v2' -> (3, 'e', 2); else None."""
    stem, ext = os.path.splitext(os.path.basename(str(path)))
    m = _CLIP.match(stem.strip())
    if not m or ext.lower() not in AUDIO_EXT:
        return None
    return int(m.group(1)), ("e" if m.group(2) else "w"), int(m.group(3) or 1)


def clip_name(k, kind, voice):
    """The file name (no extension) of word k's clip: clip_name(3, 'e', 2) = 'w3e_v2'."""
    return f"w{k}" + ("e" if kind == "e" else "") + ("_v2" if voice == 2 else "")


def readers(value):
    v = str(value or "12")
    return [int(c) for c in v if c in "12"] or [1, 2]


def needed(items, word_by="12", sent_by="12"):
    """[(k, kind, voice)] of every clip the video reads, in order."""
    out = []
    for k, it in enumerate(items, 1):
        out += [(k, "w", v) for v in readers(word_by)]
        if spoken(it.get("ex")):
            out += [(k, "e", v) for v in readers(sent_by)]
    return out


# ------------------------------------------------------------------ easing
def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _prog(t, a, d):
    return _clamp((t - a) / d) if d > 0 else float(t >= a)


def _out(x, p=3):
    return 1 - (1 - _clamp(x)) ** p


def _back(x, s=1.6):
    x -= 1
    return 1 + x * x * ((s + 1) * x + s)


def _spring(x, k=7.0, z=0.42):
    """0 -> 1 with a damped overshoot."""
    if x <= 0:
        return 0.0
    return 1 - math.exp(-z * k * x) * math.cos(k * math.sqrt(1 - z * z) * x * 1.6)


def _fade(im, a):
    if a >= 1:
        return im
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return out


def _wipe_rtl(im, p, soft=60):
    """im revealed from its right edge towards the left (soft edge)."""
    if p >= 1:
        return im
    w = im.width
    edge = w - p * (w + soft)
    ramp = np.clip((np.arange(w) - edge) / soft, 0, 1).astype(np.float32)
    a = np.asarray(im.getchannel("A"), np.float32) * ramp[None]
    out = im.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8)))
    return out


def _crop_x(im):
    b = im.getchannel("A").getbbox()
    return im.crop((b[0], 0, b[2], im.height)) if b else im


# ------------------------------------------------------------------ paper
@lru_cache(1)
def _background():
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = ((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.62)) ** 2
    base = np.array((246, 244, 238), np.float32) * (1 - 0.07 * np.clip(v, 0, 1.4)[..., None])
    fib = Image.fromarray((rng.normal(0, 1, (H // 3, W // 3)) * 30 + 128).clip(0, 255).astype(np.uint8))
    fib = np.asarray(fib.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2)), np.float32) - 128
    base += fib[..., None] * 0.05 + rng.normal(0, 1.3, (H, W, 1))
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(8)
def _sheet(col, seed):
    """A sheet torn at the top and the bottom (white paper fibres along the tears), (image, pad)."""
    rng = np.random.default_rng(seed)
    pad = 40
    hs = SHEET_H + 2 * pad
    oct_ = ((170, 18.0), (44, 7.0), (10, 2.4), (3, 0.9))
    top = pad + _smooth_noise(W, rng, 1.0, oct_)
    bot = pad + SHEET_H + _smooth_noise(W, rng, 1.0, oct_)
    ftop = top - 3 - np.abs(_smooth_noise(W, rng, 1.0, ((22, 6.0), (5, 2.0))))
    fbot = bot + 3 + np.abs(_smooth_noise(W, rng, 1.0, ((22, 6.0), (5, 2.0))))
    yy = np.arange(hs)[:, None].astype(np.float32)
    paper = ((yy >= top[None]) & (yy <= bot[None])).astype(np.float32)
    fibre = (((yy < top[None]) & (yy >= ftop[None])) | ((yy > bot[None]) & (yy <= fbot[None]))).astype(np.float32)
    grain = np.asarray(Image.fromarray((rng.normal(0, 1, (hs // 2, W // 2)) * 40 + 128).clip(0, 255)
                                       .astype(np.uint8)).resize((W, hs), Image.BICUBIC), np.float32) - 128
    tex = 1 + 0.018 * grain / 40 + 0.03 * _smooth_noise(W, rng, 1.0, ((300, 1.0),))[None]
    shade = 1 - 0.05 * ((yy - pad) / SHEET_H)
    rgb = np.array(col, np.float32)[None, None] * (tex * shade)[..., None]
    rgb = rgb * paper[..., None] + np.array((250, 250, 246), np.float32) * fibre[..., None]
    a = np.clip(paper + fibre, 0, 1)
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a[..., None] * 255]).astype(np.uint8), "RGBA")
    return im, pad


@lru_cache(8)
def _shadow_mask(col, seed):
    im, _ = _sheet(col, seed)
    return im.getchannel("A").filter(ImageFilter.GaussianBlur(16))


def _pivot(size, ang, pivot):
    """Top-left of an image rotated (expand=True) by ang degrees about `pivot`, relative to the unrotated one."""
    w, h = size
    a = math.radians(ang)
    cs, sn = math.cos(a), math.sin(a)
    pts = []
    for px, py in ((0, 0), (w, 0), (0, h), (w, h)):
        dx, dy = px - pivot[0], py - pivot[1]
        pts.append((pivot[0] + dx * cs + dy * sn, pivot[1] - dx * sn + dy * cs))
    return min(p[0] for p in pts), min(p[1] for p in pts)


def _tone(col, k):
    """col darkened by k (0..1)."""
    return tuple(int(c * (1 - k)) for c in col)


# ------------------------------------------------------------------ pen + marker
@lru_cache(64)
def _loop_pts(rx, ry, seed):
    rng = np.random.default_rng(seed)
    a0 = math.radians(rng.uniform(195, 225))
    tilt = math.radians(rng.uniform(-4, 2))
    pts, n = [], 240
    for j in range(n):
        t = j / (n - 1)
        a = a0 + t * 2.12 * math.pi
        grow = 1 + 0.07 * t
        px, py = rx * grow * math.cos(a), ry * grow * math.sin(a)
        pts.append((px * math.cos(tilt) - py * math.sin(tilt) + 4 * t,
                    px * math.sin(tilt) + py * math.cos(tilt) - 2 * t, t))
    return pts


def _pen_loop(rx, ry, p, seed, width=6.0):
    """The red loop drawn up to fraction p of its path (thin where the pen lands and lifts)."""
    if p >= 1:
        return _pen_full(rx, ry, seed, width)
    pad = 30
    wl, hl = int(2 * rx * 1.1 + 2 * pad), int(2 * ry * 1.1 + 2 * pad)
    s = 3
    big = Image.new("L", (wl * s, hl * s), 0)
    d = ImageDraw.Draw(big)
    pts = _loop_pts(round(rx, 1), round(ry, 1), seed)
    prev = None
    for x, y, t in pts[:max(1, int(len(pts) * p))]:
        x, y = x + wl / 2, y + hl / 2
        wd = width * (0.35 + 0.65 * min(1, t / 0.12, (1 - t) / 0.18))
        if prev:
            d.line([(prev[0] * s, prev[1] * s), (x * s, y * s)], fill=255, width=max(1, int(wd * s)))
            r = wd * s / 2
            d.ellipse([x * s - r, y * s - r, x * s + r, y * s + r], fill=255)
        prev = (x, y)
    return _colored(big.resize((wl, hl), Image.LANCZOS), PEN, 0.95)


@lru_cache(16)
def _pen_full(rx, ry, seed, width):
    return _pen_loop(rx, ry, 0.9999, seed, width)


@lru_cache(64)
def _marker(w, h, seed):
    return _marker_band(w, h, MARK, seed=seed)


# ------------------------------------------------------------------ one sheet
class _Sheet:
    """Everything of one word's sheet that does not change per frame + its timing (local time 0 = sheet in place)."""

    def __init__(self, video, k, it):
        self.v, self.k = video, k
        self.col = video.colour(k)
        self.seed = 11 + k
        self._lay_out(it)
        self._time(it)

    # -------------------------------------------------------- layout
    def _lay_out(self, it):
        v = self.v
        word = it["en"]
        size = 146
        while True:
            f = get_font(size, "Bold", v.word_font)
            if f.getlength(word) <= TEXT_W - 60 or size <= 70:
                break
            size -= 6
        self.wf = f
        self.letters = [(ch, f.getlength(word[:i])) for i, ch in enumerate(word)]
        self.word_w = f.getlength(word)
        bb = f.getbbox(word)
        self.word_top, self.word_bot = bb[1], bb[3]
        self.ar = v.ar_lines(it["ar"])
        text = str(it.get("ex") or "")
        stars = "*" in text
        toks = spoken(text).split()
        self.toks = toks
        if stars:  # the *starred* words are the highlight
            hit, inside = set(), False
            for i, raw in enumerate(_clean(text).split()):
                if raw.startswith("*"):
                    inside = True
                if inside:
                    hit.add(i)
                if raw.rstrip(".,;:!?\"')").endswith("*"):
                    inside = False
            self.hit = {i for i in hit if i < len(toks)}
        else:
            span = find_phrase({"words": toks}, word) if toks else None
            self.hit = set(range(span[0], span[1] + 1)) if span else set()
        self.ex_ar_txt = it.get("ex_ar") or ""
        # the sentence block: shrink until everything fits the sheet
        for sc in (1.0, 0.92, 0.84, 0.76, 0.68):
            self._sentence_layout(sc)
            if self.total <= SHEET_H - 150:
                break
        self.y = {}
        y = 60 + (SHEET_H - 60 - self.total) / 2 + 10
        for name, h in self.blocks:
            self.y[name] = y
            y += h
        self.circ = dict(cy=self.y["word"] + 15 + (self.word_bot - self.word_top) / 2,
                         rx=round(self.word_w / 2 + 40, 1), ry=round((self.word_bot - self.word_top) / 2 + 40, 1))

    def _sentence_layout(self, sc):
        v = self.v
        fs = int(round(48 * sc))
        self.sf = get_font(fs, "Medium", MONTSERRAT)
        self.sfb = get_font(fs, "Bold", MONTSERRAT)
        self.lh = int(round(66 * sc))
        toks = self.toks
        space = self.sf.getlength(" ")
        widths = [(self.sfb if i in self.hit else self.sf).getlength(t) for i, t in enumerate(toks)]

        def flow(limit):
            lines, cur, cw = [], [], 0
            for i, t in enumerate(toks):
                tw = widths[i]
                if cur and cw + space + tw > limit:
                    lines.append((cur, cw))
                    cur, cw = [], 0
                cur.append((i, t, tw))
                cw += (space if len(cur) > 1 else 0) + tw
            if cur:
                lines.append((cur, cw))
            return lines
        lines = flow(TEXT_W)
        if toks:  # the narrowest width with the same number of lines: even lines, no lone last word
            lo, hi = max(widths), TEXT_W
            while hi - lo > 2:
                mid = (lo + hi) / 2
                if len(flow(mid)) <= len(lines):
                    hi = mid
                else:
                    lo = mid
            lines = flow(hi)
        self.slines, self.space = lines, space
        self.ex_ar = v.ar_wrap(self.ex_ar_txt, int(round(46 * sc))) if self.ex_ar_txt else []
        self.ex_ar_step = [im.height - int(54 * sc) for im in self.ex_ar]
        blocks = [("kick", 40), ("gap", 70), ("word", self.word_bot - self.word_top + 30), ("gap", 70),
                  ("ar", sum(im.height - 40 for im in self.ar))]
        if lines:
            blocks += [("gap", 80), ("ex", self.lh * len(lines))]
        if self.ex_ar:
            blocks += [("gap", 34), ("exar", sum(self.ex_ar_step))]
        self.blocks = blocks
        self.total = sum(h for _, h in blocks)

    # -------------------------------------------------------- timing
    def _time(self, it):
        v, k = self.v, self.k
        t = ENTER * 0.55 if k == 0 else 0.3
        self.t_letters = t
        self.voices = []
        tv = t + 0.25
        reads = []
        for r in v.word_by:
            c = v.clips.get((k + 1, "w", r))
            if c:
                self.voices.append((tv, c[0]))
            reads.append(tv)
            tv += (c[1] if c else WORD_PACE) + 0.25
        self.t_circle = reads[1] if len(reads) > 1 else reads[0] + 0.35
        self.t_ar = max(tv - 0.1, self.t_circle + 0.45)
        self.reads = []
        if self.toks:
            tv = self.t_ar + 0.95
            for r in v.sent_by:
                c = v.clips.get((k + 1, "e", r))
                if c:
                    from .words_video import clip_word_times
                    times = clip_word_times(c[0], c[1], self.toks)
                    self.voices.append((tv, c[0]))
                    ln = c[1]
                else:
                    wts = [len(w) + 2 for w in self.toks]
                    tot = sum(wts)
                    ln = SENT_PACE * len(self.toks)
                    times, a = [], 0.0
                    for wt in wts:
                        times.append((a, a + ln * wt / tot))
                        a += ln * wt / tot
                self.reads.append([(tv + a, tv + b) for a, b in times])
                tv += ln + 0.35
            first = self.reads[0]
            self.word_t = {i: first[i][0] - 0.06 for i in range(len(self.toks))}
            self.t_mark = first[min(self.hit)][0] if self.hit else None
            self.t_exar = first[-1][1] + 0.3
            end = max(tv + 0.7, self.t_exar + (2.0 if self.ex_ar else 1.2))
        else:
            self.word_t, self.t_mark, self.t_exar = {}, None, None
            end = max(tv + 0.6, self.t_ar + 2.6)
        self.D = end + TEAR

    # -------------------------------------------------------- drawing
    def boxes(self):
        out, y = {}, self.y.get("ex", 0)
        for line, lw in self.slines:
            x = W / 2 - lw / 2
            for i, tok, tw in line:
                out[i] = (x, y, tw)
                x += tw + self.space
            y += self.lh
        return out

    def draw(self, t, pad):
        """The content of the sheet at local time t, as an RGBA layer the size of the sheet image."""
        layer = Image.new("RGBA", (W, SHEET_H + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        oy = pad
        sub = _tone(self.col, 0.62)
        self.v.kicker(layer, d, oy + self.y["kick"], self.k, t, sub, self.D)
        # the word: letters rise in one after another (one image once they have all landed)
        base = W / 2 - self.word_w / 2
        wy = oy + self.y["word"] - self.word_top + 15
        n = len(self.letters)
        if t >= self.t_letters + 0.045 * (n - 1) + 0.5:
            im = self._word_img()
            layer.alpha_composite(im, (int(base - 10), int(wy - 10)))
        else:
            for i, (ch, lx) in enumerate(self.letters):
                p = _prog(t, self.t_letters + 0.045 * i, 0.5)
                if p <= 0:
                    continue
                e = _back(p)
                gl = self._glyph(ch, int(255 * _clamp(p * 2.2)))
                sc = 0.6 + 0.4 * e
                gw, gh = gl.size
                g2 = gl.resize((max(1, int(gw * sc)), max(1, int(gh * sc))), Image.BICUBIC)
                ox, oyy = (gw - g2.width) / 2, (gh - g2.height) * 0.75
                layer.alpha_composite(g2, (int(base + lx - 10 + ox), int(wy - 10 + (1 - e) * 70 + oyy)))
        # the red pen circle
        p = _prog(t, self.t_circle, 0.55)
        if p > 0:
            c = self.circ
            m = _pen_loop(c["rx"], c["ry"], _out(p), self.seed)
            layer.alpha_composite(m, (int(W / 2 - m.width / 2), int(oy + c["cy"] - m.height / 2)))
        # the Arabic meaning, wiped in right to left
        y = oy + self.y["ar"] - 20
        p = _prog(t, self.t_ar, 0.7)
        for li, im in enumerate(self.ar):
            q = _clamp(p * len(self.ar) - li)
            if q > 0:
                layer.alpha_composite(_wipe_rtl(im, _out(q)), (int(W / 2 - im.width / 2), int(y)))
            y += im.height - 40
        if self.slines:
            self._reader(layer, t, oy)
            y = oy + self.y["ex"]
            for line, lw in self.slines:
                x = W / 2 - lw / 2
                for i, tok, tw in line:
                    p = _prog(t, self.word_t[i], 0.32)
                    if p > 0:
                        e = _out(p)
                        hit = i in self.hit
                        f_ = self.sfb if hit else self.sf
                        if hit and self.t_mark is not None:
                            m = _prog(t, self.t_mark, 0.42)
                            if m > 0:
                                core = tok.rstrip(".,;:!?\"')”’")
                                mw = f_.getlength(core)
                                band, bp = _marker(int(mw + 20), int(self.lh * 0.76), self.k * 7 + i)
                                vis = int(band.width * _out(m))
                                if vis > 0:
                                    layer.alpha_composite(band.crop((0, 0, vis, band.height)),
                                                          (int(x - 10 - bp), int(y + self.lh * 0.12 - bp)))
                        col = (20, 24, 22) if hit else INK
                        d.text((x, y + (1 - e) * 18), tok, font=f_, fill=col + (int(255 * e),))
                    x += tw + self.space
                y += self.lh
        if self.ex_ar:
            y = oy + self.y["exar"] - 15
            p = _prog(t, self.t_exar, 0.8)
            ink = _tone(self.col, 0.72)
            for li, im in enumerate(self.ex_ar):
                q = _clamp(p * len(self.ex_ar) * 1.2 - li * 0.6)
                if q > 0:
                    layer.alpha_composite(_wipe_rtl(_colored(im.getchannel("A"), ink), _out(q)),
                                          (int(W / 2 - im.width / 2), int(y)))
                y += self.ex_ar_step[li]
        return layer

    def _glyph(self, ch, alpha):
        gl = Image.new("RGBA", (int(self.wf.size * 1.4), int(self.wf.size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(gl).text((10, 10), ch, font=self.wf, fill=INK_WORD + (alpha,))
        return gl

    def _word_img(self):
        if getattr(self, "_wimg", None) is None:
            im = Image.new("RGBA", (int(self.word_w + 60), int(self.wf.size * 1.6)), (0, 0, 0, 0))
            dd = ImageDraw.Draw(im)
            for ch, lx in self.letters:  # the same places as while they rise in (no jump when they land)
                dd.text((10 + lx, 10), ch, font=self.wf, fill=INK_WORD + (255,))
            self._wimg = im
        return self._wimg

    def _reader(self, layer, t, oy):
        """On the second (and later) reading a soft light pill glides behind the word being said."""
        boxes = None
        for times in self.reads[1:]:
            if not (times[0][0] - 0.25 <= t <= times[-1][1] + 0.35):
                continue
            boxes = boxes or self.boxes()
            a = _clamp(min((t - times[0][0] + 0.25) / 0.25, (times[-1][1] + 0.35 - t) / 0.35))
            j = 0
            while j < len(times) - 1 and t >= times[j + 1][0]:
                j += 1
            x0, y0, w0 = boxes[j]
            if j < len(times) - 1:  # glide into the next word during the last 0.12 s of this one
                g = _clamp((t - (times[j + 1][0] - 0.12)) / 0.12)
                g = g * g * (3 - 2 * g)
                x1, y1, w1 = boxes[j + 1]
                if abs(y1 - y0) > 1:  # the next line: no slide across the page
                    g = 1.0 if g >= 0.5 else 0.0
                x0, y0, w0 = x0 + (x1 - x0) * g, y0 + (y1 - y0) * g, w0 + (w1 - w0) * g
            ph = int(self.lh * 0.94)
            pill = Image.new("RGBA", (int(w0 + 28), ph), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([0, 0, pill.width - 1, ph - 1], int(ph * 0.3),
                                                   fill=(255, 255, 255, int(150 * a)))
            layer.alpha_composite(pill, (int(x0 - 14), int(oy + y0 + self.lh * 0.03)))


class _EndSheet:
    """The 🔚 Ending as the last sheet: small intro line, the question (a [colour] line in red), the call to action
    on a red pill."""

    def __init__(self, video, k, intro, q, cta):
        self.v, self.k = video, k
        self.col = video.colour(k)
        self.seed = 11 + k
        self.items = []  # (image, height step)
        sub = _tone(self.col, 0.62)
        if intro:
            im = video.ar_line(intro, 44, sub, "Bold") if ARABIC_RE.search(intro) else video.line(intro, 44, sub)
            self.items.append(("intro", im, 70))
        n = len(q)
        size = 92 if n <= 2 else 76
        for s, col in q:
            c = PEN if col != to_rgb("white") else INK_WORD
            if ARABIC_RE.search(s):
                im = video.ar_line(s, size, c)
            else:
                z = size
                while z > 44 and get_font(int(z), "Bold", video.word_font).getlength(s) > TEXT_W:
                    z -= 2
                im = video.line(s, z, c, "Bold", video.word_font)
            self.items.append(("q", im, int(size * 1.18)))
        if cta:
            txt = video.ar_line(cta, 46, (255, 255, 255), "Bold") if ARABIC_RE.search(cta) else \
                video.line(cta, 44, (255, 255, 255), "Bold")
            if txt.width > TEXT_W - 40:
                txt = txt.resize((TEXT_W - 40, int(txt.height * (TEXT_W - 40) / txt.width)), Image.LANCZOS)
            pw, ph = txt.width + 70, 96
            pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([0, 0, pw - 1, ph - 1], ph // 2, fill=PEN + (255,))
            pill.alpha_composite(txt, ((pw - txt.width) // 2, (ph - txt.height) // 2))
            self.items.append(("cta", pill, ph + 20))
        heights = [step for _, _, step in self.items]
        gaps = 40 * (len(self.items) - 1)
        self.y0 = 60 + (SHEET_H - 60 - sum(heights) - gaps) / 2
        self.D = END_LEN
        self.voices = []
        self.t_letters = 0.3

    def draw(self, t, pad):
        layer = Image.new("RGBA", (W, SHEET_H + 2 * pad), (0, 0, 0, 0))
        y = pad + self.y0
        for j, (kind, im, step) in enumerate(self.items):
            p = _prog(t, 0.25 + 0.22 * j, 0.5)
            if p > 0:
                e = _back(p, 1.2) if kind == "cta" else _out(p)
                img = _fade(im, _clamp(p * 1.8))
                if kind == "cta" and e != 1:
                    s_ = max(0.05, 0.7 + 0.3 * e)
                    img = img.resize((max(1, int(im.width * s_)), max(1, int(im.height * s_))), Image.BICUBIC)
                cy = y + step / 2 + (1 - e) * 26 * (kind != "cta")
                layer.alpha_composite(img, (int(W / 2 - img.width / 2), int(cy - img.height / 2)))
            y += step + 40
        return layer


EXAMPLE = {
    "template": "tornpad",
    "settings": {"theme": "Royal Blue", "language": "ar", "fps": 30, "music": "Lo-fi Chill", "music_gain": 0.5,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@logolept AR EN", "font_file": "", "intro_sound": "None",
                 "tick_sound": "Classic", "tick_gain": 1.0},
    "ending": {"intro": "", "question": "", "cta": ""},
    "tornpad": {
        "title": "",
        "subtitle": "",
        "words": words_text([dict(en=r[0], ar=r[1].split(" | "), ex=r[2], ex_ar=r[3]) for r in TEMPLATE_ROWS[1:]]),
        "sheet_color": "sage",
        "word_by": "12",
        "sent_by": "12",
        "voice_on": True,
        "voice1": "",
        "voice2": "",
        "audio": [],
        "audio_gain": 1.0,
        "arabic_font": "",
    },
}


class TornPad:
    def __init__(self, project):
        d = project.get("tornpad", {})
        s = project.get("settings", {})
        self.fps = int(s.get("fps") or 30)
        self.items = parse_words(d.get("words"))
        if not self.items:
            raise ValueError("Write at least one word: English | Arabic meaning | English sentence | Arabic sentence")
        bad = [it["en"] for it in self.items if not it["ar"]]
        if bad:
            raise ValueError(f"“{bad[0]}” has no Arabic meaning (English | Arabic meaning | sentence | Arabic sentence)")
        self.n = n = len(self.items)
        look = d.get("sheet_color") or "sage"
        self.look = look if look in LOOKS or look == "cycle" else "sage"
        self.word_by = readers(d.get("word_by"))
        self.sent_by = readers(d.get("sent_by"))
        self.audio_gain = float(d.get("audio_gain") or 1.0)
        self.handle = str(s.get("handle") or "").strip()
        picked = _state["font"] if s.get("font_file") else None  # a 🎨 Style & sound font replaces the word's
        self.word_font = picked or PLAYFAIR
        from .idiom_cards import _arabic_font
        self.ar_font = _arabic_font(d.get("arabic_font") or AR_DEFAULT)
        cnt = str(n)
        self.title = _clean(d.get("title")).replace("{count}", cnt)
        self.subtitle = _clean(d.get("subtitle")).replace("{count}", cnt)
        self.clips = {}
        for p in d.get("audio") or []:
            key = clip_key(p) if p and os.path.isfile(str(p)) else None
            if key and 1 <= key[0] <= n:
                try:
                    self.clips[key] = (p, audio_length(p))
                except Exception:
                    pass
        e = project.get("ending", {})
        e_intro = _clean(e.get("intro")).replace("{count}", cnt)
        e_q = parse_lines(str(e.get("question") or "").replace("{count}", cnt), ["white"])
        e_cta = _clean(e.get("cta")).replace("{count}", cnt)
        self.sheets = [_Sheet(self, k, it) for k, it in enumerate(self.items)]
        if e_intro or e_q or e_cta:
            self.sheets.append(_EndSheet(self, n, e_intro, e_q, e_cta))
        self.starts, t = [], 0.0
        for sh in self.sheets:
            self.starts.append(t)
            t += sh.D
        last = self.sheets[-1]
        self.base_duration = self.dur = t - (TEAR if isinstance(last, _Sheet) else 0) + 0.8
        first = self.sheets[0]
        self.cover_time = min(self.dur - 0.1, (first.t_exar or first.t_ar) + 1.2)
        self.silences = []
        self._head = self._header()
        self._hand = self._handle()

    # ------------------------------------------------------------ text helpers
    def colour(self, k):
        return LOOKS[CYCLE[k % len(CYCLE)]] if self.look == "cycle" else LOOKS[self.look]

    def line(self, txt, size, col, weight="Bold", font=None):
        f = get_font(int(size), weight, font or MONTSERRAT)
        asc, desc = f.getmetrics()
        w = int(math.ceil(f.getlength(txt)))
        im = Image.new("RGBA", (w + 20, asc + desc + 20), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10 + asc), txt, font=f, fill=tuple(col) + (255,), anchor="ls")
        return im

    def ar_line(self, txt, size, col, weight="Black"):
        """Arabic meanings ([list] or one text) -> one image, the first on the right, red bars between them."""
        parts = [p for p in (txt if isinstance(txt, (list, tuple)) else [txt]) if p]
        ims = [_crop_x(text_img_in(self.ar_font, p, int(size), col, weight)) for p in parts]
        gap, bw = int(size * 0.42), max(6, int(size * 0.11))
        total = sum(i.width for i in ims) + (len(ims) - 1) * (2 * gap + bw)
        h = max(i.height for i in ims)
        out = Image.new("RGBA", (max(1, total), h), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        x = total
        for j, im in enumerate(ims):
            x -= im.width
            out.alpha_composite(im, (x, (h - im.height) // 2))
            if j < len(ims) - 1:
                x -= gap + bw
                cy = h / 2 + size * 0.05
                d.rounded_rectangle([x, cy - size * 0.5, x + bw, cy + size * 0.42], bw / 2, fill=PEN)
                x -= gap
        return out

    def ar_lines(self, means):
        """The meanings at the biggest size that fits one line; else one meaning per line (or a long one wrapped)."""
        for size in range(88, 50, -2):
            im = self.ar_line(means, size, INK)
            if im.width <= TEXT_W:
                return [im]
        if len(means) > 1:
            return [self.ar_line([m], 58, INK) for m in means]
        return self.ar_wrap(means[0], 64, weight="Black", col=INK)

    def ar_wrap(self, txt, size, weight="Bold", col=INK):
        """A long Arabic text on balanced lines (fewest lines, the widest as narrow as possible)."""
        words = txt.split()
        best = None
        for lines in range(1, 5):
            if lines > len(words):
                break
            # all splits into `lines` lines are too many to try: greedy by characters, then measured
            target = len(txt) / lines
            out, cur = [], []
            for w in words:
                if cur and len(" ".join(cur + [w])) > target * 1.1 and len(out) < lines - 1:
                    out.append(cur)
                    cur = []
                cur.append(w)
            out.append(cur)
            ims = [_crop_x(text_img_in(self.ar_font, " ".join(c), size, col, weight)) for c in out]
            best = ims
            if max(i.width for i in ims) <= TEXT_W:
                return ims
        return [im.resize((min(im.width, TEXT_W), int(im.height * min(1, TEXT_W / im.width))), Image.LANCZOS)
                for im in best]

    def kicker(self, layer, d, y, k, t, col, dur):
        """WORD 01 / 05 + the progress dashes (the current one fills while the sheet is up)."""
        if k >= self.n:  # the ending sheet: no counter
            return
        kf = get_font(26, "Bold", INTER)
        txt = f"WORD  {k + 1:02d} / {self.n:02d}"
        tw = kf.getlength(txt) + 3 * len(txt)
        a = _out(_prog(t, 0.05 if k else 0.35, 0.4))
        x = W / 2 - tw / 2
        for ch in txt:
            d.text((x, y), ch, font=kf, fill=col + (int(255 * a),))
            x += kf.getlength(ch) + 3
        seg = min(46, 640 / self.n - 10)
        gp = 10
        bx = W / 2 - (self.n * seg + (self.n - 1) * gp) / 2
        by = y + 44
        for j in range(self.n):
            x0 = bx + j * (seg + gp)
            d.rounded_rectangle([x0, by, x0 + seg, by + 6], 3, fill=col + (int(70 * a),))
            fill = 1.0 if j < k else (_prog(t, 0.2, dur - TEAR - 0.4) if j == k else 0)
            if fill > 0:
                d.rounded_rectangle([x0, by, x0 + max(6, seg * fill), by + 6], 3, fill=PEN + (int(255 * a),))

    def _header(self):
        """The title (+ Arabic subtitle) over the pad, above the sheets."""
        if not (self.title or self.subtitle):
            return None
        ims = []
        if self.title:
            z = 64
            while z > 36 and get_font(z, "Bold", self.word_font).getlength(self.title) > TEXT_W:
                z -= 2
            ims.append(self.line(self.title, z, INK_WORD, "Bold", self.word_font))
        if self.subtitle:
            ims.append(self.ar_line(self.subtitle, 40, (96, 104, 96), "Bold") if ARABIC_RE.search(self.subtitle)
                       else self.line(self.subtitle, 36, (96, 104, 96), "SemiBold"))
        h = sum(i.height for i in ims) - 10 * (len(ims) - 1)
        out = Image.new("RGBA", (W, h), (0, 0, 0, 0))
        y = 0
        for im in ims:
            out.alpha_composite(im, (int(W / 2 - im.width / 2), y))
            y += im.height - 10
        return out

    def _handle(self):
        if not self.handle:
            return None
        f = get_font(30, "SemiBold", INTER)
        tw = int(f.getlength(self.handle))
        lg = None
        if os.path.isfile(LOGO):
            lg = Image.open(LOGO).convert("RGBA")
            lg = lg.resize((44, max(1, int(44 * lg.height / lg.width))), Image.LANCZOS)
        off = 58 if lg else 0
        im = Image.new("RGBA", (tw + off + 10, 52), (0, 0, 0, 0))
        if lg:
            im.alpha_composite(lg, (0, (im.height - lg.height) // 2))
        if ARABIC_RE.search(self.handle):
            txt = _crop_x(text_img_in(self.ar_font, self.handle, 30, (70, 80, 70), "Bold"))
            im = im.resize((off + txt.width + 10, max(52, txt.height)))
            im.alpha_composite(txt, (off, (im.height - txt.height) // 2))
        else:
            ImageDraw.Draw(im).text((off, im.height / 2), self.handle, font=f, fill=(70, 80, 70, 255), anchor="lm")
        return im

    # ------------------------------------------------------------ frame
    def _place(self, fr, im, x, y, ang=0.0, lift=0.0, shadow=None):
        """A sheet at (x, y), turned by ang degrees about the left end of its top edge; its shadow grows as it
        lifts."""
        pad = 40
        if ang:
            ox, oy = _pivot(im.size, ang, (0, pad))
            im = im.rotate(ang, Image.BICUBIC, expand=True, center=(0, pad))
            x, y = x + ox, y + oy
            sh = im.getchannel("A").filter(ImageFilter.GaussianBlur(14 + 30 * lift))
        else:
            sh = shadow
        fr.alpha_composite(_colored(sh, (30, 40, 28), 0.30 + 0.12 * lift), (int(x + 6 + 30 * lift),
                                                                              int(y + 12 + 50 * lift)))
        fr.alpha_composite(im, (int(x), int(y)))

    def render(self, t):
        fr = _background().copy()
        a = _out(_prog(t, 0.45, 0.6))
        if self._head is not None:
            hd = self._head
            fr.alpha_composite(_fade(hd, a), (0, int(SHEET_Y - 40 - hd.height + (1 - a) * 12)))
        if self._hand is not None:
            hi = self._hand
            fr.alpha_composite(_fade(hi, a), (int(W / 2 - hi.width / 2), SHEET_Y + SHEET_H + 70))
        k = 0
        for j, st in enumerate(self.starts):
            if t >= st:
                k = j
        sh = self.sheets[k]
        lt = t - self.starts[k]
        base, pad = _sheet(sh.col, sh.seed)
        nxt = self.sheets[k + 1] if k + 1 < len(self.sheets) else None
        tear = _prog(lt, sh.D - TEAR, TEAR) if nxt is not None else 0.0
        if tear > 0:  # the next sheet waits under this one
            nb, _ = _sheet(nxt.col, nxt.seed)
            img = nb.copy()
            img.alpha_composite(nxt.draw(-1.0, pad))
            self._place(fr, img, 0, SHEET_Y - pad, shadow=_shadow_mask(nxt.col, nxt.seed))
        img = base.copy()
        img.alpha_composite(sh.draw(lt, pad))
        x, y, ang, lift = 0.0, SHEET_Y - pad, 0.0, 0.0
        if k == 0 and lt < ENTER:  # the first sheet slides up and settles
            e = _spring(lt / ENTER)
            y += (1 - e) * 1300
            ang = (1 - e) * -4
        if tear > 0:  # a short tug, then it is ripped away up and to the left
            tug = math.sin(_clamp(tear / 0.18) * math.pi) * 0.4
            e = _clamp((tear - 0.12) / 0.88) ** 3
            ang = tug * 3 + e * 24
            x -= e * 520
            y -= e * 1500 - tug * 10
            lift = _clamp(tear * 2)
        self._place(fr, img, x, y, ang, lift, shadow=_shadow_mask(sh.col, sh.seed))
        z = 1 + 0.012 * _clamp(lt / max(1.0, sh.D))  # a slow push-in on every sheet
        if z > 1.0005:
            cw, ch = W / z, H / z
            fr = fr.crop((int((W - cw) / 2), int((H - ch) / 2), int((W + cw) / 2), int((H + ch) / 2))).resize(
                (W, H), Image.BICUBIC)
        global_fade(fr, t, self.dur)
        return fr.convert("RGB")

    # ------------------------------------------------------------ sound
    def sound(self, mx):
        mx.add(0.05, mx.paper(), 0.45)
        for k, sh in enumerate(self.sheets):
            t0 = self.starts[k]
            quiet = 0.35 if sh.voices else 1.0  # under a voice the effects step back
            if isinstance(sh, _Sheet):
                mx.add(t0 + sh.t_letters, mx.pop(), 0.2 * quiet)
                mx.add(t0 + sh.t_circle, mx.scribble(0.5), 0.3 * quiet)
                s, pn = mx.whoosh(0.5)
                mx.add(t0 + sh.t_ar, s, 0.14 * quiet, pn)
                if sh.t_mark is not None:
                    mx.add(t0 + sh.t_mark, mx.scribble(0.35), 0.12 * quiet)
            else:
                mx.add(t0 + 0.3, mx.chime(), 0.25)
            if k + 1 < len(self.sheets):
                mx.add(t0 + sh.D - TEAR, _rip(mx), 0.6)
            for at, path in sh.voices:
                mx.add_voice(path, t0 + at, self.audio_gain)


def _rip(mx):
    """Paper ripped off: a crackling burst of filtered noise."""
    n = int(0.45 * SR)
    x = np.arange(n) / SR
    nz = mx.rng.standard_normal(n)
    crack = (mx.rng.random(n) > 0.985) * mx.rng.uniform(-1, 1, n) * 4
    env = np.clip(x / 0.02, 0, 1) * np.exp(-x * 7)
    s = (_lowpass(nz, 5000) * 0.8 + _lowpass(crack, 7000)) * env
    return s / (np.abs(s).max() + 1e-9)

