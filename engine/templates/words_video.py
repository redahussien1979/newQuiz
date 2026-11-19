"""🎬 Words video (English Words → 🎬 Words video): any number of words float on screen as glass bubbles over a living
aurora background. One after another (a light first hops over the words still waiting — `pick` = roulette), a
bubble is picked, flies to the centre and POPS into a decorated card: number chip, the word dropping in letter by
letter, IPA pill with a speaker, an ornament divider, the Arabic meaning written in from the right on a marker band,
the English meaning, and the example sentence word by word with the word itself on a pill. The card then collapses
back into its bubble, which lands checked (✓). After the last word the bubbles line up into a recap list, then the
shared 🔚 Ending card.

`wordsvideo.words` = one word per line, `English | Arabic | IPA | English meaning | example sentence` (all but the
English optional; `*stars*` in the sentence mark the highlighted words, else the word is found in any form).
Audio clips named `w<k>` (the word) and `w<k>e` (its sentence) are played and the card waits for them.
Looks `DESIGNS` (colour sets over the same motion design). Every frame depends only on t (rendered on several
processes); cards are built lazily and kept in a small per-process cache."""
import math
import os
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..audio import audio_length
from ..core import (ARABIC_RE, H, ROOT, W, _state, composite, ease_io, ease_out_back, fade, get_font, global_fade,
                    parse_lines, prog, text_img_in, to_rgb)
from .vocab import clip_key

NAME = "Words Video"

LIB = os.path.join(ROOT, "fonts", "library")
EN_FONT = os.path.join(LIB, "Poppins", "Poppins-Bold.ttf")
AR_DEFAULT = "Noto Sans Arabic"  # the Arabic font family (any library family can be picked: wordsvideo.arabic_font)
IPA_FONT = os.path.join(ROOT, "fonts", "NotoSans-Bold.ttf")

# Clean, light colour sets (one "a little dark"): bg = background gradient top / bottom, dots = the faint dot
# pattern, head / head_soft = text on the background, acc = one accent per word (cycled), card = the white card,
# ink / soft = text on cards, light = light background
_ACC = ((233, 95, 74), (16, 145, 140), (52, 110, 220), (205, 140, 10), (148, 72, 180), (36, 150, 84))
DESIGNS = {
    "paper": dict(bg=((251, 248, 242), (244, 239, 230)), dots=(150, 130, 100), head=(30, 34, 52), head_soft=(110, 104, 96),
                  acc=_ACC, card=(255, 255, 255), ink=(28, 32, 52), soft=(96, 102, 122), light=True),
    "sky": dict(bg=((240, 247, 253), (224, 237, 250)), dots=(90, 130, 180), head=(20, 40, 76), head_soft=(84, 104, 136),
                acc=((37, 99, 235), (219, 80, 74), (13, 148, 136), (217, 119, 6), (124, 58, 237), (22, 163, 74)),
                card=(255, 255, 255), ink=(20, 32, 60), soft=(90, 104, 130), light=True),
    "mint": dict(bg=((239, 249, 244), (224, 242, 233)), dots=(80, 150, 120), head=(18, 52, 42), head_soft=(80, 112, 100),
                 acc=((5, 140, 110), (230, 100, 70), (40, 100, 210), (200, 140, 20), (170, 60, 140), (60, 130, 60)),
                 card=(255, 255, 255), ink=(20, 40, 36), soft=(86, 108, 100), light=True),
    "blush": dict(bg=((253, 244, 242), (248, 231, 230)), dots=(170, 110, 110), head=(60, 24, 36), head_soft=(130, 92, 100),
                  acc=((214, 64, 96), (30, 130, 150), (90, 90, 210), (210, 130, 30), (150, 70, 170), (40, 140, 90)),
                  card=(255, 255, 255), ink=(48, 26, 36), soft=(118, 96, 104), light=True),
    "slate": dict(bg=((58, 68, 86), (40, 48, 62)), dots=(200, 210, 230), head=(248, 249, 252), head_soft=(196, 204, 220),
                  acc=((242, 112, 86), (30, 170, 160), (70, 130, 240), (226, 160, 30), (168, 96, 220), (52, 170, 100)),
                  card=(255, 255, 255), ink=(28, 34, 50), soft=(96, 104, 124), light=False),
}
DESIGN_CHOICES = [("Warm paper", "paper"), ("Soft sky", "sky"), ("Fresh mint", "mint"), ("Blush", "blush"),
                  ("Slate (a little dark)", "slate")]
PACES = {"calm": 1.25, "normal": 1.0, "fast": 0.8}
# how the Arabic meaning arrives (word by word, right to left): (lead before the first word, step between words)
AR_STYLES = [("Brush stroke — paint sweeps in, the words pop on it", "brush"),
             ("Stamp — every word slams in with an ink splash", "stamp"),
             ("Ribbon — a ribbon unrolls, white words on it", "ribbon"),
             ("Hand-drawn swoosh under the words", "swoosh"),
             ("Simple — the words fade in", "plain")]
# what the items are: the card label ("IDIOM 2 OF 6"), the header ("ENGLISH · 6 IDIOMS"), the automatic title
KINDS = [("Automatic — WORD for one word, EXPRESSION for more", "auto"), ("Words", "word"), ("Idioms", "idiom"),
         ("Expressions", "expression"), ("Phrasal verbs", "phrasal"), ("Proverbs", "proverb")]
KIND_LABEL = {"word": ("WORD", "WORDS"), "idiom": ("IDIOM", "IDIOMS"), "expression": ("EXPRESSION", "EXPRESSIONS"),
              "phrasal": ("PHRASAL VERB", "PHRASAL VERBS"), "proverb": ("PROVERB", "PROVERBS")}
KIND_TITLE = {"word": "English Words", "idiom": "English Idioms", "expression": "English Expressions",
              "phrasal": "Phrasal Verbs", "proverb": "English Proverbs"}
# in an idiom these stand for anyone / any form ("bite off more than YOU CAN chew" ~ "I bit off more than I could chew")
_ANY = {"i", "me", "my", "myself", "you", "your", "yours", "yourself", "he", "him", "his", "himself", "she", "her",
        "hers", "herself", "it", "its", "itself", "we", "us", "our", "ourselves", "they", "them", "their",
        "themselves", "one", "oneself", "can", "could", "will", "would", "may", "might", "shall", "should", "must"}
# how the example sentence follows the voice (every word timed to when it is spoken)
EX_REVEALS = [("Red + bold — the spoken word turns red and bold", "redbold"),
              ("Karaoke — the words darken as they are spoken", "karaoke"),
              ("Marker — a highlighter glides under the spoken word", "marker"),
              ("Appear — each word pops in when it is spoken", "appear")]
RED = (214, 36, 36)
GAP_MAX = 0.32  # a justified line adds at most this much (x the text size) to each space: tight, even word spacing
AR_TIME = {"brush": (0.1, 0.13), "stamp": (0.0, 0.22), "ribbon": (0.14, 0.12), "swoosh": (0.0, 0.1),
           "plain": (0.0, 0.09)}
PICKS = [("Roulette — a light hops over the words, then lands on the next one", "roulette"),
         ("Straight to the next word", "direct")]

CW = 940            # card width
MARGIN = 64         # room around the card for its shadow
PAD = 60            # inside the card
CARD_MAX = 1250     # tallest card
CARD_CY = 1000      # card centre
ZONE = (600, 1520)  # where the bubbles float (under the header, above the Shorts captions)
DOT_GAP = 46        # background dot pattern
_BG_CACHE = {}


# ------------------------------------------------------------------ the words text
def parse_words(text):
    """[dict(en, ar, ipa, df, ex)] from 'English | Arabic | IPA | English meaning | example' lines."""
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [" ".join(p.split()) for p in line.split("|")]
        parts += [""] * (5 - len(parts))
        en, ar, ipa, df, ex = parts[:5]
        if not en:
            continue
        if ipa and not ipa.startswith("/") and not ipa.startswith("["):
            ipa = f"/{ipa.strip('/')}/"
        out.append(dict(en=en, ar=ar, ipa=ipa, df=df, ex=ex))
    return out


def words_text(words):
    """The editor's text from word dicts (word_import.read_words: en, ar, ipa, def, ex)."""
    lines = []
    for w in words:
        cells = [w.get("en", ""), w.get("ar", ""), w.get("ipa", ""), w.get("def", w.get("df", "")), w.get("ex", "")]
        cells = [" ".join(str(c or "").replace("|", "/").split()) for c in cells]
        while len(cells) > 2 and not cells[-1]:
            cells.pop()
        lines.append(" | ".join(cells))
    return "\n".join(lines)


# ------------------------------------------------------------------ small drawing helpers
def _spring(x, damp=6.0, freq=11.0):
    """0 -> 1 with a lively overshoot (pop-ins)."""
    if x <= 0:
        return 0.0
    if x >= 1.6:
        return 1.0
    return 1 - math.exp(-damp * x) * math.cos(freq * x)


def _out3(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _in2(x):
    x = min(1.0, max(0.0, x))
    return x * x


def _mix(a, b, k):
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


def _lum(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def _on(c):
    """Text colour that reads on colour c."""
    return (18, 20, 36) if _lum(c) > 0.55 else (255, 255, 255)


def _rr_mask(w, h, r, ss=3):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], int(r * ss), fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _scale_mask(m, a):
    return m.point(lambda v: int(v * a)) if a < 0.999 else m


def _vgrad(w, h, c0, c1):
    y = np.linspace(0, 1, max(1, h))[:, None, None]
    arr = np.array(c0, float) * (1 - y) + np.array(c1, float) * y
    return Image.fromarray(np.repeat(arr, max(1, w), axis=1).astype(np.uint8), "RGB")


def _solid(mask, col, a=1.0):
    im = Image.new("RGBA", mask.size, tuple(col[:3]) + (0,))
    im.putalpha(_scale_mask(mask, a))
    return im


def _grad_fill(mask, c0, c1, a=1.0):
    im = _vgrad(mask.width, mask.height, c0, c1).convert("RGBA")
    im.putalpha(_scale_mask(mask, a))
    return im


def _glow(mask, col, radius, a=1.0, grow=0):
    """mask on a bigger canvas, blurred and coloured (a soft light around a shape)."""
    m = Image.new("L", (mask.width + 4 * radius, mask.height + 4 * radius), 0)
    m.paste(mask, (2 * radius, 2 * radius))
    if grow:
        m = m.filter(ImageFilter.MaxFilter(grow * 2 + 1))
    m = m.filter(ImageFilter.GaussianBlur(radius))
    return _solid(m, col, a)


def _ltext(path, txt, size, weight, fill):
    """Latin text on a fixed-height box (baseline at pad + ascent: lines of tokens share one baseline).
    Returns (image, baseline y, advance width)."""
    f = get_font(int(size), weight, path)
    asc, desc = f.getmetrics()
    adv = f.getlength(txt)
    p = int(size * 0.25) + 6
    im = Image.new("RGBA", (int(math.ceil(adv)) + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((p, p + asc), txt, font=f, fill=tuple(fill[:3]) + (255,), anchor="ls")
    return im, p + asc, adv, p


def _adv(path, txt, size, weight):
    return get_font(int(size), weight, path).getlength(txt)


def _ink_w(path, txt, size, weight):
    return text_img_in(path, txt, int(size), (255, 255, 255), weight).width - 60


def _lines(measure, txt, max_w, n_max):
    """Greedy lines, re-balanced (two or three lines of similar width read better than a long + a short one)."""
    words = txt.split()
    if not words:
        return []
    lines, cur = [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if cur and measure(test) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = test
    lines.append(cur)
    if len(lines) == 2 and len(words) >= 2:
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            m = max(measure(a), measure(b))
            if m <= max_w and (best is None or m < best[0]):
                best = (m, [a, b])
        if best:
            lines = best[1]
    elif len(lines) == 3 and len(words) >= 3 and len(words) <= 18:
        best = None
        for i in range(1, len(words) - 1):
            for j in range(i + 1, len(words)):
                parts = [" ".join(words[:i]), " ".join(words[i:j]), " ".join(words[j:])]
                m = max(measure(p) for p in parts)
                if m <= max_w and (best is None or m < best[0]):
                    best = (m, parts)
        if best:
            lines = best[1]
    return lines if len(lines) <= n_max and all(measure(x) <= max_w for x in lines) else None


def _fit_lines(measure_at, txt, size, min_size, max_w, n_max):
    """(size, lines): the biggest size at which txt fits in n_max lines of max_w."""
    s = size
    while True:
        lines = _lines(lambda x: measure_at(x, s), txt, max_w, n_max)
        if lines or s <= min_size:
            return s, lines or [txt]
        s = max(min_size, int(s * 0.93))


def timings_path(audio_path):
    """Where the word timings of a voice clip are kept: DATA_DIR/tts/timings/<sha1 of the audio>.json (the app copies
    uploaded files, so a file next to the clip would be lost; the content stays the same)."""
    import hashlib
    from ..userdata import data_dir
    with open(audio_path, "rb") as f:
        h = hashlib.sha1(f.read()).hexdigest()
    return os.path.join(data_dir(ROOT), "tts", "timings", h + ".json")


def save_timings(audio_path, words, times):
    import json
    path = timings_path(audio_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"words": list(words), "times": [list(x) for x in times]}, f)


def clip_word_times(path, length, words):
    """[(start, end)] seconds of every word of a voice clip: the ElevenLabs timings when the clip was made by the app,
    else spread over the part of the clip with sound, by word length."""
    import json
    try:
        with open(timings_path(path), encoding="utf-8") as f:
            d = json.load(f)
        if len(d.get("times", [])) == len(words):
            return [tuple(x) for x in d["times"]]
    except (OSError, ValueError):
        pass
    a0, a1 = 0.05, max(0.2, length - 0.05)
    try:
        from ..audio import SR, load_audio
        x = np.abs(load_audio(path)).mean(axis=1)
        k = int(0.02 * SR)
        env = np.convolve(x, np.ones(k) / k, "same")
        on = np.nonzero(env > env.max() * 0.08)[0]
        if len(on):
            a0, a1 = on[0] / SR, on[-1] / SR
    except Exception:
        pass
    wts = [len(w.strip(".,;:!?\"'")) + 2 for w in words]
    tot = float(sum(wts)) or 1.0
    out, c = [], a0
    for wt in wts:
        d = (a1 - a0) * wt / tot
        out.append((c, c + d))
        c += d
    return out


def _ex_chunks(text, phrase):
    """The sample sentence as [(text, highlighted)] chunks: a highlighted run stays one chunk (never broken)."""
    from ..list_designs import _ex_tokens
    try:
        toks = _ex_tokens(text, phrase)
        if "*" not in str(text) and not any(hl for _, hl in toks):  # an idiom said by another person / tense
            loose = " ".join("(something)" if w.lower().strip(".,!?") in _ANY else w for w in str(phrase).split())
            if loose != phrase and loose.replace("(something)", "").strip():
                toks = _ex_tokens(text, loose)
    except Exception:
        toks = [(x, False) for x in " ".join(str(text).replace("*", "").split()).split(" ")]
    words = []  # (text, hl, glued to the previous: no space between, spoken word number)
    space = True
    wi = -1
    for tx, hl in toks:
        if tx == " ":
            space = True
            continue
        if space:
            wi += 1
        words.append([tx, bool(hl), not space, wi])
        space = False
    chunks = []  # [text, hl, glued, first word, last word]
    for tx, hl, glued, wi in words:
        if chunks and (glued or (hl and chunks[-1][1])):
            if glued and chunks[-1][1] == hl:
                chunks[-1][0] += tx
                continue
            if hl and chunks[-1][1] and not glued:
                chunks[-1][0] += " " + tx
                chunks[-1][4] = wi
                continue
            if glued:  # punctuation right after a pill: its own chunk with no space
                chunks.append([tx, hl, True, wi, wi])
                continue
        chunks.append([tx, hl, False, wi, wi])
    return chunks


def _slot(f, fb, c):
    """Room a sentence chunk takes on its line: its own width, plus half of what its bold form adds (the spoken word
    turns bold), or its pill for the word itself."""
    if c[1]:
        return fb.getlength(c[0]) + 20
    a = f.getlength(c[0])
    return a + max(0.0, fb.getlength(c[0]) - a) * 0.5


def _even_lines(chunks, widths, space, avail):
    """[(chunks, width)] lines of similar width (least squared free space, the last line free) — justified lines
    then get small, even gaps. Glued chunks (punctuation) never start a line."""
    n = len(chunks)
    INF = float("inf")
    best = [INF] * (n + 1)
    cut = [0] * (n + 1)
    best[0] = 0.0

    def width(i, j):
        w = 0.0
        for k in range(i, j):
            w += widths[k] + (space if k > i and not chunks[k][2] else 0)
        return w
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            if i > 0 and chunks[i][2]:
                continue
            w = width(i, j)
            if w > avail and j - i > 1:
                break
            free = max(0.0, avail - w)
            gaps = sum(1 for k in range(i + 1, j) if not chunks[k][2])
            gap = free / gaps if gaps else avail * 0.6  # the extra space each gap of a justified line gets
            cost = best[i] + avail * avail * 4 + (0 if j == n else gap * gap * max(1, gaps))  # fewest lines first
            if cost < best[j]:
                best[j], cut[j] = cost, i
    out, j = [], n
    while j > 0:
        i = cut[j]
        out.append((chunks[i:j], width(i, j)))
        j = i
    return out[::-1]


def _sprite_dot(d, col, soft=2.2):
    yy, xx = np.mgrid[0:d, 0:d]
    r = np.sqrt((xx - (d - 1) / 2) ** 2 + (yy - (d - 1) / 2) ** 2) / (d / 2)
    a = np.clip(np.exp(-(r ** 2) * soft) - 0.02, 0, 1)
    arr = np.zeros((d, d, 4), np.uint8)
    arr[..., :3] = col
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _sprite_star(d, col):
    """Four-point sparkle with a soft core."""
    yy, xx = np.mgrid[0:d, 0:d]
    x = (xx - (d - 1) / 2) / (d / 2)
    y = (yy - (d - 1) / 2) / (d / 2)
    arms = np.exp(-np.abs(x) * 18) * np.exp(-np.abs(y) * 2.2) + np.exp(-np.abs(y) * 18) * np.exp(-np.abs(x) * 2.2)
    core = np.exp(-(x ** 2 + y ** 2) * 14)
    a = np.clip(arms + core, 0, 1)
    arr = np.zeros((d, d, 4), np.uint8)
    arr[..., :3] = np.clip(np.array(col, float)[None, None] * (1 - core[..., None] * 0.6) + 255 * core[..., None] * 0.6, 0, 255)
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _ring(radius, width, col, a):
    """A thin glowing ring (shockwave)."""
    r = int(radius + width) + 4
    ss = 2
    m = Image.new("L", (2 * r * ss, 2 * r * ss), 0)
    ImageDraw.Draw(m).ellipse([(r - radius) * ss, (r - radius) * ss, (r + radius) * ss, (r + radius) * ss],
                              outline=255, width=max(1, int(width * ss)))
    m = m.resize((2 * r, 2 * r), Image.LANCZOS)
    return _solid(m, col, a)


def _check(d, col, width):
    """A check mark drawn in a d x d box."""
    ss = 3
    im = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(0.22 * d * ss, 0.52 * d * ss), (0.42 * d * ss, 0.72 * d * ss),
                             (0.78 * d * ss, 0.3 * d * ss)], fill=tuple(col) + (255,), width=int(width * ss),
                            joint="curve")
    return im.resize((d, d), Image.LANCZOS)


def _arabic_font(name):
    """The file of the Arabic font family `name` (a library family; empty / unknown = AR_DEFAULT)."""
    from ..fonts import find, resolve
    name = str(name or "").strip() or AR_DEFAULT
    fam = find(name)
    if fam is None:
        path = resolve(name)
        fam = find(name) or (None if path == resolve("") else {"main": path})
    if fam is None and name != AR_DEFAULT:
        return _arabic_font(AR_DEFAULT)
    return fam["main"] if fam else resolve("")


def _ar_words(path, line, size, color):
    """One image per Arabic word of `line`, all on one baseline: ([(image, advance)], space, ascent, pad).
    Words are shaped one by one (words never join across a space), so they can animate apart."""
    from ..core import _basic_font, _prep
    path = _basic_font(line) or path
    f = get_font(int(size), "Black", path)
    asc, desc = f.getmetrics()
    p = int(size * 0.35)
    old = _state["font"]
    _state["font"] = path  # _prep's missing-forms fix reads the current font
    try:
        out = []
        for wd in line.split():
            t2, kw = _prep(wd)
            adv = f.getlength(t2, **kw)
            im = Image.new("RGBA", (int(math.ceil(adv)) + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((p, p + asc), t2, font=f, fill=tuple(color[:3]) + (255,), anchor="ls", **kw)
            out.append((im, adv))
    finally:
        _state["font"] = old
    return out, f.getlength(" "), asc, p


def _brush_mask(w, h, seed):
    """A realistic paint stroke: wobbly edges, bristle streaks, a round wet start on the right and a dry, broken
    end on the left (it is painted right to left)."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(0, 1, w)
    y = np.arange(h, dtype=float)[:, None]

    def wave(amp):
        v = sum(np.sin(2 * np.pi * (f * xs + rng.uniform())) * amp / f for f in (1.2, 2.6, 5.3))
        return v + rng.normal(0, amp * 0.06, w)
    top = h * 0.1 + wave(h * 0.06)
    bot = h * 0.9 + wave(h * 0.06)
    a = np.clip((y - top[None, :]) / 2.5, 0, 1) * np.clip((bot[None, :] - y) / 2.5, 0, 1)
    rows = np.convolve(rng.normal(0, 1, h), np.ones(4) / 4, "same")
    a *= (0.78 + 0.22 * np.tanh(rows * 1.5))[:, None]  # bristle streaks
    yy = (np.arange(h) / h - 0.5) * 2
    start = 0.99 - 0.035 * yy ** 2 - rng.uniform(0, 0.01, h)  # round wet start (right)
    end = np.convolve(0.01 + 0.12 * rng.random(h), np.ones(3) / 3, "same")  # ragged dry end (left)
    x = xs[None, :]
    a *= np.clip((x - end[:, None]) / 0.025, 0, 1) * np.clip((start[:, None] - x) / 0.008, 0, 1)
    gaps = rng.random(h) < 0.3  # some bristles run dry before the end
    a *= np.where(gaps[:, None], np.clip((x - 0.06 - 0.2 * rng.random(h)[:, None]) / 0.08, 0, 1), 1)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L")


def _ribbon(w, h, col):
    """A ribbon banner with notched ends and a soft top light."""
    ss = 3
    W_, H_ = w * ss, h * ss
    n = h * 0.32 * ss
    m = Image.new("L", (W_, H_), 0)
    ImageDraw.Draw(m).polygon([(0, 0), (W_, 0), (W_ - n, H_ / 2), (W_, H_), (0, H_), (n, H_ / 2)], fill=255)
    m = m.resize((w, h), Image.LANCZOS)
    im = _grad_fill(m, _mix(col, (255, 255, 255), 0.12), _mix(col, (0, 0, 0), 0.12))
    return im


def _swoosh(w, h, col):
    """A hand-drawn tapered pen stroke under a line (drawn right to left, lifting at the end)."""
    ss = 3
    u = np.linspace(0, 1, 160)
    xs = (1 - u) * (w - 8) + 4
    ys = h * (0.42 + 0.12 * np.sin(np.pi * u)) - h * 0.32 * np.clip((u - 0.78) / 0.22, 0, 1) ** 2
    wd = h * 0.2 * np.sin(np.pi * np.clip(u * 1.08, 0, 1)) ** 0.7 + 1.5
    pts = [(x * ss, (y - d / 2) * ss) for x, y, d in zip(xs, ys, wd)] + \
          [(x * ss, (y + d / 2) * ss) for x, y, d in zip(xs[::-1], ys[::-1], wd[::-1])]
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return _solid(m.resize((w, h), Image.LANCZOS), col)


def _rotate_scale(im, scale, angle):
    if abs(scale - 1) > 0.004:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if abs(angle) > 0.05:
        im = im.rotate(angle, Image.BICUBIC, expand=True)
    return im


def _put(frame, im, cx, cy, alpha=1.0):
    if alpha <= 0.01:
        return
    composite(frame, fade(im, alpha), int(round(cx - im.width / 2)), int(round(cy - im.height / 2)))


# ------------------------------------------------------------------ the video
EXAMPLE = {
    "template": "wordsvideo",
    "settings": {"theme": "Royal Blue", "language": "ar", "fps": 30, "music": "Lo-fi Chill", "music_gain": 0.9,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@logolept AR EN", "font_file": "", "intro_sound": "Swoosh + impact",
                 "tick_sound": "Classic", "tick_gain": 1.0},
    "ending": {"intro": "الحلقة القادمة:", "question": "{count} more words\n[gold]for daily conversations",
               "cta": "كم كلمة كنت تعرف؟ اكتب الرقم في التعليقات"},
    "wordsvideo": {
        "title": "{count} Words to Sound Smarter",
        "subtitle": "كلمات إنجليزية ستبهر بها الجميع",
        "words": ("Resilient | مَرِن، سريع التعافي | /rɪˈzɪliənt/ | able to recover quickly from difficulties | "
                  "Kids are often more resilient than we think.\n"
                  "Overwhelmed | مُنهَك، غارق في المهام | /ˌəʊvəˈwelmd/ | having too much to deal with at once | "
                  "I felt overwhelmed by all the emails.\n"
                  "Grateful | مُمتنّ | /ˈɡreɪtfl/ | feeling thankful for something | "
                  "I'm so grateful for your help.\n"
                  "Reluctant | متردّد، غير راغب | /rɪˈlʌktənt/ | not willing to do something | "
                  "He was reluctant to ask for help.\n"
                  "Thrive | يزدهر، ينمو بقوة | /θraɪv/ | to grow or develop very well | "
                  "Plants thrive in warm sunlight.\n"
                  "Genuine | حقيقي، صادق | /ˈdʒenjuɪn/ | real and sincere, not fake | "
                  "She has a genuine smile."),
        "design": "paper",
        "arabic_font": "",
        "ar_style": "brush",
        "kind": "auto",
        "ex_reveal": "redbold",
        "pace": "normal",
        "pick": "roulette",
        "recap": True,
        "audio": [],
        "audio_gain": 1.0,
    },
}


class WordsVideo:
    def __init__(self, project):
        d = project.get("wordsvideo", {})
        s = project.get("settings", {})
        self.fps = int(s.get("fps") or 30)
        self.words = parse_words(d.get("words"))
        if not self.words:
            raise ValueError("Write at least one word: English | Arabic | IPA | English meaning | example sentence")
        self.n = n = len(self.words)
        self.look = L = DESIGNS.get(d.get("design") or "paper", DESIGNS["paper"])
        self.light = L["light"]
        self.pace = PACES.get(d.get("pace") or "normal", 1.0)
        self.pick = (d.get("pick") or "roulette") == "roulette"
        self.ar_style = d.get("ar_style") if d.get("ar_style") in AR_TIME else "brush"
        self.ex_reveal = d.get("ex_reveal") if d.get("ex_reveal") in dict((v, k) for k, v in EX_REVEALS) else "redbold"
        self.recap_on = d.get("recap", True) is not False
        self.audio_gain = float(d.get("audio_gain") or 1.0)
        self.handle = s.get("handle") or ""
        # a font picked in 🎨 Style & sound replaces the English font; the Arabic one is its own setting
        picked = _state["font"] if s.get("font_file") else None
        self.en_font = picked or EN_FONT
        self.ar_font = _arabic_font(d.get("arabic_font"))
        cnt = str(n)
        kind = d.get("kind") if d.get("kind") in KIND_LABEL or d.get("kind") == "auto" else "auto"
        multi = [len(w["en"].split()) > 1 for w in self.words]
        if kind == "auto":
            self.labels = [KIND_LABEL["expression" if m else "word"][0] for m in multi]
            self.kicker = ("EXPRESSIONS" if all(multi) else "WORDS & EXPRESSIONS" if any(multi) else "WORDS") \
                if n != 1 else self.labels[0]
            auto_title = "English Expressions" if all(multi) else "English Words"
        else:
            self.labels = [KIND_LABEL[kind][0]] * n
            self.kicker = KIND_LABEL[kind][1 if n != 1 else 0]
            auto_title = KIND_TITLE[kind]
        self.title = str(d.get("title") or "{count} " + auto_title).replace("{count}", cnt)
        self.subtitle = str(d.get("subtitle") or "").replace("{count}", cnt)
        e = project.get("ending", {})
        self.e_intro = str(e.get("intro") or "").replace("{count}", cnt)
        self.e_q = parse_lines(str(e.get("question") or "").replace("{count}", cnt), ["white"])
        self.e_cta = str(e.get("cta") or "").replace("{count}", cnt)
        self.acc = [L["acc"][k % len(L["acc"])] for k in range(n)]
        self._clips(d.get("audio") or [])
        self._layout_header()
        self._layout_bubbles()
        self._timeline()
        self._sprites()
        self._cards = OrderedDict()
        self.silences = []
        self.chunk = 6

    # ============================================================ audio clips
    def _clips(self, paths):
        self.clip = {}
        for p in paths or []:
            if not p or not os.path.isfile(str(p)):
                continue
            key = clip_key(p)
            if key and 1 <= key[0] <= self.n and key[1] in ("w", "e"):
                try:
                    self.clip[(key[0] - 1, key[1])] = (p, audio_length(p))
                except Exception:
                    pass

    # ============================================================ header
    def _layout_header(self):
        L = self.look
        a0 = self.acc[0]
        top_c = bot_c = L["head"]
        size, lines = _fit_lines(lambda x, s: _adv(self.en_font, x, s, "Black"), self.title, 92, 50, 920, 2)
        self.h_lines = []
        y = 300
        for ln in lines:
            im, base, adv, p = _ltext(self.en_font, ln, size, "Black", (255, 255, 255))
            m = im.getchannel("A")
            g = _grad_fill(m, top_c, bot_c)
            sh = _glow(m, (0, 0, 0), 10, 0.0 if self.light else 0.25)
            lay = Image.new("RGBA", sh.size, (0, 0, 0, 0))
            lay.alpha_composite(g, (40, 32))
            sh.alpha_composite(lay)
            self.h_lines.append((sh, y))
            y += int(size * 1.08)
        self.h_sub = None
        if self.subtitle:
            im = text_img_in(self.ar_font, self.subtitle, 62, L["head_soft"], "Bold", max_w=920)
            self.h_sub = (im, y + 18)
            y += 18 + im.height - 30
        # kicker pill: ENGLISH · 6 WORDS
        txt = f"ENGLISH  ·  {self.n} {self.kicker}"
        k_im, _, adv, p = _ltext(EN_FONT, txt, 28, "Bold", _on(a0))
        kw, kh = int(adv) + 56, 56
        m = _rr_mask(kw, kh, kh / 2)
        pill = _solid(m, a0)
        pill.alpha_composite(k_im, (28 - p, (kh - k_im.height) // 2 + 1))
        self.h_kick = (pill, 215)
        self.header_bottom = y + 10
        self.bar_y = self.header_bottom + 6

    def _mask_rise(self, frame, im, cx, cy, p, alpha=1.0):
        """Motion-design reveal: the text slides up from behind an invisible line (cropped to its own box)."""
        if p <= 0 or alpha <= 0.01:
            return
        e = _out3(p)
        dy = int((1 - e) * im.height * 0.9)
        part = im.crop((0, 0, im.width, im.height - dy)) if dy > 0 else im
        x = int(cx - im.width / 2)
        y = int(cy - im.height / 2) + dy
        composite(frame, fade(part, alpha * min(1, p * 1.6)), x, y)

    def _header(self, frame, t, alpha):
        if alpha <= 0.01:
            return
        pill, ky = self.h_kick
        p = prog(t, 0.12, 0.5)
        if p > 0:
            sc = 0.6 + 0.4 * _spring(p * 0.9)
            _put(frame, _rotate_scale(pill, sc, 0), 540, ky, alpha * min(1, p * 2))
        for i, (im, y) in enumerate(self.h_lines):
            self._mask_rise(frame, im, 540, y + im.height / 2 - 60, prog(t, 0.3 + 0.13 * i, 0.85 + 0.13 * i), alpha)
        if self.h_sub:
            im, y = self.h_sub
            p = prog(t, 0.7, 1.2)
            if p > 0:  # written in from the right
                e = _out3(p)
                w = max(1, int(im.width * e))
                composite(frame, fade(im.crop((im.width - w, 0, im.width, im.height)), alpha * min(1, p * 2)),
                          int(540 + im.width / 2 - w), int(y))
        # progress line: fills word by word
        p = prog(t, 0.9, 1.4)
        if self.recap_on:  # the recap title takes its place
            alpha *= 1 - prog(t, self.R0, self.R0 + 0.35)
        if p > 0 and alpha > 0.01:
            bw = int(420 * _out3(p))
            y = self.bar_y + 40
            track = self.look["head"]
            lay = Image.new("RGBA", (bw + 2, 8), (0, 0, 0, 0))
            ImageDraw.Draw(lay).rounded_rectangle([0, 0, bw + 1, 7], 4, fill=tuple(track) + (int(34 * alpha),))
            fill = self._progress(t)
            if fill > 0:
                ImageDraw.Draw(lay).rounded_rectangle([0, 0, max(8, int(bw * fill)), 7], 4,
                                                      fill=tuple(self.acc[min(self.n - 1, int(fill * self.n - 1e-6))])
                                                      + (int(235 * alpha),))
            composite(frame, lay, 540 - bw // 2, y)

    def _progress(self, t):
        done = 0.0
        for k, sg in enumerate(self.seg):
            if t >= sg["out"]:
                done = k + 1
            elif t >= sg["pop"]:
                done = k + prog(t, sg["pop"], sg["out"])
        return done / self.n

    # ============================================================ bubbles
    def _bubble_imgs(self, k, size):
        L = self.look
        w = self.words[k]
        acc = self.acc[k]
        txt_im, base, adv, p = _ltext(self.en_font, w["en"], size, "Bold", L["ink"])
        bh = int(size * 1.95)
        dot = int(bh * 0.62)
        bw = int(adv) + dot + int(size * 1.25) + 16
        m = _rr_mask(bw, bh, bh / 2)
        inner = Image.new("L", (bw, bh), 0)
        inner.paste(_rr_mask(bw - 5, bh - 5, bh / 2 - 2.5), (2, 2))
        edge = Image.fromarray(np.clip(np.array(m, int) - np.array(inner, int), 0, 255).astype(np.uint8))
        tx = dot + int(size * 0.55) + 8
        ty = (bh - txt_im.height) // 2 + int(size * 0.04)
        dx = int(bh * 0.19)
        num = f"{k + 1}"

        def chip(col, ink, check=False):
            c = Image.new("RGBA", (dot, dot), (0, 0, 0, 0))
            cm = Image.new("L", (dot * 3, dot * 3), 0)
            ImageDraw.Draw(cm).ellipse([0, 0, dot * 3 - 1, dot * 3 - 1], fill=255)
            cm = cm.resize((dot, dot), Image.LANCZOS)
            c.alpha_composite(_solid(cm, col))
            if check:
                c.alpha_composite(_check(dot, ink, max(3, dot * 0.11)))
            else:
                ni, nb, nadv, npd = _ltext(EN_FONT, num, int(dot * 0.5), "Bold", ink)
                c.alpha_composite(ni, (int((dot - nadv) / 2) - npd, int(dot / 2 + dot * 0.18) - nb))
            return c

        # a soft shadow under the pill (drawn on a bigger canvas: SH px of room on every side)
        SH = 18
        shadow = Image.new("RGBA", (bw + 2 * SH, bh + 2 * SH), (0, 0, 0, 0))
        sm = Image.new("L", shadow.size, 0)
        sm.paste(m, (SH, SH + 5))
        shadow.alpha_composite(_solid(sm.filter(ImageFilter.GaussianBlur(8)), (20, 24, 40), 0.16 if self.light else 0.3))

        def on_shadow(im):
            out = shadow.copy()
            out.alpha_composite(im, (SH, SH))
            return out

        # idle: white pill, hairline edge, the number in an accent chip
        idle = _solid(m, L["card"])
        idle.alpha_composite(_solid(edge, L["ink"], 0.08))
        idle.alpha_composite(chip(acc, _on(acc)), (dx, (bh - dot) // 2))
        idle.alpha_composite(txt_im, (tx - p, ty))
        # done: filled with the accent, a check in the chip
        done = _solid(m, acc)
        ink = _on(acc)
        done.alpha_composite(chip(ink, acc, check=True), (dx, (bh - dot) // 2))
        dt, _, _, dp = _ltext(self.en_font, w["en"], size, "Bold", ink)
        done.alpha_composite(dt, (tx - dp, ty))
        glow = _glow(m, acc, 18, 0.45, grow=3)
        return dict(idle=on_shadow(idle), done=on_shadow(done), glow=glow, w=bw, h=bh)

    def _layout_bubbles(self):
        """Bubbles in staggered rows filling the float zone, at the biggest size that fits."""
        y0, y1 = ZONE
        avail_h = y1 - max(y0, self.header_bottom + 90)
        top = y1 - avail_h
        for size in range(66, 25, -2):
            ws = [int(_adv(self.en_font, w["en"], size, "Bold")) + int(size * 1.95 * 0.62) + int(size * 1.25) + 16
                  for w in self.words]
            bh = int(size * 1.95)
            rows, cur, cw = [], [], 0
            for k, w in enumerate(ws):
                need = w if not cur else cw + 34 + w
                if cur and need > 960:
                    rows.append(cur)
                    cur, cw = [k], w
                else:
                    cur.append(k)
                    cw = need
            rows.append(cur)
            if len(rows) * (bh + 30) <= avail_h and max(ws) <= 980:
                break
        self.b_size = size
        self.bub = [self._bubble_imgs(k, size) for k in range(self.n)]
        pitch = min(avail_h / len(rows), (bh + 30) * 1.75)
        ys = top + (avail_h - pitch * len(rows)) / 2 + pitch / 2
        rng = np.random.default_rng(11)
        self.pos = [None] * self.n
        for r, row in enumerate(rows):
            widths = [self.bub[k]["w"] for k in row]
            free = 1000 - sum(widths)
            gap = min(free / (len(row) + 1), 120)
            x = 540 - (sum(widths) + gap * (len(row) - 1)) / 2
            shift = (1 if r % 2 else -1) * min(40, max(0, (free - gap * (len(row) - 1)) / 2 - 10))
            for j, k in enumerate(row):
                jx = rng.uniform(-1, 1) * min(14, gap / 4)
                jy = rng.uniform(-1, 1) * min(22, (pitch - bh) / 3)
                self.pos[k] = (x + widths[j] / 2 + shift + jx, ys + r * pitch + jy)
                x += widths[j] + gap
        self.phase = [(rng.uniform(0, 6.3), rng.uniform(0, 6.3), rng.uniform(0.7, 1.1), rng.uniform(0.9, 1.4))
                      for _ in range(self.n)]

    def _float(self, k, t):
        a, b, f1, f2 = self.phase[k]
        x, y = self.pos[k]
        return x + 9 * math.sin(t * f1 + a), y + 13 * math.sin(t * f2 + b)

    # ============================================================ timeline
    def _timeline(self):
        P = self.pace
        n = self.n
        self.spawn = min(0.09, 0.9 / max(1, n))
        self.b0 = 1.05
        t = self.b0 + self.spawn * n + 0.75
        self.intro_end = t
        self.seg = []
        rng = np.random.default_rng(5)
        self.voices = []
        for k, w in enumerate(self.words):
            sg = {"s": t}
            waiting = list(range(k, n))
            hops = []
            if self.pick and len(waiting) >= 3:
                order = [j for j in waiting if j != k]
                seq = []
                for i in range(5):
                    c = order[int(rng.integers(len(order)))]
                    if seq and c == seq[-1]:
                        c = order[(order.index(c) + 1) % len(order)]
                    seq.append(c)
                seq.append(k)
                r = 0.85 * P
                times = [t + r * (i / len(seq)) ** 1.45 for i in range(len(seq))]
                hops = list(zip(times, seq))
                t += r
            sg["hops"] = hops
            sg["sel"] = t
            sg["fly0"] = t + 0.22
            sg["fly1"] = sg["fly0"] + 0.34
            sg["pop"] = sg["fly1"] - 0.05
            pop = sg["pop"]
            sg["w0"] = pop + 0.16
            sg["lstep"] = min(0.04, 0.55 / max(1, len(w["en"])))
            w_end = sg["w0"] + sg["lstep"] * len(w["en"]) + 0.3
            sg["ipa"] = pop + 0.55
            clip_end = 0
            if (k, "w") in self.clip:
                path, ln = self.clip[(k, "w")]
                at = pop + 0.4
                self.voices.append((at, path))
                clip_end = at + ln
                sg["say"] = (at, at + ln)
            else:
                sg["say"] = (sg["ipa"] + 0.15, sg["ipa"] + 0.95)
            sg["ar"] = max(w_end, sg["ipa"] + 0.35, clip_end + 0.1)
            lead, step = AR_TIME[self.ar_style]
            nwd = len(w["ar"].split())
            sg["ar_words"] = [sg["ar"] + lead + step * j for j in range(nwd)]
            ar_len = (lead + step * nwd + 0.3 + (0.45 if self.ar_style == "swoosh" else 0)) if nwd else 0
            sg["ar_mark"] = sg["ar"] + lead + step * nwd + 0.02  # the swoosh is drawn after the words
            # impacts: the pop, and the slammed words (a camera punch + shake)
            sg["impacts"] = [(sg["pop"] + 0.1, 1.0)] + [(a, 0.55 if self.ar_style == "stamp" else 0.2)
                                                        for a in (sg["ar_words"] if self.ar_style in ("stamp", "brush")
                                                                  else [])]
            nxt = sg["ar"] + max(ar_len, 0.5 * P if nwd else 0)
            sg["df"] = nxt if w["df"] else None
            if w["df"]:
                nxt += 0.55 * P
            if w["ex"]:
                sg["ex"] = nxt + 0.25 * P
                spoken = w["ex"].replace("*", "").split()
                nwords = len(spoken)
                t0 = sg["ex"] + 0.45
                if (k, "e") in self.clip:  # every word lights up exactly when it is heard
                    path, ln = self.clip[(k, "e")]
                    self.voices.append((t0, path))
                    rel = clip_word_times(path, ln, spoken)
                    end = t0 + max(ln, rel[-1][1] if rel else 0) + 1.0
                else:  # no voice: a calm reading pace
                    step = (0.12 if self.ex_reveal == "appear" else 0.32) * P
                    rel = [(i * step, i * step + step * 0.92) for i in range(nwords)]
                    end = t0 + nwords * step + (1.4 + 0.1 * nwords) * P
                sg["extimes"] = [(t0 + a, t0 + b) for a, b in rel]
            else:
                sg["ex"] = None
                sg["extimes"] = []
                end = nxt + (1.8 + (0.6 if w["df"] else 0)) * P
            sg["end"] = end
            sg["out"] = end + 0.55
            self.seg.append(sg)
            t = sg["out"] + 0.12
        self.R0 = t + 0.25
        if self.recap_on:
            self.rstep = min(0.16, 1.6 / self.n)
            self.E0 = self.R0 + 0.5 + self.rstep * n + 2.4 + 0.08 * n
        else:
            self.E0 = self.R0
        self.has_end = bool(self.e_intro or self.e_q or self.e_cta)
        self.base_duration = self.E0 + (4.6 if self.has_end else 0.8)
        self.dur = self.base_duration
        self.cover_time = self.intro_end - 0.1
        if self.recap_on:
            self._layout_recap()

    # ============================================================ background + particles
    def _sprites(self):
        L = self.look
        key = (L["bg"], L["dots"])
        if key not in _BG_CACHE:  # clean background: a soft gradient + a faint dot pattern (it drifts slowly)
            y = np.linspace(0, 1, H)[:, None, None]
            c0, c1 = (np.array(c, float) for c in L["bg"])
            arr = np.repeat(c0 * (1 - y) + c1 * y, W, axis=1)
            base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
            dots = Image.new("L", (W, H + DOT_GAP), 0)
            dd = ImageDraw.Draw(dots)
            for gy in range(DOT_GAP // 2, H + DOT_GAP, DOT_GAP):
                for gx in range(DOT_GAP // 2, W, DOT_GAP):
                    dd.ellipse([gx - 2.2, gy - 2.2, gx + 2.2, gy + 2.2], fill=255)
            _BG_CACHE[key] = (base, _solid(dots, L["dots"], 0.16 if self.light else 0.12))
        self.bg_base, self.bg_dots = _BG_CACHE[key]
        # confetti for the pop: crisp discs in the accent colours
        self.confetti = {}
        for c in set(self.acc):
            ss = 4
            m = Image.new("L", (24 * ss, 24 * ss), 0)
            ImageDraw.Draw(m).ellipse([0, 0, 24 * ss - 1, 24 * ss - 1], fill=255)
            self.confetti[tuple(c)] = _solid(m.resize((24, 24), Image.LANCZOS), c)

    def _background(self, t, dim):
        frame = self.bg_base.copy()
        off = int(t * 6) % DOT_GAP
        frame.alpha_composite(self.bg_dots.crop((0, off, W, off + H)))
        if dim > 0:  # the world steps back while a card is up
            veil = (24, 28, 44) if self.light else (16, 20, 30)
            frame.alpha_composite(Image.new("RGBA", (W, H), veil + (int(255 * dim * (0.15 if self.light else 0.35)),)))
        return frame

    # ============================================================ the card of a word
    def _card(self, k):
        if k in self._cards:
            self._cards.move_to_end(k)
            return self._cards[k]
        for sc in (1.0, 0.93, 0.86, 0.8, 0.74, 0.68, 0.62):
            c = self._build_card(k, sc)
            if c["ch"] <= CARD_MAX:
                break
        self._cards[k] = c
        while len(self._cards) > 3:
            self._cards.popitem(last=False)
        return c

    def _build_card(self, k, sc):
        L = self.look
        w = self.words[k]
        acc = self.acc[k]
        acc2, acc3 = self.acc[(k + 1) % self.n] if self.n > 1 else L["acc"][1], L["acc"][(k + 2) % len(L["acc"])]
        if acc2 == acc:
            acc2 = L["acc"][(k + 1) % len(L["acc"])]
        ink, soft = L["ink"], L["soft"]
        acc_txt = _mix(acc, (0, 0, 0), 0.12)  # the card is white: a slightly deeper accent reads better
        inner = CW - 2 * PAD
        els = []  # dict(kind, img, x, y (top-left in card coords), ...)
        y = 46
        # ---- top row: number chip + label + window dots
        chip_d = 72
        cm = Image.new("L", (chip_d * 3, chip_d * 3), 0)
        ImageDraw.Draw(cm).ellipse([0, 0, chip_d * 3 - 1, chip_d * 3 - 1], fill=255)
        cm = cm.resize((chip_d, chip_d), Image.LANCZOS)
        chip = Image.new("RGBA", (chip_d, chip_d), (0, 0, 0, 0))
        chip.alpha_composite(_grad_fill(cm, _mix(acc, (255, 255, 255), 0.2), _mix(acc, (0, 0, 0), 0.1)))
        ni, nb, nadv, npd = _ltext(EN_FONT, f"{k + 1:02d}", 30, "Bold", _on(acc))
        chip.alpha_composite(ni, (int((chip_d - nadv) / 2) - npd, int(chip_d / 2 + 11) - nb))
        els.append(dict(kind="pop", img=chip, x=PAD, y=y, t=0.22))
        lab, lb, ladv, lp = _ltext(EN_FONT, f"{self.labels[k]} {k + 1} OF {self.n}", 27, "Bold", soft)
        els.append(dict(kind="slide", img=lab, x=PAD + chip_d + 20 - lp, y=y + chip_d / 2 - lb + 10, t=0.3))
        for j, c in enumerate((acc, acc2, acc3)):
            dm = Image.new("L", (54, 54), 0)
            ImageDraw.Draw(dm).ellipse([0, 0, 53, 53], fill=255)
            dm = dm.resize((18, 18), Image.LANCZOS)
            els.append(dict(kind="pop", img=_solid(dm, c, 0.9), x=CW - PAD - 18 - j * 30, y=y + chip_d / 2 - 9,
                            t=0.36 + 0.06 * j))
        y += chip_d + int(34 * sc)
        # ---- the word (letters drop in)
        wsize, wlines = _fit_lines(lambda x, s: _adv(self.en_font, x, s, "Black"), w["en"], int(138 * sc), 58, inner, 2)
        top_c, bot_c = ink, _mix(ink, acc, 0.35)
        n0 = 0
        for ln in wlines:
            im, base, adv, p = _ltext(self.en_font, ln, wsize, "Black", (255, 255, 255))
            m = im.getchannel("A")
            g = _grad_fill(m, top_c, bot_c)
            word = Image.new("RGBA", im.size, (0, 0, 0, 0))
            word.alpha_composite(g)
            cuts = [p + _adv(self.en_font, ln[:i], wsize, "Black") for i in range(len(ln) + 1)]
            # crop the box to the ink so the line pitch is tight
            top_ink = base - int(wsize * 0.78)
            bot_ink = base + int(wsize * 0.26)
            word = word.crop((0, max(0, top_ink - 10), word.width, min(word.height, bot_ink + 14)))
            x = (CW - adv) / 2 - p
            els.append(dict(kind="letters", img=word, x=x, y=y - 6, cuts=cuts, n0=n0))
            n0 += len(ln)
            y += int((bot_ink - top_ink) + wsize * 0.12)
        y += int(18 * sc)
        # ---- IPA pill with a speaker
        if w["ipa"]:
            isz = int(40 * sc)
            it, ib, iadv, ip = _ltext(IPA_FONT, w["ipa"], isz, "Bold", acc_txt)
            ph = int(isz * 1.75)
            spk = int(ph * 0.62)
            pw = int(iadv) + spk + int(isz * 1.6)
            m = _rr_mask(pw, ph, ph / 2)
            pill = _solid(m, acc, 0.1)
            ring = Image.new("L", (pw, ph), 0)
            ring.paste(_rr_mask(pw - 4, ph - 4, ph / 2 - 2), (2, 2))
            ring = Image.fromarray(np.clip(np.array(m, int) - np.array(ring, int), 0, 255).astype(np.uint8))
            pill.alpha_composite(_solid(ring, acc, 0.55))
            sx, sy = int(isz * 0.55), (ph - spk) // 2
            ss = 3
            sp = Image.new("RGBA", (spk * ss, spk * ss), (0, 0, 0, 0))
            dd = ImageDraw.Draw(sp)
            u = spk * ss
            dd.polygon([(0.08 * u, 0.36 * u), (0.3 * u, 0.36 * u), (0.56 * u, 0.12 * u), (0.56 * u, 0.88 * u),
                        (0.3 * u, 0.64 * u), (0.08 * u, 0.64 * u)], fill=tuple(acc_txt) + (255,))
            dd.arc([0.5 * u, 0.3 * u, 0.82 * u, 0.7 * u], -50, 50, fill=tuple(acc_txt) + (255,), width=int(0.07 * u))
            sp = sp.resize((spk, spk), Image.LANCZOS)
            pill.alpha_composite(sp, (sx, sy))
            pill.alpha_composite(it, (sx + spk + int(isz * 0.3) - ip, int(ph / 2 + isz * 0.36) - ib))
            els.append(dict(kind="pop", img=pill, x=(CW - pw) / 2, y=y, t="ipa"))
            self_wave = dict(kind="wave", x=(CW - pw) / 2 + sx + spk * 0.62, y=y + ph / 2, r=spk * 0.42, col=acc_txt)
            els.append(self_wave)
            y += ph + int(30 * sc)
        # ---- ornament divider
        dw, dh = 560, 22
        div = Image.new("RGBA", (dw, dh), (0, 0, 0, 0))
        xs = np.abs(np.linspace(-1, 1, dw))
        line = np.zeros((dh, dw, 4), np.uint8)
        line[..., :3] = acc
        a_line = np.clip((1 - xs) * 1.4, 0, 1) * 200
        line[dh // 2 - 1:dh // 2 + 1, :, 3] = a_line.astype(np.uint8)
        line[:, dw // 2 - 24:dw // 2 + 24, 3] = 0
        div = Image.fromarray(line, "RGBA")
        dm = Image.new("L", (dh * 3, dh * 3), 0)
        ImageDraw.Draw(dm).polygon([(dh * 1.5, 0), (dh * 3 - 1, dh * 1.5), (dh * 1.5, dh * 3 - 1), (0, dh * 1.5)], fill=255)
        dm = dm.resize((dh, dh), Image.LANCZOS)
        div.alpha_composite(_solid(dm, acc), (dw // 2 - dh // 2, 0))
        for side in (-1, 1):
            sm = dm.resize((10, 10), Image.LANCZOS)
            div.alpha_composite(_solid(sm, acc, 0.7), (dw // 2 + side * 30 - 5, dh // 2 - 5))
        els.append(dict(kind="divider", img=div, x=(CW - dw) / 2, y=y, t="ipa+"))
        y += dh + int(26 * sc)
        # ---- Arabic meaning: word by word, right to left, with the chosen effect (AR_STYLES)
        if w["ar"]:
            st = self.ar_style
            lead, step = AR_TIME[st]
            asz, alines = _fit_lines(lambda x, s_: _ink_w(self.ar_font, x, s_, "Black"), w["ar"], int(92 * sc), 44,
                                     inner - (100 if st == "ribbon" else 20), 2)
            txt_col = _on(acc) if st == "ribbon" else _mix(acc, (0, 0, 0), 0.22)
            j = 0
            y += int(asz * 0.1)
            for li, ln in enumerate(alines):
                words, space, asc, p = _ar_words(self.ar_font, ln, asz, txt_col)
                total = sum(a_ for _, a_ in words) + space * (len(words) - 1)
                base = y + asz * 1.0  # the baseline of this line
                if st == "brush":
                    bw_, bh_ = int(total + 70), int(asz * 1.3)
                    mark = _solid(_brush_mask(bw_, bh_, 7 + k * 13 + li), acc, 0.34)
                    els.append(dict(kind="armark", img=mark, x=(CW - bw_) / 2, y=base - asz * 0.9, t="ar",
                                    d=step * len(words) * li, dur=lead + step * len(words) + 0.08))
                elif st == "ribbon":
                    bw_, bh_ = int(total + 130), int(asz * 1.45)
                    els.append(dict(kind="armark", img=_ribbon(bw_, bh_, acc), x=(CW - bw_) / 2, y=base - asz * 1.0,
                                    t="ar", d=step * len(words) * li, dur=lead + step * len(words) + 0.05))
                xr = CW / 2 + total / 2
                for im, adv in words:
                    x0 = xr - adv
                    els.append(dict(kind="arword", img=im, x=x0 - p, y=base - p - asc, t="ar", d=lead + step * j,
                                    style=st))
                    if st == "stamp":
                        rng = np.random.default_rng(k * 31 + j)
                        dots = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.55, 0.8), int(rng.uniform(7, 15)))
                                for _ in range(7)]
                        els.append(dict(kind="splat", cx=x0 + adv / 2, cy=base - asz * 0.35, rx=adv / 2 + 20,
                                        ry=asz * 0.6, dots=dots, col=acc, t="ar", d=lead + step * j + 0.12))
                    xr = x0 - space
                    j += 1
                if st == "swoosh":
                    sw, sh_ = int(total + 50), int(asz * 0.55)
                    els.append(dict(kind="armark", img=_swoosh(sw, sh_, acc), x=(CW - sw) / 2, y=base + asz * 0.12,
                                    t="ar", d=lead + step * sum(len(x.split()) for x in alines) + 0.02, dur=0.42))
                y = int(base + asz * (0.62 if st != "ribbon" else 0.72)) + (int(asz * 0.15) if li + 1 < len(alines) else 0)
            y += int(26 * sc)
        # ---- English meaning
        if w["df"]:
            dsz, dlines = _fit_lines(lambda x, s: _adv(self.en_font, x, s, "Medium"), w["df"], int(40 * sc), 28, inner, 3)
            for i, ln in enumerate(dlines):
                im, base, adv, p = _ltext(self.en_font, ln, dsz, "Medium", soft)
                els.append(dict(kind="rise", img=im, x=(CW - adv) / 2 - p, y=y - (base - dsz), t="df", d=0.09 * i))
                y += int(dsz * 1.38)
            y += int(10 * sc)
        # ---- example panel
        if w["ex"]:
            y += int(26 * sc)
            pw = inner
            chunks = _ex_chunks(w["ex"], w["en"])
            best = None  # the biggest size whose justified lines keep their gaps small (<= ~0.9 em), at most 4 lines
            for esz in range(int(46 * sc), max(28, int(36 * sc)) - 1, -1):
                f = get_font(esz, "SemiBold", self.en_font)
                fb = get_font(esz, "Black", self.en_font)
                sp_w = f.getlength(" ")
                lines = _even_lines(chunks, [_slot(f, fb, c) for c in chunks], sp_w, pw - 100)
                worst = max([(pw - 100 - wd) / max(1, sum(1 for i, c in enumerate(cur) if i and not c[2])) / esz
                             for cur, wd in lines[:-1]] or [0])
                score = (len(lines) > 4, worst > GAP_MAX, worst if worst > GAP_MAX else -esz)
                if best is None or score < best[0]:
                    best = (score, esz, lines, sp_w)
            _, esz, lines, sp_w = best
            pitch = int(esz * 1.62)
            top_pad = int(esz * 1.25)
            ph = top_pad + pitch * len(lines) + int(esz * 0.55)
            pm = _rr_mask(pw, ph, 34)
            panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            panel.alpha_composite(_solid(pm, _mix(acc, (255, 255, 255), 0.92)))
            bar = _rr_mask(8, ph - 60, 4)
            panel.alpha_composite(_solid(bar, acc, 0.9), (26, 30))
            els.append(dict(kind="panel", img=panel, x=PAD, y=y, t="ex"))
            tag, tb, tadv, tp = _ltext(EN_FONT, "EXAMPLE", 24, "Bold", _on(acc))
            tw_, th_ = int(tadv) + 36, 40
            tg = _solid(_rr_mask(tw_, th_, 20), acc)
            tg.alpha_composite(tag, (18 - tp, int(th_ / 2 + 9) - tb))
            els.append(dict(kind="pop", img=tg, x=PAD + 44, y=y - th_ / 2, t="ex", d=0.12))
            # tokens: justified lines (the last one starts at the left), each chunk in a slot wide enough for its
            # bold form, so a word turning bold never moves the others
            red = RED if self.ex_reveal == "redbold" else _mix(acc, (0, 0, 0), 0.15)
            left = PAD + 60
            avail = pw - 100
            if self.ex_reveal == "marker":
                els.append(dict(kind="exmark", rects=[], col=acc))
                mark = els[-1]
            ly = y + top_pad + int(esz * 0.75)
            for li, (cur, width) in enumerate(lines):
                gaps = sum(1 for i, c in enumerate(cur) if i and not c[2])
                last = li == len(lines) - 1
                extra = min((avail - width) / gaps, esz * GAP_MAX) if gaps and not last else 0
                x = left
                for i, (tx, hl, glued, w0, w1) in enumerate(cur):
                    if i and not glued:
                        x += sp_w + extra
                    n_im, base, adv, p = _ltext(self.en_font, tx, esz, "SemiBold", ink)
                    b_im, bb, badv, bp = _ltext(self.en_font, tx, esz, "Black", red)
                    sw = adv + max(0.0, badv - adv) * 0.5
                    e = dict(kind="tok", x=x, y=ly, sw=sw, w0=w0, w1=w1, hl=hl, n=(n_im, base, adv, p),
                             b=(b_im, bb, badv, bp))
                    if hl:  # the word itself: on an accent pill once it is spoken
                        h_im, hb, hadv, hp = _ltext(self.en_font, tx, esz, "Black", _on(acc))
                        pwid, pht = int(hadv) + 20, int(esz * 1.32)
                        pl = Image.new("RGBA", (pwid + 2 * hp, h_im.height), (0, 0, 0, 0))
                        pl.alpha_composite(_grad_fill(_rr_mask(pwid, pht, 14), _mix(acc, (255, 255, 255), 0.12), acc),
                                           (hp, int(hb - esz * 0.98)))
                        pl.alpha_composite(h_im, (10, 0))
                        e["pill"] = (pl, hb, pwid, hp)
                        e["n"] = _ltext(self.en_font, tx, esz, "Black", ink)  # bold before it is spoken: fills its room
                        sw = pwid
                        e["sw"] = sw
                    if self.ex_reveal == "marker":
                        mark["rects"].append((w0, w1, x - 8, ly - esz * 0.95, x + sw + 8, ly + esz * 0.3))
                    els.append(e)
                    x += sw
                ly += pitch
            y += ph
        y += 54
        ch = int(y)
        return self._card_body(k, ch, els, acc, acc2, acc3) | dict(ch=ch, els=els, ntok=sum(1 for e in els if e["kind"] == "tok"))

    def _card_body(self, k, ch, els, acc, acc2, acc3):
        L = self.look
        cw = CW
        m = _rr_mask(cw, ch, 48)
        full = (cw + 2 * MARGIN, ch + 2 * MARGIN)
        body = Image.new("RGBA", full, (0, 0, 0, 0))
        shadow = _glow(m, (20, 24, 40), 26, 0.22 if self.light else 0.45)
        body.alpha_composite(shadow, (MARGIN - 52, MARGIN - 52 + 18))
        card = _solid(m, L["card"])
        strip = Image.new("L", (cw, ch), 0)  # accent strip along the top, clipped to the rounded corners
        strip.paste(255, (0, 0, cw, 14))
        strip = Image.fromarray(np.minimum(np.array(strip), np.array(m)).astype(np.uint8))
        card.alpha_composite(_solid(strip, acc))
        inner = Image.new("L", (cw, ch), 0)
        inner.paste(_rr_mask(cw - 4, ch - 4, 46), (2, 2))
        hair = Image.fromarray(np.clip(np.array(m, int) - np.array(inner, int), 0, 255).astype(np.uint8))
        card.alpha_composite(_solid(hair, L["ink"], 0.08))
        body.alpha_composite(card, (MARGIN, MARGIN))
        return dict(body=body)

    def _when(self, sg, key):
        return {"ipa": sg["ipa"], "ipa+": sg["ipa"] + 0.12, "ar": sg["ar"], "df": sg["df"] or 0,
                "ex": sg["ex"] or 0}.get(key, sg["pop"] + key if isinstance(key, (int, float)) else 0)

    def _card_frame(self, k, t):
        sg = self.seg[k]
        c = self._card(k)
        img = c["body"].copy()
        say0, say1 = sg["say"]
        for e in c["els"]:
            kind = e["kind"]
            if kind == "splat":  # ink drops thrown out by a slammed word
                u = t - self._when(sg, "ar") - e["d"]
                if 0 < u < 0.5:
                    q = _out3(u / 0.5)
                    for ang, r0, sz in e["dots"]:
                        rr = r0 + 0.55 * q
                        dot = _rotate_scale(self.confetti[tuple(e["col"])], sz / 24 * (1 - 0.4 * q), 0)
                        px = MARGIN + e["cx"] + math.cos(ang) * e["rx"] * rr * 1.3
                        py = MARGIN + e["cy"] + math.sin(ang) * e["ry"] * rr * 1.3
                        composite(img, fade(dot, 1 - u / 0.5), int(px - dot.width / 2), int(py - dot.height / 2))
                continue
            if kind == "tok":
                self._token(img, e, t, sg)
                continue
            if kind == "exmark":
                self._ex_marker(img, e, t, sg)
                continue
            if kind == "wave":
                if say0 <= t <= say1 + 0.2:
                    u = (t - say0) * 5
                    for i in range(2):
                        ph = (u + i * 0.5) % 1.0
                        r = e["r"] * (1 + ph * 1.5)
                        ring = _ring(r, 3, e["col"], (1 - ph) * 0.8)
                        composite(img, ring, int(MARGIN + e["x"] - ring.width / 2), int(MARGIN + e["y"] - ring.height / 2))
                continue
            x, y = MARGIN + e["x"], MARGIN + e["y"]
            if kind == "letters":
                self._letters(img, e, x, y, t, sg)
                continue
            t0 = self._when(sg, e.get("t", 0)) + e.get("d", 0)
            p = prog(t, t0, t0 + (0.35 if kind != "tok" else 0.24))
            if t <= t0:
                continue
            im = e["img"]
            if kind == "pop":
                s = 0.4 + 0.6 * _spring(p * 1.1)
                si = _rotate_scale(im, s, 0)
                composite(img, fade(si, min(1, p * 3)), int(x + im.width / 2 - si.width / 2),
                          int(y + im.height / 2 - si.height / 2))
            elif kind in ("slide", "rise"):
                e3 = _out3(p)
                dx = -24 * (1 - e3) if kind == "slide" else 0
                dy = 0 if kind == "slide" else (22 if kind == "rise" else 16) * (1 - e3)
                composite(img, fade(im, e3), int(x + dx), int(y + dy))
            elif kind == "divider":
                e3 = _out3(prog(t, t0, t0 + 0.55))
                wv = max(2, int(im.width * e3))
                composite(img, im.crop(((im.width - wv) // 2, 0, (im.width + wv) // 2, im.height)),
                          int(x + (im.width - wv) / 2), int(y))
            elif kind == "armark":  # brush / ribbon / swoosh, revealed right to left with a soft edge
                pp = prog(t, t0, t0 + e["dur"])
                e3 = ease_io(pp) if pp < 1 else 1.0
                if e3 <= 0:
                    continue
                wv = max(1, int(im.width * e3))
                part = im.crop((im.width - wv, 0, im.width, im.height))
                if e3 < 1:
                    a_ = np.array(part.getchannel("A"), float)
                    ramp = np.clip(np.arange(wv) / 26.0, 0, 1)[None, :]
                    part.putalpha(Image.fromarray((a_ * ramp).astype(np.uint8)))
                composite(img, part, int(x + im.width - wv), int(y))
            elif kind == "arword":
                u = t - t0
                st = e["style"]
                dy = 0.0
                if st == "stamp":  # falls from the camera and slams flat, a little bounce
                    if u < 0.16:
                        q = u / 0.16
                        sc_, al = 2.2 - 1.2 * q * q, min(1, q * 1.8)
                    else:
                        v = u - 0.16
                        sc_, al = 1 + 0.09 * math.exp(-v * 14) * math.cos(v * 40), 1
                elif st in ("brush", "ribbon"):
                    q = min(1, u / 0.32)
                    sc_, al = 0.5 + 0.5 * ease_out_back(q), min(1, q * 3)
                elif st == "swoosh":
                    q = _out3(u / 0.3)
                    sc_, al, dy = 1, q, 28 * (1 - q)
                else:
                    sc_, al = 1, _out3(u / 0.35)
                si = _rotate_scale(im, sc_, 0) if abs(sc_ - 1) > 0.004 else im
                composite(img, fade(si, al), int(x + im.width / 2 - si.width / 2),
                          int(y + im.height / 2 - si.height / 2 + dy))
            elif kind == "panel":
                e3 = _out3(p)
                hh = max(2, int(im.height * (0.7 + 0.3 * e3)))
                si = im.resize((im.width, hh), Image.BILINEAR) if hh != im.height else im
                composite(img, fade(si, e3), int(x), int(y + (im.height - hh) / 2 + 20 * (1 - e3)))
        return img

    def _spoken(self, sg, e):
        """(start, end) of a chunk of the example sentence in video time."""
        tt = sg["extimes"]
        if not tt:
            return 1e9, 1e9
        a = tt[min(e["w0"], len(tt) - 1)][0]
        b = tt[min(e["w1"], len(tt) - 1)][1]
        return a, b

    def _token(self, img, e, t, sg):
        """One chunk of the example sentence in the chosen reveal (EX_REVEALS), timed to its spoken word."""
        mode = self.ex_reveal
        s0, s1 = self._spoken(sg, e)
        open_ = prog(t, sg["ex"] + 0.15, sg["ex"] + 0.45)  # the panel is open: the sentence is there
        if open_ <= 0:
            return
        bx, by = MARGIN + e["x"], MARGIN + e["y"]

        def draw(spec, alpha=1.0, scale=1.0, dy=0.0):
            im, base, adv, p = spec
            if scale != 1.0:
                si = _rotate_scale(im, scale, 0)
                cx = bx + e["sw"] / 2
                cy = by - base + im.height / 2 + dy
                composite(img, fade(si, alpha), int(cx - si.width / 2), int(cy - si.height / 2))
            else:
                composite(img, fade(im, alpha), int(bx + (e["sw"] - adv) / 2 - p), int(by - base + dy))
        if e["hl"] and t >= s0:  # the word itself pops onto its pill when it is spoken, and stays
            q = min(1, (t - s0) / 0.3)
            draw(e["pill"], min(1, q * 3), 0.6 + 0.4 * ease_out_back(q))
            return
        if mode == "appear":
            if t < s0:
                return
            q = _out3((t - s0) / 0.22)
            draw(e["n"], q, 1.0, 18 * (1 - q))
        elif mode == "karaoke":
            q = prog(t, s0, s0 + 0.12)
            if q < 1:
                draw(e["n"], 0.28 * open_)
            if q > 0:
                draw(e["n"], q)
        elif mode == "redbold":
            if s0 <= t < s1 + 0.06:  # the spoken word: red, bold, a little pop
                u = t - s0
                draw(e["b"], 1.0, 1 + 0.12 * math.exp(-u * 9) * math.cos(u * 14))
            else:
                draw(e["n"], open_)
        else:  # marker: the words stay, the marker moves under them
            draw(e["n"], open_)

    def _ex_marker(self, img, e, t, sg):
        rects = e["rects"]
        if not rects or not sg["extimes"]:
            return
        times = [self._spoken(sg, dict(w0=r[0], w1=r[1])) for r in rects]
        cur = None
        for i, (a, b) in enumerate(times):
            if t >= a:
                cur = i
        if cur is None:
            return
        fade_out = 1 - prog(t, times[-1][1] + 0.4, times[-1][1] + 0.8)
        if fade_out <= 0:
            return
        x0, y0, x1, y1 = rects[cur][2:]
        q = _out3((t - times[cur][0]) / 0.14)
        if cur > 0 and q < 1 and abs(rects[cur - 1][3] - y0) < 1:  # glide along the line
            px0, _, px1, _ = rects[cur - 1][2:]
            x0, x1 = px0 + (x0 - px0) * q, px1 + (x1 - px1) * q
        w_, h_ = max(4, int(x1 - x0)), int(y1 - y0)
        box = _solid(_rr_mask(w_, h_, 12), e["col"], 0.3 * fade_out)
        composite(img, box, int(MARGIN + x0), int(MARGIN + y0))

    def _letters(self, img, e, x, y, t, sg):
        im = e["img"]
        cuts = e["cuts"]
        n = len(cuts) - 1
        t_last = sg["w0"] + sg["lstep"] * (e["n0"] + n) + 0.45
        if t >= t_last:
            composite(img, im, int(x), int(y))
            return
        for i in range(n):
            t0 = sg["w0"] + sg["lstep"] * (e["n0"] + i)
            p = prog(t, t0, t0 + 0.42)
            if p <= 0:
                break
            a = int(cuts[i]) if i else 0
            b = int(cuts[i + 1]) if i < n - 1 else im.width
            if b <= a:
                continue
            strip = im.crop((a, 0, b, im.height))
            s = _spring(p * 1.15, 7, 12)
            dy = -90 * (1 - s)
            composite(img, fade(strip, min(1, p * 2.5)), int(x + a), int(y + dy))

    # ============================================================ recap
    def _layout_recap(self):
        """Recap rows (✓ chip, English, Arabic) with ONE English and ONE Arabic size for every row, as big as the
        rows allow: side by side when every row fits at a good size, else English on top and Arabic under it."""
        L = self.look
        n = self.n
        top = self.header_bottom + 130
        bottom = 1580
        cols = 1 if n <= 10 else 2
        rows = math.ceil(n / cols)
        rh = min(190 if cols == 1 else 150, (bottom - top) / rows)
        gap = min(18, rh * 0.12)
        h = int(rh - gap)
        cw = 940 if cols == 1 else 460
        d = int(h * (0.5 if cols == 1 else 0.42))
        x0 = int(h * 0.16) + d + 22
        room = cw - x0 - int(h * 0.3)
        has_ar = any(w["ar"] for w in self.words)

        def ew(w, sz):
            return _adv(self.en_font, w["en"], sz, "Bold")

        def aw(w, sz):
            return _ink_w(self.ar_font, w["ar"], sz, "Black") if w["ar"] else 0
        side, es, asz = False, 0, 0
        if cols == 1:
            sz = int(h * 0.36)
            while sz >= int(h * 0.27):
                if all(ew(w, sz) + aw(w, sz * 1.08) + 46 <= room for w in self.words):
                    side, es, asz = True, sz, int(sz * 1.08)
                    break
                sz -= 2
        if not side:  # stacked: each language as big as the widest row allows
            es = int(h * (0.31 if has_ar else 0.4))
            while es > 16 and any(ew(w, es) > room for w in self.words):
                es -= 2
            asz = int(h * 0.31)
            while asz > 16 and any(aw(w, asz) > room for w in self.words):
                asz -= 2
        self.rec = []
        for k, w in enumerate(self.words):
            acc = self.acc[k]
            m = _rr_mask(cw, h, min(h / 2, 44))
            row = _solid(m, L["card"])
            ring = Image.new("L", (cw, h), 0)
            ring.paste(_rr_mask(cw - 4, h - 4, min(h / 2, 44) - 2), (2, 2))
            ring = Image.fromarray(np.clip(np.array(m, int) - np.array(ring, int), 0, 255).astype(np.uint8))
            row.alpha_composite(_solid(ring, L["ink"], 0.08))
            sm = Image.new("L", (cw + 30, h + 30), 0)  # soft shadow
            sm.paste(m, (15, 20))
            shadowed = _solid(sm.filter(ImageFilter.GaussianBlur(7)), (20, 24, 40), 0.14 if self.light else 0.3)
            cm = Image.new("L", (d * 3, d * 3), 0)
            ImageDraw.Draw(cm).ellipse([0, 0, d * 3 - 1, d * 3 - 1], fill=255)
            cm = cm.resize((d, d), Image.LANCZOS)
            row.alpha_composite(_solid(cm, acc), (int(h * 0.16), (h - d) // 2))
            row.alpha_composite(_check(d, _on(acc), max(3, d * 0.11)), (int(h * 0.16), (h - d) // 2))
            ar_col = _mix(acc, (0, 0, 0), 0.15)
            right = cw - int(h * 0.3)
            et, eb, eadv, ep = _ltext(self.en_font, w["en"], es, "Bold", L["ink"])
            if side:
                row.alpha_composite(et, (x0 - ep, int(h / 2 + es * 0.36) - eb))
                if w["ar"]:
                    ai = text_img_in(self.ar_font, w["ar"], asz, ar_col, "Black")
                    composite(row, ai, int(right - ai.width + 30), int(h / 2 - ai.height / 2))
            else:
                ey = h * (0.32 if w["ar"] else 0.5)
                row.alpha_composite(et, (x0 - ep, int(ey + es * 0.36) - eb))
                if w["ar"]:
                    ai = text_img_in(self.ar_font, w["ar"], asz, ar_col, "Black")
                    composite(row, ai, int(right - ai.width + 30), int(h * 0.71 - ai.height / 2))
            r, c = (k, 0) if cols == 1 else (k // 2, k % 2)
            cx = 540 if cols == 1 else 540 + (c - 0.5) * (cw + 16)
            cy = top + rh * r + rh / 2 + ((bottom - top) - rh * rows) / 2
            shadowed.alpha_composite(row, (15, 15))
            self.rec.append((shadowed, cx, cy))
        self.rec_title = _ltext(EN_FONT, "QUICK RECAP", 40, "Bold", self.acc[0])

    def _recap(self, frame, t):
        R0 = self.R0
        out = 1 - 0.85 * prog(t, self.E0, self.E0 + 0.5) if self.has_end else 1
        im, base, adv, p = self.rec_title
        pr = prog(t, R0 + 0.1, R0 + 0.5)
        if pr > 0:
            composite(frame, fade(im, pr * out), int(540 - adv / 2 - p),
                      int(self.header_bottom + 66 - base + 18 * (1 - _out3(pr))))
        for k, (row, cx, cy) in enumerate(self.rec):
            t0 = R0 + 0.35 + self.rstep * k
            pr = prog(t, t0, t0 + 0.55)
            if pr <= 0:
                continue
            e = ease_io(pr)
            bx, by = self._float(k, t0)
            x = bx + (cx - bx) * e
            y = by + (cy - by) * e - math.sin(math.pi * e) * 60
            s = 0.55 + 0.45 * _spring(pr, 6, 10)
            _put(frame, _rotate_scale(row, s, 0), x, y, min(1, pr * 2.5) * out)

    # ============================================================ frame
    def render(self, t):
        n = self.n
        # which word is on: dim the world while its card is up
        dim = 0.0
        cur = None
        for k, sg in enumerate(self.seg):
            if sg["s"] - 0.05 <= t < sg["out"] + 0.12:
                cur = k
                if sg["hops"] and t < sg["sel"]:
                    dim = 0.25 * prog(t, sg["s"], sg["s"] + 0.3)
                elif t < sg["end"]:
                    dim = 0.25 + 0.75 * ease_io(prog(t, sg["sel"], sg["pop"] + 0.25)) if sg["hops"] else \
                        ease_io(prog(t, sg["sel"], sg["pop"] + 0.25))
                else:
                    dim = 1 - ease_io(prog(t, sg["end"], sg["out"]))
                break
        in_recap = self.recap_on and t >= self.R0
        if in_recap:
            dim = 0.0
        frame = self._background(t, dim)
        self._header(frame, t, 1 - 0.75 * dim)
        # shake after the pop
        shx = shy = 0.0
        punch = 0.0
        if cur is not None:
            for ti, st in self.seg[cur]["impacts"]:
                u = t - ti
                if 0 < u < 0.35:
                    amp = 11 * st * (1 - u / 0.35)
                    shx += amp * math.sin(u * 90)
                    shy += amp * math.cos(u * 77)
                    punch += 0.03 * st * math.exp(-u * 11)
        # bubbles
        recap_fade = 1 - prog(t, self.R0 + 0.35, self.R0 + 0.35 + self.rstep * n + 0.6) if self.recap_on else 1
        for k in range(n):
            if in_recap and t >= self.R0 + 0.35 + self.rstep * k:
                continue
            self._draw_bubble(frame, k, t, cur, dim, shx, shy, recap_fade if in_recap else 1)
        if cur is not None:
            self._draw_focus(frame, cur, t, shx, shy)
        if in_recap:
            self._recap(frame, t)
        if self.has_end and t >= self.E0:
            self._ending(frame, t)
        if punch > 0.002:  # camera punch-in on an impact
            z = 1 + punch
            big = frame.resize((int(W * z), int(H * z)), Image.BILINEAR)
            ox, oy = (big.width - W) // 2, (big.height - H) // 2
            frame = big.crop((ox, oy, ox + W, oy + H))
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

    def _draw_bubble(self, frame, k, t, cur, dim, shx, shy, alpha):
        b = self.bub[k]
        sg = self.seg[k]
        # spawn: burst out of the centre on an arc
        t_sp = self.b0 + self.spawn * k
        ps = prog(t, t_sp, t_sp + 0.75)
        if ps <= 0:
            return
        fx, fy = self._float(k, t)
        if ps < 1:
            e = _out3(ps)
            sx, sy = 540, 1040
            x = sx + (fx - sx) * e
            y = sy + (fy - sy) * e - math.sin(math.pi * e) * 120
            s = 0.2 + 0.8 * _spring(ps, 5.5, 10)
            _put(frame, _rotate_scale(b["idle"], s, (1 - e) * (14 if k % 2 else -14)), x, y, min(1, ps * 3) * alpha)
            return
        done = t >= sg["out"]
        if k == cur and sg["sel"] - 0.01 <= t < sg["out"]:
            return  # drawn by _draw_focus (flying / as the card)
        x, y = fx + shx * 0.5, fy + shy * 0.5
        a = alpha * (1 - 0.6 * dim if k != cur else 1)
        s = 1 - 0.05 * dim
        # roulette light
        if cur is not None:
            for i, (ht, j) in enumerate(self.seg[cur]["hops"]):
                nxt = self.seg[cur]["hops"][i + 1][0] if i + 1 < len(self.seg[cur]["hops"]) else self.seg[cur]["sel"]
                if j == k and ht <= t < nxt + 0.12 and j != cur:
                    hp = 1 - prog(t, ht, nxt + 0.12)
                    _put(frame, b["glow"], x, y, hp * 0.9)
                    s *= 1 + 0.08 * hp
                    a = max(a, alpha * (0.4 + 0.6 * hp))
        if done:
            land = prog(t, sg["out"], sg["out"] + 0.5)
            if land < 1:  # squash on landing + ring
                sq = math.exp(-6 * land) * math.cos(16 * land)
                dn = b["done"]
                im = dn.resize((max(1, int(dn.width * s * (1 + 0.22 * sq))), max(1, int(dn.height * s * (1 - 0.22 * sq)))),
                               Image.BILINEAR)
                _put(frame, b["glow"], x, y, (1 - land) * a)
                _put(frame, im, x, y, a)
                rg = _ring(b["h"] * 0.5 + land * 110, 4, self.acc[k], (1 - land) * 0.8 * a)
                _put(frame, rg, x, y)
                return
            _put(frame, _rotate_scale(b["done"], s, 0), x, y, a)
            return
        _put(frame, _rotate_scale(b["idle"], s, 0), x, y, a)

    def _draw_focus(self, frame, k, t, shx, shy):
        sg = self.seg[k]
        b = self.bub[k]
        fx, fy = self._float(k, t)
        acc = self.acc[k]
        c = self._card(k)
        ccy = max(c["ch"] / 2 + 270, min(CARD_CY, 1660 - c["ch"] / 2))
        # 1) picked: the bubble grows and glows, a ripple goes out
        if sg["sel"] <= t < sg["fly1"]:
            ps = prog(t, sg["sel"], sg["fly0"])
            pf = prog(t, sg["fly0"], sg["fly1"])
            e = ease_io(pf)
            x = fx + (540 - fx) * e
            y = fy + (ccy - fy) * e - math.sin(math.pi * e) * 90
            s = (1 + 0.2 * ease_out_back(ps)) * (1 + 1.1 * _in2(pf))
            _put(frame, b["glow"], x, y, 0.95 * (1 - pf * 0.5))
            if ps < 1:
                rg = _ring(b["h"] * 0.55 + ps * 90, 3, acc, (1 - ps) * 0.85)
                _put(frame, rg, fx, fy)
            _put(frame, _rotate_scale(b["idle"], s, 0), x, y, 1 - _in2(prog(t, sg["fly1"] - 0.08, sg["fly1"])))
        # 2) the card pops
        if sg["pop"] <= t < sg["out"]:
            img = self._card_frame(k, t)
            pp = prog(t, sg["pop"], sg["pop"] + 0.75)
            s = 0.3 + 0.7 * _spring(pp * 1.25, 6.0, 11.0)
            ang = -7 * (1 - _out3(pp * 1.3))
            x, y, a = 540 + shx, ccy + shy, min(1, pp * 6)
            if t >= sg["end"]:  # collapse back into its bubble
                pc = prog(t, sg["end"], sg["out"])
                e = _in2(pc) * 0.6 + ease_io(pc) * 0.4
                bs = b["w"] / (CW + 2 * MARGIN)
                s = 1 + (bs - 1) * e
                x = 540 + (fx - 540) * e
                y = ccy + (fy - ccy) * e
                ang = 6 * math.sin(math.pi * pc)
                a = 1 - prog(pc, 0.55, 1.0)
            _put(frame, _rotate_scale(img, s, ang), x, y, a)
            # shockwave + confetti
            u = t - sg["pop"]
            if 0 <= u < 0.7:
                pr = u / 0.7
                _put(frame, _ring(120 + _out3(pr) * 620, 6 * (1 - pr) + 1, acc, (1 - pr) * 0.75), 540, ccy)
            if 0.05 <= u < 1.1:
                self._sparks(frame, k, u - 0.05, ccy, c["ch"])

    def _ending(self, frame, t):
        """The 🔚 Ending card in the video's own colours (intro line, question lines, arrow, call to action, handle)."""
        L = self.look
        t0 = self.E0
        a = ease_io(prog(t, t0, t0 + 0.5))
        frame.alpha_composite(Image.new("RGBA", (W, H), tuple(L["bg"][0]) + (int(240 * a),)))

        def txt(s, size, col):
            path = self.ar_font if ARABIC_RE.search(s) else self.en_font
            return text_img_in(path, s, size, col, "Black" if size >= 70 else "Bold", max_w=960)
        y = 640
        items = []
        if self.e_intro:
            items.append((txt(self.e_intro, 56, L["head_soft"]), y, t0 + 0.2))
            y += 130
        n = len(self.e_q)
        size, pitch = (96, 115) if n <= 2 else (80, 98)
        for i, (s, col) in enumerate(self.e_q):
            col = L["head"] if col == to_rgb("white") else (_mix(col, (0, 0, 0), 0.3) if self.light else col)
            items.append((txt(s, size, col), y + i * pitch, t0 + 0.35 + 0.15 * i))
        last = y + (n - 1) * pitch if n else y - 130
        arrow_y = last + 205
        if self.e_cta:
            items.append((txt(self.e_cta, 52, L["head"]), arrow_y + 160, t0 + 1.0))
        if self.handle:
            items.append((txt(self.handle, 46, L["head_soft"]), arrow_y + 330, t0 + 1.3))
        for im, yy, ti in items:
            p = prog(t, ti, ti + 0.35)
            if p > 0:
                _put(frame, _rotate_scale(im, 0.8 + 0.2 * ease_out_back(p), 0), 540, yy, min(1, p * 1.5))
        p = prog(t, t0 + 0.8, t0 + 1.1)
        if p > 0 and (n or self.e_cta):
            ay = arrow_y + math.sin(t * 5) * 14
            lay = Image.new("RGBA", (120, 140), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            c = tuple(self.acc[0]) + (int(255 * p),)
            d.line([(60, 15), (60, 100)], fill=c, width=12)
            d.polygon([(22, 85), (98, 85), (60, 132)], fill=c)
            composite(frame, lay, 480, int(ay - 70))

    def _sparks(self, frame, k, u, cy, ch):
        rng = np.random.default_rng(100 + k)
        pr = u / 1.05
        for i in range(22):
            ang = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(380, 900)
            dist = sp * (1 - math.exp(-3.2 * u)) / 3.2 * 2.2
            x = 540 + math.cos(ang) * (CW * 0.36 + dist)
            y = cy + math.sin(ang) * (ch * 0.36 + dist) + 140 * u * u
            col = self.acc[(k + i) % self.n] if i % 3 else self.acc[k]
            st = self.confetti[tuple(col)]
            sc = rng.uniform(0.4, 1.0) * (1 - pr * 0.5)
            a = (1 - pr) ** 1.3
            _put(frame, _rotate_scale(st, sc, 0), x, y, a)

    # ============================================================ sound
    def sound(self, mx):
        mx.intro(0.05)
        s, pn = mx.whoosh(0.6)
        mx.add(0.2, s, 0.25, pn)
        pop = mx.pop()
        for k in range(min(self.n, 14)):
            mx.add(self.b0 + self.spawn * k + 0.05, pop, 0.12)
        for k, sg in enumerate(self.seg):
            for i, (ht, j) in enumerate(sg["hops"]):
                mx.add(ht, mx.tick(1500 + 60 * i), 0.16)
            mx.add(sg["sel"], mx.click(), 0.25)
            s, pn = mx.whoosh(0.45)
            mx.add(sg["fly0"] - 0.08, s, 0.32, pn)
            mx.add(sg["pop"], mx.hit(0.9), 0.32)
            mx.add(sg["pop"] + 0.02, pop, 0.45)
            mx.add(sg["pop"] + 0.08, mx.sparkle(), 0.2)
            st = self.ar_style
            if sg["ar_words"]:
                if st == "brush":
                    mx.add(sg["ar"], mx.scribble(AR_TIME["brush"][1] * len(sg["ar_words"]) + 0.15), 0.16)
                elif st in ("ribbon", "plain"):
                    s, pn = mx.whoosh(0.45)
                    mx.add(sg["ar"] - 0.05, s, 0.18, pn)
                for a in sg["ar_words"]:
                    if st == "stamp":
                        mx.add(a + 0.14, mx.stamp(), 0.38)
                    elif st != "plain":
                        mx.add(a + 0.02, pop, 0.12)
                if st == "swoosh":
                    mx.add(sg["ar_mark"], mx.scribble(0.4), 0.2)
            if sg["ex"]:
                mx.add(sg["ex"], mx.click(), 0.14)
            s, pn = mx.whoosh(0.5)
            mx.add(sg["end"] - 0.05, s, 0.26, -pn)
            mx.add(sg["out"], mx.thump(), 0.3)
            mx.add(sg["out"] + 0.02, mx.ding(), 0.16)
        if self.recap_on:
            s, pn = mx.whoosh(0.7)
            mx.add(self.R0, s, 0.3, pn)
            for k in range(self.n):
                mx.add(self.R0 + 0.45 + self.rstep * k, pop, 0.16)
        if self.has_end:
            mx.add(self.E0 + 0.2, mx.chime(), 0.3)
        for at, path in self.voices:
            mx.add_voice(path, at, self.audio_gain)
