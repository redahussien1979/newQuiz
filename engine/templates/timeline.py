"""Timeline Collision: 2-5 events on a flying timeline (or any number line), gap counters, comparison bars and a reveal."""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import countries as CT
from .. import finish as FX
from .. import globe as GL
from ..core import (COLORS, GREY, H, W, WHITE, Stars, clamp, composite, draw_ending, draw_scene, ease_io, ease_out_back, fade,
                    get_theme, global_fade, make_bg, nice_step, parse_lines, paste, prog, shade, stack_lines,
                    text_img, to_rgb)
from ..icons import make_card
from ..timers import draw_timer
from ..strings import (S, amount_str, fmt_num, fmt_val, gap_str, gap_years, ratio_str, with_unit, year_str,
                       years_word)

NAME = "Timeline Collision"
DEFAULT_COLORS = ["sand", "gold", "blue", "green", "pink"]
RIBBON_Y = 1150
GLOBE_LEN = 8.2    # length of the globe intro (beats: zoom, borders, labels, hold, dim, fly into the cards)
GLOBE_HAND = 3.35  # timeline time shown when the globe hands over (the cards are in place)

EXAMPLE = {
    "template": "timeline",
    "settings": {"theme": "Night Sky", "language": "ar", "fps": 30, "music": "Tension", "music_gain": 1.0,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": ""},
    "ending": {"intro": "سؤال الحلقة القادمة:", "question": "أيّ جامعة عربية\n[gold]أقدم من أكسفورد؟",
               "cta": "اكتب جوابك في التعليقات"},
    "timeline": {
        "mode": "calendar",
        "events": [
            {"name": "الهرم الأكبر", "year": -2560, "label": "نحو 2560 ق.م", "color": "sand", "icon": "pyramid", "image": ""},
            {"name": "كليوباترا", "year": -30, "label": "توفيت 30 ق.م", "color": "gold", "icon": "ankh", "image": ""},
            {"name": "الهبوط على القمر", "year": 1969, "label": "1969 م", "color": "blue", "icon": "moon", "image": ""},
        ],
        "hook": "كليوباترا أقرب إلى\n[blue]هبوط الإنسان على القمر\n[sand]منها إلى بناء الهرم!",
        "hide_first_in_hook": True,
        "doubt": "مستحيل؟", "doubt_sub": "تابع الخط الزمني…",
        "compare_title": "قارن بنفسك…",
        "reveal": "[gold]كليوباترا أقرب إلينا\nمن الأهرامات!",
        "polish": True, "finish": True,
    },
}


def _spread(xs, D):
    """Push overlapping card centres apart (keeps clusters centred on their anchors)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    clusters = [[i] for i in order]

    def place(c):
        mean = sum(xs[i] for i in c) / len(c)
        return {i: mean + (k - (len(c) - 1) / 2) * D for k, i in enumerate(c)}

    while True:
        pos = {}
        for c in clusters:
            pos.update(place(c))
        merged = False
        for j in range(len(clusters) - 1):
            a, b = clusters[j], clusters[j + 1]
            if pos[a[-1]] + D > pos[b[0]]:
                clusters[j:j + 2] = [a + b]
                merged = True
                break
        if not merged:
            return [pos[i] for i in range(len(xs))]


# ---------------------------------------------------------------- visual effects (built once, reused per frame)
AMB_TOP, AMB_H = RIBBON_Y - 900, 1500
_amb_mask = None


def _ambient_mask():
    """Soft elliptical light centred just above the ribbon (L image, 0-255)."""
    global _amb_mask
    if _amb_mask is None:
        yy, xx = np.mgrid[0:AMB_H, 0:W]
        g = np.exp(-(((xx - 540) / 640.0) ** 2 + ((yy - 760) / 560.0) ** 2) * 2.0)
        _amb_mask = Image.fromarray((g * 255).astype(np.uint8), "L")
    return _amb_mask


def _mix(a, b, k):
    return tuple(int(a[j] + (b[j] - a[j]) * k) for j in range(3))


def _halo(card, col):
    """Coloured glow the size of an event card, shown behind the active card."""
    m = 40
    im = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([m - 6, m - 6, card.width - m + 6, card.height - m + 6], 46,
                                         fill=col + (255,))
    return im.filter(ImageFilter.GaussianBlur(26))


def _panel(col, card_bg, w=880, h=320):
    """Glass panel behind the year counter."""
    S = 2
    im = Image.new("RGBA", ((w + 40) * S, (h + 40) * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([20 * S, 20 * S, (w + 20) * S, (h + 20) * S], 36 * S,
                                         fill=tuple(card_bg) + (190,), outline=col + (150,), width=3 * S)
    return im.resize((w + 40, h + 40), Image.LANCZOS)


class _Shifted:
    """Mixer wrapper that plays every sound `off` seconds later (after the globe intro)."""

    def __init__(self, mx, off):
        self._mx, self._off = mx, off

    def add(self, t0, sig, gain=1.0, pan=0.0):
        return self._mx.add(t0 + self._off, sig, gain, pan)

    def __getattr__(self, name):
        return getattr(self._mx, name)


class TimelineVideo:
    def __init__(self, project):
        s = project.get("settings", {})
        d = project.get("timeline", {})
        e = project.get("ending", {})
        self.lang = s.get("language", "ar")
        self.L = S(self.lang)
        self.mode = d.get("mode") or "calendar"
        self.unit = str(d.get("unit") or "").strip()  # number-line mode: km, m, °C, ${n}…
        self.theme = get_theme(s.get("theme"))
        self.bg = make_bg(self.theme)
        self.stars = Stars() if self.theme["stars"] else None
        self.fps = int(s.get("fps", 30))

        evs = []
        for i, ev in enumerate(d.get("events", [])):
            code = str(ev.get("country") or "").strip().upper()
            code = code if CT.info(code) else ""
            outline = str(ev.get("outline") or "")
            outline = outline if outline and os.path.isfile(outline) else ""
            name = str(ev.get("name") or "").strip() or (CT.name(code, self.lang) if code else "")
            if not name or ev.get("year") in (None, "") or ev.get("enabled") is False:
                continue
            try:
                year = float(ev["year"])
            except (TypeError, ValueError):
                raise ValueError(f"Event '{name}': {'value' if self.mode == 'scale' else 'year'} must be a number.")
            v = -abs(year) if self.mode == "ago" else year
            col = to_rgb(ev.get("color") or DEFAULT_COLORS[len(evs) % 5])
            icon, image = ev.get("icon") or "none", ev.get("image") or ""
            if (code or outline) and not image and icon in ("none", "flag", "map"):
                # a country shows its flag on the card (or its map when the icon is "map")
                image = (CT.flag_path(code) if icon != "map" else "") or CT.map_icon(code, outline, col)
            evs.append(dict(name=name, v=v, col=col, icon=icon, image=image, code=code, outline=outline,
                            label=str(ev.get("label") or "").strip()))
        if len(evs) < 2:
            raise ValueError("The timeline needs at least 2 events, each with a name and a "
                             + ("value." if self.mode == "scale" else "year."))
        evs = sorted(evs[:5], key=lambda x: x["v"])
        self.evs = evs
        N = self.N = len(evs)
        G = self.G = N - 1
        ys = self.ys = [x["v"] for x in evs]
        span = ys[-1] - ys[0]
        if span <= 0:
            raise ValueError("Events must have different " + ("values." if self.mode == "scale" else "years."))

        # ---------------- optional scenes: guess moment, true-size maps (values must be positive)
        mev = [x for x in evs if x["code"] or x["outline"]]
        self.use_maps = bool(d.get("maps")) and len(mev) >= 2 and mev[0]["v"] > 0 and self.mode == "scale"
        pair = (mev[0], mev[-1]) if self.use_maps else (evs[0], evs[-1])
        self.use_guess = bool(d.get("guess")) and pair[0]["v"] > 0
        compact = self.use_maps or self.use_guess
        intro = str(d.get("intro") or "hook")
        if intro == "globe" and not (mev and GL.available()):
            intro = "hook"  # the globe needs at least one country (or own outline)
        self.intro = intro if intro in ("vs", "globe") else "hook"
        self.polish = bool(d.get("polish"))  # slow camera drift + push-ins on key moments
        self.finish = bool(d.get("finish"))  # bloom, vignette, grain, light leaks

        # ---------------- camera plan
        self.z_full = z_full = 680.0 / span
        self.cam_full = ys[0] + 340.0 / z_full
        FULL = (self.cam_full, z_full)
        self.s_full = min(0.48, 980.0 / (N * 560.0))
        zg = [min(max(z_full * 4, 600.0 / max(ys[i + 1] - ys[i], span * 1e-3)), z_full * 60) for i in range(G)]
        self.hidden_first = bool(d.get("hide_first_in_hook", True)) and N >= 2
        hk = ys[1:] if self.hidden_first else ys
        if len(hk) == 1:
            hook = (hk[0], z_full * 4)
        else:
            hook = ((hk[0] + hk[-1]) / 2, max(z_full, min(z_full * 4, 560.0 / (hk[-1] - hk[0]))))
        hook2 = (hook[0], hook[1] * 1.03)
        K = [(0.0, 2.6, hook, hook2), (2.6, 4.2, hook2, FULL), (4.2, 5.0, FULL, FULL), (5.0, 5.9, FULL, (ys[0], zg[0]))]
        t = 5.9
        fd = clamp(10.0 / G, 3.2, 5.0) if compact else clamp(13.0 / G, 3.5, 6.5)
        self.flights = []
        for i in range(G):
            a, b = (ys[i], zg[i]), (ys[i + 1], zg[i])
            fs, fe = t, t + fd
            K.append((fs, fe, a, b))
            last = i == G - 1
            hold = 0.0 if last else 0.8
            if not last:
                K.append((fe, fe + hold, b, (ys[i + 1], zg[i + 1])))
            unit = nice_step((ys[i + 1] - ys[i]) / 25.0)
            self.flights.append(dict(i=i, fs=fs, fe=fe, unit=unit, vis=fe + (0.4 if last else 0.55),
                                     out=fe + (0.4 if last else 0.5), col=evs[i + 1]["col"],
                                     final=self.fmt_gap(gap_years(ys[i], ys[i + 1], self.mode))))
            t = fe + hold
        K.append((t, t + 0.9, (ys[-1], zg[-1]), FULL))
        self.Tc = Tc = t + 0.9
        K.append((Tc, 1e9, FULL, FULL))
        self.K = K

        # ---------------- guess / maps or bars / reveal / ending timing
        T = Tc
        self.silences = []
        self.m_t = []  # map slide-in times (set below when the map scene is on)
        self.t_hide = Tc + 0.05 if compact else None  # the timeline fades away for the guess and the maps
        if self.use_guess:
            self.g0 = T + 0.1
            self.g_tick = self.g0 + 0.8  # 3-second countdown
            self.g_ans = self.g_tick + 3.0
            T = self.g_ans + 0.75
            self.silences.append((self.g_tick, self.g_ans - 0.6))
        if self.use_maps:
            self.m0 = T
            self.map_style = self._pick_style(str(d.get("map_style") or "auto"), mev)
            if self.map_style == "side":
                self.m_t = []
                self.side_t = [T + 0.3 + 0.4 * k for k in range(len(mev))]
                self.side_sym = self.side_t[-1] + 0.7
                self.s0 = self.side_sym + 1.3
            else:
                n_ov = len(mev) - (1 if self.map_style == "overlay" else 2)  # tiles: the smallest fills instead
                self.m_t = [T + 0.7 + 1.35 * k for k in range(n_ov)]
                end = T + 0.7 + 1.35 * n_ov
                if self.map_style == "tiles":
                    self.tf = end
                    end += 3.2
                self.s0 = end + 0.25
        else:
            self.bars_t0 = T + 0.1
            self.s0 = self.bars_t0 + 0.25 * (G - 1) + 0.5
        self.reveal_in = self.s0 + 0.5
        self.E = self.reveal_in + (3.4 if self.use_maps else 4.55)
        self.base_duration = self.dur = self.E + 4.0
        self.silences.append((self.s0, self.s0 + 0.5))
        self.gaps = [gap_years(ys[i], ys[i + 1], self.mode) for i in range(G)]
        self.hi = min(range(G), key=lambda i: self.gaps[i])

        # ---------------- cards
        card_bg = self.theme["card"]
        for k, ev in enumerate(evs):
            sub = ev["label"] or self.fmt_pos(ev["v"])
            ev["img"] = make_card(ev["name"], sub, ev["col"], ev["icon"], ev["image"], card_bg)
        for ev in evs:
            ev["halo"] = _halo(ev["img"], ev["col"])
        self.panels = [_panel(evs[i + 1]["col"], card_bg) for i in range(G)]
        rnd = random.Random(11)
        # speed streaks: (x0, y, length, width, parallax, brightness)
        self.streaks = [(rnd.uniform(0, W + 600), rnd.uniform(RIBBON_Y - 620, RIBBON_Y + 470), rnd.uniform(90, 300),
                         rnd.choice((2, 3, 3, 4)), rnd.uniform(1.6, 4.2), rnd.uniform(0.35, 1.0)) for _ in range(30)]
        # comet sparks: (phase, vertical spread, size)
        self.sparks = [(rnd.random(), rnd.uniform(-1, 1), rnd.uniform(2.5, 6)) for _ in range(26)]
        self.rtl = self.lang == "ar"
        self._amb_cache = {}
        order = list(range(N))
        later = order[1:] if self.hidden_first else order
        for k, i in enumerate(later):
            evs[i]["t_app"] = 0.15 + 0.3 * k
        if self.hidden_first:
            evs[0]["t_app"] = 3.3
        if self.intro in ("vs", "globe"):  # the timeline appears after the VS clash / the globe
            for k, ev in enumerate(evs):
                ev["t_app"] = 2.6 + 0.12 * k

        # ---------------- scenes
        L = self.L
        hook_lines = parse_lines(d.get("hook", ""), ["white", evs[-1]["col"], evs[0]["col"]])
        doubt = d.get("doubt", "")
        self.scenes = [
            dict(t_in=1.25 if self.intro == "vs" else 0.1, t_out=2.55, lines=stack_lines(hook_lines, 330, 76, 64)),
            dict(t_in=2.65, t_out=4.95, shake=True,
                 lines=[(doubt, 160, WHITE, 410), (d.get("doubt_sub", ""), 52, GREY, 565)]),
        ]
        for f in self.flights:
            i = f["i"]
            self.scenes.append(dict(
                t_in=5.05 if i == 0 else f["fs"] - 0.15, t_out=f["out"],
                lines=[(L["frm"].format(a=evs[i]["name"]), 72, evs[i]["col"], 370),
                       (L["to"].format(b=evs[i + 1]["name"]), 72, evs[i + 1]["col"], 470)]))
        self.scenes.append(dict(t_in=(self.m0 + 0.05) if self.use_maps else self.bars_t0 - 0.05, t_out=self.s0,
                                lines=[(d.get("compare_title", ""), 84, WHITE, 430)]))
        if self.use_guess:
            self._setup_guess(d, pair)
        if self.use_maps:
            self._setup_maps(mev)
        if self.intro == "vs":
            self._setup_vs(pair)
        if self.intro == "globe":
            self._setup_globe(mev)
        self._setup_polish()
        rv = parse_lines(d.get("reveal", ""), ["white"])
        self.scenes.append(dict(t_in=self.reveal_in, t_out=self.E, lines=stack_lines(rv, 380, 88, 76)))
        self.ending = (e.get("intro", ""), parse_lines(e.get("question", ""), ["white", "gold"]),
                       e.get("cta", ""), s.get("handle", ""))
        self.accent = evs[1]["col"] if N > 2 else evs[-1]["col"]
        # the globe intro has its own length: everything after it is shifted by `off`
        self.off = GLOBE_LEN - GLOBE_HAND if self.intro == "globe" else 0.0
        if self.off:
            self.base_duration = self.dur = self.dur + self.off
            self.silences = [(a + self.off, b + self.off) for a, b in self.silences]

    # ------------------------------------------------------------ number formatting (years or any unit)
    def fmt_pos(self, v, short=False):
        if self.mode == "scale":  # ruler labels show the number only (the unit is on the cards and counter)
            return fmt_val(v, self.lang) if short else with_unit(fmt_val(v, self.lang), self.unit)
        return year_str(v, self.mode, self.lang, short=short)

    def fmt_gap(self, g):
        return amount_str(g, self.unit, self.lang) if self.mode == "scale" else gap_str(g, self.lang)

    def fmt_running(self, g):
        if self.mode == "scale":
            return "+ " + with_unit(fmt_val(g, self.lang), self.unit)
        return f"+ {fmt_num(g, self.lang)} {years_word(g, self.lang)}"

    # ------------------------------------------------------------ camera
    def camera(self, t):
        for t0, t1, a, b in self.K:
            if t <= t1:
                e = ease_io(prog(t, t0, t1))
                z = math.exp(math.log(a[1]) + (math.log(b[1]) - math.log(a[1])) * e)
                return a[0] + (b[0] - a[0]) * e, z
        return self.cam_full, self.z_full

    def card_scale(self, z):
        r = math.log(max(z, 1e-30) / self.z_full) / math.log(4)
        return clamp(self.s_full + (1 - self.s_full) * r, self.s_full, 1.0)

    # ------------------------------------------------------------ render
    def speed(self, t, h=1 / 60):
        """Camera speed in screen pixels per second."""
        a, z = self.camera(t - h)
        b, _ = self.camera(t + h)
        return abs(b - a) * z / (2 * h)

    def ambient_color(self, cam):
        """Event colour blended by where the camera is on the timeline."""
        ys, evs = self.ys, self.evs
        if cam <= ys[0]:
            return evs[0]["col"]
        for i in range(self.G):
            if cam <= ys[i + 1]:
                return _mix(evs[i]["col"], evs[i + 1]["col"], ease_io((cam - ys[i]) / (ys[i + 1] - ys[i])))
        return evs[-1]["col"]

    def background(self, col, a):
        """Theme background with the ambient light baked in (cached; colour/strength quantised invisibly)."""
        col, a = tuple(min(255, int(round(c / 6.0)) * 6) for c in col), round(a / 0.01) * 0.01
        key = (col, a)
        bg = self._amb_cache.get(key)
        if bg is None:
            bg = self.bg.copy()
            if a > 0.005:
                lay = Image.new("RGBA", (W, AMB_H), col + (0,))
                lay.putalpha(_ambient_mask().point([int(v * a) for v in range(256)]))
                bg.alpha_composite(lay, (0, AMB_TOP))
            if len(self._amb_cache) > 96:
                self._amb_cache.clear()
            self._amb_cache[key] = bg
        return bg.copy()

    # ------------------------------------------------------------ render
    def render(self, t):
        if self.off and t < GLOBE_LEN:
            return self._post(self._globe_intro(t), t, None)
        return self._post(self._compose(t - self.off), t, t - self.off)

    def _compose(self, t):
        cam, z = self.camera(t)
        flying = next((f for f in self.flights if f["fs"] <= t < f["fe"]), None)
        # ambient light: tinted by the era the camera is in, brighter while travelling
        a_amb = (0.20 + 0.16 * (flying is not None) + 0.04 * math.sin(t * 2.2)) * (1 - prog(t, self.E, self.E + 0.4))
        frame = self.background(self.ambient_color(cam), max(0.0, a_amb))
        d = ImageDraw.Draw(frame)
        if self.stars:
            self.stars.draw(d, t, (cam - self.cam_full) * z)

        # speed streaks during the flights
        if flying:
            k = clamp(self.speed(t) / 420.0) * min(1, prog(t, flying["fs"], flying["fs"] + 0.4))
            if k > 0.02:
                c = _mix(flying["col"], WHITE, 0.45)
                for x0, y, ln, wd, par, br in self.streaks:
                    x = (x0 - cam * z * par) % (W + 600) - 300
                    ln2 = int(ln * (0.4 + 0.6 * k))
                    if x + ln2 > 0 and x < W and ln2 > 1:
                        composite(frame, Image.new("RGBA", (ln2, wd), c + (int(150 * br * k),)), int(x), int(y - wd / 2))

        # timeline (ribbon, cards, counters); fades out for the guess and the maps
        tl_a = 1.0
        if self.t_hide is not None:
            tl_a = 1 - prog(t, self.t_hide, self.t_hide + 0.35)
            if not self.use_maps:  # the ribbon comes back with the comparison bars
                tl_a = max(tl_a, prog(t, self.bars_t0 - 0.35, self.bars_t0))
        if self.intro in ("vs", "globe"):
            tl_a *= prog(t, 2.45, 2.8)
        if tl_a > 0.01:
            cv = frame if tl_a >= 0.999 else Image.new("RGBA", frame.size, (0, 0, 0, 0))
            self._timeline(cv, t, cam, z, flying)
            if cv is not frame:
                frame.alpha_composite(fade(cv, tl_a))

        if not self.use_maps and t >= self.bars_t0 - 0.05:
            self._bars(frame, t)
        if self.use_guess and self.g0 <= t <= self.g_ans + 0.8:
            self._guess(frame, t)
        if self.use_maps and t >= self.m0:
            self._maps(frame, t)
        if self.intro == "vs" and t < 2.85:
            self._vs(frame, t)
        for sc_ in self.scenes:
            draw_scene(frame, t, sc_)
        draw_ending(frame, t, self.E, *self.ending, self.accent)
        return frame

    def _post(self, frame, t, te):
        """t = video time, te = timeline time (None during the globe intro)."""
        if self.polish:  # slow camera drift + push-ins (no blur of any kind)
            push = self._bump(te, self.pushes, 0.035) if te is not None else 0.0
            frame = FX.camera(frame, 1.035 + push, 9 * math.sin(t * 0.55), 7 * math.sin(t * 0.43 + 1.1))
        if self.finish:
            frame = FX.grade(frame, int(round(t * self.fps)), self._leak(te) if te is not None else 0.0)
        frame = frame.convert("RGBA")
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

    # ------------------------------------------------------------ polish
    def _setup_polish(self):
        land = []
        if self.use_maps:
            land = [tk + 0.5 for tk in self.m_t]
            if self.map_style == "tiles":
                land.append(self.tf + 2.9)
            if self.map_style == "side":
                land.append(self.side_sym)
        self.pushes = [f["fe"] for f in self.flights] + land + [self.s0 + 0.47] + \
            ([self.g_ans] if self.use_guess else [])
        self.leaks = land + [self.s0 + 0.47]

    @staticmethod
    def _bump(t, times, amount):
        """Sum of quick rise / slow fall pulses at `times` (camera push-ins)."""
        v = 0.0
        for p in times:
            x = t - p
            if -0.15 <= x < 0:
                v += amount * ease_io((x + 0.15) / 0.15)
            elif 0 <= x < 0.9:
                v += amount * (1 - x / 0.9) ** 2
        return v

    def _leak(self, t):
        return max([0.0] + [0.55 * max(0.0, 1 - abs(t - p - 0.15) / 0.35) for p in self.leaks])

    def _timeline(self, frame, t, cam, z, flying):
        sx = lambda v: 540 + (v - cam) * z
        d = ImageDraw.Draw(frame)
        # ribbon + ticks
        wave = any(f["fe"] < t < f["fe"] + 0.6 for f in self.flights)
        strip_h, ry = (300, 150) if wave else (160, 80)
        top = RIBBON_Y - ry
        strip = Image.new("RGBA", (W, strip_h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(strip)
        sd.line([(0, ry), (W, ry)], fill=(120, 135, 170, 200), width=5)
        major = nice_step((W / z) / 5.0)
        minor = major / 5.0
        left, right = cam - 560 / z, cam + 560 / z
        k0, k1 = math.floor(left / minor), math.ceil(right / minor)
        labels = []
        if k1 - k0 < 400:
            for k in range(k0, k1 + 1):
                v = k * minor
                x = sx(v)
                is_major = abs(v / major - round(v / major)) < 1e-6
                if is_major:
                    sd.line([(x, ry - 14), (x, ry + 14)], fill=(140, 155, 190, 220), width=3)
                    labels.append((v, x))
                elif minor * z >= 14:
                    sd.line([(x, ry - 7), (x, ry + 7)], fill=(140, 155, 190, 110), width=2)
        glow = Image.new("RGBA", (W, strip_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for f in self.flights:
            i = f["i"]
            if t < f["fs"]:
                continue
            end = self.ys[i + 1] if t >= f["fe"] else clamp(cam, self.ys[i], self.ys[i + 1])
            xa, xb = sx(self.ys[i]), sx(end)
            gd.line([(xa, ry), (xb, ry)], fill=f["col"] + (255,), width=26)
            sd.line([(xa, ry), (xb, ry)], fill=f["col"] + (255,), width=14)
            # arrival shockwave
            pa = prog(t, f["fe"], f["fe"] + 0.6)
            if 0 < pa < 1:
                xr, r = sx(self.ys[i + 1]), 18 + 110 * (1 - (1 - pa) ** 3)
                al = int(255 * (1 - pa))
                gd.ellipse([xr - r, ry - r, xr + r, ry + r], outline=f["col"] + (al,), width=10)
                sd.ellipse([xr - r, ry - r, xr + r, ry + r], outline=WHITE + (al,), width=3)
        if flying:
            tx = sx(cam)
            k = clamp(self.speed(t) / 420.0)
            tail = min(tx - sx(self.ys[flying["i"]]), 60 + 240 * k)
            for j in range(12):  # tapering comet tail
                q = j / 12
                r = 14 * (1 - q)
                xj = tx - tail * q
                gd.ellipse([xj - r * 2, ry - r * 2, xj + r * 2, ry + r * 2], fill=flying["col"] + (int(200 * (1 - q)),))
            for ph, vy, sz in self.sparks:  # sparks shed behind the head
                age = (t * 1.7 + ph) % 1.0
                xs = tx - age * (40 + 200 * k)
                if xs < sx(self.ys[flying["i"]]):
                    continue
                ys_ = ry + vy * age * 46
                r = sz * (1 - age)
                sd.ellipse([xs - r, ys_ - r, xs + r, ys_ + r], fill=_mix(flying["col"], WHITE, 0.5) + (int(255 * (1 - age)),))
            pr = 34 + 5 * math.sin(t * 14)
            gd.ellipse([tx - pr, ry - pr, tx + pr, ry + pr], fill=flying["col"] + (255,))
            sd.ellipse([tx - 14, ry - 14, tx + 14, ry + 14], fill=WHITE + (255,))
        strip = Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)), strip)
        frame.alpha_composite(strip, (0, top))
        for v, x in labels:
            if 50 < x < W - 50:
                paste(frame, text_img(self.fmt_pos(v, short=True), 28, GREY, "SemiBold",
                                      shadow=False, max_w=220), x, RIBBON_Y + 52, 1.0, 0.8)

        # cards
        sc = self.card_scale(z)
        D = 500 * sc + 16
        anchors = [sx(v) for v in self.ys]
        cx = _spread(anchors, D)
        if z <= self.z_full * 1.3:  # keep cards on screen in the overview
            lo, hi = 250 * sc + 12, W - 250 * sc - 12
            shift = (lo - min(cx)) if min(cx) < lo else ((hi - max(cx)) if max(cx) > hi else 0)
            cx = [c + shift for c in cx]
        for k_ev, (ev, x, xc) in enumerate(zip(self.evs, anchors, cx)):
            p = prog(t, ev["t_app"], ev["t_app"] + 0.45)
            if p <= 0 or xc < -400 or xc > W + 400:
                continue
            img = ev["img"]
            ch = img.height * sc
            cy = RIBBON_Y - 40 * sc - ch / 2 + (1 - ease_out_back(p)) * 60
            # highlight: the card the comet is flying to, and a pop when it lands
            hl, bump = 0.0, 0.0
            for f in self.flights:
                if f["i"] + 1 == k_ev:
                    if f["fs"] <= t < f["fe"]:
                        hl = max(hl, 0.35 + 0.15 * math.sin(t * 6))
                    pa = prog(t, f["fe"], f["fe"] + 0.9)
                    if 0 < pa < 1:
                        hl = max(hl, 1 - pa)
                        bump = max(bump, math.sin(pa * math.pi) * (1 - pa) * 0.18)
            s_card = sc * (0.7 + 0.3 * ease_out_back(p)) * (1 + bump)
            d.line([(x, RIBBON_Y - 10), (xc, RIBBON_Y - 80 * sc + 4)], fill=ev["col"] + (255,), width=4)
            d.ellipse([x - 11, RIBBON_Y - 11, x + 11, RIBBON_Y + 11], fill=ev["col"] + (255,), outline=WHITE + (255,), width=3)
            if hl > 0.01:
                paste(frame, ev["halo"], xc, cy, s_card, hl * min(1, p * 1.6))
            paste(frame, img, xc, cy, s_card, min(1, p * 1.6))

        self._counters(frame, t, cam)

    def _counters(self, frame, t, cam):
        for f in self.flights:
            if f["fs"] <= t <= f["vis"]:
                a = min(1, prog(t, f["fs"], f["fs"] + 0.3)) * (1 - prog(t, f["vis"] - 0.2, f["vis"]))
                paste(frame, self.panels[f["i"]], 540, RIBBON_Y + 270, 1.0, a)
                fr = clamp((cam - self.ys[f["i"]]) / (self.ys[f["i"] + 1] - self.ys[f["i"]]))
                pb = Image.new("RGBA", (720, 14), (0, 0, 0, 0))
                pd = ImageDraw.Draw(pb)
                pd.rounded_rectangle([0, 0, 719, 13], 7, fill=shade(f["col"], 0.35) + (255,))
                if fr > 0.01:  # fills in the comet's direction (the ribbon runs left to right in every language)
                    pd.rounded_rectangle([0, 0, 719 * fr, 13], 7, fill=f["col"] + (255,))
                paste(frame, pb, 540, RIBBON_Y + 395, 1.0, a)
                paste(frame, text_img(self.fmt_pos(cam), 112, WHITE, max_w=980), 540, RIBBON_Y + 200, 1.0, a)
                if t >= f["fe"]:
                    el, pop = f["final"], 1 + 0.15 * (1 - prog(t, f["fe"], f["fe"] + 0.3))
                else:
                    g = max(0.0, cam - self.ys[f["i"]])
                    el, pop = self.fmt_running(g), 1
                paste(frame, text_img(el, 64, f["col"], max_w=980), 540, RIBBON_Y + 320, pop, a)

    # ------------------------------------------------------------ guess moment
    def _setup_guess(self, d, pair):
        small, big = pair
        r = big["v"] / small["v"]
        right = ratio_str(r)
        opts = [right]
        for k in (0.5, 1.8, 0.7, 2.6, 1.35, 3.5):
            cand = r * k
            txt = ratio_str(cand)
            if cand >= 1.2 and txt not in opts:
                opts.append(txt)
            if len(opts) == 3:
                break
        n = 2
        while len(opts) < 3:  # ratios close to 1
            opts.append(ratio_str(r + n))
            n += 1
        wrong = opts[1:]
        pos = int(r * 997) % 3
        opts = wrong[:pos] + [right] + wrong[pos:]
        self.g_col = big["col"]
        L, card_bg = self.L, self.theme["card"]
        letters = L["letters"]
        self.g_imgs = [(self._opt(letters[k], txt, card_bg, False), self._opt(letters[k], txt, card_bg, True), txt == right)
                       for k, txt in enumerate(opts)]
        q = str(d.get("guess_q") or "").strip() or L["guess_area" if self.use_maps else "guess_ratio"]
        q = q.replace("{ca}", "#%02x%02x%02x" % tuple(small["col"]))  # {ca} = colour of the smaller item
        q = q.replace("{a}", small["name"]).replace("{b}", big["name"])
        lines = parse_lines(q, ["white", "white"])
        self.scenes.append(dict(t_in=self.g0, t_out=self.g_ans + 0.55, lines=stack_lines(lines, 330, 76, 64)))

    def _opt(self, letter, txt, card_bg, right):
        """Answer option pill; the 'right' version is green with a glow."""
        w, h, S = 760, 118, 2
        col = COLORS["green"] if right else self.g_col
        im = Image.new("RGBA", ((w + 60) * S, (h + 60) * S), (0, 0, 0, 0))
        if right:
            g = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(g).rounded_rectangle([30 * S, 30 * S, (w + 30) * S, (h + 30) * S], h * S // 2,
                                                fill=col + (200,))
            im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(16 * S)))
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle([30 * S, 30 * S, (w + 30) * S, (h + 30) * S], h * S // 2,
                             fill=(shade(col, 0.45) if right else tuple(card_bg)) + (235,), outline=col + (255,), width=4 * S)
        cx = (w + 30 - h / 2) if self.rtl else (30 + h / 2)
        r = h / 2 - 14
        dr.ellipse([(cx - r) * S, (30 + h / 2 - r) * S, (cx + r) * S, (30 + h / 2 + r) * S], fill=col + (255,))
        im = im.resize((w + 60, h + 60), Image.LANCZOS)
        lt = text_img(letter, 48, (15, 18, 30), "Black", shadow=False)
        im.alpha_composite(lt, (int(cx - lt.width / 2), int(30 + h / 2 - lt.height / 2)))
        tt = text_img(txt, 66, WHITE, "Black", shadow=False)
        im.alpha_composite(tt, (int(30 + w / 2 - tt.width / 2), int(30 + h / 2 - tt.height / 2)))
        return im

    def _guess(self, frame, t):
        out = 1 - prog(t, self.g_ans + 0.55, self.g_ans + 0.8)
        if out <= 0:
            return
        u = t - self.g_tick
        a_tm = prog(t, self.g_tick - 0.3, self.g_tick) * (1 - prog(t, self.g_ans + 0.1, self.g_ans + 0.35))
        if a_tm > 0.01:
            left = 3 if u <= 0 else max(0, math.ceil(3.0 - u - 1e-9))
            col = COLORS["red"] if 0 < left <= 1 else self.g_col
            draw_timer("Neon Ring", frame, 540, 730, clamp(1 - u / 3.0), left, 3, col, WHITE, max(0.0, u),
                       a_tm * out, self.rtl, ("pulse", "glow"))
        rv = prog(t, self.g_ans, self.g_ans + 0.25)
        for k, (plain, green, ok) in enumerate(self.g_imgs):
            p = prog(t, self.g0 + 0.3 + 0.12 * k, self.g0 + 0.65 + 0.12 * k)
            if p <= 0:
                continue
            y = 1010 + k * 150
            sc = (0.8 + 0.2 * ease_out_back(p)) * (1 + (0.07 * math.sin(rv * math.pi) if ok else 0))
            a = min(1, p * 1.5) * out
            if ok:
                paste(frame, plain, 540, y, sc, a * (1 - rv))
                paste(frame, green, 540, y, sc, a * rv)
            else:
                paste(frame, plain, 540, y, sc, a * (1 - 0.65 * rv))

    # ------------------------------------------------------------ true-size maps
    def _setup_maps(self, mev):
        prs = [CT.projected(x["code"], x["outline"]) for x in mev]
        km_px = min(860.0 / max(p[1] for p in prs), 700.0 / max(p[2] for p in prs))
        unit = self.unit
        for x, pr in zip(mev, prs):
            fill = 255 if x is mev[-1] else 235
            x["tile"] = CT.map_tile(x["code"], x["outline"], km_px, x["col"], 14 if x is mev[-1] else 10, True, fill)
            x["tiny"] = max(pr[1], pr[2]) * km_px < 120
            x["tag"] = CT.name_tag(x["name"], with_unit(fmt_val(x["v"], self.lang), unit), x["col"], x["code"], self.rtl)
        # overlays from the largest down to the smallest (tile fill: the smallest fills the largest instead)
        self.m_base = mev[-1]
        self.m_ovs = mev[-2::-1] if self.map_style == "overlay" else mev[-2:0:-1]
        b = self.m_base
        b["dim"] = CT.map_tile(b["code"], b["outline"], km_px, b["col"], 14, False, 90)
        self.m_grid = CT.globe_grid(tuple(b["col"]))
        if self.map_style == "tiles":
            sm = self.m_small = mev[0]
            self.m_flat = CT.flat_tile(sm["code"], sm["outline"], km_px, tuple(sm["col"]))
            self.m_cells = CT.fill_cells(b["code"], b["outline"], sm["code"], sm["outline"], km_px, 74)
        if self.map_style == "side":
            self._setup_side(mev)

    def _pick_style(self, style, mev):
        """overlay / tiles / side; 'auto' picks by the size ratio of the largest to the smallest."""
        r = mev[-1]["v"] / mev[0]["v"]
        can_tile = 2.0 <= r <= 400.0  # beyond 400 the tiles get too small to read
        if style == "tiles":
            return "tiles" if can_tile else "overlay"
        if style in ("overlay", "side"):
            return style
        if can_tile and r >= 20:
            return "tiles"
        return "side" if r <= 1.5 else "overlay"

    def _setup_side(self, mev):
        n = len(mev)
        slot = 980.0 / n
        prs = [CT.projected(x["code"], x["outline"]) for x in mev]
        km_px = min((slot - 40) / max(p[1] for p in prs), 560.0 / max(p[2] for p in prs))
        for k, x in enumerate(mev):  # smallest first: on the right in Arabic, on the left in English
            x["sx"] = (1030 - slot * (k + 0.5)) if self.rtl else (50 + slot * (k + 0.5))
            x["stile"] = CT.map_tile(x["code"], x["outline"], km_px, x["col"], 12, True, 255)
            x["pod"] = CT.podium(tuple(x["col"]), int(min(420, slot - 30)))
            x["stag"] = CT.name_tag(x["name"], with_unit(fmt_val(x["v"], self.lang), self.unit), x["col"], x["code"],
                                    self.rtl, max_w=int(min(470, slot - 26)))
        self.m_side = mev

    def _maps(self, frame, t):
        a_all = prog(t, self.m0, self.m0 + 0.4) * (1 - prog(t, self.E - 0.1, self.E + 0.3))
        if a_all <= 0:
            return
        paste(frame, self.m_grid, 540, 960, 1.0, a_all)
        if self.map_style == "side":
            self._maps_side(frame, t, a_all)
            return
        tiles = self.map_style == "tiles"
        cy, b = 1010, self.m_base
        pb = prog(t, self.m0, self.m0 + 0.6)
        sc = 0.6 + 0.4 * ease_out_back(pb)
        cur = max([k for k, tk in enumerate(self.m_t) if t >= tk], default=-1)
        dim = 0.0
        if cur >= 0 and self.m_ovs[cur]["tiny"]:
            dim = prog(t, self.m_t[cur], self.m_t[cur] + 0.4)
        if cur >= 1 and self.m_ovs[cur - 1]["tiny"]:
            dim = max(dim, 1 - prog(t, self.m_t[cur], self.m_t[cur] + 0.4))
        if tiles and t >= self.tf:
            dim = max(dim, 0.85 * prog(t, self.tf, self.tf + 0.4))
        a_b = a_all * min(1, pb * 1.6)
        paste(frame, b["tile"], 540, cy, sc, a_b * (1 - dim))
        if dim > 0:
            paste(frame, b["dim"], 540, cy, sc, a_b * dim)
        tag_x = (780, 300) if self.rtl else (300, 780)
        paste(frame, b["tag"], tag_x[0], 1580, 1.0, a_b)
        for k, ov in enumerate(self.m_ovs):
            tk = self.m_t[k]
            if t < tk:
                break
            nxt = self.m_t[k + 1] if k + 1 < len(self.m_t) else (self.tf if tiles else None)
            fo = 1 - prog(t, nxt, nxt + 0.3) if nxt else 1.0
            if fo <= 0:
                continue
            p = prog(t, tk, tk + 0.5)
            x = 540 + (1 - ease_out_back(p)) * (620 if self.rtl else -620)
            bump = 1 + 0.06 * math.sin(prog(t, tk + 0.5, tk + 0.8) * math.pi)
            a = a_all * fo * min(1, p * 2)
            paste(frame, ov["tile"], x, cy, bump, a)
            if ov["tiny"]:
                paste(frame, CT.ring(tuple(ov["col"])), x, cy, 1 + 0.08 * math.sin(t * 6), a * prog(t, tk + 0.4, tk + 0.7))
            paste(frame, ov["tag"], tag_x[1], 1580, 1.0, a)
            pc = prog(t, tk + 0.45, tk + 1.0)
            if pc > 0:
                r = b["v"] / ov["v"]
                val = 1 + (r - 1) * ease_io(pc)
                paste(frame, CT.badge(ratio_str(val), ov["col"]), 820 if self.rtl else 260, 690,
                      0.7 + 0.3 * ease_out_back(prog(t, tk + 0.45, tk + 0.75)), a_all * fo)
        if tiles and t >= self.tf:
            self._maps_tiles(frame, t, a_all, tag_x[1])

    def _maps_tiles(self, frame, t, a_all, tag_x):
        """Copies of the smallest country pop in until they fill the largest; the badge counts the real ratio."""
        b, sm = self.m_base, self.m_small
        ox, oy = 540 - b["tile"].width / 2, 1010 - b["tile"].height / 2
        fill = ease_io(prog(t, self.tf + 0.3, self.tf + 2.9))
        shown = fill * len(self.m_cells)
        for k, (x, y) in enumerate(self.m_cells):
            if k >= shown:
                break
            p = clamp(shown - k)
            paste(frame, self.m_flat, ox + x, oy + y, 0.4 + 0.6 * ease_out_back(p), a_all * min(1, p * 2))
        paste(frame, sm["tag"], tag_x, 1580, 1.0, a_all * prog(t, self.tf, self.tf + 0.4))
        if t >= self.tf + 0.3:
            r = b["v"] / sm["v"]
            done = prog(t, self.tf + 2.9, self.tf + 3.2)
            sc = 0.8 + 0.2 * ease_out_back(prog(t, self.tf + 0.3, self.tf + 0.6)) + 0.12 * math.sin(done * math.pi)
            paste(frame, CT.badge(ratio_str(1 + (r - 1) * fill), sm["col"]), 820 if self.rtl else 260, 690, sc, a_all)

    def _maps_side(self, frame, t, a_all):
        """The countries rise side by side on platforms, at the same scale."""
        mev = self.m_side
        for k, x in enumerate(mev):
            t0 = self.side_t[k]
            p = prog(t, t0, t0 + 0.7)
            if p <= 0:
                continue
            e = ease_out_back(p)
            paste(frame, x["pod"], x["sx"], 1330, 0.6 + 0.4 * e, a_all * min(1, p * 2))
            tl = x["stile"]
            paste(frame, tl, x["sx"], 1330 - tl.height / 2 + 20 + (1 - e) * 260, 0.3 + 0.7 * e, a_all * min(1, p * 2))
            paste(frame, x["stag"], x["sx"], 1520, 1.0, a_all * prog(t, t0 + 0.5, t0 + 0.9))
        pe = prog(t, self.side_sym, self.side_sym + 0.4)
        if pe <= 0:
            return
        r = mev[-1]["v"] / mev[0]["v"]
        if len(mev) == 2 and r <= 1.15:  # near-twins: "≈" and how small the difference is
            paste(frame, text_img("≈", 170, COLORS["gold"], "Black"), 540, 1000, 0.5 + 0.5 * ease_out_back(pe), a_all * pe)
            pct = (r - 1) * 100
            txt = f"{pct:.1f}".rstrip("0").rstrip(".") if pct < 10 else str(int(round(pct)))
            paste(frame, text_img(self.L["diff"].format(p=txt), 60, WHITE, max_w=960), 540, 1690, 1.0,
                  a_all * prog(t, self.side_sym + 0.4, self.side_sym + 0.8))
        else:
            paste(frame, CT.badge(ratio_str(r), mev[-1]["col"]), 540, 690, 0.6 + 0.4 * ease_out_back(pe), a_all * pe)

    # ------------------------------------------------------------ globe intro
    def _setup_globe(self, mev):
        items = [(x["code"], x["outline"]) for x in mev]
        self.gl_plan = GL.plan(items)
        self.gl_mev = mev
        self.gl_items = [(x["code"], x["outline"], tuple(x["col"])) for x in mev]
        self.gl_points = GL.label_points(items)
        self.gl_tags = [GL.tag(x["name"], x["code"], tuple(x["col"]), self.rtl) for x in mev]
        self.gl_icons = [CT.map_icon(x["code"], x["outline"], tuple(x["col"]), 420) for x in mev]
        # where each country's card (its flag circle) is when the globe hands over
        cam, z = self.camera(GLOBE_HAND)
        sc = self.card_scale(z)
        anchors = [540 + (v - cam) * z for v in self.ys]
        cx = _spread(anchors, 500 * sc + 16)
        if z <= self.z_full * 1.3:
            lo, hi = 250 * sc + 12, W - 250 * sc - 12
            shift = (lo - min(cx)) if min(cx) < lo else ((hi - max(cx)) if max(cx) > hi else 0)
            cx = [c + shift for c in cx]
        self.gl_targets = []
        for x in mev:
            i = self.evs.index(x)
            top = RIBBON_Y - 40 * sc - self.evs[i]["img"].height * sc
            self.gl_targets.append((cx[i], top + 170 * sc, sc))
        has_hook = any(line[0] for line in self.scenes[0]["lines"])
        self.gl_hook = dict(self.scenes[0], t_in=0.15, t_out=5.7) if has_hook else None

    @staticmethod
    def _smooth(x):
        x = clamp(x)
        return x * x * x * (x * (x * 6 - 15) + 10)

    def _globe_intro(self, t):
        """0-3.6 s zoom and settle, 2.6-3.8 borders draw on, 3.3-4.6 callout labels, hold, 5.8-6.5 the Earth
        dims, 6.3-7.8 the countries fly into their cards, then a short dissolve into the timeline."""
        sm = self._smooth
        lon_c, lat_c, rt = self.gl_plan
        k = sm(t / 3.6)
        lon0, lat0 = lon_c - 55 * (1 - k), lat_c * (0.35 + 0.65 * k)
        R = math.exp(math.log(470) + (math.log(max(rt, 470)) - math.log(470)) * k) * (1 + 0.03 * sm((t - 3.6) / 2.6))
        g = GL.render(lon0, lat0, R)
        dim = sm(prog(t, 5.8, 6.5))
        if dim > 0:  # the Earth dims away, the countries stay lit
            g.alpha_composite(Image.new("RGBA", (W, H), (6, 9, 20, int(235 * dim))))
        fly = sm(prog(t, 6.3, 7.8))
        draw = sm(prog(t, 2.6, 3.8))
        if draw > 0 and fly < 1:
            g.alpha_composite(fade(GL.outlines(self.gl_items, lon0, lat0, R, draw, sm(prog(t, 3.4, 4.0))), 1 - fly))
        pts = []
        for pt in self.gl_points:
            if pt is None:
                pts.append(None)
                continue
            x, y, vis = GL.to_screen(np.array([pt[0]]), np.array([pt[1]]), lon0, lat0, R)
            pts.append((float(x[0]), float(y[0])) if vis[0] else None)
        out = 1 - prog(t, 6.0, 6.4)
        shown = [i for i, p in enumerate(pts) if p is not None]
        if t >= 3.3 and out > 0 and shown:  # callouts: dot -> line -> name tag, one country after another
            xs, row_y, ks, order = GL.callout_layout([pts[i] for i in shown], [self.gl_tags[i] for i in shown])
            d = ImageDraw.Draw(g)
            for slot, j in enumerate(order):
                i = shown[j]
                ax, ay = pts[i]
                col = tuple(self.gl_mev[i]["col"])
                k0 = 3.3 + 0.3 * slot
                pd, pl, pt_ = prog(t, k0, k0 + 0.3), sm(prog(t, k0 + 0.15, k0 + 0.75)), sm(prog(t, k0 + 0.55, k0 + 1.05))
                if pd > 0:
                    r = 9 * ease_out_back(pd)
                    d.ellipse([ax - r - 5, ay - r - 5, ax + r + 5, ay + r + 5], fill=col + (int(110 * out),))
                    d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=(255, 255, 255, int(255 * out)), outline=col + (255,),
                              width=3)
                tx, ty = xs[j], row_y + (-42 if row_y > ay else 42) * ks
                if pl > 0:
                    d.line([(ax, ay), (ax + (tx - ax) * pl, ay + (ty - ay) * pl)], fill=(255, 255, 255, int(220 * out)),
                           width=3)
                if pt_ > 0:
                    paste(g, self.gl_tags[i], tx, row_y + (1 - pt_) * 30, ks * (0.9 + 0.1 * pt_), pt_ * out)
        if fly > 0:  # the countries lift off the globe and fly into their cards
            fade_out = 1 - sm(prog(t, 7.75, GLOBE_LEN))
            for i, p in enumerate(pts):
                if p is None:
                    continue
                tx, ty, sc = self.gl_targets[i]
                px = p[0] + (tx - p[0]) * fly
                py = p[1] + (ty - p[1]) * fly - math.sin(fly * math.pi) * 120
                size = 1.0 + (190 * sc / 420 / 0.84 - 1.0) * fly
                paste(g, self.gl_icons[i], px, py, size, fade_out)
        if self.gl_hook:  # the hook text over a soft shade
            ph = prog(t, 0.1, 0.5) * (1 - prog(t, 5.7, 6.1))
            if ph > 0:
                g.alpha_composite(fade(GL.hook_shade(), ph))
                draw_scene(g, t, self.gl_hook)
        kx = sm(prog(t, GLOBE_LEN - 0.4, GLOBE_LEN))
        if kx > 0:  # dissolve into the timeline, where the cards already are
            g = Image.blend(g, self._compose(GLOBE_HAND - 0.4 * (1 - kx)).convert("RGBA"), kx)
        return g

    # ------------------------------------------------------------ VS intro
    def _setup_vs(self, pair):
        a, b = pair  # a = smaller / first, shown on the reading side (right in Arabic)
        sides = ("right", "left") if self.rtl else ("left", "right")
        self.vs = []
        for ev, side in zip((a, b), sides):
            if ev["code"] or ev["outline"]:
                emb = CT.map_icon(ev["code"], ev["outline"], tuple(ev["col"]), 420)
            else:
                emb = ev["img"].resize((ev["img"].width * 3 // 4, ev["img"].height * 3 // 4), Image.LANCZOS)
            pos = ((845, 790, 1030) if side == "right" else (240, 1310, 1550))  # map y, name y
            self.vs.append(dict(panel=CT.vs_panel(ev["code"], tuple(ev["col"]), side), side=side, emb=emb, pos=pos,
                                name=text_img(ev["name"], 96, WHITE, max_w=430)))
        self.vs_bolt = CT.vs_bolt(COLORS["gold"])
        self.vs_txt = text_img("VS", 300, WHITE, "Black")
        self.vs_glow = text_img("VS", 300, COLORS["gold"], "Black", shadow=False).filter(ImageFilter.GaussianBlur(26))

    def _vs(self, frame, t):
        a = 1 - prog(t, 2.45, 2.8)
        if a <= 0:
            return
        lay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        slide = ease_io(prog(t, 0.0, 0.45))
        shake = math.sin(t * 70) * 22 * (1 - prog(t, 0.5, 0.95)) if t >= 0.45 else 0
        for k, v in enumerate(self.vs):
            dx = (1 - slide) * (700 if v["side"] == "right" else -700)
            paste(lay, v["panel"], 540 + dx + shake, 960, 1.0, 1.0)
        clash = prog(t, 0.45, 0.6)
        if clash > 0:
            paste(lay, self.vs_bolt, 540 + shake, 960, 1.0, min(1, clash * 2) * (0.75 + 0.25 * math.sin(t * 30)))
        for k, v in enumerate(self.vs):
            x, ye, yn = v["pos"]
            pi_ = prog(t, 0.55 + 0.1 * k, 1.0 + 0.1 * k)
            paste(lay, v["emb"], x + shake, ye, 0.6 + 0.4 * ease_out_back(pi_), pi_)
            paste(lay, v["name"], x + shake, yn, 1.0, prog(t, 0.75 + 0.1 * k, 1.05 + 0.1 * k))
        pv = prog(t, 0.45, 0.75)
        if pv > 0:
            sc = 2.2 - 1.2 * ease_out_back(pv) + 0.04 * math.sin(t * 8)
            paste(lay, self.vs_glow, 540 + shake, 960, sc, pv)
            paste(lay, self.vs_txt, 540 + shake, 960, sc, pv)
        if t >= 0.45:
            fl = 1 - prog(t, 0.45, 0.7)
            if fl > 0:
                lay.alpha_composite(Image.new("RGBA", frame.size, (255, 255, 255, int(200 * fl))))
        ph = prog(t, 1.1, 1.4) * (1 - prog(t, 2.45, 2.7))  # dark band behind the hook text
        if ph > 0:
            band = Image.new("RGBA", (W, 400), (5, 8, 20, int(210 * ph)))
            lay.alpha_composite(band, (0, 190))
        frame.alpha_composite(fade(lay, a))

    def _bars(self, frame, t):
        G = self.G
        a_all = 1 - prog(t, self.E - 0.1, self.E + 0.3)
        if a_all <= 0:
            return
        compact = G >= 3
        lab_sz, bar_h, lab_dy = (30, 24, 30) if compact else (42, 44, 50)
        y0 = 1262 if compact else 1300
        pitch = 140 if G <= 2 else (1500 - y0) / (G - 1)
        scale = 660.0 / max(self.gaps)
        for i in range(G):
            f = self.flights[i]
            t0 = self.bars_t0 + 0.25 * i
            by = y0 + i * pitch
            g = ease_io(prog(t, t0, t0 + 0.45))
            Lw = self.gaps[i] * scale * g
            lab = self.L["from_to"].format(a=self.evs[i]["name"], b=self.evs[i + 1]["name"])
            paste(frame, text_img(lab, lab_sz, WHITE, "Bold", max_w=900), W - 70 if self.rtl else 70, by - lab_dy,
                  1.0, min(1, g * 2) * a_all, anchor="r" if self.rtl else "l")
            rtl = self.rtl
            bw = 660 + 60
            bar = Image.new("RGBA", (bw, bar_h + 60), (0, 0, 0, 0))
            ImageDraw.Draw(bar).rounded_rectangle([30, 30, 30 + 660, 30 + bar_h], bar_h // 2,
                                                  fill=f["col"] + (int(45 * min(1, g * 2)),))
            x0, x1 = (30 + 660 - Lw, 30 + 660) if rtl else (30, 30 + Lw)
            if Lw > 2:
                if i == self.hi and t >= self.s0 + 0.45:
                    pulse = 0.5 + 0.5 * math.sin((t - self.s0 - 0.45) * 6)
                    gl = Image.new("RGBA", bar.size, (0, 0, 0, 0))
                    ImageDraw.Draw(gl).rounded_rectangle([x0, 30, x1, 30 + bar_h], bar_h // 2,
                                                         fill=f["col"] + (int(200 * pulse),))
                    bar = Image.alpha_composite(bar, gl.filter(ImageFilter.GaussianBlur(12)))
                ImageDraw.Draw(bar).rounded_rectangle([x0, 30, x1, 30 + bar_h], bar_h // 2, fill=f["col"] + (255,))
            if rtl:
                paste(frame, fade(bar, a_all), W - 70, by + bar_h / 2, anchor="r")
            else:
                paste(frame, fade(bar, a_all), 70, by + bar_h / 2, anchor="l")
            if g >= 1:
                val = text_img(f["final"], 40 if not compact else 30, WHITE)
                va = prog(t, t0 + 0.45, t0 + 0.65) * a_all
                if rtl:
                    paste(frame, val, W - 100 - Lw - 14, by + bar_h / 2, 1.0, va, anchor="r")
                else:
                    paste(frame, val, 100 + Lw + 14, by + bar_h / 2, 1.0, va, anchor="l")

    # ------------------------------------------------------------ sound
    def sound(self, mx):
        if self.intro == "globe":
            s, pn = mx.whoosh(3.0); mx.add(0.1, s, 0.4, pn)
            mx.add(2.2, mx.riser(1.4), 0.22)
            for k in range(len(self.gl_mev)):
                mx.add(3.3 + 0.3 * k, mx.pop(), 0.35)
            s, pn = mx.whoosh(1.5); mx.add(6.3, s, 0.5, pn)
            mx = _Shifted(mx, self.off)  # the rest of the video plays `off` seconds later
        elif self.intro == "vs":
            s, pn = mx.whoosh(0.5); mx.add(0.0, s, 0.5, pn)
            s, pn = mx.whoosh(0.5); mx.add(0.0, s, 0.5, pn[::-1])
            mx.add(0.45, mx.hit(1.6), 0.85)
            mx.add(0.6, mx.pop(), 0.35)
            mx.add(0.7, mx.pop(), 0.35)
        else:
            mx.intro(0.05)
        for ev in self.evs:
            mx.add(ev["t_app"], mx.pop(), 0.35)
        s, pn = mx.whoosh(1.4); mx.add(2.6, s, 0.55, pn)
        s, pn = mx.whoosh(0.9); mx.add(5.0, s, 0.5, pn[::-1])
        for f in self.flights:
            s, pn = mx.whoosh(1.2); mx.add(f["fs"] - 0.05, s, 0.45, pn)
            last, k, tt = None, 0, f["fs"]
            while tt < f["fe"]:
                b = math.floor(self.camera(tt)[0] / f["unit"] + 1e-9)
                if last is not None and b != last:
                    mx.add(tt, mx.tick(1900 if k % 2 else 2300), 0.28)
                    k += 1
                last = b
                tt += 1 / 600
            mx.add(f["fe"], mx.pop(), 0.4)
        s, pn = mx.whoosh(1.0); mx.add(self.flights[-1]["fe"], s, 0.5, pn[::-1])
        if self.use_guess:
            for k in range(3):
                mx.add(self.g0 + 0.3 + 0.12 * k, mx.pop(), 0.3)
                mx.add(self.g_tick + k, mx.tick(2400 if k == 2 else 1500), 0.32)
            mx.add(self.g_ans, mx.ding(), 0.5)
        if self.use_maps:
            if self.map_style == "side":
                for k, t0 in enumerate(self.side_t):
                    s, pn = mx.whoosh(0.5); mx.add(t0, s, 0.35, pn)
                    mx.add(t0 + 0.45, mx.pop(), 0.45)
                mx.add(self.side_sym, mx.ding(), 0.5)
            else:
                mx.add(self.m0 + 0.05, mx.pop(), 0.4)
            for tk in self.m_t:
                s, pn = mx.whoosh(0.7); mx.add(tk - 0.1, s, 0.45, pn[::-1])
                mx.add(tk + 0.5, mx.pop(), 0.45)
            if self.map_style == "tiles":  # ticks speed up and slow down with the filling, then a ding
                n, a, b = 28, self.tf + 0.3, self.tf + 2.9
                for j in range(1, n):
                    lo, hi = 0.0, 1.0
                    for _ in range(30):  # time at which ease_io reaches j/n
                        mid = (lo + hi) / 2
                        lo, hi = (mid, hi) if ease_io(mid) < j / n else (lo, mid)
                    mx.add(a + (b - a) * lo, mx.tick(1700 + 900 * j / n), 0.22)
                mx.add(b, mx.ding(), 0.55)
        else:
            for i in range(self.G):
                mx.add(self.bars_t0 + 0.25 * i, mx.pop(), 0.3)
        mx.add(self.s0 - 1.1, mx.riser(1.1), 0.3)
        mx.add(self.s0 + 0.47, mx.hit(2.4), 0.95)
        mx.add(self.E + 0.2, mx.chime(), 0.35)
