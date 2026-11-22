"""🃏 Idiom cards (English Words → 🃏 Idiom cards): a felt board with a white band across the middle; each card on the
band = the English idiom on a yellow highlighter, its Arabic name in [brackets] and the Arabic meaning in red. A short
hook opens the video (the band slices open, the title words slam in, a highlighter swipes under them), then the cards
follow one another with a cinematic transition (`idiomcards.transition`: whip pan, slice, 3D flip, zoom punch, soft
wipe, or a mix of them), and the shared 🔚 Ending card closes it on the same band.

`idiomcards.items` = one card per line: the English, then any of an [Arabic name], an English meaning and the Arabic
meaning, told apart by their language (`sort_parts`): `Achilles' heel | كعب أخيل | نقطة الضعف القاتلة`,
`Resilient | able to recover quickly | مَرِن`, `Grateful | ممتنّ`. Voice clips `w<k>` (the k-th card's English) and
`w<k>e` (its English meaning) are played when they show and the card waits for them.
Every frame depends only on t (frames are drawn on several processes); card layers are cached per process."""
import math
import os
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..audio import audio_length
from ..core import (ARABIC_RE, H, ROOT, W, _family_file, _state, composite, ease_out_back, fade, get_font,
                    global_fade, parse_lines, prog, text_img_in, to_rgb)
from .vocab import clip_key

NAME = "Idiom Cards"

EN_FONT = os.path.join(ROOT, "fonts", "library", "Montserrat", "Montserrat[wght].ttf")
AR_DEFAULT = "Tajawal"  # the Arabic font family (any library family can be picked: idiomcards.arabic_font)

# the board behind the band: felt colour, light / dark of its texture, the progress bar + counter colour
LOOKS = {
    "green": dict(felt=(20, 62, 42), bar=(22, 92, 58)),
    "navy": dict(felt=(22, 38, 72), bar=(34, 66, 140)),
    "wine": dict(felt=(78, 22, 36), bar=(150, 34, 58)),
    "charcoal": dict(felt=(38, 40, 44), bar=(70, 74, 82)),
    "sand": dict(felt=(214, 196, 164), bar=(150, 112, 60)),
}
LOOK_CHOICES = [("Green felt (like a classroom board)", "green"), ("Navy felt", "navy"), ("Wine felt", "wine"),
                ("Charcoal felt", "charcoal"), ("Sand (light)", "sand")]
MARKERS = {"yellow": (255, 246, 70), "green": (150, 240, 120), "pink": (255, 160, 200), "orange": (255, 196, 90),
           "blue": (140, 210, 255)}
MARKER_CHOICES = [("Yellow", "yellow"), ("Green", "green"), ("Pink", "pink"), ("Orange", "orange"), ("Blue", "blue")]
TRANSITIONS = [("Mix — a different cinematic move for every card", "mix"),
               ("Whip pan — the band shoots sideways with motion blur", "whip"),
               ("Slice — the band splits into strips that fly out and back in", "slice"),
               ("3D flip — the band turns over like a card", "flip"),
               ("Zoom punch — the card flies into the camera, the next one punches in", "zoom"),
               ("Soft wipe — the text wipes away and in (calm)", "wipe")]
MIX = ("whip", "slice", "flip", "zoom")
TOUCHES = [("Card counter (3 / 7) on the band", "counter"), ("Timer bar along the band", "progress"),
           ("Light sweep over the highlighter", "shine"), ("Camera punch-in when a card lands", "punch"),
           ("Slow camera drift over the board", "drift"), ("Soft shadow under the band", "shadow")]
TOUCH_DEFAULT = ["counter", "progress", "shine", "punch", "drift", "shadow"]
PACES = {"calm": 3.4, "normal": 2.75, "fast": 2.2}  # how long a card stays after it lands (s)

INK = (14, 14, 16)
RED = (226, 22, 22)
BAND = (250, 250, 249)
CY = 900            # band centre
TR = 0.5            # transition length
OPEN = 0.55         # the band opening at the start
EN_MAX, EN_MIN = 106, 70
NAME_SIZE, MEAN_SIZE, DEF_SIZE = 58, 60, 50
DEF_INK = (58, 62, 74)  # the English meaning: dark slate, quieter than the idiom
TEXT_W = 920
_BG = {}


# ------------------------------------------------------------------ text
def sort_parts(en, parts):
    """dict(en, name, df, mean) from the parts after the English, by their language (in their order): English text =
    the English meaning (df); one Arabic part = the Arabic meaning; two = the [Arabic name] + the Arabic meaning."""
    parts = [" ".join(str(p or "").split()) for p in parts]
    ar = [p for p in parts if p and ARABIC_RE.search(p)]
    df = " ".join(p for p in parts if p and not ARABIC_RE.search(p))
    name = ar[0] if len(ar) >= 2 else ""
    mean = " ".join(ar[1:] if len(ar) >= 2 else ar)
    return dict(en=en, name=name, df=df, mean=mean)


def parse_items(text):
    """[dict(en, name, df, mean)] from 'English | … ' lines: after the English, any of an [Arabic name], an English
    meaning and the Arabic meaning, told apart by their language (`sort_parts`)."""
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [" ".join(p.split()) for p in line.split("|")]
        if not parts[0]:
            continue
        out.append(sort_parts(parts[0], parts[1:]))
    return out


def items_text(items):
    """The editor's text from item dicts (en, name, df, mean): English | name | English meaning | meaning, empty parts
    left out (parse_items tells them apart again by their language)."""
    lines = []
    for it in items:
        cells = [" ".join(str(it.get(k) or "").replace("|", "/").split()) for k in ("en", "name", "df", "mean")]
        lines.append(" | ".join([cells[0]] + [c for c in cells[1:] if c]))
    return "\n".join(lines)


_HEAD = {"df": ("english meaning", "english definition", "definition", "meaning in english", "التعريف",
                "المعنى بالإنجليزي", "المعنى بالانجليزي"),
         "en": ("english", "idiom", "expression", "phrase", "word", "الإنجليزي", "الانجليزي", "التعبير"),
         "name": ("arabic name", "name", "translation", "arabic", "عربي", "الاسم", "الترجمة"),
         "mean": ("meaning", "arabic meaning", "المعنى", "الشرح"),
         "title": ("title", "العنوان"), "sub": ("subtitle", "sub title", "العنوان الفرعي")}


def read_sheet(path, sheet=None):
    """([dict(en, name, df, mean, title, sub)], [problems]) from an Excel / CSV sheet: columns English | Arabic name |
    English meaning | Arabic meaning (any of the last three; + optional Title, Subtitle), with or without a header
    row. A Title goes on until the next one."""
    from ..batch import read_table
    rows = read_table(path, sheet)
    cols, start = None, 0
    for i, row in enumerate(rows[:10]):  # a header row (it may sit under a title row)
        found = {}
        for j, cell in enumerate(row):
            c = " ".join(str(cell or "").lower().split())
            for key in ("sub", "title", "df", "mean", "name", "en"):  # longer names first ("arabic name" ≠ "name")
                if key not in found and c and any(c == h or c.startswith(h) for h in _HEAD[key]):
                    found[key] = j
                    break
        if "en" in found and ("mean" in found or "name" in found or "df" in found):
            cols, start = found, i + 1
            break
    if cols is None:
        cols = {"en": 0, "name": 1, "mean": 2, "df": 3}  # no header: columns B-D, told apart by language
    items, problems = [], []
    title = sub = ""
    for r, row in enumerate(rows[start:], start + 1):
        cell = lambda k: " ".join(str(row[cols[k]] or "").replace("|", "/").split()) \
            if k in cols and cols[k] < len(row) else ""  # noqa: E731
        if cell("title"):
            title, sub = cell("title"), cell("sub")
        elif cell("sub"):
            sub = cell("sub")
        en = cell("en")
        # the cells in sheet order; what each one is comes from its language (an English meaning may sit in the
        # Arabic name column and so on)
        rest = [cell(k) for k in sorted(("name", "df", "mean"), key=lambda k: cols.get(k, 99)) if k in cols]
        if not en and not any(rest):
            continue
        if not en:
            problems.append(f"row {r}: the English idiom is empty — left out")
            continue
        if not any(rest):
            problems.append(f"row {r}: no meaning for “{en}” — left out")
            continue
        items.append(dict(sort_parts(en, rest), title=title, sub=sub))
    return items, problems


TEMPLATE_ROWS = [
    ("English idiom / word", "Arabic name (optional)", "English meaning (optional)", "Arabic meaning", "Title",
     "Subtitle"),
    ("Achilles' heel", "كعب أخيل", "", "نقطة الضعف القاتلة", "{count} Idioms from Greek Myths",
     "تعابير إنجليزية أصلها أساطير يونانية"),
    ("Pandora's box", "صندوق باندورا", "", "مصدر لمشكلات متعاقبة يصعب احتواؤها", "", ""),
    ("Herculean effort", "جهد هرقلي", "", "جهد خارق يفوق المعتاد", "", ""),
    ("Gordian knot", "العقدة الغوردية", "", "معضلة معقدة يصعب حلها بالوسائل التقليدية", "", ""),
    ("Elysian fields", "حقول إليسيوم", "", "رمز للنعيم الأبدي أو المكان المثالي", "", ""),
    ("Procrustean bed", "سرير بروكرست", "", "إطار قسري تُفرض فيه الوقائع أو الأفراد ليتوافقوا مع معيار صارم", "", ""),
    ("Trojan horse", "حصان طروادة", "", "خدعة تبدو بريئة وتُخفي خطرًا من الداخل", "", ""),
    ("Break the ice", "", "to make people feel relaxed when they first meet", "بدء الحديث وإزالة التوتر في أول لقاء",
     "{count} Everyday Idioms", "تعابير يستخدمها الإنجليز كل يوم"),
    ("Spill the beans", "", "to tell a secret too early", "كشف سرٍّ قبل أوانه", "", ""),
    ("Hit the sack", "", "to go to bed", "الذهاب إلى النوم", "", ""),
    ("Piece of cake", "", "something very easy to do", "أمر سهل جدًا", "", ""),
    ("Resilient", "", "able to recover quickly from difficulties", "مَرِن، سريع التعافي", "{count} Words to Sound Smarter",
     "كلمات إنجليزية ستبهر بها الجميع"),
    ("Overwhelmed", "", "having too much to deal with at once", "مُنهَك، غارق في المهام", "", ""),
]


def write_template(path):
    """projects/idioms_template.xlsx: English | Arabic name | English meaning | Arabic meaning | Title | Subtitle."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Idioms"
    for row in TEMPLATE_ROWS:
        ws.append(list(row))
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="14402A")
    for col, w in zip("ABCDEF", (24, 22, 46, 56, 32, 38)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in (row[1], row[3], row[5]):
            c.alignment = Alignment(horizontal="right", readingOrder=2)
    ws.freeze_panes = "A2"
    wb.save(path)


def _arabic_font(name):
    name = str(name or "").strip()
    if not name or name == AR_DEFAULT:
        path = _family_file(AR_DEFAULT)
        if path and os.path.isfile(path):
            return path
    from .words_video import _arabic_font as wv_font
    return wv_font(name or AR_DEFAULT)


def _en_line(path, txt, size, color=INK, weight="Black"):
    """A Latin line on a fixed-height box: (image, baseline y, advance, pad)."""
    f = get_font(int(size), weight, path)
    asc, desc = f.getmetrics()
    adv = f.getlength(txt)
    p = int(size * 0.3) + 8
    im = Image.new("RGBA", (int(math.ceil(adv)) + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((p, p + asc), txt, font=f, fill=tuple(color[:3]) + (255,), anchor="ls")
    return im, p + asc, adv, p


def _ink(im):
    """(left, right) of the ink in a text image (the box and the centring follow the letters, not the advance)."""
    box = im.getchannel("A").getbbox()
    return (box[0], box[2]) if box else (0, im.width)


def _ar_img(path, txt, size, color):
    return text_img_in(path, txt, int(size), color, "Black")


def _wrap(measure, txt, max_w, n_max=3):
    """Lines of txt that fit max_w (greedy, then evened out so the last line is not a lone word)."""
    words = txt.split()
    if not words:
        return []
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if cur and measure(test) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    lines.append(cur)
    if len(lines) == 2:  # balance two lines
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wa, wb = measure(a), measure(b)
            if max(wa, wb) <= max_w and (best is None or max(wa, wb) < best[0]):
                best = (max(wa, wb), [a, b])
        if best:
            lines = best[1]
    return lines if len(lines) <= n_max else None


# ------------------------------------------------------------------ small helpers
def _ease_in(x, p=3):
    x = min(1.0, max(0.0, x))
    return x ** p


def _ease_out(x, p=3):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** p


def _ease_io(x, p=4):
    x = min(1.0, max(0.0, x))
    return 2 ** (p - 1) * x ** p if x < 0.5 else 1 - (-2 * x + 2) ** p / 2


def _spring(x, damp=7.0, freq=13.0):
    """1 -> 0 wobble (a landing settle)."""
    if x <= 0:
        return 1.0
    return math.exp(-damp * x) * math.cos(freq * x)


def _wipe(im, p, rtl=False, feather=90):
    """im revealed by a soft edge travelling left -> right (rtl: right -> left), p = 0..1."""
    if p >= 1:
        return im
    if p <= 0:
        return None
    w = im.width
    pos = p * (w + feather)
    x = np.arange(w, dtype=np.float32)
    if rtl:
        x = w - 1 - x
    ramp = np.clip((pos - x) / feather, 0, 1)
    a = np.asarray(im.getchannel("A"), np.float32) * ramp[None, :]
    out = im.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    return out


def _erase(im, p, feather=90):
    """im erased by a soft edge travelling left -> right."""
    if p <= 0:
        return im
    if p >= 1:
        return None
    w = im.width
    pos = p * (w + feather) - feather
    x = np.arange(w, dtype=np.float32)
    ramp = np.clip((x - pos) / feather, 0, 1)
    a = np.asarray(im.getchannel("A"), np.float32) * ramp[None, :]
    out = im.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    return out


def _hblur(im, k):
    """Horizontal motion blur by k (1 = none): squeeze and stretch back."""
    if k <= 1.05:
        return im
    w, h = im.size
    return im.resize((max(1, int(w / k)), h), Image.BILINEAR).resize((w, h), Image.BILINEAR)


def _blur(im, k):
    if k <= 1.05:
        return im
    w, h = im.size
    return im.resize((max(1, int(w / k)), max(1, int(h / k))), Image.BILINEAR).resize((w, h), Image.BILINEAR)


def _scaled(im, s):
    if abs(s - 1) < 0.004:
        return im
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR)


def _put(frame, im, cx, cy, alpha=1.0):
    if im is None or alpha <= 0.01:
        return
    composite(frame, fade(im, alpha), int(round(cx - im.width / 2)), int(round(cy - im.height / 2)))


def _persp(dst, src):
    """PIL PERSPECTIVE coefficients that map output points dst to input points src (4 corners each)."""
    a = []
    b = []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    return np.linalg.solve(np.array(a, float), np.array(b, float)).tolist()


def _felt(look):
    """The felt board (a little bigger than the screen so the camera can drift over it), cached per look."""
    if look in _BG:
        return _BG[look]
    base = np.array(LOOKS[look]["felt"], np.float32)
    pw, ph = W + 80, H + 80
    rng = np.random.default_rng(11)
    tex = np.zeros((ph, pw), np.float32)
    for div, amp in ((90, 0.55), (28, 0.35), (8, 0.22)):  # soft clouds of fibre at three scales
        small = rng.standard_normal((ph // div + 2, pw // div + 2)).astype(np.float32)
        im = Image.fromarray(((small * 40) + 128).clip(0, 255).astype(np.uint8), "L")
        tex += (np.asarray(im.resize((pw, ph), Image.BICUBIC), np.float32) - 128) / 40 * amp
    tex += rng.standard_normal((ph, pw)).astype(np.float32) * 0.35  # fine grain
    yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
    nx, ny = (xx - pw / 2) / (pw / 2), (yy - ph / 2) / (ph / 2)
    vig = 1 - 0.28 * np.clip(nx ** 2 * 0.6 + ny ** 2 * 0.5, 0, 1.4)  # darker edges
    light = 1 + 0.06 * (1 - (xx / pw + yy / ph))  # a soft light from the top left
    lum = (1 + tex * 0.045) * vig * light
    arr = base[None, None, :] * lum[..., None]
    img = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")
    _BG[look] = img
    return img


# ------------------------------------------------------------------ the video
EXAMPLE = {
    "template": "idiomcards",
    "settings": {"theme": "Royal Blue", "language": "ar", "fps": 30, "music": "Epic", "music_gain": 0.8,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@logolept AR EN", "font_file": "", "intro_sound": "Swoosh + impact",
                 "tick_sound": "Classic", "tick_gain": 1.0},
    "ending": {"intro": "الحلقة القادمة:", "question": "{count} more idioms\n[gold]from history",
               "cta": "كم تعبيرًا كنت تعرف؟ اكتب الرقم في التعليقات"},
    "idiomcards": {
        "title": "{count} Idioms from Greek Myths",
        "subtitle": "تعابير إنجليزية أصلها أساطير يونانية",
        "items": ("Achilles' heel | كعب أخيل | نقطة الضعف القاتلة\n"
                  "Pandora's box | صندوق باندورا | مصدر لمشكلات متعاقبة يصعب احتواؤها\n"
                  "Herculean effort | جهد هرقلي | جهد خارق يفوق المعتاد\n"
                  "Gordian knot | العقدة الغوردية | معضلة معقدة يصعب حلها بالوسائل التقليدية\n"
                  "Elysian fields | حقول إليسيوم | رمز للنعيم الأبدي أو المكان المثالي\n"
                  "Procrustean bed | سرير بروكرست | إطار قسري تُفرض فيه الوقائع أو الأفراد ليتوافقوا مع معيار صارم\n"
                  "Trojan horse | حصان طروادة | خدعة تبدو بريئة وتُخفي خطرًا من الداخل"),
        "look": "green",
        "marker": "yellow",
        "transition": "mix",
        "pace": "normal",
        "touches": list(TOUCH_DEFAULT),
        "arabic_font": "",
        "audio": [],
        "audio_gain": 1.0,
        "voice_on": False,
        "voice_id": "",
    },
}


class IdiomCards:
    def __init__(self, project):
        d = project.get("idiomcards", {})
        s = project.get("settings", {})
        self.fps = int(s.get("fps") or 30)
        self.items = parse_items(d.get("items"))
        if not self.items:
            raise ValueError("Write at least one card: English | Arabic name | Arabic meaning")
        self.n = n = len(self.items)
        self.look = d.get("look") if d.get("look") in LOOKS else "green"
        self.bar = LOOKS[self.look]["bar"]
        self.marker = MARKERS.get(d.get("marker") or "yellow", MARKERS["yellow"])
        tr = d.get("transition")
        self.transition = tr if tr in dict((v, k) for k, v in TRANSITIONS) else "mix"
        self.hold = PACES.get(d.get("pace") or "normal", PACES["normal"])
        tch = d.get("touches")
        valid = {v for _, v in TOUCHES}
        self.touch = set(TOUCH_DEFAULT if tch is None else [x for x in (tch or []) if x in valid])
        self.audio_gain = float(d.get("audio_gain") or 1.0)
        self.handle = str(s.get("handle") or "")
        picked = _state["font"] if s.get("font_file") else None  # a 🎨 Style & sound font replaces the English one
        self.en_font = picked or EN_FONT
        self.ar_font = _arabic_font(d.get("arabic_font"))
        cnt = str(n)
        self.title = str(d.get("title") or "").replace("{count}", cnt).strip()
        self.subtitle = str(d.get("subtitle") or "").replace("{count}", cnt).strip()
        e = project.get("ending", {})
        self.e_intro = str(e.get("intro") or "").replace("{count}", cnt).strip()
        self.e_q = parse_lines(str(e.get("question") or "").replace("{count}", cnt), ["white"])
        self.e_cta = str(e.get("cta") or "").replace("{count}", cnt).strip()
        self.has_end = bool(self.e_intro or self.e_q or self.e_cta)
        self.clip = {}
        for p in d.get("audio") or []:
            if p and os.path.isfile(str(p)):
                key = clip_key(p)
                if key and 1 <= key[0] <= n and key[1] in ("w", "e"):
                    try:
                        self.clip[(key[0] - 1, key[1])] = (p, audio_length(p))
                    except Exception:
                        pass
        self._layout()
        self._timeline()
        self._cache = OrderedDict()
        self.silences = []
        self.chunk = 6

    # ============================================================ layout
    def _txt(self, s, size, col, weight="Black"):
        """One line in the right font for its script (English font / Arabic font)."""
        if ARABIC_RE.search(s):
            return _ar_img(self.ar_font, s, size, col)
        im, base, adv, p = _en_line(self.en_font, s, size, col)
        return im

    def _en_block(self, txt, max_size=EN_MAX):
        """English lines (1-2) at one size that fits: [(image, baseline, advance, pad)], size, line pitch."""
        meas = lambda s, z: get_font(int(z), "Black", self.en_font).getlength(s)  # noqa: E731
        size = max_size
        while size > EN_MIN and meas(txt, size) > TEXT_W:
            size -= 2
        lines = [txt]
        if meas(txt, size) > TEXT_W:  # too long for one line even at the smallest size: two lines
            size = max_size
            while size > 40:
                ls = _wrap(lambda s: meas(s, size), txt, TEXT_W, 2)
                if ls:
                    lines = ls
                    break
                size -= 2
        return [_en_line(self.en_font, ln, size) for ln in lines], size

    def _df_block(self, txt):
        """The English meaning: up to 3 lines in the English font, a little lighter and smaller than the idiom."""
        if not txt:
            return [], DEF_SIZE
        meas = lambda s, z: get_font(int(z), "Bold", self.en_font).getlength(s)  # noqa: E731
        z = DEF_SIZE
        while z > 34:
            ls = _wrap(lambda s: meas(s, z), txt, TEXT_W, 3)
            if ls:
                return [_en_line(self.en_font, ln, z, DEF_INK, "Bold") for ln in ls], z
            z -= 2
        return [_en_line(self.en_font, txt, 34, DEF_INK, "Bold")], 34

    def _ar_block(self, txt, size, col, n_max=3):
        meas = lambda s, z: _ar_img(self.ar_font, s, z, (0, 0, 0)).width - 60  # noqa: E731
        z = size
        while z > 34:
            ls = _wrap(lambda s: meas(s, z), txt, TEXT_W, n_max)
            if ls:
                return [_ar_img(self.ar_font, ln, z, col) for ln in ls], z
            z -= 2
        return [_ar_img(self.ar_font, txt, 34, col)], 34

    def _layout_card(self, it):
        """Elements of one card, centred on y = 0: dict(en=[(img, x, y, box)], name=(img, cx, cy), mean=[...])."""
        en, size = self._en_block(it["en"])
        pitch = int(size * 1.32)
        blocks = []
        en_h = pitch * (len(en) - 1) + int(size * 1.06)
        blocks.append(("en", en_h))
        name = _ar_img(self.ar_font, f"[{it['name']}]", NAME_SIZE, INK) if it["name"] else None
        if name is not None:
            blocks.append(("name", name.height - 60))
        df, dz = self._df_block(it.get("df") or "")
        dpitch = int(dz * 1.3)
        if df:
            blocks.append(("df", dpitch * (len(df) - 1) + int(dz * 1.0)))
        mean, mz = self._ar_block(it["mean"], MEAN_SIZE, RED) if it["mean"] else ([], MEAN_SIZE)
        mpitch = int(mz * 1.45)
        if mean:
            blocks.append(("mean", mpitch * (len(mean) - 1) + max(m.height for m in mean) - 60))
        gaps = {"name": 62, "df": 58, "mean": 72}
        total = sum(h for _, h in blocks) + sum(gaps[k] for k, _ in blocks[1:])
        y = -total / 2
        out = dict(en=[], name=None, df=[], mean=[], h=total)
        for kind, h in blocks:
            if kind != "en":
                y += gaps[kind]
            if kind == "en":
                for i, (im, base, adv, p) in enumerate(en):
                    by = y + size * 0.84 + i * pitch  # baseline
                    l, r = _ink(im)
                    x = 540 - (l + r) / 2  # the image's left edge: the letters are centred
                    pad = size * 0.16  # the same room on both sides of the letters
                    box = (x + l - pad, by - size * 0.86, x + r + pad, by + size * 0.2)
                    out["en"].append((im, x, by - base, box))
            elif kind == "name":
                out["name"] = (name, 540, y + h / 2)
            elif kind == "df":
                for i, (im, base, adv, p) in enumerate(df):
                    by = y + dz * 0.78 + i * dpitch
                    l, r = _ink(im)
                    out["df"].append((im, 540 - (l + r) / 2, by - base))
            else:
                for i, im in enumerate(mean):
                    out["mean"].append((im, 540, y + (h - mpitch * (len(mean) - 1)) / 2 + i * mpitch))
            y += h
        return out

    def _layout_intro(self):
        """The hook: title words (each its own image, slammed in one by one) + the Arabic subtitle."""
        size = 112
        meas = lambda s, z: get_font(int(z), "Black", self.en_font).getlength(s)  # noqa: E731
        lines = None
        while size > 56:
            lines = _wrap(lambda s: meas(s, size), self.title, TEXT_W, 3)
            if lines:
                break
            size -= 4
        lines = lines or [self.title]
        pitch = int(size * 1.3)
        sub, sz = self._ar_block(self.subtitle, 56, RED, 2) if self.subtitle else ([], 56)
        spitch = int(sz * 1.45)
        sub_h = (spitch * (len(sub) - 1) + max(m.height for m in sub) - 60) if sub else 0
        total = pitch * (len(lines) - 1) + size * 1.06 + (70 + sub_h if sub else 0)
        y = -total / 2
        words, boxes = [], []
        sp = meas(" ", size)
        for i, ln in enumerate(lines):
            by = y + size * 0.84 + i * pitch
            l, _, r, _ = get_font(int(size), "Black", self.en_font).getbbox(ln, anchor="ls")  # the letters' ink
            x = 540 - (l + r) / 2
            pad = size * 0.16
            boxes.append((x + l - pad, by - size * 0.86, x + r + pad, by + size * 0.2))
            for wd in ln.split():
                im, base, adv, p = _en_line(self.en_font, wd, size)
                words.append((im, x + adv / 2, by - base + im.height / 2))
                x += adv + sp
        y += pitch * (len(lines) - 1) + size * 1.06 + 70
        subs = [(im, 540, y + (sub_h - spitch * (len(sub) - 1)) / 2 + i * spitch) for i, im in enumerate(sub)]
        return dict(words=words, boxes=boxes, sub=subs, h=total)

    def _layout_end(self):
        items, y = [], 0
        if self.e_intro:
            im = _ar_img(self.ar_font, self.e_intro, 50, (110, 110, 116)) if ARABIC_RE.search(self.e_intro) else \
                _en_line(self.en_font, self.e_intro, 50, (110, 110, 116))[0]
            items.append(("plain", im, y + im.height / 2 - 30))
            y += im.height - 60 + 56
        n = len(self.e_q)
        size = 92 if n <= 2 else 76
        for s, col in self.e_q:
            mark = col != to_rgb("white")
            if ARABIC_RE.search(s):
                im = _ar_img(self.ar_font, s, size, INK)
                h_ = im.height - 60
                items.append(("mark" if mark else "plain", im, y + h_ / 2))
            else:
                z = size
                while z > 44 and get_font(int(z), "Black", self.en_font).getlength(s) > TEXT_W:
                    z -= 2
                im, base, adv, p = _en_line(self.en_font, s, z)
                l, r = _ink(im)
                im = im.crop((max(0, l - 30), 0, min(im.width, r + 30), im.height))  # centred by its letters
                h_ = int(z * 1.06)
                items.append(("mark" if mark else "plain", im, y + z * 0.84 - base + im.height / 2))
            y += h_ + 34
        if self.e_cta:
            cta, _ = self._ar_block(self.e_cta, 52, RED, 2) if ARABIC_RE.search(self.e_cta) else \
                ([_en_line(self.en_font, self.e_cta, 52, RED)[0]], 52)
            y += 36
            for im in cta:
                h_ = im.height - 60
                items.append(("cta", im, y + h_ / 2))
                y += h_ + 18
        total = y
        return dict(items=[(k, im, cy - total / 2) for k, im, cy in items], h=total)

    def _layout(self):
        self.cards = [self._layout_card(it) for it in self.items]
        self.intro = self._layout_intro() if self.title else None
        self.end = self._layout_end() if self.has_end else None
        tallest = max([c["h"] for c in self.cards] + [self.intro["h"] if self.intro else 0,
                                                       self.end["h"] if self.end else 0])
        self.BH = int(min(1180, max(700, tallest + 300)))
        self.BY = int(CY - self.BH / 2)
        # the band (with the handle at its foot) and its shadow, drawn once
        band = Image.new("RGBA", (W, self.BH), BAND + (255,))
        g = np.linspace(0, 1, self.BH, dtype=np.float32)[:, None]
        shade = (1 - 0.025 * g) * 255  # a hint of light from above
        arr = np.asarray(band, np.float32)
        arr[..., :3] = arr[..., :3] * (shade[..., None] / 255)
        band = Image.fromarray(arr.astype(np.uint8), "RGBA")
        if self.handle:
            h_im = _en_line(self.en_font, self.handle, 30, (200, 200, 204))[0] if not ARABIC_RE.search(self.handle) \
                else _ar_img(self.ar_font, self.handle, 30, (200, 200, 204))
            composite(band, h_im, int(540 - h_im.width / 2), int(self.BH - 52 - h_im.height / 2))
        self.band = band
        m = Image.new("L", (W + 200, self.BH + 200), 0)
        ImageDraw.Draw(m).rectangle([0, 100 + 14, W + 200, 100 + self.BH + 14], fill=150)
        m = m.filter(ImageFilter.GaussianBlur(28))
        self.shadow = Image.new("RGBA", m.size, (0, 0, 0, 0))
        self.shadow.putalpha(m)

    # ============================================================ timeline
    def _timeline(self):
        """Scenes on the band: [dict(kind, k, L = landed, x = leaves)]; a transition runs from x to the next L."""
        self.scenes = []
        self.voices = []
        self.impacts = []
        t = OPEN
        if self.intro:
            nw = len(self.intro["words"])
            sc = dict(kind="intro", k=-1, L=t, slam=[t - 0.12 + 0.15 * i for i in range(nw)])
            last = sc["slam"][-1] + 0.2
            sc["hl"] = (last - 0.05, last + 0.35)
            sc["sub"] = last + 0.25
            sc["x"] = sc["sub"] + 0.45 + (1.3 if self.intro["sub"] else 0.7)  # long enough to read it
            self.impacts += [(a + 0.17, 0.8) for a in sc["slam"]]
            self.scenes.append(sc)
            t = sc["x"] + TR
        for k, it in enumerate(self.items):
            c = self.cards[k]
            sc = dict(kind="card", k=k, L=t)
            sc["hl"] = (t, t + 0.34)
            sc["name"] = t + 0.3
            cur = t + (0.55 if c["name"] is not None else 0.35)
            x = t + self.hold
            said = t  # when the English has been said
            if (k, "w") in self.clip:
                path, ln = self.clip[(k, "w")]
                self.voices.append((t + 0.1, path))
                said = t + 0.1 + ln
                x = max(x, said + 0.6)
            sc["df"] = None
            if c["df"]:  # the English meaning, after the English has been said; then its own clip
                sc["df"] = max(cur, said + 0.05)
                nd = len(c["df"])
                df_end = sc["df"] + 0.2 * (nd - 1) + 0.4
                cur = sc["df"] + 0.45
                x = max(x + 0.8, df_end + 1.4)  # more to read
                if (k, "e") in self.clip:
                    path, ln = self.clip[(k, "e")]
                    self.voices.append((sc["df"] + 0.05, path))
                    x = max(x, sc["df"] + 0.05 + ln + 0.6)
            sc["mean"] = cur
            nm = len(c["mean"])
            mean_end = sc["mean"] + 0.25 * max(0, nm - 1) + 0.42 if nm else cur
            sc["x"] = max(x, mean_end + 0.9)
            if "punch" in self.touch:
                self.impacts.append((sc["hl"][1], 0.55))
            self.scenes.append(sc)
            t = sc["x"] + TR
        if self.end:
            sc = dict(kind="end", k=-2, L=t)
            sc["x"] = t + 4.4
            self.scenes.append(sc)
            self.base_duration = sc["x"]
        else:
            self.scenes[-1]["x"] += 0.4
            self.base_duration = self.scenes[-1]["x"] + 0.3
        self.dur = self.base_duration
        # the move between scene i and i + 1
        self.moves = []
        for i in range(len(self.scenes) - 1):
            self.moves.append(MIX[i % len(MIX)] if self.transition == "mix" else self.transition)
        self.cover_time = (self.scenes[0]["x"] - 0.05) if self.intro else self.scenes[0]["x"] - 0.3

    # ============================================================ content layers (W x BH, transparent)
    def _content(self, i, t):
        """Scene i as it looks at time t (clamped to its landed / final state)."""
        sc = self.scenes[i]
        if t >= sc["x"]:
            key = (i, "final")
        elif t < sc["L"]:
            key = (i, "pre")
        else:
            key = None
        if key is not None:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            im = self._draw_content(i, sc["x"] if key[1] == "final" else sc["L"] - 1e-3)
            self._cache[key] = im
            while len(self._cache) > 8:
                self._cache.popitem(last=False)
            return im
        return self._draw_content(i, t)

    def _band_img(self, content):
        im = self.band.copy()
        im.alpha_composite(content)
        return im

    def _draw_content(self, i, t):
        sc = self.scenes[i]
        lay = Image.new("RGBA", (W, self.BH), (0, 0, 0, 0))
        oy = self.BH / 2
        if sc["kind"] == "card":
            self._draw_card(lay, sc, self.cards[sc["k"]], t, oy)
        elif sc["kind"] == "intro":
            self._draw_intro(lay, sc, t, oy)
        else:
            self._draw_end(lay, sc, t, oy)
        return lay

    def _highlight(self, lay, box, p, oy, t0=None, t=None):
        """The highlighter under a line, drawn left -> right (p 0..1), with a light sweep once it is done."""
        if p <= 0:
            return
        x0, y0, x1, y1 = box
        xe = x0 + (x1 - x0) * _ease_out(p, 2)
        d = ImageDraw.Draw(lay)
        d.rectangle([int(x0), int(y0 + oy), int(xe), int(y1 + oy)], fill=self.marker + (255,))
        if p < 1:  # the marker's tip: a slightly rounded, brighter edge
            d.ellipse([int(xe - 8), int(y0 + oy), int(xe + 8), int(y1 + oy)], fill=self.marker + (255,))
        if t0 is not None and "shine" in self.touch:
            u = (t - t0) / 0.55
            if 0 < u < 1:
                w, h = int(x1 - x0), int(y1 - y0)
                sh = Image.new("L", (w, h), 0)
                cx = -h + (w + 2 * h) * _ease_io(u, 2)
                ImageDraw.Draw(sh).polygon([(cx, 0), (cx + 70, 0), (cx + 70 - h * 0.6, h), (cx - h * 0.6, h)],
                                           fill=int(150 * math.sin(math.pi * u)))
                sh = sh.filter(ImageFilter.GaussianBlur(6))
                glint = Image.new("RGBA", (w, h), (255, 255, 255, 0))
                glint.putalpha(sh)
                lay.alpha_composite(glint, (int(x0), int(y0 + oy)))

    def _draw_card(self, lay, sc, c, t, oy):
        h0, h1 = sc["hl"]
        nl = len(c["en"])
        for j, (im, x, y, box) in enumerate(c["en"]):
            a = h0 + (h1 - h0) * j / nl
            b = h0 + (h1 - h0) * (j + 1) / nl
            self._highlight(lay, box, prog(t, a, b), oy, h1, t)
        # the English settles with a small squash when the highlighter finishes
        sq = 0.06 * _spring((t - h1) / 0.5) if t > h1 else 0
        for im, x, y, box in c["en"]:
            if abs(sq) > 0.002:
                s = 1 + sq
                big = _scaled(im, s)
                composite(lay, big, int(x - (big.width - im.width) / 2), int(y + oy - (big.height - im.height) / 2))
            else:
                composite(lay, im, int(x), int(y + oy))
        if c["name"] is not None:
            p = prog(t, sc["name"], sc["name"] + 0.32)
            if p > 0:
                im, cx, cy = c["name"]
                _put(lay, _scaled(im, 0.6 + 0.4 * ease_out_back(p)), cx, cy + oy + 18 * (1 - _ease_out(p)),
                     min(1, p * 2))
        for j, (im, x, y) in enumerate(c["df"]):  # the English meaning writes in left to right
            a = sc["df"] + 0.2 * j
            p = prog(t, a, a + 0.4)
            if p > 0:
                w_ = _wipe(im, _ease_out(p, 2))
                composite(lay, w_, int(x), int(y + oy + 10 * (1 - _ease_out(p))))
        for j, (im, cx, cy) in enumerate(c["mean"]):
            a = sc["mean"] + 0.25 * j
            p = prog(t, a, a + 0.42)
            if p > 0:
                _put(lay, _wipe(im, _ease_out(p, 2), rtl=True), cx, cy + oy)
        if "progress" in self.touch:
            p = prog(t, sc["L"], sc["x"])
            if p > 0:
                ImageDraw.Draw(lay).rectangle([0, self.BH - 10, int(W * p), self.BH], fill=self.bar + (235,))

    def _draw_intro(self, lay, sc, t, oy):
        ins = self.intro
        h0, h1 = sc["hl"]
        nb = len(ins["boxes"])
        for j, box in enumerate(ins["boxes"]):
            self._highlight(lay, box, prog(t, h0 + (h1 - h0) * j / nb, h0 + (h1 - h0) * (j + 1) / nb), oy, h1, t)
        for (im, cx, cy), at in zip(ins["words"], sc["slam"]):
            p = prog(t, at, at + 0.17)
            if p <= 0:
                continue
            s = 1 + 1.4 * (1 - _ease_in(p, 2) if p < 1 else 0) if p < 1 else 1 - 0.07 * _spring((t - at - 0.17) / 0.45)
            _put(lay, _scaled(im, s), cx, cy + oy, min(1, p * 2.5))
        for j, (im, cx, cy) in enumerate(ins["sub"]):
            a = sc["sub"] + 0.2 * j
            p = prog(t, a, a + 0.45)
            if p > 0:
                _put(lay, _wipe(im, _ease_out(p, 2), rtl=True), cx, cy + oy)

    def _draw_end(self, lay, sc, t, oy):
        L = sc["L"]
        for j, (kind, im, cy) in enumerate(self.end["items"]):
            at = L + 0.1 + 0.18 * j
            p = prog(t, at, at + 0.35)
            if p <= 0:
                continue
            if kind == "mark":
                w = im.width - 60
                box = (540 - w / 2 - 14, cy - im.height / 2 + 22, 540 + w / 2 + 14, cy + im.height / 2 - 18)
                self._highlight(lay, box, prog(t, at + 0.1, at + 0.45), oy)
            if kind == "cta":
                _put(lay, _wipe(im, _ease_out(p, 2), rtl=bool(ARABIC_RE.search(self.e_cta))), 540, cy + oy)
            else:
                _put(lay, _scaled(im, 0.7 + 0.3 * ease_out_back(p)), 540, cy + oy, min(1, p * 2))

    # ============================================================ drawing the band
    def _shadow_at(self, frame, x, y, a, sy=1.0):
        if "shadow" not in self.touch or a <= 0.02:
            return
        sh = self.shadow if abs(sy - 1) < 0.01 else self.shadow.resize(
            (self.shadow.width, max(1, int(self.shadow.height * sy))), Image.BILINEAR)
        composite(frame, fade(sh, a), int(x - 100), int(y - 100 - (sh.height - self.shadow.height) / 2))

    def _band_static(self, frame, content, alpha=1.0):
        self._shadow_at(frame, 0, self.BY, alpha)
        im = self._band_img(content)
        composite(frame, fade(im, alpha), 0, self.BY)

    def _open(self, frame, t, content):
        """The opening: a line shoots across, then the band snaps open (with a little overshoot)."""
        p1 = _ease_out(prog(t, 0.0, 0.2), 3)
        p2 = prog(t, 0.16, OPEN)
        if p2 <= 0:
            w = int(W * p1)
            ImageDraw.Draw(frame).rectangle([0, CY - 4, w, CY + 4], fill=BAND + (255,))
            return
        k = 1 - _spring(p2 * 0.9, 6.5, 9.0) if p2 < 1 else 1 - _spring((t - 0.16) / (OPEN - 0.16) * 0.9, 6.5, 9.0)
        h = max(8, int(self.BH * k))
        im = self._band_img(content)
        y0 = (self.BH - h) // 2
        if h < self.BH:
            crop = im.crop((0, max(0, y0), W, min(self.BH, y0 + h)))
        else:  # overshoot: stretch a little
            crop = im.resize((W, h), Image.BILINEAR)
        self._shadow_at(frame, 0, CY - h / 2, min(1.0, k), h / self.BH)
        composite(frame, crop, 0, int(CY - crop.height / 2))

    def _move(self, frame, kind, u, A, B, a_c, b_c):
        """Transition `kind` at u (0..1) from band A to band B (full band images; a_c / b_c = content only)."""
        by = self.BY
        if kind == "wipe":
            self._shadow_at(frame, 0, by, 1)
            band = self.band.copy()
            ea = _erase(a_c, _ease_io(u / 0.55, 2))
            if ea is not None:
                band.alpha_composite(ea)
            eb = _wipe(b_c, _ease_io((u - 0.4) / 0.6, 2))
            if eb is not None:
                band.alpha_composite(eb)
            composite(frame, band, 0, by)
            return frame
        if kind == "whip":
            e = _ease_io(u, 4)
            speed = abs(_ease_io(min(1, u + 0.02), 4) - _ease_io(max(0, u - 0.02), 4)) / 0.04  # 0..~2.5
            k = 1 + speed * 9
            shown = [(im, x) for im, x in ((A, -W * e), (B, W * (1 - e))) if -W < x < W]
            for im, x in shown:  # both shadows first: a shadow never falls on the other band
                self._shadow_at(frame, x, by, 1)
            for im, x in shown:
                composite(frame, _hblur(im, k), int(x), by)
            return _hblur(frame, 1 + speed * 2.2)  # the whole camera whips
        if kind == "slice":
            n = 5
            hs = [self.BH * j // n for j in range(n + 1)]
            self._shadow_at(frame, 0, by, 0.6 * (1 - math.sin(math.pi * u)))
            for j in range(n):
                d = 1 if j % 2 == 0 else -1
                y0, y1 = hs[j], hs[j + 1]
                qa = _ease_in((u - 0.07 * j) / 0.5, 3)
                qb = _ease_out((u - 0.35 - 0.06 * j) / 0.45, 4)
                if qa < 1:
                    strip = A.crop((0, y0, W, y1))
                    composite(frame, _hblur(strip, 1 + 8 * qa), int(d * W * 1.1 * qa), by + y0)
                if qb > 0:
                    strip = B.crop((0, y0, W, y1))
                    composite(frame, _hblur(strip, 1 + 8 * (1 - qb)), int(-d * W * 1.1 * (1 - qb)), by + y0)
            return frame
        if kind == "flip":
            ang = math.pi * _ease_io(u, 3)
            im = A if ang < math.pi / 2 else B
            th = ang if ang < math.pi / 2 else ang - math.pi
            c, s_ = math.cos(th), math.sin(th)
            if abs(c) < 0.02:
                return frame
            D = 2200.0
            hh = self.BH / 2
            zt, zb = -hh * s_, hh * s_  # top edge away from / towards the camera
            ft, fb = D / (D + zt), D / (D + zb)
            yt, yb = CY - hh * c * ft, CY + hh * c * fb
            pad = 260
            dst = [(540 - 540 * ft + pad, yt - by + pad), (540 + 540 * ft + pad, yt - by + pad),
                   (540 + 540 * fb + pad, yb - by + pad), (540 - 540 * fb + pad, yb - by + pad)]
            src = [(0, 0), (W, 0), (W, self.BH), (0, self.BH)]
            out = im.transform((W + 2 * pad, self.BH + 2 * pad), Image.PERSPECTIVE, _persp(dst, src), Image.BILINEAR)
            dark = (1 - abs(c)) * 0.55
            if dark > 0.01:
                a = out.getchannel("A")
                sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
                sh.putalpha(a.point(lambda v: int(v * dark)))
                out.alpha_composite(sh)
            self._shadow_at(frame, 0, by, abs(c), abs(c))
            composite(frame, out, -pad, by - pad)
            return frame
        if kind == "zoom":
            qa = _ease_in(u / 0.45, 2)
            if qa < 1:  # the card rushes into the camera, blurring, and is gone
                s = 1 + 0.75 * qa
                im = _blur(A, 1 + 6 * qa)
                _put(frame, _scaled(im, s), 540, CY, (1 - qa) ** 1.6)
            qb = prog(u, 0.42, 1.0)
            if qb > 0:  # the next one punches in from deep, overshoots and settles
                s = 0.62 + 0.38 * ease_out_back(qb)
                self._shadow_at(frame, 0, by, qb)
                _put(frame, _scaled(_blur(B, 1 + 3 * (1 - qb) ** 2), s), 540, CY, min(1, qb * 3))
            fl = max(0.0, 1 - abs(u - 0.44) / 0.09)
            if fl > 0:
                frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(70 * fl))))
            return frame
        return frame

    def _counter(self, frame, t):
        """A small pill on the band's top edge: 3 / 7 — the number rolls when the card changes."""
        cards = [i for i, sc in enumerate(self.scenes) if sc["kind"] == "card"]
        if not cards:
            return
        first, last = self.scenes[cards[0]], self.scenes[cards[-1]]
        a_in = prog(t, first["L"] - TR * 0.6, first["L"] - TR * 0.1)
        a_out = 1 - prog(t, last["x"], last["x"] + TR * 0.5) if last["x"] < self.dur - 0.5 else 1
        a = min(a_in, a_out)
        if a <= 0:
            return
        k = 0
        roll = 1.0
        for i in cards:
            sc = self.scenes[i]
            if t >= sc["L"] - TR * 0.5:
                k = sc["k"]
                roll = prog(t, sc["L"] - TR * 0.5, sc["L"] - TR * 0.5 + 0.3)
        pw, ph = 176, 62
        pill = Image.new("RGBA", (pw + 40, ph + 40), (0, 0, 0, 0))
        m = Image.new("L", (pw + 40, ph + 40), 0)
        ImageDraw.Draw(m).rounded_rectangle([20, 26, 20 + pw, 26 + ph], ph // 2, fill=110)
        pill.putalpha(m.filter(ImageFilter.GaussianBlur(8)))
        body = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ImageDraw.Draw(body).rounded_rectangle([0, 0, pw - 1, ph - 1], ph // 2, fill=BAND + (255,),
                                               outline=self.bar + (255,), width=4)
        clip = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        f = get_font(34, "Black", self.en_font)
        tot = f"/ {self.n}"
        num_w = max(f.getlength(str(j + 1)) for j in range(self.n))
        tw = num_w + 12 + f.getlength(tot)
        x0 = (pw - tw) / 2
        dd = ImageDraw.Draw(clip)
        ink = self.bar if sum(self.bar) < 450 else INK
        dd.text((x0 + num_w + 12, ph / 2), tot, font=f, fill=ink + (255,), anchor="lm")
        e = _ease_out(roll, 3)
        if k > 0 and e < 1:  # the old number slides up, the new one comes from below
            dd.text((x0 + num_w, ph / 2 - ph * e), str(k), font=f, fill=ink + (255,), anchor="rm")
        dd.text((x0 + num_w, ph / 2 + ph * (1 - e) if k > 0 else ph / 2), str(k + 1), font=f,
                fill=ink + (255,), anchor="rm")
        body.alpha_composite(clip)
        pill.alpha_composite(body, (20, 20))
        s = 0.6 + 0.4 * ease_out_back(min(1, a_in * 1.0)) if a_in < 1 else 1.0
        _put(frame, _scaled(pill, s), 540, self.BY - 2 + 6, a)

    # ============================================================ frame
    def _background(self, t):
        bg = _felt(self.look)
        if "drift" in self.touch:
            dx = 40 + 30 * math.sin(t * 0.23)
            dy = 40 + 30 * math.cos(t * 0.17)
        else:
            dx = dy = 40
        return bg.crop((int(dx), int(dy), int(dx) + W, int(dy) + H))

    def render(self, t):
        frame = self._background(t)
        scenes = self.scenes
        if t < OPEN:
            self._open(frame, t, self._content(0, t))
        else:
            cur = None
            for i, sc in enumerate(scenes):
                if t < sc["x"] or i == len(scenes) - 1:
                    cur = i
                    break
                if i + 1 < len(scenes) and t < scenes[i + 1]["L"]:  # in the move to the next scene
                    u = (t - sc["x"]) / TR
                    a_c, b_c = self._content(i, t), self._content(i + 1, t)
                    frame = self._move(frame, self.moves[i], u, self._band_img(a_c), self._band_img(b_c), a_c, b_c)
                    cur = -1
                    break
            if cur is not None and cur >= 0:
                self._band_static(frame, self._content(cur, t))
        if "counter" in self.touch:
            self._counter(frame, t)
        # camera punch-in on an impact
        z = 0.0
        sx = sy = 0.0
        for ti, st in self.impacts:
            u = t - ti
            if 0 <= u < 0.45:
                z += 0.035 * st * math.exp(-u * 9)
                if st >= 0.8:
                    amp = 9 * st * (1 - u / 0.45)
                    sx += amp * math.sin(u * 85)
                    sy += amp * math.cos(u * 71)
        if z > 0.002 or abs(sx) + abs(sy) > 0.5:
            zz = 1 + z
            big = frame.resize((int(W * zz), int(H * zz)), Image.BILINEAR)
            ox = (big.width - W) // 2 + int(sx)
            oy = (big.height - H) // 2 + int(sy)
            ox = max(0, min(big.width - W, ox))
            oy = max(0, min(big.height - H, oy))
            frame = big.crop((ox, oy, ox + W, oy + H))
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

    # ============================================================ sound
    def sound(self, mx):
        mx.intro(0.02)
        s, pn = mx.whoosh(0.45)
        mx.add(0.0, s, 0.28, pn)
        pop = mx.pop()
        for i, sc in enumerate(self.scenes):
            if sc["kind"] == "intro":
                for a in sc["slam"]:
                    mx.add(a + 0.15, mx.stamp(), 0.32)
                mx.add(sc["hl"][0], mx.scribble(0.36), 0.14)
                if self.intro["sub"]:
                    s, pn = mx.whoosh(0.4)
                    mx.add(sc["sub"], s, 0.1, -pn)
            elif sc["kind"] == "card":
                k = sc["k"]
                # a voice clip starts with the card: the effects step back so they never cover its first syllable
                v = 0.3 if (k, "w") in self.clip else 1.0
                ve = 0.3 if (k, "e") in self.clip else 1.0
                mx.add(sc["L"] - 0.04, mx.thump(), 0.22 * v)
                mx.add(sc["hl"][0], mx.scribble(0.34), 0.14 * v)
                if self.cards[k]["name"] is not None:
                    mx.add(sc["name"] + 0.05, pop, 0.18 * v)
                if sc["df"] is not None:
                    s, pn = mx.whoosh(0.35)
                    mx.add(sc["df"], s, 0.07 * ve, pn)
                if self.cards[k]["mean"]:
                    s, pn = mx.whoosh(0.35)
                    mx.add(sc["mean"], s, 0.08 * min(v, ve), -pn)
            else:
                mx.add(sc["L"] + 0.1, mx.chime(), 0.3)
            if i < len(self.moves):
                kind = self.moves[i]
                x = sc["x"]
                if kind == "whip":
                    s, pn = mx.whoosh(0.5)
                    mx.add(x - 0.02, s, 0.42, pn)
                elif kind == "slice":
                    for j in range(3):
                        s, pn = mx.whoosh(0.28)
                        mx.add(x + 0.08 * j, s, 0.2, pn if j % 2 else -pn)
                elif kind == "flip":
                    mx.add(x, mx.paper(), 0.4)
                    s, pn = mx.whoosh(0.4)
                    mx.add(x + 0.05, s, 0.18, pn)
                elif kind == "zoom":
                    mx.add(x - 0.1, mx.riser(0.3), 0.22)
                    mx.add(x + TR * 0.42, mx.hit(1.0), 0.3)
                else:
                    s, pn = mx.whoosh(0.5)
                    mx.add(x, s, 0.14, pn)
        for at, path in self.voices:
            mx.add_voice(path, at, self.audio_gain)
