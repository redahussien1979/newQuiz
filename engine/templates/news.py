"""English in News: a short news clip (your own video) with big subtitles. The subtitles follow the speech word by word
(the timings come from ElevenLabs speech-to-text), the key words you pick are marked in the subtitles and, when they
are spoken, a card pops up with the word and its Arabic meaning. A recap of every key word closes the video.

Words box (the project's `news.words`, the same columns as 📖 English Texts):
    word | start | end | highlighted | arabic
one spoken word per line, times in seconds in the uploaded video. A line with something in `highlighted` is a key
word (`*` = the word itself); neighbouring lines with the same several-word highlighted text are one phrase.

Layout: a landscape / square video sits in a framed panel near the top over a blurred, darkened copy of itself; a
vertical video fills the screen. Subtitles and the word card stay inside the Shorts safe area (above y 1536).
The source video is decoded by FFmpeg as it is needed; render(t) depends only on t (frames are drawn on several
processes, each with its own decoder, in long runs of frames: `chunk`).
"""
import math
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..audio import SR, load_audio
from ..core import H, ROOT, W, ffmpeg_exe, get_font
from .text import (DEFAULT_LOGO, LABEL, PLEX_AR, _ar_fit, _comp, _fade, _groups, _shadow_box, _spring, logo_badge,
                   parse_words)

NAME = "English in News"

LEAD = 0.7                  # the header comes in over the first frame before the clip plays
ENDING_LEN = 5.0
CARD_MIN, CARD_HOLD = 1.8, 4.2
SAFE_BOTTOM = 1536
CAP_SIZE = 62
CAP_MAX_W = 900
ACCENTS = {"red": (228, 30, 48), "blue": (28, 110, 230), "teal": (0, 150, 150), "orange": (240, 120, 20),
           "purple": (126, 64, 210)}
ACCENT_CHOICES = [("News red", "red"), ("Blue", "blue"), ("Teal", "teal"), ("Orange", "orange"),
                  ("Purple", "purple")]
MARK = (255, 214, 10)       # the key-word marker in the subtitles
INK = (20, 22, 28)
_SENT_END = re.compile(r"[.!?…][\"'”’)\]]*$")

EXAMPLE = {
    "template": "news",
    "settings": {"theme": "Night Sky", "language": "en", "fps": 30, "music": "None", "music_gain": 0.4,
                 "music_file": "", "voice_file": "", "voice_offset": 0.0, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": "", "intro_sound": "None", "tick_sound": "Classic",
                 "tick_gain": 1.0},
    "ending": {"intro": "Words from the news", "question": "", "cta": "Follow for English from the news every day"},
    "news": {
        "video": "",
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
    import io
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
def _font(size, weight="Bold"):
    return get_font(int(size), weight, LABEL)


def _text(txt, size, col, weight="Bold", stroke=0, stroke_col=(0, 0, 0)):
    """One line of Latin text as a tight RGBA image (+ the pad around the ink box)."""
    f = _font(size, weight)
    asc, desc = f.getmetrics()
    pad = 6 + stroke
    w = int(math.ceil(f.getlength(txt))) + 2 * pad
    im = Image.new("RGBA", (max(1, w), asc + desc + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), txt, font=f, fill=tuple(col) + (255,), stroke_width=stroke,
                            stroke_fill=tuple(stroke_col) + (255,))
    return im


def _fit_text(txt, size, col, max_w, weight="Bold", min_size=30):
    im = _text(txt, size, col, weight)
    if im.width > max_w:
        im = _text(txt, max(min_size, int(size * max_w / im.width)), col, weight)
    return im


def _wrap(txt, size, weight, max_w, max_lines=2):
    f = _font(size, weight)
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


# ------------------------------------------------------------------ the video
class NewsVideo:
    chunk = 45                    # frames per job when rendering on several processes (fewer decoder restarts)

    def __init__(self, project):
        s = project.get("settings", {}) or {}
        n = dict(EXAMPLE["news"])
        n.update({k: v for k, v in (project.get("news", {}) or {}).items() if v is not None})
        e = project.get("ending", {}) or {}
        self.fps = int(s.get("fps") or 30)
        self.handle = str(s.get("handle") or "").strip()
        self.accent = ACCENTS.get(n.get("accent"), ACCENTS["red"])
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
        else:               # a framed panel near the top
            pw = 1000
            ph = min(720, int(round(pw * sh / sw)))
            pw = min(pw, int(round(ph * sw / sh)))
            self.vsize = (pw // 2 * 2, ph // 2 * 2)
            self.vpos = ((W - self.vsize[0]) // 2, 360)
        self.dec = _Decoder(self.path, self.vsize, self.fps, self.trim0) if self.path else None

        # words (times relative to the clip, then to the video)
        words = parse_words(n.get("words"))
        self.words = []
        for w in words:
            s0, e0 = w["s"] - self.trim0, w["e"] - self.trim0
            if e0 <= 0 or s0 >= self.clip:
                continue
            self.words.append(dict(w, s=LEAD + max(0.0, s0), e=LEAD + min(self.clip, e0)))
        self.groups = [g for g in _groups(self.words)]
        for g in self.groups:
            g["t0"] = self.words[g["i0"]]["s"]
            g["t1"] = self.words[g["i1"]]["e"]
        self.key_of = {}
        for gi, g in enumerate(self.groups):
            for k in range(g["i0"], g["i1"] + 1):
                self.key_of[k] = gi

        self.E = LEAD + self.clip                     # the clip ends
        self.ending_on = bool(n.get("ending_on", True)) and bool(self.groups)
        self.base_duration = self.E + (ENDING_LEN if self.ending_on else 0.6)
        self.dur = self.base_duration

        self._layout(n)

    # -------------------------------------------------------------- layout (once)
    def _layout(self, n):
        A = self.accent
        # header: [logo] LABEL / [TAG] headline
        logo = n.get("logo") or DEFAULT_LOGO
        self.logo = logo_badge(logo, 92, n.get("logo_shape") or "circle")
        name = str(n.get("brand_name") or "").strip().upper()
        self.brand_im = _text(name, 30, (255, 255, 255), "Black") if name else None
        self.label_im = _text(self.label, 26, (255, 255, 255), "Bold") if self.label else None
        self.tag_im = None
        if self.tag:
            t = _text(self.tag, 28, (255, 255, 255), "Black")
            pill = _rounded((t.width + 44, t.height + 6), (t.height + 6) // 2, A + (255,))
            pill.alpha_composite(t, (30, 3))
            ImageDraw.Draw(pill).ellipse([12, pill.height // 2 - 6, 24, pill.height // 2 + 6], fill=(255, 255, 255))
            self.tag_im = pill
        hl_size, lines = 56, None
        while hl_size >= 36:
            lines = _wrap(self.headline, hl_size, "ExtraBold", 930, 2)
            if lines:
                break
            hl_size -= 2
        lines = lines or [self.headline]
        self.head_lines = [_text(ln, hl_size, (255, 255, 255), "ExtraBold") for ln in lines if ln]

        if self.vertical:
            self.cap_y, self.card_y = 1150, 1290
        else:
            self.cap_y = self.vpos[1] + self.vsize[1] + 70
            self.card_y = max(self.cap_y + 210, 1180)
        self.head_y = 110
        if not self.vertical:  # the panel goes under the headline
            head_bottom = self.head_y + 120 + sum(im.height - 12 for im in self.head_lines)
            self.vpos = (self.vpos[0], max(330, head_bottom + 40))
            self.cap_y = self.vpos[1] + self.vsize[1] + 70
            self.card_y = max(self.cap_y + 210, 1180)

        # panel frame (landscape)
        if not self.vertical:
            pw, ph = self.vsize
            self.mask = _round_mask(self.vsize, 26)
            pad = 40
            self.shadow = _shadow_box((pw + 2 * pad, ph + 2 * pad), (pad, pad + 10, pad + pw, pad + ph + 10), 30,
                                      18, 150, 0)
            self.rim = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            S = 3
            big = Image.new("RGBA", (pw * S, ph * S), (0, 0, 0, 0))
            ImageDraw.Draw(big).rounded_rectangle([1, 1, pw * S - 2, ph * S - 2], 26 * S,
                                                  outline=(255, 255, 255, 70), width=3 * S)
            self.rim = big.resize((pw, ph), Image.LANCZOS)
        # shading over a full-screen video: dark at the top (header) and the bottom (subtitles)
        y = np.linspace(0, 1, H)[:, None]
        a = np.clip((0.30 - y) / 0.30, 0, 1) ** 1.4 * 0.75 + np.clip((y - 0.45) / 0.40, 0, 1) ** 1.3 * 0.82
        if not self.vertical:
            a = 0.45 + 0.3 * np.clip((y - 0.5) / 0.5, 0, 1)
        sh = np.zeros((H, W, 4), np.uint8)
        sh[..., :3] = (6, 8, 14)
        sh[..., 3] = np.broadcast_to(np.clip(a, 0, 1) * 255, (H, W)).astype(np.uint8)
        self.shade = Image.fromarray(sh, "RGBA")

        self._layout_captions()
        self._layout_cards()
        if self.ending_on:
            self._layout_ending()

    def _layout_captions(self):
        """Words -> subtitle pages of one or two lines, each word placed once."""
        f = _font(CAP_SIZE, "ExtraBold")
        space = f.getlength(" ")
        pages, cur = [], []

        def lines_of(idx):
            lines, row, x = [], [], 0.0
            for i in idx:
                w = f.getlength(self.words[i]["w"])
                if row and x + space + w > CAP_MAX_W:
                    lines.append(row)
                    row, x = [], 0.0
                row.append(i)
                x += (space if len(row) > 1 else 0) + w
            if row:
                lines.append(row)
            return lines

        for i, w in enumerate(self.words):
            if cur:
                prev = self.words[cur[-1]]
                gap = w["s"] - prev["e"]
                too_long = w["e"] - self.words[cur[0]]["s"] > 3.4
                sent = _SENT_END.search(prev["w"]) and len(cur) >= 3
                key_split = self.key_of.get(i) is not None and self.key_of.get(i) == self.key_of.get(cur[-1])
                if not key_split and (gap > 0.7 or too_long or sent or len(lines_of(cur + [i])) > 2):
                    pages.append(cur)
                    cur = []
            cur.append(i)
        if cur:
            pages.append(cur)

        self.pages = []
        lh = int(CAP_SIZE * 1.32)
        for k, idx in enumerate(pages):
            t0 = self.words[idx[0]]["s"] - 0.12
            nxt = self.words[pages[k + 1][0]]["s"] - 0.12 if k + 1 < len(pages) else self.E
            t1 = min(nxt, self.words[idx[-1]]["e"] + 1.2)
            items = []
            for li, row in enumerate(lines_of(idx)):
                ims = [self._cap_word(i) for i in row]
                total = sum(im[0].width - 2 * im[2] for im in ims) + space * (len(row) - 1)
                x = (W - total) / 2
                for i, (white, dark, pad) in zip(row, ims):
                    items.append(dict(i=i, white=white, dark=dark, pad=pad, x=x, line=li))
                    x += white.width - 2 * pad + space
            nl = max(it["line"] for it in items) + 1
            self.pages.append(dict(t0=t0, t1=t1, items=items, lines=nl, lh=lh))

    def _cap_word(self, i):
        txt = self.words[i]["w"]
        white = _text(txt, CAP_SIZE, (255, 255, 255), "ExtraBold", stroke=4, stroke_col=(10, 12, 18))
        dark = _text(txt, CAP_SIZE, INK, "ExtraBold", stroke=4, stroke_col=MARK)
        return white, dark, 6 + 4

    def _layout_cards(self):
        """The key-word card: KEY WORD n/N · the English · a line · the Arabic. When each is on screen."""
        A = self.accent
        self.cards = []
        n = len(self.groups)
        for gi, g in enumerate(self.groups):
            cw = 860
            label = _text(f"KEY WORD  {gi + 1}/{n}", 26, A, "Black")
            en = _fit_text(g["text"], 88, INK, cw - 80, "ExtraBold")
            ar = _ar_fit(g["ar"], 76, A, PLEX_AR, cw - 80) if g["ar"] else None
            ch = 40 + label.height + en.height - 4 + (24 + ar.height if ar is not None else 0) + 34
            card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
            card.alpha_composite(_shadow_box(card.size, (40, 48, 40 + cw, 48 + ch), 36, 20, 120, 0))
            body = _rounded((cw, ch), 36, (255, 255, 255, 255))
            band = Image.new("RGBA", (cw, 10), A + (255,))
            body.paste(band, (0, 0), _round_mask((cw, 40), 36).crop((0, 0, cw, 10)))
            card.alpha_composite(body, (40, 40))
            y = 40 + 34
            card.alpha_composite(label, (40 + (cw - label.width) // 2, y))
            y += label.height - 4
            card.alpha_composite(en, (40 + (cw - en.width) // 2, y))
            y += en.height
            if ar is not None:
                d = ImageDraw.Draw(card)
                d.line([(40 + cw / 2 - 60, y + 6), (40 + cw / 2 + 60, y + 6)], fill=(225, 228, 232), width=3)
                y += 24
                card.alpha_composite(ar, (40 + (cw - ar.width) // 2, y))
            t0 = g["t0"]
            nxt = self.groups[gi + 1]["t0"] if gi + 1 < n else self.E + 0.3
            t1 = min(nxt - 0.27, t0 + CARD_HOLD, self.E + 0.2)  # gone (0.25 s exit) before the next one comes
            t1 = max(t1, t0 + min(CARD_MIN, max(0.6, nxt - 0.27 - t0)))
            self.cards.append(dict(im=card, t0=t0, t1=t1, gi=gi))

    def _layout_ending(self):
        A = self.accent
        rows = [(g["text"], g["ar"]) for g in self.groups]
        n = len(rows)
        cw = 900
        row_h = max(84, min(124, int(880 / max(1, n))))
        es = int(row_h * 0.44)
        title = _fit_text(self.ending_title.upper(), 44, INK, cw - 100, "Black")
        sub = _text(f"{n} word{'s' if n != 1 else ''} from this news", 28, (120, 126, 136), "SemiBold")
        top = 54 + title.height + sub.height + 26
        ch = top + n * row_h + 40
        card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        card.alpha_composite(_shadow_box(card.size, (40, 50, 40 + cw, 50 + ch), 40, 24, 140, 0))
        card.alpha_composite(_rounded((cw, ch), 40, (255, 255, 255, 255)), (40, 40))
        card.alpha_composite(title, (40 + (cw - title.width) // 2, 40 + 40))
        card.alpha_composite(sub, (40 + (cw - sub.width) // 2, 40 + 40 + title.height - 6))
        self.end_card = card
        self.end_rows = []
        for k, (en, ar) in enumerate(rows):
            r = Image.new("RGBA", (cw - 60, row_h - 14), (0, 0, 0, 0))
            r.alpha_composite(_rounded(r.size, 22, (244, 245, 248, 255)))
            num = _rounded((row_h - 44, row_h - 44), (row_h - 44) // 2, A + (255,))
            nt = _text(str(k + 1), int(row_h * 0.32), (255, 255, 255), "Black")
            num.alpha_composite(nt, ((num.width - nt.width) // 2, (num.height - nt.height) // 2 - 2))
            r.alpha_composite(num, (14, (r.height - num.height) // 2))
            half = (r.width - num.width - 60) // 2
            et = _fit_text(en, es, INK, half, "ExtraBold", 22)
            r.alpha_composite(et, (num.width + 30, (r.height - et.height) // 2 - 2))
            if ar:
                at = _ar_fit(ar, int(es * 0.95), A, PLEX_AR, half, 22)
                r.alpha_composite(at, (r.width - at.width - 20, (r.height - at.height) // 2))
            self.end_rows.append((r, 40 + 30, 40 + top + k * row_h))
        self.end_pos = ((W - card.width) // 2, max(140, (SAFE_BOTTOM - card.height) // 2 + 30))
        h = _text(self.handle, 34, (255, 255, 255), "Bold") if self.handle else None
        self.end_handle = h
        self.end_cta = _fit_text(self.cta, 32, (255, 255, 255), 900, "SemiBold") if self.cta else None

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

    def _background(self, vf, blur_more=0.0):
        if self.vertical:
            frame = Image.new("RGB", (W, H), (0, 0, 0))
            frame.paste(vf, self.vpos)
            frame = frame.convert("RGBA")
            if blur_more > 0:
                frame = frame.filter(ImageFilter.GaussianBlur(28 * blur_more))
            return frame
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
        frame.alpha_composite(self.shade)
        if not self.vertical:
            self._draw_panel(frame, vf, t, end_p)
        if end_p > 0:
            dim = Image.new("RGBA", (W, H), (6, 8, 14, int(150 * end_p)))
            frame.alpha_composite(dim)
        if end_p < 1:
            self._draw_header(frame, t, 1 - end_p)
            self._draw_captions(frame, t, 1 - end_p)
            self._draw_card(frame, t, 1 - end_p)
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
        # progress line under the panel
        p = max(0.0, min(1.0, (t - LEAD) / self.clip))
        bar_y = y + self.vsize[1] + 18
        d = ImageDraw.Draw(frame)
        d.rounded_rectangle([x, bar_y, x + self.vsize[0], bar_y + 6], 3, fill=(255, 255, 255, int(60 * a)))
        if p > 0:
            d.rounded_rectangle([x, bar_y, x + max(6, int(self.vsize[0] * p)), bar_y + 6], 3,
                                fill=self.accent + (int(255 * a),))

    def _draw_header(self, frame, t, a):
        k = _ease(t / 0.5)
        if k <= 0:
            return
        y = self.head_y
        x = 70
        dy = int((1 - k) * -30)
        al = a * k
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
            d = ImageDraw.Draw(tag)
            cy = tag.height // 2
            d.ellipse([12, cy - 6, 24, cy + 6], fill=(255, 255, 255, int(255 * pulse)))
            _comp(frame, _fade(tag, al), W - 70 - tag.width, y + dy + 26)
        hy = y + 120
        for li, im in enumerate(self.head_lines):
            kk = _ease((t - 0.12 - 0.08 * li) / 0.5)
            if kk <= 0:
                continue
            _comp(frame, _fade(im, a * kk), 64 + int((1 - kk) * 40), hy)
            hy += im.height - 12
        # an accent bar left of the headline
        if self.head_lines:
            kk = _ease((t - 0.1) / 0.45)
            ImageDraw.Draw(frame).rounded_rectangle(
                [44, y + 128, 52, y + 128 + int((hy - y - 128 - 6) * kk)], 4, fill=self.accent + (int(255 * a),))

    def _draw_captions(self, frame, t, a):
        page = next((p for p in self.pages if p["t0"] <= t < p["t1"]), None)
        if page is None:
            return
        ka = _ease((t - page["t0"]) / 0.15) * min(1.0, (page["t1"] - t) / 0.12) * a
        rise = int((1 - _ease((t - page["t0"]) / 0.2)) * 18)
        lh = page["lh"]
        base_y = self.cap_y + (0 if page["lines"] == 2 else lh // 2) + rise
        d = ImageDraw.Draw(frame)
        for it in page["items"]:
            w = self.words[it["i"]]
            y = base_y + it["line"] * lh
            x = it["x"] - it["pad"]
            gi = self.key_of.get(it["i"])
            spoken = t >= w["s"]
            speaking = w["s"] <= t < w["e"] + 0.05
            ww = it["white"].width - 2 * it["pad"]
            if gi is not None and spoken:   # the marker swipes in behind the key word
                g = self.groups[gi]
                p = _ease((t - w["s"]) / max(0.12, min(0.35, w["e"] - w["s"])))
                if p > 0:
                    x0 = it["x"] - 10
                    x1 = x0 + (ww + 20) * p
                    d.rounded_rectangle([x0, y + 4, x1, y + it["white"].height - 4], 12,
                                        fill=MARK + (int(255 * ka),))
                im = it["dark"] if p > 0.5 else it["white"]
                pop = 1.0 + 0.08 * _spring(t - g["t0"]) if it["i"] == g["i0"] else 1.0
                if abs(pop - 1) > 0.005:
                    im = im.resize((int(im.width * pop), int(im.height * pop)), Image.BILINEAR)
                    x -= (im.width - it["white"].width) // 2
                    y -= (im.height - it["white"].height) // 2
                _comp(frame, _fade(im, ka), int(x), int(y))
                continue
            alpha = ka if spoken else ka * 0.55
            im = it["white"]
            if speaking:
                d.rounded_rectangle([it["x"] - 10, y + 6, it["x"] + ww + 10, y + im.height - 6], 12,
                                    fill=self.accent + (int(235 * ka),))
            if gi is not None:  # a key word not spoken yet: underline it
                d.rounded_rectangle([it["x"], y + im.height - 12, it["x"] + ww, y + im.height - 6], 3,
                                    fill=MARK + (int(200 * alpha),))
            _comp(frame, _fade(im, alpha), int(x), int(y))

    def _draw_card(self, frame, t, a):
        for c in self.cards:
            if not (c["t0"] - 0.05 <= t < c["t1"] + 0.25):
                continue
            tin = t - c["t0"]
            k = _back(tin / 0.42)
            out = _ease((t - c["t1"]) / 0.25) if t >= c["t1"] else 0.0
            al = min(1.0, max(0.0, tin / 0.18)) * (1 - out) * a
            if al <= 0:
                continue
            im = c["im"]
            sc = 0.82 + 0.18 * k
            if abs(sc - 1) > 0.004:
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
            x = (W - im.width) // 2
            y = self.card_y + (c["im"].height - im.height) // 2 + int(out * 40)
            _comp(frame, _fade(im, al), x, y)

    def _draw_ending(self, frame, te):
        k = _back((te - 0.25) / 0.55)
        if k <= 0:
            return
        card = self.end_card.copy()
        for n, (r, rx, ry) in enumerate(self.end_rows):
            kk = _ease((te - 0.55 - 0.16 * n) / 0.35)
            if kk > 0:
                _comp(card, _fade(r, kk), rx + int((1 - kk) * 60), ry)
        sc = 0.86 + 0.14 * k
        im = card if abs(sc - 1) < 0.004 else card.resize((int(card.width * sc), int(card.height * sc)),
                                                         Image.BILINEAR)
        x, y = self.end_pos
        x += (card.width - im.width) // 2
        y += (card.height - im.height) // 2 + int((1 - min(1.0, k)) * 80)
        _comp(frame, _fade(im, min(1.0, (te - 0.25) / 0.25)), x, y)
        yb = self.end_pos[1] + card.height + 10
        for im2, delay in ((self.end_cta, 0.9 + 0.16 * len(self.end_rows)), (self.end_handle, 1.1 + 0.16 * len(self.end_rows))):
            if im2 is None:
                continue
            kk = _ease((te - delay) / 0.4)
            if kk > 0:
                _comp(frame, _fade(im2, kk), (W - im2.width) // 2, yb + int((1 - kk) * 20))
            yb += im2.height + 6

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
