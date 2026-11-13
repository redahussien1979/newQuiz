"""📰 English in News — the transcript editor behind the tab: ElevenLabs words -> the Words box, click a word to make
it a key word (the next word joins it into a phrase), the Arabic meanings table, and suggested key words.

The Words box (`news.words`) is the only place the choices live, one spoken word per line:
    word | start | end | highlighted | arabic | repeat
`*` in highlighted = the word itself; a phrase has its text (e.g. `cooling centres`) on each of its lines; the Arabic
sits on the first line of the word / phrase (the same format as 📖 English Texts, read by templates/news.py), and so
does `repeat`: how many extra times the video replays the key word (0-10).
"""
import re

from . import paragraphs as para
from .templates.news import REP_MAX
from .templates.text import _clean, _groups, parse_words

_SENT = re.compile(r"[.!?…][\"'”’)\]]*$")


def _t(x):
    return f"{float(x):.2f}"


def dump(words):
    """Words (dicts w, s, e, mark, ar, rep) -> the Words box text."""
    lines = []
    for w in words:
        rep = rep_of(w)
        parts = [w["w"], _t(w["s"]), _t(w["e"]), str(w.get("mark") or "").strip(), str(w.get("ar") or "").strip(),
                 str(rep) if rep else ""]
        while len(parts) > 3 and not parts[-1]:
            parts.pop()
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def load(text):
    return parse_words(text)


def from_stt(stt):
    """ElevenLabs words -> the Words box text (no key words yet)."""
    return dump([dict(w=re.sub(r"[|\s]+", " ", x["text"]).strip() or "…", s=x["start"], e=x["end"], mark="", ar="",
                      rep="") for x in stt])


def rep_of(w):
    """A word line's repeat count (extra replays of its key word, 0-10)."""
    try:
        return max(0, min(REP_MAX, int(float(str(w.get("rep") or 0).strip() or 0))))
    except ValueError:
        return 0


def group_rep(words, g):
    return max((rep_of(words[k]) for k in range(g["i0"], g["i1"] + 1)), default=0)


def groups(words):
    return _groups(words)


def view(words):
    """Value for the clickable gr.HighlightedText: one token per word, labelled with its key-word number."""
    lab = {}
    for n, g in enumerate(_groups(words), 1):
        for i in range(g["i0"], g["i1"] + 1):
            lab[i] = str(n)
    return [(w["w"] + " ", lab.get(i)) for i, w in enumerate(words)]


def _set_phrase(words, i0, i1, ar, rep=0):
    if i1 > i0:
        text = " ".join(_clean(words[k]["w"]) for k in range(i0, i1 + 1))
        for k in range(i0, i1 + 1):
            words[k]["mark"], words[k]["ar"], words[k]["rep"] = text, "", ""
    else:
        words[i0]["mark"], words[i0]["ar"], words[i0]["rep"] = "*", "", ""
    words[i0]["ar"], words[i0]["rep"] = ar, (str(rep) if rep else "")


def toggle(words, i, join=True):
    """Click on word i: a key word (or phrase) is removed; else the word becomes a key word — or, when `join` and the
    word just before it is the end of a key word, that key word grows into a phrase."""
    if not 0 <= i < len(words):
        return words
    gs = _groups(words)
    for g in gs:
        if g["i0"] <= i <= g["i1"]:
            for k in range(g["i0"], g["i1"] + 1):
                words[k]["mark"], words[k]["ar"], words[k]["rep"] = "", "", ""
            return words
    prev = next((g for g in gs if g["i1"] == i - 1), None)
    if join and prev is not None and not _SENT.search(words[i - 1]["w"]):
        _set_phrase(words, prev["i0"], i, prev["ar"], group_rep(words, prev))
    else:
        _set_phrase(words, i, i, "")
    return words


def clear(words):
    for w in words:
        w["mark"], w["ar"], w["rep"] = "", "", ""
    return words


def table(words):
    """Rows for the meanings table: [#, key word, Arabic, repeat]."""
    return [[n, g["text"], g["ar"], group_rep(words, g)] for n, g in enumerate(_groups(words), 1)]


def _cell(v):
    if v is None or (isinstance(v, float) and v != v):  # empty / NaN (pandas)
        return ""
    return str(v).strip()


def set_meanings(words, rows):
    """The meanings table back: each row's Arabic and repeat count go onto its key word (rows match the key words in
    order)."""
    gs = _groups(words)
    for g, row in zip(gs, rows or []):
        row = list(row) + [""] * (4 - len(row))
        rep = rep_of({"rep": _cell(row[3])})
        for k in range(g["i0"], g["i1"] + 1):
            words[k]["ar"], words[k]["rep"] = "", ""
        words[g["i0"]]["ar"], words[g["i0"]]["rep"] = _cell(row[2]), (str(rep) if rep else "")
    return words


def suggest(words, n=5, common=6000):
    """Mark up to n key words in all: the least common words of the transcript (rarer than the `common` most frequent
    English words), skipping names, short words and words already marked."""
    gs = _groups(words)
    taken = {k for g in gs for k in range(g["i0"], g["i1"] + 1)}
    seen = {_clean(words[k]["w"]).lower() for k in taken}
    cands = []
    for i, w in enumerate(words):
        c = _clean(w["w"])
        if i in taken or len(c) < 4 or not c.replace("-", "").isalpha():
            continue
        if c[0].isupper() and not (i == 0 or _SENT.search(words[i - 1]["w"])):
            continue  # a name (Antalya, Paris)
        r = para.rank(c)
        if common < r <= len(para._freq()):
            cands.append((r, i))
    have = len(gs)
    for _, i in sorted(cands, reverse=True):
        if have >= n:
            break
        c = _clean(words[i]["w"]).lower()
        if c in seen:
            continue
        seen.add(c)
        words[i]["mark"] = "*"
        have += 1
    return words


def report(words, clip=None):
    if not words:
        return "_No transcript yet — upload a video (with your ElevenLabs key saved) or paste the words below._"
    gs = _groups(words)
    bits = [f"**{len(words)} words**", f"**{len(gs)} key word{'s' if len(gs) != 1 else ''}**",
            f"speech {words[0]['s']:.1f}–{words[-1]['e']:.1f} s"]
    if clip:
        bits.append(f"video {clip:.1f} s")
    no_ar = [g["text"] for g in gs if not g["ar"]]
    if no_ar:
        bits.append("⚠️ no Arabic for: " + ", ".join(no_ar[:5]) + (" …" if len(no_ar) > 5 else ""))
    if len(gs) > 8:
        bits.append("💡 4–6 key words read best")
    return " · ".join(bits)


# ------------------------------------------------------------------ the key-words sheet (Excel round trip)
SHEET_HEADERS = ["Clip", "#", "Key word", "Arabic meaning", "Repeat (extra times, 0-10)", "Sentence (for context)"]
_HEAD_KEYS = {"clip": "clip", "#": "num", "key": "key", "arabic": "ar", "repeat": "rep", "sentence": "sent"}


def _sentence(words, g):
    """The sentence a key word is in, with the key word in «»."""
    a = g["i0"]
    while a > 0 and not _SENT.search(words[a - 1]["w"]):
        a -= 1
    b = g["i1"]
    while b < len(words) - 1 and not _SENT.search(words[b]["w"]):
        b += 1
    out = []
    for k in range(a, b + 1):
        w = words[k]["w"]
        if k == g["i0"]:
            w = "«" + w
        if k == g["i1"]:   # » before the word's own punctuation: «risk».
            m = re.search(r"[^\w']+$", w)
            w = (w[:m.start()] + "»" + w[m.start():]) if m and m.start() > 0 else w + "»"
        out.append(w)
    return " ".join(out)


def _norm(txt):
    return " ".join(_clean(x).lower() for x in str(txt or "").split())


def export_xlsx(clips, path):
    """One row per key word of every clip: Clip · # · Key word · Arabic meaning · Repeat · Sentence. Fill D (and E),
    upload it back with import_xlsx. Returns (path, number of key words)."""
    import os

    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "key words"
    ws.append(SHEET_HEADERS)
    n = 0
    for c in clips:
        words = load(c.get("words"))
        for k, g in enumerate(_groups(words), 1):
            ws.append([os.path.basename(c.get("video") or ""), k, g["text"], g["ar"] or None,
                       group_rep(words, g) or None, _sentence(words, g)])
            n += 1
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="8C0E1A")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for col, w in zip("ABCDEF", [26, 5, 26, 34, 12, 70]):
        ws.column_dimensions[col].width = w
    yellow = PatternFill("solid", fgColor="FFF6CC")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top",
                                       horizontal="right" if cell.column == 4 else
                                       ("center" if cell.column in (2, 5) else "left"),
                                       readingOrder=2 if cell.column == 4 else 0)
            if cell.column in (4, 5):
                cell.fill = yellow   # the columns to fill
    ws.freeze_panes = "A2"
    wb.save(path)
    return path, n


def import_xlsx(path, clips):
    """A filled key-words sheet back into the clips: each row's Arabic (and repeat) goes onto its key word, found by
    clip file name + key word (or its # in that clip). Returns (clips, message)."""
    import os

    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["key words"] if "key words" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise ValueError("The sheet is empty.")
    col = {}
    for i, h in enumerate(rows[0]):
        h = str(h or "").strip().lower()
        for key, name in _HEAD_KEYS.items():
            if name not in col and (h.startswith(key) if key != "#" else h == "#"):
                col[name] = i
    if "ar" not in col or ("key" not in col and "num" not in col):
        raise ValueError("No 'Key word' / 'Arabic meaning' columns — use the sheet made by ⬇️ Key words → Excel.")
    by_name = {}
    for ci, c in enumerate(clips):
        by_name.setdefault(os.path.basename(c.get("video") or "").lower(), ci)
    parsed = [load(c.get("words")) for c in clips]
    filled, missed, changed = 0, [], set()

    def cell(r, name):
        i = col.get(name)
        return r[i] if i is not None and i < len(r) else None
    for r in rows[1:]:
        if not r or all(v is None or str(v).strip() == "" for v in r):
            continue
        name = str(cell(r, "clip") or "").strip().lower()
        ci = by_name.get(name, 0 if len(clips) == 1 else None)
        key = _norm(cell(r, "key"))
        if ci is None:
            missed.append(f"{cell(r, 'clip')} / {cell(r, 'key')}")
            continue
        words = parsed[ci]
        gs = _groups(words)
        g = next((x for x in gs if _norm(x["text"]) == key), None) if key else None
        if g is None:
            try:
                k = int(float(cell(r, "num")))
                g = gs[k - 1] if 1 <= k <= len(gs) and (not key or _norm(gs[k - 1]["text"]) == key) else None
            except (TypeError, ValueError):
                g = None
        if g is None:
            missed.append(f"{cell(r, 'clip') or 'clip ' + str(ci + 1)} / {cell(r, 'key')}")
            continue
        ar = _cell(cell(r, "ar"))
        for k in range(g["i0"], g["i1"] + 1):
            words[k]["ar"] = ""
        words[g["i0"]]["ar"] = ar
        if "rep" in col:
            rep = rep_of({"rep": _cell(cell(r, "rep"))})
            for k in range(g["i0"], g["i1"] + 1):
                words[k]["rep"] = ""
            words[g["i0"]]["rep"] = str(rep) if rep else ""
        filled += bool(ar)
        changed.add(ci)
    out = [dict(c) for c in clips]
    for ci in changed:
        out[ci]["words"] = dump(parsed[ci])
    msg = f"✅ {filled} Arabic meaning{'s' if filled != 1 else ''} filled in {len(changed)} clip" \
          f"{'s' if len(changed) != 1 else ''}."
    if missed:
        msg += f" ⚠️ {len(missed)} row{'s' if len(missed) != 1 else ''} not found (key word changed or clip " \
               f"removed): " + ", ".join(missed[:5])
    return out, msg
