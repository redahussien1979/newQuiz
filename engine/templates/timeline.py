"""Timeline Collision: 2-5 events on a flying timeline, gap counters, comparison bars and a reveal."""
import math

from PIL import Image, ImageDraw, ImageFilter

from ..core import (GREY, W, WHITE, Stars, clamp, draw_ending, draw_scene, ease_io, ease_out_back, fade,
                    get_theme, global_fade, make_bg, nice_step, parse_lines, paste, prog, stack_lines,
                    text_img, to_rgb)
from ..icons import make_card
from ..strings import S, fmt_num, gap_str, gap_years, year_str, years_word

NAME = "Timeline Collision"
DEFAULT_COLORS = ["sand", "gold", "blue", "green", "pink"]
RIBBON_Y = 1150

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


class TimelineVideo:
    def __init__(self, project):
        s = project.get("settings", {})
        d = project.get("timeline", {})
        e = project.get("ending", {})
        self.lang = s.get("language", "ar")
        self.L = S(self.lang)
        self.mode = d.get("mode", "calendar")
        self.theme = get_theme(s.get("theme"))
        self.bg = make_bg(self.theme)
        self.stars = Stars() if self.theme["stars"] else None
        self.fps = int(s.get("fps", 30))

        evs = []
        for i, ev in enumerate(d.get("events", [])):
            name = str(ev.get("name") or "").strip()
            if not name or ev.get("year") in (None, "") or ev.get("enabled") is False:
                continue
            try:
                year = float(ev["year"])
            except (TypeError, ValueError):
                raise ValueError(f"Event '{name}': year must be a number.")
            v = year if self.mode == "calendar" else -abs(year)
            evs.append(dict(name=name, v=v, col=to_rgb(ev.get("color") or DEFAULT_COLORS[len(evs) % 5]),
                            icon=ev.get("icon") or "none", image=ev.get("image") or "",
                            label=str(ev.get("label") or "").strip()))
        if len(evs) < 2:
            raise ValueError("The timeline needs at least 2 events, each with a name and a year.")
        evs = sorted(evs[:5], key=lambda x: x["v"])
        self.evs = evs
        N = self.N = len(evs)
        G = self.G = N - 1
        ys = self.ys = [x["v"] for x in evs]
        span = ys[-1] - ys[0]
        if span <= 0:
            raise ValueError("Events must have different years.")

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
        fd = clamp(13.0 / G, 3.5, 6.5)
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
                                     final=gap_str(gap_years(ys[i], ys[i + 1], self.mode), self.lang)))
            t = fe + hold
        K.append((t, t + 0.9, (ys[-1], zg[-1]), FULL))
        self.Tc = Tc = t + 0.9
        K.append((Tc, 1e9, FULL, FULL))
        self.K = K

        # ---------------- comparison / reveal / ending timing
        self.s0 = Tc + 0.1 + 0.25 * (G - 1) + 0.45 + 0.05
        self.reveal_in = self.s0 + 0.5
        self.E = self.reveal_in + 4.55
        self.base_duration = self.dur = self.E + 4.0
        self.silences = [(self.s0, self.s0 + 0.5)]
        self.gaps = [gap_years(ys[i], ys[i + 1], self.mode) for i in range(G)]
        self.hi = min(range(G), key=lambda i: self.gaps[i])

        # ---------------- cards
        card_bg = self.theme["card"]
        for k, ev in enumerate(evs):
            sub = ev["label"] or year_str(ev["v"], self.mode, self.lang)
            ev["img"] = make_card(ev["name"], sub, ev["col"], ev["icon"], ev["image"], card_bg)
        order = list(range(N))
        later = order[1:] if self.hidden_first else order
        for k, i in enumerate(later):
            evs[i]["t_app"] = 0.15 + 0.3 * k
        if self.hidden_first:
            evs[0]["t_app"] = 3.3

        # ---------------- scenes
        L = self.L
        hook_lines = parse_lines(d.get("hook", ""), ["white", evs[-1]["col"], evs[0]["col"]])
        doubt = d.get("doubt", "")
        self.scenes = [
            dict(t_in=0.1, t_out=2.55, lines=stack_lines(hook_lines, 330, 76, 64)),
            dict(t_in=2.65, t_out=4.95, shake=True,
                 lines=[(doubt, 160, WHITE, 410), (d.get("doubt_sub", ""), 52, GREY, 565)]),
        ]
        for f in self.flights:
            i = f["i"]
            self.scenes.append(dict(
                t_in=5.05 if i == 0 else f["fs"] - 0.15, t_out=f["out"],
                lines=[(L["frm"].format(a=evs[i]["name"]), 72, evs[i]["col"], 370),
                       (L["to"].format(b=evs[i + 1]["name"]), 72, evs[i + 1]["col"], 470)]))
        self.scenes.append(dict(t_in=Tc + 0.05, t_out=self.s0, lines=[(d.get("compare_title", ""), 84, WHITE, 430)]))
        rv = parse_lines(d.get("reveal", ""), ["white"])
        self.scenes.append(dict(t_in=self.reveal_in, t_out=self.E, lines=stack_lines(rv, 380, 88, 76)))
        self.ending = (e.get("intro", ""), parse_lines(e.get("question", ""), ["white", "gold"]),
                       e.get("cta", ""), s.get("handle", ""))
        self.accent = evs[1]["col"] if N > 2 else evs[-1]["col"]

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
    def render(self, t):
        frame = self.bg.copy()
        cam, z = self.camera(t)
        sx = lambda v: 540 + (v - cam) * z
        d = ImageDraw.Draw(frame)
        if self.stars:
            self.stars.draw(d, t, (cam - self.cam_full) * z)

        # ribbon + ticks
        strip_h, top, ry = 160, RIBBON_Y - 80, 80
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
        flying = None
        for f in self.flights:
            i = f["i"]
            if t < f["fs"]:
                continue
            end = self.ys[i + 1] if t >= f["fe"] else clamp(cam, self.ys[i], self.ys[i + 1])
            xa, xb = sx(self.ys[i]), sx(end)
            gd.line([(xa, ry), (xb, ry)], fill=f["col"] + (255,), width=26)
            sd.line([(xa, ry), (xb, ry)], fill=f["col"] + (255,), width=14)
            if t < f["fe"]:
                flying = f
        if flying:
            tx = sx(cam)
            gd.ellipse([tx - 34, ry - 34, tx + 34, ry + 34], fill=flying["col"] + (255,))
            sd.ellipse([tx - 14, ry - 14, tx + 14, ry + 14], fill=WHITE + (255,))
        strip = Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)), strip)
        frame.alpha_composite(strip, (0, top))
        for v, x in labels:
            if 50 < x < W - 50:
                paste(frame, text_img(year_str(v, self.mode, self.lang, short=True), 28, GREY, "SemiBold",
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
        for ev, x, xc in zip(self.evs, anchors, cx):
            p = prog(t, ev["t_app"], ev["t_app"] + 0.45)
            if p <= 0 or xc < -400 or xc > W + 400:
                continue
            img = ev["img"]
            ch = img.height * sc
            cy = RIBBON_Y - 40 * sc - ch / 2
            d.line([(x, RIBBON_Y - 10), (xc, RIBBON_Y - 80 * sc + 4)], fill=ev["col"] + (255,), width=4)
            d.ellipse([x - 11, RIBBON_Y - 11, x + 11, RIBBON_Y + 11], fill=ev["col"] + (255,), outline=WHITE + (255,), width=3)
            paste(frame, img, xc, cy + (1 - ease_out_back(p)) * 60, sc * (0.7 + 0.3 * ease_out_back(p)), min(1, p * 1.6))

        # counters
        for f in self.flights:
            if f["fs"] <= t <= f["vis"]:
                a = min(1, prog(t, f["fs"], f["fs"] + 0.3)) * (1 - prog(t, f["vis"] - 0.2, f["vis"]))
                paste(frame, text_img(year_str(cam, self.mode, self.lang), 112, WHITE, max_w=980), 540, RIBBON_Y + 200, 1.0, a)
                if t >= f["fe"]:
                    el, pop = f["final"], 1 + 0.15 * (1 - prog(t, f["fe"], f["fe"] + 0.3))
                else:
                    g = max(0.0, cam - self.ys[f["i"]])
                    el, pop = f"+ {fmt_num(g, self.lang)} {years_word(g, self.lang)}", 1
                paste(frame, text_img(el, 64, f["col"], max_w=980), 540, RIBBON_Y + 320, pop, a)

        # comparison bars
        if t >= self.Tc + 0.05:
            self._bars(frame, t)
        for sc_ in self.scenes:
            draw_scene(frame, t, sc_)
        draw_ending(frame, t, self.E, *self.ending, self.accent)
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

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
            t0 = self.Tc + 0.1 + 0.25 * i
            by = y0 + i * pitch
            g = ease_io(prog(t, t0, t0 + 0.45))
            Lw = self.gaps[i] * scale * g
            lab = self.L["from_to"].format(a=self.evs[i]["name"], b=self.evs[i + 1]["name"])
            paste(frame, text_img(lab, lab_sz, WHITE, "Bold", max_w=900), 70, by - lab_dy,
                  1.0, min(1, g * 2) * a_all, anchor="l")
            if Lw > 2:
                bar = Image.new("RGBA", (int(Lw) + 60, bar_h + 60), (0, 0, 0, 0))
                bd = ImageDraw.Draw(bar)
                if i == self.hi and t >= self.s0 + 0.45:
                    pulse = 0.5 + 0.5 * math.sin((t - self.s0 - 0.45) * 6)
                    bd.rounded_rectangle([30, 30, 30 + Lw, 30 + bar_h], bar_h // 2, fill=f["col"] + (int(160 * pulse),))
                    bar = bar.filter(ImageFilter.GaussianBlur(12))
                    bd = ImageDraw.Draw(bar)
                bd.rounded_rectangle([30, 30, 30 + Lw, 30 + bar_h], bar_h // 2, fill=f["col"] + (255,))
                paste(frame, fade(bar, a_all), 70, by + bar_h / 2, anchor="l")
            if g >= 1:
                paste(frame, text_img(f["final"], 40 if not compact else 30, WHITE), 100 + Lw + 10, by + bar_h / 2,
                      1.0, prog(t, t0 + 0.45, t0 + 0.65) * a_all, anchor="l")

    # ------------------------------------------------------------ sound
    def sound(self, mx):
        mx.add(0.05, mx.hit(1.6), 0.55)
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
        for i in range(self.G):
            mx.add(self.Tc + 0.1 + 0.25 * i, mx.pop(), 0.3)
        mx.add(self.s0 - 1.1, mx.riser(1.1), 0.3)
        mx.add(self.s0 + 0.47, mx.hit(2.4), 0.95)
        mx.add(self.E + 0.2, mx.chime(), 0.35)
