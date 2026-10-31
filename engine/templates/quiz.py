"""Clue Quiz: one mystery answer, clues revealed one by one with a timer, then a big reveal."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..core import (GREY, W, WHITE, Stars, draw_ending, draw_scene, ease_io, ease_out_back, ellipsize,
                    get_theme, global_fade, make_bg, parse_lines, paste, prog, shade, stack_lines, text_img,
                    to_rgb, wrap)
from ..strings import S

NAME = "Clue Quiz"
PALETTE = ["gold", "blue", "green", "pink", "orange", "purple"]

EXAMPLE = {
    "template": "quiz",
    "settings": {"theme": "Deep Purple", "language": "ar", "fps": 30, "music": "Pulse", "music_gain": 1.0,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": ""},
    "ending": {"intro": "تحدي الحلقة القادمة:", "question": "خمّن المدينة\n[gold]من 5 أدلة فقط!",
               "cta": "كم دليلاً احتجت؟ اكتب في التعليقات"},
    "quiz": {
        "title": "خمّن… من أنا؟",
        "subtitle": "5 أدلة — حاول قبل الجواب!",
        "clues": "وُلدتُ في البصرة نحو سنة 965م\nقضيتُ سنوات في القاهرة أدرس الضوء\nأثبتُّ أن الضوء يدخل العين ولا يخرج منها\nكتابي «المناظر» غيّر علم البصريات في أوروبا\nيسمّيني كثيرون «أبو المنهج العلمي»",
        "clue_seconds": 4.0,
        "answer_intro": "الجواب…",
        "answer": "ابن الهيثم",
        "answer_sub": "عالم البصريات (965 – 1040م)",
        "answer_image": "",
        "accent": "gold",
    },
}


class QuizVideo:
    def __init__(self, project):
        s = project.get("settings", {})
        q = project.get("quiz", {})
        e = project.get("ending", {})
        self.lang = s.get("language", "ar")
        self.L = S(self.lang)
        self.theme = get_theme(s.get("theme"))
        self.bg = make_bg(self.theme)
        self.stars = Stars(seed=11) if self.theme["stars"] else None
        self.fps = int(s.get("fps", 30))
        self.accent = to_rgb(q.get("accent") or "gold")
        clues = q.get("clues", "")
        clues = clues if isinstance(clues, list) else str(clues).splitlines()
        self.clues = [c.strip() for c in clues if c.strip()][:8]
        if not self.clues:
            raise ValueError("Add at least one clue (one per line).")
        if not str(q.get("answer", "")).strip():
            raise ValueError("The answer is empty.")
        n = len(self.clues)
        self.cs = cs = max(2.0, float(q.get("clue_seconds") or 4.0))
        self.c0 = 2.6
        self.A0 = self.c0 + n * cs
        self.Hh = self.A0 + 1.7          # reveal hit
        self.E = self.Hh + 4.0
        self.base_duration = self.dur = self.E + 4.0
        self.silences = [(self.A0 + 1.2, self.A0 + 1.7)]
        self.cols = [to_rgb(PALETTE[i % len(PALETTE)]) for i in range(n)]
        card_bg = self.theme["card"]

        # clue cards + chips
        self.cards, self.chips = [], []
        for i, txt in enumerate(self.clues):
            self.cards.append(self._clue_card(i, n, txt, self.cols[i], card_bg))
            self.chips.append(self._chip(i, txt, self.cols[i], card_bg))
        # answer image
        self.ans_img = None
        img = q.get("answer_image") or ""
        if img:
            try:
                self.ans_img = self._photo(img, self.accent)
            except Exception:
                self.ans_img = None
        ay = 1170 if self.ans_img else 800
        title = parse_lines(q.get("title", ""), ["white"])
        sub = q.get("subtitle", "")
        self.title_small = title[0][0] if title else ""
        self.scenes = [
            dict(t_in=0.1, t_out=2.4, shake=False,
                 lines=stack_lines(title, 700, 120, 96) + ([(sub, 54, self.accent, 700 + 170 * max(1, len(title)))] if sub else [])),
            dict(t_in=self.A0 + 0.05, t_out=self.Hh - 0.05, shake=True,
                 lines=[(q.get("answer_intro") or self.L["answer_intro"], 130, WHITE, 800)]),
            dict(t_in=self.Hh, t_out=self.E,
                 lines=[(str(q.get("answer")).strip(), 104, self.accent, ay)] +
                       ([(q.get("answer_sub"), 52, GREY, ay + 120)] if q.get("answer_sub") else [])),
        ]
        self.ending = (e.get("intro", ""), parse_lines(e.get("question", ""), ["white", "gold"]),
                       e.get("cta", ""), s.get("handle", ""))
        rng = np.random.default_rng(5)
        self.confetti = [dict(a=rng.uniform(-math.pi * 0.95, -math.pi * 0.05), v=rng.uniform(700, 1700),
                              c=to_rgb(PALETTE[k % len(PALETTE)]), sz=rng.uniform(10, 22),
                              spin=rng.uniform(-9, 9), ph=rng.uniform(0, 6)) for k in range(110)]
        self.conf_y = 760 if self.ans_img else 800

    # ------------------------------------------------------------ assets
    def _clue_card(self, i, n, txt, col, card_bg):
        size = 62
        lines = wrap(txt, size, "Bold", 820)
        if len(lines) > 3:
            size = 52
            lines = wrap(txt, size, "Bold", 840)[:5]
        pitch = int(size * 1.45)
        cw, chh = 940, 150 + pitch * len(lines) + 40
        S2 = 2
        im = Image.new("RGBA", ((cw + 80) * S2, (chh + 80) * S2), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([40 * S2, 54 * S2, (40 + cw) * S2, (54 + chh) * S2], 44 * S2, fill=(0, 0, 0, 170))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(18 * S2)))
        ImageDraw.Draw(im).rounded_rectangle([40 * S2, 40 * S2, (40 + cw) * S2, (40 + chh) * S2], 44 * S2,
                                             fill=tuple(card_bg) + (245,), outline=col + (255,), width=4 * S2)
        im = im.resize((cw + 80, chh + 80), Image.LANCZOS)
        badge = text_img(self.L["clue"].format(i=i + 1, n=n), 44, col, "Black", shadow=False)
        pill = Image.new("RGBA", (badge.width + 10, 84), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle([0, 6, pill.width - 1, 78], 36, fill=shade(col, 0.22) + (255,))
        pill.alpha_composite(badge, (5, 42 - badge.height // 2))
        im.alpha_composite(pill, (40 + cw // 2 - pill.width // 2, 40 + 30))
        for k, line in enumerate(lines):
            li = text_img(line, size, WHITE, "Bold", shadow=False, max_w=860)
            im.alpha_composite(li, (40 + cw // 2 - li.width // 2, int(40 + 150 + k * pitch + pitch / 2 - li.height / 2)))
        return im

    def _chip(self, i, txt, col, card_bg):
        im = Image.new("RGBA", (920, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, 919, 79], 30, fill=tuple(card_bg) + (225,), outline=shade(col, 0.7) + (255,), width=2)
        rtl = self.lang == "ar"
        nx = 870 if rtl else 50
        d.ellipse([nx - 26, 14, nx + 26, 66], fill=col + (255,))
        num = text_img(str(i + 1), 34, (20, 20, 30), "Black", shadow=False)
        im.alpha_composite(num, (nx - num.width // 2, 40 - num.height // 2))
        t = text_img(ellipsize(txt, 36, "SemiBold", 760), 36, WHITE, "SemiBold", shadow=False)
        x = 820 - t.width if rtl else 100
        im.alpha_composite(t, (x, 40 - t.height // 2))
        return im

    def _photo(self, path, col):
        S2, sz, m = 2, 560, 40
        ph = ImageOps.fit(Image.open(path).convert("RGBA"), (sz * S2, sz * S2), Image.LANCZOS)
        mask = Image.new("L", ph.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, ph.width - 1, ph.height - 1], 50 * S2, fill=255)
        ph.putalpha(mask)
        im = Image.new("RGBA", ((sz + 2 * m) * S2, (sz + 2 * m) * S2), (0, 0, 0, 0))
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle([m * S2, m * S2, (m + sz) * S2, (m + sz) * S2], 50 * S2, fill=col + (200,))
        im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(22 * S2)))
        im.alpha_composite(ph, (m * S2, m * S2))
        ImageDraw.Draw(im).rounded_rectangle([m * S2, m * S2, (m + sz) * S2, (m + sz) * S2], 50 * S2,
                                             outline=col + (255,), width=6 * S2)
        return im.resize(((sz + 2 * m), (sz + 2 * m)), Image.LANCZOS)

    # ------------------------------------------------------------ render
    def render(self, t):
        frame = self.bg.copy()
        d = ImageDraw.Draw(frame)
        if self.stars:
            self.stars.draw(d, t, t * 25)
        n, cs = len(self.clues), self.cs
        cur = int((t - self.c0) // cs) if self.c0 <= t < self.A0 else (-1 if t < self.c0 else n)

        # small header during clues
        if self.title_small and self.c0 <= t < self.E:
            a = prog(t, self.c0, self.c0 + 0.4) * (1 - prog(t, self.A0, self.A0 + 0.3))
            paste(frame, text_img(self.title_small, 60, WHITE, max_w=960), 540, 330, 1.0, a)

        # current clue card
        if 0 <= cur < n:
            ts = self.c0 + cur * cs
            p = ease_out_back(prog(t, ts, ts + 0.45))
            out = prog(t, ts + cs - 0.25, ts + cs)
            card = self.cards[cur]
            dx = (1 - p) * (380 if self.lang == "ar" else -380)
            cy = 760 + out * 300
            paste(frame, card, 540 + dx, cy, 1 - 0.35 * out, min(1, prog(t, ts, ts + 0.3)) * (1 - out))
            # timer bar
            bar_y = int(cy + card.height / 2 - 6)
            rem = 1 - prog(t, ts + 0.3, ts + cs - 0.25)
            a = min(1, prog(t, ts, ts + 0.3)) * (1 - out)
            if a > 0.02:
                col = self.cols[cur]
                d.rounded_rectangle([110, bar_y, 970, bar_y + 14], 7, fill=(60, 70, 95, 255))
                w = 860 * rem
                if w > 14:
                    x0 = 970 - w if self.lang == "ar" else 110
                    d.rounded_rectangle([x0, bar_y, x0 + w, bar_y + 14], 7, fill=shade(col, 0.4 + 0.6 * a))

        # chips (previous clues)
        if self.c0 <= t < self.A0 + 0.4:
            done = min(cur, n)
            vis = list(range(max(0, done - 4), done))
            a_all = 1 - prog(t, self.A0, self.A0 + 0.35)
            for k, j in enumerate(vis):
                tj = self.c0 + (j + 1) * cs
                p = prog(t, tj - 0.05, tj + 0.3)
                paste(frame, self.chips[j], 540, 1130 + k * 94 + (1 - p) * 40, 1.0, p * a_all)

        # answer image + confetti
        if t >= self.Hh:
            if self.ans_img is not None:
                p = prog(t, self.Hh, self.Hh + 0.5)
                paste(frame, self.ans_img, 540, 760, 0.6 + 0.4 * ease_out_back(p), min(1, p * 2) * (1 - prog(t, self.E, self.E + 0.3)))
            tc = t - self.Hh
            if tc < 2.6:
                for c in self.confetti:
                    x = 540 + math.cos(c["a"]) * c["v"] * tc
                    y = self.conf_y + math.sin(c["a"]) * c["v"] * tc + 0.5 * 1700 * tc * tc
                    alpha = int(255 * (1 - tc / 2.6))
                    ang = c["ph"] + c["spin"] * tc
                    s_ = c["sz"]
                    pts = [(x + s_ * math.cos(ang + q), y + s_ * 0.55 * math.sin(ang + q)) for q in (0, 1.6, math.pi, 4.7)]
                    d.polygon(pts, fill=c["c"] + (alpha,))

        for sc in self.scenes:
            draw_scene(frame, t, sc)
        draw_ending(frame, t, self.E, *self.ending, self.accent)
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

    # ------------------------------------------------------------ sound
    def sound(self, mx):
        n, cs = len(self.clues), self.cs
        mx.intro(0.05)
        for i in range(n):
            ts = self.c0 + i * cs
            s, pn = mx.whoosh(0.8)
            mx.add(ts - 0.1, s, 0.45, pn[::-1] if self.lang == "ar" else pn)
            if i:
                mx.add(ts + 0.05, mx.pop(), 0.3)
            for k in range(1, int(cs)):
                hi = i == n - 1 and k >= int(cs) - 2
                mx.add(ts + k, mx.tick(2400 if hi else 1500), 0.3 if hi else 0.22)
        mx.add(self.A0 + 0.1, mx.riser(1.1), 0.3)
        mx.add(self.Hh - 0.03, mx.hit(2.4), 0.95)
        mx.add(self.Hh + 0.05, mx.chime(), 0.25)
        mx.add(self.E + 0.2, mx.chime(), 0.3)
