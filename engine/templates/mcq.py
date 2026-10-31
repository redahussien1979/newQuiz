"""Multiple Choice: several questions, each with 3-4 options, a countdown timer and a correct-answer reveal.

Questions are written as blocks separated by an empty line:
    Question text
    Option 1
    Option 2 *          <- the star marks the correct option
    Option 3
    Option 4            (optional 4th option)
    > Explanation shown after the reveal (optional)

Narration (optional): upload audio clips named after what they read, e.g.
    q1.mp3   -> question 1        q1a.mp3 / q1-b.wav / q1_3.m4a -> an option of question 1
    q1e.mp3  -> the explanation of question 1
Each question's timing stretches to fit its clips: options appear as they are read and the countdown starts after.
"""
import bisect
import math
import os
import re

from PIL import Image, ImageDraw, ImageFilter

from ..core import (GREY, WHITE, Stars, draw_ending, draw_scene, ease_out_back, fade, get_theme, global_fade,
                    make_bg, parse_lines, paste, prog, shade, stack_lines, text_img, to_rgb, wrap)
from ..audio import audio_length
from ..mcq_styles import STYLE_NAMES, Backdrop, build_box, get_style, letter_badge, with_theme_colors
from ..strings import S
from ..timers import TIMER_NAMES, draw_timer

NAME = "Multiple Choice"
OPT_COLORS = ["gold", "blue", "pink", "purple"]
GREEN = (70, 215, 120)
RED = (255, 90, 90)

EXAMPLE = {
    "template": "mcq",
    "settings": {"theme": "Night Sky", "language": "ar", "fps": 30, "music": "Pulse", "music_gain": 1.0,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": ""},
    "ending": {"intro": "النتيجة؟", "question": "كم إجابة صحيحة\n[gold]حصلت عليها من {count}؟",
               "cta": "اكتب نتيجتك في التعليقات"},
    "mcq": {
        "title": "اختبر معلوماتك!",
        "subtitle": "{count} أسئلة — هل تجيب عنها كلها؟",
        "questions": (
            "كم عدد عظام جسم الإنسان البالغ؟\n186\n206 *\n226\n306\n> يولد الطفل بنحو 300 عظمة يلتحم بعضها مع النمو\n\n"
            "ما أكبر كوكب في المجموعة الشمسية؟\nزحل\nنبتون\nالمشتري *\n> يتسع حجمه لأكثر من 1300 كوكب بحجم الأرض\n\n"
            "في أي مدينة تأسست جامعة القرويين؟\nالقيروان\nبغداد\nالقاهرة\nفاس *\n> أسستها فاطمة الفهرية سنة 859م\n\n"
            "ما الفلز السائل في درجة حرارة الغرفة؟\nالزئبق *\nالرصاص\nالصوديوم\n> الزئبق هو الفلز الوحيد السائل في الظروف العادية\n\n"
            "كم يستغرق ضوء الشمس ليصل إلى الأرض؟\nنحو 30 ثانية\nنحو 8 دقائق *\nنحو ساعة\nنحو يوم كامل\n> نحو 8 دقائق و20 ثانية"
        ),
        "think_seconds": 5,
        "reveal_seconds": 2.8,
        "accent": "gold",
        "style": "Game Show",
        "timer": "Ring",
        "colors": "style",
        "narration": [],
        "narration_gain": 1.0,
    },
}

COLOR_MODES = ["style", "theme"]
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma")
_NARR_RE = re.compile(r"^q\s*0*(\d{1,2})(?:[\s_.\-]*([a-e])|[\s_.\-]+([1-4]))?$", re.I)
GAP = 0.15  # pause between narration clips (s)


def _narr_key(path):
    """'q3' -> (3, 'q'), 'q3b' / 'q3_2' -> (3, 1), 'q3e' -> (3, 'e'); None if the name does not match."""
    stem, ext = os.path.splitext(os.path.basename(str(path)))
    mt = _NARR_RE.match(stem.strip())
    if not mt or ext.lower() not in AUDIO_EXT:
        return None
    qn = int(mt.group(1))
    if mt.group(3):
        return qn, int(mt.group(3)) - 1
    letter = (mt.group(2) or "").lower()
    if not letter:
        return qn, "q"
    return qn, ("e" if letter == "e" else "abcd".index(letter))


def match_narration(paths, qs):
    """Map uploaded clips to questions. Returns ({(q_index, slot): path}, [problems])."""
    found, problems = {}, []
    for path in paths or []:
        if not path or not os.path.isfile(str(path)):
            continue
        name = os.path.basename(str(path))
        key = _narr_key(path)
        if key is None:
            problems.append(f"`{name}`: name not recognised (use q1, q1a … q1d, q1e)")
            continue
        qn, slot = key
        if not 1 <= qn <= len(qs):
            problems.append(f"`{name}`: there is no question {qn}")
            continue
        if isinstance(slot, int) and slot >= len(qs[qn - 1]["opts"]):
            problems.append(f"`{name}`: question {qn} has only {len(qs[qn - 1]['opts'])} options")
            continue
        if not qs[qn - 1]["expl"] and slot == "e":
            problems.append(f"`{name}`: question {qn} has no explanation line (> …), clip is still played")
        if (qn - 1, slot) in found:
            problems.append(f"`{name}`: replaces `{os.path.basename(found[(qn - 1, slot)])}`")
        found[(qn - 1, slot)] = str(path)
    return found, problems


def narration_report(paths, questions_text):
    """Short Markdown summary of which clips belong to which question (for the app)."""
    paths = [p for p in (paths or []) if p]
    if not paths:
        return "No narration clips yet."
    try:
        qs = parse_questions(questions_text)
    except ValueError as e:
        return f"⚠️ Fix the questions first: {e}"
    found, problems = match_narration(paths, qs)
    rows = []
    letters = "ABCD"
    for i, q in enumerate(qs):
        parts = (["question"] if (i, "q") in found else []) + \
                [letters[k] for k in range(len(q["opts"])) if (i, k) in found] + \
                (["explanation"] if (i, "e") in found else [])
        rows.append(f"**Q{i + 1}:** " + (", ".join(parts) if parts else "—"))
    out = " · ".join(rows)
    if problems:
        out += "\n\n⚠️ " + "  \n⚠️ ".join(problems)
    return out


def parse_questions(text):
    qs = []
    blocks = [b for b in str(text or "").replace("\r", "").split("\n\n") if b.strip()]
    for n, block in enumerate(blocks, 1):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        expl = " ".join(l.lstrip(">»").strip() for l in lines if l.startswith((">", "»")))
        lines = [l for l in lines if not l.startswith((">", "»"))]
        if len(lines) < 3:
            raise ValueError(f"Question {n}: write the question, then 2-4 options on separate lines.")
        q, opts, correct = lines[0], [], []
        for k, o in enumerate(lines[1:]):
            if o.startswith("*") or o.endswith("*"):
                correct.append(k)
                o = o.strip("*").strip()
            opts.append(o)
        if len(opts) > 4:
            raise ValueError(f"Question {n}: maximum 4 options (found {len(opts)}).")
        if len(correct) != 1:
            raise ValueError(f"Question {n}: mark exactly ONE correct option with * at the end of its line.")
        qs.append(dict(q=q, opts=opts, correct=correct[0], expl=expl))
    if not qs:
        raise ValueError("Add at least one question.")
    return qs[:10]


class MCQVideo:
    def __init__(self, project):
        s = project.get("settings", {})
        m = project.get("mcq", {})
        e = project.get("ending", {})
        self.lang = s.get("language", "ar")
        self.rtl = self.lang == "ar"
        self.L = S(self.lang)
        self.fps = int(s.get("fps", 30))
        self.accent = to_rgb(m.get("accent") or "gold")
        self.st = get_style(m.get("style"))
        self.timer = m.get("timer") if m.get("timer") in TIMER_NAMES else "Ring"
        if m.get("colors") == "theme":
            self.st = with_theme_colors(self.st, s.get("theme"))
        self.backdrop = Backdrop(self.st, s.get("theme"), self.accent)
        self.ink = self.st["ink"]
        self.card_ink = self.st["card_text"]
        self.qs = parse_questions(m.get("questions", ""))
        self.T = max(2.0, float(m.get("think_seconds") or 5))
        self.R = max(1.5, float(m.get("reveal_seconds") or 2.8))
        self.q0 = 2.6
        self.narr_gain = float(m.get("narration_gain") if m.get("narration_gain") is not None else 1.0)
        narr, _ = match_narration(m.get("narration") or [], self.qs)
        t = self.q0
        for i, q in enumerate(self.qs):
            self._plan(i, q, narr)
            q["t0"] = t
            t += q["D"]
        self.starts = [q["t0"] for q in self.qs]
        self.E = t
        self.base_duration = self.dur = self.E + 4.0
        self.silences = []
        if self.st["card"] is None:
            self.st = dict(self.st, card=get_theme(s.get("theme"))["card"])
        self.glow = self._glow()

        def fill(txt):  # {count} = number of questions in this video
            return str(txt or "").replace("{count}", str(len(self.qs)))
        title = parse_lines(fill(m.get("title", "")), [self.ink])
        sub = fill(m.get("subtitle", ""))
        lines = stack_lines(title, 720, 120, 96)
        if sub:
            sub_col = shade(self.accent, 0.62) if self.st.get("light") else self.accent  # readable on light pages
            lines.append((sub, 54, sub_col, (lines[-1][3] if lines else 720) + 150))
        self.scenes = [dict(t_in=0.1, t_out=2.4, lines=lines)]
        self.ending = (fill(e.get("intro", "")), parse_lines(fill(e.get("question", "")), ["white", "gold"]),
                       fill(e.get("cta", "")), s.get("handle", ""))

    # ------------------------------------------------------------ timing
    def _plan(self, i, q, narr):
        """Per-question timing (seconds from the question start). Without narration this is the classic
        0.9 s intro + think time + reveal time; with clips the intro stretches so every clip is heard first."""
        q["voice"] = []
        cur = 0.35  # first clip starts when the card has landed
        if (i, "q") in narr:
            q["voice"].append((cur, narr[(i, "q")]))
            cur += audio_length(narr[(i, "q")]) + GAP
        opt_audio = any((i, k) in narr for k in range(len(q["opts"])))
        q["opt_t"] = []
        for k in range(len(q["opts"])):
            if not opt_audio:
                q["opt_t"].append(0.35 + 0.12 * k)
            elif (i, k) in narr:
                q["opt_t"].append(cur)
                q["voice"].append((cur, narr[(i, k)]))
                cur += audio_length(narr[(i, k)]) + GAP
            else:
                q["opt_t"].append(cur)
                cur += 0.3
        q["ts"] = max(0.9, cur + 0.2) if q["voice"] else 0.9  # countdown start
        q["r"] = q["ts"] + self.T  # reveal
        rev = self.R
        if (i, "e") in narr:
            q["voice"].append((q["r"] + 0.3, narr[(i, "e")]))
            rev = max(rev, 0.3 + audio_length(narr[(i, "e")]) + 0.6)
        q["D"] = q["r"] + rev

    # ------------------------------------------------------------ assets
    def _assets(self, i):
        """Card and option images for question i, built the first time it is shown (keeps previews fast)."""
        q = self.qs[i]
        if "card" not in q:
            card_bg = self.st["card"]
            q["card"] = self._question_card(q["q"], card_bg)
            top = 560 + q["card"].height / 2 - 40
            q["opt_y0"] = max(860, int(top + 110))
            q["imgs"] = [self._option(k, o, to_rgb(self.st["palette"][k]), card_bg, False) for k, o in enumerate(q["opts"])]
            q["ok_img"] = self._option(q["correct"], q["opts"][q["correct"]], GREEN, card_bg, True)
            q["expl_lines"] = wrap(q["expl"], 40, "SemiBold", 900)[:2] if q["expl"] else []
        return q

    def _question_card(self, txt, card_bg):
        size = 62
        lines = wrap(txt, size, "Bold", 840)
        if len(lines) > 3:
            size = 50
            lines = wrap(txt, size, "Bold", 860)[:4]
        pitch = int(size * 1.4)
        cw, ch = 960, 70 + pitch * len(lines)
        im = build_box(cw, ch, 40, self.st, self.accent, card=True)
        for k, line in enumerate(lines):
            li = text_img(line, size, self.card_ink, "Bold", shadow=False, max_w=880)
            im.alpha_composite(li, (40 + cw // 2 - li.width // 2, int(40 + 35 + k * pitch + pitch / 2 - li.height / 2)))
        return im

    def _option(self, k, txt, col, card_bg, correct):
        w, h, m = 920, 112, 30
        im = build_box(w, h, m, self.st, col, correct=correct)
        cx = (m + w - 70) if self.rtl else (m + 70)
        cy = m + h / 2
        letter_badge(im, cx, cy, lambda t_, sz, c: text_img(t_, sz, c, "Black", shadow=False),
                     self.L["letters"][k], col, self.st, correct)
        tc = (30, 60, 40) if correct and (self.st.get("light") or self.st.get("light_cards")) else self.card_ink
        t = text_img(txt, 50, tc, "Bold", shadow=False, max_w=w - 190)
        x = (m + w - 130 - t.width) if self.rtl else (m + 130)
        im.alpha_composite(t, (int(x), int(cy - t.height / 2)))
        return im

    def _glow(self):
        w, h, m = 920, 112, 50
        g = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle([m, m, m + w, m + h], 34, fill=GREEN + (230,))
        return g.filter(ImageFilter.GaussianBlur(22))

    # ------------------------------------------------------------ render
    def render(self, t):
        frame = self.backdrop.draw(t)
        d = ImageDraw.Draw(frame)
        n = len(self.qs)
        i = bisect.bisect_right(self.starts, t) - 1 if self.q0 <= t < self.E else -1
        if 0 <= i < n:
            self._question(frame, d, i, t - self.qs[i]["t0"])
        for sc in self.scenes:
            draw_scene(frame, t, sc)
        draw_ending(frame, t, self.E, *self.ending, self.accent)
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

    def _question(self, frame, d, i, u):
        q, n = self._assets(i), len(self.qs)
        D, T = q["D"], self.T
        r, ts = q["r"], q["ts"]
        out = prog(u, D - 0.3, D)
        a_in = prog(u, 0, 0.3)

        # header + progress dots
        light = self.st.get("light")
        hdr = text_img(self.L["question"].format(i=i + 1, n=n), 46, (32, 30, 40) if light else self.accent, "Black", shadow=False)
        pill = Image.new("RGBA", (hdr.width + 20, 86), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle([0, 6, pill.width - 1, 80], 37,
                                               fill=(self.accent if light else shade(self.accent, 0.22)) + (255,))
        pill.alpha_composite(hdr, (10, 43 - hdr.height // 2))
        paste(frame, pill, 540, 285, 1.0, a_in * (1 - out))
        gap = 34
        x0 = 540 - (n - 1) * gap / 2
        for k in range(n):
            x = x0 + (k if not self.rtl else (n - 1 - k)) * gap
            rr = 10 if k == i else 7
            col = self.accent if k == i else (shade(self.ink, 0.6) if k < i else ((200, 190, 170) if light else (70, 80, 105)))
            al = int(255 * a_in * (1 - out))
            d.ellipse([x - rr, 372 - rr, x + rr, 372 + rr], fill=col + (al,))

        # question card
        p = prog(u, 0.05, 0.45)
        paste(frame, q["card"], 540, 560 - out * 60, 0.85 + 0.15 * ease_out_back(p), min(1, p * 1.5) * (1 - out))

        # options
        for k, img in enumerate(q["imgs"]):
            y = q["opt_y0"] + k * 140
            pk = prog(u, q["opt_t"][k], q["opt_t"][k] + 0.35)
            dx = (1 - ease_out_back(pk)) * (320 if self.rtl else -320)
            alpha = min(1, pk * 1.5) * (1 - out)
            if u >= r:
                if k == q["correct"]:
                    pr = prog(u, r, r + 0.25)
                    pulse = 1 + 0.06 * math.sin(math.pi * prog(u, r, r + 0.4))
                    paste(frame, self.glow, 540, y, pulse, (0.55 + 0.3 * math.sin((u - r) * 5)) * pr * (1 - out))
                    paste(frame, img, 540, y, pulse, alpha * (1 - pr))
                    paste(frame, q["ok_img"], 540, y, pulse, alpha * pr)
                    continue
                alpha *= 1 - 0.65 * prog(u, r, r + 0.3)
            paste(frame, img, 540 + dx, y, 1.0, alpha)

        # timer ring, then explanation
        ty = q["opt_y0"] + (len(q["opts"]) - 1) * 140 + 150
        ty = min(ty, 1450)
        if ts - 0.3 <= u < r + 0.2:
            rem = 1 - prog(u, ts, r)
            left = max(0, math.ceil(r - u)) if u >= ts else int(T)
            col = RED if (r - u) <= 2 and u >= ts else self.accent
            a = prog(u, ts - 0.3, ts) * (1 - prog(u, r, r + 0.2))
            total = int(math.ceil(T))
            draw_timer(self.timer, frame, 540, ty, rem, min(total, left), total, col, self.ink, max(0.0, u - ts), a, self.rtl)
        if q["expl_lines"] and u >= r + 0.2:
            pe = prog(u, r + 0.2, r + 0.5)
            for k, line in enumerate(q["expl_lines"]):
                paste(frame, text_img(line, 40, self.ink, "SemiBold", shadow=not self.st.get("light"), max_w=960), 540, ty - 20 + k * 58,
                      0.9 + 0.1 * pe, pe * (1 - out))

    # ------------------------------------------------------------ sound
    def sound(self, mx):
        mx.add(0.05, mx.hit(1.6), 0.55)
        for i, q in enumerate(self.qs):
            t0, ts = q["t0"], q["t0"] + q["ts"]
            s, pn = mx.whoosh(0.8)
            mx.add(t0 - 0.05, s, 0.45, pn[::-1] if self.rtl else pn)
            for k in range(len(q["opts"])):
                mx.add(t0 + q["opt_t"][k] + 0.05, mx.pop(), 0.22)
            secs = int(math.ceil(self.T))
            for k in range(secs):
                hi = k >= secs - 2
                mx.add(ts + k, mx.tick(2400 if hi else 1500), 0.32 if hi else 0.24)
            if self.timer == "Fuse":
                mx.add(ts, mx.sizzle(self.T), 0.22)
            mx.add(t0 + q["r"], mx.ding(), 0.55)
            for off, path in q["voice"]:
                mx.add_voice(path, t0 + off, self.narr_gain)
        mx.add(self.E + 0.2, mx.chime(), 0.3)
