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
from ..core import ARABIC_RE, H, ROOT, W, _state, get_font, global_fade, parse_lines, to_rgb
from ..list_designs import _colored
from ..paragraphs import find_phrase
from .text import _AR_PAD, _ar_justified, _ar_line
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
BRANDS = [("Handle only (Facebook / Reels show your logo already)", "handle"), ("Logo + handle", "logo"),
          ("Nothing", "none")]
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
    _MID[(col, seed)] = float(top.mean() + bot.mean()) / 2  # the middle of the green paper (image pixels)
    return im, pad


_MID = {}


def _sheet_mid(col, seed):
    """The y of the middle of a sheet's green paper (between its two torn edges), in the sheet image's pixels."""
    _sheet(col, seed)
    return _MID[(col, seed)]


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
# ------------------------------------------------------------------ measuring + justified lines
def _ink(im):
    """(left, top, right, bottom) of the ink of an image (its alpha), or the whole image."""
    return im.getchannel("A").getbbox() or (0, 0, im.width, im.height)


def _tight(im):
    return im.crop(_ink(im))


def _ar_adv(txt, size, font, weight="Bold"):
    """The advance width of an Arabic text as text._ar_line draws it."""
    return _ar_line(txt, size, INK, font, weight).width - 2 * _AR_PAD


def _ar_space(size, font, weight="Bold"):
    """The width of one space between two Arabic words (as text._ar_justified measures it)."""
    return max(4, _ar_adv("ب ب", size, font, weight) - 2 * _ar_adv("ب", size, font, weight))


def _widow(lines):
    """1 when the last of several lines holds one word, else 0."""
    return 1 if len(lines) > 1 and lines[-1][1] - lines[-1][0] == 1 else 0


def _breaks(widths, space, width, last_min=0.6):
    """Justified lines `width` wide: [(i0, i1)] word ranges with the least squared stretch of the spaces (1 = the
    spaces doubled) over the lines; the last line is not stretched, but one shorter than last_min of the width costs
    too, and so does a line of one word. (lines, cost); lines None when it cannot be done."""
    n = len(widths)
    inf = float("inf")
    best, prev = [0.0] + [inf] * n, [0] * (n + 1)
    for j in range(1, n + 1):
        ln = -space
        for i in range(j - 1, -1, -1):
            ln += widths[i] + space
            if ln > width:
                if i < j - 1:
                    break
                c = 1e6  # one word wider than the line
            elif j == n:  # the last line: not stretched, but never a lone word or a short stub
                c = 12 * (max(0.0, last_min * width - ln) / width) ** 2 + (3.0 if j - i == 1 and i > 0 else 0.0)
            elif j - i > 1:
                c = ((width - ln) / ((j - i - 1) * space)) ** 2
            else:
                c = 50 * ((width - ln) / width) ** 2
            if best[i] + c < best[j]:
                best[j], prev[j] = best[i] + c, i
    if best[n] == inf:
        return None, inf
    lines, j = [], n
    while j > 0:
        lines.append((prev[j], j))
        j = prev[j]
    return lines[::-1], best[n]


class _Sheet:
    """Everything of one word's sheet that does not change per frame + its timing (local time 0 = sheet in place).
    Every element is placed by its ink: centred left-right on the sheet, the whole block centred top-bottom on the
    middle of the green paper (`_sheet_mid`); positions are in the sheet image's pixels."""

    GAPS = dict(kick=44, word=40, ar=66, ex=50)  # the space under each element (ink to ink)

    def __init__(self, video, k, it):
        self.v, self.k = video, k
        self.col = video.colour(k)
        self.seed = 11 + k
        self._lay_out(it)
        self._time(it)

    # -------------------------------------------------------- layout
    def _lay_out(self, it):
        v = self.v
        text = str(it.get("ex") or "")
        toks = spoken(text).split()
        self.toks = toks
        if "*" in text:  # the *starred* words are the highlight
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
            span = find_phrase({"words": toks}, it["en"]) if toks else None
            self.hit = set(range(span[0], span[1] + 1)) if span else set()
        self.kick = v.kicker_img(self.k, _tone(self.col, 0.62))
        self.ar = v.ar_lines(it["ar"])
        ex_ar = it.get("ex_ar") or ""
        room = SHEET_H - 190
        # the biggest sizes that fit the sheet AND set the text cleanly (no lone last word, spaces at most ~2x); a
        # sentence that cannot be set cleanly at any size takes the least flawed layout that fits
        combos = ((1.0, 1.0), (1.0, 0.96), (1.0, 0.92), (1.0, 0.88), (1.0, 0.84), (0.9, 0.84), (0.9, 0.8),
                  (0.8, 0.74), (0.72, 0.66), (0.66, 0.6))
        fits = []
        for wk, sc in combos:
            self._word_layout(it["en"], wk)
            self._sentence_layout(sc, ex_ar)
            heights = self._heights()
            total = sum(h for _, h in heights) + sum(self.GAPS[n] for n, _ in heights[:-1])
            if total <= room:
                if not self.flaw:
                    break
                fits.append((self.flaw + 4 * (1 - sc), wk, sc))
        else:
            if fits:
                _, wk, sc = min(fits)
                self._word_layout(it["en"], wk)
                self._sentence_layout(sc, ex_ar)
                heights = self._heights()
                total = sum(h for _, h in heights) + sum(self.GAPS[n] for n, _ in heights[:-1])
        mid = _sheet_mid(self.col, self.seed)
        y = mid - total / 2
        self.top = {}
        for name, h in heights:
            self.top[name] = y
            y += h + self.GAPS.get(name, 0)
        self._place_all()

    def _word_layout(self, word, k):
        v = self.v
        size = int(146 * k)
        while True:
            f = get_font(size, "Bold", v.word_font)
            if f.getlength(word) <= TEXT_W - 80 or size <= 60:
                break
            size -= 4
        self.wf = f
        self.letters = [(ch, f.getlength(word[:i])) for i, ch in enumerate(word)]
        self.word_w = f.getlength(word)
        self._wimg = None
        wi = self._word_img()
        self.w_ink = _ink(wi)
        wh = self.w_ink[3] - self.w_ink[1]
        hw = (self.w_ink[2] - self.w_ink[0]) / 2
        # an oval whose first pass clears the word's corners by ~14 px (corner inside: (x/rx)² + (y/ry)² <= 1)
        rx = min(500.0, hw + 72)
        cx_, cy_ = hw + 14, wh / 2 + 12
        ry = cy_ / math.sqrt(max(0.05, 1 - (cx_ / rx) ** 2))
        rx, ry = round(rx, 1), round(max(wh / 2 + 34, min(ry, wh / 2 + 120)), 1)
        self.circ = (rx, ry)
        self.c_ink = _ink(_pen_full(rx, ry, self.seed, 6.0))
        self.word_h = max(wh, self.c_ink[3] - self.c_ink[1])

    def _sentence_layout(self, sc, ex_ar):
        """The sentence and its translation: ONE width for both blocks (`_breaks` over a range of widths, the least
        stretch for the two together), every line but the last justified to it — the English by its spaces, the
        Arabic with kashidas first (text._ar_justified) — the last line centred."""
        v = self.v
        fs = int(round(48 * sc))
        self.fs = fs
        self.sf = get_font(fs, "Medium", MONTSERRAT)
        self.sfb = get_font(fs, "Bold", MONTSERRAT)
        self.lh = int(round(fs * 1.38))
        toks = self.toks
        font = lambda i: self.sfb if i in self.hit else self.sf  # noqa: E731
        ew = [font(i).getlength(t) for i, t in enumerate(toks)]
        esp = self.sf.getlength(" ")
        afs = int(round(46 * sc))
        self.afs = afs
        self.ar_col = _tone(self.col, 0.72)
        aw = [_ar_adv(w, afs, v.ar_font) for w in ex_ar.split()]
        asp = _ar_space(afs, v.ar_font) if aw else 0
        one_e = sum(ew) + esp * (len(ew) - 1) <= TEXT_W if ew else True
        one_a = sum(aw) + asp * (len(aw) - 1) <= TEXT_W if aw else True
        if one_e and one_a:
            best = (TEXT_W, [(0, len(ew))] if ew else [], [(0, len(aw))] if aw else [])
        else:
            best, low = None, max(ew + aw + [TEXT_W * 0.55])
            for B in range(int(low), TEXT_W + 1, 6):
                le, ce = _breaks(ew, esp, B) if ew else ([], 0.0)
                la, ca = _breaks(aw, asp, B) if aw else ([], 0.0)
                if le is None or la is None:
                    continue
                # the English spaces show every stretch; the Arabic takes most of it in kashidas (but a lone last
                # word is as bad in either language)
                cost = ce + 0.15 * ca + 0.1 * (len(le) + len(la)) + 0.1 * (TEXT_W - B) / TEXT_W \
                    + 2.5 * _widow(la)
                if best is None or cost < best[0]:
                    best = (cost, B, le, la)
            best = best[1:] if best else (TEXT_W, [(0, len(ew))], [(0, len(aw))])
        B, le, la = best
        self.B = B
        stretch = max([(B - sum(ew[a:b]) - esp * (b - a - 1)) / ((b - a - 1) * esp)
                       for a, b in le[:-1] if b - a > 1] + [0.0])
        self.flaw = 3.0 * (_widow(le) + _widow(la)) + max(0.0, stretch - 1.15) ** 2
        self.elines = [[(i, toks[i], ew[i]) for i in range(a, b)] for a, b in le]
        self.esp = esp
        words = ex_ar.split()
        self.alines_txt = [" ".join(words[a:b]) for a, b in la]

    def _heights(self):
        out = [("kick", self.kick[1]), ("word", self.word_h)]
        self.ar_h = sum(im.height for im in self.ar) + 18 * (len(self.ar) - 1)
        out.append(("ar", self.ar_h))
        if self.elines:
            ascent = min(self._tb(i)[1] for i, _, _ in self.elines[0])
            descent = max(self._tb(i)[3] for i, _, _ in self.elines[-1])
            self.e_asc = -ascent
            out.append(("ex", self.lh * (len(self.elines) - 1) + descent - ascent))
        if self.alines_txt:
            self._ar_sentence()
            out.append(("exar", self.a_bot - self.a_top))
        return out

    def _tb(self, i):
        """The ink box of sentence word i around its baseline."""
        f = self.sfb if i in self.hit else self.sf
        return f.getbbox(self.toks[i], anchor="ls")

    def _ar_sentence(self):
        """The translation's line images (justified to B, the last centred), ink-exact: a justified line whose ink
        comes out a few pixels off B is justified again to the corrected width."""
        v, B = self.v, self.B
        n = len(self.alines_txt)
        self.alines = []
        pitch = int(round(self.afs * 1.6))
        for j, txt in enumerate(self.alines_txt):
            if j < n - 1 and len(txt.split()) > 1:
                im = _ar_justified([txt, txt], self.afs, self.ar_col, v.ar_font, int(B))[0]
                x0, _, x1, _ = _ink(im)
                if x1 - x0 != int(B):
                    im = _ar_justified([txt, txt], self.afs, self.ar_col, v.ar_font, int(2 * B - (x1 - x0)))[0]
                just = True
            else:
                im = _ar_line(txt, self.afs, self.ar_col, v.ar_font)
                just = False
            self.alines.append([im, just, j * pitch])
        inks = [_ink(im) for im, _, _ in self.alines]
        self.a_top = min(y + b[1] for (im, _, y), b in zip(self.alines, inks))
        self.a_bot = max(y + b[3] for (im, _, y), b in zip(self.alines, inks))

    def _place_all(self):
        """Absolute positions (sheet image pixels) of every piece, from the element tops."""
        cx = W / 2
        # kicker: text + dashes
        self.kick_xy = (cx - self.kick[0].width / 2, self.top["kick"])
        # word + circle: both centred on the word's ink centre
        w0, w1, w2, w3 = self.w_ink
        wcy = self.top["word"] + self.word_h / 2
        self.word_xy = (cx - (w0 + w2) / 2, wcy - (w1 + w3) / 2)
        m = _pen_full(self.circ[0], self.circ[1], self.seed, 6.0)  # the oval's centre = its image's centre
        self.circ_xy = (cx - m.width / 2, wcy - m.height / 2)
        # Arabic meaning(s)
        y = self.top["ar"]
        self.ar_xy = []
        for im in self.ar:
            self.ar_xy.append((cx - im.width / 2, y))
            y += im.height + 18
        # the sentence: every line but the last justified to [L, R] by its ink, the last one centred
        L, R = cx - self.B / 2, cx + self.B / 2
        self.tok_xy = {}  # i -> (x, baseline, advance, ink left, ink right)
        if self.elines:
            base = self.top["ex"] + self.e_asc
            for n, line in enumerate(self.elines):
                bb = [self._tb(i) for i, _, _ in line]
                adv = [w for _, _, w in line]
                if n < len(self.elines) - 1 and len(line) > 1:
                    x_first = L - bb[0][0]
                    x_last = R - bb[-1][2]
                    g = (x_last - x_first - sum(adv[:-1])) / (len(line) - 1)
                else:
                    g = self.esp
                    ink_w = sum(adv[:-1]) + g * (len(line) - 1) + bb[-1][2] - bb[0][0]
                    x_first = cx - ink_w / 2 - bb[0][0]
                x = x_first
                for (i, tok, w), b in zip(line, bb):
                    self.tok_xy[i] = (x, base, w, x + b[0], x + b[2])
                    x += w + g
                base += self.lh
        # the translation: justified lines by their ink right edge (= R), the last centred
        if self.alines_txt:
            y0 = self.top["exar"] - self.a_top
            self.alines_xy = []
            for im, just, dy in self.alines:
                i0, _, i2, _ = _ink(im)
                x = (R - i2) if just else (cx - (i0 + i2) / 2)
                self.alines_xy.append((x, y0 + dy))

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
            end = max(tv + 0.7, self.t_exar + (2.0 if self.alines_txt else 1.2))
        else:
            self.word_t, self.t_mark, self.t_exar = {}, None, None
            end = max(tv + 0.6, self.t_ar + 2.6)
        self.D = end + TEAR

    # -------------------------------------------------------- drawing
    def draw(self, t, pad):
        """The content of the sheet at local time t, as an RGBA layer the size of the sheet image."""
        layer = Image.new("RGBA", (W, SHEET_H + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        self.v.draw_kicker(layer, d, self.kick, self.kick_xy, self.k, t, _tone(self.col, 0.62), self.D)
        # the word: letters rise in one after another (one image once they have all landed)
        X, Y = self.word_xy
        n = len(self.letters)
        if t >= self.t_letters + 0.045 * (n - 1) + 0.5:
            layer.alpha_composite(self._word_img(), (int(round(X)), int(round(Y))))
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
                layer.alpha_composite(g2, (int(round(X + lx + ox)), int(round(Y + (1 - e) * 70 + oyy))))
        # the red pen circle
        p = _prog(t, self.t_circle, 0.55)
        if p > 0:
            m = _pen_loop(self.circ[0], self.circ[1], _out(p), self.seed)
            layer.alpha_composite(m, (int(round(self.circ_xy[0])), int(round(self.circ_xy[1]))))
        # the Arabic meaning, wiped in right to left
        p = _prog(t, self.t_ar, 0.7)
        for li, (im, (x, y)) in enumerate(zip(self.ar, self.ar_xy)):
            q = _clamp(p * len(self.ar) - li)
            if q > 0:
                layer.alpha_composite(_wipe_rtl(im, _out(q)), (int(round(x)), int(round(y))))
        if self.elines:
            self._reader(layer, t)
            for line in self.elines:
                for i, tok, _ in line:
                    p = _prog(t, self.word_t[i], 0.32)
                    if p <= 0:
                        continue
                    e = _out(p)
                    x, base, w, il, ir = self.tok_xy[i]
                    hit = i in self.hit
                    f_ = self.sfb if hit else self.sf
                    if hit and self.t_mark is not None:
                        m = _prog(t, self.t_mark, 0.42)
                        if m > 0:  # the marker covers the letters, not the comma / full stop after them
                            core = tok.rstrip(".,;:!?\"')”’")
                            cb = f_.getbbox(core, anchor="ls")
                            band, bp = _marker(int(cb[2] - cb[0] + 20), int(self.fs * 1.04), self.k * 7 + i)
                            vis = int(band.width * _out(m))
                            if vis > 0:
                                layer.alpha_composite(band.crop((0, 0, vis, band.height)),
                                                      (int(round(x + cb[0] - 10 - bp)),
                                                       int(round(base - self.fs * 0.8 - bp))))
                    col = (20, 24, 22) if hit else INK
                    d.text((x, base + (1 - e) * 18), tok, font=f_, fill=col + (int(255 * e),), anchor="ls")
        if self.alines_txt:
            p = _prog(t, self.t_exar, 0.8)
            n = len(self.alines)
            for li, ((im, _, _), (x, y)) in enumerate(zip(self.alines, self.alines_xy)):
                q = _clamp(p * n * 1.2 - li * 0.6)
                if q > 0:
                    layer.alpha_composite(_wipe_rtl(im, _out(q)), (int(round(x)), int(round(y))))
        return layer

    def _glyph(self, ch, alpha):
        gl = Image.new("RGBA", (int(self.wf.size * 1.4), int(self.wf.size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(gl).text((10, 10), ch, font=self.wf, fill=INK_WORD + (alpha,))
        return gl

    def _word_img(self):
        if self._wimg is None:
            im = Image.new("RGBA", (int(self.word_w + 60), int(self.wf.size * 1.6)), (0, 0, 0, 0))
            dd = ImageDraw.Draw(im)
            for ch, lx in self.letters:  # the same places as while they rise in (no jump when they land)
                dd.text((10 + lx, 10), ch, font=self.wf, fill=INK_WORD + (255,))
            self._wimg = im
        return self._wimg

    def _reader(self, layer, t):
        """On the second (and later) reading a soft light pill glides behind the word being said."""
        for times in self.reads[1:]:
            if not (times[0][0] - 0.25 <= t <= times[-1][1] + 0.35):
                continue
            a = _clamp(min((t - times[0][0] + 0.25) / 0.25, (times[-1][1] + 0.35 - t) / 0.35))
            j = 0
            while j < len(times) - 1 and t >= times[j + 1][0]:
                j += 1
            _, b0, _, l0, r0 = self.tok_xy[j]
            if j < len(times) - 1:  # glide into the next word during the last 0.12 s of this one
                g = _clamp((t - (times[j + 1][0] - 0.12)) / 0.12)
                g = g * g * (3 - 2 * g)
                _, b1, _, l1, r1 = self.tok_xy[j + 1]
                if abs(b1 - b0) > 1:  # the next line: no slide across the page
                    g = 1.0 if g >= 0.5 else 0.0
                b0, l0, r0 = b0 + (b1 - b0) * g, l0 + (l1 - l0) * g, r0 + (r1 - r0) * g
            ph = int(self.fs * 1.3)
            pw = int(r0 - l0 + 28)
            pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([0, 0, pw - 1, ph - 1], int(ph * 0.3),
                                                   fill=(255, 255, 255, int(150 * a)))
            layer.alpha_composite(pill, (int(round(l0 - 14)), int(round(b0 - self.fs * 0.98))))


class _EndSheet:
    """The 🔚 Ending as the last sheet: small intro line, the question (a [colour] line in red), the call to action
    on a red pill — each item centred by its ink, the block centred on the green paper."""

    def __init__(self, video, k, intro, q, cta):
        self.v, self.k = video, k
        self.col = video.colour(k)
        self.seed = 11 + k
        self.items = []  # (kind, tight image)
        sub = _tone(self.col, 0.62)
        if intro:
            im = video.ar_line(intro, 44, sub, "Bold") if ARABIC_RE.search(intro) else video.line(intro, 44, sub)
            self.items.append(("intro", _tight(im)))
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
            self.items.append(("q", _tight(im)))
        if cta:
            txt = _tight(video.ar_line(cta, 46, (255, 255, 255), "Bold") if ARABIC_RE.search(cta) else
                         video.line(cta, 44, (255, 255, 255), "Bold"))
            if txt.width > TEXT_W - 80:
                txt = txt.resize((TEXT_W - 80, max(1, int(txt.height * (TEXT_W - 80) / txt.width))), Image.LANCZOS)
            ph = txt.height + 50
            pw = txt.width + 80
            pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([0, 0, pw - 1, ph - 1], ph // 2, fill=PEN + (255,))
            pill.alpha_composite(txt, ((pw - txt.width) // 2, (ph - txt.height) // 2))
            self.items.append(("cta", pill))
        gaps = [44 if b[0] == "cta" else (34 if a[0] == "intro" else 26) for a, b in zip(self.items, self.items[1:])]
        total = sum(im.height for _, im in self.items) + sum(gaps)
        y = _sheet_mid(self.col, self.seed) - total / 2
        self.ys = []
        for j, (_, im) in enumerate(self.items):
            self.ys.append(y)
            y += im.height + (gaps[j] if j < len(gaps) else 0)
        self.D = END_LEN
        self.voices = []
        self.t_letters = 0.3

    def draw(self, t, pad):
        layer = Image.new("RGBA", (W, SHEET_H + 2 * pad), (0, 0, 0, 0))
        for j, ((kind, im), y) in enumerate(zip(self.items, self.ys)):
            p = _prog(t, 0.25 + 0.22 * j, 0.5)
            if p <= 0:
                continue
            e = _back(p, 1.2) if kind == "cta" else _out(p)
            img = _fade(im, _clamp(p * 1.8))
            cy = y + im.height / 2 + (1 - e) * 26 * (kind != "cta")
            if kind == "cta" and e != 1:
                s_ = max(0.05, 0.7 + 0.3 * e)
                img = img.resize((max(1, int(im.width * s_)), max(1, int(im.height * s_))), Image.BICUBIC)
            layer.alpha_composite(img, (int(round(W / 2 - img.width / 2)), int(round(cy - img.height / 2))))
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
        "brand_mark": "handle",
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
        bm = d.get("brand_mark") or "handle"
        self.brand = bm if bm in dict((v, k) for k, v in BRANDS) else "handle"
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
        im = Image.new("RGBA", (w + 40, asc + desc + 40), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((20, 20 + asc), txt, font=f, fill=tuple(col) + (255,), anchor="ls")
        return im

    def ar_line(self, txt, size, col, weight="Black"):
        """Arabic meanings ([list] or one text) -> one tight image, the first on the right, red bars between them;
        every part on ONE baseline (text._ar_line: a fixed baseline per font and size)."""
        parts = [p for p in (txt if isinstance(txt, (list, tuple)) else [txt]) if p]
        ims = [_ar_line(p, int(size), col, self.ar_font, weight) for p in parts]
        gap, bw = int(size * 0.42), max(6, int(size * 0.11))
        adv = [im.width - 2 * _AR_PAD for im in ims]
        total = sum(adv) + (len(ims) - 1) * (2 * gap + bw)
        h = ims[0].height
        out = Image.new("RGBA", (int(total) + 2 * _AR_PAD, h), (0, 0, 0, 0))
        f = get_font(int(size), weight, self.ar_font)
        baseline = int(size * 0.25) + f.getmetrics()[0]  # as text._ar_line draws it
        d = ImageDraw.Draw(out)
        x = total + _AR_PAD
        for j, (im, a) in enumerate(zip(ims, adv)):
            x -= a
            out.alpha_composite(im, (int(round(x - _AR_PAD)), 0))
            if j < len(ims) - 1:
                x -= gap + bw
                d.rounded_rectangle([x, baseline - size * 0.7, x + bw, baseline + size * 0.16], bw / 2, fill=PEN)
                x -= gap
        return _tight(out)

    def ar_lines(self, means):
        """The meanings at the biggest size that fits one line; else one meaning per line (or a long one on balanced
        lines), all centred."""
        for size in range(88, 50, -2):
            im = self.ar_line(means, size, INK)
            if im.width <= TEXT_W:
                return [im]
        if len(means) > 1:
            return [self.ar_line([m], 58, INK) for m in means]
        words = means[0].split()
        widths = [_ar_adv(w, 60, self.ar_font, "Black") for w in words]
        lines, _ = _breaks(widths, _ar_space(60, self.ar_font, "Black"), TEXT_W, last_min=0.8)
        return [self.ar_line(" ".join(words[a:b]), 60, INK) for a, b in lines or [(0, len(words))]]

    def kicker_img(self, k, col):
        """(WORD 01 / 05 as a tight letter-spaced image, the height of the text + dashes) — None on the ending."""
        kf = get_font(26, "Bold", INTER)
        txt = f"WORD  {k + 1:02d} / {self.n:02d}"
        im = Image.new("RGBA", (int(kf.getlength(txt) + 4 * len(txt) + 40), 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = 20
        for ch in txt:
            d.text((x, 40), ch, font=kf, fill=tuple(col) + (255,), anchor="ls")
            x += kf.getlength(ch) + 3
        im = _tight(im)
        return im, im.height + 16 + 6

    def draw_kicker(self, layer, d, kick, xy, k, t, col, dur):
        """The counter text, then the progress dashes under it (the current one fills while the sheet is up)."""
        im, h = kick
        a = _out(_prog(t, 0.05 if k else 0.35, 0.4))
        if a <= 0:
            return
        x, y = xy
        layer.alpha_composite(_fade(im, a), (int(round(x)), int(round(y))))
        seg = min(46.0, 640 / self.n - 10)
        gp = 10
        bx = W / 2 - (self.n * seg + (self.n - 1) * gp) / 2
        by = y + im.height + 16
        for j in range(self.n):
            x0 = bx + j * (seg + gp)
            d.rounded_rectangle([x0, by, x0 + seg, by + 6], 3, fill=tuple(col) + (int(70 * a),))
            fill = 1.0 if j < k else (_prog(t, 0.2, dur - TEAR - 0.4) if j == k else 0)
            if fill > 0:
                d.rounded_rectangle([x0, by, x0 + max(6, seg * fill), by + 6], 3, fill=PEN + (int(255 * a),))

    def _header(self):
        """The title (+ subtitle) over the pad, each line centred by its ink."""
        if not (self.title or self.subtitle):
            return None
        ims = []
        if self.title:
            z = 64
            while z > 36 and get_font(z, "Bold", self.word_font).getlength(self.title) > TEXT_W:
                z -= 2
            ims.append(_tight(self.line(self.title, z, INK_WORD, "Bold", self.word_font)))
        if self.subtitle:
            ims.append(self.ar_line(self.subtitle, 40, (96, 104, 96), "Bold") if ARABIC_RE.search(self.subtitle)
                       else _tight(self.line(self.subtitle, 36, (96, 104, 96), "SemiBold")))
        gap = 18
        h = sum(i.height for i in ims) + gap * (len(ims) - 1)
        out = Image.new("RGBA", (W, h), (0, 0, 0, 0))
        y = 0
        for im in ims:
            out.alpha_composite(im, (int(round(W / 2 - im.width / 2)), y))
            y += im.height + gap
        return out

    def _handle(self):
        """The brand under the pad (`brand_mark`): the handle alone (default: Facebook / Reels already show the
        page's logo next to its name), the logo + the handle, or nothing."""
        if self.brand == "none" or not self.handle:
            return None
        col = (86, 96, 86)
        txt = _tight(self.ar_line(self.handle, 30, col, "Bold") if ARABIC_RE.search(self.handle)
                     else self.line(self.handle, 30, col, "SemiBold", INTER))
        if self.brand != "logo" or not os.path.isfile(LOGO):
            return txt
        lg = Image.open(LOGO).convert("RGBA")
        lg = lg.resize((46, max(1, int(46 * lg.height / lg.width))), Image.LANCZOS)
        h = max(lg.height, txt.height)
        im = Image.new("RGBA", (lg.width + 14 + txt.width, h), (0, 0, 0, 0))
        im.alpha_composite(lg, (0, (h - lg.height) // 2))
        im.alpha_composite(txt, (lg.width + 14, (h - txt.height) // 2))
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

