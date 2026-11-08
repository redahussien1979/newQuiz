"""English Texts from an Excel workbook: every tab = one paragraph = one video.

Tab layout (row 1 = headers, any order; without headers the columns are read as A..F below):
    A index | B word | C start | D end | E highlighted words | F arabic translation | title | subtitle | audio

- One spoken word per row (B), with its start / end time in seconds in the recording (C / D) — e.g. the word
  timings ElevenLabs exports.
- E: write the word (or anything, e.g. *) on the row of a word that should fly into the word bank. Neighbouring rows
  with the same several-word text in E (e.g. "ten-minute walk" on both rows) fly together as one phrase.
- F: the Arabic meaning, on the row of the highlighted word (any row of a phrase).
- title / subtitle / audio (optional columns): the cell under the header (row 2). title = the big title of the
  video, subtitle = the small line above it, audio = the file name of the recording.
- The recording: upload it with the sheet. A file named like the tab (`paragraph1.mp3`) or named in the audio column
  goes to that tab; any other file (e.g. ElevenLabs_2026-….mp3) goes to the tab whose reading length it matches.
"""
import copy
import os
import re

from .batch import _norm, read_table, sheet_names

_ALIASES = {
    "index": ["index", "#", "no", "n", "num", "number", "رقم", "الرقم", "م"],
    "word": ["word", "words", "text", "token", "الكلمه", "كلمه", "الكلمات"],
    "start": ["start", "from", "begin", "starttime", "startsec", "start(s)", "البدايه", "بدايه", "من"],
    "end": ["end", "to", "stop", "endtime", "endsec", "end(s)", "النهايه", "نهايه", "الي"],
    "mark": ["highlightedwords", "highlightedword", "highlighted", "highlight", "keyword", "keywords", "key", "mark",
             "fly", "flyword", "vocab", "vocabulary", "الكلماتالمميزه", "الكلمهالمميزه", "مميزه", "تمييز"],
    "arabic": ["arabictranslation", "arabic", "translation", "meaning", "arabicmeaning", "الترجمه", "الترجمهالعربيه",
               "المعني", "معني", "عربي"],
    "title": ["title", "videotitle", "العنوان", "عنوان"],
    "subtitle": ["subtitle", "unit", "topline", "lesson", "العنوانالفرعي", "الوحده", "الدرس"],
    "audio": ["audio", "audiofile", "sound", "recording", "voice", "mp3", "الصوت", "صوت", "التسجيل"],
}
_LOOKUP = {_norm(a): k for k, names in _ALIASES.items() for a in names}
_POSITIONAL = ["index", "word", "start", "end", "mark", "arabic"]  # columns A..F when there is no header row
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma")
HEADERS = ["index", "word", "start", "end", "highlighted words", "arabic translation", "title", "subtitle"]


def _columns(header):
    cols = {}
    for i, h in enumerate(header):
        key = _LOOKUP.get(_norm(h))
        if key and key not in cols:
            cols[key] = i
    return cols if "word" in cols else None


def _first_below(rows, col):
    """The first non-empty cell under the header in column col."""
    if col is None:
        return ""
    for r in rows:
        if col < len(r) and str(r[col]).strip():
            return str(r[col]).strip()
    return ""


def read_tab(path, tab=None):
    """One tab -> dict(tab, title, subtitle, audio_name, rows=[(word, start, end, mark, arabic)], problems)."""
    table = [r for r in read_table(path, tab) if any(str(c).strip() for c in r)]
    if not table:
        raise ValueError(f"Tab '{tab or 'first'}' is empty.")
    cols = _columns(table[0])
    body = table[1:] if cols else table
    if not cols:
        cols = {k: i for i, k in enumerate(_POSITIONAL)}

    def get(r, key):
        i = cols.get(key)
        return str(r[i]).strip() if i is not None and i < len(r) else ""

    rows, problems = [], []
    for n, r in enumerate(body, 2 if table is not body else 1):
        w = get(r, "word")
        if not w:
            continue
        rows.append((w, get(r, "start"), get(r, "end"), get(r, "mark"), get(r, "arabic")))
        for key in ("start", "end"):
            v = get(r, key)
            if v and not _is_num(v):
                problems.append(f"Row {n}: the {key} time '{v}' is not a number (seconds).")
    if not rows:
        raise ValueError(f"Tab '{tab or 'first'}' has no words in the word column.")
    return dict(tab=tab or "", title=_first_below(body, cols.get("title")),
                subtitle=_first_below(body, cols.get("subtitle")), audio_name=_first_below(body, cols.get("audio")),
                rows=rows, problems=problems)


def _is_num(v):
    try:
        float(str(v).replace(",", "."))
        return True
    except ValueError:
        return False


def rows_text(rows):
    """The editor's Words box: one word per line, `word | start | end | highlighted | arabic` (like columns B-F)."""
    out = []
    for w, s, e, mark, ar in rows:
        parts = [w, s, e, mark, ar]
        while len(parts) > 1 and not str(parts[-1]).strip():
            parts.pop()
        out.append(" | ".join(str(p) for p in parts))
    return "\n".join(out)


# ------------------------------------------------------------------ audio
def _stem(path):
    return re.sub(r"[^0-9a-z؀-ۿ]+", "", os.path.splitext(os.path.basename(str(path)))[0].lower())


def find_audio(par, uploads, folder="", n_tabs=1):
    """The recording of a paragraph: the file named in its audio cell, else the upload named like the tab,
    else (a workbook with one tab) the only uploaded audio file."""
    uploads = [u for u in (uploads or []) if u and os.path.isfile(u)]
    name = par.get("audio_name") or ""
    if name:
        if os.path.isabs(name) and os.path.isfile(name):
            return name
        if folder and os.path.isfile(os.path.join(folder, name)):
            return os.path.join(folder, name)
        for u in uploads:
            if _stem(u) == _stem(name):
                return u
    tab = _stem(par.get("tab") or "")
    if tab:
        hits = [u for u in uploads if _stem(u) == tab]
        if hits:
            return hits[0]
        if folder and os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(AUDIO_EXT) and _stem(f) == tab:
                    return os.path.join(folder, f)
    return ""


def _length(path):
    try:
        from .audio import audio_length
        return audio_length(path)
    except Exception:
        return None


def _reading_len(par):
    ends = [float(str(r[2]).replace(",", ".")) for r in par["rows"] if _is_num(r[2])]
    return max(ends) if ends else None


def _match_by_length(pars, uploads):
    """Recordings whose names say nothing (ElevenLabs_2026-…mp3) go to the tabs still without one: each to the tab
    whose last word ends closest to the recording's length. Pairs are taken best first; a recording more than 40 %
    longer / shorter than every remaining tab is left out (it is probably not one of these paragraphs)."""
    used = {p["audio"] for p in pars if p.get("audio")}
    files = [u for u in uploads if u not in used]
    tabs = [p for p in pars if p["rows"] and not p.get("audio")]
    if not files or not tabs:
        return
    lens = {u: _length(u) for u in files}
    pairs = []
    for u in files:
        for p in tabs:
            r, a = _reading_len(p), lens[u]
            if r and a:
                pairs.append((abs(a - r) / max(r, 0.1), u, p))
    pairs.sort(key=lambda x: x[0])
    for diff, u, p in pairs:
        if diff > 0.4 or u in used or p.get("audio"):
            continue
        p["audio"], p["audio_by"] = u, "length"
        used.add(u)
    left = [u for u in files if u not in used]
    still = [p for p in tabs if not p.get("audio")]
    if len(left) == 1 and len(still) == 1:  # one recording and one tab left: they belong together
        still[0]["audio"], still[0]["audio_by"] = left[0], "only"


def load_book(path, uploads=(), folder=""):
    """Every visible tab of the workbook (or the CSV file) -> list of paragraphs (see read_tab), each with its
    `audio` path ('' when no recording was found) and `problems`. A recording named like a tab (or named in its
    audio column) goes to that tab; the other recordings are matched by length (_match_by_length)."""
    uploads = [u for u in (uploads or []) if u and os.path.isfile(u)]
    tabs = sheet_names(path) or [None]
    out = []
    for tab in tabs:
        try:
            par = read_tab(path, tab)
        except ValueError as e:
            out.append(dict(tab=tab or "", title="", subtitle="", rows=[], audio="", problems=[str(e)]))
            continue
        par["audio"] = find_audio(par, uploads, folder, len(tabs))
        out.append(par)
    _match_by_length(out, uploads)
    return out


def summary(pars):
    usable = [p for p in pars if p["rows"]]
    if not pars:
        return "The workbook has no tabs."
    ready = [p for p in usable if p.get("audio")]
    skip = len(usable) - len(ready)
    lines = [f"**{len(ready)} video{'s' if len(ready) != 1 else ''}** to render — one per tab"
             + (f" ({skip} tab{'s' if skip != 1 else ''} without a recording will be skipped)" if skip else "") + ":"]
    for k, p in enumerate(pars, 1):
        if not p["rows"]:
            lines.append(f"- ⚠️ tab **{p['tab']}**: {p['problems'][0] if p['problems'] else 'no words'}")
            continue
        keys = count_keys(p["rows"])
        no_ar = missing_arabic(p["rows"])
        bits = [f"{len(p['rows'])} words", f"{keys} highlighted"]
        if p["audio"]:
            ln = _length(p["audio"])
            how = " (matched by length)" if p.get("audio_by") == "length" else ""
            bits.append(f"🎙️ `{os.path.basename(p['audio'])}`" + (f" {ln:.1f} s" if ln else "") + how)
        else:
            bits.append("⚠️ no recording — upload one about "
                        f"{_reading_len(p) or 0:.0f} s long, or name it `{p['tab'] or 'paragraph'}.mp3`")
        if not p["title"]:
            bits.append("⚠️ no title")
        if no_ar:
            bits.append(f"⚠️ no Arabic for: {', '.join(no_ar[:4])}")
        lines.append(f"- tab **{p['tab'] or '—'}** · {p['title'] or '(no title)'} — " + " · ".join(bits))
        lines += [f"  - ⚠️ {x}" for x in p["problems"][:3]]
    return "\n".join(lines)


def _groups(rows):
    """[(display text, arabic)] of the highlighted words / phrases, in reading order (same rule as the template)."""
    from .templates.text import group_keys
    return group_keys([dict(w=r[0], mark=r[3], ar=r[4]) for r in rows])


def count_keys(rows):
    return len(_groups(rows))


def missing_arabic(rows):
    return [txt for txt, ar in _groups(rows) if not ar]


# ------------------------------------------------------------------ projects
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def video_name(par, k, taken):
    base = _BAD.sub(" ", par.get("title") or par.get("tab") or f"text {k}").strip(" .")[:70] or f"text {k}"
    name = f"{k:02d} {base}"
    n = 2
    while name.lower() in taken:
        name = f"{k:02d} {base} ({n})"
        n += 1
    taken.add(name.lower())
    return name


def part_project(base, par):
    """The editor's project with this paragraph's words, title and recording."""
    p = copy.deepcopy(base)
    d = p.setdefault("text", {})
    d["words"] = rows_text(par["rows"])
    if par.get("title"):
        d["title"] = par["title"]
    if par.get("subtitle"):
        d["subtitle"] = par["subtitle"]
    d["reading_audio"] = par.get("audio") or ""
    return p


def write_template(path):
    """A workbook with two example tabs in the layout described at the top of this file."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from .templates.text import EXAMPLE
    from .templates.text import parse_words
    wb = openpyxl.Workbook()
    words = parse_words(EXAMPLE["text"]["words"])
    for k, name in enumerate(["paragraph1", "paragraph2"]):
        ws = wb.active if k == 0 else wb.create_sheet()
        ws.title = name
        ws.append(HEADERS)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="0F6E74")
        for i, w in enumerate(words, 1):
            ws.append([i, w["w"], w["s"], w["e"], w["mark"] or None, w["ar"] or None,
                       (EXAMPLE["text"]["title"] if k == 0 else "Paragraph two title") if i == 1 else None,
                       EXAMPLE["text"]["subtitle"] if i == 1 else None])
        for col, width in zip("ABCDEFGH", [7, 18, 8, 8, 22, 26, 30, 22]):
            ws.column_dimensions[col].width = width
    wb.save(path)
    return path
