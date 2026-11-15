"""English Words — more designs for the word-list page (item type `list`), next to Editorial / Chalkboard in
word_list.py. Each design is a class built once per page (everything still is pre-rendered) with draw(frame, u)
that depends only on the item time u. They share ListPage's layout (`pg.cy`, `pg.pitch`, `pg.sc`) and timing
(`pg._lit`, `pg._row_in`, `pg.starts`, `pg.ends`, `pg.speak`).

    Glass      modern app look: colour-mesh background, frosted glass cards; the card being read turns white,
               springs forward, its badge shows live sound bars and a progress line fills; read cards get a tick
    Pop        bold pop-art: halftone colour, thick black outlines, hard shadows; the card being read jumps out in
               yellow, tilts, and a starburst sticker with a speaker pops on its corner; read cards get a tick
    Spotlight  lyrics style: big centred words on a deep gradient; the word being read grows to full size under a
               soft spotlight with sound bars, the others shrink and dim (read ones a little brighter)
    Bright     the list fills the screen: tall white cards on a bright gradient (its own layout, TOP..BOT); the card
               being read gets a yellow border, springs forward and shows live sound bars; read cards get a tick

`list_palette` colours all four: PALETTES (12 colour pairs) or DUOS (10 two-tone sets: deep base + bright accent,
6 three-tone sets with a second accent; Navy + juice is the default)."""
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from .core import DEFAULT_FONT as CAIRO
from .core import H, W, ease_io, ease_out_back, paste, prog
from .word_list import MESSIRI, PATRICK, PLAYFAIR, RUQAA, _font, _gradient, _ipa, _speaker, _t, resolve_font

POPPINS_B = _font("Poppins", "Poppins-Bold.ttf")
POPPINS_K = _font("Poppins", "Poppins-Black.ttf")
MONTSERRAT = _font("Montserrat", "Montserrat[wght].ttf")
ANTON = _font("Anton", "Anton-Regular.ttf")
TAJAWAL = _font("Tajawal", "Tajawal-Bold.ttf")
TAJAWAL_K = _font("Tajawal", "Tajawal-Black.ttf")
LALEZAR = _font("Lalezar", "Lalezar-Regular.ttf")
READEX = _font("ReadexPro", "ReadexPro[HEXP,wght].ttf")
PLEX_B = _font("IBMPlexSansArabic", "IBMPlexSansArabic-Bold.ttf")
# more families for the font sets
ALEXANDRIA = _font("Alexandria", "Alexandria[wght].ttf")
ALMARAI = _font("Almarai", "Almarai-Bold.ttf")
BALOO = _font("BalooBhaijaan2", "BalooBhaijaan2[wght].ttf")
BANGERS = _font("Bangers", "Bangers-Regular.ttf")
BEBAS = _font("BebasNeue", "BebasNeue-Regular.ttf")
CHANGA = _font("Changa", "Changa[wght].ttf")
FREDOKA = _font("Fredoka", "Fredoka[wdth,wght].ttf")
LEMONADA = _font("Lemonada", "Lemonada[wght].ttf")
LITERATA = _font("Literata", "Literata[opsz,wght].ttf")
LOBSTER = _font("Lobster", "Lobster-Regular.ttf")
MARHEY = _font("Marhey", "Marhey[wght].ttf")
NOTO_KUFI = _font("NotoKufiArabic", "NotoKufiArabic[wght].ttf")
OSWALD = _font("Oswald", "Oswald[wght].ttf")
PLEX_S = _font("IBMPlexSansArabic", "IBMPlexSansArabic-SemiBold.ttf")
REEM = _font("ReemKufi", "ReemKufi[wght].ttf")
RIGHTEOUS = _font("Righteous", "Righteous-Regular.ttf")
# fonts of well-known apps (Google Fonts, OFL): Figma / GitHub, Android / YouTube, Google, learning apps …
INTER = _font("Inter", "Inter[opsz,wght].ttf")
ROBOTO = _font("Roboto", "Roboto[wdth,wght].ttf")
OPENSANS = _font("OpenSans", "OpenSans[wdth,wght].ttf")
NUNITO = _font("Nunito", "Nunito[wght].ttf")
LEXEND = _font("Lexend", "Lexend[wght].ttf")
DMSANS = _font("DMSans", "DMSans[opsz,wght].ttf")
JAKARTA = _font("PlusJakartaSans", "PlusJakartaSans[wght].ttf")
RUBIK = _font("Rubik", "Rubik[wght].ttf")
NOTO_AR = _font("NotoSansArabic", "NotoSansArabic[wdth,wght].ttf")
NASKH = _font("NotoNaskhArabic", "NotoNaskhArabic[wght].ttf")
VAZIR = _font("Vazirmatn", "Vazirmatn[wght].ttf")

# (main colour A, second colour B); Bright uses them as its background gradient (A at the top, B at the bottom)
PALETTES = {"sky": ((56, 152, 236), (99, 182, 255)),
            "royal": ((52, 84, 209), (86, 120, 240)),
            "ocean": ((14, 140, 233), (34, 211, 200)),
            "lavender": ((139, 112, 232), (176, 150, 250)),
            "violet": ((139, 92, 246), (236, 72, 153)),
            "rose": ((232, 92, 150), (250, 130, 175)),
            "coral": ((245, 110, 100), (255, 150, 120)),
            "sunset": ((249, 98, 40), (250, 196, 30)),
            "mango": ((245, 160, 30), (252, 200, 60)),
            "mint": ((16, 185, 129), (163, 230, 53)),
            "emerald": ((12, 150, 100), (40, 185, 120)),
            "tealblue": ((16, 160, 170), (40, 120, 220))}
PALETTE_CHOICES = [("Royal blue", "royal"), ("Ocean", "ocean"), ("Lavender", "lavender"),
                   ("Purple + pink", "violet"), ("Rose", "rose"), ("Coral", "coral"), ("Sunset", "sunset"),
                   ("Mango", "mango"), ("Mint", "mint"), ("Emerald", "emerald"), ("Teal + blue", "tealblue")]
# two-tone sets for Bright: (deep base colour, bright accent)
# two-tone sets: (deep base, bright accent); three-tone sets add a second accent (titles, lesson line, ticks).
# Deep bases dark enough for white text, accents light enough for dark text on the card being read.
DUOS = {"navy_juice": ((37, 26, 102), (229, 245, 24)),
        "navy_orange": ((20, 33, 61), (252, 163, 17)),
        "slate_yellow": ((43, 50, 63), (253, 239, 75)),
        "darkgreen_butter": ((0, 54, 49), (255, 237, 168)),
        "deepblue_warmyellow": ((1, 17, 123), (255, 186, 9)),
        "deepblue_vividyellow": ((1, 17, 123), (255, 219, 0)),
        "teal_beige": ((0, 128, 128), (245, 245, 220)),
        "customs_lemon": ((1, 62, 55), (255, 239, 178)),
        "midnight_coral": ((22, 30, 58), (255, 122, 105)),
        "forest_gold": ((17, 56, 46), (240, 190, 80)),
        "charcoal_mint": ((32, 38, 46), (88, 226, 190)),
        "plum_peach": ((54, 26, 66), (255, 178, 145)),
        "teal_sun": ((7, 62, 72), (255, 204, 70)),
        "wine_blush": ((72, 20, 40), (255, 188, 200)),
        "indigo_lime": ((44, 30, 104), (184, 240, 92)),
        # three tones
        "navy_red_gold": ((17, 26, 54), (238, 82, 83), (255, 206, 92)),
        "midnight_coral_aqua": ((22, 30, 58), (255, 118, 117), (85, 214, 205)),
        "teal_gold_coral": ((10, 54, 64), (255, 196, 76), (255, 128, 108)),
        "plum_pink_yellow": ((46, 22, 64), (255, 120, 184), (255, 218, 70)),
        "charcoal_lime_sky": ((32, 36, 42), (182, 236, 92), (110, 200, 255)),
        "forest_mustard_cream": ((20, 50, 40), (236, 178, 58), (247, 236, 214))}
DUO_CHOICES = [("Navy + juice", "navy_juice"), ("Navy + orange", "navy_orange"), ("Gray blue + yellow", "slate_yellow"),
               ("Dark green + butter yellow", "darkgreen_butter"), ("Deep blue + warm yellow", "deepblue_warmyellow"),
               ("Deep blue + vivid yellow", "deepblue_vividyellow"), ("Teal + beige", "teal_beige"),
               ("Customs green + creamy lemon", "customs_lemon"),
               ("Midnight + coral", "midnight_coral"), ("Forest + gold", "forest_gold"),
               ("Charcoal + mint", "charcoal_mint"), ("Plum + peach", "plum_peach"),
               ("Deep teal + sunflower", "teal_sun"),
               ("Wine + blush", "wine_blush"), ("Indigo + lime", "indigo_lime"),
               ("Navy · red · gold", "navy_red_gold"), ("Midnight · coral · aqua", "midnight_coral_aqua"),
               ("Deep teal · gold · coral", "teal_gold_coral"), ("Plum · pink · yellow", "plum_pink_yellow"),
               ("Charcoal · lime · sky", "charcoal_lime_sky"), ("Forest · mustard · cream", "forest_mustard_cream")]
DEFAULT_PALETTE = "navy_juice"
OWN = "own"  # "the design's own colours": Editorial / Chalkboard use their own pickers, the others their first look
OWN_LOOK = {"Bright": "navy_juice", "Glass": "violet", "Pop": "violet", "Spotlight": "violet",
            "Table": "navy_juice", "Stepper": "navy_juice"}
# the menu: the two- and three-tone sets (the single colours stay in PALETTES only so older projects still render)
PALETTE_CHOICES = [("🎨 Design's own colours", OWN)] + DUO_CHOICES


def _pal_key(pal, design="Bright"):
    if pal == OWN:
        return OWN_LOOK.get(design, DEFAULT_PALETTE)
    return pal if pal in PALETTES or pal in DUOS else DEFAULT_PALETTE


def tones(pal):
    """(dark, light, second light) of a two- / three-tone set, or None (single colours / own colours)."""
    if pal not in DUOS:
        return None
    t = DUOS[pal]
    return t[0], t[1], (t[2] if len(t) > 2 else t[1])


def _pair(pal):
    """(colour A, colour B) of a palette; a two-tone set gives its accent and a deeper shade of it."""
    if pal in DUOS:
        dk, x = DUOS[pal][:2]
        return x, (DUOS[pal][2] if len(DUOS[pal]) > 2 else _mix(x, dk, 0.3))
    return PALETTES[pal]


# Pop: background, its halftone dots (the first four tuned by hand; the others follow colour A)
_POP_BG = {"violet": ((118, 72, 250), (96, 50, 226)), "sunset": ((255, 92, 57), (228, 66, 34)),
           "ocean": ((0, 146, 250), (0, 118, 214)), "mint": ((0, 190, 132), (0, 160, 108))}
YELLOW, BLACK, WHITE = (255, 222, 0), (14, 14, 18), (255, 255, 255)

_cache = {}
PAD = 40  # transparent margin around glow / shadow images


# ---------------------------------------------------------------- helpers
def _mix(a, b, k):
    return tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b))


def _on_white(c, lum=0.2):
    """c darkened just enough to read well on white (relative luminance at most `lum`, contrast about 4.5:1)."""
    def L(col):
        ch = [v / 255 for v in col]
        ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    k = 0.0
    while L(_mix(c, BLACK, k)) > lum and k < 1:
        k += 0.04
    return _mix(c, BLACK, k)


def _lum(c):
    """Relative luminance 0 (black) .. 1 (white)."""
    ch = [v / 255 for v in c]
    ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _vis_w(im):
    """Visible width of a text image (text_img leaves 30 px on each side)."""
    return im.width - 60


def _fit(im, max_w):
    """Shrink a text image so its visible part is at most max_w wide."""
    vw = _vis_w(im)
    if vw <= max_w or vw <= 0:
        return im
    k = max_w / vw
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


IPA_GAP = 22  # between the English word and its IPA when they share a line


def _stack_k(makes, avail, max_h=None):
    """ONE size factor for every row of a page with the meaning on its own line under the word (the IPA beside the
    word): the largest k (<= 1) at which every row's word line and meaning line fit in `avail` px wide and `max_h` px
    tall. makes = one make(k) -> (english, ipa or None, arabic, ...) per row. Every word of the page then has the same
    size, and so has every meaning."""
    def need(imgs):
        en, ipa, ar = imgs[:3]
        w = max(_vis_w(en) + (IPA_GAP + _vis_w(ipa) if ipa is not None else 0), _vis_w(ar))
        h = (en.height - 60) + (ar.height - 60) * 1.2
        return max(w / avail, h / max_h if max_h else 0.0)
    k = 1.0
    for mk in makes:  # k only goes down, so the rows already checked still fit
        for _ in range(8):
            r = need(mk(k))
            if r <= 1:
                break
            k *= max(0.6, 1 / r) * 0.99
    return k


def _place(en, ipa, ar, two_lines, xl, xr, cy, sc):
    """Where the parts of a row go: {"en"/"ipa": (left x, top of the letters), "ar": (right x, centre y)}."""
    eh, ah = en.height - 60, ar.height - 60
    ih = ipa.height - 60 if ipa is not None else 0
    if not two_lines:
        gap = 12 * sc
        y0 = cy - (eh + (gap + ih if ipa is not None else 0)) / 2
        pos = {"en": (xl, y0), "ar": (xr, cy)}
        if ipa is not None:
            pos["ipa"] = (xl, y0 + eh + gap)
    else:
        gap = 16 * sc
        y0 = cy - (eh + gap + ah) / 2
        pos = {"en": (xl, y0), "ar": (xr, y0 + eh + gap + ah / 2)}
        if ipa is not None:
            pos["ipa"] = (xl + _vis_w(en) + IPA_GAP, y0 + eh - ih - 2 * sc)  # on the word's line, bottoms level
    return pos


def _put_row(card, en, ipa, ar, pos):
    """Draw a row's texts onto a card image at the places _place() gave (card coordinates)."""
    for key, im in (("en", en), ("ipa", ipa)):
        if im is not None:
            x, y = pos[key]
            card.alpha_composite(im, (int(round(x - 30)), int(round(y - 30))))
    x, y = pos["ar"]
    card.alpha_composite(ar, (int(round(x + 30 - ar.width)), int(round(y - ar.height / 2))))


def _top(fr, im, x, ytop, alpha=1.0, anchor="c", scale=1.0):
    """Paste a text image by the top of its letters (keeps words with and without descenders on one line)."""
    paste(fr, im, x, ytop + (im.height / 2 - 30) * scale, scale, alpha, anchor)


def _colored(mask, col, k=1.0):
    im = Image.new("RGBA", mask.size, tuple(col) + (0,))
    im.putalpha(mask if k == 1.0 else mask.point(lambda v: min(255, int(v * k))))
    return im


def _padded_alpha(im, pad=PAD):
    m = Image.new("L", (im.width + 2 * pad, im.height + 2 * pad), 0)
    m.paste(im.split()[3], (pad, pad))
    return m


def _gradient_fill(mask, c0, c1, vertical=False):
    """mask (L) filled with a left-to-right (or top-to-bottom) gradient c0 -> c1."""
    w, h = mask.size
    n = h if vertical else w
    ramp = np.linspace(0, 1, max(2, n), dtype=np.float32)
    cols = np.array(c0, np.float32)[None] * (1 - ramp[:, None]) + np.array(c1, np.float32)[None] * ramp[:, None]
    arr = np.repeat(cols[:, None, :], w, axis=1) if vertical else np.repeat(cols[None, :, :], h, axis=0)
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    im.putalpha(mask)
    return im


def _grad_text(src, c0, c1):
    """A text image re-coloured with a horizontal gradient."""
    return _gradient_fill(src.split()[3], c0, c1)


def _round_mask(w, h, r, s=3, outline=0):
    """Anti-aliased rounded rectangle (filled, or only its outline of width `outline`)."""
    big = Image.new("L", (int(w) * s, int(h) * s), 0)
    d = ImageDraw.Draw(big)
    if outline:
        d.rounded_rectangle([0, 0, big.width - 1, big.height - 1], r * s, outline=255, width=int(outline * s))
    else:
        d.rounded_rectangle([0, 0, big.width - 1, big.height - 1], r * s, fill=255)
    return big.resize((int(w), int(h)), Image.LANCZOS)


def _circle_mask(d, s=3):
    big = Image.new("L", (int(d) * s, int(d) * s), 0)
    ImageDraw.Draw(big).ellipse([0, 0, big.width - 1, big.height - 1], fill=255)
    return big.resize((int(d), int(d)), Image.LANCZOS)


def _tick_img(size, col, width):
    s = 3
    im = Image.new("RGBA", (int(size) * s, int(size) * s), (0, 0, 0, 0))
    k = size * s
    ImageDraw.Draw(im).line([(k * 0.2, k * 0.53), (k * 0.42, k * 0.74), (k * 0.82, k * 0.3)],
                            fill=tuple(col) + (255,), width=int(width * s), joint="curve")
    return im.resize((int(size), int(size)), Image.LANCZOS)


def _bars(fr, cx, cy, h, col, u, sp, alpha, n=4, bw=7, gap=6):
    """Live sound bars (moving only while the clip plays)."""
    total = n * bw + (n - 1) * gap
    x0 = cx - total / 2
    playing = sp is not None and sp[0] <= u < sp[1]
    d = ImageDraw.Draw(fr, "RGBA")
    for i in range(n):
        if playing:
            v = 0.35 + 0.65 * abs(math.sin(u * (7.0 + i * 1.7) + i * 1.3))
        elif sp is None:  # no clip: a gentle idle wave
            v = 0.3 + 0.25 * (1 + math.sin(u * 4 + i * 0.9)) / 2
        else:
            v = 0.3
        bh = max(bw, h * v)
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, cy - bh / 2, x + bw, cy + bh / 2], bw / 2, fill=tuple(col) + (int(255 * alpha),))


def _noise(arr, sigma, seed):
    return arr + np.random.default_rng(seed).normal(0, sigma, (H, W, 1)).astype(np.float32)


def _blobs(arr, blobs):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for cx, cy, r, col, s in blobs:
        g = (np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (r * r)) * 1.6) * s)[..., None]
        arr = arr * (1 - g) + np.array(col, np.float32) * g
    return arr


def _to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def _row_state(pg, j, u):
    """(highlight 0..1 of the row being read, settled-after-reading 0..1)."""
    c_in, c_out = pg._lit(j, u)
    return c_in * (1 - c_out), c_out


# ================================================================ Glass
def _mesh(pal):
    key = ("mesh", pal)
    if key not in _cache:
        a, b = _pair(pal)
        if pal in DUOS:  # two-tone: a deep base with soft lighter shades and a touch of the accent
            dk, x = DUOS[pal][:2]
            arr = _gradient([(0, _mix(dk, WHITE, 0.06)), (1, _mix(dk, BLACK, 0.3))])
            arr = _blobs(arr, [(120, 260, 640, _mix(dk, WHITE, 0.22), 0.8), (1000, 820, 560, x, 0.28),
                               (200, 1500, 620, _mix(dk, WHITE, 0.16), 0.6), (980, 1880, 560, _mix(dk, x, 0.25), 0.4)])
        else:
            arr = _gradient([(0, (18, 14, 38)), (1, (8, 6, 20))])
            arr = _blobs(arr, [(120, 260, 640, a, 0.85), (1000, 820, 560, b, 0.62),
                               (200, 1500, 620, _mix(a, b, 0.5), 0.6), (980, 1880, 560, a, 0.55)])
        im = _to_img(_noise(arr, 2.5, 5))
        frost = im.filter(ImageFilter.GaussianBlur(28))
        frost.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, 30)))
        _cache[key] = (im, frost)
    return _cache[key]


class Glass:
    X0, CW = 60, 960

    def __init__(self, pg, opts, title, subtitle, kicker):
        self.pg = pg
        self.pal = _pal_key(opts.get("palette"), type(self).__name__)
        theme, scrim = kit_theme(self.pal, "Glass")
        self.sentence_look = (theme, scrim, POPPINS_B, "SemiBold", "Bold", 34, 0.5)
        a, b = _pair(self.pal)
        self.a, self.b = a, b
        dark = (22, 18, 40)
        self.dark = dark
        sc = pg.sc
        bg, frost = _mesh(self.pal)
        kt = _t(MONTSERRAT, (kicker or "Vocabulary").upper(), 26, WHITE, "Bold", 800)
        pill = Image.new("RGBA", (_vis_w(kt) + 64, 58), (0, 0, 0, 0))
        pm = _round_mask(pill.width, pill.height, 29)
        pill.alpha_composite(_colored(pm, WHITE, 0.2))
        pill.alpha_composite(_colored(_round_mask(pill.width, pill.height, 29, outline=2), WHITE, 0.55))
        pill.alpha_composite(kt, (pill.width // 2 - kt.width // 2, pill.height // 2 - kt.height // 2))
        self.kick = pill
        self.title = _t(POPPINS_K, title, 92, WHITE, "Black", 960)
        self.sub = _grad_text(_t(TAJAWAL_K, subtitle, 62, WHITE, "Black", 940), _mix(a, WHITE, 0.62),
                              _mix(b, WHITE, 0.62)) if subtitle else None
        ch = int(pg.pitch - 24)
        self.ch = ch
        self.bd = int(min(76, ch * 0.5) * max(0.8, sc))  # badge diameter
        self.prog_w = self.CW - 80
        self.rows = []
        tx = 38 + self.bd + 26  # where the words start, right of the badge

        def make(k, w):
            return (_t(POPPINS_B, w["en"], 54 * sc * k, WHITE, "Bold"),
                    _ipa(w["ipa"], 31 * sc * k, (225, 222, 240)) if w["ipa"] else None,
                    _t(TAJAWAL_K, w["ar"], 56 * sc * k, WHITE, "Black"), k)
        kc = _stack_k([lambda k, w=w: make(k, w) for w in pg.words], self.CW - tx - 34, ch * 0.78)
        for j, w in enumerate(pg.words):
            cy = int(pg.cy[j])
            y0 = cy - ch // 2
            (en_n, ipa_n, ar_k, k), two = make(kc, w), True  # one size for the page, the meaning under the word
            pos = _place(en_n, ipa_n, ar_k, two, tx, self.CW - 34, ch / 2, sc)
            ar_n = _fit(_t(TAJAWAL, w["ar"], 56 * sc * k, WHITE, "Bold"), _vis_w(ar_k))
            en_a = _fit(_t(POPPINS_B, w["en"], 54 * sc * k, dark, "Bold"), 520)
            ipa_a = _fit(_ipa(w["ipa"], 31 * sc * k, (110, 104, 135)), 520) if w["ipa"] else None
            ar_a = _grad_text(ar_k, _on_white(a), _on_white(_mix(a, b, 0.45)))
            # frosted card (normal), the same with a tick (read), and the white card (being read) with its glow
            crop = frost.crop((self.X0, y0, self.X0 + self.CW, y0 + ch))
            mask = _round_mask(self.CW, ch, 34)
            card = Image.new("RGBA", (self.CW, ch), (0, 0, 0, 0))
            card.paste(crop, (0, 0), mask)
            card.alpha_composite(_colored(_round_mask(self.CW, ch, 34, outline=2), WHITE, 0.45))
            hi = Image.new("L", (self.CW, ch), 0)
            ImageDraw.Draw(hi).line([(40, 2), (self.CW - 40, 2)], fill=150, width=2)
            card.alpha_composite(_colored(hi, WHITE))
            norm = self._content(card.copy(), en_n, ipa_n, ar_n, pos, ch, self._badge(str(j + 1), False))
            done = self._content(card.copy(), en_n, ipa_n, ar_n, pos, ch, self._badge(None, False))
            glow = _gradient_fill(_padded_alpha(Image.merge("RGBA", [mask] * 4)), a, b).filter(
                ImageFilter.GaussianBlur(20))

            def active(ar_img):
                white = Image.new("RGBA", (self.CW, ch), (0, 0, 0, 0))
                white.paste(Image.new("RGBA", (self.CW, ch), (255, 255, 255, 250)), (0, 0), mask)
                white = self._content(white, en_a, ipa_a, ar_img, pos, ch, None)
                act = Image.new("RGBA", (self.CW + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0))
                act.alpha_composite(_colored(glow.split()[3], _mix(a, b, 0.5), 0.75))
                act.alpha_composite(white, (PAD, PAD))
                return act
            row = dict(norm=norm, done=done, act=active(ar_a))
            if pg.hider:  # the cards without their meaning, and where it goes
                row["norm_h"] = self._content(card.copy(), en_n, ipa_n, blank_like(ar_n), pos, ch,
                                              self._badge(str(j + 1), False))
                row["act_h"] = active(blank_like(ar_a))
                xr, yc = pos["ar"]
                row["off_n"] = (xr + 30 - ar_n.width, yc - ar_n.height / 2)
                row["off_a"] = (PAD + xr + 30 - ar_a.width, PAD + yc - ar_a.height / 2)
                pg.hider.add(j, "n", ar_n, _mix(dark, WHITE, 0.25), WHITE, TAJAWAL, int(56 * sc * k), "Bold")
                pg.hider.add(j, "a", ar_a, WHITE, _on_white(a), TAJAWAL_K, int(56 * sc * k), "Black")
            self.rows.append(row)
        self.badge_ring = self._badge("", True)

    def _badge(self, txt, active):
        """Round badge: gradient disc with a number, a tick (txt None) or nothing (active: sound bars on top)."""
        d = self.bd
        im = _gradient_fill(_circle_mask(d), self.a, self.b)
        if txt:
            n = _t(POPPINS_B, txt, d * 0.5, WHITE, "Bold")
            im.alpha_composite(n, (d // 2 - n.width // 2, d // 2 - n.height // 2))
        elif txt is None:
            tk = _tick_img(d * 0.62, WHITE, max(4, d * 0.09))
            im.alpha_composite(tk, (d // 2 - tk.width // 2, d // 2 - tk.height // 2))
        return im

    def _content(self, card, en, ipa, ar, pos, ch, badge):
        bx = 38 + self.bd // 2
        if badge is not None:
            card.alpha_composite(badge, (bx - badge.width // 2, ch // 2 - badge.height // 2))
        _put_row(card, en, ipa, ar, pos)
        return card

    def draw(self, fr, u):
        pg = self.pg
        fr.paste(_mesh(self.pal)[0], (0, 0))
        hp = prog(u, 0.05, 0.45)
        e = ease_io(hp)
        paste(fr, self.kick, W / 2, 150 + 16 * (1 - e), 1, hp)
        _top(fr, self.title, W / 2, 205 + 24 * (1 - e), prog(u, 0.12, 0.5))
        if self.sub is not None:
            paste(fr, self.sub, W / 2, 372 + 24 * (1 - e), 1, prog(u, 0.2, 0.6))
        for j, r in enumerate(self.rows):
            a, dy = pg._row_in(j, u)
            if a <= 0.01:
                continue
            cy = pg.cy[j] + dy
            hl, done = _row_state(pg, j, u)
            started = u >= pg.starts[j] - 0.12
            hid = pg.hider is not None and pg.hider.hidden(j, u)
            base = r["done"] if started and done > 0 else r["norm"]
            if hid:
                base = with_meaning(r["norm_h"], pg.hider.render(j, "n", u), r["off_n"])
            paste(fr, base, W / 2, cy, 1, a)
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                s = 1 + 0.035 * ease_out_back(c_in)
                act = with_meaning(r["act_h"], pg.hider.render(j, "a", u), r["off_a"]) if hid else r["act"]
                paste(fr, act, W / 2, cy, s, a * hl)
                bx = W / 2 + (self.X0 + 38 + self.bd / 2 - W / 2) * s
                paste(fr, self.badge_ring, bx, cy, s, a * hl)
                _bars(fr, bx, cy, self.bd * 0.48 * s, WHITE, u, pg.speak[j], a * hl, n=4,
                      bw=max(4, int(self.bd * 0.08)), gap=max(3, int(self.bd * 0.06)))
                sp = pg.speak[j]
                t0, t1 = (sp if sp else (pg.starts[j], pg.ends[j]))
                pr = prog(u, t0, t1)
                if pr > 0:  # progress line along the bottom of the card
                    half = self.ch / 2 * s
                    x0 = W / 2 - self.prog_w / 2 * s
                    lw = max(2, int(self.prog_w * s * pr))
                    line = _gradient_fill(Image.new("L", (int(self.prog_w * s) + 1, max(3, int(5 * s))), 255),
                                          self.a, self.b).crop((0, 0, lw, max(3, int(5 * s))))
                    paste(fr, line, x0, cy + half - 12 * s, 1, a * hl, anchor="l")


# ================================================================ Pop
def _halftone(pal):
    key = ("pop", pal)
    if key not in _cache:
        bg = _pair(pal)[0]
        bg, dot = _POP_BG.get(pal, (bg, _mix(bg, BLACK, 0.14)))
        im = Image.new("RGBA", (W, H), tuple(bg) + (255,))
        d = ImageDraw.Draw(im)
        step = 36
        for r, y in enumerate(range(0, H + step, step)):
            for x in range((r % 2) * step // 2, W + step, step):
                k = 0.5 + 0.5 * math.sin(x / 260 + y / 340) * math.cos(y / 420)  # dot size waves over the page
                rad = 3 + 7 * k
                d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=tuple(dot) + (255,))
        burst = Image.new("L", (W, H), 0)  # pale rays from the top
        bd = ImageDraw.Draw(burst)
        for i in range(18):
            a0 = i * 20
            pts = [(W / 2, 260)] + [(W / 2 + 2600 * math.cos(math.radians(a0 + k)),
                                     260 + 2600 * math.sin(math.radians(a0 + k))) for k in (0, 9)]
            bd.polygon(pts, fill=24)
        im.alpha_composite(_colored(burst, WHITE))
        _cache[key] = im
    return _cache[key]


def _outlined(src, col, width):
    """A text image with a thick outline of colour col (alpha dilated)."""
    m = _padded_alpha(src, width + 4)
    ring = m.filter(ImageFilter.MaxFilter(2 * width + 1))
    out = _colored(ring, col)
    inner = Image.new("RGBA", m.size, (0, 0, 0, 0))
    inner.alpha_composite(src, (width + 4, width + 4))
    out.alpha_composite(inner)
    return out


def _hard_shadow(im, dx, dy, col=BLACK):
    out = Image.new("RGBA", (im.width + abs(dx), im.height + abs(dy)), (0, 0, 0, 0))
    out.alpha_composite(_colored(im.split()[3], col), (max(0, dx), max(0, dy)))
    out.alpha_composite(im, (max(0, -dx), max(0, -dy)))
    return out


def _starburst(d, col, spikes=14):
    s = 3
    big = Image.new("L", (int(d) * s, int(d) * s), 0)
    c = d * s / 2
    pts = []
    for i in range(spikes * 2):
        r = c * (1.0 if i % 2 == 0 else 0.74)
        ang = math.pi * i / spikes
        pts.append((c + r * math.cos(ang), c + r * math.sin(ang)))
    ImageDraw.Draw(big).polygon(pts, fill=255)
    m = big.resize((int(d), int(d)), Image.LANCZOS)
    out = Image.new("RGBA", (int(d) + 8, int(d) + 8), (0, 0, 0, 0))
    out.alpha_composite(_colored(m.filter(ImageFilter.MaxFilter(7)), BLACK), (4, 4))
    out.alpha_composite(_colored(m, col), (4, 4))
    return out


class Pop:
    X0, CW = 66, 930

    def __init__(self, pg, opts, title, subtitle, kicker):
        self.pg = pg
        self.pal = _pal_key(opts.get("palette"), type(self).__name__)
        self.sentence_look = (dict(back=YELLOW, ex=BLACK, hl=BLACK, hl_txt=YELLOW, label=(70, 70, 70), head=BLACK,
                                   shadow=BLACK, bars_b=BLACK, border=BLACK, border_w=5),
                              BLACK, POPPINS_K, "Bold", "Black", 16, 0.45)
        sc = pg.sc
        kt = _t(MONTSERRAT, (kicker or "Vocabulary").upper(), 28, WHITE, "Black", 800)
        pill = Image.new("RGBA", (_vis_w(kt) + 56, 60), (0, 0, 0, 0))
        pill.alpha_composite(_colored(_round_mask(pill.width, pill.height, 30), BLACK))
        pill.alpha_composite(kt, (pill.width // 2 - kt.width // 2, pill.height // 2 - kt.height // 2))
        self.kick = pill
        self.title = _hard_shadow(_outlined(_t(ANTON, title.upper(), 118, WHITE, "Regular", 900), BLACK, 9), 9, 10)
        self.sub = None
        if subtitle:
            st = _fit(_t(LALEZAR, subtitle, 62, BLACK, "Regular"), 820)
            band = Image.new("RGBA", (_vis_w(st) + 80, st.height - 24), (0, 0, 0, 0))
            band.alpha_composite(_colored(Image.new("L", band.size, 255), YELLOW))
            ImageDraw.Draw(band).rectangle([0, 0, band.width - 1, band.height - 1], outline=BLACK + (255,), width=5)
            band.alpha_composite(st, (band.width // 2 - st.width // 2, band.height // 2 - st.height // 2 + 2))
            self.sub = _hard_shadow(band, 7, 7).rotate(-2.5, Image.BICUBIC, expand=True)
        ch = int(pg.pitch - 34)
        self.ch = ch
        tab = int(min(96, ch * 0.62))
        self.tab = tab
        self._tilted = {}
        self.rows = []
        spk = _speaker(BLACK, int(78 * max(0.8, sc)))
        self.burst = _starburst(int(118 * max(0.8, sc)), WHITE)
        for im in spk:
            self.burst.alpha_composite(im, (self.burst.width // 2 - im.width // 2 + 4,
                                            self.burst.height // 2 - im.height // 2))

        def make(k, w):
            return (_t(POPPINS_K, w["en"], 56 * sc * k, BLACK, "Black"),
                    _ipa(w["ipa"], 30 * sc * k, (70, 70, 80)) if w["ipa"] else None,
                    _t(LALEZAR, w["ar"], 64 * sc * k, BLACK, "Regular"))
        # the corner sticker covers the top right of the card being read: the word line keeps clear of it
        kc = _stack_k([lambda k, w=w: make(k, w) for w in pg.words], self.CW - (18 + tab + 26) - 28 - 110, ch * 0.8)
        for j, w in enumerate(pg.words):
            (en, ipa, ar), two = make(kc, w), True  # one size for the page, the meaning under the word
            pos = _place(en, ipa, ar, two, 18 + tab + 26, self.CW - 28, ch / 2, sc)
            num = _t(ANTON, str(j + 1), tab * 0.62, WHITE, "Regular")
            row = dict(norm=self._card(WHITE, en, ipa, ar, pos, num, 10),
                       done=self._card(WHITE, en, ipa, ar, pos, None, 10),
                       act=self._card(YELLOW, en, ipa, ar, pos, num, 20))
            if pg.hider:  # the cards without their meaning, and where it goes
                row["norm_h"] = self._card(WHITE, en, ipa, blank_like(ar), pos, num, 10)
                row["act_h"] = self._card(YELLOW, en, ipa, blank_like(ar), pos, num, 20)
                row["off"] = (pos["ar"][0] + 30 - ar.width, pos["ar"][1] - ar.height / 2)
                for key, card_col in (("n", WHITE), ("a", YELLOW)):
                    pg.hider.add(j, key, ar, card_col, BLACK, LALEZAR, int(64 * sc), "Regular")
            self.rows.append(row)

    def _card(self, fill, en, ipa, ar, pos, num, sh):
        ch, cw, tab = self.ch, self.CW, self.tab
        card = Image.new("RGBA", (cw, ch), tuple(fill) + (255,))
        d = ImageDraw.Draw(card)
        tx0, ty0 = 18, (ch - tab) // 2
        d.rectangle([tx0, ty0, tx0 + tab, ty0 + tab], fill=BLACK + (255,))
        if num is not None:
            card.alpha_composite(num, (tx0 + tab // 2 - num.width // 2, ty0 + tab // 2 - num.height // 2))
        else:
            tk = _tick_img(tab * 0.8, YELLOW, max(5, tab * 0.12))
            card.alpha_composite(tk, (tx0 + tab // 2 - tk.width // 2, ty0 + tab // 2 - tk.height // 2))
        _put_row(card, en, ipa, ar, pos)
        d.rectangle([0, 0, cw - 1, ch - 1], outline=BLACK + (255,), width=6)
        return _hard_shadow(card, sh, sh + 2)

    def draw(self, fr, u):
        pg = self.pg
        fr.paste(_halftone(self.pal), (0, 0))
        hp = prog(u, 0.05, 0.35)
        paste(fr, self.kick, W / 2, 128, 0.6 + 0.4 * ease_out_back(hp), hp)
        tp = prog(u, 0.12, 0.45)
        paste(fr, self.title, W / 2, 252, 1.25 - 0.25 * ease_out_back(tp), tp)
        if self.sub is not None:
            sp = prog(u, 0.25, 0.55)
            paste(fr, self.sub, W / 2, 380, 0.5 + 0.5 * ease_out_back(sp), sp)
        for j, r in enumerate(self.rows):
            a, dy = pg._row_in(j, u)
            if a <= 0.01:
                continue
            cy = pg.cy[j] + dy
            hl, done = _row_state(pg, j, u)
            started = u >= pg.starts[j] - 0.12
            base = r["done"] if started and done > 0 else r["norm"]
            hid = pg.hider is not None and pg.hider.hidden(j, u)
            if hid:
                base = with_meaning(r["norm_h"], pg.hider.render(j, "n", u), r["off"])
            cx = self.X0 + base.width / 2
            paste(fr, base, cx, cy + 6, 1, a)
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                k = ease_out_back(c_in)
                ang = -1.6 * k
                act = with_meaning(r["act_h"], pg.hider.render(j, "a", u), r["off"]) if hid else r["act"]
                if c_in >= 0.999 and not hid:  # settled tilt: rotated once per row of this page
                    if j not in self._tilted:
                        self._tilted[j] = act.rotate(-1.6, Image.BICUBIC, expand=True)
                    img = self._tilted[j]
                else:
                    img = act.rotate(ang, Image.BICUBIC, expand=True)
                paste(fr, img, cx - 10 * k + 6, cy - 6 * k + 6, 1 + 0.03 * k, a * hl)
                bp = prog(u, pg.starts[j] + 0.05, pg.starts[j] + 0.35)
                if bp > 0:
                    bob = 1 + 0.06 * math.sin(u * 9) if pg.speak[j] and pg.speak[j][0] <= u < pg.speak[j][1] else 1
                    paste(fr, self.burst.rotate(12 * (1 - bp) - 8, Image.BICUBIC, expand=True),
                          self.X0 + self.CW - 30, cy - self.ch / 2 - 6, ease_out_back(bp) * bob, a * hl)


# ================================================================ Spotlight
def _deep(pal):
    key = ("deep", pal)
    if key not in _cache:
        a, b = _pair(pal)
        if pal in DUOS:  # two-tone: the deep colour, lighter at the top
            dk, x = DUOS[pal][:2]
            arr = _gradient([(0, _mix(dk, WHITE, 0.1)), (0.5, dk), (1, _mix(dk, BLACK, 0.35))])
            arr = _blobs(arr, [(140, 420, 600, _mix(dk, WHITE, 0.2), 0.45), (980, 1450, 640, _mix(dk, x, 0.18), 0.4)])
        else:
            arr = _gradient([(0, _mix(a, BLACK, 0.55)), (0.5, _mix(_mix(a, b, 0.5), BLACK, 0.72)),
                             (1, _mix(b, BLACK, 0.8))])
            arr = _blobs(arr, [(140, 420, 600, _mix(a, BLACK, 0.2), 0.45),
                               (980, 1450, 640, _mix(b, BLACK, 0.3), 0.4)])
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        v = 1 - 0.5 * np.clip(((xx - W / 2) / (W * 0.8)) ** 2 + ((yy - H / 2) / (H * 0.65)) ** 2, 0, 1)
        _cache[key] = _to_img(_noise(arr * v[..., None], 3, 13))
        spot = Image.new("L", (1000, 520), 0)
        ImageDraw.Draw(spot).ellipse([100, 90, 900, 430], fill=255)
        _cache[key + ("spot",)] = _colored(spot.filter(ImageFilter.GaussianBlur(70)), WHITE, 0.22)
    return _cache[key], _cache[key + ("spot",)]


class Spotlight:
    MIN = 0.56          # scale of the rows not being read
    TOP, BOT = 470, 1480

    def __init__(self, pg, opts, title, subtitle, kicker):
        self.pg = pg
        self.pal = _pal_key(opts.get("palette"), type(self).__name__)
        theme, scrim = kit_theme(self.pal, "Spotlight")
        self.sentence_look = (theme, scrim, MONTSERRAT, "SemiBold", "ExtraBold", 34, 0.5)
        a, b = _pair(self.pal)
        self.ar_col = _mix(b, WHITE, 0.35)
        self.kick = _t(MONTSERRAT, "  ".join((kicker or "Vocabulary").upper()), 26, _mix(b, WHITE, 0.55), "Bold", 900)
        self.title = _t(MONTSERRAT, title, 88, WHITE, "Black", 960)
        self.sub = _t(READEX, subtitle, 52, (235, 232, 245), "Bold", 940) if subtitle else None
        self.blocks, self.en_w, self.hblocks, self.ar_off = [], [], [], []
        for j, w in enumerate(pg.words):
            en = _fit(_t(MONTSERRAT, w["en"], 100, WHITE, "ExtraBold"), 900)
            ipa = _fit(_ipa(w["ipa"], 40, (225, 222, 238)), 900) if w["ipa"] else None
            ar = _fit(_t(READEX, w["ar"], 70, self.ar_col, "Bold"), 920)
            self.blocks.append(self._block(en, ipa, ar))
            self.en_w.append(_vis_w(en))
            if pg.hider:  # the block without its meaning, and where it goes
                self.hblocks.append(self._block(en, ipa, blank_like(ar)))
                self.ar_off.append((480 - ar.width // 2, int(104 + 54 + 96 / 2 - ar.height / 2)))
                pg.hider.add(j, "n", ar, _mix(_pair(self.pal)[0], BLACK, 0.55), self.ar_col, READEX, 70, "Bold")
        self.bh = max(b.height for b in self.blocks)
        n = len(self.blocks)
        need = self.bh * (1 + self.MIN * (n - 1)) + 18 * (n - 1)
        self.k = min(1.0, (self.BOT - self.TOP) / need)
        # no word being read (before the first, after the last): every row at one calm, medium size
        self.rest = min(0.8, (self.BOT - self.TOP) / (self.bh * n + 18 * (n - 1)))

    def _block(self, en, ipa, ar):
        """English / IPA / Arabic centred in fixed bands (every block the same height)."""
        h_en, h_ipa, h_ar = 104, 54, 96
        hb = h_en + h_ipa + h_ar
        im = Image.new("RGBA", (960, hb), (0, 0, 0, 0))
        im.alpha_composite(en, (480 - en.width // 2, int(h_en - (en.height - 30))))  # letters sit on the band bottom
        if ipa is not None:
            im.alpha_composite(ipa, (480 - ipa.width // 2, int(h_en + h_ipa / 2 - ipa.height / 2 + 4)))
        im.alpha_composite(ar, (480 - ar.width // 2, int(h_en + h_ipa + h_ar / 2 - ar.height / 2)))
        return im

    def draw(self, fr, u):
        pg = self.pg
        bg, spot = _deep(self.pal)
        fr.paste(bg, (0, 0))
        hp = prog(u, 0.05, 0.45)
        e = ease_io(hp)
        paste(fr, self.kick, W / 2, 150, 1, hp)
        _top(fr, self.title, W / 2, 198 + 20 * (1 - e), prog(u, 0.12, 0.5))
        if self.sub is not None:
            paste(fr, self.sub, W / 2, 352 + 20 * (1 - e), 1, prog(u, 0.2, 0.6))
        n = len(self.blocks)
        focus, state = [], []
        for j in range(n):
            hl, done = _row_state(pg, j, u)
            focus.append(ease_io(hl))
            state.append(done if u >= pg.starts[j] else 0.0)
        anyf = max(focus)
        base = self.k * self.MIN * anyf + self.rest * (1 - anyf)
        scales = [base + (self.k - base) * f for f in focus]
        gap = 18 * self.k
        total = sum(self.bh * s for s in scales) + gap * (n - 1)
        y = (self.TOP + self.BOT) / 2 - total / 2
        self.row_ys = []
        for j, blk in enumerate(self.blocks):
            s = scales[j]
            h = self.bh * s
            cy = y + h / 2
            self.row_ys.append(cy)
            y += h + gap
            a, dy = pg._row_in(j, u)
            if a <= 0.01:
                continue
            f = focus[j]
            if f > 0.01:
                paste(fr, spot, W / 2, cy, 0.6 + 0.4 * s / self.k, a * f)
            alpha = 0.38 + 0.2 * state[j]
            alpha = alpha + (1 - alpha) * f
            if pg.hider is not None and pg.hider.hidden(j, u):
                blk = with_meaning(self.hblocks[j], pg.hider.render(j, "n", u), self.ar_off[j])
            paste(fr, blk, W / 2, cy + dy, s, a * alpha)
            if f > 0.05:
                half = self.en_w[j] * s / 2
                ytxt = cy + dy - h / 2 + 64 * s  # the middle of the English letters
                _bars(fr, max(40, W / 2 - half - 44 * s), ytxt, 50 * s, self.ar_col, u, pg.speak[j], a * f,
                      n=3, bw=max(4, int(8 * s)), gap=max(3, int(6 * s)))


# ================================================================ Bright
def _shadow_card(w, h, r, fill, sh_col, sh_alpha, blur=18, dy=10):
    """A filled rounded card with a soft drop shadow, PAD px of margin on every side."""
    m = _round_mask(w, h, r)
    pm = _padded_alpha(Image.merge("RGBA", [m] * 4))
    out = Image.new("RGBA", pm.size, (0, 0, 0, 0))
    out.alpha_composite(_colored(pm.filter(ImageFilter.GaussianBlur(blur)), sh_col, sh_alpha), (0, dy))
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    card.paste(Image.new("RGBA", (w, h), tuple(fill) + (255,)), (0, 0), m)
    out.alpha_composite(card, (PAD, PAD))
    return out


def _bright_bg(top, bottom):
    key = ("bright", top, bottom)
    if key not in _cache:
        _cache[key] = _to_img(_noise(_gradient([(0, top), (1, bottom)]), 1.0, 7))
    return _cache[key]


_PUNCT = ".,;:!?\"'”“’‘)(…—–"


def _ex_tokens(text, phrase):
    """[(text, highlighted)] pieces of a sample sentence, split at spaces: the *starred* part, else the phrase
    found by paragraphs.find_phrase (other forms too). Punctuation touching a highlighted word stays outside."""
    raw = " ".join(str(text or "").split())
    chars, flags = [], []
    if "*" in raw:
        on = False
        for ch in raw:
            if ch == "*":
                on = not on
            else:
                chars.append(ch)
                flags.append(on and ch != " ")
    else:
        chars, flags = list(raw), [False] * len(raw)
        words, starts, pos = raw.split(" "), [], 0
        for wd in words:
            starts.append(pos)
            pos += len(wd) + 1
        try:
            from .paragraphs import find_phrase
            hit = find_phrase({"words": words}, phrase)
        except Exception:
            hit = None
        if hit:
            for k in range(hit[0], hit[1] + 1):
                wd = words[k]
                core = wd.strip(_PUNCT) or wd
                a = starts[k] + wd.find(core)
                for c in range(a, a + len(core)):
                    flags[c] = True
    for k, ch in enumerate(chars):  # punctuation is never on the pill
        if ch in _PUNCT:
            flags[k] = False
    out, cur, cur_f = [], "", None
    for ch, f in zip(chars, flags):
        if ch == " ":
            if cur:
                out.append((cur, cur_f))
            out.append((" ", False))
            cur, cur_f = "", None
        elif cur and f != cur_f:
            out.append((cur, cur_f))
            cur, cur_f = ch, f
        else:
            cur, cur_f = cur + ch, f
    if cur:
        out.append((cur, cur_f))
    return out


def _wrap(toks, fn, fh, width, room=0.0):
    """Pieces -> lines of [(text, highlighted, width)] no wider than width, breaking only at spaces. The highlighted
    words stay together on one line (unless they alone are too wide) and get `room` px on each side for the pill
    (as empty pieces); the pill is drawn from the first to the last highlighted piece of a line."""
    words, cur = [], []
    for txt, hl in toks:  # a space ends a word
        if txt == " ":
            words.append(cur)
            cur = []
        else:
            cur.append((txt, hl))
    words.append(cur)
    words = [w for w in words if w]
    units = []  # words joined while the highlight runs across the space between them
    for w in words:
        if units and units[-1][-1][-1][1] and w[0][1]:
            units[-1].append(w)
        else:
            units.append([w])
    sp = fn.getlength(" ")

    def measure(unit):
        out, prev = [], False
        for n, w in enumerate(unit):
            if n:
                out.append((" ", False, sp))
            for t, h in w:
                if h and not prev:
                    out.append(("", False, room))
                out.append((t, h, (fh if h else fn).getlength(t)))
                if not h and prev:
                    out.insert(len(out) - 1, ("", False, room))
                prev = h
        if prev:
            out.append(("", False, room))
        return out

    lines, line, lw = [], [], 0.0
    for unit in units:
        pieces = measure(unit)
        wsum = sum(p[2] for p in pieces)
        if line and lw + sp + wsum > width:
            lines.append(line)
            line, lw = [], 0.0
        if line:
            line.append((" ", False, sp))
            lw += sp
        line += pieces
        lw += wsum
    if line:
        lines.append(line)
    return lines


def _bright_scheme(pal):
    """Colours of the Bright design: a bright gradient with white cards (PALETTES) or a two-tone set (DUOS):
    deep background, cards a shade lighter, the accent for the Arabic and the card being read."""
    if pal in DUOS:
        dk, x = DUOS[pal][:2]
        y = DUOS[pal][2] if len(DUOS[pal]) > 2 else x  # three tones: the second accent
        return dict(bg=(_mix(dk, WHITE, 0.07), _mix(dk, BLACK, 0.28)), card=_mix(dk, WHITE, 0.1), card_a=x, ring=None,
                    en=WHITE, ipa=_mix(dk, WHITE, 0.66), ar=x, en_a=dk, ipa_a=_mix(dk, x, 0.4), ar_a=dk,
                    disc=_mix(dk, WHITE, 0.24), num=WHITE, disc_a=dk, bars=x, disc_d=y, tick=dk,
                    title=WHITE, kick=y, sub=y, shadow=_mix(dk, BLACK, 0.7),
                    back=x, ex=dk, hl=dk, hl_txt=y if y != x and _lum(y) > 0.35 else x, label=_mix(dk, x, 0.4),
                    bars_b=dk)
    a, b = PALETTES[pal if pal in PALETTES else "sky"]
    ink, acc = (24, 26, 36), _on_white(a)
    return dict(bg=(a, b), card=WHITE, card_a=WHITE, ring=(255, 206, 60), en=ink, ipa=(110, 114, 130), ar=acc,
                en_a=ink, ipa_a=(110, 114, 130), ar_a=acc, disc=a, num=WHITE, disc_a=a, bars=WHITE,
                disc_d=(34, 170, 100), tick=WHITE, title=WHITE, kick=WHITE, sub=WHITE, shadow=_mix(a, BLACK, 0.6),
                back=WHITE, ex=ink, hl=acc, hl_txt=WHITE, label=(122, 126, 142), bars_b=acc)


# ================================================================ sample sentences (shared)
def _optimal(toks, fn, fh, width, room):
    """Lines chosen like a typesetter does (all break points weighed at once, not line by line): the sum of the
    squared free space of every line but the last is as small as possible, and a very short last line costs extra.
    The highlighted words stay together. Returns lines of [(text, highlighted, width)] (as _wrap)."""
    units = _wrap(toks, fn, fh, 1, room)  # width 1: every unbreakable unit on a line of its own
    sp = fn.getlength(" ")
    ws = [sum(p[2] for p in u) for u in units]
    n = len(units)
    best = [0.0] + [math.inf] * n  # best[j] = cost of setting units[:j]
    cut = [0] * (n + 1)
    for j in range(1, n + 1):
        lw = -sp
        for i in range(j - 1, -1, -1):
            lw += ws[i] + sp
            if lw > width and i < j - 1:
                break
            free = max(0.0, width - lw)
            cost = (free / width) ** 2 if j < n else 2.0 * (max(0.0, 0.5 * width - lw) / width) ** 2
            if best[i] + cost < best[j]:
                best[j], cut[j] = best[i] + cost, i
    lines, j = [], n
    while j > 0:
        i = cut[j]
        line = []
        for k in range(i, j):
            if k > i:
                line.append((" ", False, sp))
            line += units[k]
        lines.append(line)
        j = i
    return lines[::-1]


def open_amount(pg, j, u):
    """How far word j's sample sentence is shown (0-1, eased) and its example dict, or (0, None) outside its time."""
    e = pg.examples[j] if j < len(pg.examples) else None
    if not e or u < e["f0"] or u >= e["f1"] + e["flip"]:
        return 0.0, None
    fl = e["flip"]
    if u < e["f0"] + fl:
        return ease_io(prog(u, e["f0"], e["f0"] + fl)), e
    if u < e["f1"]:
        return 1.0, e
    return 1 - ease_io(prog(u, e["f1"], e["f1"] + fl)), e


def turn(img, ang):
    """img seen while it turns over on its horizontal middle: squashed, with a little perspective and shade."""
    rad = math.radians(ang)
    cos, sin = abs(math.cos(rad)), abs(math.sin(rad))
    w, h = img.size
    nh = max(2, int(round(h * cos)))
    back = 90 < ang % 360 < 270
    k = 0.07 * sin  # the edge coming towards us is wider
    wt, wb = (w * (1 - k), w * (1 + k)) if back else (w * (1 + k), w * (1 - k))
    W0 = int(max(wt, wb)) + 2
    qx = lambda edge: (W0 - edge) / 2 * w / edge  # noqa: E731  (source x reached by the output's left side)
    quad = (-qx(wt), 0, -qx(wb), h, w + qx(wb), h, w + qx(wt), 0)
    out = img.transform((W0, nh), Image.QUAD, quad, Image.BICUBIC)
    if sin > 0.02:
        a = out.split()[3]
        out = ImageEnhance.Brightness(out.convert("RGB")).enhance(1 - 0.35 * sin).convert("RGBA")
        out.putalpha(a)
    return out


def reveal(img, full_h, h, r=40):
    """A card image (PAD margin) of card height full_h shown at height h: its top and its rounded bottom edge."""
    h = int(max(r + 2, min(full_h, h)))
    top = img.crop((0, 0, img.width, PAD + h - r))
    bot = img.crop((0, PAD + full_h - r, img.width, img.height))
    out = Image.new("RGBA", (img.width, top.height + bot.height), (0, 0, 0, 0))
    out.alpha_composite(top)
    out.alpha_composite(bot, (0, top.height))
    return out


class SentenceKit:
    """Draws sample sentences in one look. theme = dict(back = panel colour, ex = text, hl / hl_txt = the word's
    pill and its text, label = EXAMPLE, head = the word above the sentence, shadow, bars_b = sound bars);
    font / weights = the design's (the font set and a 🎨 Style & sound font apply: resolve_font)."""

    def __init__(self, theme, karaoke=False, font=POPPINS_B, w_text="SemiBold", w_hl="Bold", radius=36):
        self.c, self.karaoke, self.radius = theme, karaoke, radius
        self.f_txt = resolve_font(font, w_text)
        self.f_hl = resolve_font(font, w_hl)
        self.f_lab = resolve_font(font, "Bold")

    def sentence(self, phrase, text, width, size_max=50, size_min=34, max_lines=4, max_h=None):
        """The sentence set in `width` px, the word / expression on a pill (find_phrase in any form, or *stars*):
        lines chosen together (_optimal), then justified (a single line is centred, the last line is flush left,
        a line that would need wide gaps stays ragged); the biggest size that fits. Returns dict(lit =
        full colours, dim = karaoke start, boxes = per word (x0, y0, x1, y1, weight), w, h)."""
        from .core import get_font
        c, S = self.c, 2  # drawn at twice the size, then scaled down
        toks = _ex_tokens(text, phrase)
        size = size_max * S
        while True:
            fn, fh = get_font(size, self.f_txt[1], self.f_txt[0]), get_font(size, self.f_hl[1], self.f_hl[0])
            lines = _optimal(toks, fn, fh, width * S, size * 0.2)
            block = max(sum(p[2] for p in ln) for ln in lines) if len(lines) > 1 else width * S
            asc, desc = fn.getmetrics()
            lh = int((asc + desc) * 1.1)
            if (len(lines) <= max_lines and (max_h is None or len(lines) * lh <= max_h * S)) or size <= size_min * S:
                break
            size -= 2 * S
        H0 = len(lines) * lh
        x_left = (width * S - block) / 2
        placed = []  # per line: [(x, text, highlighted, width)]
        for n, line in enumerate(lines):
            lw = sum(p[2] for p in line)
            gaps = [k for k, p in enumerate(line) if p[0] == " "]
            last = n == len(lines) - 1
            extra = 0.0
            if len(lines) > 1 and not last and gaps:
                extra = (block - lw) / len(gaps)
                if extra > size * 0.45:  # too loose to justify cleanly: keep it ragged
                    extra = 0.0
            x = (width * S - lw) / 2 if len(lines) == 1 else x_left
            row = []
            for k, (txt, hl, wdt) in enumerate(line):
                row.append((x, txt, hl, wdt))
                x += wdt + (extra if k in gaps else 0.0)
            placed.append(row)
        layers, boxes = {}, []
        for mode in ("lit", "dim"):
            k_txt, k_pill, k_hl = (1.0, 1.0, 1.0) if mode == "lit" else (0.34, 0.3, 0.5)
            lay = Image.new("RGBA", (width * S, H0), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            y = asc
            for row in placed:
                run = [p for p in row if p[2]]
                pad = size * 0.14
                if run:  # one pill under the highlighted words of this line
                    d.rounded_rectangle([run[0][0] - pad, y - asc * 0.84, run[-1][0] + run[-1][3] + pad,
                                         y + desc * 0.58], size * 0.24, fill=tuple(c["hl"]) + (int(255 * k_pill),))
                for x0, txt, hl, wdt in row:
                    if txt.strip():
                        col = c["hl_txt"] if hl else c["ex"]
                        d.text((x0, y), txt, font=fh if hl else fn,
                               fill=tuple(col) + (int(255 * (k_hl if hl else k_txt)),), anchor="ls")
                        if mode == "lit":
                            e = pad if hl else 2
                            boxes.append(((x0 - e) / S, (y - lh * 0.82) / S, (x0 + wdt + e) / S, (y + lh * 0.3) / S,
                                          len(txt) + 1))
                y += lh
            layers[mode] = lay.resize((width, max(1, H0 // S)), Image.LANCZOS)
        return dict(lit=layers["lit"], dim=layers["dim"], boxes=boxes, w=width, h=max(1, H0 // S))

    def now(self, sl, e, u):
        """The sentence as it looks at time u: all lit, or (karaoke) its words lit one after another while it is read
        (word times from the clip length, by letters)."""
        if not self.karaoke or u >= e["e1"]:
            return sl["lit"]
        img = sl["dim"].copy()
        p = prog(u, e["e0"], e["e1"])
        total = sum(b[4] for b in sl["boxes"]) or 1
        acc = 0.0
        for x0, y0, x1, y1, wt in sl["boxes"]:
            if acc / total >= p:
                break
            box = tuple(int(round(v)) for v in (max(0, x0), max(0, y0), min(sl["w"], x1), min(sl["h"], y1)))
            if box[2] > box[0] and box[3] > box[1]:
                img.paste(sl["lit"].crop(box), box[:2])
            acc += wt
        return img

    def label(self, size=22):
        return _t(self.f_lab[0], "  ".join("EXAMPLE"), size, self.c["label"], self.f_lab[1])

    def panel(self, phrase, text, pw, handle=False, max_h=520):
        """A panel of its own: (grab handle) · the word + EXAMPLE label (+ sound bars) · the sentence."""
        c = self.c
        lab = self.label()
        sl = self.sentence(phrase, text, pw - 110, max_h=max_h)
        word = _fit(_t(self.f_hl[0], phrase, 34, c["head"], self.f_hl[1]), pw - 300)
        head = max(lab.height, word.height) - 60
        ph = (30 if handle else 0) + 28 + head + 22 + sl["h"] + 36
        panel = _shadow_card(pw, ph, self.radius, c["back"], c["shadow"], 0.4, 26, 14)
        if c.get("border"):
            ImageDraw.Draw(panel).rounded_rectangle([PAD, PAD, PAD + pw - 1, PAD + ph - 1], self.radius,
                                                    outline=tuple(c["border"]) + (255,), width=c.get("border_w", 3))
        y0 = PAD + 28
        if handle:  # the grab handle of a bottom sheet
            ImageDraw.Draw(panel).rounded_rectangle([PAD + pw / 2 - 40, PAD + 14, PAD + pw / 2 + 40, PAD + 22], 4,
                                                    fill=tuple(c["label"]) + (140,))
            y0 += 30
        panel.alpha_composite(word, (PAD + 40 - 30, y0 - 30))
        lx = PAD + pw - 40 - (lab.width - 60) - 30 - 50  # the label, left of the sound bars
        panel.alpha_composite(lab, (lx, y0 + (word.height - 60 - (lab.height - 60)) // 2 - 30))
        return dict(panel=panel, h=ph, w=pw, sent=sl, sent_xy=(PAD + 55, y0 + head + 22),
                    bars=(pw - 40 - 18, y0 - PAD + (word.height - 60) / 2))

    def compose(self, base, sent, xy, e, u):
        img = base.copy()
        img.alpha_composite(self.now(sent, e, u), tuple(int(v) for v in xy))
        return img

    def bars(self, fr, x, y, e, u, a, s=1.0):
        _bars(fr, x, y, 26 * s, self.c["bars_b"], u, e["speak"], a, n=4, bw=5, gap=4)


class SentenceOverlay:
    """The six ways to show a sample sentence for the designs that draw no card of their own for it (Glass, Pop,
    Spotlight, Editorial, Chalkboard): a panel in the design's look, anchored at the row being read; the rest of the
    page steps back under a scrim (the row itself stays clear, except in Focus zoom)."""
    TOP, BOT, SHEET_BOT = 440, 1700, 1700

    def __init__(self, pg, style, kit, scrim, scrim_k=0.5):
        self.pg, self.st, self.kit, self.scrim, self.scrim_k = pg, style, kit, tuple(scrim), scrim_k
        self.p = {}
        for j, w in enumerate(pg.words):
            e = pg.examples[j] if j < len(pg.examples) else None
            if e:
                self.p[j] = kit.panel(w["en"], e["text"], 980 if style == "sheet" else 960, handle=style == "sheet",
                                      max_h=640)

    def draw(self, fr, u, ys=None):
        pg = self.pg
        ys = ys or pg.cy
        opens = [open_amount(pg, j, u) for j in range(len(pg.words))]
        cur = max(range(len(opens)), key=lambda j: opens[j][0]) if opens else 0
        o, e = opens[cur] if opens else (0.0, None)
        if e is None or cur not in self.p:
            return
        P, y, half = self.p[cur], ys[cur], pg.pitch / 2
        mask = Image.new("L", (W, H), int(255 * self.scrim_k * (1.2 if self.st == "zoom" else 1.0) * o))
        if self.st != "zoom":  # the word's own row stays clear
            ImageDraw.Draw(mask).rectangle([0, int(y - half), W, int(y + half)], fill=0)
        fr.paste(self.scrim + (255,), (0, 0, W, H), mask)
        img = self.kit.compose(P["panel"], P["sent"], P["sent_xy"], e, u) if o > 0.02 else P["panel"]
        ph, pw = P["h"], P["w"]
        clamp = lambda cy: min(max(cy, self.TOP + ph / 2), self.BOT - ph / 2)  # noqa: E731
        bars_at = None
        if self.st == "sheet":
            rest = self.SHEET_BOT - ph / 2
            cy = rest + (H + ph / 2 - rest) * (1 - o)
            paste(fr, img, W / 2, cy, 1.0, 1.0)
            bars_at = (W / 2 - pw / 2 + P["bars"][0], cy - ph / 2 + P["bars"][1], 1.0)
        elif self.st == "bubble":
            below = y < (self.TOP + self.BOT) / 2
            edge = y + (half - 4) * (1 if below else -1)
            cy = min(max(edge + (28 + ph / 2) * (1 if below else -1), self.TOP - 20 + ph / 2), 1720 - ph / 2)
            k = 0.55 + 0.45 * ease_out_back(o) if o < 1 else 1.0
            tail_x = W / 2 - pw / 2 + 150
            tail = Image.new("RGBA", (120, 64), (0, 0, 0, 0))
            pts = [(12, 64), (108, 64), (34, 0)] if below else [(12, 0), (108, 0), (34, 64)]
            ImageDraw.Draw(tail).polygon(pts, fill=tuple(self.kit.c["back"]) + (255,))
            tail = tail.resize((60, 32), Image.LANCZOS)
            bx, by = tail_x + (W / 2 - tail_x) * k, edge + (cy - edge) * k
            paste(fr, tail, tail_x + 18, edge + 16 * (1 if below else -1), k, min(1.0, o * 2))
            paste(fr, img, bx, by, k, min(1.0, o * 2))
            bars_at = (W / 2 - pw / 2 + P["bars"][0], by - ph / 2 + P["bars"][1], 1.0)
        elif self.st == "zoom":
            s = 0.86 + 0.14 * ease_out_back(o) if o < 1 else 1.0
            cy = (self.TOP + self.BOT) / 2
            paste(fr, img, W / 2, cy, s, min(1.0, o * 1.6))
            bars_at = (W / 2 + (P["bars"][0] - pw / 2) * s, cy + (P["bars"][1] - ph / 2) * s, s)
        elif self.st == "flip":  # the panel turns in over the row (edge-on -> facing) and away again
            ang = 90 + 90 * o if u < e["f1"] else 270 - 90 * o
            cy = clamp(y)
            paste(fr, turn(img, ang), W / 2, cy, 1.0, 1.0)
            bars_at = (W / 2 - pw / 2 + P["bars"][0], cy - ph / 2 + P["bars"][1], 1.0)
        elif self.st == "expand":  # the panel unrolls from the row's edge (down, or up near the bottom)
            hh = ph * o
            down = y + half + ph <= self.BOT + 20
            img = reveal(img, ph, hh)
            vis = img.height - 2 * PAD
            cy = (y + half - 8 + vis / 2) if down else (y - half + 8 - vis / 2)
            paste(fr, img, W / 2, cy, 1.0, min(1.0, o * 3))
            if o >= 0.999:
                bars_at = (W / 2 - pw / 2 + P["bars"][0], cy - vis / 2 + P["bars"][1], 1.0)
        else:  # drawer: slides in from the right over the row, and out again
            cy = clamp(y)
            paste(fr, img, W / 2 + W * (1 - o), cy, 1.0, 1.0)
            bars_at = (W / 2 - pw / 2 + P["bars"][0], cy - ph / 2 + P["bars"][1], 1.0)
        if o >= 0.999 and bars_at:
            self.kit.bars(fr, bars_at[0], bars_at[1], e, u, 1.0, bars_at[2])


def kit_theme(pal, design):
    """A sentence-panel look from a design's colours: a two- / three-tone set, or its single colour pair."""
    pal = _pal_key(pal, design)
    tn = tones(pal)
    if tn:
        dk, x, y = tn
        return dict(back=x, ex=dk, hl=dk, hl_txt=y if y != x and _lum(y) > 0.35 else x, label=_mix(dk, x, 0.4),
                    head=dk, shadow=_mix(dk, BLACK, 0.7), bars_b=dk), _mix(dk, BLACK, 0.35)
    a, b = PALETTES[pal]
    acc = _on_white(a)
    return dict(back=WHITE, ex=(24, 26, 36), hl=acc, hl_txt=WHITE, label=(122, 126, 142), head=acc,
                shadow=_mix(a, BLACK, 0.6), bars_b=acc), _mix(a, BLACK, 0.75)


# ================================================================ meanings hidden until the word is spoken
# vocab `list_hide`: the Arabic meanings start hidden and are uncovered just after their word is heard
HIDE_STYLES = [("Off — the meanings show from the start", "none"),
               ("Reveal — blurred, wiped clear with a shine", "reveal"),
               ("Typewriter — typed in letter by letter", "typewriter"),
               ("Split-flap — letters flip like a departure board, then settle", "splitflap")]
_HIDE_WIN = {"reveal": (0.3, 0.85), "typewriter": (0.25, 1.3), "splitflap": (0.2, 1.1)}
_AR_LETTERS = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"


def hide_window(style, start, word_end):
    """(t0, t1): the meaning of a word heard from `start` is uncovered between t0 and t1 (before word_end, when the
    card may flip over to its sample sentence)."""
    a, b = _HIDE_WIN.get(style, (0.3, 0.85))
    t1 = max(start + 0.35, min(start + b, word_end - 0.05))
    return min(start + a, t1 - 0.3), t1


def hide_sounds(style, t0, t1, n_letters):
    """Sound cues (kind, time, gain) of a meaning being uncovered."""
    if style == "reveal":
        return [("swish", t0 - 0.05, 0.1)]
    if style == "typewriter":
        n = max(1, n_letters)
        return [("tap", t0 + (t1 - t0) * k / n, 0.07) for k in range(n)]
    if style == "splitflap":
        steps = max(4, int((t1 - t0) / 0.05))
        return [("tap", t0 + (t1 - t0) * k / steps, 0.045) for k in range(steps)] + [("click", t1, 0.14)]
    return []


class MeaningHider:
    """Hides the Arabic meanings of a page until each word is spoken. A design registers every meaning image it
    would draw (`add`, while the page is built, so its fonts apply); while `hidden(j, u)` it draws `render(j, key, u)`
    instead: an image of the same size, placed exactly like the meaning (so it follows the card's scale / tilt).
    reveal = a frosted pill with the word blurred under it, wiped clear right to left with a shine; typewriter = one
    dash per letter, typed in right to left with a cursor; splitflap = scrambled letters that flip and settle."""
    LEVELS = 10
    WAITS = ("dashes", "shimmer", "dots", "ghost", "caret")

    def __init__(self, pg, style, wait="dashes"):
        self.pg, self.style = pg, style
        self.wait = wait if wait in self.WAITS else "dashes"
        self.m = {}
        self.win = []
        for j in range(len(pg.words)):
            e = pg.examples[j] if j < len(pg.examples) else None
            self.win.append(hide_window(style, pg.starts[j], e["f0"] if e else pg.ends[j]))

    def add(self, j, key, img, card_col, text_col, font=None, size=None, weight="Bold", post=None):
        """img = the meaning as drawn (state `key`: 'n' normal / 'a' being read); card_col = what it sits on;
        text_col = its colour; font / size / weight / post (e.g. chalk texture) let the split-flap redraw it."""
        txt = self.pg.words[j]["ar"]
        cover = _mix(card_col, WHITE if _lum(card_col) < 0.45 else BLACK, 0.16)
        it = dict(img=img, cover=cover, col=tuple(text_col), n=max(1, len(txt.replace(" ", ""))))
        vw, vh = img.width - 60, img.height - 60
        if self.style == "reveal":
            pw, ph = vw + 36, vh + 22
            pill = Image.new("RGBA", img.size, (0, 0, 0, 0))
            pill.paste(Image.new("RGBA", (pw, ph), tuple(cover) + (255,)),
                       ((img.width - pw) // 2, (img.height - ph) // 2), _round_mask(pw, ph, ph // 2))
            pill.alpha_composite(img.filter(ImageFilter.GaussianBlur(max(6, vh * 0.2))))
            q = _t(POPPINS_B, "?", max(18, vh * 0.55), text_col, "Bold")
            pill.alpha_composite(q, ((img.width - q.width) // 2, (img.height - q.height) // 2))
            it["pill"] = pill
            sh = Image.new("L", (44, img.height), 0)
            for i in range(44):
                ImageDraw.Draw(sh).line([(i, 0), (i, img.height)], fill=int(170 * math.sin(math.pi * i / 43)))
            it["shine"] = _colored(sh, WHITE)
        elif self.style == "splitflap" and font:
            frames = []
            for lv in range(self.LEVELS + 1):
                row = []
                for var in range(2):
                    rnd = random.Random(j * 1000 + lv * 10 + var + (7 if key == "a" else 0))
                    settled = int(len(txt) * lv / self.LEVELS)
                    s = "".join(c if (k < settled or c == " ") else rnd.choice(_AR_LETTERS) for k, c in enumerate(txt))
                    im = _t(font, s, size, text_col, weight, vw)
                    if post:
                        im = post(im)
                    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    x = img.width - im.width  # right aligned like the meaning
                    canvas.alpha_composite(im.crop((max(0, -x), 0, im.width, im.height)),
                                           (max(0, x), (img.height - im.height) // 2))
                    row.append(canvas)
                frames.append(row)
            it["frames"] = frames
        self.m[(j, key)] = it

    def hidden(self, j, u):
        return u < self.win[j][1]

    def _waiting(self, out, it, img, cw, u):
        """Typewriter: what holds the place of the letters not typed yet (x from the left of the text to the cursor).
        wait = dashes / shimmer (a skeleton bar with light sweeping over it) / dots (three bouncing dots, "is
        typing…") / ghost (the meaning faint and blurred: its shape, not its letters) / caret (only the cursor)."""
        vw, vh = img.width - 60, img.height - 60
        x0, x1 = 30, img.width - 30 - cw - (14 if cw else 0)
        if x1 - x0 < 4:
            return
        col = it["col"]
        d = ImageDraw.Draw(out)
        if self.wait == "dashes":
            n = it["n"]
            step = vw / n
            yb = img.height - 30 - 2
            for k in range(int(n * cw / vw + 0.5), n):
                xr = img.width - 30 - step * k
                d.rounded_rectangle([xr - step + 4, yb - 5, xr - 3, yb], 2, fill=col + (150,))
        elif self.wait == "shimmer":
            bh = max(10, vh * 0.42)
            y0 = img.height / 2 - bh / 2
            bar = Image.new("L", out.size, 0)
            ImageDraw.Draw(bar).rounded_rectangle([x0, y0, x1, y0 + bh], bh / 2, fill=255)
            base = _colored(bar, col, 0.22)
            sweep = Image.new("L", out.size, 0)  # a soft band of light running right to left, again and again
            sx = img.width - ((u * 1.1) % 1.0) * (img.width + 160) + 80
            sd = ImageDraw.Draw(sweep)
            for i in range(-70, 71, 2):
                sd.line([(sx + i, 0), (sx + i + 30, out.height)], fill=int(150 * (1 - abs(i) / 70)), width=3)
            base.alpha_composite(_colored(ImageChops.multiply(sweep, bar), WHITE, 0.55))
            out.alpha_composite(base)
        elif self.wait == "dots":
            r = max(6, vh * 0.15)
            cy = img.height / 2
            for i in range(3):  # bouncing one after another, like a chat app's "is typing…"
                ph = (u * 2.4 - i * 0.18) % 1.0
                lift = math.sin(math.pi * min(1.0, ph * 2.2)) * r * 1.3 if ph < 0.45 else 0.0
                k = 0.45 + 0.55 * (lift / (r * 1.3))
                x = x1 - r - i * r * 3.0
                if x - r < x0:
                    break
                d.ellipse([x - r, cy - r - lift, x + r, cy + r - lift], fill=col + (int(255 * k),))
        elif self.wait == "ghost":
            if "ghost" not in it:
                it["ghost"] = _fade(img.filter(ImageFilter.GaussianBlur(max(5, vh * 0.16))), 0.32)
            g = it["ghost"].crop((0, 0, int(x1) + 6, img.height))
            out.alpha_composite(g)

    def render(self, j, key, u):
        it = self.m.get((j, key)) or self.m.get((j, "n"))
        if it is None:
            return None
        img = it["img"]
        t0, t1 = self.win[j]
        p = prog(u, t0, t1)
        if p >= 1:
            return img
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        vw = img.width - 60
        if self.style == "reveal":
            if p <= 0:
                return it["pill"]
            out.alpha_composite(_fade(it["pill"], 1 - p))
            cw = max(1, int(vw * ease_io(p))) + 30
            out.alpha_composite(img.crop((img.width - cw, 0, img.width, img.height)), (img.width - cw, 0))
            sx = img.width - cw - 22
            if 0 <= sx < img.width:
                out.alpha_composite(it["shine"].crop((0, 0, min(44, img.width - sx), img.height)), (sx, 0))
            return out
        if self.style == "typewriter":
            n = it["n"]
            shown = int(n * p)
            cw = int(vw * shown / n)
            if cw > 0:
                out.alpha_composite(img.crop((img.width - 30 - cw, 0, img.width, img.height)), (img.width - 30 - cw, 0))
            self._waiting(out, it, img, cw, u)  # what holds the place of the letters still to come
            d = ImageDraw.Draw(out)
            col = it["col"]
            if p > 0 or self.wait == "caret":  # the cursor (blinking while it waits)
                if p > 0 or (u * 1.6) % 1 < 0.6:
                    cx = img.width - 30 - cw - 5
                    d.rounded_rectangle([cx - 5, 32, cx, img.height - 28], 2, fill=col + (255,))
            return out
        if self.style == "splitflap" and "frames" in it:
            if p <= 0:
                return _fade(it["frames"][0][0], 0.55)
            lv = min(self.LEVELS, int(p * self.LEVELS))
            return it["frames"][lv][int(u * 22) % 2]
        return img if p >= 1 else _fade(img, p)


def _fade(img, k):
    out = img.copy()
    out.putalpha(img.split()[3].point(lambda v: int(v * k)))
    return out


def blank_like(img):
    return Image.new("RGBA", img.size, (0, 0, 0, 0))


def with_meaning(card, layer, off):
    """card (without its meaning) + the hider's picture of the meaning at offset off."""
    out = card.copy()
    if layer is not None:
        out.alpha_composite(layer, tuple(int(round(v)) for v in off))
    return out


# how a word-list card shows its sample sentence (vocab `list_ex_style`; `list_karaoke` lights its words in turn)
EX_STYLES = [("Flip — the card turns over", "flip"), ("Expand — the card grows, the sentence slides out", "expand"),
             ("Bottom sheet — a panel slides up", "sheet"), ("Speech bubble — pops out of the card", "bubble"),
             ("Focus zoom — the card comes to the centre", "zoom"), ("Drawer — the card slides away", "drawer")]


class Bright:
    TOP, BOT, GAP, CW = 420, 1660, 22, 960   # the cards fill the screen between the title and the bottom
    SHEET_BOT = 1700  # the bottom sheet's lower edge

    def __init__(self, pg, opts, title, subtitle, kicker):
        self.pg = pg
        pal = opts.get("palette")
        self.c = c = _bright_scheme(_pal_key(pal, "Bright"))
        st = opts.get("ex_style")
        self.ex_style = st if st in dict((v, k) for k, v in EX_STYLES) else "flip"
        self.karaoke = bool(opts.get("karaoke"))
        self.kit = SentenceKit(dict(back=c["back"], ex=c["ex"], hl=c["hl"], hl_txt=c["hl_txt"], label=c["label"],
                                    head=c["hl"] if c["back"] == WHITE else c["ex"], shadow=c["shadow"],
                                    bars_b=c["bars_b"]), self.karaoke)
        n = len(pg.words)
        self.kick = _t(POPPINS_B, (kicker or "Vocabulary").upper(), 28, c["kick"], "Bold", 800)
        self.title = _t(POPPINS_B, title, 80, c["title"], "Bold", 960)
        self.sub = _t(PLEX_B, subtitle, 50, c["sub"], "Bold", 940) if subtitle else None
        ch = int(min(250, (self.BOT - self.TOP - self.GAP * (n - 1)) / n))
        self.ch = ch
        y0 = (self.TOP + self.BOT) / 2 - (n * ch + (n - 1) * self.GAP) / 2
        self.ys = [y0 + j * (ch + self.GAP) + ch / 2 for j in range(n)]
        k0 = min(1.15, ch / 210)  # the text follows the card height
        self.d = d = int(min(96, ch * 0.5))  # badge diameter
        cw, tx = self.CW, 30 + d + 30
        self.cards = []
        kc = _stack_k([lambda k, w=w: (_t(POPPINS_B, w["en"], 62 * k0 * k, c["en"], "Bold"),
                                       _ipa(w["ipa"], 34 * k0 * k, c["ipa"]) if w["ipa"] else None,
                                       _t(PLEX_B, w["ar"], 64 * k0 * k, c["ar"], "Bold")) for w in pg.words],
                      cw - tx - 34, ch * 0.8)
        for j, w in enumerate(pg.words):
            def make(k, w=w, sfx=""):
                return (_t(POPPINS_B, w["en"], 62 * k0 * k, c["en" + sfx], "Bold"),
                        _ipa(w["ipa"], 34 * k0 * k, c["ipa" + sfx]) if w["ipa"] else None,
                        _t(PLEX_B, w["ar"], 64 * k0 * k, c["ar" + sfx], "Bold"), k)
            (en, ipa, ar, k), two = make(kc), True  # one size for the page, the meaning under the word
            en_a, ipa_a, ar_a, _ = make(k, sfx="_a")  # the same sizes in the colours of the card being read
            pos = {key: (x + PAD, y + PAD) for key, (x, y) in _place(en, ipa, ar, two, tx, cw - 34, ch / 2, k0).items()}
            out = {}
            for state in ("n", "a", "d"):  # normal / being read / read
                im = _shadow_card(cw, ch, 32, c["card_a"] if state == "a" else c["card"], c["shadow"],
                                  0.3 if state == "a" else 0.18)
                if state == "a" and c["ring"]:
                    ImageDraw.Draw(im).rounded_rectangle([PAD, PAD, PAD + cw - 1, PAD + ch - 1], 32,
                                                         outline=tuple(c["ring"]) + (255,), width=8)
                disc = _colored(_circle_mask(d), c[{"n": "disc", "a": "disc_a", "d": "disc_d"}[state]])
                if state == "d":
                    tk = _tick_img(d * 0.62, c["tick"], max(5, d * 0.1))
                    disc.alpha_composite(tk, (d // 2 - tk.width // 2, d // 2 - tk.height // 2))
                elif state == "n":
                    nm = _t(POPPINS_B, str(j + 1), d * 0.5, c["num"], "Bold")
                    disc.alpha_composite(nm, (d // 2 - nm.width // 2, d // 2 - nm.height // 2))
                im.alpha_composite(disc, (PAD + 30, PAD + ch // 2 - d // 2))
                row = (en_a, ipa_a, ar_a) if state == "a" else (en, ipa, ar)
                if pg.hider and state != "d":  # the same card without its meaning (drawn by the hider)
                    h = im.copy()
                    _put_row(h, row[0], row[1], blank_like(row[2]), pos)
                    out[state + "_h"] = h
                _put_row(im, *row, pos)
                out[state] = im
            if pg.hider:
                out["ar_off"] = (pos["ar"][0] + 30 - ar.width, pos["ar"][1] - ar.height / 2)
                for key, img, card_col, col in (("n", ar, c["card"], c["ar"]), ("a", ar_a, c["card_a"], c["ar_a"])):
                    pg.hider.add(j, key, img, card_col, col, PLEX_B, int(64 * k0 * k), "Bold")
            self.cards.append(out)
        for j, w in enumerate(pg.words):  # sample sentences: the pictures the chosen style needs
            ex = pg.examples[j] if j < len(pg.examples) else None
            if ex:
                self._build_examples(j, w, ex, self.cards[j])

    # ------------------------------------------------------------ sample sentences
    def _sentence(self, w, text, width, size_max=50, size_min=34, max_lines=4, max_h=None):
        return self.kit.sentence(w["en"], text, width, size_max, size_min, max_lines, max_h)

    def _sent_now(self, sl, e, u):
        return self.kit.now(sl, e, u)

    def _label(self, size=22):
        return self.kit.label(size)

    def _build_examples(self, j, w, e, out):
        """The images the chosen style needs for word j's sample sentence."""
        c, cw, ch, d = self.c, self.CW, self.ch, self.d
        front = out["a"].copy()  # the active front with its sound bars drawn in (it moves as one picture)
        _bars(front, PAD + 30 + d / 2, PAD + ch / 2, d * 0.45, c["bars"], 0.0, None, 1.0, n=4,
              bw=max(5, int(d * 0.08)), gap=max(3, int(d * 0.06)))
        out["a_turn"] = front
        lab = self._label()
        st = self.ex_style
        if st in ("flip", "drawer"):  # a card of its own (taller when the sentence needs it)
            sl = self._sentence(w, e["text"], cw - 110, max_h=self.BOT - self.TOP - 160)
            hb = max(ch, 26 + (lab.height - 60) + 26 + sl["h"] + 34)
            out["back"] = _shadow_card(cw, hb, 32, c["back"], c["shadow"], 0.34, 22, 12)
            out["back"].alpha_composite(lab, (PAD + 36 - 30, PAD + 26 - 30))
            out["sent"], out["back_h"], out["back_lab"] = sl, hb, 26 + (lab.height - 60) / 2
            free = hb - (26 + (lab.height - 60) + 26) - 34
            out["sent_xy"] = (PAD + 55, PAD + 26 + (lab.height - 60) + 26 + (free - sl["h"]) // 2)
        elif st in ("expand", "zoom"):  # the card itself grows: the word on top, the sentence under a line
            n = len(self.pg.words)
            room = self.BOT - self.TOP - ch - (n - 1) * (0.5 * ch + self.GAP) - 110 if st == "expand" else 700
            sl = self._sentence(w, e["text"], cw - 110, max_h=max(90, room))
            extra = 8 + (lab.height - 60) + 14 + sl["h"] + 34
            full = _shadow_card(cw, ch + extra, 32, c["card_a"], c["shadow"], 0.34, 22, 12)
            if c["ring"]:
                ImageDraw.Draw(full).rounded_rectangle([PAD, PAD, PAD + cw - 1, PAD + ch + extra - 1], 32,
                                                       outline=tuple(c["ring"]) + (255,), width=8)
            full.alpha_composite(front.crop((PAD + 10, PAD + 10, PAD + cw - 10, PAD + ch - 6)), (PAD + 10, PAD + 10))
            ImageDraw.Draw(full).line([(PAD + 36, PAD + ch), (PAD + cw - 36, PAD + ch)],
                                      fill=tuple(c["label"]) + (110,), width=2)
            full.alpha_composite(lab, (PAD + 36 - 30, PAD + ch + 8 - 30))
            out["exp"], out["exp_h"], out["sent"] = full, ch + extra, sl
            out["sent_xy"] = (PAD + 55, PAD + ch + 8 + (lab.height - 60) + 14)
            out["exp_lab"] = ch + 8 + (lab.height - 60) / 2
        else:  # sheet / bubble: a panel of its own
            P = self.kit.panel(w["en"], e["text"], 980 if st == "sheet" else 900, handle=st == "sheet")
            out["panel"], out["panel_h"], out["panel_w"], out["sent"] = P["panel"], P["h"], P["w"], P["sent"]
            out["sent_xy"], out["panel_bars"] = P["sent_xy"], P["bars"]

    def _open(self, j, u):
        return open_amount(self.pg, j, u)

    def _flip(self, j, u):
        """(angle 0-360 of the card turning over, how far the sentence is shown 0-1) or (None, 0)."""
        e = self.pg.examples[j] if j < len(self.pg.examples) else None
        if not e or u < e["f0"] or u >= e["f1"] + e["flip"]:
            return None, 0.0
        fl = e["flip"]
        if u < e["f0"] + fl:
            p = prog(u, e["f0"], e["f0"] + fl)
            return 180 * ease_io(p), p
        if u < e["f1"]:
            return 180.0, 1.0
        p = prog(u, e["f1"], e["f1"] + fl)
        return 180 + 180 * ease_io(p), 1 - p

    _turn = staticmethod(turn)
    _reveal = staticmethod(reveal)

    def _with_sentence(self, base, c, e, u):
        """base (a card / panel picture) with the sentence as it looks at time u."""
        img = base.copy()
        img.alpha_composite(self._sent_now(c["sent"], e, u), tuple(int(v) for v in c["sent_xy"]))
        return img

    def _sent_bars(self, fr, x, y, e, u, a, s=1.0):
        _bars(fr, x, y, 26 * s, self.c["bars_b"], u, e["speak"], a, n=4, bw=5, gap=4)

    def draw(self, fr, u):
        pg, st, n = self.pg, self.ex_style, len(self.cards)
        fr.paste(_bright_bg(*self.c["bg"]), (0, 0))
        hp = prog(u, 0.05, 0.45)
        paste(fr, self.kick, W / 2, 150, 1, hp)
        _top(fr, self.title, W / 2, 192 + 20 * (1 - ease_io(hp)), hp)
        if self.sub is not None:
            paste(fr, self.sub, W / 2, 340, 1, prog(u, 0.15, 0.55))
        opens = [self._open(j, u) for j in range(n)]
        cur = max(range(n), key=lambda j: opens[j][0]) if n else 0
        o, e = opens[cur] if n else (0.0, None)
        ys, scales = list(self.ys), [1.0] * n
        if e is not None and st in ("expand", "sheet"):
            # expand: the open card grows and the others step back (smaller) to make room; sheet: the whole list
            # makes room above the sheet (the word being read keeps its size)
            c = self.cards[cur]
            bot = self.BOT if st == "expand" else self.BOT + (self.SHEET_BOT - c["panel_h"] - 24 - self.BOT) * o
            hs = [self.ch] * n
            if st == "expand":
                hs[cur] = self.ch + (c["exp_h"] - self.ch) * o
            free = bot - self.TOP - hs[cur] - self.GAP * (n - 1)
            s_min = max(0.3, min(1.0, free / max(1, (n - 1) * self.ch))) if n > 1 else 1.0
            for k in range(n):
                if k != cur:
                    scales[k] = 1 - (1 - s_min) * (o if st == "expand" else 1.0)
                    hs[k] = self.ch * scales[k]
            total = sum(hs) + self.GAP * (n - 1)
            y = (self.TOP + bot) / 2 - total / 2
            for k in range(n):
                ys[k] = y + hs[k] / 2
                y += hs[k] + self.GAP
        dim = {"sheet": 0.6, "zoom": 0.65}.get(st, 0.45) * o if e is not None else 0.0
        later = []
        for j, c in enumerate(self.cards):
            a, dy = pg._row_in(j, u)
            if a <= 0.01:
                continue
            y, s0 = ys[j] + dy, scales[j]
            if j == cur and e is not None and st in ("flip", "drawer", "zoom", "expand"):
                later.append((j, c, y, a))  # drawn by its style (over the other cards)
                continue
            keep = j == cur and e is not None and st in ("sheet", "bubble")  # the word stays lit next to its sentence
            if dim and not keep:
                a *= 1 - dim
            hl, done = _row_state(pg, j, u)
            hid = pg.hider is not None and pg.hider.hidden(j, u)
            base = c["d"] if u >= pg.starts[j] and done > 0 else c["n"]
            if hid:
                base = with_meaning(c["n_h"], pg.hider.render(j, "n", u), c["ar_off"])
            paste(fr, base, W / 2, y, s0, a)
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                s = s0 * (1 + 0.035 * ease_out_back(c_in))
                act = with_meaning(c["a_h"], pg.hider.render(j, "a", u), c["ar_off"]) if hid else c["a"]
                paste(fr, act, W / 2, y, s, a * hl)
                bx = W / 2 + (60 + 30 + self.d / 2 - W / 2) * s
                _bars(fr, bx, y, self.d * 0.45 * s, self.c["bars"], u, pg.speak[j], a * hl, n=4,
                      bw=max(5, int(self.d * 0.08)), gap=max(3, int(self.d * 0.06)))
        for j, c, y, a in later:
            getattr(self, "_draw_" + st)(fr, j, c, y, a, o, e, u)
        if e is not None and st in ("sheet", "bubble"):
            getattr(self, "_draw_" + st)(fr, cur, self.cards[cur], ys[cur], 1.0, o, e, u)

    # ------------------------------------------------------------ the six ways to show a sentence
    def _draw_flip(self, fr, j, c, y, a, o, e, u):
        ang, _ = self._flip(j, u)
        back = 90 < ang < 270
        lift = 1.035 + 0.035 * abs(math.sin(math.radians(ang)))
        if back:  # a taller back stays inside the screen
            half = c["back_h"] / 2 * lift
            y = min(max(y, self.TOP + half), self.BOT - half)
        face = self._with_sentence(c["back"], c, e, u) if back else c["a_turn"]
        paste(fr, self._turn(face, ang), W / 2, y, lift, a)
        if ang == 180.0:
            self._sent_bars(fr, W / 2 + (self.CW / 2 - 64) * lift, y + (c["back_lab"] - c["back_h"] / 2) * lift, e, u,
                            a, lift)

    def _draw_drawer(self, fr, j, c, y, a, o, e, u):
        half = c["back_h"] / 2 * 1.035
        yb = min(max(y, self.TOP + half), self.BOT - half)
        paste(fr, self._with_sentence(c["back"], c, e, u), W / 2, yb, 1.035, a * min(1.0, o * 1.6))
        if o >= 0.999:
            self._sent_bars(fr, W / 2 + (self.CW / 2 - 64) * 1.035, yb + (c["back_lab"] - c["back_h"] / 2) * 1.035,
                            e, u, a, 1.035)
        if o < 0.999:  # the front slides away to the right like a drawer, and back again
            paste(fr, c["a_turn"], W / 2 + 1100 * o, y, 1.035 - 0.05 * o, a * (1 - 0.3 * o))

    def _draw_expand(self, fr, j, c, y, a, o, e, u):
        h = self.ch + (c["exp_h"] - self.ch) * o
        img = self._reveal(self._with_sentence(c["exp"], c, e, u) if o > 0.02 else c["exp"], c["exp_h"], h)
        paste(fr, img, W / 2, y, 1.02, a)
        if o >= 0.999:
            self._sent_bars(fr, W / 2 + (self.CW / 2 - 64) * 1.02, y + (c["exp_lab"] - h / 2) * 1.02, e, u, a, 1.02)

    def _draw_zoom(self, fr, j, c, y, a, o, e, u):
        h = self.ch + (c["exp_h"] - self.ch) * o
        yc = (self.TOP + self.BOT) / 2 + 40
        yy = y + (yc - y) * o
        s = 1.02 + 0.05 * o
        img = self._reveal(self._with_sentence(c["exp"], c, e, u) if o > 0.02 else c["exp"], c["exp_h"], h)
        paste(fr, img, W / 2, yy, s, a)
        if o >= 0.999:
            self._sent_bars(fr, W / 2 + (self.CW / 2 - 64) * s, yy + (c["exp_lab"] - h / 2) * s, e, u, a, s)

    def _draw_sheet(self, fr, j, c, y, a, o, e, u):
        ph = c["panel_h"]
        rest = self.SHEET_BOT - ph / 2
        yy = rest + (H + ph / 2 - rest) * (1 - o)
        img = self._with_sentence(c["panel"], c, e, u) if o > 0.02 else c["panel"]
        paste(fr, img, W / 2, yy, 1.0, a)
        if o >= 0.999:
            bx, by = c["panel_bars"]
            self._sent_bars(fr, W / 2 - c["panel_w"] / 2 + bx, yy - ph / 2 + by, e, u, a)

    def _draw_bubble(self, fr, j, c, y, a, o, e, u):
        ph, pw = c["panel_h"], c["panel_w"]
        below = y < (self.TOP + self.BOT) / 2  # the bubble opens on the side with more room
        tail_x = W / 2 - self.CW / 2 + 150
        edge = y + (self.ch / 2 + 14) * (1 if below else -1)  # the tail's tip touches the card
        cy = edge + (28 + ph / 2) * (1 if below else -1)
        cy = min(max(cy, self.TOP - 20 + ph / 2), 1720 - ph / 2)
        k = 0.55 + 0.45 * ease_out_back(o) if o < 1 else 1.0
        img = self._with_sentence(c["panel"], c, e, u) if o > 0.02 else c["panel"]
        tail = Image.new("RGBA", (120, 64), (0, 0, 0, 0))  # drawn at twice the size: a smooth edge
        pts = [(12, 64), (108, 64), (34, 0)] if below else [(12, 0), (108, 0), (34, 64)]
        ImageDraw.Draw(tail).polygon(pts, fill=tuple(self.c["back"]) + (255,))
        tail = tail.resize((60, 32), Image.LANCZOS)
        # grow out of the tail: the bubble's centre moves from the tail's tip to its place
        bx = tail_x + (W / 2 - tail_x) * k
        by = edge + (cy - edge) * k
        paste(fr, tail, tail_x + 18, edge + 16 * (1 if below else -1), k, a * min(1.0, o * 2))
        paste(fr, img, bx, by, k, a * min(1.0, o * 2))
        if o >= 0.999:
            px, py = c["panel_bars"]
            self._sent_bars(fr, W / 2 - pw / 2 + px, by - ph / 2 + py, e, u, a)

# ================================================================ Table / Stepper (two-tone looks)
class _Toned:
    """Shared by Table and Stepper: the colour set (dark, accent, second accent), the background and the heading."""
    TOP, BOT = 430, 1660

    def _setup(self, pg, opts, title, subtitle, kicker, design):
        self.pg, self.n = pg, len(pg.words)
        key = _pal_key(opts.get("palette"), design)
        self.dk, self.x, self.y = tones(key) or tones(DEFAULT_PALETTE)
        dk = self.dk
        self.bg = (_mix(dk, WHITE, 0.07), _mix(dk, BLACK, 0.28))
        self.mute = _mix(dk, WHITE, 0.62)
        self.kick = _t(POPPINS_B, (kicker or "Vocabulary").upper(), 28, self.y, "Bold", 800)
        self.title = _t(POPPINS_B, title, 80, WHITE, "Bold", 960)
        self.sub = _t(PLEX_B, subtitle, 50, self.y, "Bold", 940) if subtitle else None
        theme, scrim = kit_theme(key, design)
        self.sentence_look = (theme, scrim, POPPINS_B, "SemiBold", "Bold", 34, 0.5)

    def _head(self, fr, u):
        fr.paste(_bright_bg(*self.bg), (0, 0))
        hp = prog(u, 0.05, 0.45)
        paste(fr, self.kick, W / 2, 150, 1, hp)
        _top(fr, self.title, W / 2, 192 + 20 * (1 - ease_io(hp)), hp)
        if self.sub is not None:
            paste(fr, self.sub, W / 2, 340, 1, prog(u, 0.15, 0.55))

    def _state(self, j, u):
        a, dy = self.pg._row_in(j, u)
        hl, done = _row_state(self.pg, j, u)
        return a, dy, hl, u >= self.pg.starts[j] and done > 0

    def _meaning(self, j, key, img, u):
        """The meaning to draw now: the hider's picture while it is hidden, else the meaning itself."""
        h = self.pg.hider
        return h.render(j, key, u) if h is not None and h.hidden(j, u) else img


class Table(_Toned):
    """A clean two-column table (ENGLISH | العربية) in a rounded panel: numbers in their own column, soft zebra rows;
    the row being read becomes an accent band (wiping in), read rows get a tick."""
    HH = 92  # header strip

    def __init__(self, pg, opts, title, subtitle, kicker):
        self._setup(pg, opts, title, subtitle, kicker, "Table")
        dk, x, n = self.dk, self.x, self.n
        self.rh = min(205, (self.BOT - self.TOP - self.HH) / n)
        pw, ph = 980, int(self.HH + n * self.rh)
        self.cy = (self.TOP + self.BOT) / 2
        self.y0 = self.cy - ph / 2
        self.row_ys = [self.y0 + self.HH + (j + 0.5) * self.rh for j in range(n)]
        body = _mix(dk, WHITE, 0.09)
        self.panel = _shadow_card(pw, ph, 30, body, _mix(dk, BLACK, 0.7), 0.4)
        d = ImageDraw.Draw(self.panel)
        m = _round_mask(pw, self.HH + 60, 30).crop((0, 0, pw, self.HH))
        self.panel.paste(Image.new("RGBA", (pw, self.HH), x + (255,)), (PAD, PAD), m)
        e = _t(POPPINS_B, "  ".join("ENGLISH"), 26, dk, "Bold")
        ar_h = _t(PLEX_B, "العربية", 36, dk, "Bold")
        self.panel.alpha_composite(e, (PAD + 130 - 30, PAD + self.HH // 2 - e.height // 2))
        self.panel.alpha_composite(ar_h, (PAD + pw - 44 + 30 - ar_h.width, PAD + self.HH // 2 - ar_h.height // 2))
        line = _mix(dk, WHITE, 0.2) + (255,)
        for j in range(n):
            yy = PAD + self.HH + j * self.rh
            if j % 2 and j < n - 1:
                d.rectangle([PAD, yy, PAD + pw - 1, yy + self.rh], fill=_mix(dk, WHITE, 0.13) + (255,))
            if j:
                d.line([(PAD + 30, yy), (PAD + pw - 30, yy)], fill=line, width=2)
        d.line([(PAD + 104, PAD + self.HH), (PAD + 104, PAD + ph - 20)], fill=line, width=2)
        k0 = min(1.1, self.rh / 190)

        def make(k, w, ce=WHITE, ci=None, ca=None):
            return (_t(POPPINS_B, w["en"], 56 * k0 * k, ce, "Bold"),
                    _ipa(w["ipa"], 30 * k0 * k, ci or self.mute) if w["ipa"] else None,
                    _t(PLEX_B, w["ar"], 54 * k0 * k, ca or x, "Bold"))
        # one size for the page, the meaning on its own line under the word (right aligned like Arabic)
        kc = _stack_k([lambda k, w=w: make(k, w) for w in pg.words], 986 - 170, self.rh * 0.8)
        self.rows = []
        for j, w in enumerate(pg.words):
            r = {"num": _t(POPPINS_B, f"{j + 1:02d}", 34 * k0, self.mute, "Bold")}
            for s, (ce, ci, ca) in (("n", (WHITE, self.mute, x)), ("a", (dk, _mix(dk, x, 0.4), dk))):
                r["en" + s], r["ipa" + s], r["ar" + s] = make(kc, w, ce, ci, ca)
                if pg.hider:
                    pg.hider.add(j, s, r["ar" + s], body if s == "n" else x, ca, PLEX_B, int(54 * k0 * kc), "Bold")
            r["pos"] = _place(r["enn"], r["ipan"], r["arn"], True, 170, 986, 0, k0 * kc)
            self.rows.append(r)
        self.tick = _tick_img(44, x, 6)
        self.band = Image.new("RGBA", (pw - 20, int(self.rh - 14)), (0, 0, 0, 0))
        self.band.paste(Image.new("RGBA", self.band.size, x + (255,)), (0, 0), _round_mask(*self.band.size, 18))

    def draw(self, fr, u):
        self._head(fr, u)
        pg = self.pg
        paste(fr, self.panel, W / 2, self.cy, 1, prog(u, 0.2, 0.6))
        for j, r in enumerate(self.rows):
            a, dy, hl, read = self._state(j, u)
            if a <= 0.01:
                continue
            cy = self.row_ys[j] + dy
            if hl > 0.005:  # the band wipes in from the left
                c_in, _ = pg._lit(j, u)
                bw = max(1, int(self.band.width * ease_io(min(1.0, c_in * 1.3))))
                paste(fr, self.band.crop((0, 0, bw, self.band.height)), W / 2 - self.band.width / 2, cy, 1,
                      a * hl, "l")
            s = "a" if hl > 0.5 else "n"
            if read and hl < 0.5:
                paste(fr, self.tick, 102, cy, 1, a)
            elif not (hl > 0.5):
                paste(fr, r["num"], 102, cy, 1, a)
            _draw_row(fr, r["en" + s], r["ipa" + s], self._meaning(j, s, r["ar" + s], u), r["pos"], cy, a)
            if hl > 0.5:  # the sound bars in the number column
                _bars(fr, 102, cy, 34, self.dk, u, pg.speak[j], a * hl)


def _draw_row(fr, en, ipa, ar, pos, cy, a):
    """A row's texts at the places _place() gave (relative to the row centre cy)."""
    for key, im in (("en", en), ("ipa", ipa)):
        if im is not None:
            x, y = pos[key]
            paste(fr, im, x - 30, cy + y - 30 + im.height / 2, 1, a, "l")
    x, y = pos["ar"]
    paste(fr, ar, x + 30, cy + y, 1, a, "r")


def _ring(d, col, w):
    s = 3
    big = Image.new("L", (int(d) * s, int(d) * s), 0)
    ImageDraw.Draw(big).ellipse([w * s / 2, w * s / 2, d * s - w * s / 2, d * s - w * s / 2], outline=255,
                                width=int(w * s))
    return _colored(big.resize((int(d), int(d)), Image.LANCZOS), col)


class Stepper(_Toned):
    """A progress line with a step dot per word (like an app's set-up steps): the line fills as the words are read,
    the current step glows with a soft card behind it, finished steps get a tick."""
    LX = 120

    def __init__(self, pg, opts, title, subtitle, kicker):
        self._setup(pg, opts, title, subtitle, kicker, "Stepper")
        dk, x, n = self.dk, self.x, self.n
        self.p = min(235, (self.BOT - self.TOP) / n)
        y0 = (self.TOP + self.BOT) / 2 - self.p * n / 2
        self.row_ys = [y0 + self.p * (j + 0.5) for j in range(n)]
        k = min(1.1, self.p / 210)
        d = int(66 * k)

        def make(kk, w):
            return (_t(POPPINS_B, w["en"], 58 * k * kk, WHITE, "Bold"),
                    _ipa(w["ipa"], 30 * k * kk, self.mute) if w["ipa"] else None,
                    _t(PLEX_B, w["ar"], 56 * k * kk, x, "Bold"))
        # one size for the page, the meaning on its own line under the word (right aligned like Arabic)
        kc = _stack_k([lambda kk, w=w: make(kk, w) for w in pg.words], 1000 - 210, self.p * 0.8)
        self.rows = []
        for j, w in enumerate(pg.words):
            en, ipa, ar = make(kc, w)
            r = {"en": en, "ipa": ipa, "ar": ar, "pos": _place(en, ipa, ar, True, 210, 1000, 0, k * kc)}
            if pg.hider:
                pg.hider.add(j, "n", r["ar"], _mix(dk, WHITE, 0.11), x, PLEX_B, int(56 * k * kc), "Bold")
            for s in "nad":
                im = Image.new("RGBA", (d + 40, d + 40), (0, 0, 0, 0))
                if s == "n":
                    im.alpha_composite(_ring(d, _mix(dk, WHITE, 0.35), 4), (20, 20))
                    im.alpha_composite(_colored(_circle_mask(d - 8), _mix(dk, WHITE, 0.06)), (24, 24))
                    nm = _t(POPPINS_B, str(j + 1), d * 0.42, self.mute, "Bold")
                else:
                    if s == "a":
                        im.alpha_composite(_colored(_circle_mask(d + 36), x, 0.25), (2, 2))
                    im.alpha_composite(_colored(_circle_mask(d), x), (20, 20))
                    nm = None
                    if s == "d":
                        tk = _tick_img(d * 0.6, dk, max(5, d * 0.1))
                        im.alpha_composite(tk, (20 + d // 2 - tk.width // 2, 20 + d // 2 - tk.height // 2))
                if nm is not None:
                    im.alpha_composite(nm, (20 + d // 2 - nm.width // 2, 20 + d // 2 - nm.height // 2))
                r[s] = im
            self.rows.append(r)
        self.d = d
        cw, ch = 1030 - 175, int(self.p - 22)
        self.card = _shadow_card(cw, ch, 26, _mix(dk, WHITE, 0.11), _mix(dk, BLACK, 0.7), 0.3)

    def draw(self, fr, u):
        self._head(fr, u)
        pg, ys = self.pg, self.row_ys
        dr = ImageDraw.Draw(fr)
        dr.line([(self.LX, ys[0]), (self.LX, ys[-1])], fill=_mix(self.dk, WHITE, 0.25), width=6)
        reach = ys[0]
        for j in range(self.n):  # the line fills down to the step being read
            if u >= pg.starts[j] - 0.12:
                c_in, _ = pg._lit(j, u)
                reach = ys[j - 1] + (ys[j] - ys[j - 1]) * ease_io(c_in) if j else ys[0]
        dr.line([(self.LX, ys[0]), (self.LX, reach)], fill=self.x, width=6)
        for j, r in enumerate(self.rows):
            a, dy, hl, read = self._state(j, u)
            if a <= 0.01:
                continue
            cy = ys[j] + dy
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                paste(fr, self.card, 175 + (1030 - 175) / 2, cy, 0.97 + 0.03 * ease_out_back(c_in), a * hl)
            paste(fr, r["d" if read else "n"], self.LX, cy, 1, a)
            if hl > 0.005:
                paste(fr, r["a"], self.LX, cy, 1, a * hl)
                if hl > 0.5:
                    _bars(fr, self.LX, cy, self.d * 0.42, self.dk, u, pg.speak[j], a * hl)
            _draw_row(fr, r["en"], r["ipa"], self._meaning(j, "n", r["ar"], u), r["pos"], cy, a)


DESIGNS = {"Bright": Bright, "Glass": Glass, "Pop": Pop, "Spotlight": Spotlight, "Table": Table, "Stepper": Stepper}


# ================================================================ font sets
def _same(src, to, w=None):
    """Every font in src replaced by `to` (weight w, or the design's own weight when None)."""
    return {f: (to, w) for f in src}


# Each design: 10 sets of (name, {design font: (new font, weight or None)}); set 1 = the design's own fonts,
# sets 6-10 = fonts of well-known apps (Inter, Roboto, Open Sans, Nunito, Lexend, DM Sans … + Noto / Vazirmatn / Cairo).
# English parts only ever map to fonts with Latin letters, Arabic parts to fonts with Arabic letters.
FONT_SETS = {
    "Bright": [  # English: POPPINS_B · Arabic: PLEX_B
        ("Poppins + IBM Plex Arabic", {}),
        ("Montserrat + Tajawal", {POPPINS_B: (MONTSERRAT, "ExtraBold"), PLEX_B: (TAJAWAL, "Bold")}),
        ("Alexandria (one family)", {POPPINS_B: (ALEXANDRIA, "SemiBold"), PLEX_B: (ALEXANDRIA, "SemiBold")}),
        ("Fredoka + Baloo (rounded)", {POPPINS_B: (FREDOKA, "SemiBold"), PLEX_B: (BALOO, "Bold")}),
        ("Oswald + Changa (condensed)", {POPPINS_B: (OSWALD, "SemiBold"), PLEX_B: (CHANGA, "SemiBold")}),
        # sets 6-10: the fonts of well-known apps
        ("Inter + Noto Sans Arabic (Figma · GitHub)", {POPPINS_B: (INTER, "Bold"), PLEX_B: (NOTO_AR, "Bold")}),
        ("Roboto + Cairo (Android · YouTube)", {POPPINS_B: (ROBOTO, "Bold"), PLEX_B: (CAIRO, "Bold")}),
        ("Nunito + Vazirmatn (friendly learning apps)", {POPPINS_B: (NUNITO, "ExtraBold"), PLEX_B: (VAZIR, "Bold")}),
        ("Lexend + Almarai (made for reading)", {POPPINS_B: (LEXEND, "SemiBold"), PLEX_B: (ALMARAI, "Bold")}),
        ("DM Sans + Noto Naskh Arabic (Google · classic naskh)", {POPPINS_B: (DMSANS, "Bold"),
                                                                  PLEX_B: (NASKH, "Bold")}),
    ],
    "Glass": [  # title POPPINS_K · words POPPINS_B · lesson line MONTSERRAT · Arabic TAJAWAL / TAJAWAL_K
        ("Poppins + Tajawal", {}),
        ("Montserrat + Almarai", {POPPINS_K: (MONTSERRAT, "Black"), POPPINS_B: (MONTSERRAT, "Bold"),
                                  TAJAWAL: (ALMARAI, "Bold"), TAJAWAL_K: (ALMARAI, "Black")}),
        ("Readex Pro (one family)", {POPPINS_K: (READEX, "Bold"), POPPINS_B: (READEX, "SemiBold"),
                                     MONTSERRAT: (READEX, "SemiBold"), TAJAWAL: (READEX, "SemiBold"),
                                     TAJAWAL_K: (READEX, "Bold")}),
        ("Playfair + El Messiri (elegant)", {POPPINS_K: (PLAYFAIR, "Black"), POPPINS_B: (PLAYFAIR, "Bold"),
                                             TAJAWAL: (MESSIRI, "SemiBold"), TAJAWAL_K: (MESSIRI, "Bold")}),
        ("Fredoka + Baloo (rounded)", {POPPINS_K: (FREDOKA, "Bold"), POPPINS_B: (FREDOKA, "SemiBold"),
                                       TAJAWAL: (BALOO, "SemiBold"), TAJAWAL_K: (BALOO, "Bold")}),
        ("Inter + Noto Sans Arabic (Figma · GitHub)", {POPPINS_K: (INTER, "ExtraBold"), POPPINS_B: (INTER, "SemiBold"),
                                                       MONTSERRAT: (INTER, "SemiBold"), TAJAWAL: (NOTO_AR, "SemiBold"),
                                                       TAJAWAL_K: (NOTO_AR, "Bold")}),
        ("Plus Jakarta Sans + Vazirmatn (fintech apps)", {POPPINS_K: (JAKARTA, "ExtraBold"),
                                                          POPPINS_B: (JAKARTA, "Bold"), MONTSERRAT: (JAKARTA, "Bold"),
                                                          TAJAWAL: (VAZIR, "SemiBold"), TAJAWAL_K: (VAZIR, "Bold")}),
        ("Roboto + Cairo (Android · YouTube)", {POPPINS_K: (ROBOTO, "Black"), POPPINS_B: (ROBOTO, "Bold"),
                                                MONTSERRAT: (ROBOTO, "Medium"), TAJAWAL: (CAIRO, "SemiBold"),
                                                TAJAWAL_K: (CAIRO, "Bold")}),
        ("DM Sans + Almarai (Google)", {POPPINS_K: (DMSANS, "ExtraBold"), POPPINS_B: (DMSANS, "Bold"),
                                       MONTSERRAT: (DMSANS, "Bold"), TAJAWAL: (ALMARAI, "Bold"),
                                       TAJAWAL_K: (ALMARAI, "ExtraBold")}),
        ("Open Sans + Noto Naskh Arabic (Google · WordPress)", {POPPINS_K: (OPENSANS, "ExtraBold"),
                                                                POPPINS_B: (OPENSANS, "Bold"),
                                                                MONTSERRAT: (OPENSANS, "SemiBold"),
                                                                TAJAWAL: (NASKH, "SemiBold"),
                                                                TAJAWAL_K: (NASKH, "Bold")}),
    ],
    "Pop": [  # title + numbers ANTON · words POPPINS_K · lesson line MONTSERRAT · Arabic LALEZAR
        ("Anton + Poppins + Lalezar", {}),
        ("Bangers + Fredoka + Marhey (comic)", {ANTON: (BANGERS, None), POPPINS_K: (FREDOKA, "Bold"),
                                                LALEZAR: (MARHEY, "Bold")}),
        ("Bebas Neue + Montserrat + Changa (poster)", {ANTON: (BEBAS, None), POPPINS_K: (MONTSERRAT, "Black"),
                                                       LALEZAR: (CHANGA, "ExtraBold")}),
        ("Righteous + Lemonada (retro)", {ANTON: (RIGHTEOUS, None), POPPINS_K: (RIGHTEOUS, None),
                                          LALEZAR: (LEMONADA, "Bold")}),
        ("Oswald + Alexandria (heavy)", {ANTON: (OSWALD, "Bold"), POPPINS_K: (OSWALD, "Bold"),
                                         LALEZAR: (ALEXANDRIA, "Black")}),
        ("Rubik + Vazirmatn (bold app look)", {ANTON: (RUBIK, "Black"), POPPINS_K: (RUBIK, "Bold"),
                                               LALEZAR: (VAZIR, "Black")}),
        ("Inter + Noto Sans Arabic (Figma · GitHub)", {ANTON: (INTER, "Black"), POPPINS_K: (INTER, "ExtraBold"),
                                                       LALEZAR: (NOTO_AR, "Black")}),
        ("Nunito + Almarai (friendly learning apps)", {ANTON: (NUNITO, "Black"), POPPINS_K: (NUNITO, "Black"),
                                                       LALEZAR: (ALMARAI, "ExtraBold")}),
        ("Lexend + Cairo (made for reading)", {ANTON: (LEXEND, "Black"), POPPINS_K: (LEXEND, "Bold"),
                                               LALEZAR: (CAIRO, "Black")}),
        ("DM Sans + Tajawal (Google)", {ANTON: (DMSANS, "Black"), POPPINS_K: (DMSANS, "ExtraBold"),
                                        LALEZAR: (TAJAWAL, "Black")}),
    ],
    "Spotlight": [  # lesson line + title + words MONTSERRAT · Arabic READEX
        ("Montserrat + Readex Pro", {}),
        ("Poppins + Tajawal", {MONTSERRAT: (POPPINS_B, None), READEX: (TAJAWAL, "ExtraBold")}),
        ("Playfair + El Messiri (elegant)", {MONTSERRAT: (PLAYFAIR, None), READEX: (MESSIRI, "Bold")}),
        ("Oswald + Noto Kufi (condensed)", {MONTSERRAT: (OSWALD, None), READEX: (NOTO_KUFI, "Bold")}),
        ("Alexandria (one family)", {MONTSERRAT: (ALEXANDRIA, None), READEX: (ALEXANDRIA, "SemiBold")}),
        ("Inter + Noto Sans Arabic (Figma · GitHub)", {MONTSERRAT: (INTER, None), READEX: (NOTO_AR, "Bold")}),
        ("DM Sans + Vazirmatn (Google)", {MONTSERRAT: (DMSANS, None), READEX: (VAZIR, "Bold")}),
        ("Plus Jakarta Sans + Almarai (fintech apps)", {MONTSERRAT: (JAKARTA, None), READEX: (ALMARAI, "Bold")}),
        ("Roboto + Cairo (Android · YouTube)", {MONTSERRAT: (ROBOTO, None), READEX: (CAIRO, "Bold")}),
        ("Lexend + Noto Naskh Arabic (made for reading)", {MONTSERRAT: (LEXEND, None), READEX: (NASKH, "Bold")}),
    ],
    "Editorial": [  # English PLAYFAIR · Arabic MESSIRI
        ("Playfair + El Messiri", {}),
        ("Literata + Almarai (book)", {PLAYFAIR: (LITERATA, None), MESSIRI: (ALMARAI, "Bold")}),
        ("Montserrat + IBM Plex Arabic (modern)", {PLAYFAIR: (MONTSERRAT, None), MESSIRI: (PLEX_S, "SemiBold")}),
        ("Oswald + Changa (newsroom)", {PLAYFAIR: (OSWALD, None), MESSIRI: (CHANGA, "SemiBold")}),
        ("Poppins + Tajawal (clean)", {PLAYFAIR: (POPPINS_B, None), MESSIRI: (TAJAWAL, "Bold")}),
        ("Inter + Noto Naskh Arabic (modern magazine)", {PLAYFAIR: (INTER, None), MESSIRI: (NASKH, "Bold")}),
        ("Roboto + Noto Sans Arabic (news apps)", {PLAYFAIR: (ROBOTO, None), MESSIRI: (NOTO_AR, "SemiBold")}),
        ("Open Sans + Vazirmatn (Google · WordPress)", {PLAYFAIR: (OPENSANS, None), MESSIRI: (VAZIR, "SemiBold")}),
        ("Literata + Noto Naskh Arabic (Google Play Books)", {PLAYFAIR: (LITERATA, None),
                                                              MESSIRI: (NASKH, "SemiBold")}),
        ("DM Sans + Cairo (Google)", {PLAYFAIR: (DMSANS, None), MESSIRI: (CAIRO, "SemiBold")}),
    ],
    "Chalkboard": [  # English PATRICK · Arabic RUQAA
        ("Patrick Hand + Aref Ruqaa", {}),
        ("Patrick Hand + Marhey", {RUQAA: (MARHEY, "SemiBold")}),
        ("Fredoka + Baloo (rounded)", {PATRICK: (FREDOKA, "Medium"), RUQAA: (BALOO, "SemiBold")}),
        ("Lobster + Aref Ruqaa (script)", {PATRICK: (LOBSTER, None)}),
        ("Patrick Hand + Reem Kufi", {RUQAA: (REEM, "SemiBold")}),
        ("Nunito + Vazirmatn (rounded)", {PATRICK: (NUNITO, "SemiBold"), RUQAA: (VAZIR, "Medium")}),
        ("Lexend + Noto Sans Arabic (made for reading)", {PATRICK: (LEXEND, "Regular"), RUQAA: (NOTO_AR, "Medium")}),
        ("Rubik + Cairo (clean)", {PATRICK: (RUBIK, "Regular"), RUQAA: (CAIRO, "SemiBold")}),
        ("Patrick Hand + Noto Naskh Arabic (classic naskh)", {RUQAA: (NASKH, "Medium")}),
        ("Inter + Almarai (Figma · GitHub)", {PATRICK: (INTER, "Medium"), RUQAA: (ALMARAI, "Bold")}),
    ],
}


FONT_SETS["Table"] = FONT_SETS["Stepper"] = FONT_SETS["Bright"]  # the same design fonts as Bright


def font_set(style, k):
    """{design font: (font, weight)} of font set k (1-10) of a design; {} = its own fonts."""
    sets = FONT_SETS.get(style) or [("", {})]
    try:
        k = int(k or 1)
    except (TypeError, ValueError):
        k = 1
    return dict(sets[k - 1][1]) if 1 <= k <= len(sets) else {}


def font_choices(style):
    """The dropdown of a design's font sets: [(label, 1..5)]."""
    return [(f"{i}. {name}", i) for i, (name, _) in enumerate(FONT_SETS.get(style) or [], 1)]
