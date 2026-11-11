"""English in News: a short news clip (your own video) with big subtitles. The subtitles follow the speech word by word
(the timings come from ElevenLabs speech-to-text), the key words you pick are marked in the subtitles and, when they
are spoken, a card pops up with the word and its Arabic meaning. A recap of every key word closes the video.

Words box (the project's `news.words`, the same columns as 📖 English Texts):
    word | start | end | highlighted | arabic
one spoken word per line, times in seconds in the uploaded video. A line with something in `highlighted` is a key
word (`*` = the word itself); neighbouring lines with the same several-word highlighted text are one phrase.

Looks (`news.look`, see LOOKS): one engine, each look only sets colours / fonts and picks its background, header,
subtitle, card and ending variants:
    pop        creator style: 1-3 huge words at a time, yellow sticker cards                  (default)
    breaking   dark, blurred copy of the clip behind a framed panel, white cards
    studio     clean and light, dark word cards
    tv         broadcast: subtitles on a solid band, lower-third word bar, a ticker of the words
    paper      newspaper: newsprint, serif type, paper clippings with tape

Layout: a landscape / square video sits in a framed panel near the top; a vertical video fills the screen.
Subtitles and the word card stay inside the Shorts safe area (above y 1536). The source video is decoded by FFmpeg
as it is needed; render(t) depends only on t (frames are drawn on several processes, each with its own decoder, in
long runs of frames: `chunk`).
"""
import io
import math
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..audio import SR, load_audio
from ..core import H, ROOT, W, ffmpeg_exe, get_font
from .text import DEFAULT_LOGO, _ar_fit, _comp, _fade, _groups, _shadow_box, _spring, logo_badge, parse_words

NAME = "English in News"

_LIB = os.path.join(ROOT, "fonts", "library")


def _lib(*parts):
    path = os.path.join(_LIB, *parts)
    return path if os.path.isfile(path) else os.path.join(ROOT, "fonts", "Cairo.ttf")


MONT = _lib("Montserrat", "Montserrat[wght].ttf")
ANTON = _lib("Anton", "Anton-Regular.ttf")
OSWALD = _lib("Oswald", "Oswald[wght].ttf")
PLAYFAIR = _lib("PlayfairDisplay", "PlayfairDisplay[wght].ttf")
LITERATA = _lib("Literata", "Literata[opsz,wght].ttf")
PLEX_AR = _lib("IBMPlexSansArabic", "IBMPlexSansArabic-Bold.ttf")
AMIRI = _lib("Amiri", "Amiri-Bold.ttf")
TAJAWAL = _lib("Tajawal", "Tajawal-Black.ttf")

LEAD = 0.7                  # the header comes in over the first frame before the clip plays
ENDING_LEN = 5.0
CARD_MIN, CARD_HOLD = 1.8, 4.2
SAFE_BOTTOM = 1536
CAP_MAX_W = 900
POP_MAX_W = 820            # pop: the widest a line of huge words may be (1080 - 2 x 130)
TICKER_Y = 1470            # the tv ticker (64 px high, ends at the safe-area line)
ACCENTS = {"red": (228, 30, 48), "blue": (28, 110, 230), "teal": (0, 150, 150), "orange": (240, 120, 20),
           "purple": (126, 64, 210)}
ACCENT_CHOICES = [("News red", "red"), ("Blue", "blue"), ("Teal", "teal"), ("Orange", "orange"),
                  ("Purple", "purple")]
YELLOW = (255, 214, 10)
INK = (20, 22, 28)
WHITE = (255, 255, 255)
_SENT_END = re.compile(r"[.!?…][\"'”’)\]]*$")

# every look: colours, fonts and which variant of each part it draws
_BASE = dict(
    bg="blur",                       # blur (the clip, blurred) | light | paper
    shade=0.45,                      # darkening over a blurred background
    header="bar",                    # bar (accent bar left of the headline) | box (tv) | masthead (paper)
    head_col=WHITE, sub_col=WHITE, head_font=MONT, head_weight="ExtraBold",
    panel_r=26, panel_rim=(255, 255, 255, 70), panel_shadow=150, track=(255, 255, 255, 60),
    cap_mode="page", cap_font=MONT, cap_weight="ExtraBold", cap_size=62, upper=False, max_lines=2, max_words=99,
    cap_col=WHITE, cap_stroke=4, stroke_col=(10, 12, 18), dim=0.55,
    speak="pill", speak_col=WHITE,   # pill (accent pill behind the spoken word) | color (spoken word recoloured)
    mark=YELLOW, key_col=INK, key_stroke=None,
    band=None,                       # a solid band behind the subtitles (tv)
    card="pop",                      # pop | bar (tv lower third) | sticker (pop) | clip (paper)
    card_bg=WHITE, card_en=INK, card_ar=None, card_label=None, card_font=MONT, card_weight="ExtraBold",
    ar_font=PLEX_AR, ticker=False,
    end_bg=WHITE, end_row=(244, 245, 248), end_en=INK, end_ar=None, end_sub=(120, 126, 136), end_font=MONT,
    end_text=WHITE,
)
LOOKS = {
    "breaking": dict(),
    "studio": dict(bg="light", head_col=INK, sub_col=(70, 76, 88), panel_rim=(0, 0, 0, 0), panel_shadow=90,
                   track=(20, 22, 28, 40), cap_col=INK, cap_stroke=0, dim=0.32, card_bg=INK, card_en=WHITE,
                   card_ar=YELLOW, end_text=INK),
    "tv": dict(header="box", head_font=OSWALD, head_weight="Bold", cap_font=OSWALD, cap_weight="SemiBold",
               cap_size=60, cap_stroke=0, band=(8, 12, 26, 235), dim=0.5, speak="color", speak_col=YELLOW,
               card="bar", card_font=OSWALD, card_weight="Bold", ticker=True, panel_r=6, end_font=OSWALD),
    "pop": dict(cap_mode="pop", cap_font=ANTON, cap_weight="Regular", cap_size=112, upper=True, max_lines=1,
                max_words=3, cap_stroke=8, stroke_col=(0, 0, 0), dim=1.0, speak="color", speak_col=YELLOW,
                key_col=WHITE, key_stroke=(0, 0, 0), card="sticker", card_bg=YELLOW, card_en=INK, card_font=ANTON,
                card_weight="Regular", ar_font=TAJAWAL, head_font=ANTON, head_weight="Regular", panel_r=34),
    "paper": dict(bg="paper", header="masthead", head_col=INK, sub_col=(90, 84, 76), head_font=PLAYFAIR,
                  head_weight="Bold", panel_r=3, panel_rim=(30, 28, 26, 255), panel_shadow=70,
                  track=(30, 28, 26, 50), cap_font=LITERATA, cap_weight="SemiBold", cap_size=58, cap_col=INK,
                  cap_stroke=0, dim=0.38, speak="color", speak_col=None, mark=(255, 226, 90), card="clip",
                  card_bg=(253, 251, 245), card_font=PLAYFAIR, card_weight="Bold", ar_font=AMIRI,
                  end_bg=(253, 251, 245), end_row=(244, 239, 228), end_font=PLAYFAIR, end_text=INK),
}
LOOK_CHOICES = [("💥 Pop (big words)", "pop"), ("🔴 Breaking (dark)", "breaking"), ("⚪ Studio (light)", "studio"),
                ("📺 TV broadcast", "tv"), ("📰 Newspaper", "paper")]
DEFAULT_LOOK = "pop"

EXAMPLE = {
    "template": "news",
    "settings": {"theme": "Night Sky", "language": "en", "fps": 30, "music": "None", "music_gain": 0.4,
                 "music_file": "", "voice_file": "", "voice_offset": 0.0, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": "", "intro_sound": "None", "tick_sound": "Classic",
                 "tick_gain": 1.0},
    "ending": {"intro": "Words from the news", "question": "", "cta": "Follow for English from the news every day"},
    "news": {
        "video": "",
        "look": DEFAULT_LOOK,
        "headline": "Heatwave pushes cities to open cooling centres",
        "tag": "NEWS",
        "label": "ENGLISH IN NEWS",
        "brand_name": "LOGOLEPT",
        "logo_shape": "circle",
        "accent": "red",
        "trim_start": 0.0,
        "trim_end": 0.0,
        "video_gain": 1.0,
        "ending_on": True,
        "words": "\n".join([
            "Officials | 0.20 | 0.72 | * | المسؤولون",
            "say | 0.78 | 0.95", "the | 0.98 | 1.05",
            "heatwave | 1.10 | 1.62 | * | موجة حر",
            "could | 1.70 | 1.88", "last | 1.92 | 2.20", "until | 2.24 | 2.48", "the | 2.52 | 2.60",
            "weekend. | 2.64 | 3.10",
            "Cities | 3.50 | 3.90", "are | 3.94 | 4.04",
            "opening | 4.08 | 4.46 | * | تفتح",
            "cooling | 4.52 | 4.90 | cooling centres | مراكز تبريد",
            "centres | 4.94 | 5.40 | cooling centres",
            "for | 5.46 | 5.58", "people | 5.62 | 5.94", "most | 6.00 | 6.24", "at | 6.28 | 6.36",
            "risk. | 6.40 | 6.86 | at risk | معرّضون للخطر"]),
    },
}


# ------------------------------------------------------------------ the source video
def probe(path):
    """(width, height, duration s, has audio) of a video as FFmpeg will deliver its frames (phone rotation applied)."""
    p = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", path, "-frames:v", "1", "-f", "image2pipe",
                        "-vcodec", "png", "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"Could not read the video: {os.path.basename(str(path))}")
    w, h = Image.open(io.BytesIO(p.stdout)).size
    info = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True).stderr.decode(errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    return w, h, dur, bool(re.search(r"Stream #.*Audio:", info))


class _Decoder:
    """Frames of the source video at the output fps, scaled to `size`, read in order from one FFmpeg process;
    a jump back (or far ahead) restarts it at the wanted time."""

    def __init__(self, path, size, fps, start):
        self.path, self.size, self.fps, self.start = path, size, fps, start
        self.proc, self.next, self.last = None, None, None

    def _open(self, idx):
        self.close()
        cmd = [ffmpeg_exe(), "-v", "error", "-ss", f"{self.start + idx / self.fps:.4f}", "-i", self.path,
               "-an", "-vf", f"fps={self.fps},scale={self.size[0]}:{self.size[1]}:flags=bicubic,setsar=1",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.next = idx

    def _read(self):
        n = self.size[0] * self.size[1] * 3
        buf = self.proc.stdout.read(n) if self.proc else b""
        if len(buf) < n:
            self.close()
            return None
        self.next += 1
        return Image.frombuffer("RGB", self.size, buf, "raw", "RGB", 0, 1)

    def frame(self, idx):
        if self.proc is None or self.next is None or idx < self.next or idx > self.next + 90:
            if self.last is not None and idx == self.last[0]:
                return self.last[1]
            self._open(idx)
        im = None
        while self.proc is not None and self.next <= idx:
            got = self._read()
            if got is not None:
                im = got
        if im is None:  # past the end (or a decode error): hold the last good frame
            return self.last[1] if self.last is not None else Image.new("RGB", self.size, (12, 14, 20))
        self.last = (idx, im)
        return im

    def close(self):
        if self.proc is not None:
            try:
                self.proc.stdout.close()
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass
        self.proc = None

    def __del__(self):
        self.close()

    def __getstate__(self):  # never send a running process to another process
        d = dict(self.__dict__)
        d.update(proc=None, next=None, last=None)
        return d


# ------------------------------------------------------------------ drawing helpers
def _text(txt, size, col, weight="Bold", path=MONT, stroke=0, stroke_col=(0, 0, 0)):
    """One line of Latin text as an RGBA image (6 px + stroke of room around the font box)."""
    f = get_font(int(size), weight, path)
    asc, desc = f.getmetrics()
    pad = 6 + stroke
    w = int(math.ceil(f.getlength(txt))) + 2 * pad
    im = Image.new("RGBA", (max(1, w), asc + desc + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), txt, font=f, fill=tuple(col)[:3] + (255,), stroke_width=stroke,
                            stroke_fill=tuple(stroke_col)[:3] + (255,))
    return im


def _fit_text(txt, size, col, max_w, weight="Bold", path=MONT, min_size=26):
    im = _text(txt, size, col, weight, path)
    if im.width > max_w:
        im = _text(txt, max(min_size, int(size * max_w / im.width)), col, weight, path)
    return im


def _wrap(txt, size, weight, path, max_w, max_lines=2):
    f = get_font(int(size), weight, path)
    lines, cur = [], ""
    for w in txt.split():
        test = (cur + " " + w).strip()
        if cur and f.getlength(test) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines if len(lines) <= max_lines else None


def _rounded(size, r, fill):
    S = 3
    im = Image.new("RGBA", (size[0] * S, size[1] * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, size[0] * S - 1, size[1] * S - 1], r * S, fill=fill)
    return im.resize(size, Image.LANCZOS)


def _round_mask(size, r):
    return _rounded(size, r, (255, 255, 255, 255)).getchannel("A")


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _back(x):
    x = max(0.0, min(1.0, x))
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _scaled(im, sc):
    if abs(sc - 1) < 0.004:
        return im
    return im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)


def _noise(size, amount, seed=3):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, amount, (max(1, size[1] // 2), max(1, size[0] // 2))).astype(np.float32)
    return np.array(Image.fromarray(n, "F").resize(size, Image.BILINEAR), np.float32)


# ------------------------------------------------------------------ the video
class NewsVideo:
    chunk = 45                    # frames per job when rendering on several processes (fewer decoder restarts)

    def __init__(self, project):
        s = project.get("settings", {}) or {}
        n = dict(EXAMPLE["news"])
        self.given = project.get("news", {}) or {}
        n.update({k: v for k, v in self.given.items() if v is not None})
        e = project.get("ending", {}) or {}
        self.fps = int(s.get("fps") or 30)
        self.handle = str(s.get("handle") or "").strip()
        self.accent = ACCENTS.get(n.get("accent"), ACCENTS["red"])
        self.look_name = n.get("look") if n.get("look") in LOOKS else DEFAULT_LOOK
        L = dict(_BASE)
        L.update(LOOKS[self.look_name])
        for k in ("card_ar", "card_label", "end_ar", "speak_col"):
            if L[k] is None:
                L[k] = self.accent
        self.L = L
        self.headline = str(n.get("headline") or "").strip()
        self.tag = str(n.get("tag") or "").strip().upper()
        self.label = str(n.get("label") or "").strip().upper()
        self.video_gain = float(n.get("video_gain") or 1.0)
        self.ending_title = str(e.get("intro") or "Words from the news").strip()
        self.cta = str(e.get("cta") or "").strip()
        self.silences = []

        # the source
        self.path = str(n.get("video") or "")
        self.trim0 = max(0.0, float(n.get("trim_start") or 0.0))
        if self.path and os.path.isfile(self.path):
            sw, sh, sdur, self.has_audio = probe(self.path)
        else:
            self.path, sw, sh, sdur, self.has_audio = "", 16, 9, 8.0, False
        end = float(n.get("trim_end") or 0.0)
        end = sdur if end <= self.trim0 or end > sdur else end
        self.clip = max(0.5, end - self.trim0)
        self.vertical = sh > sw * 1.05
        if self.vertical:   # fills the screen (cover)
            k = max(W / sw, H / sh)
            self.vsize = (int(round(sw * k)) // 2 * 2, int(round(sh * k)) // 2 * 2)
            self.vpos = ((W - self.vsize[0]) // 2, (H - self.vsize[1]) // 2)
        else:               # a framed panel under the headline (placed in _layout)
            pw = 1000
            ph = min(720, int(round(pw * sh / sw)))
            pw = min(pw, int(round(ph * sw / sh)))
            self.vsize = (pw // 2 * 2, ph // 2 * 2)
            self.vpos = ((W - self.vsize[0]) // 2, 360)
        self.dec = _Decoder(self.path, self.vsize, self.fps, self.trim0) if self.path else None

        # words (times relative to the clip, then to the video)
        self.words = []
        for w in parse_words(n.get("words")):
            s0, e0 = w["s"] - self.trim0, w["e"] - self.trim0
            if e0 <= 0 or s0 >= self.clip:
                continue
            self.words.append(dict(w, s=LEAD + max(0.0, s0), e=LEAD + min(self.clip, e0)))
        self.groups = _groups(self.words)
        self.key_of = {}
        for gi, g in enumerate(self.groups):
            g["t0"] = self.words[g["i0"]]["s"]
            g["t1"] = self.words[g["i1"]]["e"]
            for k in range(g["i0"], g["i1"] + 1):
                self.key_of[k] = gi

        self.E = LEAD + self.clip                     # the clip ends
        self.ending_on = bool(n.get("ending_on", True)) and bool(self.groups)
        self.base_duration = self.E + (ENDING_LEN if self.ending_on else 0.6)
        self.dur = self.base_duration
        self._layout(n)

    # -------------------------------------------------------------- layout (once)
    def _layout(self, n):
        L, A = self.L, self.accent
        # no "logo" in the project = the bundled logo; a removed picture (empty) = no logo
        given = self.given
        logo = given.get("logo") if "logo" in given else DEFAULT_LOGO
        self.logo = logo_badge(logo, 92, n.get("logo_shape") or "circle") if logo else None
        self.brand_name = str(n.get("brand_name") or "").strip().upper()
        self.brand_im = _text(self.brand_name, 30, L["head_col"], "Black") if self.brand_name else None
        self.label_im = _text(self.label, 26, L["sub_col"], "Bold") if self.label else None
        self.tag_im = None
        if self.tag:
            t = _text(self.tag, 28, WHITE, "Black")
            pill = _rounded((t.width + 44, t.height + 6), (t.height + 6) // 2, A + (255,))
            pill.alpha_composite(t, (30, 3))
            self.tag_im = pill
        self._layout_headline()

        self.head_y = 110
        cap_block = int(L["cap_size"] * (1.10 if L["cap_mode"] == "pop" else 1.32)) * L["max_lines"]
        if self.vertical:   # subtitles in the middle-low part, the card under them (all above the safe line)
            self.cap_y = 960 if L["cap_mode"] == "pop" else 880
            self.card_y = self.cap_y + cap_block + 40
        else:
            self.vpos = (self.vpos[0], max(330, self.head_bottom + 40))
            self.cap_y = self.vpos[1] + self.vsize[1] + (58 if L["band"] else 70)
            self.card_y = max(self.cap_y + (150 if L["cap_mode"] == "pop" else 210), 1180)
        if L["card"] == "bar":
            self.card_y = min(self.card_y, 1250)

        self._layout_background()
        if not self.vertical:
            self._layout_panel()
        self._layout_captions()
        self._layout_cards()
        if L["ticker"]:
            self._layout_ticker()
        if self.ending_on:
            self._layout_ending()

    def _layout_headline(self):
        L = self.L
        size = 66 if L["head_font"] == ANTON else (60 if L["header"] == "masthead" else 56)
        width = 880 if L["header"] == "box" else 930
        txt = self.headline.upper() if L["head_font"] in (ANTON, OSWALD) else self.headline
        lines = None
        while size >= 34:
            lines = _wrap(txt, size, L["head_weight"], L["head_font"], width, 2)
            if lines:
                break
            size -= 2
        lines = lines or [txt]
        col = WHITE if L["header"] == "box" else L["head_col"]
        self.head_lines = [_text(ln, size, col, L["head_weight"], L["head_font"]) for ln in lines if ln]
        self.head_lh = int(size * 1.22)
        top = 110 + (150 if L["header"] == "masthead" else 120)
        self.head_bottom = top + self.head_lh * len(self.head_lines) + (30 if L["header"] == "box" else 0)

    def _layout_background(self):
        L = self.L
        y = np.linspace(0, 1, H)[:, None]
        if L["bg"] == "light":
            c0, c1 = np.array([250, 250, 252]), np.array([226, 231, 240])
            arr = np.broadcast_to(c0 * (1 - y[..., None]) + c1 * y[..., None], (H, W, 3)).copy()
            xx = np.linspace(0, 1, W)[None, :]
            blob = np.exp(-(((xx - 0.95) / 0.45) ** 2 + ((y - 0.05) / 0.25) ** 2))
            arr += (np.array(self.accent) - arr) * (blob[..., None] * 0.22)
            self.static_bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        elif L["bg"] == "paper":
            arr = np.broadcast_to(np.array([243, 238, 226], np.float32), (H, W, 3)).copy()
            arr += _noise((W, H), 7.0)[..., None]
            arr -= (np.abs(y - 0.5) * 14)[..., None]
            self.static_bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        else:
            self.static_bg = None
        self.shade = None
        a = None
        if self.vertical:
            if L["cap_col"] == INK:   # dark text over a full-screen clip: a light sheet behind header + subtitles
                y0 = (self.cap_y - 90) / H
                v = np.clip((0.26 - y) / 0.10, 0, 1) + np.clip((y - y0) / 0.04, 0, 1) * (y < 0.85)
                veil = np.zeros((H, W, 4), np.uint8)
                veil[..., :3] = 250
                veil[..., 3] = np.broadcast_to(np.clip(v, 0, 1) * 225, (H, W)).astype(np.uint8)
                self.shade = Image.fromarray(veil, "RGBA")
            else:                     # dark at the top (header) and the bottom (subtitles)
                a = np.clip((0.30 - y) / 0.30, 0, 1) ** 1.4 * 0.75 + np.clip((y - 0.45) / 0.40, 0, 1) ** 1.3 * 0.82
        elif self.static_bg is None:  # an even darkening over the blurred clip
            a = L["shade"] + 0.3 * np.clip((y - 0.5) / 0.5, 0, 1)
        if a is not None:
            sh = np.zeros((H, W, 4), np.uint8)
            sh[..., :3] = (6, 8, 14)
            sh[..., 3] = np.broadcast_to(np.clip(a, 0, 1) * 255, (H, W)).astype(np.uint8)
            self.shade = Image.fromarray(sh, "RGBA")

    def _layout_panel(self):
        L = self.L
        pw, ph = self.vsize
        r = L["panel_r"]
        self.mask = _round_mask(self.vsize, r)
        pad = 40
        self.shadow = _shadow_box((pw + 2 * pad, ph + 2 * pad), (pad, pad + 10, pad + pw, pad + ph + 10), r + 4,
                                  18, L["panel_shadow"], 0)
        S = 3
        big = Image.new("RGBA", (pw * S, ph * S), (0, 0, 0, 0))
        if L["panel_rim"][3]:
            ImageDraw.Draw(big).rounded_rectangle([1, 1, pw * S - 2, ph * S - 2], r * S, outline=L["panel_rim"],
                                                  width=3 * S)
        self.rim = big.resize((pw, ph), Image.LANCZOS)

    # ---------------------------------------------------------- subtitles
    def _cap_txt(self, i):
        w = self.words[i]["w"]
        return w.upper() if self.L["upper"] else w

    def _layout_captions(self):
        """Words -> subtitle pages (one or two lines; 1-3 words in the pop look), each word placed once."""
        L = self.L
        size = L["cap_size"]
        f = get_font(size, L["cap_weight"], L["cap_font"])
        space = f.getlength(" ")

        def lines_of(idx):
            lines, row, x = [], [], 0.0
            for i in idx:
                w = f.getlength(self._cap_txt(i))
                if row and x + space + w > CAP_MAX_W:
                    lines.append(row)
                    row, x = [], 0.0
                row.append(i)
                x += (space if len(row) > 1 else 0) + w
            if row:
                lines.append(row)
            return lines

        pages, cur = [], []
        pop = L["cap_mode"] == "pop"
        for i, w in enumerate(self.words):
            if cur:
                prev = self.words[cur[-1]]
                gap = w["s"] - prev["e"]
                too_long = w["e"] - self.words[cur[0]]["s"] > (1.6 if pop else 3.4)
                sent = _SENT_END.search(prev["w"]) and (len(cur) >= 3 or pop)
                comma = pop and prev["w"].endswith(",")
                same_key = self.key_of.get(i) is not None and self.key_of.get(i) == self.key_of.get(cur[-1])
                if not same_key and (gap > (0.45 if pop else 0.7) or too_long or sent or comma
                                     or len(cur) >= L["max_words"] or len(lines_of(cur + [i])) > L["max_lines"]):
                    pages.append(cur)
                    cur = []
            cur.append(i)
        if cur:
            pages.append(cur)

        self.pages = []
        lh = int(size * (1.10 if pop else 1.32))
        lead = 0.04 if pop else 0.12
        for k, idx in enumerate(pages):
            t0 = self.words[idx[0]]["s"] - lead
            nxt = self.words[pages[k + 1][0]]["s"] - lead if k + 1 < len(pages) else self.E
            t1 = min(nxt, self.words[idx[-1]]["e"] + (0.5 if pop else 1.2))
            items = []
            for li, row in enumerate(lines_of(idx)):
                ims = [self._cap_word(i) for i in row]
                total = sum(im["w"] for im in ims) + space * (len(row) - 1)
                x = (W - total) / 2
                for i, im in zip(row, ims):
                    items.append(dict(im, i=i, x=x, line=li))
                    x += im["w"] + space
            nl = max(it["line"] for it in items) + 1
            widest = max(sum(it["w"] for it in items if it["line"] == li) + space * (sum(
                1 for it in items if it["line"] == li) - 1) for li in range(nl))
            fit = min(1.0, POP_MAX_W / widest) if pop else 1.0   # a long word group shrinks to stay clear of the
            self.pages.append(dict(t0=t0, t1=t1, items=items, lines=nl, lh=lh, fit=fit))  # Shorts buttons
        if L["band"]:
            self.band_box = (0, self.cap_y - 18, W, self.cap_y - 18 + lh * L["max_lines"] + 30)

    def _cap_word(self, i):
        L = self.L
        txt, size, st = self._cap_txt(i), L["cap_size"], L["cap_stroke"]

        def mk(col, stroke=st, sc=L["stroke_col"]):
            return _text(txt, size, col, L["cap_weight"], L["cap_font"], stroke, sc)

        norm = mk(L["cap_col"])
        if L["speak"] == "pill":
            speak = mk(WHITE) if L["cap_col"] == INK else norm
        else:
            speak = mk(L["speak_col"])
        if L["key_stroke"]:
            key = mk(L["key_col"], st, L["key_stroke"])
        else:
            key = mk(L["key_col"], 3 if st else 0, L["mark"])
        pad = 6 + st
        return dict(norm=norm, speak=speak, key=key, pad=pad, w=norm.width - 2 * pad)

    def _draw_captions(self, frame, t, a):
        L = self.L
        if L["band"]:
            self._draw_band(frame, a)
        page = next((p for p in self.pages if p["t0"] <= t < p["t1"]), None)
        if page is None:
            return
        pop = L["cap_mode"] == "pop"
        ka = _ease((t - page["t0"]) / (0.08 if pop else 0.15)) * min(1.0, (page["t1"] - t) / 0.1) * a
        rise = 0 if pop else int((1 - _ease((t - page["t0"]) / 0.2)) * 18)
        fit = page["fit"]
        pscale = (0.75 + 0.25 * _back((t - page["t0"]) / 0.22)) * fit if pop else 1.0
        lh = page["lh"]
        base_y = self.cap_y + (0 if page["lines"] == L["max_lines"] else lh // 2 * (L["max_lines"] - 1)) + rise
        d = ImageDraw.Draw(frame)
        for it in page["items"]:
            if fit < 1:   # move the word towards the centre as the whole line shrinks
                cx = it["x"] + it["w"] / 2
                it = dict(it, x=it["x"] + (W / 2 + (cx - W / 2) * fit - cx))
            w = self.words[it["i"]]
            y = base_y + it["line"] * lh
            gi = self.key_of.get(it["i"])
            spoken = t >= w["s"]
            speaking = w["s"] <= t < w["e"] + 0.05
            h = it["norm"].height
            if gi is not None and spoken:   # the marker swipes in behind the key word
                p = _ease((t - w["s"]) / max(0.12, min(0.35, w["e"] - w["s"])))
                im = it["key"] if p > 0.5 else it["norm"]
                sc = pscale * (1.0 + 0.08 * _spring(t - self.groups[gi]["t0"]))
                if L["key_stroke"]:         # pop: an accent box springs up behind the word
                    self._pop_box(frame, it, y, p * ka, pscale)
                else:
                    x0 = it["x"] - 10
                    d.rounded_rectangle([x0, y + 4, x0 + (it["w"] + 20) * p, y + h - 4], 12,
                                        fill=L["mark"] + (int(255 * ka),))
                self._put_word(frame, im, it, y, sc, ka)
                continue
            im, alpha, sc = it["norm"], (ka if spoken else ka * L["dim"]), pscale
            if speaking:
                im = it["speak"]
                if L["speak"] == "pill":
                    d.rounded_rectangle([it["x"] - 10, y + 6, it["x"] + it["w"] + 10, y + h - 6], 12,
                                        fill=self.accent + (int(235 * ka),))
                else:
                    sc *= 1.0 + 0.07 * math.sin(math.pi * min(1.0, (t - w["s"]) / 0.25))
                    if L["bg"] == "paper":  # newspaper: the spoken word is also underlined
                        d.line([(it["x"], y + h - 12), (it["x"] + it["w"], y + h - 12)], fill=self.accent,
                               width=4)
            elif gi is not None:  # a key word not spoken yet: underlined
                d.rounded_rectangle([it["x"], y + h - 12, it["x"] + it["w"], y + h - 6], 3,
                                    fill=L["mark"] + (int(220 * alpha),))
            self._put_word(frame, im, it, y, sc, alpha)

    def _put_word(self, frame, im, it, y, sc, alpha):
        x = it["x"] - it["pad"]
        if abs(sc - 1) > 0.004:
            big = _scaled(im, sc)
            x -= (big.width - im.width) / 2
            y -= (big.height - im.height) / 2
            im = big
        _comp(frame, _fade(im, alpha), int(x), int(y))

    def _pop_box(self, frame, it, y, k, sc):
        if k <= 0:
            return
        h = it["norm"].height
        box = _rounded((max(2, int((it["w"] + 28) * sc)), max(2, int((h - 20) * sc))), 16, self.accent + (255,))
        box = _scaled(box.rotate(-2.5, expand=True, resample=Image.BICUBIC), 0.7 + 0.3 * _back(k))
        cx, cy = it["x"] + it["w"] / 2, y + h / 2 + 2
        _comp(frame, _fade(box, min(1.0, k * 1.5)), int(cx - box.width / 2), int(cy - box.height / 2))

    def _draw_band(self, frame, a):
        x0, y0, x1, y1 = self.band_box
        band = Image.new("RGBA", (x1 - x0, y1 - y0), self.L["band"][:3] + (int(self.L["band"][3] * a),))
        frame.alpha_composite(band, (x0, y0))
        ImageDraw.Draw(frame).rectangle([x0, y0, x1, y0 + 5], fill=self.accent + (int(255 * a),))

    # ---------------------------------------------------------- word cards
    def _layout_cards(self):
        self.cards = []
        n = len(self.groups)
        make = {"pop": self._card_pop, "bar": self._card_bar, "sticker": self._card_sticker,
                "clip": self._card_clip}[self.L["card"]]
        for gi, g in enumerate(self.groups):
            t0 = g["t0"]
            nxt = self.groups[gi + 1]["t0"] if gi + 1 < n else self.E + 0.3
            t1 = min(nxt - 0.27, t0 + CARD_HOLD, self.E + 0.2)  # gone (0.25 s exit) before the next one comes
            t1 = max(t1, t0 + min(CARD_MIN, max(0.6, nxt - 0.27 - t0)))
            self.cards.append(dict(im=make(gi, g, n), t0=t0, t1=t1, gi=gi))
        if self.L["card"] == "bar" and self.cards:  # the lower third sits just above the ticker
            low = max(c["im"].height for c in self.cards) - 20
            self.card_y = min(self.card_y, TICKER_Y - 14 - low)

    def _card_pop(self, gi, g, n):
        """breaking / studio: a rounded card, KEY WORD n/N, the English, a short line, the Arabic."""
        L = self.L
        cw = 860
        label = _text(f"KEY WORD  {gi + 1}/{n}", 26, L["card_label"], "Black")
        en = _fit_text(g["text"], 88, L["card_en"], cw - 80, L["card_weight"], L["card_font"])
        ar = _ar_fit(g["ar"], 76, L["card_ar"], L["ar_font"], cw - 80) if g["ar"] else None
        ch = 40 + label.height + en.height - 4 + (24 + ar.height if ar is not None else 0) + 34
        card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        card.alpha_composite(_shadow_box(card.size, (40, 48, 40 + cw, 48 + ch), 36, 20, 120, 0))
        body = _rounded((cw, ch), 36, L["card_bg"] + (255,))
        body.paste(Image.new("RGBA", (cw, 10), self.accent + (255,)), (0, 0),
                   _round_mask((cw, 40), 36).crop((0, 0, cw, 10)))
        card.alpha_composite(body, (40, 40))
        y = 40 + 34
        card.alpha_composite(label, (40 + (cw - label.width) // 2, y))
        y += label.height - 4
        card.alpha_composite(en, (40 + (cw - en.width) // 2, y))
        y += en.height
        if ar is not None:
            line = (225, 228, 232) if L["card_bg"] == WHITE else (70, 74, 84)
            ImageDraw.Draw(card).line([(40 + cw / 2 - 60, y + 6), (40 + cw / 2 + 60, y + 6)], fill=line, width=3)
            y += 24
            card.alpha_composite(ar, (40 + (cw - ar.width) // 2, y))
        return card

    def _card_bar(self, gi, g, n):
        """tv: a lower third — accent block (KEY WORD n/N), white bar with the English, dark bar with the Arabic."""
        L = self.L
        bw = 960
        tag = _text("KEY WORD", 26, WHITE, "Bold", OSWALD)
        num = _text(f"{gi + 1}/{n}", 40, WHITE, "Bold", OSWALD)
        en = _fit_text(g["text"].upper(), 74, INK, bw - 260, L["card_weight"], OSWALD)
        ar = _ar_fit(g["ar"], 54, WHITE, L["ar_font"], bw - 260) if g["ar"] else None
        if ar is not None:  # only the ink + a little room (the font box is tall)
            box = ar.getchannel("A").getbbox() or (0, 0, ar.width, ar.height)
            ar = ar.crop((0, max(0, box[1] - 12), ar.width, min(ar.height, box[3] + 14)))
        h1 = 108
        h2 = (ar.height + 8) if ar is not None else 0
        im = Image.new("RGBA", (bw + 40, h1 + h2 + 40), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (20, 26, 20 + bw, 26 + h1 + h2), 4, 12, 120, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([20, 20, 20 + bw, 20 + h1], fill=WHITE)
        d.rectangle([20, 20, 20 + 190, 20 + h1], fill=self.accent)
        im.alpha_composite(tag, (20 + (190 - tag.width) // 2, 20 + 12))
        im.alpha_composite(num, (20 + (190 - num.width) // 2, 20 + 42))
        im.alpha_composite(en, (20 + 220, 20 + (h1 - en.height) // 2))
        if ar is not None:
            d.rectangle([20 + 190, 20 + h1, 20 + bw, 20 + h1 + h2], fill=(10, 14, 28))
            im.alpha_composite(ar, (20 + bw - 30 - ar.width, 20 + h1 + 2))
        return im

    def _card_sticker(self, gi, g, n):
        """pop: a tilted yellow sticker with the English, and the Arabic on a black pill under it."""
        L = self.L
        en = _fit_text(g["text"].upper(), 104, INK, 760, "Regular", ANTON)
        ar = _ar_fit(g["ar"], 70, WHITE, L["ar_font"], 720) if g["ar"] else None
        sw, sh = en.width + 90, en.height + 40
        im = Image.new("RGBA", (max(sw, (ar.width + 100) if ar is not None else 0) + 80,
                                sh + (ar.height + 30 if ar is not None else 0) + 100), (0, 0, 0, 0))
        cx = im.width // 2
        st = _rounded((sw, sh), 30, YELLOW + (255,))
        ImageDraw.Draw(st).rounded_rectangle([3, 3, sw - 4, sh - 4], 28, outline=INK, width=6)
        st.alpha_composite(en, ((sw - en.width) // 2, (sh - en.height) // 2 - 4))
        st = st.rotate(3, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(_shadow_box(im.size, (cx - sw // 2, 50, cx + sw // 2, 50 + sh), 30, 14, 140, 6))
        im.alpha_composite(st, (cx - st.width // 2, 40 - (st.height - sh) // 2))
        if ar is not None:
            pw, ph = ar.width + 70, ar.height + 14
            pill = _rounded((pw, ph), ph // 2, (0, 0, 0, 255))
            pill.alpha_composite(ar, ((pw - ar.width) // 2, (ph - ar.height) // 2))
            pill = pill.rotate(-2, expand=True, resample=Image.BICUBIC)
            im.alpha_composite(pill, (cx - pill.width // 2, 40 + sh + 6))
        return im

    def _card_clip(self, gi, g, n):
        """paper: a newspaper clipping with a strip of tape: No. n · the English (serif) · the Arabic (naskh)."""
        L = self.L
        cw = 820
        label = _text(f"VOCABULARY  ·  No. {gi + 1}", 24, self.accent, "Bold", MONT)
        en = _fit_text(g["text"], 92, INK, cw - 90, "Bold", PLAYFAIR)
        ar = _ar_fit(g["ar"], 80, self.accent, AMIRI, cw - 90) if g["ar"] else None
        ch = 46 + label.height + en.height + (16 + ar.height if ar is not None else 0) + 34
        arr = np.empty((ch, cw, 4), np.float32)
        arr[..., :3] = L["card_bg"]
        arr[..., 3] = 255
        arr[..., :3] += _noise((cw, ch), 4.0, gi + 7)[..., None]
        paper = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
        d = ImageDraw.Draw(paper)
        d.rectangle([14, 14, cw - 15, ch - 15], outline=(40, 36, 32), width=2)
        y = 40
        paper.alpha_composite(label, ((cw - label.width) // 2, y))
        y += label.height + 2
        d.line([(cw / 2 - 150, y), (cw / 2 + 150, y)], fill=(40, 36, 32), width=2)
        y += 6
        paper.alpha_composite(en, ((cw - en.width) // 2, y))
        y += en.height + 6
        if ar is not None:
            paper.alpha_composite(ar, ((cw - ar.width) // 2, y))
        im = Image.new("RGBA", (cw + 80, ch + 120), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (40, 66, 40 + cw, 66 + ch), 2, 14, 110, 0))
        im.alpha_composite(paper, (40, 60))
        tape = Image.new("RGBA", (200, 52), (236, 226, 190, 190)).rotate(-4, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(tape, ((im.width - tape.width) // 2, 34))
        return im.rotate(-1.4 if gi % 2 == 0 else 1.4, expand=True, resample=Image.BICUBIC)

    def _draw_card(self, frame, t, a):
        kind = self.L["card"]
        for c in self.cards:
            if not (c["t0"] - 0.05 <= t < c["t1"] + 0.25):
                continue
            tin = t - c["t0"]
            out = _ease((t - c["t1"]) / 0.25) if t >= c["t1"] else 0.0
            al = min(1.0, max(0.0, tin / 0.15)) * (1 - out) * a
            if al <= 0:
                continue
            im = c["im"]
            if kind == "bar":      # slides in from the left, out to the left
                k = _ease(tin / 0.35)
                x0 = (W - im.width) // 2
                _comp(frame, _fade(im, al), int(-im.width + (x0 + im.width) * k - out * 120), self.card_y)
                continue
            if kind == "sticker":
                im = _scaled(im, 0.6 + 0.4 * _back(tin / 0.32))
                dy = 0
            elif kind == "clip":   # drops onto the page
                k = _ease(tin / 0.4)
                im = _scaled(im, 1.12 - 0.12 * k)
                dy = -int((1 - k) * 30)
            else:
                im = _scaled(im, 0.82 + 0.18 * _back(tin / 0.42))
                dy = 0
            x = (W - im.width) // 2
            y = self.card_y + (c["im"].height - im.height) // 2 + dy + int(out * 40)
            _comp(frame, _fade(im, al), x, y)

    # ---------------------------------------------------------- tv ticker
    def _layout_ticker(self):
        parts = []
        for g in self.groups:
            parts.append(_text(g["text"].upper(), 34, WHITE, "SemiBold", OSWALD))
            if g["ar"]:
                parts.append(_ar_fit(g["ar"], 34, YELLOW, self.L["ar_font"], 600))
            parts.append(_text("•", 34, self.accent, "Bold", OSWALD))
        h = max(p.height for p in parts) if parts else 40
        w = sum(p.width + 18 for p in parts) or 1
        strip = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = 0
        for p in parts:
            strip.alpha_composite(p, (x, (h - p.height) // 2))
            x += p.width + 18
        self.ticker = strip
        self.ticker_lbl = _text("TODAY'S WORDS", 30, WHITE, "Bold", OSWALD)
        self.ticker_y = TICKER_Y

    def _draw_ticker(self, frame, t, a):
        if not self.groups:
            return
        y, h = self.ticker_y, 64
        lw = self.ticker_lbl.width + 30
        bar = Image.new("RGBA", (W, h), (8, 12, 26, int(240 * a)))
        x = lw + 20 - int((t * 110) % self.ticker.width)
        while x < W:
            _comp(bar, _fade(self.ticker, a), x, (h - self.ticker.height) // 2)
            x += self.ticker.width
        ImageDraw.Draw(bar).rectangle([0, 0, lw, h], fill=self.accent + (int(255 * a),))
        _comp(bar, _fade(self.ticker_lbl, a), 15, (h - self.ticker_lbl.height) // 2)
        frame.alpha_composite(bar, (0, y))

    # ---------------------------------------------------------- ending
    def _layout_ending(self):
        L = self.L
        rows = [(g["text"], g["ar"]) for g in self.groups]
        n = len(rows)
        cw = 900
        row_h = max(84, min(124, int(880 / max(1, n))))
        es = int(row_h * 0.44)
        tf = L["end_font"]
        title = _fit_text(("GLOSSARY" if L["bg"] == "paper" else self.ending_title.upper()), 46, INK, cw - 100,
                          "Black" if tf == MONT else "Bold", tf)
        sub = _text(f"{n} word{'s' if n != 1 else ''} from this news", 28, L["end_sub"], "SemiBold")
        top = 54 + title.height + sub.height + 26
        ch = top + n * row_h + 40
        r = 4 if L["bg"] == "paper" else 40
        card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        card.alpha_composite(_shadow_box(card.size, (40, 50, 40 + cw, 50 + ch), r, 24, 140, 0))
        card.alpha_composite(_rounded((cw, ch), r, L["end_bg"] + (255,)), (40, 40))
        card.alpha_composite(Image.new("RGBA", (cw - 2 * r, 8), self.accent + (255,)), (40 + r, 40))
        card.alpha_composite(title, (40 + (cw - title.width) // 2, 40 + 40))
        card.alpha_composite(sub, (40 + (cw - sub.width) // 2, 40 + 40 + title.height - 6))
        self.end_card = card
        self.end_rows = []
        for k, (en, ar) in enumerate(rows):
            rim = Image.new("RGBA", (cw - 60, row_h - 14), (0, 0, 0, 0))
            rim.alpha_composite(_rounded(rim.size, 22 if r > 4 else 3, L["end_row"] + (255,)))
            num = _rounded((row_h - 44, row_h - 44), (row_h - 44) // 2, self.accent + (255,))
            nt = _text(str(k + 1), int(row_h * 0.32), WHITE, "Black")
            num.alpha_composite(nt, ((num.width - nt.width) // 2, (num.height - nt.height) // 2 - 2))
            rim.alpha_composite(num, (14, (rim.height - num.height) // 2))
            half = (rim.width - num.width - 60) // 2
            et = _fit_text(en, es, L["end_en"], half, "ExtraBold" if tf == MONT else "Bold", tf, 22)
            rim.alpha_composite(et, (num.width + 30, (rim.height - et.height) // 2 - 2))
            if ar:
                at = _ar_fit(ar, int(es * 0.95), L["end_ar"], L["ar_font"], half, 22)
                rim.alpha_composite(at, (rim.width - at.width - 20, (rim.height - at.height) // 2))
            self.end_rows.append((rim, 40 + 30, 40 + top + k * row_h))
        self.end_pos = ((W - card.width) // 2, max(140, (SAFE_BOTTOM - card.height) // 2 + 30))
        col = WHITE if self.vertical else L["end_text"]
        self.end_handle = _text(self.handle, 34, col, "Bold") if self.handle else None
        self.end_cta = _fit_text(self.cta, 32, col, 900, "SemiBold") if self.cta else None

    def _draw_ending(self, frame, te):
        k = _back((te - 0.25) / 0.55)
        if k <= 0:
            return
        card = self.end_card.copy()
        for n, (rim, rx, ry) in enumerate(self.end_rows):
            kk = _ease((te - 0.55 - 0.16 * n) / 0.35)
            if kk > 0:
                _comp(card, _fade(rim, kk), rx + int((1 - kk) * 60), ry)
        im = _scaled(card, 0.86 + 0.14 * k)
        x, y = self.end_pos
        x += (card.width - im.width) // 2
        y += (card.height - im.height) // 2 + int((1 - min(1.0, k)) * 80)
        _comp(frame, _fade(im, min(1.0, (te - 0.25) / 0.25)), x, y)
        yb = self.end_pos[1] + card.height + 10
        nr = len(self.end_rows)
        for im2, delay in ((self.end_cta, 0.9 + 0.16 * nr), (self.end_handle, 1.1 + 0.16 * nr)):
            if im2 is None:
                continue
            kk = _ease((te - delay) / 0.4)
            if kk > 0:
                _comp(frame, _fade(im2, kk), (W - im2.width) // 2, yb + int((1 - kk) * 20))
            yb += im2.height + 6

    # -------------------------------------------------------------- per frame
    def _video_frame(self, t):
        if self.dec is None:
            return self._placeholder()
        idx = int(round(max(0.0, min(t, self.E) - LEAD) * self.fps))
        idx = min(idx, max(0, int(self.clip * self.fps) - 1))
        return self.dec.frame(idx)

    def _placeholder(self):
        if not hasattr(self, "_ph"):
            g = np.linspace(0, 1, self.vsize[1])[:, None, None]
            arr = (np.array([30, 36, 52]) * (1 - g) + np.array([12, 14, 22]) * g)
            arr = np.broadcast_to(arr, (self.vsize[1], self.vsize[0], 3)).astype(np.uint8)
            im = Image.fromarray(arr, "RGB")
            msg = _text("Upload a video", 44, (200, 205, 215), "Bold")
            im.paste(msg, ((im.width - msg.width) // 2, (im.height - msg.height) // 2), msg)
            self._ph = im
        return self._ph

    def _background(self, vf, end_p):
        if self.vertical:
            frame = Image.new("RGB", (W, H), (0, 0, 0))
            frame.paste(vf, self.vpos)
            frame = frame.convert("RGBA")
            if end_p > 0:
                frame = frame.filter(ImageFilter.GaussianBlur(28 * end_p))
            return frame
        if self.static_bg is not None:
            return self.static_bg.copy()
        k = max(W / vf.width, H / vf.height)
        sw, sh = max(1, int(vf.width * k / 16)), max(1, int(vf.height * k / 16))
        small = vf.resize((sw, sh), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.2))
        big = small.resize((int(sw * 16), int(sh * 16)), Image.BILINEAR)
        x0, y0 = (big.width - W) // 2, (big.height - H) // 2
        return big.crop((x0, y0, x0 + W, y0 + H)).convert("RGBA")

    def render(self, t):
        vf = self._video_frame(t)
        end_p = _ease((t - self.E) / 0.6) if self.ending_on else 0.0
        frame = self._background(vf, end_p)
        if self.shade is not None:
            frame.alpha_composite(self.shade)
        if not self.vertical:
            self._draw_panel(frame, vf, t, end_p)
        if end_p > 0:
            dark = self.static_bg is None or self.vertical
            veil = (6, 8, 14, int(150 * end_p)) if dark else (250, 249, 246, int(170 * end_p))
            frame.alpha_composite(Image.new("RGBA", (W, H), veil))
        if end_p < 1:
            self._draw_header(frame, t, 1 - end_p)
            self._draw_captions(frame, t, 1 - end_p)
            self._draw_card(frame, t, 1 - end_p)
            if self.L["ticker"]:
                self._draw_ticker(frame, t, 1 - end_p)
        if self.ending_on and t >= self.E:
            self._draw_ending(frame, t - self.E)
        if t > self.dur - 0.35:  # fade out
            k = (t - (self.dur - 0.35)) / 0.35
            frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * min(1, k)))))
        return frame.convert("RGB")

    def _draw_panel(self, frame, vf, t, end_p):
        x, y = self.vpos
        a = 1 - end_p
        if a <= 0:
            return
        _comp(frame, _fade(self.shadow, a), x - 40, y - 40)
        im = vf.convert("RGBA")
        im.putalpha(self.mask if a >= 0.999 else self.mask.point(lambda v: int(v * a)))
        frame.alpha_composite(im, (x, y))
        frame.alpha_composite(_fade(self.rim, a), (x, y))
        p = max(0.0, min(1.0, (t - LEAD) / self.clip))      # progress line under the panel
        bar_y = y + self.vsize[1] + 18
        tr = self.L["track"]
        d = ImageDraw.Draw(frame)
        d.rounded_rectangle([x, bar_y, x + self.vsize[0], bar_y + 6], 3, fill=tr[:3] + (int(tr[3] * a),))
        if p > 0:
            d.rounded_rectangle([x, bar_y, x + max(6, int(self.vsize[0] * p)), bar_y + 6], 3,
                                fill=self.accent + (int(255 * a),))

    def _draw_header(self, frame, t, a):
        L = self.L
        k = _ease(t / 0.5)
        if k <= 0:
            return
        y, dy, al = self.head_y, int((1 - k) * -30), a * k
        d = ImageDraw.Draw(frame)
        if L["header"] == "masthead":   # newspaper: name between rules, a dateline, then the headline centred
            big = _text(self.label or "ENGLISH IN NEWS", 64, INK, "Black", PLAYFAIR)
            _comp(frame, _fade(big, al), (W - big.width) // 2, y + dy - 6)
            yl = y + dy + big.height + 4
            rule = (30, 28, 26, int(255 * al))
            d.line([(60, yl), (W - 60, yl)], fill=rule, width=3)
            d.line([(60, yl + 7), (W - 60, yl + 7)], fill=rule, width=1)
            bits = [b for b in (self.brand_name, self.tag) if b]
            if bits:
                line = _text("  ·  ".join(bits), 22, (90, 84, 76), "Bold")
                _comp(frame, _fade(line, al), (W - line.width) // 2, yl + 12)
            d.line([(60, yl + 52), (W - 60, yl + 52)], fill=rule, width=1)
            hy = y + 150
            for li, im in enumerate(self.head_lines):
                kk = _ease((t - 0.12 - 0.08 * li) / 0.5)
                if kk > 0:
                    _comp(frame, _fade(im, a * kk), (W - im.width) // 2, hy + int((1 - kk) * 16))
                hy += self.head_lh
            return
        x = 70
        if self.logo is not None:
            _comp(frame, _fade(self.logo, al), x - 10, y + dy - 10)
            tx = x + self.logo.width + 6
        else:
            tx = x
        if self.brand_im is not None:
            _comp(frame, _fade(self.brand_im, al), tx, y + dy + 6)
        if self.label_im is not None:
            _comp(frame, _fade(self.label_im, al * 0.85), tx, y + dy + 44)
        if self.tag_im is not None:
            pulse = 0.65 + 0.35 * math.sin(t * 5.5)
            tag = self.tag_im.copy()
            cy = tag.height // 2
            ImageDraw.Draw(tag).ellipse([12, cy - 6, 24, cy + 6], fill=(255, 255, 255, int(255 * pulse)))
            _comp(frame, _fade(tag, al), W - 70 - tag.width, y + dy + 26)
        hy = y + 120
        if L["header"] == "box" and self.head_lines:   # tv: the headline on a dark box with an accent edge
            kk = _ease((t - 0.1) / 0.45)
            bh = self.head_lh * len(self.head_lines) + 30
            bw = int((W - 80) * kk)
            if bw > 0:
                d.rectangle([40, hy - 6, 40 + bw, hy - 6 + bh], fill=(8, 12, 26, int(235 * a)))
                d.rectangle([40, hy - 6, 52, hy - 6 + bh], fill=self.accent + (int(255 * a),))
            hy += 8
            for li, im in enumerate(self.head_lines):
                k2 = _ease((t - 0.25 - 0.08 * li) / 0.4)
                if k2 > 0:
                    _comp(frame, _fade(im, a * k2), 74, hy - 8)
                hy += self.head_lh
            return
        top = hy
        for li, im in enumerate(self.head_lines):
            kk = _ease((t - 0.12 - 0.08 * li) / 0.5)
            if kk > 0:
                _comp(frame, _fade(im, a * kk), 64 + int((1 - kk) * 40), hy - 8)
            hy += self.head_lh
        if self.head_lines:   # an accent bar left of the headline
            kk = _ease((t - 0.1) / 0.45)
            d.rounded_rectangle([44, top + 4, 52, top + 4 + int((hy - top - 14) * kk)], 4,
                                fill=self.accent + (int(255 * a),))

    # -------------------------------------------------------------- sound
    def sound(self, mx):
        if self.path and self.has_audio:
            try:
                a = load_audio(self.path)
            except Exception:
                a = None
            if a is not None and len(a):
                seg = a[int(self.trim0 * SR):int((self.trim0 + self.clip) * SR)] * self.video_gain
                f = min(len(seg) // 4, int(0.02 * SR))
                if f > 1:
                    ramp = np.linspace(0, 1, f)[:, None]
                    seg[:f] *= ramp
                    seg[-f:] *= ramp[::-1]
                at = int(LEAD * SR)
                n = min(len(seg), mx.n - at)
                if n > 0:
                    mx.voice[at:at + n] += seg[:n]
                    mx.has_voice = True
        sig, pan = mx.whoosh(0.5)
        mx.add(0.02, sig, 0.08, pan)
        for c in self.cards:
            mx.add(c["t0"], mx.pop(), 0.10)
        if self.ending_on:
            sig, pan = mx.whoosh(0.7)
            mx.add(self.E, sig, 0.10, pan)
            mx.add(self.E + 0.3, mx.chime(), 0.16)
            for n in range(len(self.end_rows)):
                mx.add(self.E + 0.55 + 0.16 * n, mx.pop(), 0.06)
