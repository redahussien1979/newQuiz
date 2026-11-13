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
CARD_MIN, CARD_HOLD = 1.0, 4.2   # a word card stays at least / at most this long (s): it gives way to the next
                                 # key word's card, but only after CARD_MIN
CARD_LAG = 1.0                   # a card may come at most this late after its word (else it is left out)
CARD_OUT = 0.25                  # its exit
SAFE_BOTTOM = 1536
CAP_MAX_W = 860            # a subtitle line (centred: clear of the Shorts buttons on the right)
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
_probed = {}


def _hms(m):
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def probe(path):
    """(width, height, duration s, has audio) of a video as FFmpeg delivers its frames (phone rotation applied).
    Cached per file and modification time (the preview asks on every change)."""
    key = (os.path.abspath(path), os.path.getmtime(path), os.path.getsize(path))
    if key in _probed:
        return _probed[key]
    p = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", path, "-frames:v", "1", "-f", "image2pipe",
                        "-vcodec", "png", "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"Could not read the video: {os.path.basename(str(path))} (is it a video file?)")
    w, h = Image.open(io.BytesIO(p.stdout)).size
    info = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True).stderr.decode(errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info)
    dur = _hms(m) if m else 0.0
    if dur <= 0:  # no duration in the header (e.g. a webm recorded in a browser): read the whole file once
        full = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null",
                               "-"], capture_output=True).stderr.decode(errors="ignore")
        times = re.findall(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)", full)
        dur = _hms(re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", ":".join(times[-1]))) if times else 0.0
    if dur <= 0:
        raise RuntimeError(f"Could not find the length of the video: {os.path.basename(str(path))}")
    out = (w, h, dur, bool(re.search(r"Stream #.*Audio:", info)))
    _probed[key] = out
    return out


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


def _tight_text(txt, size, col, max_w, weight="Bold", path=MONT, min_size=26, pad=8):
    """_fit_text cropped to the font's letter band (top of the capitals / accents to the bottom of g, j, y) + pad:
    the same height for every word at a size, without the font's empty line spacing."""
    f = get_font(int(size), weight, path)
    if f.getlength(txt) + 12 > max_w:
        size = max(min_size, int(size * max_w / (f.getlength(txt) + 12)))
        f = get_font(int(size), weight, path)
    im = _text(txt, size, col, weight, path)
    _, y0, _, y1 = f.getbbox("HÁÉgjpyQ|")
    return im.crop((0, max(0, 6 + y0 - pad), im.width, min(im.height, 6 + y1 + pad)))


def _ink_crop(im, pad=10):
    """An image cropped top and bottom to its ink + pad (Arabic: the font box is much taller than the letters)."""
    box = im.getchannel("A").getbbox()
    if not box:
        return im
    return im.crop((0, max(0, box[1] - pad), im.width, min(im.height, box[3] + pad)))


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
        self.ending_sub = " ".join(str(e.get("question") or "").split())  # optional line under the recap title
        self.silences = []

        # the source
        self.path = str(n.get("video") or "")
        self.trim0 = max(0.0, float(n.get("trim_start") or 0.0))
        if self.path and os.path.isfile(self.path):
            sw, sh, sdur, self.has_audio = probe(self.path)
        else:
            self.path, sw, sh, sdur, self.has_audio = "", 16, 9, 8.0, False
        if self.trim0 > sdur - 0.5:  # a start past the end of the video: use the whole video
            self.trim0 = 0.0
        end = float(n.get("trim_end") or 0.0)
        end = sdur if end <= self.trim0 + 0.5 or end > sdur else end
        self.clip = max(0.5, end - self.trim0)
        self.vertical = sh > sw * 1.05
        if self.vertical:   # fills the screen (cover)
            k = max(W / sw, H / sh)
            self.vsize = (int(round(sw * k)) // 2 * 2, int(round(sh * k)) // 2 * 2)
            self.vpos = ((W - self.vsize[0]) // 2, (H - self.vsize[1]) // 2)
        else:               # a framed panel under the headline (placed in _layout)
            pw = 1000           # at most 600 high (4:3, square): the subtitles + card need the room below
            ph = min(600, int(round(pw * sh / sw)))
            pw = min(pw, int(round(ph * sw / sh)))
            self.vsize = (pw // 2 * 2, ph // 2 * 2)
            self.vpos = ((W - self.vsize[0]) // 2, 360)

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
        self.dec = _Decoder(self.path, self.vsize, self.fps, self.trim0) if self.path else None

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
        if L["header"] == "masthead":  # the newspaper's name: the small line, else ENGLISH IN NEWS
            self.mast_im = _fit_text(self.label or "ENGLISH IN NEWS", 64, INK, 700, "Black", PLAYFAIR)

        self.head_y = 110
        self._layout_captions()
        self._layout_cards()
        self._place()
        if L["band"]:
            self.band_box = (0, int(self.cap_y + self.cap_box[0]), W, int(self.cap_y + self.cap_box[1]))
        self._layout_background()
        if not self.vertical:
            self._layout_panel()
        if L["ticker"]:
            self._layout_ticker()
        if self.ending_on:
            self._layout_ending()

    def _place(self):
        """Where the panel, the subtitles and the word card go, from their real heights: subtitles under the clip,
        the card under the subtitles, everything above the safe line (the tv card above its ticker). A landscape
        clip's panel only gets smaller when a tall card would not fit otherwise."""
        L = self.L
        limit = (TICKER_Y - 14) if L["card"] == "bar" else SAFE_BOTTOM - 6
        rt, rb = self.card_box                     # the cards' real top / bottom inside their images
        gap = 20 if self.cards else 0
        # the subtitle block's drawn rows relative to cap_y: letters + the marker / box around them (+ tv band)
        m = 30 if L["band"] else 16
        top_off = self.cap_band[0] - m
        bot_off = self.cap_lh * (L["max_lines"] - 1) + self.cap_band[1] + m
        cap_h = bot_off - top_off
        if self.vertical:   # subtitles in the middle-low part, the card under them
            self.cap_y = (960 if L["cap_mode"] == "pop" else 880) - top_off
        else:
            top = max(300, self.head_bottom + 36)
            cap_gap = 44             # under the panel's progress line
            room = limit - top - cap_gap - cap_h - gap - (rb - rt)
            pw, ph = self.vsize
            if ph > room:   # shrink the panel (same shape) so the card fits under the subtitles
                k = max(300, room) / ph
                self.vsize = (int(pw * k) // 2 * 2, int(ph * k) // 2 * 2)
            self.vpos = ((W - self.vsize[0]) // 2, top)
            self.cap_y = top + self.vsize[1] + cap_gap - top_off
        self.card_y = self.cap_y + bot_off + gap - rt
        if L["card"] == "bar":       # the lower third sits on the ticker
            self.card_y = limit - rb
        if self.card_y + rb > limit:  # never under the safe line: lift the card, and the subtitles with it
            self.card_y = limit - rb
        self.cap_y = min(self.cap_y, self.card_y + rt - gap - bot_off)
        self.cap_box = (top_off, bot_off)

    def _layout_headline(self):
        L = self.L
        size = 60 if L["head_font"] == ANTON else (56 if L["header"] == "masthead" else 52)
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
        self.head_lh = int(size * (1.12 if L["head_font"] in (ANTON, OSWALD) else 1.2))
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
        self.cap_lh = lh
        st = L["cap_stroke"]
        _, y0, _, y1 = f.getbbox("HÁÉQ|" if L["upper"] else "HÁÉgjpyQ|")
        self.cap_band = (6 + st + y0 - st, 6 + st + y1 + st)   # the letters' rows inside a subtitle word image

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
        b0, b1 = self.cap_band
        items = page["items"]
        if fit < 1:   # move the words towards the centre as the whole line shrinks
            items = [dict(it, x=it["x"] + (W / 2 + (it["x"] + it["w"] / 2 - W / 2) * fit - it["x"] - it["w"] / 2))
                     for it in items]
        if L["key_stroke"]:   # pop: ONE accent box springs up behind each key word / phrase (its spoken part)
            spans = {}
            for it in items:
                gi, w = self.key_of.get(it["i"]), self.words[it["i"]]
                if gi is not None and t >= w["s"]:
                    cx, half = it["x"] + it["w"] / 2, it["w"] * pscale / 2   # the word as it is drawn
                    sp = spans.setdefault((gi, it["line"]), [cx - half, cx + half, w["s"], 0])
                    sp[0], sp[1] = min(sp[0], cx - half), max(sp[1], cx + half)
            for (gi, li), (x0, x1, ts, _) in spans.items():
                self._pop_box(frame, x0, x1, base_y + li * lh, _ease((t - ts) / 0.18) * ka, pscale)
        for it in items:
            w = self.words[it["i"]]
            y = base_y + it["line"] * lh
            gi = self.key_of.get(it["i"])
            spoken = t >= w["s"]
            speaking = w["s"] <= t < w["e"] + 0.05
            if gi is not None and spoken:   # the marker swipes in behind the key word
                p = _ease((t - w["s"]) / max(0.12, min(0.35, w["e"] - w["s"])))
                im = it["key"] if p > 0.5 else it["norm"]
                sc = pscale * (1.0 + 0.08 * _spring(t - self.groups[gi]["t0"]))
                if not L["key_stroke"]:     # a marker swipes in behind the word
                    x0 = it["x"] - 10
                    d.rounded_rectangle([x0, y + b0 - 9, x0 + (it["w"] + 20) * p, y + b1 + 9], 12,
                                        fill=L["mark"] + (int(255 * ka),))
                self._put_word(frame, im, it, y, sc, ka)
                continue
            im, alpha, sc = it["norm"], (ka if spoken else ka * L["dim"]), pscale
            if speaking:
                im = it["speak"]
                if L["speak"] == "pill":
                    d.rounded_rectangle([it["x"] - 10, y + b0 - 7, it["x"] + it["w"] + 10, y + b1 + 7], 12,
                                        fill=self.accent + (int(235 * ka),))
                else:
                    sc *= 1.0 + 0.07 * math.sin(math.pi * min(1.0, (t - w["s"]) / 0.25))
                    if L["bg"] == "paper":  # newspaper: the spoken word is also underlined
                        d.line([(it["x"], y + b1 + 4), (it["x"] + it["w"], y + b1 + 4)], fill=self.accent,
                               width=4)
            elif gi is not None:  # a key word not spoken yet: underlined
                d.rounded_rectangle([it["x"], y + b1 + 3, it["x"] + it["w"], y + b1 + 8], 3,
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

    def _pop_box(self, frame, x0, x1, y, k, sc):
        """The pop look's accent box behind a key word / phrase spanning x0..x1 of a line (k: 0 -> 1 as it pops)."""
        if k <= 0:
            return
        b0, b1 = self.cap_band
        box = _rounded((max(2, int(x1 - x0 + 30 * sc)), max(2, int((b1 - b0 + 26) * sc))), 16, self.accent + (255,))
        box = _scaled(box.rotate(-2.0, expand=True, resample=Image.BICUBIC), 0.7 + 0.3 * _back(k))
        cx, cy = (x0 + x1) / 2, y + (b0 + b1) / 2
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
        free = 0.0                 # when the card before has fully gone (cards never overlap: they queue)
        for gi, g in enumerate(self.groups):
            t0 = max(g["t0"], free)
            if t0 - g["t0"] > CARD_LAG or t0 > self.E - 0.6:
                continue  # key words too close together / too late: this one is marked in the subtitles + recap
            nxt = self.groups[gi + 1]["t0"] if gi + 1 < n else self.E + 0.3
            t1 = min(max(nxt - CARD_OUT - 0.02, t0 + CARD_MIN), t0 + CARD_HOLD, self.E + 0.2)
            free = t1 + CARD_OUT + 0.02
            self.cards.append(dict(im=make(gi, g, n), t0=t0, t1=t1, gi=gi))
        # the solid card only (its soft shadow is at most 140 opaque)
        boxes = [c["im"].getchannel("A").point(lambda v: 255 if v > 200 else 0).getbbox() for c in self.cards]
        boxes = [bx for bx in boxes if bx]
        self.card_box = (min(bx[1] for bx in boxes), max(bx[3] for bx in boxes)) if boxes else (0, 0)

    def _card_pop(self, gi, g, n):
        """breaking / studio: a rounded card, KEY WORD n/N, the English, a short line, the Arabic."""
        L = self.L
        cw = 860
        label = _tight_text(f"KEY WORD  {gi + 1}/{n}", 26, L["card_label"], cw, "Black", pad=2)
        en = _tight_text(g["text"], 80, L["card_en"], cw - 80, L["card_weight"], L["card_font"], pad=6)
        ar = _ink_crop(_ar_fit(g["ar"], 68, L["card_ar"], L["ar_font"], cw - 80), 8) if g["ar"] else None
        ch = 30 + label.height + 12 + en.height + (30 + ar.height if ar is not None else 0) + 30
        card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        card.alpha_composite(_shadow_box(card.size, (40, 48, 40 + cw, 48 + ch), 36, 20, 120, 0))
        body = _rounded((cw, ch), 36, L["card_bg"] + (255,))
        body.paste(Image.new("RGBA", (cw, 10), self.accent + (255,)), (0, 0),
                   _round_mask((cw, 40), 36).crop((0, 0, cw, 10)))
        card.alpha_composite(body, (40, 40))
        y = 40 + 30
        card.alpha_composite(label, (40 + (cw - label.width) // 2, y))
        y += label.height + 12
        card.alpha_composite(en, (40 + (cw - en.width) // 2, y))
        y += en.height
        if ar is not None:
            line = (225, 228, 232) if L["card_bg"] == WHITE else (70, 74, 84)
            ImageDraw.Draw(card).line([(40 + cw / 2 - 60, y + 15), (40 + cw / 2 + 60, y + 15)], fill=line, width=3)
            y += 30
            card.alpha_composite(ar, (40 + (cw - ar.width) // 2, y))
        return card

    def _card_bar(self, gi, g, n):
        """tv: a lower third — accent block (KEY WORD n/N), white bar with the English, dark bar with the Arabic."""
        L = self.L
        bw = 960
        tag = _text("KEY WORD", 26, WHITE, "Bold", OSWALD)
        num = _text(f"{gi + 1}/{n}", 40, WHITE, "Bold", OSWALD)
        en = _tight_text(g["text"].upper(), 74, INK, bw - 260, L["card_weight"], OSWALD, pad=4)
        ar = _ink_crop(_ar_fit(g["ar"], 54, WHITE, L["ar_font"], bw - 260), 13) if g["ar"] else None
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
        en = _tight_text(g["text"].upper(), 96, INK, 760, "Regular", ANTON, pad=4)
        ar = _ink_crop(_ar_fit(g["ar"], 64, WHITE, L["ar_font"], 720), 10) if g["ar"] else None
        sw, sh = en.width + 90, en.height + 44
        im = Image.new("RGBA", (max(sw, (ar.width + 100) if ar is not None else 0) + 80,
                                sh + (ar.height + 30 if ar is not None else 0) + 100), (0, 0, 0, 0))
        cx = im.width // 2
        st = _rounded((sw, sh), 30, YELLOW + (255,))
        ImageDraw.Draw(st).rounded_rectangle([3, 3, sw - 4, sh - 4], 28, outline=INK, width=6)
        st.alpha_composite(en, ((sw - en.width) // 2, (sh - en.height) // 2))
        st = st.rotate(3, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(_shadow_box(im.size, (cx - sw // 2, 50, cx + sw // 2, 50 + sh), 30, 14, 140, 6))
        im.alpha_composite(st, (cx - st.width // 2, 40 - (st.height - sh) // 2))
        if ar is not None:
            pw, ph = ar.width + 70, ar.height + 20
            pill = _rounded((pw, ph), ph // 2, (0, 0, 0, 255))
            pill.alpha_composite(ar, ((pw - ar.width) // 2, (ph - ar.height) // 2))
            pill = pill.rotate(-2, expand=True, resample=Image.BICUBIC)
            im.alpha_composite(pill, (cx - pill.width // 2, 40 + sh + 6))
        return im

    def _card_clip(self, gi, g, n):
        """paper: a newspaper clipping with a strip of tape: No. n · the English (serif) · the Arabic (naskh)."""
        L = self.L
        cw = 780
        label = _tight_text(f"VOCABULARY  ·  No. {gi + 1}", 24, self.accent, cw, "Bold", MONT, pad=2)
        en = _tight_text(g["text"], 84, INK, cw - 90, "Bold", PLAYFAIR, pad=6)
        ar = _ink_crop(_ar_fit(g["ar"], 72, self.accent, AMIRI, cw - 90), 8) if g["ar"] else None
        ch = 36 + label.height + 18 + en.height + (14 + ar.height if ar is not None else 0) + 32
        arr = np.empty((ch, cw, 4), np.float32)
        arr[..., :3] = L["card_bg"]
        arr[..., 3] = 255
        arr[..., :3] += _noise((cw, ch), 4.0, gi + 7)[..., None]
        paper = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
        d = ImageDraw.Draw(paper)
        d.rectangle([14, 14, cw - 15, ch - 15], outline=(40, 36, 32), width=2)
        y = 36
        paper.alpha_composite(label, ((cw - label.width) // 2, y))
        y += label.height + 8
        d.line([(cw / 2 - 150, y), (cw / 2 + 150, y)], fill=(40, 36, 32), width=2)
        y += 10
        paper.alpha_composite(en, ((cw - en.width) // 2, y))
        y += en.height + 14
        if ar is not None:
            paper.alpha_composite(ar, ((cw - ar.width) // 2, y))
        im = Image.new("RGBA", (cw + 80, ch + 120), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (40, 66, 40 + cw, 66 + ch), 2, 14, 110, 0))
        im.alpha_composite(paper, (40, 60))
        tape = Image.new("RGBA", (200, 52), (236, 226, 190, 190)).rotate(-4, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(tape, ((im.width - tape.width) // 2, 34))
        return im.rotate(-1.2 if gi % 2 == 0 else 1.2, expand=True, resample=Image.BICUBIC)

    def _draw_card(self, frame, t, a):
        kind = self.L["card"]
        for c in self.cards:
            if not (c["t0"] <= t < c["t1"] + CARD_OUT):
                continue
            tin = t - c["t0"]
            out = _ease((t - c["t1"]) / CARD_OUT) if t >= c["t1"] else 0.0
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
        sub = _fit_text(self.ending_sub or f"{n} word{'s' if n != 1 else ''} from this news", 28, L["end_sub"],
                        cw - 100, "SemiBold")
        top = 54 + title.height + sub.height + 26
        room = SAFE_BOTTOM - 150 - 140 - top - 40 - 90   # rows must leave room for the CTA + handle below the card
        cols = 2 if n > 8 else 1   # many words: two columns, each word over its Arabic (big enough on a phone)
        per = -(-n // cols)
        if cols == 2:
            row_h = max(70, min(104, room // max(1, per)))
            es = int(row_h * 0.36)
        elif n * row_h > room:
            row_h = max(60, room // max(1, n))
            es = int(row_h * 0.44)
        ch = top + per * row_h + 40
        r = 4 if L["bg"] == "paper" else 40
        card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        card.alpha_composite(_shadow_box(card.size, (40, 50, 40 + cw, 50 + ch), r, 24, 140, 0))
        card.alpha_composite(_rounded((cw, ch), r, L["end_bg"] + (255,)), (40, 40))
        card.alpha_composite(Image.new("RGBA", (cw - 2 * r, 8), self.accent + (255,)), (40 + r, 40))
        card.alpha_composite(title, (40 + (cw - title.width) // 2, 40 + 40))
        card.alpha_composite(sub, (40 + (cw - sub.width) // 2, 40 + 40 + title.height - 6))
        self.end_card = card
        self.end_rows = []
        en_weight = "ExtraBold" if tf == MONT else "Bold"
        rw = (cw - 60 - (20 if cols == 2 else 0)) // cols
        for k, (en, ar) in enumerate(rows):
            col, row = divmod(k, per)
            rim = Image.new("RGBA", (rw, row_h - 14), (0, 0, 0, 0))
            rim.alpha_composite(_rounded(rim.size, 22 if r > 4 else 3, L["end_row"] + (255,)))
            d = min(row_h - 44, 52)
            num = _rounded((d, d), d // 2, self.accent + (255,))
            nt = _text(str(k + 1), int(d * 0.55), WHITE, "Black")
            num.alpha_composite(nt, ((num.width - nt.width) // 2, (num.height - nt.height) // 2 - 2))
            rim.alpha_composite(num, (12, (rim.height - num.height) // 2))
            tx = num.width + 24
            if cols == 2:   # the English over the Arabic (right-aligned)
                et = _fit_text(en, es, L["end_en"], rw - tx - 14, en_weight, tf, 20)
                at = _ar_fit(ar, int(es * 0.95), L["end_ar"], L["ar_font"], rw - tx - 14, 20) if ar else None
                hh = et.height - 14 + (at.height - 10 if at is not None else 0)
                y0 = (rim.height - hh) // 2 - 6
                rim.alpha_composite(et, (tx, y0))
                if at is not None:
                    rim.alpha_composite(at, (rw - at.width - 14, y0 + et.height - 18))
            else:
                half = (rw - tx - 40) // 2
                et = _fit_text(en, es, L["end_en"], half, en_weight, tf, 22)
                rim.alpha_composite(et, (tx, (rim.height - et.height) // 2 - 2))
                if ar:
                    at = _ar_fit(ar, int(es * 0.95), L["end_ar"], L["ar_font"], half, 22)
                    rim.alpha_composite(at, (rw - at.width - 20, (rim.height - at.height) // 2))
            self.end_rows.append((rim, 40 + 30 + col * (rw + 20), 40 + top + row * row_h))
        self.end_step = min(0.16, 1.6 / max(1, n))   # rows come in one after another (all within 1.6 s)
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
            kk = _ease((te - 0.55 - self.end_step * n) / 0.35)
            if kk > 0:
                _comp(card, _fade(rim, kk), rx + int((1 - kk) * 60), ry)
        im = _scaled(card, 0.86 + 0.14 * k)
        x, y = self.end_pos
        x += (card.width - im.width) // 2
        y += (card.height - im.height) // 2 + int((1 - min(1.0, k)) * 80)
        _comp(frame, _fade(im, min(1.0, (te - 0.25) / 0.25)), x, y)
        yb = self.end_pos[1] + card.height + 10
        nr = len(self.end_rows)
        for im2, delay in ((self.end_cta, 0.9 + self.end_step * nr), (self.end_handle, 1.1 + self.end_step * nr)):
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
            if end_p > 0:  # blurred at a quarter size (the same look, 16 x faster)
                small = frame.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7 * end_p))
                frame = small.resize((W, H), Image.BILINEAR)
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
            big = self.mast_im
            _comp(frame, _fade(big, al), (W - big.width) // 2, y + dy - 6)
            if self.logo is not None:   # the logo at the left of the masthead
                lg = _scaled(self.logo, 0.8)
                _comp(frame, _fade(lg, al), 50, y + dy + big.height // 2 - lg.height // 2 - 4)
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
                seg = a[int(self.trim0 * SR):int((self.trim0 + self.clip) * SR)].copy()
                peak = np.abs(seg).max() if len(seg) else 0.0
                seg = seg / (peak + 1e-9) * 0.9 * self.video_gain   # same level whatever the clip (like a voice)
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
                mx.add(self.E + 0.55 + self.end_step * n, mx.pop(), 0.06)
