"""English Words — the word-list page (item type `list`): up to 6 English words with their Arabic meanings on one
page, read one after another (clips w1_1, w1_2 …); the word being read is highlighted.

Two designs (vocab setting `list_style`):
    Editorial   a magazine page (Playfair Display + El Messiri); `list_highlight` = how the row being read is marked:
                red / cream / outline / navy / gold / marker
    Chalkboard  hand-written chalk (Patrick Hand + Aref Ruqaa); `chalk_board` green / black / blue, `chalk_mark`
                circle / underline / box (drawn live around the word being read), `chalk_color` pink / yellow /
                orange / blue. Words already read get a chalk tick.

More designs (Bright = the default, Glass, Pop, Spotlight; colours `list_palette`) live in list_designs.py.
Each design has 5 font sets (list_designs.FONT_SETS, vocab `list_fonts` 1-5, 1 = its own fonts); the font picked in
🎨 Style & sound (`settings.font_file`, opts["font"]) is used instead of them for English, and for Arabic if it
writes Arabic (`user_fonts`). Both are applied in `_t`; the IPA keeps Noto Sans.

ListPage(...) pre-renders everything that does not move; draw(frame, u) depends only on the item time u (frames are
rendered on several processes)."""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import DEFAULT_FONT, H, ROOT, W, ease_io, is_rtl, paste, prog, text_img_in

_LIB = os.path.join(ROOT, "fonts", "library")


def _font(*parts):
    path = os.path.join(_LIB, *parts)
    return path if os.path.isfile(path) else DEFAULT_FONT


PLAYFAIR = _font("PlayfairDisplay", "PlayfairDisplay[wght].ttf")
MESSIRI = _font("ElMessiri", "ElMessiri[wght].ttf")
PATRICK = _font("PatrickHand", "PatrickHand-Regular.ttf")
RUQAA = _font("ArefRuqaa", "ArefRuqaa-Bold.ttf")
IPA_FONT = os.path.join(ROOT, "fonts", "NotoSans-Bold.ttf")

HIGHLIGHTS = [("Cream + red bar", "cream"), ("Deep red", "red"), ("Red outline", "outline"), ("Navy", "navy"),
              ("Gold", "gold"), ("Marker stroke", "marker")]
BOARDS = {"green": ((36, 62, 52), (42, 72, 60), (28, 50, 42), (120, 80, 44)),
          "black": ((30, 32, 34), (40, 42, 44), (22, 23, 25), (110, 74, 40)),
          "blue": ((28, 46, 70), (34, 56, 86), (20, 34, 54), (150, 150, 158))}
BOARD_CHOICES = [("Green", "green"), ("Black", "black"), ("Blue", "blue")]
MARKS = [("Circle", "circle"), ("Underline + arrow", "underline"), ("Box", "box")]
CHALK_COLORS = {"pink": (255, 160, 190), "yellow": (255, 220, 90), "orange": (255, 170, 90), "blue": (130, 210, 255)}
CHALK_COLOR_CHOICES = [("Pink", "pink"), ("Yellow", "yellow"), ("Orange", "orange"), ("Blue", "blue")]

ROWS_TOP, ROWS_BOTTOM = 452, 1500   # the rows sit under the page title, above the Shorts caption zone
INK, RED, NUM = (18, 18, 18), (150, 30, 30), (190, 60, 50)
PAPER = (247, 243, 236)
CHALK, CHALK_AR, TICK = (248, 248, 242), (255, 225, 110), (160, 240, 170)
# Editorial highlight: band colour (None = no band), English, Arabic, number, IPA colours of the row being read
_HL = {"cream": ((240, 222, 180), INK, RED, NUM, (110, 95, 80)),
       "red": ((170, 34, 34), (255, 250, 242), (255, 222, 170), (255, 250, 242), (255, 225, 210)),
       "outline": ((255, 252, 246), INK, RED, NUM, (110, 95, 80)),
       "navy": ((22, 40, 78), (255, 255, 255), (240, 200, 120), (240, 200, 120), (205, 215, 240)),
       "gold": ((214, 168, 72), INK, (110, 20, 20), (110, 20, 20), (80, 50, 20)),
       "marker": (None, INK, RED, NUM, (110, 95, 80))}

_bg_cache = {}


# ---------------------------------------------------------------- small helpers
_USER = {}  # the font picked in 🎨 Style & sound while a page is being built: {"en": path, "ar": path}
_SET = {}   # the design's font set (list_designs.FONT_SETS) while a page is being built: {design font: (font, weight)}


def user_fonts(value):
    """{"en": path, "ar": path} for the font picked in 🎨 Style & sound (a library family name or a font file):
    it replaces the design's English fonts, and its Arabic fonts only if it writes Arabic. {} = the design's own."""
    if not value:
        return {}
    path = str(value)
    if not os.path.isfile(path):
        try:
            from .fonts import resolve
            path = resolve(value)
        except Exception:
            return {}
    if not path or not os.path.isfile(path) or (path == DEFAULT_FONT and str(value) != DEFAULT_FONT):
        return {}
    from .core import _font_cmap
    cmap = _font_cmap(path)
    out = {}
    if cmap is None or ord("a") in cmap:
        out["en"] = path
    if cmap is None or 0x0644 in cmap:
        out["ar"] = path
    return out


def resolve_font(font, weight, rtl=False):
    """(font, weight) actually used for a design font while a page is built: the font picked in 🎨 Style & sound
    wins, else the chosen font set swaps the design's fonts."""
    user = _USER.get("ar" if rtl else "en")
    if user:
        return user, weight
    if font in _SET:
        f, w = _SET[font]
        return f, (w or weight)
    return font, weight


def _t(font, txt, size, col, weight="Bold", max_w=None):
    font, weight = resolve_font(font, weight, is_rtl(txt))
    return text_img_in(font, txt, max(12, int(size)), tuple(col), weight, shadow=False, max_w=max_w)


def _ipa(txt, size, col):
    from .templates.vocab import ipa_img
    return ipa_img(txt, max(12, int(size)), tuple(col))


def _speaker(col, w=72):
    from .templates.vocab import speaker_imgs
    return [im.resize((w, int(w * 0.75)), Image.LANCZOS) for im in speaker_imgs(tuple(col))]


def _rect(w, h, fill, outline=None, width=0):
    im = Image.new("RGBA", (max(1, int(w)), max(1, int(h))), tuple(fill) + (255,) if fill else (0, 0, 0, 0))
    if outline:
        ImageDraw.Draw(im).rectangle([0, 0, im.width - 1, im.height - 1], outline=tuple(outline) + (255,), width=width)
    return im


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


def _jitter(pts, rnd, j):
    return [(x + rnd.uniform(-j, j), y + rnd.uniform(-j, j)) for x, y in pts]


def _chalkify(im, seed):
    """Grainy chalk: the alpha is broken up by fixed noise (the same every frame)."""
    rng = np.random.default_rng(seed)
    a = np.asarray(im.split()[3], np.float32)
    noise = rng.uniform(0.62, 1.0, a.shape).astype(np.float32)
    noise[rng.uniform(0, 1, a.shape) < 0.07] = 0.15
    out = im.copy()
    out.putalpha(Image.fromarray(np.clip(a * noise, 0, 255).astype(np.uint8)))
    return out


def _gradient(stops):
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    arr = np.zeros((H, 1, 3), np.float32)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        m = ((y >= p0) & (y <= p1))[..., None]
        k = ((y - p0) / (p1 - p0))[..., None]
        arr = np.where(m, np.array(c0, np.float32) * (1 - k) + np.array(c1, np.float32) * k, arr)
    return np.repeat(arr, W, axis=1)


def _blob(arr, cx, cy, r, col, s):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = (np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / r ** 2) * 1.8) * s)[..., None]
    return arr * (1 - g) + np.array(col, np.float32) * g


def _mix(a, b, k):
    return tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b))


def _paper(col=PAPER):
    key = ("paper", tuple(col))
    if key not in _bg_cache:
        arr = _gradient([(0, col), (1, _mix(col, (120, 100, 70), 0.06))])
        _bg_cache[key] = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    return _bg_cache[key]


def _board(name):
    """A chalkboard: a name from BOARDS, or (top, mid, bottom, wood) colours (a colour set's dark tone)."""
    key = ("board", name if isinstance(name, str) else tuple(map(tuple, name)))
    if key not in _bg_cache:
        top, mid, bot, wood = BOARDS[name] if isinstance(name, str) else name
        arr = _gradient([(0, top), (0.5, mid), (1, bot)])
        arr = _blob(arr, 300, 500, 420, tuple(min(255, c + 30) for c in mid), 0.35)
        arr = _blob(arr, 800, 1300, 520, tuple(min(255, c + 22) for c in mid), 0.3)
        arr = arr + np.random.default_rng(2).normal(0, 5, (H, W, 1)).astype(np.float32)
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
        smudge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(smudge)
        r = random.Random(4)
        for _ in range(14):
            x, y = r.randint(0, W), r.randint(0, H)
            d.ellipse([x - 160, y - 40, x + 160, y + 40], fill=(255, 255, 255, 16))
        im.alpha_composite(smudge.filter(ImageFilter.GaussianBlur(30)))
        frame = Image.new("RGBA", (W, 50), tuple(wood) + (255,))
        im.alpha_composite(frame, (0, 0))
        im.alpha_composite(frame, (0, H - 50))
        _bg_cache[key] = im
    return _bg_cache[key]


# ---------------------------------------------------------------- the page
class ListPage:
    def __init__(self, style, opts, words, title, subtitle, kicker, rows, starts, ends, speak, D, exit_len,
                 examples=None):
        self.style = style
        # per word: None or dict(text, f0 flip over, e0..e1 the sentence, f1 flip back, flip = its length, speak)
        self.examples = list(examples or [None] * len(words))
        self.words = words
        self.n = len(words)
        self.rows, self.starts, self.ends, self.speak = rows, starts, ends, speak
        self.D, self.exit = D, exit_len
        self.pitch = min(240.0, (ROWS_BOTTOM - ROWS_TOP) / self.n)
        self.sc = min(1.12, self.pitch / 209)
        self.cy = [ROWS_TOP + self.pitch * (j + 0.5) for j in range(self.n)]
        from .list_designs import DESIGNS, HIDE_STYLES, MeaningHider, font_set
        self.impl = None
        hide = opts.get("hide")
        self.hider = MeaningHider(self, hide) if hide in [v for _, v in HIDE_STYLES] and hide != "none" else None
        _USER.clear()
        _USER.update(user_fonts(opts.get("font")))  # every text image is made here, in __init__ (not per frame)
        _SET.clear()
        _SET.update(font_set(style, opts.get("fonts")))
        try:
            if style in DESIGNS:
                self.impl = DESIGNS[style](self, opts, title, subtitle, kicker)
            elif style == "Chalkboard":
                self._build_chalk(opts, title, subtitle)
            else:
                self._build_editorial(opts, title, subtitle, kicker)
            self.overlay = None  # sample sentences for the designs that draw no card of their own for them
            look = getattr(self.impl if self.impl is not None else self, "sentence_look", None)
            if look and style != "Bright" and any(self.examples):
                from .list_designs import EX_STYLES, SentenceKit, SentenceOverlay
                theme, scrim, font, w_txt, w_hl, radius, scrim_k = look
                kit = SentenceKit(theme, bool(opts.get("karaoke")), font, w_txt, w_hl, radius)
                st = opts.get("ex_style") if opts.get("ex_style") in [v for _, v in EX_STYLES] else "flip"
                self.overlay = SentenceOverlay(self, st, kit, scrim, scrim_k)
        finally:
            _USER.clear()
            _SET.clear()

    # ------------------------------------------------------------ timing shared by both designs
    def _lit(self, j, u):
        """(coming in 0..1, going out 0..1) of the highlight on row j."""
        s = self.starts[j]
        nxt = self.starts[j + 1] if j + 1 < self.n else self.ends[j] + 0.9
        return ease_io(prog(u, s - 0.12, s + 0.2)), prog(u, nxt - 0.12, nxt + 0.12)

    def _row_in(self, j, u):
        p = prog(u, self.rows[j], self.rows[j] + 0.35)
        return p, 24 * (1 - ease_io(p))

    def _speaker_alpha(self, j, u):
        sp = self.speak[j]
        if sp and sp[0] <= u < sp[1] + 0.15:
            ph = (u - sp[0]) * 7
            return 0.35 + 0.65 * max(0.0, math.sin(ph)), 0.35 + 0.65 * max(0.0, math.sin(ph - 1.1))
        return 1.0, 1.0

    def draw(self, frame, u):
        a = prog(u, 0.0, 0.4) * (1 - prog(u, self.D - self.exit, self.D))
        if a <= 0.01:
            return
        page = frame if a >= 0.999 else frame.copy()
        if self.impl is not None:
            self.impl.draw(page, u)
        elif self.style == "Chalkboard":
            self._draw_chalk(page, u)
        else:
            self._draw_editorial(page, u)
        if self.overlay is not None:
            self.overlay.draw(page, u, getattr(self.impl, "row_ys", None))
        if page is not frame:
            frame.paste(Image.blend(frame, page, a))

    # ============================================================ Editorial
    def _build_editorial(self, opts, title, subtitle, kicker):
        from .list_designs import tones
        tn = tones(opts.get("palette"))
        if tn:  # a colour set: paper = its light tone, ink = its dark tone, the row being read = a dark band
            dk, lt, lt2 = tn
            INK = RED = dk  # noqa: N806 (the design's names for its colours)
            NUM = _mix(dk, lt, 0.25)  # noqa: N806
            self.paper = _mix(lt, (255, 255, 255), 0.55)
            self.sep_col, self.ipa_col = _mix(dk, self.paper, 0.72), _mix(dk, self.paper, 0.4)
            hl = "navy"
            band, en_a, ar_a, num_a, ipa_a = dk, (255, 255, 255), lt2, lt2, _mix(lt, dk, 0.25)
        else:
            INK, RED, NUM = globals()["INK"], globals()["RED"], globals()["NUM"]  # noqa: N806
            self.paper, self.sep_col, self.ipa_col = PAPER, (180, 170, 155), (120, 110, 100)
            hl = opts.get("highlight") if opts.get("highlight") in _HL else "cream"
            band, en_a, ar_a, num_a, ipa_a = _HL[hl]
        self.hl = hl
        sc = self.sc
        head = Image.new("RGBA", (W, 450), (0, 0, 0, 0))
        d = ImageDraw.Draw(head)
        d.rectangle([60, 140, 1020, 146], fill=INK + (255,))
        d.rectangle([60, 152, 1020, 154], fill=INK + (255,))
        kick = _t(PLAYFAIR, (kicker or "Vocabulary").upper(), 28, RED, "Bold", max_w=900)
        head.alpha_composite(kick, (W // 2 - kick.width // 2, 185 - kick.height // 2))
        tt = _t(PLAYFAIR, title, 100, INK, "Black", max_w=960)
        head.alpha_composite(tt, (W // 2 - tt.width // 2, 280 - tt.height // 2))
        if subtitle:
            st = _t(MESSIRI, subtitle, 52, RED, "Bold", max_w=960)
            head.alpha_composite(st, (W // 2 - st.width // 2, 380 - st.height // 2))
        d.rectangle([60, 428, 1020, 430], fill=INK + (255,))
        self.head = head
        self.sep = _rect(960, 2, self.sep_col)
        self.rule = _rect(960, 2, INK)
        self.spk = _speaker(INK if band is None or hl in ("cream", "outline", "gold") else (255, 250, 242))
        bh = int(self.pitch - 16)
        if band is None:
            self.band = None
        elif hl == "outline":
            self.band = _rect(960, bh, band, (170, 34, 34), 5)
        else:
            self.band = _rect(960, bh, band)
            if hl == "cream":
                self.band.paste((170, 34, 34, 255), (0, 0, 12, bh))
        self.recolor = hl in ("red", "navy", "gold")
        # sample sentences: a paper card, ink text, the word on the row colour, the page fades back to paper
        card = _mix(self.paper, (255, 255, 255), 0.6)
        pill = dk if tn else (170, 34, 34)
        self.sentence_look = (dict(back=card, ex=INK, hl=pill, hl_txt=(255, 255, 255) if not tn else lt2,
                                   label=NUM, head=RED, shadow=(70, 55, 40), bars_b=RED, border=INK, border_w=2),
                              self.paper, PLAYFAIR, "SemiBold", "Bold", 6, 0.62)
        self.erows = []
        for j, w in enumerate(self.words):
            r = {}
            for state, (ce, ca, cn, ci) in (("n", (INK, RED, NUM, self.ipa_col)), ("a", (en_a, ar_a, num_a, ipa_a))):
                if state == "a" and not self.recolor:
                    break
                r["num" + state] = _t(PLAYFAIR, f"{j + 1:02d}", 64 * sc, cn, "Bold")
                r["en" + state] = _t(PLAYFAIR, w["en"], 54 * sc, ce, "Bold", max_w=700)
                r["ipa" + state] = _ipa(w["ipa"], 34 * sc, ci) if w["ipa"] else None
                ipa_w = (r["ipa" + state].width - 60 + 40) if w["ipa"] else 0
                r["ar" + state] = _t(MESSIRI, w["ar"], 50 * sc, ca, "Bold", max_w=800 - ipa_w)
                if self.hider:  # meanings hidden until spoken: what each one sits on and its colour
                    on = self.paper if state == "n" or band is None else band
                    self.hider.add(j, state, r["ar" + state], on, ca, MESSIRI, int(50 * sc), "Bold")
            if hl == "marker":
                r["marker"] = self._marker(r["enn"].width - 60, int(52 * sc), j)
            self.erows.append(r)

    @staticmethod
    def _marker(w, h, seed):
        rnd = random.Random(seed + 7)
        s = 2
        im = Image.new("RGBA", ((w + 40) * s, (h + 20) * s), (0, 0, 0, 0))
        top = [(20 + w * i / 12, 10 + rnd.uniform(-3, 3)) for i in range(13)]
        bot = [(20 + w * i / 12, 10 + h + rnd.uniform(-3, 3)) for i in range(12, -1, -1)]
        ImageDraw.Draw(im).polygon([(x * s, y * s) for x, y in top + bot], fill=(255, 214, 60, 205))
        return im.resize((w + 40, h + 20), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))

    def _draw_editorial(self, fr, u):
        fr.paste(_paper(self.paper), (0, 0))
        hp = prog(u, 0.1, 0.5)
        paste(fr, self.head, W / 2, 225 + 20 * (1 - ease_io(hp)), 1, hp)
        sc, p = self.sc, self.pitch
        lit = [self._lit(j, u) for j in range(self.n)]
        cs = [i * (1 - o) for i, o in lit]
        for j, r in enumerate(self.erows):
            a, dy = self._row_in(j, u)
            if a <= 0.01:
                continue
            cy = self.cy[j] + dy
            y0 = cy - p / 2
            c_in, c_out = lit[j]
            if c_in > 0.001 and c_out < 0.999:
                if self.band is not None:  # the band wipes in from the left, fades out when the next word starts
                    bw = max(1, int(960 * c_in))
                    paste(fr, self.band.crop((0, 0, bw, self.band.height)), 60, y0 + p / 2, 1, a * (1 - c_out),
                          anchor="l")
                elif "marker" in r:
                    m = r["marker"]
                    mw = max(1, int(m.width * c_in))
                    paste(fr, m.crop((0, 0, mw, m.height)), 190 - 20, cy - 34 * sc + 4, 1, a * (1 - c_out), anchor="l")
            c = cs[j] if self.recolor else 0.0
            for key, x, y, anchor in (("num", 120, cy - 4, "c"), ("en", 190 - 30, cy - 34 * sc, "l"),
                                      ("ipa", 190 - 30, cy + 40 * sc, "l"), ("ar", 990 + 30, cy + 40 * sc, "r")):
                im_n = r[key + "n"]
                if im_n is None:
                    continue
                im_a = r.get(key + "a")
                if key == "ar" and self.hider is not None and self.hider.hidden(j, u):
                    im_n = self.hider.render(j, "n", u)
                    im_a = self.hider.render(j, "a", u)
                paste(fr, im_n, x, y, 1, a * (1 - c), anchor=anchor)
                if c > 0.001:
                    paste(fr, im_a, x, y, 1, a * c, anchor=anchor)
            if cs[j] > 0.01:
                a1, a2 = self._speaker_alpha(j, u)
                body, w1, w2 = self.spk
                for im, k in ((body, 1.0), (w1, a1), (w2, a2)):
                    paste(fr, im, 975, cy - 34 * sc, 1, a * cs[j] * k)
            if j < self.n - 1:  # the line under the row (hidden next to a band)
                hide = max(cs[j], cs[j + 1]) if self.band is not None else 0.0
                paste(fr, self.sep, W / 2, y0 + p, 1, a * (1 - hide))
        a_last, dy = self._row_in(self.n - 1, u)
        paste(fr, self.rule, W / 2, self.cy[-1] + p / 2 + 10 + dy, 1, a_last)

    # ============================================================ Chalkboard
    def _build_chalk(self, opts, title, subtitle):
        from .list_designs import tones
        tn = tones(opts.get("palette"))
        self.mark = opts.get("mark") if opts.get("mark") in dict((v, k) for k, v in MARKS) else "circle"
        if tn:  # a colour set: the board = its dark tone, the Arabic / tick = its light tone, the mark = its 2nd tone
            dk, lt, lt2 = tn
            self.board = (_mix(dk, (255, 255, 255), 0.06), _mix(dk, (255, 255, 255), 0.12), _mix(dk, (0, 0, 0), 0.25),
                          (120, 80, 44))
            self.chalk_ar, self.tick = lt, lt
            self.mcol = lt2 if lt2 != lt else _mix(lt, (255, 255, 255), 0.45)
        else:
            self.board = opts.get("board") if opts.get("board") in BOARDS else "green"
            self.mcol = CHALK_COLORS.get(opts.get("color"), CHALK_COLORS["pink"])
            self.chalk_ar, self.tick = CHALK_AR, TICK
        sc = self.sc
        self.title_img = _chalkify(_t(PATRICK, title, 96, (245, 245, 240), "Regular", max_w=960), 1)
        self.sub_img = _chalkify(_t(RUQAA, subtitle, 66, self.chalk_ar, "Bold", max_w=960), 2) if subtitle else None
        self.crows = []
        for j, w in enumerate(self.words):
            en = _chalkify(_t(PATRICK, f"{j + 1}. {w['en']}", 70 * sc, CHALK, "Regular", max_w=940), 10 + j)
            arn = _chalkify(_t(RUQAA, w["ar"], 60 * sc, self.chalk_ar, "Bold", max_w=940), 20 + j)
            ara = _chalkify(_t(RUQAA, w["ar"], 60 * sc, self.mcol, "Bold", max_w=940), 30 + j)
            if self.hider:  # meanings hidden until spoken (the split-flap letters get the chalk texture too)
                board = (BOARDS[self.board] if isinstance(self.board, str) else self.board)[1]
                for key, img, col, seed in (("n", arn, self.chalk_ar, 20 + j), ("a", ara, self.mcol, 30 + j)):
                    self.hider.add(j, key, img, board, col, RUQAA, int(60 * sc), "Bold",
                                   post=lambda im, seed=seed: _chalkify(im, seed))
            ew = en.width - 60
            self.crows.append(dict(en=en, arn=arn, ara=ara, ew=ew, mark=self._mark_paths(j, ew),
                                   tick=self._tick_path(j, ew)))
        self._done_cache = {}
        # sample sentences: a darker slate with chalk text, the word on the chalk colour
        top, mid, bot = (BOARDS[self.board] if isinstance(self.board, str) else self.board)[:3]
        self.sentence_look = (dict(back=_mix(mid, (0, 0, 0), 0.15), ex=CHALK, hl=self.mcol,
                                   hl_txt=_mix(bot, (0, 0, 0), 0.3), label=self.chalk_ar, head=self.chalk_ar,
                                   shadow=(0, 0, 0), bars_b=self.mcol,
                                   border=_mix(CHALK, mid, 0.55), border_w=3),
                              _mix(bot, (0, 0, 0), 0.3), PATRICK, "Regular", "Regular", 14, 0.5)

    def _mark_paths(self, j, ew):
        """The chalk mark around row j as polylines in row coordinates (y = 0 is the row centre)."""
        rnd = random.Random(100 + j)
        sc = self.sc
        if self.mark == "underline":
            y = 0
            wave = [(540 - ew / 2 + ew * i / 60, y + 6 * math.sin(i / 60 * 4 * 2 * math.pi)) for i in range(61)]
            ax = 540 - ew / 2 - 25
            ay = -38 * sc
            lines = [wave, [(ax - 50, ay), (ax, ay)], [(ax - 22, ay - 20), (ax, ay), (ax - 22, ay + 20)]]
        elif self.mark == "box":
            x0, x1, y0, y1 = 540 - ew / 2 - 40, 540 + ew / 2 + 40, -92 * sc, 92 * sc
            lines = [[(x0, y0), (x1, y0 + rnd.uniform(-3, 3))], [(x1, y0 - 4), (x1 + rnd.uniform(-4, 4), y1 + 4)],
                     [(x1 + 4, y1), (x0, y1 + rnd.uniform(-3, 3))], [(x0, y1 + 4), (x0 + rnd.uniform(-4, 4), y0 - 4)]]
        else:
            a0 = rnd.uniform(0, 6.28)
            rx, ry = ew / 2 + 60, 98 * sc
            ring = []
            for i in range(100):
                a = a0 + 2 * math.pi * i / 90
                k = 1 + 0.05 * math.sin(a * 3 + a0) + 0.02 * i / 90
                ring.append((540 + rx * k * math.cos(a), ry * k * math.sin(a)))
            lines = [ring]
        return [(_jitter(l, rnd, 2.0), _jitter(l, rnd, 2.0)) for l in lines]

    def _tick_path(self, j, ew):
        x, y, s = 540 + ew / 2 + 50, -40 * self.sc, 18
        return [(x - s, y), (x - s * 0.3, y + s * 0.8), (x + s * 1.2, y - s)]

    def _stroke_img(self, lines, p, col, width, seed, h):
        """Chalk strokes (each line = two jittered passes) drawn up to fraction p, as a row-sized image."""
        s = 2
        im = Image.new("RGBA", (W * s, int(h) * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        total = len(lines)
        for k, passes in enumerate(lines):
            q = min(1.0, max(0.0, p * total - k))  # the lines are drawn one after another
            if q <= 0:
                break
            for pts in passes:
                part = _partial(pts, q)
                if len(part) > 1:
                    d.line([(x * s, (y + h / 2) * s) for x, y in part], fill=tuple(col) + (230,), width=width * s,
                           joint="curve")
        return _chalkify(im.resize((W, int(h)), Image.LANCZOS), seed)

    def _draw_chalk(self, fr, u):
        fr.paste(_board(self.board), (0, 0))
        hp = prog(u, 0.1, 0.5)
        rise = 20 * (1 - ease_io(hp))
        paste(fr, self.title_img, W / 2, 225 + rise, 1, hp)
        if self.sub_img is not None:
            paste(fr, self.sub_img, W / 2, 330 + rise, 1, hp)
        sc, box_h = self.sc, self.pitch + 60
        for j, r in enumerate(self.crows):
            a, dy = self._row_in(j, u)
            if a <= 0.01:
                continue
            cy = self.cy[j] + dy
            c_in, c_out = self._lit(j, u)
            c = c_in * (1 - c_out)
            bright = 0.72 + 0.28 * prog(u, self.starts[j] - 0.15, self.starts[j] + 0.15)  # not read yet = faded
            paste(fr, r["en"], W / 2, cy - 38 * sc, 1, a * bright)
            arn, ara = r["arn"], r["ara"]
            if self.hider is not None and self.hider.hidden(j, u):
                arn, ara = self.hider.render(j, "n", u), self.hider.render(j, "a", u)
            paste(fr, arn, W / 2, cy + 46 * sc, 1, a * bright * (1 - c))
            if c > 0.001:
                paste(fr, ara, W / 2, cy + 46 * sc, 1, a * c)
            pm = prog(u, self.starts[j] - 0.05, self.starts[j] + 0.5)
            if pm > 0 and c_out < 1:
                key = ("mark", j)
                if pm >= 1:
                    if key not in self._done_cache:
                        self._done_cache[key] = self._stroke_img(r["mark"], 1.0, self.mcol, 6, 40 + j, box_h)
                    img = self._done_cache[key]
                else:
                    img = self._stroke_img(r["mark"], pm, self.mcol, 6, 40 + j, box_h)
                paste(fr, img, W / 2, cy, 1, a * (1 - c_out))
            pt = prog(u, self.ends[j], self.ends[j] + 0.3)
            if pt > 0:
                key = ("tick", j)
                if pt >= 1:
                    if key not in self._done_cache:
                        self._done_cache[key] = self._stroke_img([(r["tick"], r["tick"])], 1.0, self.tick, 7, 60 + j,
                                                                 box_h)
                    img = self._done_cache[key]
                else:
                    img = self._stroke_img([(r["tick"], r["tick"])], pt, self.tick, 7, 60 + j, box_h)
                paste(fr, img, W / 2, cy, 1, a)
