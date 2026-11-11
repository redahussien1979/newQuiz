"""✍️ Paragraphs (English Texts): paste paragraphs, click words to highlight them, let ElevenLabs read them, render.

Paste box: paragraphs separated by an empty line; an optional first line `# Title`. One paragraph = one video.

The choices are kept in a small JSON "store" saved with the project (text.para_store):
    {"marks": {key: [[phrase, n], ...]},          highlighted words / phrases (normalised words, n-th occurrence)
     "meanings": {key: {phrase: arabic}},          the Arabic meaning of each highlighted phrase
     "translations": {key: arabic},                the Arabic translation of the whole paragraph
     "heads": {key: {phrase: headword}}}           how the Word Bank writes a phrase when it differs from the text
                                                   (a dictionary form from Excel: "give (something) a wide berth")
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
    heads = store.get("heads", {}).get(p["key"], {})
    out = []
    for i0, i1 in groups(p, store):
        ph = " ".join(_norm(w) for w in p["words"][i0:i1 + 1])
        shown = heads.get(ph) or " ".join(_clean(w) for w in p["words"][i0:i1 + 1])
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


def _take_files(p, aliases, data_dir, settings):
    """(current mp3, current json, previous mp3, previous json) of the paragraph's voice with these settings."""
    text, _ = spoken(p, aliases)
    key = el.cache_key(text, settings["voice_id"], settings["model"], settings["speed"], settings["stability"],
                       settings["similarity"])
    base = os.path.join(data_dir, "tts", key)
    return base + ".mp3", base + ".json", base + ".prev.mp3", base + ".prev.json"


def has_previous(p, aliases, data_dir, settings):
    _, _, pm, pj = _take_files(p, aliases, data_dir, settings)
    return os.path.isfile(pm) and os.path.isfile(pj)


def regenerate(p, aliases, data_dir, settings):
    """A new take of the paragraph's voice (ElevenLabs reads it again: only this paragraph's characters are
    charged). The take it replaces is kept as the previous take. Returns (mp3, word times)."""
    cm, cj, pm, pj = _take_files(p, aliases, data_dir, settings)
    if os.path.isfile(cm) and os.path.isfile(cj):
        os.replace(cm, pm)
        os.replace(cj, pj)
    try:
        return voice_for(p, aliases, data_dir, settings)
    except Exception:
        if os.path.isfile(pm) and not os.path.isfile(cm):  # ElevenLabs failed: keep the take we had
            os.replace(pm, cm)
            os.replace(pj, cj)
        raise


def swap_takes(p, aliases, data_dir, settings):
    """Back to the previous take (the current one becomes the previous: press again to come back). No credits."""
    cm, cj, pm, pj = _take_files(p, aliases, data_dir, settings)
    if not (os.path.isfile(pm) and os.path.isfile(pj)):
        raise RuntimeError("There is no previous take of this paragraph yet (🔄 Regenerate voice makes one).")
    tmp_m, tmp_j = cm + ".swap", cj + ".swap"
    if os.path.isfile(cm):
        os.replace(cm, tmp_m)
        os.replace(cj, tmp_j)
    os.replace(pm, cm)
    os.replace(pj, cj)
    if os.path.isfile(tmp_m):
        os.replace(tmp_m, pm)
        os.replace(tmp_j, pj)
    return voice_for(p, aliases, data_dir, settings, make=False)


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
    heads = store.get("heads", {}).get(p["key"], {})
    mark = {}
    for i0, i1 in groups(p, store):
        ph = " ".join(_norm(w) for w in p["words"][i0:i1 + 1])
        shown = heads.get(ph) or " ".join(_clean(w) for w in p["words"][i0:i1 + 1])
        if i1 > i0 and " " not in shown:  # a one-word headword over a phrase: keep the rows one phrase
            shown = " ".join(_clean(w) for w in p["words"][i0:i1 + 1])
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


# ------------------------------------------------------------------ finding a sheet's word in the text
# Irregular past forms -> base (the -s / -ed / -ing forms are handled by _bases).
_IRREG = {}
for _base, _forms in {
        "be": "am is are was were been being", "have": "has had having", "do": "does did done doing",
        "go": "goes went gone going", "make": "made", "take": "took taken", "give": "gave given", "get": "got gotten",
        "come": "came", "run": "ran", "see": "saw seen", "keep": "kept", "bring": "brought", "buy": "bought",
        "think": "thought", "fight": "fought", "catch": "caught", "teach": "taught", "seek": "sought",
        "hold": "held", "fall": "fell fallen", "break": "broke broken", "speak": "spoke spoken",
        "throw": "threw thrown", "draw": "drew drawn", "grow": "grew grown", "know": "knew known",
        "blow": "blew blown", "fly": "flew flown", "show": "showed shown", "write": "wrote written",
        "ride": "rode ridden", "rise": "rose risen", "drive": "drove driven", "eat": "ate eaten",
        "beat": "beaten", "bite": "bit bitten", "hide": "hid hidden", "forget": "forgot forgotten",
        "choose": "chose chosen", "freeze": "froze frozen", "steal": "stole stolen", "wake": "woke woken",
        "wear": "wore worn", "tear": "tore torn", "bear": "bore borne born", "swear": "swore sworn",
        "begin": "began begun", "drink": "drank drunk", "sing": "sang sung", "swim": "swam swum",
        "ring": "rang rung", "sink": "sank sunk", "shrink": "shrank shrunk", "spring": "sprang sprung",
        "stand": "stood", "understand": "understood", "sit": "sat", "win": "won", "lose": "lost",
        "find": "found", "feel": "felt", "leave": "left", "meet": "met", "pay": "paid", "say": "said",
        "lay": "laid", "lie": "lay lain lying", "tell": "told", "sell": "sold", "send": "sent", "spend": "spent",
        "lend": "lent", "build": "built", "bend": "bent", "lead": "led", "feed": "fed", "hear": "heard",
        "mean": "meant", "deal": "dealt", "sleep": "slept", "sweep": "swept", "weep": "wept", "creep": "crept",
        "light": "lit", "slide": "slid", "stick": "stuck", "strike": "struck", "swing": "swung",
        "hang": "hung", "dig": "dug", "shoot": "shot", "shine": "shone", "spin": "spun", "flee": "fled",
        "become": "became", "overcome": "overcame", "undergo": "underwent undergone", "withdraw": "withdrew withdrawn",
        "foresee": "foresaw foreseen", "mistake": "mistook mistaken", "shake": "shook shaken",
        "bid": "bade bidden", "tread": "trod trodden", "weave": "wove woven",
}.items():
    for _f in _forms.split():
        _IRREG.setdefault(_f, set()).add(_base)
_GAP = {"something", "someone", "somebody", "sth", "sb", "smth", "sth.", "sb."}
_POSS = {"one's", "someone's", "somebody's", "sb's"}
_POSS_WORDS = {"my", "your", "his", "her", "its", "our", "their", "one's"}


def _bases(w):
    """The forms word w may be the inflection of (walked -> walk, making -> make, stopped -> stop, went -> go)."""
    out = {w} | _IRREG.get(w, set())
    for suf in ("s", "es", "ed", "d", "ing", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            b = w[:-len(suf)]
            out |= {b, b + "e"}
            if len(b) >= 3 and b[-1] == b[-2] and b[-1] not in "aeiouls":
                out.add(b[:-1])  # stopped -> stop
    for suf, rep in (("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y")):
        if w.endswith(suf):
            out.add(w[:-len(suf)] + rep)
    if w.endswith("'s") or w.endswith("’s"):
        out.add(w[:-2])
    return out


def _pattern(phrase):
    """Sheet phrase -> tokens: a word, ("gap",) for (something) / sb / sth, ("poss",) for one's / someone's."""
    toks = []
    for raw in re.sub(r"\(([^)]*)\)", lambda m: " (" + m.group(1).replace(" ", "_") + ") ", str(phrase)).split():
        if raw.startswith("(") and raw.endswith(")"):
            inner = raw[1:-1].replace("_", " ").lower().strip()
            if not inner or inner.split()[0] in _GAP or inner in _GAP:
                toks.append(("gap",))
            continue  # other bracketed notes ("(informal)") are ignored
        w = _norm(raw.replace("’", "'"))
        lw = raw.lower().replace("’", "'").strip(".,;:!?\"")
        if lw in _POSS:
            toks.append(("poss",))
        elif lw in _GAP:
            toks.append(("gap",))
        elif w:
            toks.append(w)
    while toks and toks[0] == ("gap",):
        toks.pop(0)
    while toks and toks[-1] == ("gap",):
        toks.pop()
    return toks


def _match_at(norm, i, toks, k=0, used=None):
    """Indices of the text words that match toks from word i on (None when they don't)."""
    used = used or []
    if k == len(toks):
        return used
    if i >= len(norm):
        return None
    t = toks[k]
    if t == ("gap",):
        for skip in range(0, 6):  # (something) = up to 5 words
            r = _match_at(norm, i + skip, toks, k + 1, used)
            if r is not None:
                return r
        return None
    w = norm[i]
    if t == ("poss",):
        ok = w in _POSS_WORDS or w.endswith("'s") or w.endswith("’s")
    else:
        ok = w == t or t in _bases(w) or w in _bases(t)
    return _match_at(norm, i + 1, toks, k + 1, used + [i]) if ok else None


def find_phrase(p, phrase, taken=()):
    """(i0, i1) word range of the sheet's word / phrase in paragraph p — also an inflected form (go -> went,
    batten -> battened) and with (something) standing for a few words. The highlight covers the whole match, or,
    when (something) stretches it past 7 words, its longest unbroken part. None when it is not in the text."""
    toks = _pattern(phrase)
    if not toks:
        return None
    norm = [_norm(w) for w in p["words"]]
    for i in range(len(norm)):
        hit = _match_at(norm, i, toks)
        if not hit:
            continue
        i0, i1 = hit[0], hit[-1]
        if i1 - i0 + 1 > 7:
            runs, cur = [], [hit[0]]
            for j in hit[1:]:
                if j == cur[-1] + 1:
                    cur.append(j)
                else:
                    runs.append(cur)
                    cur = [j]
            runs.append(cur)
            best = max(runs, key=len)
            i0, i1 = best[0], best[-1]
        if any(not (i1 < a or i0 > b) for a, b in taken):
            continue
        return i0, i1
    return None


# ------------------------------------------------------------------ reading the sheet back
def _same(p, q):
    return p["key"] == q["key"] or [_norm(w) for w in p["words"]] == [_norm(w) for w in q["words"]]


def _block(title, body):
    return (f"# {title}\n" if title else "") + " ".join(str(body).split())


def import_xlsx(path, paras, store, text=""):
    """Read a words sheet (made by ⬇️ or written by hand) back: paragraphs that are not in the paste box yet are
    added to it (the 'paragraphs' tab: title + English paragraph), the words of the 'words' tab are found in their
    paragraph and highlighted (also an inflected form), their Arabic meanings and the paragraph translations filled
    in. Returns (store, new paste text or None when unchanged, message)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        prows = list(wb["paragraphs"].iter_rows(values_only=True))[1:] if "paragraphs" in wb.sheetnames else []
        wrows = list(wb["words"].iter_rows(values_only=True))[1:] if "words" in wb.sheetnames else []
    finally:
        wb.close()

    def cell(row, j):
        return str(row[j]).strip() if row and len(row) > j and row[j] is not None else ""

    paras = list(paras)
    blocks = [_block(p["title"], " ".join(p["words"])) for p in paras]
    added, trans = 0, 0
    by_num, by_title = {}, {}  # the sheet's paragraph number / title -> paragraph in the box
    for row in prows:
        title, body, ar = cell(row, 1), cell(row, 2), cell(row, 3)
        if not body and not title:
            continue
        q = None
        if body:
            new = parse(_block(title, body))
            q = new[0] if new else None
        p = next((x for x in paras if q and _same(x, q)), None)
        if p is None and title:
            p = next((x for x in paras if x["title"] and x["title"].lower() == title.lower()), None)
        if p is None and q is not None:
            paras.append(q)
            blocks.append(_block(title, body))
            p = q
            added += 1
        if p is None:
            continue
        if cell(row, 0).isdigit():
            by_num[int(cell(row, 0))] = p
        if title:
            by_title[title.lower()] = p
        if ar:
            store.setdefault("translations", {})[p["key"]] = " ".join(ar.split())
            trans += 1

    marked, filled, missing = 0, 0, []
    for row in wrows:
        num, title, phrase, ar = cell(row, 0), cell(row, 1), cell(row, 2), cell(row, 3)
        if not phrase:
            continue
        p = by_num.get(int(num)) if num.isdigit() else None
        p = p or by_title.get(title.lower().rstrip("…").strip())
        if p is None and title:
            p = next((x for x in paras if x["title"] and x["title"].lower() == title.lower()), None)
        if p is None and num.isdigit() and 0 < int(num) <= len(paras):
            p = paras[int(num) - 1]
        if p is None:
            missing.append(phrase)
            continue
        ph = " ".join(_norm(w) for w in phrase.split())
        gs = groups(p, store)
        have = next((g for g in gs if " ".join(_norm(w) for w in p["words"][g[0]:g[1] + 1]) == ph), None)
        if have is None:  # already highlighted in the form the text uses (went by the board <- go by the board)
            hit = find_phrase(p, phrase)
            have = hit if hit in gs else None
        if have is None:
            have = find_phrase(p, phrase, gs)
            if have is None:
                missing.append(phrase)
                continue
            _set_groups(p, store, gs + [have])
            marked += 1
        key_ph = " ".join(_norm(w) for w in p["words"][have[0]:have[1] + 1])
        shown = " ".join(_clean(w) for w in p["words"][have[0]:have[1] + 1])
        heads = store.setdefault("heads", {}).setdefault(p["key"], {})
        if _clean(phrase).lower() != shown.lower():
            heads[key_ph] = " ".join(phrase.split())
        else:
            heads.pop(key_ph, None)
        if ar:
            store.setdefault("meanings", {}).setdefault(p["key"], {})[key_ph] = " ".join(ar.split())
            filled += 1

    new_text = "\n\n".join(blocks) if added else None
    bits = []
    if added:
        bits.append(f"{added} paragraph{'s' if added != 1 else ''} added")
    if marked:
        bits.append(f"{marked} word{'s' if marked != 1 else ''} highlighted")
    bits.append(f"{filled} meaning{'s' if filled != 1 else ''}")
    bits.append(f"{trans} paragraph translation{'s' if trans != 1 else ''} filled in")
    msg = "✅ " + ", ".join(bits) + "."
    if missing:
        msg += f" ⚠️ Not found in the text: {', '.join(missing[:6])}{' …' if len(missing) > 6 else ''}."
    return store, new_text, msg
