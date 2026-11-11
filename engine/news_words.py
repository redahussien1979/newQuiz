"""📰 English in News — the transcript editor behind the tab: ElevenLabs words -> the Words box, click a word to make
it a key word (the next word joins it into a phrase), the Arabic meanings table, and suggested key words.

The Words box (`news.words`) is the only place the choices live, one spoken word per line:
    word | start | end | highlighted | arabic
`*` in highlighted = the word itself; a phrase has its text (e.g. `cooling centres`) on each of its lines; the Arabic
sits on the first line of the word / phrase (the same format as 📖 English Texts, read by templates/news.py).
"""
import re

from . import paragraphs as para
from .templates.text import _clean, _groups, parse_words

_SENT = re.compile(r"[.!?…][\"'”’)\]]*$")


def _t(x):
    return f"{float(x):.2f}"


def dump(words):
    """Words (dicts w, s, e, mark, ar) -> the Words box text."""
    lines = []
    for w in words:
        parts = [w["w"], _t(w["s"]), _t(w["e"]), str(w.get("mark") or "").strip(), str(w.get("ar") or "").strip()]
        while len(parts) > 3 and not parts[-1]:
            parts.pop()
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def load(text):
    return parse_words(text)


def from_stt(stt):
    """ElevenLabs words -> the Words box text (no key words yet)."""
    return dump([dict(w=x["text"], s=x["start"], e=x["end"], mark="", ar="") for x in stt])


def groups(words):
    return _groups(words)


def view(words):
    """Value for the clickable gr.HighlightedText: one token per word, labelled with its key-word number."""
    lab = {}
    for n, g in enumerate(_groups(words), 1):
        for i in range(g["i0"], g["i1"] + 1):
            lab[i] = str(n)
    return [(w["w"] + " ", lab.get(i)) for i, w in enumerate(words)]


def _set_phrase(words, i0, i1, ar):
    if i1 > i0:
        text = " ".join(_clean(words[k]["w"]) for k in range(i0, i1 + 1))
        for k in range(i0, i1 + 1):
            words[k]["mark"], words[k]["ar"] = text, ""
    else:
        words[i0]["mark"], words[i0]["ar"] = "*", ""
    words[i0]["ar"] = ar


def toggle(words, i, join=True):
    """Click on word i: a key word (or phrase) is removed; else the word becomes a key word — or, when `join` and the
    word just before it is the end of a key word, that key word grows into a phrase."""
    if not 0 <= i < len(words):
        return words
    gs = _groups(words)
    for g in gs:
        if g["i0"] <= i <= g["i1"]:
            for k in range(g["i0"], g["i1"] + 1):
                words[k]["mark"], words[k]["ar"] = "", ""
            return words
    prev = next((g for g in gs if g["i1"] == i - 1), None)
    if join and prev is not None and not _SENT.search(words[i - 1]["w"]):
        _set_phrase(words, prev["i0"], i, prev["ar"])
    else:
        _set_phrase(words, i, i, "")
    return words


def clear(words):
    for w in words:
        w["mark"], w["ar"] = "", ""
    return words


def table(words):
    """Rows for the meanings table: [#, key word, Arabic]."""
    return [[n, g["text"], g["ar"]] for n, g in enumerate(_groups(words), 1)]


def set_meanings(words, rows):
    """The meanings table back: each row's Arabic goes onto its key word (rows match the key words in order)."""
    gs = _groups(words)
    for g, row in zip(gs, rows or []):
        ar = str(row[2] if len(row) > 2 and row[2] is not None else "").strip()
        for k in range(g["i0"], g["i1"] + 1):
            words[k]["ar"] = ""
        words[g["i0"]]["ar"] = ar
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
