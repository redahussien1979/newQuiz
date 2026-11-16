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
    notify     frosted glass over colour blobs; a key word drops in from the top as a phone notification
    podcast    dark studio, a waveform moving with the speech under the clip, lime karaoke, a key-word pill
    post       the clip inside a social post (logo, name, headline, actions); key words as pinned replies

Layout: a landscape / square video sits in a framed panel near the top; a vertical video fills the screen.
Subtitles and the word card stay inside the Shorts safe area (above y 1536). The source video is decoded by FFmpeg
as it is needed; render(t) depends only on t (frames are drawn on several processes, each with its own decoder, in
long runs of frames: `chunk`).
"""
import bisect
import hashlib
import io
import math
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..audio import SR
from ..core import H, ROOT, W, ffmpeg_exe, get_font
from .text import (_AR_PAD, DEFAULT_LOGO, _ar_fit, _ar_font_for, _ar_line, _comp, _fade, _groups, _shadow_box, _spring,
                   logo_badge, parse_words)

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
INTER = _lib("Inter", "Inter[opsz,wght].ttf")

LEAD = 0.7                  # the header comes in over the first frame before the clip plays
SPEED_MIN, SPEED_MAX = 0.5, 1.5
REP_MAX = 10                # a key word is replayed at most this many extra times
REP_PRE, REP_POST = 0.18, 0.15   # a replay starts this much before the key word and ends this much after it
REP_GAP = 0.45              # the held frame (with REPEAT k/n) before each replay
ENDING_LEN = 5.0            # the table recap
RECAP_CHOICES = [("🃏 Flashcards — new colours for every video", "flashcards"), ("📋 Table", "table")]
DEFAULT_RECAP = "flashcards"
# Flashcards: every video gets one of these colour sets (picked from the clip, so a video always keeps its own):
# the cards cycle through `cards`; text is dark or white by each card's brightness; `hi` = the Arabic on dark
# cards, `deep` = the Arabic on light cards and the progress ring.
PALETTES = [
    {"cards": ["#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF", "#8B4FD8"], "hi": "#FFF3B0", "deep": "#B5179E"},  # candy
    {"cards": ["#0B3954", "#087E8B", "#3C91E6", "#145C9E", "#1B998B"], "hi": "#FFE66D", "deep": "#087E8B"},  # ocean
    {"cards": ["#FF7B54", "#FFB26B", "#FFD56F", "#EA5455", "#F07B3F"], "hi": "#FFF6D6", "deep": "#B22222"},  # sunset
    {"cards": ["#FFFFFF"], "hi": "#FFD166", "deep": "#E41E30"},                                            # classic
    {"cards": ["#1E1E2E", "#24243A", "#1B1B2F", "#26263F", "#202036"], "hi": "#4CC9F0", "deep": "#F72585"},  # neon
    {"cards": ["#FFC8DD", "#BDE0FE", "#CDB4DB", "#A2D2FF", "#FFAFCC"], "hi": "#FFFFFF", "deep": "#7A1F5C"},  # pastel
    {"cards": ["#2D6A4F", "#40916C", "#1B4332", "#52B788", "#245C47"], "hi": "#D8F3DC", "deep": "#2D6A4F"},  # forest
    {"cards": ["#3A0CA3", "#480CA8", "#3F37C9", "#560BAD", "#4361EE"], "hi": "#FFD166", "deep": "#3A0CA3"},  # royal
    {"cards": ["#FF6F61", "#2E4057"], "hi": "#FFE5D9", "deep": "#C0392B"},                                 # coral & navy
    {"cards": ["#F4A261", "#E76F51", "#2A9D8F", "#264653", "#E9C46A"], "hi": "#FFF1C1", "deep": "#264653"},  # desert
    {"cards": ["#111111", "#FFD60A"], "hi": "#FFD60A", "deep": "#111111"},                                 # bold
    {"cards": ["#E0FBFC", "#C2DFE3", "#9DB4C0", "#5C6B73", "#253237"], "hi": "#E0FBFC", "deep": "#253237"},  # steel
]


def recap_len(kind, n):
    """How long the recap lasts (s) with n key words: the flashcards land one after another, then stay long enough
    to read them (≈ 0.45 s a word, at most 8 s in all)."""
    if kind == "table":
        return ENDING_LEN
    done = 0.5 + min(0.2, 2.0 / max(1, n)) * (n - 1) + 0.22
    return min(8.0, max(4.6, done + 1.0 + 0.45 * n))
CARD_MIN, CARD_HOLD = 1.0, 4.2   # a word card stays at least / at most this long (s): it gives way to the next
                                 # key word's card, but only after CARD_MIN
REC_MIN = 0.72                   # the recap's common text size may go down to this share of its full size
CARD_LAG = 1.0                   # a card may come at most this late after its word (else it is left out)
CARD_OUT = 0.25                  # its exit
SAFE_BOTTOM = 1536
CAP_MAX_W = 860            # a subtitle line (centred: clear of the Shorts buttons on the right)
POP_MAX_W = 820            # pop: the widest a line of huge words may be (1080 - 2 x 130)
NOTIFY_ROOM = 180          # notify: the header starts this much lower (the banner drops in above it)
WAVE_H = 76                # podcast: the waveform's height
POST_PAD, POST_FOOT = 34, 112   # post: the card's top padding / below the clip (progress line + actions row)
TICKER_Y = 1470            # the tv ticker (64 px high, ends at the safe-area line)
ACCENTS = {"red": (228, 30, 48), "blue": (28, 110, 230), "teal": (0, 150, 150), "orange": (240, 120, 20),
           "purple": (126, 64, 210)}
ACCENT_CHOICES = [("News red", "red"), ("Blue", "blue"), ("Teal", "teal"), ("Orange", "orange"),
                  ("Purple", "purple")]
YELLOW = (255, 214, 10)
LIME = (198, 255, 61)        # podcast
FEED_BLUE = (29, 155, 240)   # social post
VIOLET = (109, 40, 217)      # notification: the Arabic
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
    dark=None,                       # the page under the recap is dark (None: dark unless a light background)
    accent=None,                     # the look's own accent (None: the accent picked in the app)
    pill_col=None, pill_text=None,   # speak="pill": the pill's colour (None: accent) / the spoken word's colour
    head_bar=True, head_align="left",  # the accent bar left of the headline / headline left or centred
    wave=False,                      # podcast: a waveform that moves with the speech under the clip
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
LOOKS.update({
    # frosted glass over soft colour blobs; a key word drops in from the top like a phone notification
    "notify": dict(bg="glass", dark=True, head_font=INTER, head_weight="ExtraBold", head_bar=False, panel_r=44,
                   panel_rim=(255, 255, 255, 110), cap_font=INTER, cap_weight="Black", cap_size=64, cap_stroke=0,
                   dim=0.5, speak="pill", pill_col=WHITE, pill_text=INK, mark=(196, 181, 253), key_col=INK,
                   card="notify", card_font=INTER, card_weight="Black", card_ar=VIOLET, ar_font=TAJAWAL),
    # dark studio, the clip with a live waveform under it, lime karaoke subtitles, a key-word pill
    "podcast": dict(bg="dark", dark=True, accent=LIME, head_weight="Bold", head_col=(235, 238, 232), head_bar=False,
                    head_align="center", panel_r=40, panel_rim=(0, 0, 0, 0), track=(255, 255, 255, 40), wave=True,
                    cap_size=64, cap_stroke=0, dim=0.42, speak="color", speak_col=LIME, mark=LIME, key_col=INK,
                    card="podpill", card_ar=LIME, ar_font=TAJAWAL),
    # the clip inside a social post (logo, name, headline, actions); a key word comes in as a pinned reply
    "post": dict(bg="feed", dark=False, accent=FEED_BLUE, header="post", head_col=INK, head_font=INTER,
                 head_weight="SemiBold", panel_r=24, panel_rim=(0, 0, 0, 0), panel_shadow=0, track=(225, 229, 235, 255),
                 cap_font=INTER, cap_weight="Black", cap_size=64, cap_col=INK, cap_stroke=0, dim=0.35, speak="pill",
                 pill_col=FEED_BLUE, pill_text=WHITE, mark=(186, 225, 252), key_col=INK, card="reply",
                 card_font=INTER, card_weight="Black", card_ar=FEED_BLUE, ar_font=TAJAWAL, end_text=INK),
})
LOOK_CHOICES = [("💥 Pop (big words)", "pop"), ("🔴 Breaking (dark)", "breaking"), ("⚪ Studio (light)", "studio"),
                ("📺 TV broadcast", "tv"), ("📰 Newspaper", "paper"), ("🔔 Notification (glass)", "notify"),
                ("🎙️ Podcast clip (lime)", "podcast"), ("💬 Social post (blue)", "post")]
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
        "speed": 1.0,
        "ending_on": True,
        "recap_style": DEFAULT_RECAP,
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
            "for | 5.46 | 5.58", "people | 5.62 | 5.94", "most | 6.00 | 6.24", "at | 6.28 | 6.36 | at risk",
            "risk. | 6.40 | 6.86 | at risk | معرّضون للخطر"]),
    },
}


# ------------------------------------------------------------------ timing: speed + repeated key words
def _rep(v):
    """A repeat count from the words box: 0-10 extra replays."""
    try:
        return max(0, min(REP_MAX, int(float(str(v).strip() or 0))))
    except ValueError:
        return 0


def timing(n, sdur):
    """(trim start, clip length, speed, words, key words, segments) of a clip, from the news settings `n` and the
    video's length. Words / key words carry clip times (0 = the trim start). The video plays as a list of segments
    dict(o0, o1, c0, c1, kind, gi, k, n): its time o0..o1 shows the clip from c0 to c1 —
      lead    the first frame held while the header comes in
      play    the clip at `speed` (0.5-1: slower, the voice keeps its pitch)
      freeze  a held frame before a replay ("REPEAT k/n")
      replay  a key word said again: from just before it to just after it, as many times as its `rep`."""
    trim0 = max(0.0, float(n.get("trim_start") or 0.0))
    if trim0 > sdur - 0.5:  # a start past the end of the video: use the whole video
        trim0 = 0.0
    end = float(n.get("trim_end") or 0.0)
    end = sdur if end <= trim0 + 0.5 or end > sdur else end
    clip = max(0.5, end - trim0)
    try:
        speed = float(n.get("speed") or 1.0)
    except ValueError:
        speed = 1.0
    speed = max(SPEED_MIN, min(SPEED_MAX, speed))
    words = []
    for w in parse_words(n.get("words")):
        s0, e0 = w["s"] - trim0, w["e"] - trim0
        if e0 <= 0 or s0 >= clip:
            continue
        words.append(dict(w, s=max(0.0, s0), e=min(clip, e0)))
    groups = _groups(words)
    for g in groups:
        g["c0"], g["c1"] = words[g["i0"]]["s"], words[g["i1"]]["e"]
        g["rep"] = max((_rep(words[k].get("rep")) for k in range(g["i0"], g["i1"] + 1)), default=0)
    segs, o = [], 0.0

    def add(kind, c0, c1, dur, gi=None, k=0, cnt=0):
        nonlocal o
        if dur > 1e-6:
            segs.append(dict(o0=o, o1=o + dur, c0=c0, c1=c1, kind=kind, gi=gi, k=k, n=cnt))
            o += dur
    add("lead", 0.0, 0.0, LEAD)
    pos = 0.0
    for gi in sorted((gi for gi, g in enumerate(groups) if g["rep"]), key=lambda i: groups[i]["c1"]):
        g = groups[gi]
        cut = max(pos, min(clip, g["c1"] + REP_POST))
        add("play", pos, cut, (cut - pos) / speed)
        pos = cut
        a = max(0.0, g["c0"] - REP_PRE)
        if g["i0"] > 0:  # never from inside the word before (its subtitle page / highlight would flash)
            a = min(g["c0"], max(a, words[g["i0"] - 1]["e"] + 0.06))
        b = cut
        for k in range(1, g["rep"] + 1):
            add("freeze", a, a, REP_GAP, gi, k, g["rep"])
            add("replay", a, b, (b - a) / speed, gi, k, g["rep"])
    add("play", pos, clip, (clip - pos) / speed)
    return trim0, clip, speed, words, groups, segs


def length_report(n, sdur):
    """One line for the editor: how long the clip part of the video is, with the speed and the repeats."""
    trim0, clip, speed, words, groups, segs = timing(n, sdur)
    played = sum(sg["o1"] - sg["o0"] for sg in segs if sg["kind"] == "play")
    rep = sum(sg["o1"] - sg["o0"] for sg in segs if sg["kind"] in ("freeze", "replay"))
    n_rep = sum(g["rep"] for g in groups)
    txt = f"⏱️ clip {clip:.1f} s"
    if abs(speed - 1) > 1e-3:
        txt += f" → **{played:.1f} s at {speed:g}×**"
    if n_rep:
        txt += f" + {rep:.1f} s of repeats ({n_rep} replay{'s' if n_rep != 1 else ''})"
    kind = n.get("recap_style") if n.get("recap_style") in ("flashcards", "table") else DEFAULT_RECAP
    return txt + f" = **{segs[-1]['o1'] - LEAD:.1f} s** (+ {LEAD:g} s intro" + \
        (f", + {recap_len(kind, len(groups)):.1f} s recap)" if groups else ")")


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


def _clip_sound(path, trim0, clip, speed=1.0):
    """The clip's sound (stereo float, 44.1 kHz) from trim0 for `clip` seconds, slowed / sped up to `speed` with its
    pitch kept (FFmpeg atempo). None when the video has no sound."""
    cmd = [ffmpeg_exe(), "-v", "error", "-ss", f"{trim0:.3f}", "-t", f"{clip:.3f}", "-i", path, "-vn"]
    if abs(speed - 1.0) > 1e-3:
        cmd += ["-af", f"atempo={speed:.4f}"]
    cmd += ["-f", "s16le", "-acodec", "pcm_s16le", "-ac", "2", "-ar", str(SR), "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, np.int16).reshape(-1, 2).astype(np.float64) / 32768.0


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


def _spring_in(t, damp=9.0, freq=14.0):
    """0 -> 1 with a natural overshoot and settle (t = seconds since the start). (text._spring, used by the
    subtitles, is the other kind: a landing wobble 1 -> 0.)"""
    return 0.0 if t <= 0 else 1 - math.exp(-damp * t) * math.cos(freq * t)


def _warp(im, quad, size):
    """im drawn into the quadrilateral quad (TL, TR, BR, BL) of a transparent canvas of `size` (3D perspective)."""
    w, h = im.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    a = []
    for (x, y), (u, v) in zip(quad, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    coeffs = np.linalg.solve(np.array(a, float), np.array([c for p in src for c in p], float)).tolist()
    return im.transform(size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)


def _shade(im, k):
    """An RGBA image darkened by k (0..1): a surface turning away from the light."""
    if k <= 0.01:
        return im
    a = np.asarray(im, np.float32).copy()
    a[..., :3] *= 1 - k
    return Image.fromarray(a.astype(np.uint8))


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    """0 (black) .. 1 (white): is a colour light enough for dark text on it?"""
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def _contrast(a, b):
    """WCAG contrast ratio of two colours (1 = none .. 21 = black on white); text needs about 4.5 to read easily."""
    def rel(c):
        v = [x / 255 for x in c[:3]]
        v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    la, lb = sorted((rel(a), rel(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _readable(col, bg, minimum=4.5):
    """col if it reads well on bg, else black or white (whichever reads better)."""
    if _contrast(col, bg) >= minimum:
        return col
    return INK if _contrast(INK, bg) >= _contrast(WHITE, bg) else WHITE


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
        if L["accent"]:
            self.accent = L["accent"]
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
        if self.path and os.path.isfile(self.path):
            sw, sh, sdur, self.has_audio = probe(self.path)
        else:
            self.path, sw, sh, sdur, self.has_audio = "", 16, 9, 8.0, False
        self.trim0, self.clip, self.speed, self.words, self.groups, self.segs = timing(n, sdur)
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

        # words / key words: times in the clip (c); the video's own time (t) maps onto it through self.segs
        self.seg_o0 = [sg["o0"] for sg in self.segs]
        self.key_of = {}
        for gi, g in enumerate(self.groups):
            g["t0"] = self._out(g["c0"])           # when the key word is first said in the video
            reps = [sg for sg in self.segs if sg["gi"] == gi]
            g["rep_end"] = reps[-1]["o1"] if reps else self._out(g["c1"])
            for k in range(g["i0"], g["i1"] + 1):
                self.key_of[k] = gi

        self.E = self.segs[-1]["o1"]                  # the clip (with its repeats) ends
        self._rep_ims = {}
        self.ending_on = bool(n.get("ending_on", True)) and bool(self.groups)
        self.recap = n.get("recap_style") if n.get("recap_style") in ("flashcards", "table") else DEFAULT_RECAP
        self.base_duration = self.E + (recap_len(self.recap, len(self.groups)) if self.ending_on else 0.6)
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
        self.on_accent = INK if _lum(A) > 0.6 else WHITE   # text / icons on an accent pill
        if self.tag:
            t = _text(self.tag, 28, self.on_accent, "Black")
            pill = _rounded((t.width + 44, t.height + 6), (t.height + 6) // 2, A + (255,))
            pill.alpha_composite(t, (30, 3))
            self.tag_im = pill
        # the header's top; the notification look keeps the top of the screen free for its banner
        self.head_y = 110 + (NOTIFY_ROOM if L["card"] == "notify" else 0)
        self._layout_headline()
        if L["header"] == "masthead":  # the newspaper's name: the small line, else ENGLISH IN NEWS
            self.mast_im = _fit_text(self.label or "ENGLISH IN NEWS", 64, INK, 700, "Black", PLAYFAIR)

        if L["header"] == "post":
            self._layout_post_head()
        if L["wave"]:
            self._layout_wave()
        self._layout_captions()
        self._layout_cards()
        self._place()
        if L["band"]:
            self.band_box = (0, int(self.cap_y + self.cap_box[0]), W, int(self.cap_y + self.cap_box[1]))
        self._layout_background()
        if not self.vertical:
            self._layout_panel()
        if L["header"] == "post":
            self._layout_post_card()
        if L["ticker"]:
            self._layout_ticker()
        if self.ending_on:
            if self.recap == "table":
                self._layout_ending()
            else:
                self._layout_flash(n)

    def _place(self):
        """Where the panel, the subtitles and the word card go, from their real heights: subtitles under the clip,
        the card under the subtitles, everything above the safe line (the tv card above its ticker). A landscape
        clip's panel only gets smaller when a tall card would not fit otherwise."""
        L = self.L
        limit = (TICKER_Y - 14) if L["card"] == "bar" else SAFE_BOTTOM - 6
        rt, rb = self.card_box                     # the cards' real top / bottom inside their images
        gap = 20 if self.cards else 0
        top_card = L["card"] == "notify"           # drops in at the top: the subtitles keep all the room below
        if top_card:
            rt = rb = gap = 0
        # the subtitle block's drawn rows relative to cap_y: letters + the marker / box around them (+ tv band)
        m = 30 if L["band"] else 16
        top_off = self.cap_band[0] - m
        bot_off = self.cap_lh * (L["max_lines"] - 1) + self.cap_band[1] + m
        cap_h = bot_off - top_off
        if self.vertical:   # subtitles in the middle-low part, the card under them
            self.cap_y = (960 if L["cap_mode"] == "pop" else 880) - top_off
        elif L["header"] == "post":   # the clip inside the post card, as wide as the card allows
            pw0, ph0 = self.vsize
            aspect = pw0 / ph0
            ph = min(560, int(round(928 / aspect)))
            vy = self.head_y + POST_PAD + self.post_head_h + 20
            post_end = lambda h: vy + h + POST_FOOT                      # noqa: E731
            over = post_end(ph) + 36 + cap_h + gap + (rb - rt) - limit
            if over > 0:   # a tall card: a smaller clip (same shape)
                ph = max(300, ph - over)
            pw = min(928, int(round(ph * aspect)))
            self.vsize = (pw // 2 * 2, ph // 2 * 2)
            self.vpos = (40 + (1000 - self.vsize[0]) // 2, vy)
            self.post_box = (40, self.head_y, 1040, post_end(self.vsize[1]))
            self.cap_y = self.post_box[3] + 36 - top_off
        else:
            top = max(300, self.head_bottom + 36)
            cap_gap = 44 + (WAVE_H + 30 if L["wave"] else 0)   # under the panel's progress line (+ the waveform)
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
        if top_card:
            self.card_y = 34 - self.card_box[0]
        else:
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
        top = self.head_y + (150 if L["header"] == "masthead" else 120)
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
        elif L["bg"] in ("glass", "dark", "feed"):
            xx = np.linspace(0, 1, W)[None, :]
            yy = y * (H / W)                                     # round blobs: both axes in widths

            def blob(cx, cy, r):
                return np.exp(-(((xx - cx) ** 2 + (yy - cy * H / W) ** 2) / r ** 2))[..., None]
            if L["bg"] == "glass":     # soft colour blobs on a deep night blue (frosted glass sits on it)
                arr = np.broadcast_to(np.array([20, 18, 31], np.float32), (H, W, 3)).copy()
                for col, cx, cy, r, k in (((124, 92, 255), 0.12, 0.18, 0.55, 0.85), ((255, 106, 61), 0.95, 0.52, 0.5, 0.75),
                                          ((0, 179, 164), 0.25, 0.95, 0.6, 0.7), ((228, 72, 140), 0.85, 0.05, 0.35, 0.4)):
                    arr += (np.array(col, np.float32) - arr) * blob(cx, cy, r) * k
            elif L["bg"] == "dark":    # studio black, a faint light from above
                arr = np.broadcast_to(np.array([12, 14, 13], np.float32), (H, W, 3)).copy()
                arr += (np.array([40, 46, 36], np.float32) - arr) * blob(0.5, -0.05, 0.75) * 0.8
            else:                      # a social feed: light grey
                c0, c1 = np.array([240, 242, 245]), np.array([228, 231, 236])
                arr = np.broadcast_to(c0 * (1 - y[..., None]) + c1 * y[..., None], (H, W, 3)).astype(np.float32)
            arr += _noise((W, H), 2.0, 11)[..., None]           # a little grain: no banding in the gradients
            self.static_bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        else:
            self.static_bg = None
        self.dark = L["dark"] if L["dark"] is not None else self.static_bg is None
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

        def lines_of(idx, max_w=CAP_MAX_W):
            lines, row, x = [], [], 0.0
            for i in idx:
                w = f.getlength(self._cap_txt(i))
                if row and x + space + w > max_w:
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
                gi = self.key_of.get(i)
                same_key = gi is not None and gi == self.key_of.get(cur[-1])
                full = len(cur) >= L["max_words"] or len(lines_of(cur + [i])) > L["max_lines"]
                if not same_key and (gap > (0.45 if pop else 0.7) or too_long or sent or comma or full):
                    pages.append(cur)
                    cur = []
                elif same_key and full:   # a key phrase stays on one page: it starts a new page instead of
                    j = next(k for k, c in enumerate(cur) if self.key_of.get(c) == gi)   # spilling onto a
                    if j > 0:                                                        # line under the card
                        pages.append(cur[:j])
                        cur = cur[j:]
            cur.append(i)
        if cur:
            pages.append(cur)

        self.pages = []
        lh = int(size * (1.10 if pop else 1.32))
        lead = 0.04 if pop else 0.12
        for k, idx in enumerate(pages):
            t0 = self.words[idx[0]]["s"] - lead
            nxt = self.words[pages[k + 1][0]]["s"] - lead if k + 1 < len(pages) else self.clip
            t1 = min(nxt, self.words[idx[-1]]["e"] + (0.5 if pop else 1.2))
            rows = lines_of(idx)
            if len(rows) > L["max_lines"]:   # a key phrase too long on its own: one line, shrunk by fit below
                rows = lines_of(idx, 1e9) if pop else rows
            items = []
            for li, row in enumerate(rows):
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
            speak = mk(L["pill_text"]) if L["pill_text"] else (mk(WHITE) if L["cap_col"] == INK else norm)
        else:
            speak = mk(L["speak_col"])
        if L["key_stroke"]:
            key = mk(L["key_col"], st, L["key_stroke"])
        else:
            key = mk(L["key_col"], 3 if st else 0, L["mark"])
        pad = 6 + st
        return dict(norm=norm, speak=speak, key=key, pad=pad, w=norm.width - 2 * pad)

    def _draw_captions(self, frame, c, a):
        """The subtitles at clip time c (animations in the video's own seconds: / speed)."""
        L = self.L
        spd = self.speed
        if L["band"]:
            self._draw_band(frame, a)
        page = next((p for p in self.pages if p["t0"] <= c < p["t1"]), None)
        if page is None:
            return
        pop = L["cap_mode"] == "pop"
        ka = _ease((c - page["t0"]) / spd / (0.08 if pop else 0.15)) * min(1.0, (page["t1"] - c) / spd / 0.1) * a
        rise = 0 if pop else int((1 - _ease((c - page["t0"]) / spd / 0.2)) * 18)
        fit = page["fit"]
        pscale = (0.75 + 0.25 * _back((c - page["t0"]) / spd / 0.22)) * fit if pop else 1.0
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
                if gi is not None and c >= w["s"]:
                    cx, half = it["x"] + it["w"] / 2, it["w"] * pscale / 2   # the word as it is drawn
                    sp = spans.setdefault((gi, it["line"]), [cx - half, cx + half, w["s"], 0])
                    sp[0], sp[1] = min(sp[0], cx - half), max(sp[1], cx + half)
            for (gi, li), (x0, x1, ts, _) in spans.items():
                self._pop_box(frame, x0, x1, base_y + li * lh, _ease((c - ts) / spd / 0.18) * ka, pscale)
        for it in items:
            w = self.words[it["i"]]
            y = base_y + it["line"] * lh
            gi = self.key_of.get(it["i"])
            spoken = c >= w["s"]
            speaking = w["s"] <= c < w["e"] + 0.05
            if gi is not None and spoken:   # the marker swipes in behind the key word
                p = _ease((c - w["s"]) / max(0.12, min(0.35, w["e"] - w["s"])))
                im = it["key"] if p > 0.5 else it["norm"]
                sc = pscale * (1.0 + 0.08 * _spring((c - self.groups[gi]["c0"]) / spd))
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
                                        fill=(L["pill_col"] or self.accent) + (int(235 * ka),))
                else:
                    sc *= 1.0 + 0.07 * math.sin(math.pi * min(1.0, (c - w["s"]) / spd / 0.25))
                    if L["bg"] == "paper":  # newspaper: the spoken word is also underlined
                        d.line([(it["x"], y + b1 + 4), (it["x"] + it["w"], y + b1 + 4)], fill=self.accent,
                               width=4)
            elif gi is not None:  # a key word not spoken yet: underlined (as wide as the word is drawn)
                cx, half, cy = it["x"] + it["w"] / 2, it["w"] * sc / 2, y + it["norm"].height / 2
                uy = cy + (b1 - it["norm"].height / 2) * sc
                d.rounded_rectangle([cx - half, uy + 3, cx + half, uy + 8], 3,
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

    # ---------------------------------------------------------- social post (look "post")
    def _layout_post_head(self):
        """The post's top: logo, brand name + a verified tick, @handle · now, then the headline (key words in blue)."""
        L = self.L
        av = 84
        name = self.brand_name.title() if self.brand_name else (self.label.title() or "English in News")
        name_im = _tight_text(name, 36, INK, 640, "Bold", INTER, pad=4)
        who = self.handle or ("@" + self.brand_name.lower().replace(" ", "") if self.brand_name else "")
        sub_im = _tight_text(" · ".join(b for b in (who, "now") if b), 28, (101, 119, 134), 700, "Medium", INTER, pad=2)
        S = 4                                                       # the verified tick, drawn large then reduced
        tick = Image.new("RGBA", (30 * S, 30 * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(tick)
        d.ellipse([0, 0, 30 * S - 1, 30 * S - 1], fill=FEED_BLUE + (255,))
        d.line([(8 * S, 15.5 * S), (13 * S, 20.5 * S), (22.5 * S, 10 * S)], fill=WHITE + (255,), width=int(3.4 * S),
               joint="curve")
        tick = tick.resize((30, 30), Image.LANCZOS)
        # the headline, word by word: the words of a key phrase in the post blue
        words = self.headline.split()
        norm = [re.sub(r"[^\w'-]", "", w).lower() for w in words]
        blue = set()
        for g in self.groups:
            ph = [re.sub(r"[^\w'-]", "", w).lower() for w in g["text"].split()]
            for i in range(len(norm) - len(ph) + 1):
                if ph and norm[i:i + len(ph)] == ph:
                    blue.update(range(i, i + len(ph)))
        size, rows = 42, []
        while size >= 32:
            f = get_font(size, L["head_weight"], INTER)
            sp, rows, x = f.getlength(" "), [[]], 0.0
            for i, w in enumerate(words):
                wl = f.getlength(w)
                if rows[-1] and x + sp + wl > 928:
                    rows.append([])
                    x = 0.0
                x += (sp if rows[-1] else 0) + wl
                rows[-1].append(i)
            if len(rows) <= 3:
                break
            size -= 2
        lh = int(size * 1.3)
        head_h = lh * len(rows) if words else 0
        im = Image.new("RGBA", (928, av + 22 + head_h), (0, 0, 0, 0))
        im.alpha_composite(self._icon(av), (0, 0))
        im.alpha_composite(name_im, (av + 20, 4))
        im.alpha_composite(tick, (av + 20 + name_im.width + 6, 4 + (name_im.height - 30) // 2))
        im.alpha_composite(sub_im, (av + 20, 4 + name_im.height + 6))
        d = ImageDraw.Draw(im)
        f = get_font(size, L["head_weight"], INTER)
        sp = f.getlength(" ")
        for r, row in enumerate(rows):
            x = 0.0
            for i in row:
                d.text((x, av + 22 + r * lh), words[i], font=f, fill=(FEED_BLUE if i in blue else INK) + (255,))
                x += f.getlength(words[i]) + sp
        self.post_head = im
        self.post_head_h = im.height

    def _post_icons(self):
        """The actions row: reply · repost · like · share as outline icons with their names (no made-up counts);
        returns (row image, the heart's centre in it, a filled heart)."""
        grey, S, sz = (101, 119, 134), 4, 40
        def canvas():
            return Image.new("RGBA", (sz * S, sz * S), (0, 0, 0, 0))
        w = int(3.2 * S)
        reply = canvas()
        d = ImageDraw.Draw(reply)
        d.rounded_rectangle([3 * S, 5 * S, 37 * S, 29 * S], 9 * S, outline=grey + (255,), width=w)
        d.polygon([(10 * S, 27 * S), (10 * S, 37 * S), (19 * S, 28 * S)], fill=grey + (255,))
        repost = canvas()
        d = ImageDraw.Draw(repost)
        d.line([(9 * S, 30 * S), (9 * S, 11 * S), (30 * S, 11 * S)], fill=grey + (255,), width=w, joint="curve")
        d.polygon([(4 * S, 15 * S), (9 * S, 8 * S), (14 * S, 15 * S)], fill=grey + (255,))
        d.line([(31 * S, 10 * S), (31 * S, 29 * S), (10 * S, 29 * S)], fill=grey + (255,), width=w, joint="curve")
        d.polygon([(26 * S, 25 * S), (31 * S, 32 * S), (36 * S, 25 * S)], fill=grey + (255,))
        heart_pts = []
        for k in range(120):
            a = 2 * math.pi * k / 120
            x = 16 * math.sin(a) ** 3
            y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
            heart_pts.append(((20 + x * 1.05) * S, (21 + y * 1.05) * S))
        like = canvas()
        ImageDraw.Draw(like).line(heart_pts + heart_pts[:1], fill=grey + (255,), width=w, joint="curve")
        full = canvas()
        ImageDraw.Draw(full).polygon(heart_pts, fill=(249, 24, 128, 255))
        share = canvas()
        d = ImageDraw.Draw(share)
        d.line([(20 * S, 26 * S), (20 * S, 5 * S)], fill=grey + (255,), width=w)
        d.line([(11 * S, 13 * S), (20 * S, 4 * S), (29 * S, 13 * S)], fill=grey + (255,), width=w, joint="curve")
        d.line([(5 * S, 22 * S), (5 * S, 35 * S), (35 * S, 35 * S), (35 * S, 22 * S)], fill=grey + (255,), width=w,
               joint="curve")
        row = Image.new("RGBA", (928, 56), (0, 0, 0, 0))
        heart = None
        for k, (ic, name) in enumerate(((reply, "Reply"), (repost, "Repost"), (like, "Like"), (share, "Share"))):
            ic = ic.resize((sz, sz), Image.LANCZOS)
            lab = _tight_text(name, 26, grey, 200, "SemiBold", INTER, pad=2)
            x = int(k * 928 / 4)
            row.alpha_composite(ic, (x, (56 - sz) // 2))
            row.alpha_composite(lab, (x + sz + 12, (56 - lab.height) // 2))
            if name == "Like":
                heart = (x + sz // 2, 28)
        return row, heart, full.resize((sz, sz), Image.LANCZOS)

    def _layout_post_card(self):
        """The white post card, pre-drawn: landscape = top + the clip's place + the actions row; vertical = only the
        top (over the clip)."""
        if self.vertical:
            x0, y0, x1, y1 = 40, self.head_y, 1040, self.head_y + POST_PAD + self.post_head_h + 26
        else:
            x0, y0, x1, y1 = self.post_box
        cw, ch = x1 - x0, y1 - y0
        im = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (40, 50, 40 + cw, 50 + ch), 40, 22, 70, 0))
        im.alpha_composite(_rounded((cw, ch), 40, WHITE + (255,)), (40, 40))
        im.alpha_composite(self.post_head, (40 + 36, 40 + POST_PAD))
        self.post_heart = None
        if not self.vertical:
            row, heart, self.heart_full = self._post_icons()
            ry = self.vpos[1] + self.vsize[1] + 36 - y0
            im.alpha_composite(row, (40 + 36, 40 + ry))
            self.post_heart = (x0 + 36 + heart[0], y0 + ry + heart[1])
        self.post_im, self.post_xy = im, (x0 - 40, y0 - 40)

    def _draw_post(self, frame, t, a):
        """The post card (it slides in with the header); the heart fills and pops as each key word's card comes."""
        k = _ease(t / 0.5) * a
        if k <= 0:
            return
        x, y = self.post_xy
        _comp(frame, _fade(self.post_im, k), x, y + int((1 - _ease(t / 0.5)) * 30))
        if self.post_heart is None:
            return
        hits = [c["t0"] for c in self.cards if c["t0"] <= t]
        if hits:
            u = t - hits[-1]
            sc = 1 + 0.45 * math.exp(-7 * u) * math.sin(min(math.pi, u * 14)) if u < 0.6 else 1.0
            im = _scaled(self.heart_full, sc)
            hx, hy = self.post_heart
            _comp(frame, _fade(im, k), int(hx - im.width / 2), int(hy - im.height / 2))

    # ---------------------------------------------------------- podcast waveform (look "podcast")
    def _layout_wave(self):
        """How much speech there is at each moment of the clip (from the word timings), 100 steps a second."""
        n = int(self.clip * 100) + 2
        env = np.zeros(n, np.float32)
        for w in self.words:
            env[max(0, int(w["s"] * 100)):max(0, int(w["e"] * 100)) + 1] = 1.0
        k = np.hanning(15)
        self.wave_env = np.convolve(env, k / k.sum(), mode="same")

    def _draw_wave(self, frame, t, a):
        """Bars that move with the speech: tall while words are spoken, low in the pauses (still while held)."""
        if a <= 0:
            return
        c = self._c(t)
        lvl = float(self.wave_env[max(0, min(len(self.wave_env) - 1, int(c * 100)))])
        n, h = 34, WAVE_H
        if self.vertical:
            x0, x1 = 150, W - 150
            yc = int(self.cap_y + self.cap_box[0]) - h // 2 - 26
        else:
            x0, x1 = self.vpos[0] + 30, self.vpos[0] + self.vsize[0] - 30
            yc = self.vpos[1] + self.vsize[1] + 18 + 6 + 22 + h // 2
        step = (x1 - x0) / n
        bw = max(4, int(step * 0.56))
        d = ImageDraw.Draw(frame)
        for i in range(n):
            shape = 0.45 + 0.55 * math.sin(math.pi * (i + 0.5) / n)
            wob = abs(math.sin(c * 7.3 + i * 1.7) * math.cos(c * 3.1 + i * 0.63))
            bh = max(bw, h * shape * (0.12 + 0.88 * lvl * (0.3 + 0.7 * wob)))
            x = x0 + i * step + (step - bw) / 2
            d.rounded_rectangle([x, yc - bh / 2, x + bw, yc + bh / 2], bw // 2,
                                fill=LIME + (int(255 * a * (0.55 + 0.45 * lvl)),))

    # ---------------------------------------------------------- word cards
    def _layout_cards(self):
        self.cards = []
        n = len(self.groups)
        make = {"pop": self._card_pop, "bar": self._card_bar, "sticker": self._card_sticker,
                "clip": self._card_clip, "notify": self._card_notify, "podpill": self._card_podpill,
                "reply": self._card_reply}[self.L["card"]]
        free = 0.0                 # when the card before has fully gone (cards never overlap: they queue)
        for gi, g in enumerate(self.groups):
            t0 = max(g["t0"], free)
            if t0 - g["t0"] > CARD_LAG or t0 > self.E - 0.6:
                continue  # key words too close together / too late: this one is marked in the subtitles + recap
            nxt = self.groups[gi + 1]["t0"] if gi + 1 < n else self.E + 0.3
            hold = max(t0 + CARD_HOLD, g["rep_end"] + 0.5)   # a repeated word keeps its card through the replays
            t1 = min(max(nxt - CARD_OUT - 0.02, t0 + CARD_MIN), hold, self.E + 0.2)
            free = t1 + CARD_OUT + 0.02
            self.cards.append(dict(im=make(gi, g, n), t0=t0, t1=t1, gi=gi))
        if self.L["card"] == "notify":   # the frosted part: where the banner itself is (not its shadow)
            for c in self.cards:
                c["glass"] = c["im"].getchannel("A").point(lambda v: 255 if v > 200 else 0)
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

    def _icon(self, size):
        """The brand's app icon: the logo, else a rounded accent square with the brand's first letter."""
        if self.logo is not None:
            return _scaled(self.logo, size / self.logo.width)
        im = _rounded((size, size), size // 4, self.accent + (255,))
        ch = _tight_text((self.brand_name or "N")[:1], int(size * 0.5), self.on_accent, size, "Black", MONT, pad=2)
        im.alpha_composite(ch, ((size - ch.width) // 2, (size - ch.height) // 2))
        return im

    def _card_notify(self, gi, g, n):
        """notify: a phone notification — app icon, NEW WORD k/N · now, the English, the Arabic — on frosted glass
        (the glass itself is drawn per frame: the picture behind it, blurred)."""
        L = self.L
        cw, pad, ic = 1000, 30, 104
        icon = self._icon(ic)
        room = cw - 2 * pad - ic - 26
        grey = (88, 94, 108)
        lab = _tight_text(f"NEW WORD  ·  {gi + 1}/{n}", 26, grey, room - 80, "Bold", INTER, pad=2)
        now = _tight_text("now", 26, grey, 100, "SemiBold", INTER, pad=2)
        en = _tight_text(g["text"], 60, INK, room, "Black", INTER, pad=4)
        ar = _ink_crop(_ar_fit(g["ar"], 52, L["card_ar"], L["ar_font"], room), 6) if g["ar"] else None
        blk = lab.height + 10 + en.height + (8 + ar.height if ar is not None else 0)
        ch = 2 * pad + max(ic, blk)
        im = Image.new("RGBA", (cw + 60, ch + 70), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (30, 40, 30 + cw, 40 + ch), 44, 22, 130, 0))
        body = _rounded((cw, ch), 44, (255, 255, 255, 208))
        ImageDraw.Draw(body).rounded_rectangle([1, 1, cw - 2, ch - 2], 43, outline=(255, 255, 255, 235), width=2)
        im.alpha_composite(body, (30, 30))
        im.alpha_composite(icon, (30 + pad, 30 + (ch - ic) // 2))
        x, y = 30 + pad + ic + 26, 30 + (ch - blk) // 2
        im.alpha_composite(lab, (x, y))
        im.alpha_composite(now, (30 + cw - pad - now.width, y))
        y += lab.height + 10
        im.alpha_composite(en, (x, y))
        if ar is not None:
            im.alpha_composite(ar, (x, y + en.height + 8))
        return im

    def _card_podpill(self, gi, g, n):
        """podcast: a dark pill with a lime rim — a KEY WORD chip, the English, the Arabic (on a second row when
        one row would be too wide)."""
        L = self.L
        chip_t = _tight_text("KEY WORD", 24, INK, 300, "Black", MONT, pad=2)
        chip = _rounded((chip_t.width + 36, chip_t.height + 22), (chip_t.height + 22) // 2, LIME + (255,))
        chip.alpha_composite(chip_t, (18, 11))
        en = _tight_text(g["text"], 56, WHITE, 760, "ExtraBold", MONT, pad=4)
        ar = _ink_crop(_ar_fit(g["ar"], 52, L["card_ar"], L["ar_font"], 760), 6) if g["ar"] else None
        one = 26 + chip.width + 22 + en.width + (26 + ar.width if ar is not None else 0) + 34
        if one <= 980:   # one row
            h = max(chip.height, en.height, ar.height if ar is not None else 0) + 34
            bw, rows = one, [(chip, 26), (en, 26 + chip.width + 22)]
            if ar is not None:
                rows.append((ar, one - 34 - ar.width))
            r = h // 2
        else:            # chip + English, the Arabic under them
            w1 = chip.width + 22 + en.width
            bw = max(w1, ar.width if ar is not None else 0) + 80
            h = max(chip.height, en.height) + (ar.height + 10 if ar is not None else 0) + 44
            rows, r = None, 46
        im = Image.new("RGBA", (bw + 60, h + 60), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (30, 38, 30 + bw, 38 + h), r, 18, 140, 0))
        body = _rounded((bw, h), r, (27, 31, 28, 255))
        ImageDraw.Draw(body).rounded_rectangle([2, 2, bw - 3, h - 3], r - 2, outline=LIME + (255,), width=5)
        im.alpha_composite(body, (30, 30))
        if rows:
            for part, x in rows:
                im.alpha_composite(part, (30 + x, 30 + (h - part.height) // 2))
        else:
            top = max(chip.height, en.height)
            x = 30 + (bw - (chip.width + 22 + en.width)) // 2
            im.alpha_composite(chip, (x, 30 + 22 + (top - chip.height) // 2))
            im.alpha_composite(en, (x + chip.width + 22, 30 + 22 + (top - en.height) // 2))
            if ar is not None:
                im.alpha_composite(ar, (30 + (bw - ar.width) // 2, 30 + 22 + top + 10))
        return im

    def _card_reply(self, gi, g, n):
        """post: a pinned reply under the post — logo, @handle · pinned, the English, the Arabic in the post blue."""
        L = self.L
        cw, pad, av = 920, 30, 76
        room = cw - 2 * pad - av - 24 - 12
        who = self.handle or ("@" + self.brand_name.lower().replace(" ", "") if self.brand_name else "@news")
        top = _tight_text(f"{who}  ·  pinned  ·  {gi + 1}/{n}", 26, (101, 119, 134), room, "SemiBold", INTER, pad=2)
        en = _tight_text(g["text"], 58, INK, room, "Black", INTER, pad=4)
        ar = _ink_crop(_ar_fit(g["ar"], 50, L["card_ar"], L["ar_font"], room), 6) if g["ar"] else None
        blk = top.height + 10 + en.height + (8 + ar.height if ar is not None else 0)
        ch = 2 * pad + max(av, blk)
        im = Image.new("RGBA", (cw + 60, ch + 70), (0, 0, 0, 0))
        im.alpha_composite(_shadow_box(im.size, (30, 40, 30 + cw, 40 + ch), 32, 18, 90, 0))
        body = _rounded((cw, ch), 32, WHITE + (255,))
        edge = Image.new("RGBA", (12, ch), FEED_BLUE + (255,))
        body.paste(edge, (0, 0), _round_mask((cw, ch), 32).crop((0, 0, 12, ch)))
        im.alpha_composite(body, (30, 30))
        icon = self._icon(av)
        x = 30 + 12 + pad
        im.alpha_composite(icon, (x, 30 + pad))
        x += av + 24
        y = 30 + (ch - blk) // 2
        im.alpha_composite(top, (x, y))
        y += top.height + 10
        im.alpha_composite(en, (x, y))
        if ar is not None:
            im.alpha_composite(ar, (x, y + en.height + 8))
        return im

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
            if kind == "notify":   # drops in from the top over frosted glass, goes back up
                k = _back(tin / 0.42)
                y = int(self.card_y - (1 - min(1.0, k)) * (im.height + 60) - out * (im.height + 60)
                        + max(0.0, k - 1) * 30)
                self._glass(frame, c["glass"], (W - im.width) // 2, y, al)
                _comp(frame, _fade(im, al), (W - im.width) // 2, y)
                continue
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

    def _glass(self, frame, mask, x, y, al):
        """Frosted glass: the picture under mask (placed at x, y) blurred — done at a sixth of the size (fast)."""
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + mask.width), min(H, y + mask.height)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        part = frame.crop((x0, y0, x1, y1))
        small = part.resize((max(1, part.width // 6), max(1, part.height // 6)), Image.BILINEAR)
        part = small.filter(ImageFilter.GaussianBlur(3)).resize(part.size, Image.BILINEAR)
        m = mask.crop((x0 - x, y0 - y, x1 - x, y1 - y))
        if al < 0.999:
            m = m.point(lambda v: int(v * al))
        part.putalpha(m)
        frame.alpha_composite(part, (x0, y0))

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
            row_h = max(70, min(110, room // max(1, per)))
            es = int(row_h * 0.38)
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
        # ONE English size and ONE Arabic size for every row (a table, not a ransom note): measured on the widest
        # word / meaning, the columns split where those need it; only a phrase too long even at REC_MIN of the size
        # gets smaller on its own.
        d = min(row_h - 44, 52)
        tx = d + 30
        ar0 = int(es * 0.95)
        f_en = get_font(es, en_weight, tf)
        w_en = max((f_en.getlength(en) + 12 for en, _ in rows), default=1.0)
        w_ar = max((_ar_line(ar, ar0, L["end_ar"], L["ar_font"]).width - 2 * _AR_PAD for _, ar in rows if ar),
                   default=0)
        if cols == 2:     # stacked: each has the row's full width
            room = rw - tx - 14
            k = max(REC_MIN, min(1.0, room / w_en, room / w_ar if w_ar else 1.0))
            col_en = col_ar = room
        else:             # side by side
            room = rw - tx - 20 - 36
            k = max(REC_MIN, min(1.0, room / (w_en + w_ar)))
            col_en = w_en * k if (w_en + w_ar) * k <= room else room * w_en / (w_en + w_ar)
            col_ar = room - col_en
        es_c, ar_c = max(18, int(es * k)), max(18, int(ar0 * k))
        if cols == 2:     # both lines must fit the row's height too: the letters' real band, the same for all rows
            for _ in range(8):
                eh = _tight_text("Hg", es_c, INK, 10 ** 6, en_weight, tf, pad=2).height
                up, dn = self._ar_ref(ar_c)
                if eh + 6 + up + dn <= row_h - 14 - 12:
                    break
                es_c, ar_c = max(16, int(es_c * 0.92)), max(16, int(ar_c * 0.92))
        up, dn = self._ar_ref(ar_c)
        for k, (en, ar) in enumerate(rows):
            col, row = divmod(k, per)
            rim = Image.new("RGBA", (rw, row_h - 14), (0, 0, 0, 0))
            rim.alpha_composite(_rounded(rim.size, 22 if r > 4 else 3, L["end_row"] + (255,)))
            num = _rounded((d, d), d // 2, self.accent + (255,))
            nt = _text(str(k + 1), int(d * 0.55), WHITE, "Black")
            num.alpha_composite(nt, ((num.width - nt.width) // 2, (num.height - nt.height) // 2 - 2))
            rim.alpha_composite(num, (12, (rim.height - num.height) // 2))
            # the English cut to its font's letter band; the Arabic on one baseline — so every row lines up
            et = _tight_text(en, es_c, L["end_en"], col_en, en_weight, tf, 16, pad=2)
            at, base = self._ar_row(ar, ar_c, L["end_ar"], col_ar) if ar else (None, 0)
            if cols == 2:   # the English over the Arabic (right-aligned)
                y0 = (rim.height - (eh + 6 + up + dn)) // 2
                rim.alpha_composite(et, (tx, y0 + (eh - et.height) // 2))
                if at is not None:
                    _comp(rim, at, rw - at.width + _AR_PAD - 14, y0 + eh + 6 + up - base)
            else:
                rim.alpha_composite(et, (tx, (rim.height - et.height) // 2))
                if at is not None:   # the letters' band centred in the row
                    _comp(rim, at, rw - at.width + _AR_PAD - 20, rim.height // 2 + (up - dn) // 2 - base)
            self.end_rows.append((rim, 40 + 30 + col * (rw + 20), 40 + top + row * row_h))
        self.end_step = min(0.16, 1.6 / max(1, n))   # rows come in one after another (all within 1.6 s)
        self.end_pos = ((W - card.width) // 2, max(140, (SAFE_BOTTOM - card.height) // 2 + 30))
        col = WHITE if self.vertical else L["end_text"]
        self.end_handle = _text(self.handle, 34, col, "Bold") if self.handle else None
        self.end_cta = _fit_text(self.cta, 32, col, 900, "SemiBold") if self.cta else None

    # ---------------------------------------------------------- 🃏 flashcards recap
    def _layout_flash(self, n):
        """Flashcards recap: one card per key word (1 column up to 5, then 2), dealt from a deck below the screen —
        each flies in, flips from edge-on in 3D, lands with a squash and settles; a shine sweeps each card; a ring
        counts the words (k/n) and bursts into a ✓ with sparks when the last lands; the camera pushes in slowly.
        Colours: one of PALETTES, picked from the clip (file name + headline + words) — every video gets its own,
        and the same video always the same. ONE English and ONE Arabic size on every card."""
        rows = [(g["text"], g["ar"]) for g in self.groups]
        k = len(rows)
        key = "|".join([os.path.basename(self.path or ""), self.headline] + [e for e, _ in rows])
        pi = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
        pal = PALETTES[pi % len(PALETTES)]
        shift = (pi // len(PALETTES)) % len(pal["cards"])
        cards = [_hex(c) for c in pal["cards"]]
        hi, deep = _hex(pal["hi"]), _hex(pal["deep"])
        self.f_ring = deep if _lum(deep) < 0.7 else self.accent
        dark = self.dark or self.vertical                      # the recap sits on a dark or a light veil
        tcol = WHITE if dark else INK
        self.f_cols = cols = 1 if k <= 5 else 2
        per = -(-k // cols)
        gap = 24
        cw = 900 if cols == 1 else 439
        ch = int(min(230 if cols == 1 else 200, (1400 - 170 - 150 - gap * (per - 1)) / per))
        block = 150 + per * ch + (per - 1) * gap
        ty = 170 + max(0, (1400 + 120 - 170 - block - 110) // 2)
        self.f_ty, self.f_cw, self.f_ch, self.f_foot = ty, cw, ch, min(1428, ty + block + 26)
        room = cw - 110
        en0, ar0 = ch * 0.31, ch * 0.29
        f = get_font(int(en0), "ExtraBold", MONT)
        w_en = max(f.getlength(e) for e, _ in rows) + 12
        w_ar = max((_ar_line(a, int(ar0), INK, PLEX_AR).width - 2 * _AR_PAD for _, a in rows if a), default=1)
        kk = max(0.6, min(1.0, room / w_en, room / w_ar))
        en_s, ar_s = int(en0 * kk), int(ar0 * kk)
        up, dn = self._ar_ref(ar_s, PLEX_AR)
        mask = _round_mask((cw, ch), 28)
        self.f_faces, self.f_slots = [], []
        for i, (en, ar) in enumerate(rows):
            col, row = divmod(i, per)
            bg = cards[(i + shift) % len(cards)]
            light = _lum(bg) > 0.6
            txt = _readable(INK if light else WHITE, bg)                   # the English, always easy to read
            arc = _readable(deep if light else hi, bg)                      # the Arabic: the palette's colour if
            edge = deep if light else hi                                    # it reads well on this card
            face = Image.new("RGBA", (cw, ch), bg + (255,))
            d = ImageDraw.Draw(face)
            d.rectangle([0, 0, 10, ch], fill=edge)                                      # the accent edge
            d.ellipse([24, 18, 70, 64], fill=edge)                                      # the number chip
            nt = _text(str(i + 1), 24, WHITE if _lum(edge) < 0.6 else INK, "Black")
            face.alpha_composite(nt, (47 - nt.width // 2, 41 - nt.height // 2 - 1))
            et = _tight_text(en, en_s, txt, room, "ExtraBold", MONT, 16, pad=2)
            at, base = self._ar_row(ar, ar_s, arc, room, PLEX_AR) if ar else (None, 0)
            blk = et.height + 10 + (up + dn if at is not None else 0)
            y0 = (ch - blk) // 2 + 4
            face.alpha_composite(et, ((cw - et.width) // 2, y0))
            if at is not None:
                _comp(face, at, (cw - at.width) // 2, y0 + et.height + 10 + up - base)
            face.putalpha(mask)
            self.f_faces.append(face)
            x = 90 + col * (cw + 22) if cols == 2 else (W - cw) // 2
            self.f_slots.append((x, ty + 150 + row * (ch + gap)))
        self.f_mask = mask
        self.f_shadow = _shadow_box((cw + 120, ch + 120), (60, 60, 60 + cw, 60 + ch), 28, 18, 150, 0)
        sh = Image.new("L", (cw, ch), 0)
        dd = ImageDraw.Draw(sh)
        for i in range(60):
            dd.line([(i, 0), (i - ch * 0.35, ch)], fill=int(110 * math.sin(math.pi * i / 60)), width=1)
        self.f_shine = sh
        self.f_step = min(0.2, 2.0 / max(1, k))
        self.f_lands = [0.5 + self.f_step * i + 0.22 for i in range(k)]
        self.f_done = self.f_lands[-1] if self.f_lands else 1.0
        self.f_title = _fit_text(self.ending_title.upper(), 52, tcol, 940, "Black")
        self.f_sub = _fit_text(self.ending_sub or f"{k} word{'s' if k != 1 else ''} from this news", 28,
                               (220, 222, 228) if dark else (90, 96, 108), 900, "SemiBold")
        # the title's underline: under the small line's letters (measured, whatever the font), above the cards
        sub_ink = self.f_sub.getchannel("A").getbbox() or (0, 0, 0, self.f_sub.height)
        self.f_sub_y = self.f_title.height + 2
        self.f_line = min(self.f_sub_y + sub_ink[3] + 14, 150 - 22)
        if self.f_line < self.f_sub_y + sub_ink[3] + 6:   # a tall font: lift the small line to keep the gap
            self.f_sub_y = self.f_line - 6 - sub_ink[3]
        right = max(x for x, _ in self.f_slots) + cw
        self.f_corner = (min(W - 80, right - 10), self.f_slots[0][1] - 10)
        rng = np.random.default_rng(pi % (2 ** 32))
        self.f_sparks = [(rng.uniform(0, 2 * math.pi), rng.uniform(380, 760), rng.uniform(5, 11),
                          [YELLOW, self.f_ring, WHITE, cards[i % len(cards)]][i % 4]) for i in range(34)]
        self.end_handle = _text(self.handle, 34, tcol, "Bold") if self.handle else None
        self.end_cta = _fit_text(self.cta, 32, tcol, 900, "SemiBold") if self.cta else None

    def _draw_flash(self, frame, te):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        k = _ease((te - 0.1) / 0.45)
        if k > 0:                                                    # the title drops in, its underline grows
            ty = self.f_ty
            _comp(layer, _fade(self.f_title, k), (W - self.f_title.width) // 2,
                  ty + int((1 - min(1.0, _spring_in(te - 0.1))) * -40))
            _comp(layer, _fade(self.f_sub, k), (W - self.f_sub.width) // 2, ty + self.f_sub_y)
            lw = int(220 * min(1.0, _spring_in(te - 0.35)))
            if lw > 0:
                ly = ty + self.f_line
                ImageDraw.Draw(layer).rounded_rectangle([W // 2 - lw // 2, ly, W // 2 + lw // 2, ly + 6], 3,
                                                        fill=self.f_ring)
        w, h = self.f_cw, self.f_ch
        for i, (face, (fx, fy)) in enumerate(zip(self.f_faces, self.f_slots)):
            t = te - (0.5 + self.f_step * i)
            if t <= 0:
                continue
            p = _spring_in(t, 8.0, 12.0)                               # flies in, overshoots, settles
            x0, y0 = W / 2 - w / 2, H + 120                            # the deck, under the screen
            x, y = x0 + (fx - x0) * p, y0 + (fy - y0) * p
            ay = math.radians(78) * max(0.0, 1 - _ease(t / 0.42))     # flips in from edge-on (around Y)
            rz = (13 if i % 2 else -11) * max(0.0, 1 - _ease(t / 0.5))
            lift = max(0.0, 1 - _ease(t / 0.5))                         # how high above the table it is
            land = t - 0.22                                             # squash on impact, then settle
            sq = 0.05 * math.exp(-10 * land) * math.cos(16 * land) if land > 0 else 0.0
            card = face
            st = te - (self.f_done + 0.25 + 0.07 * i)                  # a shine sweeps across once settled
            if 0 < st < 0.5:
                card = face.copy()
                band = Image.new("L", card.size, 0)
                band.paste(self.f_shine, (int(-80 + (w + 160) * (st / 0.5)), 0))
                band = Image.fromarray((np.asarray(band, np.float32) * np.asarray(self.f_mask, np.float32) / 255)
                                       .astype(np.uint8))
                white = Image.new("RGBA", card.size, (255, 255, 255, 0))
                white.putalpha(band)
                card.alpha_composite(white)
            if ay > 0.001:
                cwp, far = w * math.cos(ay), h * (1 - 0.28 * math.sin(ay))
                quad = [(w / 2 - cwp / 2, 0), (w / 2 + cwp / 2, (h - far) / 2), (w / 2 + cwp / 2, (h + far) / 2),
                        (w / 2 - cwp / 2, h)]
                card = _shade(_warp(card, quad, (w, h)), 0.35 * math.sin(ay))
            if abs(sq) > 0.002:
                card = card.resize((int(w * (1 + sq)), int(h * (1 - sq))), Image.BICUBIC)
            if abs(rz) > 0.05:
                card = card.rotate(rz, resample=Image.BICUBIC, expand=True)
            card = _scaled(card, 0.82 + 0.18 * min(1.0, p) + 0.06 * lift)
            cx, cy = x + w / 2, y + h / 2
            sh = _scaled(self.f_shadow, 1 + 0.25 * lift)               # the shadow spreads while the card is high
            _comp(layer, _fade(sh, 0.55 + 0.45 * (1 - lift)), int(cx - sh.width / 2 + 30 * lift),
                  int(cy - sh.height / 2 + 14 + 70 * lift))
            _comp(layer, card, int(cx - card.width / 2), int(cy - card.height / 2))
        y = self.f_foot                                                 # CTA + handle (move with the camera)
        for im, dl in ((self.end_cta, 0.0), (self.end_handle, 0.18)):
            if im is None:
                continue
            kk = _ease((te - self.f_done - 0.3 - dl) / 0.4)
            if kk > 0:
                _comp(layer, _fade(im, kk), (W - im.width) // 2, y + int((1 - kk) * 18))
            y += im.height + 4
        self._flash_ring(layer, te)
        z = 1 + 0.035 * _ease((te - self.f_done) / 1.6) if te > self.f_done else 1.0   # slow camera push-in
        if z > 1.0005:
            cy = (170 + 1400) / 2
            big = layer.resize((int(W * z), int(H * z)), Image.BICUBIC)
            x0, y0 = int(W / 2 * z - W / 2), int(cy * z - cy)
            layer = big.crop((x0, y0, x0 + W, y0 + H))
        frame.alpha_composite(layer)

    def _flash_ring(self, layer, te):
        """The progress ring (k/n as the cards land) that becomes a ✓ with a burst of sparks."""
        cx, cy = self.f_corner
        k = _ease((te - 0.3) / 0.4)
        if k <= 0:
            return
        done, lands = self.f_done, self.f_lands
        landed = sum(1 for t in lands if te >= t)
        r = 58
        c = r + 20
        ring = Image.new("RGBA", (2 * c, 2 * c), (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        d.ellipse([c - r, c - r, c + r, c + r], fill=(255, 255, 255, 245))
        box = [c - r + 6, c - r + 6, c + r - 6, c + r - 6]
        d.arc(box, 0, 360, fill=(225, 228, 234), width=10)
        prev = max([t for t in lands if t <= te], default=None)
        frac = 1.0 if landed == len(lands) else (
            (landed - 1 + _ease((te - prev) / 0.35)) / len(lands) if prev is not None else 0.0)
        if frac > 0:
            d.arc(box, -90, -90 + 360 * frac, fill=self.f_ring, width=10)
        if te >= done:
            u = min(1.0, (te - done) / 0.25)
            pts = [(c - 22, c + 2), (c - 6, c + 18), (c + 24, c - 16)]
            a = min(1.0, u * 2)
            d.line([pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * a, pts[0][1] + (pts[1][1] - pts[0][1]) * a)],
                   fill=self.f_ring, width=10)
            if u > 0.5:
                b = (u - 0.5) * 2
                d.line([pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * b, pts[1][1] + (pts[2][1] - pts[1][1]) * b)],
                       fill=self.f_ring, width=10)
        else:
            t = _text(f"{landed}/{len(lands)}", 34, INK, "Black")
            ring.alpha_composite(t, (c - t.width // 2, c - t.height // 2 - 2))
        pop = 1 + 0.18 * math.exp(-9 * (te - done)) * math.sin(18 * (te - done)) if te >= done else 1.0
        sc = (0.3 + 0.7 * min(1.0, _spring_in(te - 0.3))) * pop
        sh = _shadow_box((ring.width + 20, ring.height + 20), (10 + c - r, 16 + c - r, 10 + c + r, 16 + c + r), r, 10,
                         120, 0)
        _comp(layer, _fade(_scaled(sh, sc), k), int(cx - sh.width * sc / 2), int(cy - sh.height * sc / 2))
        _comp(layer, _fade(_scaled(ring, sc), k), int(cx - ring.width * sc / 2), int(cy - ring.height * sc / 2))
        st = te - done                                                   # the burst of sparks
        if 0 < st < 1.1:
            d = ImageDraw.Draw(layer)
            for ang, v, size, col in self.f_sparks:
                x = cx + math.cos(ang) * v * st * (1 - 0.35 * st)
                y = cy + math.sin(ang) * v * st * (1 - 0.35 * st) + 520 * st * st
                s = size * (1 - 0.5 * st)
                d.rounded_rectangle([x - s, y - s * 0.45, x + s, y + s * 0.45], 3,
                                    fill=tuple(col) + (int(255 * max(0.0, 1 - st / 1.1)),))

    def _flash_sounds(self, mx):
        for i in range(len(self.f_faces)):
            t = self.E + 0.5 + self.f_step * i
            sig, pan = mx.whoosh(0.3)
            mx.add(t, sig, 0.06, pan)
            mx.add(t + 0.22, mx.thump(), 0.10)
            mx.add(t + 0.22, mx.click(), 0.04)
        mx.add(self.E + self.f_done, mx.sparkle(), 0.12)
        mx.add(self.E + self.f_done, mx.chime(), 0.10)

    def _ar_ref(self, size, font=None):
        """(above, below): how far the recap's Arabic letters reach above / below their baseline at a size (tall
        letters with hamza / shadda to the lowest descenders) — every meaning is placed by its baseline with it."""
        font = font or self.L["ar_font"]
        im = _ar_line("أإلكجـيظ", size, INK, font)
        box = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
        base = int(size * 0.25) + get_font(int(size), "Bold", _ar_font_for(font, "أ")).getmetrics()[0]
        return base - box[1], box[3] - base

    def _ar_row(self, txt, size, col, max_w, font=None):
        """A meaning on a FIXED baseline (+ where that baseline is in the image), smaller only if it is too wide."""
        font = font or self.L["ar_font"]
        while size > 16 and _ar_line(txt, size, col, font).width - 2 * _AR_PAD > max_w:
            size = max(16, int(size * 0.94))
        im = _ar_line(txt, size, col, font)
        return im, int(size * 0.25) + get_font(int(size), "Bold", _ar_font_for(font, txt)).getmetrics()[0]

    def _draw_ending(self, frame, te):
        if self.recap == "flashcards":
            return self._draw_flash(frame, te)
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

    # -------------------------------------------------------------- time: the video <-> the clip
    def _seg(self, t):
        i = bisect.bisect_right(self.seg_o0, t) - 1
        return self.segs[max(0, min(i, len(self.segs) - 1))]

    def _c(self, t):
        """The clip time shown at video time t (held at the end once the clip is over)."""
        if t >= self.E:
            return self.clip
        sg = self._seg(t)
        d = sg["o1"] - sg["o0"]
        return sg["c0"] + (sg["c1"] - sg["c0"]) * max(0.0, min(1.0, (t - sg["o0"]) / d)) if d > 0 else sg["c0"]

    def _out(self, c):
        """The video time at which clip time c is first played."""
        for sg in self.segs:
            if sg["kind"] == "play" and sg["c0"] <= c <= sg["c1"] and sg["c1"] > sg["c0"]:
                return sg["o0"] + (c - sg["c0"]) / self.speed
        return LEAD if c <= 0 else self.segs[-1]["o1"]

    def _draw_repeat(self, frame, t, a):
        """REPEAT k/n badge while a key word is replayed (with the held frame before it)."""
        sg = self._seg(t)
        if sg["kind"] not in ("freeze", "replay") or t >= self.E:
            return
        same = [x for x in self.segs if x["gi"] == sg["gi"]]
        t0, t1 = same[0]["o0"], same[-1]["o1"]
        k = _back((t - t0) / 0.3) * min(1.0, (t1 - t) / 0.2) * a
        if k <= 0:
            return
        key = (sg["k"], sg["n"])
        if key not in self._rep_ims:
            self._rep_ims[key] = self._repeat_badge(*key)
        im = _scaled(self._rep_ims[key], 0.6 + 0.4 * min(1.0, k))
        if sg["kind"] == "freeze":   # a soft pulse while the frame is held
            im = _scaled(im, 1.0 + 0.05 * math.sin(math.pi * (t - sg["o0"]) / max(1e-6, sg["o1"] - sg["o0"])))
        if self.vertical:
            x, y = (W - im.width) // 2, int(self.cap_y + self.cap_box[0]) - im.height - 24
        else:
            x, y = self.vpos[0] + self.vsize[0] - im.width - 16, self.vpos[1] + 16
        _comp(frame, _fade(im, min(1.0, k)), int(x), int(y))

    def _repeat_badge(self, k, n):
        """An accent pill: a circular 'replay' arrow + REPEAT k/n."""
        fg = self.on_accent
        txt = _tight_text(f"REPEAT {k}/{n}" if n > 1 else "REPEAT", 34, fg, 600, "Black", MONT, pad=4)
        h = txt.height + 26
        icon = h - 22
        S = 4
        ic = Image.new("RGBA", (icon * S, icon * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(ic)
        m, wdt = int(icon * S * 0.14), int(icon * S * 0.12)
        d.arc([m, m, icon * S - m, icon * S - m], 40, 330, fill=fg + (255,), width=wdt)
        cx, cy, r = icon * S / 2, icon * S / 2, icon * S / 2 - m
        ax, ay = cx + r * math.cos(math.radians(330)), cy + r * math.sin(math.radians(330))
        tri = [(ax + wdt * 1.3, ay - wdt * 0.4), (ax - wdt * 0.9, ay - wdt * 1.4), (ax - wdt * 0.2, ay + wdt * 1.2)]
        d.polygon(tri, fill=fg + (255,))
        ic = ic.resize((icon, icon), Image.LANCZOS)
        pill = _rounded((icon + txt.width + 52, h), h // 2, self.accent + (255,))
        pill.alpha_composite(ic, (20, 11))
        pill.alpha_composite(txt, (20 + icon + 10, (h - txt.height) // 2))
        out = Image.new("RGBA", (pill.width + 30, pill.height + 30), (0, 0, 0, 0))
        out.alpha_composite(_shadow_box(out.size, (15, 19, 15 + pill.width, 19 + pill.height), h // 2, 8, 120, 0))
        out.alpha_composite(pill, (15, 15))
        return out

    # -------------------------------------------------------------- per frame
    def _video_frame(self, t):
        if self.dec is None:
            return self._placeholder()
        idx = int(round(self._c(t) * self.fps))
        idx = max(0, min(idx, int(self.clip * self.fps) - 1))
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
        if self.L["header"] == "post" and not self.vertical:
            self._draw_post(frame, t, 1 - end_p)
        if not self.vertical:
            self._draw_panel(frame, vf, t, end_p)
        if self.L["wave"] and end_p < 1:
            self._draw_wave(frame, t, 1 - end_p)
        if end_p > 0:
            dark = self.dark or self.vertical
            veil = (6, 8, 14, int(150 * end_p)) if dark else (250, 249, 246, int(170 * end_p))
            frame.alpha_composite(Image.new("RGBA", (W, H), veil))
        if end_p < 1:
            self._draw_header(frame, t, 1 - end_p)
            self._draw_captions(frame, self._c(t), 1 - end_p)
            self._draw_repeat(frame, t, 1 - end_p)
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
        p = max(0.0, min(1.0, (t - LEAD) / max(1e-6, self.E - LEAD)))   # progress line under the panel
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
        if L["header"] == "post":
            if self.vertical:
                self._draw_post(frame, t, a)
            return
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
            ImageDraw.Draw(tag).ellipse([12, cy - 6, 24, cy + 6], fill=self.on_accent + (int(255 * pulse),))
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
        centre = L["head_align"] == "center"
        for li, im in enumerate(self.head_lines):
            kk = _ease((t - 0.12 - 0.08 * li) / 0.5)
            if kk > 0:
                x = (W - im.width) // 2 if centre else 64 + int((1 - kk) * 40)
                _comp(frame, _fade(im, a * kk), x, hy - 8 + (int((1 - kk) * 14) if centre else 0))
            hy += self.head_lh
        if self.head_lines and L["head_bar"]:   # an accent bar left of the headline
            kk = _ease((t - 0.1) / 0.45)
            d.rounded_rectangle([44, top + 4, 52, top + 4 + int((hy - top - 14) * kk)], 4,
                                fill=self.accent + (int(255 * a),))

    # -------------------------------------------------------------- sound
    def sound(self, mx):
        a = _clip_sound(self.path, self.trim0, self.clip, self.speed) if self.path and self.has_audio else None
        if a is not None and len(a):
            peak = np.abs(a).max()
            a = a / (peak + 1e-9) * 0.9 * self.video_gain   # same level whatever the clip (like a voice)
            f = int(0.012 * SR)                             # short fades: no click where the clip is cut
            for sg in self.segs:
                if sg["kind"] not in ("play", "replay"):
                    continue
                seg = a[int(sg["c0"] / self.speed * SR):int(sg["c1"] / self.speed * SR)].copy()
                if len(seg) > 4 * f:
                    ramp = np.linspace(0, 1, f)[:, None]
                    seg[:f] *= ramp
                    seg[-f:] *= ramp[::-1]
                at = int(sg["o0"] * SR)
                n = min(len(seg), mx.n - at)
                if n > 0:
                    mx.voice[at:at + n] += seg[:n]
                    mx.has_voice = True
        for sg in self.segs:   # a soft rewind swish as each replay begins
            if sg["kind"] == "freeze":
                sig, pan = mx.whoosh(0.35)
                mx.add(sg["o0"], sig[::-1].copy(), 0.07, pan)
        sig, pan = mx.whoosh(0.5)
        mx.add(0.02, sig, 0.08, pan)
        for c in self.cards:   # the notification banner comes with a soft chime, the other cards with a pop
            mx.add(c["t0"], mx.chime() if self.L["card"] == "notify" else mx.pop(), 0.07 if self.L["card"] == "notify"
                   else 0.10)
        if self.ending_on and self.recap == "flashcards":
            self._flash_sounds(mx)
        elif self.ending_on:
            sig, pan = mx.whoosh(0.7)
            mx.add(self.E, sig, 0.10, pan)
            mx.add(self.E + 0.3, mx.chime(), 0.16)
            for n in range(len(self.end_rows)):
                mx.add(self.E + 0.55 + self.end_step * n, mx.pop(), 0.06)
