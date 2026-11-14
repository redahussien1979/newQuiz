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

`list_palette` colours all four: PALETTES (12 colour pairs) or DUOS (3 two-tone sets: deep base + bright accent;
Navy + juice is the default)."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

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
DUOS = {"navy_juice": ((37, 26, 102), (229, 245, 24)),
        "navy_orange": ((20, 33, 61), (252, 163, 17)),
        "slate_yellow": ((43, 50, 63), (253, 239, 75))}
DUO_CHOICES = [("Navy + juice", "navy_juice"), ("Navy + orange", "navy_orange"), ("Gray blue + yellow", "slate_yellow")]
DEFAULT_PALETTE = "navy_juice"
# the four favourites first (the two-tone sets and Sky blue), then the other colours
PALETTE_CHOICES = DUO_CHOICES + [("Sky blue", "sky")] + PALETTE_CHOICES


def _pal_key(pal):
    return pal if pal in PALETTES or pal in DUOS else DEFAULT_PALETTE


def _pair(pal):
    """(colour A, colour B) of a palette; a two-tone set gives its accent and a deeper shade of it."""
    if pal in DUOS:
        dk, x = DUOS[pal]
        return x, _mix(x, dk, 0.3)
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


def _share(make, avail, cut=0):
    """make(k) -> (english, ipa or None, arabic, ...) at k x the normal size -> (images, two_lines).
    One line: English (IPA under it) on the left, Arabic on the right, together at most `avail` px wide; when they
    do not fit, both are re-rendered smaller together (never stretched). When that would make them much smaller,
    the Arabic gets its own line under the English (two_lines, the IPA then follows the word) and both stay big;
    `cut` = px of the first line kept free in that case (e.g. under a corner sticker)."""
    def one(imgs):
        en, ipa, ar = imgs[:3]
        return max(_vis_w(en), _vis_w(ipa) if ipa is not None else 0) + _vis_w(ar)

    def two(imgs):
        en, ipa, ar = imgs[:3]
        return max(_vis_w(en) + (IPA_GAP + _vis_w(ipa) if ipa is not None else 0), _vis_w(ar))

    def fit(need, room):
        k = 1.0
        for _ in range(6):
            n = need(make(k))
            if n <= room:
                return k
            k *= max(0.6, room / n) * 0.99
        return k

    k1 = fit(one, avail)
    if k1 < 0.8:
        k2 = fit(two, avail + 50 - cut)
        if k2 > k1:
            return make(k2), True
    return make(k1), False


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
            dk, x = DUOS[pal]
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
        self.pal = _pal_key(opts.get("palette"))
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
        for j, w in enumerate(pg.words):
            cy = int(pg.cy[j])
            y0 = cy - ch // 2
            def make(k, w=w):
                return (_fit(_t(POPPINS_B, w["en"], 54 * sc * k, WHITE, "Bold"), 520),
                        _fit(_ipa(w["ipa"], 31 * sc * k, (225, 222, 240)), 520) if w["ipa"] else None,
                        _fit(_t(TAJAWAL_K, w["ar"], 56 * sc * k, WHITE, "Black"), 680), k)
            tx = 38 + self.bd + 26  # where the words start, right of the badge
            (en_n, ipa_n, ar_k, k), two = _share(make, self.CW - tx - 34 - 50)
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
            white = Image.new("RGBA", (self.CW, ch), (0, 0, 0, 0))
            white.paste(Image.new("RGBA", (self.CW, ch), (255, 255, 255, 250)), (0, 0), mask)
            white = self._content(white, en_a, ipa_a, ar_a, pos, ch, None)
            act = Image.new("RGBA", (self.CW + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0))
            glow = _gradient_fill(_padded_alpha(Image.merge("RGBA", [mask] * 4)), a, b).filter(
                ImageFilter.GaussianBlur(20))
            act.alpha_composite(_colored(glow.split()[3], _mix(a, b, 0.5), 0.75))
            act.alpha_composite(white, (PAD, PAD))
            self.rows.append(dict(norm=norm, done=done, act=act))
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
            base = r["done"] if started and done > 0 else r["norm"]
            paste(fr, base, W / 2, cy, 1, a)
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                s = 1 + 0.035 * ease_out_back(c_in)
                paste(fr, r["act"], W / 2, cy, s, a * hl)
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
        self.pal = _pal_key(opts.get("palette"))
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
        for j, w in enumerate(pg.words):
            (en, ipa, ar), two = _share(
                lambda k, w=w: (_fit(_t(POPPINS_K, w["en"], 56 * sc * k, BLACK, "Black"), 500),
                                _fit(_ipa(w["ipa"], 30 * sc * k, (70, 70, 80)), 500) if w["ipa"] else None,
                                _fit(_t(LALEZAR, w["ar"], 64 * sc * k, BLACK, "Regular"), 720)),
                self.CW - (18 + tab + 26) - 28 - 50, cut=110)
            pos = _place(en, ipa, ar, two, 18 + tab + 26, self.CW - 28, ch / 2, sc)
            num = _t(ANTON, str(j + 1), tab * 0.62, WHITE, "Regular")
            self.rows.append(dict(norm=self._card(WHITE, en, ipa, ar, pos, num, 10),
                                  done=self._card(WHITE, en, ipa, ar, pos, None, 10),
                                  act=self._card(YELLOW, en, ipa, ar, pos, num, 20)))

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
            cx = self.X0 + base.width / 2
            paste(fr, base, cx, cy + 6, 1, a)
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                k = ease_out_back(c_in)
                ang = -1.6 * k
                act = r["act"]
                if c_in >= 0.999:  # settled tilt: rotated once per row of this page
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
            dk, x = DUOS[pal]
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
        self.pal = _pal_key(opts.get("palette"))
        a, b = _pair(self.pal)
        self.ar_col = _mix(b, WHITE, 0.35)
        self.kick = _t(MONTSERRAT, "  ".join((kicker or "Vocabulary").upper()), 26, _mix(b, WHITE, 0.55), "Bold", 900)
        self.title = _t(MONTSERRAT, title, 88, WHITE, "Black", 960)
        self.sub = _t(READEX, subtitle, 52, (235, 232, 245), "Bold", 940) if subtitle else None
        self.blocks, self.en_w = [], []
        for w in pg.words:
            en = _fit(_t(MONTSERRAT, w["en"], 100, WHITE, "ExtraBold"), 900)
            ipa = _fit(_ipa(w["ipa"], 40, (225, 222, 238)), 900) if w["ipa"] else None
            ar = _fit(_t(READEX, w["ar"], 70, self.ar_col, "Bold"), 920)
            self.blocks.append(self._block(en, ipa, ar))
            self.en_w.append(_vis_w(en))
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
        for j, blk in enumerate(self.blocks):
            s = scales[j]
            h = self.bh * s
            cy = y + h / 2
            y += h + gap
            a, dy = pg._row_in(j, u)
            if a <= 0.01:
                continue
            f = focus[j]
            if f > 0.01:
                paste(fr, spot, W / 2, cy, 0.6 + 0.4 * s / self.k, a * f)
            alpha = 0.38 + 0.2 * state[j]
            alpha = alpha + (1 - alpha) * f
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
        dk, x = DUOS[pal]
        return dict(bg=(_mix(dk, WHITE, 0.07), _mix(dk, BLACK, 0.28)), card=_mix(dk, WHITE, 0.1), card_a=x, ring=None,
                    en=WHITE, ipa=_mix(dk, WHITE, 0.66), ar=x, en_a=dk, ipa_a=_mix(dk, x, 0.4), ar_a=dk,
                    disc=_mix(dk, WHITE, 0.24), num=WHITE, disc_a=dk, bars=x, disc_d=x, tick=dk,
                    title=WHITE, kick=x, sub=x, shadow=_mix(dk, BLACK, 0.7),
                    back=x, ex=dk, hl=dk, hl_txt=x, label=_mix(dk, x, 0.4), bars_b=dk)
    a, b = PALETTES[pal if pal in PALETTES else "sky"]
    ink, acc = (24, 26, 36), _on_white(a)
    return dict(bg=(a, b), card=WHITE, card_a=WHITE, ring=(255, 206, 60), en=ink, ipa=(110, 114, 130), ar=acc,
                en_a=ink, ipa_a=(110, 114, 130), ar_a=acc, disc=a, num=WHITE, disc_a=a, bars=WHITE,
                disc_d=(34, 170, 100), tick=WHITE, title=WHITE, kick=WHITE, sub=WHITE, shadow=_mix(a, BLACK, 0.6),
                back=WHITE, ex=ink, hl=acc, hl_txt=WHITE, label=(122, 126, 142), bars_b=acc)


class Bright:
    TOP, BOT, GAP, CW = 420, 1660, 22, 960   # the cards fill the screen between the title and the bottom

    def __init__(self, pg, opts, title, subtitle, kicker):
        self.pg = pg
        pal = opts.get("palette")
        self.c = c = _bright_scheme(_pal_key(pal))
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
        for j, w in enumerate(pg.words):
            def make(k, w=w, sfx=""):
                return (_fit(_t(POPPINS_B, w["en"], 62 * k0 * k, c["en" + sfx], "Bold"), 560),
                        _fit(_ipa(w["ipa"], 34 * k0 * k, c["ipa" + sfx]), 560) if w["ipa"] else None,
                        _fit(_t(PLEX_B, w["ar"], 64 * k0 * k, c["ar" + sfx], "Bold"), 760), k)
            (en, ipa, ar, k), two = _share(make, cw - tx - 34 - 50)
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
                if state == "a":
                    _put_row(im, en_a, ipa_a, ar_a, pos)
                else:
                    _put_row(im, en, ipa, ar, pos)
                out[state] = im
            ex = pg.examples[j] if j < len(pg.examples) else None
            if ex:
                out["back"], out["back_h"], out["back_lab"] = self._back(w, ex["text"], k0)
                front = out["a"].copy()  # the front while it turns: its badge keeps the sound bars
                _bars(front, PAD + 30 + d / 2, PAD + ch / 2, d * 0.45, c["bars"], 0.0, None, 1.0, n=4,
                      bw=max(5, int(d * 0.08)), gap=max(3, int(d * 0.06)))
                out["a_turn"] = front
            self.cards.append(out)

    # ------------------------------------------------------------ sample sentence on the back of a card
    def _back(self, w, text, k0):
        """The back of a card: EXAMPLE label + the sentence (wrapped, centred) with the word / expression on a pill.
        The word is found in the sentence by find_phrase (other forms too: battle -> battles, go -> went), or
        marked by hand with *stars*. The text keeps a comfortable size: the back grows taller than the card when the
        sentence needs it (it is drawn over the other cards, which step back). Returns (image, its card height)."""
        from .core import get_font
        c, cw, ch = self.c, self.CW, self.ch
        S = 2  # drawn at twice the size, then scaled down (smooth pill edges)
        toks = _ex_tokens(text, w["en"])
        f_path, f_w = resolve_font(POPPINS_B, "SemiBold")
        h_path, h_w = resolve_font(POPPINS_B, "Bold")
        lab_f, lab_w = resolve_font(POPPINS_B, "Bold")
        lf = get_font(int(22 * S), lab_w, lab_f)
        top, gap, bottom = 26 * S, 26 * S, 34 * S
        area_w = (cw - 110) * S
        max_h = (self.BOT - self.TOP - 40) * S
        size = 50 * S
        while True:  # the biggest size (50 px down to 34) at which the sentence takes at most 4 lines
            fn, fh = get_font(size, f_w, f_path), get_font(size, h_w, h_path)
            lines = _wrap(toks, fn, fh, area_w, size * 0.2)
            asc, desc = fn.getmetrics()
            lh = int((asc + desc) * 1.08)
            body = len(lines) * lh
            hb = top + lf.size + gap + body + bottom
            if (len(lines) <= 4 and hb <= max_h) or size <= 34 * S:
                break
            size -= 2 * S
        hb = max(ch * S, hb)
        im = _shadow_card(cw, hb // S, 32, c["back"], c["shadow"], 0.34, 22, 12)
        lay = Image.new("RGBA", (cw * S, hb), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        d.text((36 * S, top), "  ".join("EXAMPLE"), font=lf, fill=tuple(c["label"]) + (255,), anchor="lt")
        label_mid = top + lf.size * 0.55
        free = hb - (top + lf.size + gap) - bottom
        y = top + lf.size + gap + (free - body) / 2 + asc
        for line in lines:
            x, pieces = (cw * S - sum(p[2] for p in line)) / 2, []
            for txt, hl, wdt in line:
                pieces.append((x, txt, hl, wdt))
                x += wdt
            run = [p for p in pieces if p[2]]
            if run:  # one pill under the highlighted words of this line
                pad = size * 0.14
                d.rounded_rectangle([run[0][0] - pad, y - asc * 0.84, run[-1][0] + run[-1][3] + pad, y + desc * 0.58],
                                    size * 0.24, fill=tuple(c["hl"]) + (255,))
            for x0, txt, hl, wdt in pieces:
                if txt.strip():
                    d.text((x0, y), txt, font=fh if hl else fn, fill=tuple(c["hl_txt"] if hl else c["ex"]) + (255,),
                           anchor="ls")
            y += lh
        im.alpha_composite(lay.resize((cw, hb // S), Image.LANCZOS), (PAD, PAD))
        return im, hb // S, label_mid / S

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

    @staticmethod
    def _turn(img, ang):
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

    def draw(self, fr, u):
        pg = self.pg
        fr.paste(_bright_bg(*self.c["bg"]), (0, 0))
        hp = prog(u, 0.05, 0.45)
        paste(fr, self.kick, W / 2, 150, 1, hp)
        _top(fr, self.title, W / 2, 192 + 20 * (1 - ease_io(hp)), hp)
        if self.sub is not None:
            paste(fr, self.sub, W / 2, 340, 1, prog(u, 0.15, 0.55))
        flips = [self._flip(j, u) for j in range(len(self.cards))]
        focus = max(f[1] for f in flips) if flips else 0.0  # a sentence is shown: the other cards step back
        turning = []
        for j, c in enumerate(self.cards):
            a, dy = pg._row_in(j, u)
            if a <= 0.01:
                continue
            y = self.ys[j] + dy
            ang, shown = flips[j]
            if ang is not None:  # turning over / showing its sentence: drawn last, over the other cards
                turning.append((j, c, ang, y, a))
                continue
            if focus > 0.001:
                a *= 1 - 0.45 * focus
            hl, done = _row_state(pg, j, u)
            base = c["d"] if u >= pg.starts[j] and done > 0 else c["n"]
            paste(fr, base, W / 2, y, 1, a)
            if hl > 0.005:
                c_in, _ = pg._lit(j, u)
                s = 1 + 0.035 * ease_out_back(c_in)
                paste(fr, c["a"], W / 2, y, s, a * hl)
                bx = W / 2 + (60 + 30 + self.d / 2 - W / 2) * s
                _bars(fr, bx, y, self.d * 0.45 * s, self.c["bars"], u, pg.speak[j], a * hl, n=4,
                      bw=max(5, int(self.d * 0.08)), gap=max(3, int(self.d * 0.06)))
        for j, c, ang, y, a in turning:
            back = 90 < ang < 270
            lift = 1.035 + 0.035 * abs(math.sin(math.radians(ang)))
            if back:  # a taller back stays inside the screen
                half = c["back_h"] / 2 * lift
                y = min(max(y, self.TOP + half), self.BOT - half)
            paste(fr, self._turn(c["back"] if back else c["a_turn"], ang), W / 2, y, lift, a)
            if ang == 180.0:  # the sentence's sound bars, top right of the back
                bx = W / 2 + (self.CW / 2 - 64) * lift
                by = y + (c["back_lab"] - c["back_h"] / 2) * lift
                _bars(fr, bx, by, 26 * lift, self.c["bars_b"], u, pg.examples[j]["speak"], a, n=4, bw=5, gap=4)


DESIGNS = {"Bright": Bright, "Glass": Glass, "Pop": Pop, "Spotlight": Spotlight}


# ================================================================ font sets
def _same(src, to, w=None):
    """Every font in src replaced by `to` (weight w, or the design's own weight when None)."""
    return {f: (to, w) for f in src}


# Each design: 5 sets of (name, {design font: (new font, weight or None)}); set 1 = the design's own fonts.
# English parts only ever map to fonts with Latin letters, Arabic parts to fonts with Arabic letters.
FONT_SETS = {
    "Bright": [  # English: POPPINS_B · Arabic: PLEX_B
        ("Poppins + IBM Plex Arabic", {}),
        ("Montserrat + Tajawal", {POPPINS_B: (MONTSERRAT, "ExtraBold"), PLEX_B: (TAJAWAL, "Bold")}),
        ("Alexandria (one family)", {POPPINS_B: (ALEXANDRIA, "SemiBold"), PLEX_B: (ALEXANDRIA, "SemiBold")}),
        ("Fredoka + Baloo (rounded)", {POPPINS_B: (FREDOKA, "SemiBold"), PLEX_B: (BALOO, "Bold")}),
        ("Oswald + Changa (condensed)", {POPPINS_B: (OSWALD, "SemiBold"), PLEX_B: (CHANGA, "SemiBold")}),
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
    ],
    "Spotlight": [  # lesson line + title + words MONTSERRAT · Arabic READEX
        ("Montserrat + Readex Pro", {}),
        ("Poppins + Tajawal", {MONTSERRAT: (POPPINS_B, None), READEX: (TAJAWAL, "ExtraBold")}),
        ("Playfair + El Messiri (elegant)", {MONTSERRAT: (PLAYFAIR, None), READEX: (MESSIRI, "Bold")}),
        ("Oswald + Noto Kufi (condensed)", {MONTSERRAT: (OSWALD, None), READEX: (NOTO_KUFI, "Bold")}),
        ("Alexandria (one family)", {MONTSERRAT: (ALEXANDRIA, None), READEX: (ALEXANDRIA, "SemiBold")}),
    ],
    "Editorial": [  # English PLAYFAIR · Arabic MESSIRI
        ("Playfair + El Messiri", {}),
        ("Literata + Almarai (book)", {PLAYFAIR: (LITERATA, None), MESSIRI: (ALMARAI, "Bold")}),
        ("Montserrat + IBM Plex Arabic (modern)", {PLAYFAIR: (MONTSERRAT, None), MESSIRI: (PLEX_S, "SemiBold")}),
        ("Oswald + Changa (newsroom)", {PLAYFAIR: (OSWALD, None), MESSIRI: (CHANGA, "SemiBold")}),
        ("Poppins + Tajawal (clean)", {PLAYFAIR: (POPPINS_B, None), MESSIRI: (TAJAWAL, "Bold")}),
    ],
    "Chalkboard": [  # English PATRICK · Arabic RUQAA
        ("Patrick Hand + Aref Ruqaa", {}),
        ("Patrick Hand + Marhey", {RUQAA: (MARHEY, "SemiBold")}),
        ("Fredoka + Baloo (rounded)", {PATRICK: (FREDOKA, "Medium"), RUQAA: (BALOO, "SemiBold")}),
        ("Lobster + Aref Ruqaa (script)", {PATRICK: (LOBSTER, None)}),
        ("Patrick Hand + Reem Kufi", {RUQAA: (REEM, "SemiBold")}),
    ],
}


def font_set(style, k):
    """{design font: (font, weight)} of font set k (1-5) of a design; {} = its own fonts."""
    sets = FONT_SETS.get(style) or [("", {})]
    try:
        k = int(k or 1)
    except (TypeError, ValueError):
        k = 1
    return dict(sets[k - 1][1]) if 1 <= k <= len(sets) else {}


def font_choices(style):
    """The dropdown of a design's font sets: [(label, 1..5)]."""
    return [(f"{i}. {name}", i) for i, (name, _) in enumerate(FONT_SETS.get(style) or [], 1)]
