"""Language strings and number/year formatting (Arabic + English)."""

STR = {
    "ar": dict(bce="ق.م", ce="م", years="سنة", years_few="سنوات", now="الآن",
               ago_short="قبل {n}", ago_full="قبل {n} سنة",
               frm="من {a}", to="إلى {b}", from_to="من {a} إلى {b}",
               million="مليون", billion="مليار",
               clue="الدليل {i} من {n}", answer_intro="الجواب…",
               question="السؤال {i} من {n}", letters=["أ", "ب", "ج", "د"],
               guess_area="خمّن: كم مرة تدخل\n[{ca}]{a} في {b}؟", guess_ratio="خمّن: {b} أكبر من\n[{ca}]{a} بكم مرة؟",
               diff="الفرق {p}% فقط!"),
    "en": dict(bce="BC", ce="AD", years="years", years_few="years", now="Now",
               ago_short="{n} ago", ago_full="{n} years ago",
               frm="From {a}", to="to {b}", from_to="{a} to {b}",
               million="million", billion="billion",
               clue="Clue {i} of {n}", answer_intro="The answer…",
               question="Question {i} of {n}", letters=["A", "B", "C", "D"],
               guess_area="Guess: how many times does\n[{ca}]{a} fit in {b}?", guess_ratio="Guess: how many times is {b}\n[{ca}]bigger than {a}?",
               diff="Only {p}% apart!"),
}


def S(lang):
    return STR.get(lang, STR["ar"])


def fmt_num(n, lang="ar"):
    n = abs(n)
    s = S(lang)
    if n >= 1e9:
        x, unit = n / 1e9, s["billion"]
    elif n >= 1e6:
        x, unit = n / 1e6, s["million"]
    else:
        n = int(round(n))
        return f"{n:,}" if n >= 10000 else str(n)
    txt = f"{x:.1f}".rstrip("0").rstrip(".")
    return f"{txt} {unit}"


def years_word(n, lang="ar"):
    s = S(lang)
    return s["years_few"] if 3 <= abs(n) <= 10 else s["years"]


def year_str(v, mode="calendar", lang="ar", short=False):
    """v is the internal timeline value: calendar year (negative = BCE) or -(years ago)."""
    s = S(lang)
    if mode == "ago":
        ago = -v
        if ago < 0.5:
            return s["now"]
        return (s["ago_short"] if short else s["ago_full"]).format(n=fmt_num(ago, lang))
    y = int(round(v))
    if y == 0:
        return "0"
    return f"{fmt_num(y, lang)} {s['bce'] if y < 0 else s['ce']}"


def gap_years(a, b, mode="calendar"):
    g = b - a
    if mode == "calendar" and a < 0 < b:
        g -= 1  # there is no year zero
    return g


def gap_str(g, lang="ar"):
    exact = int(round(g))
    if g < 1000:
        r = exact
    elif g < 1e6:
        r = int(round(g / 10.0) * 10)
    else:
        r = float(f"{g:.3g}")
    approx = abs(r - g) > 0.5
    return f"{'≈ ' if approx else ''}{fmt_num(r, lang)} {years_word(r, lang)}"


# ---------------------------------------------------------------- number-line mode (any unit)
def fmt_val(x, lang="ar"):
    """Signed number for the number-line mode: keeps decimals for small values (2.5, 0.75, -89.2)."""
    a = abs(x)
    if a >= 1e9:
        body = fmt_num(a, lang)
    elif a >= 100 or a == int(a):
        n = int(round(a))
        body = f"{n:,}" if n >= 10000 else str(n)  # full digits so close values stay distinct
    else:
        body = f"{a:.{1 if a >= 10 else 2}f}".rstrip("0").rstrip(".")
    return ("-" if x < 0 and body not in ("0", "") else "") + body


def with_unit(num, unit):
    """'5' + 'km' -> '5 km'; a unit containing {n} places the number itself: '${n}' -> '$5'."""
    unit = (unit or "").strip()
    if "{n}" in unit:
        neg = num.startswith("-") and not unit.startswith("{n}")
        return ("-" if neg else "") + unit.replace("{n}", num[1:] if neg else num)
    return f"{num} {unit}" if unit else num


def amount_str(g, unit, lang="ar"):
    """Gap between two values with its unit; '≈' only when the displayed number had to be rounded."""
    num = fmt_val(g, lang)
    a = abs(g)
    if a >= 1e9:
        shown = float(f"{a / 1e9:.1f}") * 1e9
    else:
        shown = float(fmt_val(a, lang).replace(",", ""))
    approx = abs(shown - a) > max(1e-9, a * 1e-9)
    return f"{'≈ ' if approx else ''}{with_unit(num, unit)}"


def ratio_str(r):
    """'× 2.1', '× 205', '× 1,250'."""
    if r < 10:
        txt = f"{r:.1f}".rstrip("0").rstrip(".")
    else:
        n = int(round(r))
        txt = f"{n:,}" if n >= 10000 else str(n)
    return "× " + txt
