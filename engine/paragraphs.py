"""✍️ Paragraphs (English Texts): paste paragraphs, click words to highlight them, let ElevenLabs read them, render.

Paste box: paragraphs separated by an empty line; an optional first line `# Title`. One paragraph = one video.

The choices are kept in a small JSON "store" saved with the project (text.para_store):
    {"marks": {key: [[phrase, n], ...]},          highlighted words / phrases (normalised words, n-th occurrence)
     "meanings": {key: {phrase: arabic}},          the Arabic meaning of each highlighted phrase
     "translations": {key: arabic}}                the Arabic translation of the whole paragraph
key = the paragraph's title, else its first words — so editing a paragraph elsewhere keeps its highlights.
"""
import copy
import os
import re

from . import elevenlabs as el
from .templates.text import _clean, make_video

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDS_PER_SECOND = 2.6  # a typical ElevenLabs reading pace, for the length estimate before the voice exists
_FREQ = None


# ------------------------------------------------------------------ paragraphs
def parse(text):
    """[dict(title, words, key)] from the paste box."""
    out = []
    for block in re.split(r"\n\s*\n", str(text or "").replace("\r", "")):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        title = ""
        if lines[0].startswith("#"):
            title = lines[0].lstrip("#").strip()
            lines = lines[1:]
        words = " ".join(lines).split()
        if not words:
            continue
        key = title or " ".join(_norm(w) for w in words[:8])
        out.append(dict(title=title, words=words, key=key))
    return out


def _norm(w):
    return _clean(w).lower()


def label(k, p):
    t = p["title"] or " ".join(p["words"][:6]) + "…"
    return f"{k + 1}. {t}"


# ------------------------------------------------------------------ highlights
def groups(p, store):
    """[(i0, i1)] word ranges of the paragraph's highlighted phrases, in reading order."""
    norm = [_norm(w) for w in p["words"]]
    out = []
    for phrase, n in store.get("marks", {}).get(p["key"], []):
        toks = phrase.split()
        hits = [i for i in range(len(norm) - len(toks) + 1) if norm[i:i + len(toks)] == toks]
        if n < len(hits):
            out.append((hits[n], hits[n] + len(toks) - 1))
    return sorted(set(out))


def _set_groups(p, store, gs):
    norm = [_norm(w) for w in p["words"]]
    marks = []
    for i0, i1 in sorted(gs):
        toks = norm[i0:i1 + 1]
        n = sum(1 for i in range(i0) if norm[i:i + len(toks)] == toks)
        marks.append([" ".join(toks), n])
    store.setdefault("marks", {})[p["key"]] = marks
    _prefill(p, store)
    return store


def _prefill(p, store):
    """A newly highlighted phrase takes the meaning it already has in another paragraph."""
    mine = store.setdefault("meanings", {}).setdefault(p["key"], {})
    known = {}
    for k, m in store["meanings"].items():
        for ph, ar in m.items():
            if ar:
                known.setdefault(ph, ar)
    for i0, i1 in groups(p, store):
        ph = " ".join(_norm(w) for w in p["words"][i0:i1 + 1])
        if not mine.get(ph) and known.get(ph):
            mine[ph] = known[ph]


def toggle(p, store, i, join=True):
    """A click on word i: a highlighted word is removed (a phrase loses that word); a plain word next to a highlight
    joins it as a phrase (when `join`), else becomes a highlight of its own."""
    gs = groups(p, store)
    for g in gs:
        if g[0] <= i <= g[1]:
            gs.remove(g)
            if g[0] < i:
                gs.append((g[0], i - 1))
            if i < g[1]:
                gs.append((i + 1, g[1]))
            return _set_groups(p, store, gs)
    if join:
        for g in gs:
            if g[1] == i - 1 and not re.search(r"[.!?,;:]$", p["words"][i - 1]):
                gs.remove(g)
                gs.append((g[0], i))
                return _set_groups(p, store, gs)
            if g[0] == i + 1 and not re.search(r"[.!?,;:]$", p["words"][i]):
                gs.remove(g)
                gs.append((i, g[1]))
                return _set_groups(p, store, gs)
    gs.append((i, i))
    return _set_groups(p, store, gs)


def clear(p, store):
    store.setdefault("marks", {})[p["key"]] = []
    return store


def view(p, store):
    """Value for the clickable gr.HighlightedText: one token per word, labelled with its highlight number."""
    lab = {}
    for n, (i0, i1) in enumerate(groups(p, store), 1):
        for i in range(i0, i1 + 1):
            lab[i] = str(n)
    return [(w + " ", lab.get(i)) for i, w in enumerate(p["words"])]


def phrases(p, store):
    """[(phrase as written, normalised phrase, arabic)] in reading order."""
    m = store.get("meanings", {}).get(p["key"], {})
    out = []
    for i0, i1 in groups(p, store):
        shown = " ".join(_clean(w) for w in p["words"][i0:i1 + 1])
        ph = " ".join(_norm(w) for w in p["words"][i0:i1 + 1])
        out.append((shown, ph, m.get(ph, "")))
    return out


def words_md(p, store):
    ph = phrases(p, store)
    if not ph:
        return "_No highlighted words yet — click words in the paragraph above (or ✨ Suggest)._"
    rows = [f"{n}. **{s}** → {ar}" if ar else f"{n}. **{s}** → ⚠️ _no Arabic yet_" for n, (s, _, ar) in enumerate(ph, 1)]
    tr = store.get("translations", {}).get(p["key"], "")
    return "  \n".join(rows) + ("\n\n🌐 Paragraph translation ✓" if tr else "")


# ------------------------------------------------------------------ suggested (less common) words
def _freq():
    global _FREQ
    if _FREQ is None:
        _FREQ = {}
        try:
            with open(os.path.join(ROOT, "data", "english_freq.txt"), encoding="utf-8") as f:
                for n, w in enumerate(f, 1):
                    _FREQ.setdefault(w.strip(), n)
        except OSError:
            pass
    return _FREQ


def rank(word):
    """How common a word is (1 = most common), trying its base form too (pledges -> pledge, studied -> study)."""
    f = _freq()
    w = _norm(word).replace("’", "'")
    if "'" in w:
        w = w.split("'")[0]
    cands = [w]
    for suf, rep in (("ies", "y"), ("es", ""), ("s", ""), ("ied", "y"), ("ed", ""), ("ed", "e"), ("ing", ""),
                     ("ing", "e"), ("ly", ""), ("er", ""), ("est", ""), ("ness", ""), ("ment", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            cands.append(w[:-len(suf)] + rep)
    return min((f[c] for c in cands if c in f), default=len(f) + 1)


def suggest(p, store, n=5, common=6000):
    """Highlight up to n of the least common words (rarer than the `common` most frequent English words), skipping
    names (capitalised inside a sentence) and short words. Keeps the highlights already there."""
    gs = groups(p, store)
    taken = {i for a, b in gs for i in range(a, b + 1)}
    cands = []
    for i, w in enumerate(p["words"]):
        c = _clean(w)
        if i in taken or len(c) < 4 or not c.isalpha():
            continue
        start = i == 0 or re.search(r"[.!?]$", p["words"][i - 1])
        if c[0].isupper() and not start:
            continue  # a name (Antalya, Paris)
        r = rank(c)
        if r > common and r <= len(_freq()):
            cands.append((r, i))
    have = len(gs)
    for r, i in sorted(cands, reverse=True):
        if have >= n:
            break
        if any(_norm(p["words"][i]) == _norm(p["words"][j]) for a, b in gs for j in range(a, b + 1)):
            continue
        gs.append((i, i))
        have += 1
    return _set_groups(p, store, gs)


# ------------------------------------------------------------------ "say it differently"
def parse_aliases(text):
    """'COP29 = cop twenty-nine' lines -> {normalised screen word: spoken form}."""
    out = {}
    for line in str(text or "").splitlines():
        if "=" in line:
            a, b = line.split("=", 1)
            if _norm(a) and b.strip():
                out[_norm(a)] = b.strip()
    return out


def spoken(p, aliases):
    """(text sent to ElevenLabs, [(a, b)] span of each screen word in it). A word with an alias is spoken
    differently but keeps its punctuation."""
    parts, spans, pos = [], [], 0
    for w in p["words"]:
        s = w
        core = _clean(w)
        if core and _norm(w) in aliases:
            k = w.find(core)
            s = w[:k] + aliases[_norm(w)] + w[k + len(core):]
        if parts:
            pos += 1
        spans.append((pos, pos + len(s)))
        parts.append(s)
        pos += len(s)
    return " ".join(parts), spans


# ------------------------------------------------------------------ voice
def voice_for(p, aliases, data_dir, settings, make=True):
    """(mp3, word times) of the paragraph: cached, else (make=True) asks ElevenLabs. None when not made."""
    text, spans = spoken(p, aliases)
    cache = os.path.join(data_dir, "tts")
    key = el.cache_key(text, settings["voice_id"], settings["model"], settings["speed"], settings["stability"],
                       settings["similarity"])
    hit = el.cached(cache, key)
    if not hit and not make:
        return None
    mp3, al = hit or el.speak(text, cache, settings)
    return mp3, el.word_times(spans, text, al)


def chars_needed(paras, aliases, data_dir, settings):
    """Characters (= ElevenLabs credits) the paragraphs still need: cached ones cost nothing."""
    total = 0
    for p in paras:
        if voice_for(p, aliases, data_dir, settings, make=False) is None:
            total += len(spoken(p, aliases)[0])
    return total


# ------------------------------------------------------------------ the video project of a paragraph
def words_text(p, store, times=None):
    """The editor's Words box (word | start | end | highlighted | arabic) for the paragraph."""
    m = store.get("meanings", {}).get(p["key"], {})
    mark = {}
    for i0, i1 in groups(p, store):
        shown = " ".join(_clean(w) for w in p["words"][i0:i1 + 1])
        ph = " ".join(_norm(w) for w in p["words"][i0:i1 + 1])
        for i in range(i0, i1 + 1):
            mark[i] = (shown, m.get(ph, "") if i == i0 else "")
    lines = []
    for i, w in enumerate(p["words"]):
        parts = [w]
        if times:
            parts += [f"{times[i][0]:.3f}", f"{times[i][1]:.3f}"]
        else:
            parts += ["", ""]
        if i in mark:
            parts += [mark[i][0], mark[i][1]]
        while len(parts) > 1 and not parts[-1]:
            parts.pop()
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def project_for(base, p, store, mp3=None, times=None):
    proj = copy.deepcopy(base)
    d = proj.setdefault("text", {})
    d["words"] = words_text(p, store, times)
    d["title"] = p["title"] or d.get("title", "")
    d["translation"] = store.get("translations", {}).get(p["key"], "")
    d["reading_audio"] = mp3 or ""
    return proj


# ------------------------------------------------------------------ the meter
def meter(paras, store, base, aliases, data_dir, settings):
    """A table: per paragraph its words, length, pages in the chosen design, highlights, meanings, voice."""
    if not paras:
        return "_Paste paragraphs above (an empty line between them)._"
    rows = ["| # | Paragraph | Words | Length | Pages | Highlighted | Arabic | Voice |", "|---|---|---|---|---|---|---|---|"]
    total_chars = 0
    for k, p in enumerate(paras):
        hit = voice_for(p, aliases, data_dir, settings, make=False)
        if hit:
            secs = hit[1][-1][1]
            voice = "✅ ready"
        else:
            secs = len(p["words"]) / WORDS_PER_SECOND
            c = len(spoken(p, aliases)[0])
            total_chars += c
            voice = f"🎙️ {c} chars"
        try:
            v = make_video(project_for(base, p, store, *(hit or (None, None))), layout_only=True)
            pages = str(len(v.page_words))
        except Exception:
            pages = "?"
        ph = phrases(p, store)
        miss = sum(1 for _, _, ar in ph if not ar)
        t = (p["title"] or " ".join(p["words"][:5]) + "…").replace("|", "/")
        long_ = " ⚠️" if secs > 50 else ""
        rows.append(f"| {k + 1} | {t} | {len(p['words'])} | ~{secs:.0f} s{long_} | {pages} | {len(ph)} | "
                    f"{'✅' if ph and not miss else (f'⚠️ {miss} missing' if miss else '—')} | {voice} |")
    note = (f"\n\n**{total_chars} characters** still to be read by ElevenLabs (your credits); ready voices cost "
            f"nothing again." if total_chars else "\n\nAll voices are ready.")
    return "\n".join(rows) + note


# ------------------------------------------------------------------ meanings in Excel (download -> fill -> upload)
WORD_HEADERS = ["#", "Paragraph", "English word / phrase", "Arabic meaning"]
PARA_HEADERS = ["#", "Paragraph", "English paragraph", "Arabic translation of the paragraph"]


def export_xlsx(paras, store, path):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "words"
    ws.append(WORD_HEADERS)
    for k, p in enumerate(paras, 1):
        for shown, ph, ar in phrases(p, store):
            ws.append([k, p["title"] or " ".join(p["words"][:6]) + "…", shown, ar or None])
    ws2 = wb.create_sheet("paragraphs")
    ws2.append(PARA_HEADERS)
    for k, p in enumerate(paras, 1):
        ws2.append([k, p["title"] or "", " ".join(p["words"]), store.get("translations", {}).get(p["key"]) or None])
    for sh, widths in ((ws, [5, 34, 30, 40]), (ws2, [5, 30, 80, 80])):
        for c in sh[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="8C0E1A")
        for col, w in zip("ABCD", widths):
            sh.column_dimensions[col].width = w
        for row in sh.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top",
                                        horizontal="right" if c.column == 4 else "left")
    wb.save(path)
    return path


def import_xlsx(path, paras, store):
    """Fill meanings / translations from the sheet; returns (store, message)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    filled, trans = 0, 0
    try:
        if "words" in wb.sheetnames:
            for row in list(wb["words"].iter_rows(values_only=True))[1:]:
                if not row or len(row) < 4 or not row[2] or not row[3]:
                    continue
                k = int(row[0]) - 1 if str(row[0] or "").strip().isdigit() else -1
                ph = " ".join(_norm(w) for w in str(row[2]).split())
                targets = [paras[k]] if 0 <= k < len(paras) else paras
                for p in targets:
                    if any(x[1] == ph for x in phrases(p, store)):
                        store.setdefault("meanings", {}).setdefault(p["key"], {})[ph] = str(row[3]).strip()
                        filled += 1
        if "paragraphs" in wb.sheetnames:
            for row in list(wb["paragraphs"].iter_rows(values_only=True))[1:]:
                if not row or len(row) < 4 or not row[3] or not str(row[0] or "").strip().isdigit():
                    continue
                k = int(row[0]) - 1
                if 0 <= k < len(paras):
                    store.setdefault("translations", {})[paras[k]["key"]] = " ".join(str(row[3]).split())
                    trans += 1
    finally:
        wb.close()
    return store, f"✅ {filled} meaning{'s' if filled != 1 else ''} and {trans} paragraph translation" \
                  f"{'s' if trans != 1 else ''} filled in."
