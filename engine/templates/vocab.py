"""English Words: teach English words, political terms, proverbs, idioms and common mistakes to Arabic speakers.

A video belongs to one group (General words, Political words, Proverbs, Idioms, Common mistakes or your own
group): the group sets the badge, the accent colour and the background theme. Inside a video every item has a
type, and types can be mixed:

    word     word card: word, IPA, part of speech, Arabic meaning, example (+ translation), similar words.
             In a "news" group (Political words) the example is shown as a BREAKING NEWS headline.
    guess    guess the meaning: the word, 2-4 options, a countdown, the correct one lights up, then the example
    reverse  the same with Arabic shown and English options ("How do you say it in English?")
    mistake  wrong sentence (struck out with a buzz) -> correct sentence -> rule -> example
    proverb  English proverb word by word -> literal translation -> the Arabic equivalent proverb -> example
    idiom    the idiom -> literal meaning (crossed out) -> the real meaning -> example
    list     one page of 1-6 words with their Arabic meanings ("- English = /ipa/ = Arabic" lines), read one after
             another (clips w1_1, w1_2 …): the word being read is highlighted. Two page designs (LIST_STYLES):
             Editorial (magazine page) and Chalkboard (hand-written chalk)

Items are written in a small "key: value" format (see EXAMPLE and parse_items()); the Excel batch
(engine/vocab_batch.py) builds the same text. Audio clips named w1 / w1e (word 1 / its example) are played on
the item and the scene waits for them. Every frame depends only on t (frames are drawn on several processes)."""
import math
import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ..audio import audio_length
from ..batch import _norm as norm_key
from ..core import _prep as prep_text
from ..core import (GREY, HAS_RAQM, ROOT, WHITE, Stars, draw_ending, ease_io, ease_out_back, ellipsize, get_font, get_theme,
                    global_fade, is_rtl, make_bg, parse_lines, paste, prog, shade, text_img, text_width, to_rgb, wrap)
from ..strings import S
from ..timers import FOOTPRINT, TIMER_FX, TIMER_NAMES, draw_timer
from ..title_fx import TitleIntro

NAME = "English Words"

# ------------------------------------------------------------------ groups
# accent / theme are the defaults; the app can override both. news = examples look like a TV news headline.
GROUPS = {
    "general": dict(label="General words", badge="WORDS • كلمات", color=(245, 197, 66), theme="Royal Blue",
                    news=False, title=("{count} English Words", "كلمات إنجليزية يجب أن تعرفها!",
                                       "Words you need to know!")),
    "politics": dict(label="Political words", badge="POLITICS • سياسة", color=(88, 160, 255), theme="Royal Blue",
                     news=True, title=("{count} Political Words", "كلمات تسمعها في الأخبار كل يوم!",
                                       "Words you hear in the news every day!")),
    "proverbs": dict(label="Proverbs", badge="PROVERBS • أمثال", color=(70, 205, 150), theme="Emerald",
                     news=False, title=("{count} English Proverbs", "وما يقابلها من الأمثال العربية",
                                        "and their Arabic equivalents")),
    "idioms": dict(label="Idioms", badge="IDIOMS • تعابير", color=(170, 130, 255), theme="Deep Purple",
                   news=False, title=("{count} English Idioms", "تعابير يستخدمها أهل اللغة كل يوم",
                                      "Expressions native speakers use every day")),
    "mistakes": dict(label="Common mistakes", badge="MISTAKES • أخطاء شائعة", color=(255, 96, 96), theme="Crimson",
                     news=False, title=("{count} Common Mistakes", "أخطاء شائعة عند العرب — هل تقع فيها؟",
                                        "Mistakes almost everyone makes")),
}
GROUP_KEYS = list(GROUPS) + ["custom"]
GROUP_CHOICES = [("📘 General words", "general"), ("🏛️ Political words", "politics"), ("📜 Proverbs", "proverbs"),
                 ("💬 Idioms", "idioms"), ("⚠️ Common mistakes", "mistakes"), ("➕ Your own group", "custom")]
# titles used when every item of the video is a guess
QUIZ_TITLES = {"proverbs": ("Guess the Arabic Proverb!", "{count} أمثال — كم مثلًا عرفت؟", "{count} proverbs — how many can you match?"),
               "mistakes": ("Which One Is Correct?", "{count} أسئلة — اختبر لغتك الإنجليزية", "{count} questions — test your English"),
               None: ("Guess the Meaning!", "{count} أسئلة — كم إجابة صحيحة؟", "{count} questions — how many can you get?")}
_GROUP_WORDS = {
    "general": ["general", "words", "word", "generalwords", "vocabulary", "vocab", "عام", "كلمات", "كلمه", "مفردات"],
    "politics": ["politics", "political", "politicalwords", "politic", "news", "سياسه", "سياسي", "سياسيه",
                 "كلماتسياسيه", "مصطلحاتسياسيه", "اخبار"],
    "proverbs": ["proverbs", "proverb", "sayings", "saying", "امثال", "الامثال", "مثل", "حكم"],
    "idioms": ["idioms", "idiom", "expressions", "expression", "تعابير", "تعبير", "اصطلاحات", "عبارات"],
    "mistakes": ["mistakes", "mistake", "commonmistakes", "errors", "اخطاء", "اخطاءشائعه", "خطا", "خطاشائع"],
}
GROUP_LOOKUP = {norm_key(w): k for k, ws in _GROUP_WORDS.items() for w in ws}
CUSTOM_COLORS = [(255, 150, 60), (70, 220, 230), (255, 110, 160), (226, 184, 102), (150, 200, 90)]


def group_key(txt):
    """'Political' / 'سياسة' -> 'politics'; '' -> 'general'; any other name -> None (= a custom group)."""
    t = norm_key(txt)
    if not t:
        return "general"
    return GROUP_LOOKUP.get(t)


def custom_color(name):
    """A stable colour for a custom group name (the same name always gets the same colour)."""
    return CUSTOM_COLORS[sum(ord(c) for c in str(name)) % len(CUSTOM_COLORS)]


# ------------------------------------------------------------------ item text format
TYPES = ["word", "guess", "reverse", "mistake", "proverb", "idiom", "list"]
TYPE_CHOICES = [("Word card", "word"), ("Guess the meaning", "guess"), ("Reverse guess (Arabic → English)", "reverse"),
                ("Common mistake", "mistake"), ("Proverb", "proverb"), ("Idiom", "idiom"),
                ("Word list (several words on one page)", "list")]
_TYPE_WORDS = {"word": ["word", "card", "wordcard", "learn", "كلمه", "بطاقه"],
               "guess": ["guess", "quiz", "question", "mcq", "guessthemeaning", "تخمين", "خمن", "سؤال", "اختبار"],
               "reverse": ["reverse", "reverseguess", "arabictoenglish", "عكسي", "عكس"],
               "mistake": ["mistake", "commonmistake", "error", "wrong", "خطا", "خطاشائع"],
               "proverb": ["proverb", "saying", "مثل", "حكمه"],
               "idiom": ["idiom", "expression", "phrase", "تعبير", "اصطلاح", "عباره"],
               "list": ["list", "wordlist", "words", "page", "listpage", "قائمه", "قائمهكلمات", "صفحه"]}
TYPE_LOOKUP = {norm_key(w): k for k, ws in _TYPE_WORDS.items() for w in ws}
_KEYS = {
    "type": ["type", "kind", "نوع", "النوع"],
    "word": ["word", "phrase", "proverb", "idiom", "expression", "term", "right", "rightsentence", "كلمه", "الكلمه",
             "عباره", "العباره", "المثل", "التعبير", "الصحيح", "الجملهالصحيحه"],
    "ipa": ["ipa", "pron", "pronunciation", "phonetic", "phonetics", "نطق", "النطق"],
    "pos": ["pos", "partofspeech", "wordtype", "class", "نوعالكلمه"],
    "meaning": ["meaning", "mean", "arabic", "معني", "المعني", "معناها"],
    "example": ["example", "ex", "sentence", "مثال", "المثال", "جمله"],
    "example_ar": ["examplear", "exampletranslation", "examplearabic", "exar", "translation", "ترجمه", "الترجمه",
                   "ترجمهالمثال"],
    "also": ["also", "synonyms", "synonym", "similar", "related", "similarwords", "مرادفات", "كلماتمشابهه"],
    "wrong": ["wrong", "mistake", "incorrect", "wrongsentence", "خطا", "الخطا", "الجملهالخاطئه"],
    "literal": ["literal", "literally", "literalmeaning", "حرفي", "الترجمهالحرفيه", "المعنيالحرفي"],
    "equivalent": ["equivalent", "arabicequivalent", "arabicproverb", "المقابل", "المثلالعربي", "المثلالمقابل"],
    "note": ["note", "extra", "ملاحظه"],
    "question": ["question", "prompt", "ask", "سؤال", "السؤال"],
    "answer": ["answer", "correct", "correctoption", "الاجابه", "الجواب"],
    "recap": ["recap", "summary", "ملخص"],
    "group": ["group", "category", "مجموعه", "المجموعه", "فئه", "الفئه", "تصنيف"],
    "title": ["title", "heading", "pagetitle", "عنوان", "العنوان"],
    "subtitle": ["subtitle", "titlear", "arabictitle", "pagesubtitle", "عنوانفرعي", "العنوانالفرعي"],
}
KEY_LOOKUP = {norm_key(a): k for k, names in _KEYS.items() for a in names}
_KEY_LINE = re.compile(r"^\s*([^:：]{1,32}?)\s*[:：]\s?(.*)$")
_OPT_LINE = re.compile(r"^\s*[-•–]\s*(.*)$")
_ANSWER = {"a": 0, "b": 1, "c": 2, "d": 3, "ا": 0, "ب": 1, "ج": 2, "د": 3, "1": 0, "2": 1, "3": 2, "4": 3}
MAX_ITEMS = 10
LIST_MAX = 6  # words on one word-list page
_LIST_SEP = re.compile(r"\s*[=|]\s*")
_LIST_SEP2 = re.compile(r"\s*[:：\t]\s*")


def clean_ipa(txt):
    t = " ".join(str(txt or "").split())
    if not t:
        return ""
    if t[0] in "/[" and t[-1] in "/]":
        return t
    return "/" + t.strip("/[]") + "/"


def _split_list(txt):
    return [w.strip() for w in re.split(r"[,،;؛|]", str(txt or "")) if w.strip()][:4]


def _blocks(text):
    """Split the items text into blocks (an empty line or a line of --- between items)."""
    blocks, cur = [], []
    for n, line in enumerate(str(text or "").replace("\r", "").split("\n"), 1):
        if not line.strip() or re.fullmatch(r"\s*-{3,}\s*", line):
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append((n, line))
    if cur:
        blocks.append(cur)
    return blocks


def parse_items(text):
    """Items text -> list of item dicts. Raises ValueError naming the item and the problem."""
    items = []
    for b, block in enumerate(_blocks(text), 1):
        it = {k: "" for k in _KEYS}
        opts, stars = [], []
        for n, line in block:
            mo = _OPT_LINE.match(line)
            mk = None if mo else _KEY_LINE.match(line)
            key = KEY_LOOKUP.get(norm_key(mk.group(1))) if mk else None
            if key:
                val = " ".join(mk.group(2).split())
                if key in ("example", "example_ar", "meaning", "note") and it[key]:
                    it[key] += " " + val  # a second line continues the field
                else:
                    it[key] = val
            elif mo:
                o = " ".join(mo.group(1).split())
                star = o.startswith("*") or o.endswith("*")
                o = o.strip("*").strip()
                if o:
                    opts.append(o)
                    stars.append(star)
            else:
                raise ValueError(f"Item {b} (line {n}): “{line.strip()[:40]}” is not understood — start the line "
                                 f"with a key like word:, meaning:, example: … or with - for an option")
        items.append(_finish(b, it, opts, stars))
    if not items:
        raise ValueError("Add at least one item (word:, meaning: …).")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"At most {MAX_ITEMS} items per video (there are {len(items)}) — use the Excel batch "
                         f"for more.")
    return items


def _finish(b, it, opts, stars):
    """Validate one parsed block and fill in its type."""
    where = f"Item {b}"
    typ = ""
    if it["type"]:
        typ = TYPE_LOOKUP.get(norm_key(it["type"]))
        if not typ:
            raise ValueError(f"{where}: unknown type “{it['type']}” — use word, guess, reverse, mistake, proverb, "
                             f"idiom or list")
    elif opts and all(_LIST_SEP.search(o) for o in opts) and not it["word"] and not it["question"]:
        typ = "list"
    elif opts:
        typ = "reverse" if is_rtl(it["word"]) and not any(is_rtl(o) for o in opts) else "guess"
    elif it["wrong"]:
        typ = "mistake"
    elif it["equivalent"]:
        typ = "proverb"
    elif it["literal"]:
        typ = "idiom"
    else:
        typ = "word"
    if typ == "list":
        if not opts:
            raise ValueError(f"{where} (list): add the words as lines like “- Airport = مطار”")
        if len(opts) > LIST_MAX:
            raise ValueError(f"{where} (list): at most {LIST_MAX} words on one page (there are {len(opts)}) — "
                             f"start another list item for the rest")
        words = [list_word(o, f"{where} (list), word {k}") for k, o in enumerate(opts, 1)]
        return list_item(words, it["title"], it["subtitle"], it["group"])
    out = dict(type=typ, word=it["word"], ipa=clean_ipa(it["ipa"]), pos=it["pos"], meaning=it["meaning"],
               example=it["example"], example_ar=it["example_ar"], also=_split_list(it["also"]), wrong=it["wrong"],
               literal=it["literal"], equivalent=it["equivalent"], note=it["note"], question=it["question"],
               recap=it["recap"], group=it["group"], options=[], correct=None, words=[], title="", subtitle="")
    if typ in ("guess", "reverse"):
        if not 2 <= len(opts) <= 4:
            raise ValueError(f"{where}: a guess needs 2 to 4 options (lines starting with -), it has {len(opts)}")
        correct = None
        if it["answer"]:
            k = norm_key(it["answer"])
            if k in _ANSWER and _ANSWER[k] < len(opts):
                correct = _ANSWER[k]
            else:
                hits = [i for i, o in enumerate(opts) if norm_key(o) == k]
                correct = hits[0] if hits else None
            if correct is None:
                raise ValueError(f"{where}: answer “{it['answer']}” does not match an option (use A–D or the text)")
        elif stars.count(True) == 1:
            correct = stars.index(True)
        else:
            raise ValueError(f"{where}: mark the correct option with * at the end of its line "
                             f"({'none' if not any(stars) else 'more than one'} is marked)")
        if not (out["word"] or out["question"]):
            raise ValueError(f"{where}: a guess needs the word (word:) or a question (question:)")
        out["options"], out["correct"] = opts, correct
    elif opts:
        raise ValueError(f"{where}: options (- lines) are only used by guess / reverse items")
    need = {"word": [("word", "the word (word:)"), ("meaning", "its meaning (meaning:)")],
            "mistake": [("wrong", "the wrong sentence (wrong:)"), ("word", "the correct sentence (word: or right:)")],
            "proverb": [("word", "the proverb (word:)")],
            "idiom": [("word", "the idiom (word:)"), ("meaning", "its real meaning (meaning:)")]}.get(typ, [])
    for k, what in need:
        if not out[k]:
            raise ValueError(f"{where} ({typ}): add {what}")
    if typ == "proverb" and not (out["equivalent"] or out["meaning"]):
        raise ValueError(f"{where} (proverb): add the Arabic equivalent (equivalent:) or its meaning (meaning:)")
    return out


def list_word(line, where="Word"):
    """'Airport = /ˈeəpɔːt/ = مطار' (or with | between the parts) -> dict(en, ipa, ar)."""
    raw = " ".join(str(line or "").split())
    parts = [p.strip() for p in _LIST_SEP.split(raw) if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in _LIST_SEP2.split(raw, maxsplit=2) if p.strip()]
    ipa = next((p for p in parts if p[0] in "/[" and p[-1] in "/]"), "")
    rest = [p for p in parts if p is not ipa]
    if len(rest) < 2:
        raise ValueError(f"{where}: write it as “English = Arabic” (got “{raw[:40]}”)")
    return dict(en=rest[0], ipa=clean_ipa(ipa), ar=" ".join(rest[1:]))


def list_item(words, title="", subtitle="", group=""):
    """A word-list item (the same keys as every other item, so the rest of the code can read it)."""
    out = {k: "" for k in ("word", "ipa", "pos", "meaning", "example", "example_ar", "wrong", "literal", "equivalent",
                           "note", "question", "recap")}
    out.update(type="list", also=[], options=[], correct=None, group=group or "", words=list(words),
               title=" ".join(str(title or "").split()), subtitle=" ".join(str(subtitle or "").split()))
    return out


def items_text(items):
    """The editor's text for a list of item dicts (inverse of parse_items, used by the Excel batch)."""
    blocks = []
    for it in items:
        lines = ([f"group: {it['group']}"] if it.get("group") else []) + [f"type: {it['type']}"]
        if it["type"] == "list":
            lines += [f"{k}: {it[k]}" for k in ("title", "subtitle") if it.get(k)]
            lines += ["- " + " = ".join(x for x in (w["en"], w["ipa"], w["ar"]) if x) for w in it["words"]]
            blocks.append("\n".join(lines))
            continue
        for k in ("word", "ipa", "pos", "question", "wrong", "meaning", "literal", "equivalent", "note"):
            if it.get(k):
                lines.append(f"{k}: {it[k]}")
        for i, o in enumerate(it.get("options") or []):
            lines.append(f"- {o}{' *' if i == it.get('correct') else ''}")
        for k in ("example", "example_ar"):
            if it.get(k):
                lines.append(f"{k}: {it[k]}")
        if it.get("also"):
            lines.append("also: " + ", ".join(it["also"]))
        if it.get("recap"):
            lines.append(f"recap: {it['recap']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ------------------------------------------------------------------ audio clips
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma")
_CLIP_RE = re.compile(r"^(?:w|word|item)?[\s_.\-]*0*(\d{1,2})"
                      r"(?:[\s_.\-]*(e|ex|example)|[\s_.\-]+0*(\d{1,2}))?$", re.I)


def clip_key(path):
    """'w3' / 'word3' / '3' -> (3, 'w'); 'w3e' / 'w3_example' -> (3, 'e'); 'w3_2' / 'w3-2' -> (3, 'l2')
    (word 2 of the word list in item 3); None if the name does not match."""
    stem, ext = os.path.splitext(os.path.basename(str(path)))
    m = _CLIP_RE.match(stem.strip())
    if not m or ext.lower() not in AUDIO_EXT:
        return None
    if m.group(3):
        return int(m.group(1)), f"l{int(m.group(3))}"
    return int(m.group(1)), ("e" if m.group(2) else "w")


def match_clips(paths, items):
    """Map uploaded clips to items. Returns ({(item_index, 'w'|'e'|'l<k>'): path}, [problems])."""
    found, problems = {}, []
    for path in paths or []:
        if not path or not os.path.isfile(str(path)):
            continue
        name = os.path.basename(str(path))
        key = clip_key(path)
        if key is None:
            problems.append(f"`{name}`: name not recognised (use w1 for item 1, w1e for its example)")
            continue
        n, slot = key
        if not 1 <= n <= len(items):
            problems.append(f"`{name}`: there is no item {n}")
            continue
        it = items[n - 1]
        if it["type"] == "list":
            if slot[0] != "l":
                problems.append(f"`{name}`: item {n} is a word list — name its clips w{n}_1, w{n}_2 … "
                                f"(one per word)")
                continue
            if not 1 <= int(slot[1:]) <= len(it["words"]):
                problems.append(f"`{name}`: the word list in item {n} has no word {slot[1:]}")
                continue
        elif slot[0] == "l":
            problems.append(f"`{name}`: item {n} is not a word list (use w{n} for it, w{n}e for its example)")
            continue
        if slot == "e" and not items[n - 1]["example"]:
            problems.append(f"`{name}`: item {n} has no example, the clip is not played")
            continue
        if (n - 1, slot) in found:
            problems.append(f"`{name}`: replaces `{os.path.basename(found[(n - 1, slot)])}`")
        found[(n - 1, slot)] = str(path)
    return found, problems


def clips_report(paths, text):
    """Short Markdown summary of which clips belong to which item (for the app)."""
    paths = [p for p in (paths or []) if p]
    if not paths:
        return "No audio clips yet."
    try:
        items = parse_items(text)
    except ValueError as e:
        return f"⚠️ Fix the items first: {e}"
    found, problems = match_clips(paths, items)
    rows = []
    for i, it in enumerate(items):
        if it["type"] == "list":
            got = [str(k) for k in range(1, len(it["words"]) + 1) if (i, f"l{k}") in found]
            label = it["title"] or ", ".join(w["en"] for w in it["words"][:2]) + ("…" if len(it["words"]) > 2 else "")
            rows.append(f"**{i + 1}. {label}:** " + (f"words {', '.join(got)} of {len(it['words'])}" if got else "—"))
            continue
        parts = (["word"] if (i, "w") in found else []) + (["example"] if (i, "e") in found else [])
        rows.append(f"**{i + 1}. {it['word'] or it['question'] or it['type']}:** " + (" + ".join(parts) if parts else "—"))
    out = " · ".join(rows)
    if problems:
        out += "\n\n⚠️ " + "  \n⚠️ ".join(problems)
    return out


# ------------------------------------------------------------------ example project
EXAMPLE = {
    "template": "vocab",
    "settings": {"theme": "Royal Blue", "language": "ar", "fps": 30, "music": "Lo-fi Chill", "music_gain": 1.0,
                 "music_file": "", "voice_file": "", "voice_offset": 0.5, "voice_gain": 1.0,
                 "handle": "@Ma3loomaFast", "font_file": "", "intro_sound": "Swoosh + impact",
                 "tick_sound": "Classic", "tick_gain": 1.0},
    "ending": {"intro": "الدرس القادم:", "question": "5 English idioms\n[gold]عن المال والعمل",
               "cta": "أي كلمة كانت جديدة عليك؟ اكتبها في التعليقات"},
    "vocab": {
        "group": "politics",
        "group_name": "",
        "accent": "group",
        "background": "group",
        "title": "",
        "subtitle": "",
        "lesson": "English Lesson #{n}",
        "lesson_n": 12,
        "title_style": "Fancy",
        "hook": True,
        "items": ("type: word\nword: Sanctions\nipa: /ˈsæŋkʃənz/\npos: noun • اسم\nmeaning: عقوبات (على دولة أو جهة)\n"
                  "example: UN imposes new *sanctions* on the regime\nexample_ar: فرضت الأمم المتحدة عقوبات جديدة على النظام\n"
                  "also: embargo, penalties\n\n"
                  "type: word\nword: Referendum\nipa: /ˌrefəˈrendəm/\npos: noun • اسم\nmeaning: استفتاء شعبي\n"
                  "example: Voters reject the *referendum* by a narrow margin\n"
                  "example_ar: الناخبون يرفضون الاستفتاء بفارق ضئيل\nalso: vote, ballot\n\n"
                  "type: guess\nword: Ceasefire\nipa: /ˈsiːsfaɪər/\n- إعلان الحرب\n- وقف إطلاق النار *\n"
                  "- انتخابات مبكرة\n- تحالف عسكري\nexample: Both sides agreed to a *ceasefire* last night\n"
                  "example_ar: اتفق الطرفان على وقف إطلاق النار الليلة الماضية\n\n"
                  "type: word\nword: Coalition\nipa: /ˌkəʊəˈlɪʃn/\npos: noun • اسم\nmeaning: ائتلاف • تحالف\n"
                  "example: The new *coalition* government takes office\nexample_ar: حكومة الائتلاف الجديدة تتسلم السلطة\n"
                  "also: alliance, union\n\n"
                  "type: guess\nword: Veto\nipa: /ˈviːtəʊ/\n- حق النقض (الرفض) *\n- حق التصويت\n- حصانة دبلوماسية\n"
                  "- قرار ملزم\nexample: Russia uses its *veto* at the Security Council\n"
                  "example_ar: روسيا تستخدم حق النقض في مجلس الأمن"),
        "guess_seconds": 5,
        "timer": "Bar",
        "timer_fx": ["pulse", "glow"],
        "pace": "normal",
        "recap": True,
        "audio": [],
        "audio_gain": 1.0,
    },
}
PACES = [("Slow", "slow"), ("Normal", "normal"), ("Fast", "fast")]
PACE_K = {"slow": 1.25, "normal": 1.0, "fast": 0.82}
TITLE_STYLES = ["Fancy", "Simple"]
RECAP_MAX = 14  # recap rows on one screen (a word list adds one row per word)
LIST_STYLES = ["Editorial", "Chalkboard"]

IPA_FONT = os.path.join(ROOT, "fonts", "NotoSans-Bold.ttf")
INK = (20, 20, 30)
DIM = (70, 82, 115)
GREEN, RED, CYAN = (80, 210, 140), (255, 90, 90), (70, 220, 230)
NEWS_RED, NEWS_NAVY, NEWS_INK = (200, 30, 45), (18, 30, 64), (20, 24, 40)
INTRO = 2.6          # the first item starts here
EXIT = 0.35          # an item slides out during its last EXIT seconds
WIDE = 840           # content width (keeps text clear of the Shorts buttons on the right)
TOP, BOTTOM = 430, 1520   # content area under the header, above the captions zone
SCALES = (1.12, 1.06, 1.0, 0.92, 0.85, 0.78, 0.72, 0.66)  # a scene uses the biggest size that fits


# ------------------------------------------------------------------ drawing helpers
_ipa_cache, _img_cache = {}, {}


def ipa_img(txt, size, col):
    """IPA in Noto Sans (Cairo has no IPA letters); falls back to the main font if the file is missing."""
    key = (txt, size, col)
    if key in _ipa_cache:
        return _ipa_cache[key]
    if not os.path.isfile(IPA_FONT):
        return text_img(txt, size, col, "Bold", shadow=False)
    f = ImageFont.truetype(IPA_FONT, size, layout_engine=ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC)
    while size > 22 and f.getlength(txt) > WIDE - 110:
        size = int(size * 0.92)
        f = ImageFont.truetype(IPA_FONT, size, layout_engine=ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC)
    l, t, r, b = f.getbbox(txt)
    im = Image.new("RGBA", (r - l + 60, b - t + 60), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30 - l, 30 - t), txt, font=f, fill=tuple(col) + (255,))
    _ipa_cache[key] = im
    return im


def card(w, h, col, fill, alpha=240, r=44, width=4, glow=None):
    """Rounded card with a soft drop shadow (and an optional coloured glow). The image has a 40 px margin."""
    key = ("card", w, h, col, fill, alpha, r, width, glow)
    if key in _img_cache:
        return _img_cache[key]
    s = 2
    im = Image.new("RGBA", ((w + 80) * s, (h + 80) * s), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.rounded_rectangle([40 * s, 54 * s, (40 + w) * s, (54 + h) * s], r * s, fill=(0, 0, 0, 165))
    if glow:
        sd.rounded_rectangle([40 * s, 40 * s, (40 + w) * s, (40 + h) * s], r * s, fill=tuple(glow) + (140,))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(18 * s)))
    ImageDraw.Draw(im).rounded_rectangle([40 * s, 40 * s, (40 + w) * s, (40 + h) * s], r * s,
                                         fill=tuple(fill) + (alpha,), outline=tuple(col) + (255,), width=width * s)
    im = im.resize((w + 80, h + 80), Image.LANCZOS)
    _img_cache[key] = im
    return im


def pill(txt, size, fg, bg, padx=34, weight="Black"):
    t = text_img(txt, size, fg, weight, shadow=False, max_w=WIDE)
    h = int(size * 1.9)
    w = t.width - 60 + padx * 2
    s = 2
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * s - 1, h * s - 1], h * s // 2, fill=tuple(bg) + (255,))
    im = im.resize((w, h), Image.LANCZOS)
    im.alpha_composite(t, (w // 2 - t.width // 2, h // 2 - t.height // 2))
    return im


def mark(ok, r=40):
    """Round ✔ / ✖ badge (drawn: the fonts have no such glyphs)."""
    key = ("mark", ok, r)
    if key in _img_cache:
        return _img_cache[key]
    s = 3
    c = r * s
    im = Image.new("RGBA", (2 * c, 2 * c), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 2 * c - 1, 2 * c - 1], fill=(GREEN if ok else RED) + (255,))
    k = c / 40
    if ok:
        d.line([(c - 20 * k, c + 2 * k), (c - 5 * k, c + 18 * k), (c + 22 * k, c - 16 * k)], fill=(14, 40, 26),
               width=int(11 * k), joint="curve")
    else:
        for a, b in (((-16, -16), (16, 16)), ((-16, 16), (16, -16))):
            d.line([(c + a[0] * k, c + a[1] * k), (c + b[0] * k, c + b[1] * k)], fill=(60, 12, 14), width=int(11 * k))
    im = im.resize((2 * r, 2 * r), Image.LANCZOS)
    _img_cache[key] = im
    return im


def speaker_imgs(col):
    """(body, inner wave, outer wave) of the speaker icon, each 120x90 with the same origin."""
    key = ("spk", col)
    if key in _img_cache:
        return _img_cache[key]
    s = 3
    out = []
    for part in range(3):
        im = Image.new("RGBA", (120 * s, 90 * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx, cy = 45 * s, 45 * s
        if part == 0:
            d.rounded_rectangle([cx - 30 * s, cy - 13 * s, cx - 12 * s, cy + 13 * s], 3 * s, fill=tuple(col) + (255,))
            d.polygon([(cx - 14 * s, cy - 13 * s), (cx + 8 * s, cy - 32 * s), (cx + 8 * s, cy + 32 * s),
                       (cx - 14 * s, cy + 13 * s)], fill=tuple(col) + (255,))
        else:
            r = (20 if part == 1 else 35) * s
            d.arc([cx + 8 * s - r, cy - r, cx + 8 * s + r, cy + r], -45, 45, fill=tuple(col) + (255,), width=6 * s)
        out.append(im.resize((120, 90), Image.LANCZOS))
    _img_cache[key] = out
    return out


def baseline_img(txt, size, col, weight="Black"):
    """One line of text on a fixed-height image with the baseline at a fixed place, so short labels such as
    «خطأ» and «صحيح» sit at exactly the same height (centring by the ink box would move them)."""
    f = get_font(size, weight)
    t2, kw = prep_text(txt)
    w = int(f.getlength(t2, **({"direction": kw["direction"]} if "direction" in kw else {}))) + 40
    h = int(size * 1.7)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((w / 2, int(size * 1.2)), t2, font=f, fill=tuple(col) + (255,), anchor="ms", **kw)
    return im


def lines_img(lines, size, col, weight="Bold", shadow=False, pitch=None, align="c"):
    """Several lines of text on one image, centred (align 'c') or aligned left ('l') / right ('r')."""
    imgs = [text_img(l, size, col, weight, shadow=shadow) for l in lines]
    pitch = pitch or int(size * 1.34)
    w = max(i.width for i in imgs)
    hmax = max(i.height for i in imgs)
    im = Image.new("RGBA", (w, pitch * (len(imgs) - 1) + hmax), (0, 0, 0, 0))
    for k, i in enumerate(imgs):
        x = (w - i.width) // 2 if align == "c" else (0 if align == "l" else w - i.width)
        im.alpha_composite(i, (x, k * pitch + (hmax - i.height) // 2))
    return im


def balanced(wrap_fn, max_w):
    """Re-wrap at the narrowest width that keeps the same number of lines, so the lines come out even
    ("UN imposes new sanctions / on the regime" instead of a lonely last word)."""
    lines = wrap_fn(max_w)
    if len(lines) < 2:
        return lines
    lo, hi = max_w * 0.45, max_w
    for _ in range(9):
        mid = (lo + hi) / 2
        if len(wrap_fn(mid)) == len(lines):
            hi = mid
        else:
            lo = mid
    return wrap_fn(hi)


def fit_lines(txt, size, weight, max_w, max_lines=2, min_size=30, one_line_down_to=None):
    """Wrap `txt` evenly into at most max_lines lines, shrinking the size if needed. Returns (lines, size).
    one_line_down_to: first try to keep it on one line by shrinking down to this size."""
    if one_line_down_to:
        sz = size
        while sz >= one_line_down_to:
            if text_width(txt, sz, weight) <= max_w:
                return [" ".join(str(txt).split())], sz
            sz = int(sz * 0.95)
    while True:
        lines = wrap(txt, size, weight, max_w)
        if len(lines) <= max_lines or size <= min_size:
            break
        size = int(size * 0.92)
    # a single word longer than the line can't wrap: shrink until every line fits
    while size > 14 and max(text_width(l, size, weight) for l in lines) > max_w:
        size = int(size * 0.94)
        lines = wrap(txt, size, weight, max_w)
    return balanced(lambda w: wrap(txt, size, weight, w), max_w), size


def _strip_marks(raw):
    """'Children are *resilient*.' -> ('Children are resilient.', [(13, 22)])"""
    raw = " ".join(str(raw or "").split())
    clean, spans, start = [], [], None
    for ch in raw:
        if ch == "*":
            if start is None:
                start = len(clean)
            else:
                spans.append((start, len(clean)))
                start = None
            continue
        clean.append(ch)
    clean = "".join(clean)
    if start is not None:  # a lonely * : ignore it
        pass
    return clean, [(a, b) for a, b in spans if b > a]


def auto_span(text, target):
    """Find `target` (a word or phrase, any inflection like -s/-ed/-ing) inside text -> (start, end) or None.
    A phrase that the example only partly repeats ("It costs an arm and a leg" in "This phone costs an arm and a
    leg") is matched by its longest repeated run of words (2+ words, or one word of 4+ letters)."""
    words = [w for w in re.findall(r"[A-Za-z']+", str(target or ""))]
    if not words:
        return None

    def part(w):
        stem = w[:-1] if len(w) > 4 and w[-1].lower() == "e" else w
        if len(stem) >= 4 and stem[-1].lower() == "y":
            stem = stem[:-1]
        return re.escape(stem) + r"[A-Za-z']*"
    n = len(words)
    for size in range(n, 0, -1):
        for a in range(0, n - size + 1):
            run = words[a:a + size]
            if size == 1 and (n > 1 and len(run[0]) < 4 or len(run[0]) < 2):
                continue
            m = re.search(r"\b" + r"\s+".join(part(w) for w in run), text, re.I)
            if m:
                return m.start(), m.end()
        if size <= max(1, n // 2) and n > 2:
            break  # less than half of a long phrase: better no highlight than a random word
    return None


class Rich:
    """An English sentence wrapped on up to max_lines lines; the *marked* part (or `target`) is coloured and gets
    underline segments. .img = all lines centred; .segs = [(x0, x1, y)] underline segments in .img coordinates."""

    def __init__(self, raw, size, col, hl, max_w=WIDE - 40, weight="Bold", target=None, max_lines=2, shadow=False):
        text, spans = _strip_marks(raw)
        if not spans and target:
            sp = auto_span(text, target)
            spans = [sp] if sp else []
        self.rtl = is_rtl(text)
        while True:
            lines = self._wrap(text, size, weight, max_w)
            if len(lines) <= max_lines or size <= 30:
                break
            size = int(size * 0.92)
        while size > 14 and max(text_width(text[a:b], size, weight) for a, b in lines) > max_w:
            size = int(size * 0.94)  # one very long word
            lines = self._wrap(text, size, weight, max_w)
        lines = balanced(lambda w: self._wrap(text, size, weight, w), max_w)
        self.size = size
        f = get_font(size, weight)
        asc = f.getmetrics()[0]
        pitch = int(size * 1.36)
        rows = []
        for ls, le in lines:
            line = text[ls:le]
            base = text_img(line, size, col, weight, shadow=shadow).copy()
            ranges = [(max(a, ls) - ls, min(b, le) - ls) for a, b in spans if a < le and b > ls]
            segs = []
            if ranges and not self.rtl:
                l0, t0 = f.getbbox(line)[:2]
                hi = text_img(line, size, hl, weight, shadow=shadow)
                m = Image.new("L", base.size, 0)
                md = ImageDraw.Draw(m)
                for a, b in ranges:
                    x0 = 30 - l0 + f.getlength(line[:a])
                    x1 = 30 - l0 + f.getlength(line[:b])
                    md.rectangle([x0 - 1, 0, x1 + 1, base.height], fill=255)
                    seg = line[a:b].rstrip(" .,!?;:\"')»")
                    seg_l = len(seg) - len(seg.lstrip(" \"'(«"))
                    ux0 = 30 - l0 + f.getlength(line[:a + seg_l])
                    ux1 = 30 - l0 + f.getlength(line[:a + len(seg)])
                    base_y = 30 - t0 + asc
                    if ux1 > ux0 + 4:
                        segs.append((ux0, ux1, base_y + max(5, size * 0.17)))
                base.paste(hi, (0, 0), ImageChops.multiply(hi.getchannel("A"), m))
            rows.append((base, segs))
        w = max(b.width for b, _ in rows)
        hmax = max(b.height for b, _ in rows)
        self.img = Image.new("RGBA", (w, pitch * (len(rows) - 1) + hmax), (0, 0, 0, 0))
        self.segs = []
        for k, (b, segs) in enumerate(rows):
            x, y = (w - b.width) // 2, k * pitch + (hmax - b.height) // 2
            self.img.alpha_composite(b, (x, y))
            self.segs += [(x + a, x + c, y + yy) for a, c, yy in segs]

    @staticmethod
    def _wrap(text, size, weight, max_w):
        """Greedy wrap -> list of (start, end) character ranges of `text` (single spaces)."""
        words = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        if not words:
            return [(0, 0)]
        lines, ls, le = [], words[0][0], words[0][1]
        for ws, we in words[1:]:
            if text_width(text[ls:we], size, weight) > max_w:
                lines.append((ls, le))
                ls = ws
            le = we
        lines.append((ls, le))
        return lines

    def underline(self, frame, cx, cy, p, col, alpha):
        """Draw the underline segments, sweeping left to right as p goes 0 -> 1."""
        if p <= 0 or alpha <= 0.02 or not self.segs:
            return
        total = sum(b - a for a, b, _ in self.segs)
        left = total * min(1.0, p)
        d = ImageDraw.Draw(frame)
        x0, y0 = cx - self.img.width / 2, cy - self.img.height / 2
        th = max(4, int(self.size * 0.11))
        for a, b, y in self.segs:
            if left <= 0:
                break
            w = min(b - a, left)
            left -= w
            d.rounded_rectangle([x0 + a, y0 + y - th / 2, x0 + a + w, y0 + y + th / 2], th / 2,
                                fill=tuple(col) + (int(255 * alpha),))


class WordLine:
    """One line of a phrase that appears word by word (crops of one rendered line, so the baseline stays exact)."""

    def __init__(self, line, size, col, weight="Black"):
        self.img = text_img(line, size, col, weight, shadow=True)
        f = get_font(size, weight)
        l0 = f.getbbox(line)[0]
        self.boxes = []
        for m in re.finditer(r"\S+", line):
            x0 = 30 - l0 + f.getlength(line[:m.start()]) - 6
            x1 = 30 - l0 + f.getlength(line[:m.end()]) + 6
            self.boxes.append((max(0, int(x0)), min(self.img.width, int(math.ceil(x1)))))
        if self.boxes:  # the first / last crop also take the padding (and the shadow)
            self.boxes[0] = (0, self.boxes[0][1])
            self.boxes[-1] = (self.boxes[-1][0], self.img.width)
        self.crops = [self.img.crop((a, 0, b, self.img.height)) for a, b in self.boxes]


def timer_slot(kind):
    """(height to keep free for a timer design, offset of its centre inside that space). The bar designs draw
    their number above the bar, the round ones around their centre."""
    if kind in ("Bar", "Segments"):
        return 120, 32
    if kind == "Fuse":
        return 140, 10
    return FOOTPRINT.get(kind, (140, 140))[1] + 40, 0


def _short(txt):
    """First part of a meaning for the recap: 'صامد • يتعافى بسرعة' -> 'صامد'."""
    t = re.split(r"\s[•|/]\s|\s[-–—]\s|[(،,]", str(txt or ""))[0].strip()
    return t or str(txt or "").strip()


# ------------------------------------------------------------------ the video
class VocabVideo:
    def __init__(self, project):
        s = project.get("settings", {})
        v = project.get("vocab", {})
        e = project.get("ending", {})
        self.lang = s.get("language", "ar")
        self.L = S(self.lang)
        self.fps = int(s.get("fps", 30))
        self.items = parse_items(v.get("items", ""))
        n = sum(len(it["words"]) if it["type"] == "list" else 1 for it in self.items)  # {count}: every listed word
        g = v.get("group") if v.get("group") in GROUP_KEYS else "general"
        self.group = g
        name = " ".join(str(v.get("group_name") or "").split())
        if g == "custom":
            gd = dict(label=name or "My words", badge=(name or "My words").upper(),
                      color=custom_color(name), theme=s.get("theme") or "Royal Blue", news=False,
                      title=("{count} English Words", "كلمات إنجليزية يجب أن تعرفها!", "Words you need to know!"))
        else:
            gd = dict(GROUPS[g])
            if name:  # rename the badge of a built-in group
                gd["badge"] = name
        acc = str(v.get("accent") or "group").strip()
        self.accent = to_rgb(gd["color"]) if acc.lower() in ("", "group") else to_rgb(acc)
        self.news = bool(gd["news"])
        for it in self.items:  # an item may belong to another group (mixed videos): its own badge and colour
            gk = group_key(it["group"]) if it["group"] else None
            if not it["group"] or gk == g:
                it["acc"], it["badge"], it["news"] = self.accent, gd["badge"], self.news
                it["label"] = name if g == "custom" else gd["label"].title()
                it["gsub"] = gd["title"][1]
            elif gk:
                it["acc"], it["badge"], it["news"] = to_rgb(GROUPS[gk]["color"]), GROUPS[gk]["badge"], GROUPS[gk]["news"]
                it["label"], it["gsub"] = GROUPS[gk]["label"].title(), GROUPS[gk]["title"][1]
            else:
                name_i = " ".join(it["group"].split())
                it["acc"], it["badge"], it["news"] = custom_color(name_i), name_i.upper(), False
                it["label"], it["gsub"] = name_i, "كلمات إنجليزية يجب أن تعرفها!"
            it["label"] = it["label"] or "English Words"
        theme_name = gd["theme"] if (v.get("background") or "group") == "group" else s.get("theme")
        self.theme = get_theme(theme_name)
        self.bg = make_bg(self.theme)
        self.stars = Stars(seed=11) if self.theme["stars"] else None
        self.card_fill = tuple(self.theme["card"])
        self.badge_txt = gd["badge"]
        self.P = PACE_K.get(v.get("pace") or "normal", 1.0)
        self.guess_secs = max(2, min(15, int(round(float(v.get("guess_seconds") or 5)))))
        self.timer = v.get("timer") if v.get("timer") in TIMER_NAMES else "Bar"
        valid_fx = {k for _, k in TIMER_FX}
        self.timer_fx = [k for k in (v.get("timer_fx") or []) if k in valid_fx]
        self.recap_on = bool(v.get("recap", True))
        ls = str(v.get("list_style") or "Editorial")
        self.list_style = ls if ls in LIST_STYLES else "Editorial"
        self.list_opts = dict(highlight=v.get("list_highlight") or "cream", board=v.get("chalk_board") or "green",
                              mark=v.get("chalk_mark") or "circle", color=v.get("chalk_color") or "pink")
        self.audio_gain = float(v.get("audio_gain") if v.get("audio_gain") is not None else 1.0)
        clips, _ = match_clips(v.get("audio") or [], self.items)

        # opening title
        def fill(txt):
            num = str(v.get("lesson_n") if v.get("lesson_n") not in (None, "") else "")
            num = num[:-2] if num.endswith(".0") else num
            return str(txt or "").replace("{count}", str(n)).replace("{n}", num)
        all_guess = all(it["type"] in ("guess", "reverse") for it in self.items)
        auto = QUIZ_TITLES.get(g if g in QUIZ_TITLES else None) if all_guess else gd["title"]
        title = fill(v.get("title") or auto[0])
        sub = fill(v.get("subtitle") or (auto[1] if self.lang == "ar" else auto[2]))
        self.lesson = fill(v.get("lesson") or "")
        self.title_style = v.get("title_style") if v.get("title_style") in TITLE_STYLES else "Fancy"
        first = self.items[0]
        self.hook_word = first["words"][0]["en"] if first["type"] == "list" else first["word"]
        self.hook = bool(v.get("hook")) and bool(self.hook_word)
        self._intro_assets(title, sub)

        # items
        t = INTRO
        self.starts = []
        self.silences = []
        self.voices = []
        for i, it in enumerate(self.items):
            it["i"] = i
            it["clip_w"] = clips.get((i, "w"))
            it["clip_e"] = clips.get((i, "e"))
            for k in range(1, len(it["words"]) + 1):
                it[f"clip_l{k}"] = clips.get((i, f"l{k}"))
            it["lesson"] = self.lesson
            getattr(self, "_build_" + ("guess" if it["type"] == "reverse" else
                                       "phrase" if it["type"] in ("proverb", "idiom") else it["type"]))(it)
            it["t0"] = t
            self.starts.append(t)
            for off, path in it["voice"]:
                self.voices.append((t + off, path))
            if it.get("reveal") is not None:
                self.silences.append((t + it["reveal"] - 0.5, t + it["reveal"]))
            t += it["D"]
        self.R0 = t
        rows = self._recap_rows() if self.recap_on else []
        self.recap_on = 0 < len(rows) <= RECAP_MAX  # a longer recap would not fit on one screen
        if self.recap_on:
            self._build_recap(rows)
            t += self.recap_len
        self.E = t
        self.base_duration = self.dur = self.E + 4.0
        self.cover_time = 1.6
        self.ending = (fill(e.get("intro", "")), parse_lines(fill(e.get("question", "")), ["white", "gold"]),
                       fill(e.get("cta", "")), s.get("handle", ""))

    # ============================================================ assets: intro + header
    def _intro_assets(self, title, sub):
        acc = self.accent
        self.badge_img = pill(self.badge_txt, 44 if self.title_style == "Simple" else 36, INK, acc, padx=40)
        self.small_badge = pill(self.badge_txt, 30, INK, acc, padx=26)
        lines = fit_lines(title, 110, "Black", 960, 2, 60)
        self.t_lines = lines
        self.lesson_img = text_img(self.lesson, 44, GREY, "Bold", shadow=False, max_w=WIDE) if self.lesson else None
        self.ghost = None
        if self.hook:
            self.ghost = text_img(self.hook_word, 260, acc, "Black", shadow=False, max_w=1000)
        if self.title_style == "Fancy":
            sz = lines[1]
            tl = [(txt, sz, WHITE, 760 + k * int(sz * 1.28)) for k, txt in enumerate(lines[0])]
            self.title_fx = VocabTitle(tl, sub, acc, WHITE, acc, t_in=0.1, t_out=INTRO - 0.35)
            self.title_fx.t_badge_y = self.title_fx.badge_y - 175
            self.sub_img = None
        else:
            self.title_fx = None
            self.title_img = lines_img(lines[0], lines[1], WHITE, "Black", shadow=True, pitch=int(lines[1] * 1.2))
            sl, ss = fit_lines(sub, 62, "Black", 960, 2, 40) if sub else ([], 0)
            self.sub_img = lines_img(sl, ss, acc, "Black", shadow=True) if sl else None

    def _header_imgs(self, it):
        n = len(self.items)
        i = it["i"]
        typ = it["type"]
        if typ == "word":
            txt = f"Word {i + 1} of {n}"
        elif typ == "proverb":
            txt = f"Proverb {i + 1} of {n}"
        elif typ == "idiom":
            txt = f"Idiom {i + 1} of {n}"
        elif typ == "mistake":
            txt = "Don't say it like this!"
        elif typ == "reverse":
            txt = "Say it in English"
        elif self.group == "proverbs":
            txt = "Guess the Arabic proverb"
        elif self.group == "mistakes":
            txt = "Which one is correct?"
        else:
            txt = "Guess the meaning"
        it["head"] = pill(txt, 40, WHITE, shade(it["acc"], 0.36))
        it["badge_img"] = pill(it["badge"], 30, INK, it["acc"], padx=26)

    # ============================================================ layout helpers
    def _stack(self, it, blocks, top=TOP, bottom=BOTTOM, gap_scale=1.0):
        """blocks = [(height, gap_after, payload)] -> payload['y'] = centre y; centred in [top, bottom].
        Returns the total height."""
        total = sum(h for h, _, _ in blocks) + sum(g for _, g, _ in blocks[:-1]) * gap_scale
        y = top + max(0.0, (bottom - top - total) / 2)
        for h, g, p in blocks:
            p["y"] = y + h / 2
            y += h + g * gap_scale
        return total

    @staticmethod
    def el(img, t, anim="rise", x=540, **kw):
        d = dict(img=img, t=t, anim=anim, x=x)
        d.update(kw)
        return d

    def _ipa_block(self, ipa, size, t, it):
        """Speaker + IPA row as one element (the speaker waves animate while the word's clip plays)."""
        im = ipa_img(ipa, size, CYAN)
        spk = speaker_imgs(CYAN)
        w = 100 + im.width - 40
        h = max(90, im.height)
        return dict(kind="ipa", img=im, spk=spk, w=w, h=h, t=t, anim="fade")

    def _voice(self, it, slot, at):
        """Schedule the item's clip at `at` (item time). Returns when the clip ends (or `at` if there is none)."""
        path = it["clip_" + slot]
        if not path:
            return at
        try:
            length = audio_length(path)
        except Exception:
            return at
        it["voice"].append((at, path))
        if slot == "w":
            it["speak"] = (at, at + length)
        return at + length

    # ============================================================ word card
    def _build_word(self, it):
        self._header_imgs(it)
        it["voice"], it["els"], it["fx"] = [], [], []
        P, acc, cf = self.P, it["acc"], self.card_fill
        news = it["news"] and bool(it["example"])
        for scale in SCALES:
            blocks = []
            pos = pill(it["pos"], int(36 * scale), INK, acc) if it["pos"] else None
            if pos:
                blocks.append((pos.height, 26 * scale, dict(img=pos, key="pos")))
            wl, ws = fit_lines(it["word"], int(150 * scale), "Black", WIDE - 60, 2, 56)
            wimg = lines_img(wl, ws, WHITE, "Black", shadow=True, pitch=int(ws * 1.12))
            blocks.append((wimg.height - 50, 4 * scale, dict(img=wimg, key="word")))
            if it["ipa"]:
                ib = self._ipa_block(it["ipa"], int(54 * scale), 0, it)
                blocks.append((ib["h"], 24 * scale, dict(ipa=ib, key="ipa")))
            blocks.append((4, 34 * scale, dict(key="div")))
            ml, msz = fit_lines(it["meaning"], int(70 * scale), "Black", WIDE - 80, 2, 40)
            mimg = lines_img(ml, msz, acc, "Black", shadow=True)
            blocks.append((mimg.height - 50, 40 * scale, dict(img=mimg, key="mean")))
            if it["example"]:
                label = text_img("In the news" if news else "Example", int(36 * scale), GREY, "Bold", shadow=False)
                blocks.append((label.height - 56, 16 * scale, dict(img=label, key="exlabel")))
                if news:
                    nimg, rich, rich_xy = self._news(it, scale)
                    blocks.append((nimg.height, 30 * scale, dict(img=nimg, key="news", rich=rich, rich_xy=rich_xy)))
                else:
                    rich = Rich(it["example"], int(56 * scale), WHITE, acc, target=it["word"], max_lines=3)
                    blocks.append((rich.img.height - 50, 12 * scale, dict(img=rich.img, key="ex", rich=rich)))
                    if it["example_ar"]:
                        al, asz = fit_lines(it["example_ar"], int(46 * scale), "SemiBold", WIDE - 40, 2, 30)
                        aimg = lines_img(al, asz, GREY, "SemiBold")
                        blocks.append((aimg.height - 50, 30 * scale, dict(img=aimg, key="exar")))
            if it["also"]:
                lab = text_img("Similar words", int(34 * scale), GREY, "Bold", shadow=False)
                chips = [pill(w, int(38 * scale), WHITE, shade(acc, 0.42), padx=28, weight="Bold") for w in it["also"]]
                while sum(c.width for c in chips) + 20 * (len(chips) - 1) > WIDE - 60 and len(chips) > 1:
                    chips.pop()
                blocks.append((lab.height - 56, 14 * scale, dict(img=lab, key="alsolabel")))
                blocks.append((chips[0].height, 0, dict(chips=chips, key="chips")))
            pad = 54 * scale
            total = self._stack(it, blocks, TOP + pad, BOTTOM - pad)
            if total <= BOTTOM - TOP - 2 * pad + 1:
                break
        top = blocks[0][2]["y"] - blocks[0][0] / 2 - pad
        bot = blocks[-1][2]["y"] + blocks[-1][0] / 2 + pad
        # timing
        tw = 0.5
        t_ipa = 1.0
        end_w = self._voice(it, "w", 1.1) if it["clip_w"] else 0
        t_mean = max(1.0 + 1.5 * P, end_w + 0.35)
        t = t_mean
        t_ex = t_exar = t_also = None
        if it["example"]:
            t_ex = t + 1.0 * P
            end_e = self._voice(it, "e", t_ex + 0.35) if it["clip_e"] else t_ex
            t_exar = t_ex + 1.0 * P
            t = max(t_exar + (0.9 if news else 0.6) * P, end_e + 0.3)
        if it["also"]:
            t_also = t + 0.4 * P
            t = t_also + 0.25 * len(it["also"])
        it["D"] = t + (1.6 + 0.3 * bool(it["example"])) * P + EXIT
        it["reveal"] = None
        cw, ch = 960, int(bot - top)
        els = it["els"]
        els.append(self.el(card(cw, ch, acc, cf), 0.05, "card", y=(top + bot) / 2))
        for h, g, p in blocks:
            k = p["key"]
            if k == "pos":
                els.append(self.el(p["img"], 0.3, "pop", y=p["y"]))
            elif k == "word":
                els.append(self.el(p["img"], tw, "slam", y=p["y"]))
            elif k == "ipa":
                ib = p["ipa"]
                ib["t"], ib["y"] = t_ipa, p["y"]
                els.append(ib)
            elif k == "div":
                els.append(dict(kind="div", t=t_mean - 0.2, y=p["y"], w=720, col=(90, 110, 160)))
            elif k == "mean":
                els.append(self.el(p["img"], t_mean, "pop", y=p["y"]))
            elif k == "exlabel":
                els.append(self.el(p["img"], t_ex, "fade", y=p["y"]))
            elif k == "ex":
                els.append(self.el(p["img"], t_ex, "rise", y=p["y"], rich=p["rich"], ul=t_ex + 0.4, ulcol=acc))
            elif k == "news":
                els.append(self.el(p["img"], t_ex, "news", y=p["y"], rich=p["rich"], rich_xy=p["rich_xy"],
                                   ul=t_ex + 0.55, ulcol=NEWS_RED))
            elif k == "exar":
                els.append(self.el(p["img"], t_exar, "fade", y=p["y"]))
            elif k == "alsolabel":
                els.append(self.el(p["img"], t_also, "fade", y=p["y"]))
            elif k == "chips":
                chips = p["chips"]
                x = 540 - (sum(c.width for c in chips) + 20 * (len(chips) - 1)) / 2
                for j, c in enumerate(chips):
                    els.append(self.el(c, t_also + 0.15 + 0.25 * j, "pop", x=x + c.width / 2, y=p["y"]))
                    x += c.width + 20
        it["snd"] = [("pop", 0.3, 0.22), ("pop", tw - 0.05, 0.4), ("ding", t_mean, 0.3)]
        if t_ex is not None:
            it["snd"].append(("news", t_ex - 0.05, 0.42) if news else ("swish", t_ex - 0.1, 0.2))
        if t_also is not None:
            it["snd"] += [("pop", t_also + 0.15 + 0.25 * j, 0.2) for j in range(len(it["also"]))]

    def _news(self, it, scale):
        """BREAKING NEWS headline card for the example (Political words). Returns (image, rich, rich centre)."""
        w = 800
        rich = Rich(it["example"], int(54 * scale), NEWS_INK, NEWS_RED, max_w=w - 70, weight="Black",
                    target=it["word"], max_lines=3)
        al = []
        asz = int(34 * scale)
        if it["example_ar"]:
            al, asz = fit_lines(it["example_ar"], asz, "Bold", w - 60, 2, 24)
        top_h, tick_pitch = int(64 * scale), int(asz * 1.4)
        tick_h = (len(al) * tick_pitch + int(22 * scale)) if al else 0
        body_h = rich.img.height - 60 + int(56 * scale)
        h = top_h + body_h + tick_h
        s = 2
        im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = 22 * s
        d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], r, fill=(245, 247, 252, 255))
        d.rounded_rectangle([0, 0, w * s - 1, top_h * s + r], r, fill=NEWS_RED + (255,))
        d.rectangle([0, top_h * s, w * s - 1, top_h * s + r + 2], fill=(245, 247, 252, 255))
        if tick_h:
            y0 = (h - tick_h) * s
            d.rounded_rectangle([0, y0 - r, w * s - 1, h * s - 1], r, fill=NEWS_NAVY + (255,))
            d.rectangle([0, y0 - r - 2, w * s - 1, y0], fill=(245, 247, 252, 255))
        im = im.resize((w, h), Image.LANCZOS)
        tag = text_img("BREAKING NEWS", int(32 * scale), WHITE, "Black", shadow=False)
        im.alpha_composite(tag, (26 - 30, top_h // 2 - tag.height // 2))
        live = pill("LIVE", int(24 * scale), NEWS_RED, WHITE, padx=16)
        im.alpha_composite(live, (w - live.width - 22, top_h // 2 - live.height // 2))
        if al:
            ar = lines_img(al, asz, WHITE, "Bold", pitch=tick_pitch)
            im.alpha_composite(ar, (w // 2 - ar.width // 2, h - tick_h // 2 - ar.height // 2))
        rich_xy = (w // 2, top_h + body_h // 2)
        im.alpha_composite(rich.img, (rich_xy[0] - rich.img.width // 2, rich_xy[1] - rich.img.height // 2))
        return im, rich, rich_xy

    # ============================================================ word list (one page, words read in turn)
    def _build_list(self, it):
        from ..word_list import ListPage
        it["voice"], it["els"], it["fx"] = [], [], []
        P, n = self.P, len(it["words"])
        rows = [0.55 + 0.16 * j for j in range(n)]  # when each row appears
        t = rows[-1] + 0.6 + 0.25 * P
        starts, ends, speak = [], [], []
        for k in range(1, n + 1):
            path, length = it.get(f"clip_l{k}"), 0.0
            if path:
                try:
                    length = audio_length(path)
                    it["voice"].append((t, path))
                except Exception:
                    length = 0.0
            hold = max(0.6, length) if length else 1.4 * P  # no clip: the word stays lit for a moment
            starts.append(t)
            ends.append(t + hold)
            speak.append((t, t + length) if length else None)
            t += hold + 0.45 * P
        it["D"] = ends[-1] + 1.6 * P + EXIT
        it["reveal"] = None
        it["snd"] = [("tap", r, 0.14) for r in rows] + [("click", s - 0.08, 0.16) for s in starts]
        title = it["title"] or it["label"]
        sub = it["subtitle"] or it["gsub"].replace("{count}", str(n))
        it["page"] = ListPage(self.list_style, self.list_opts, it["words"], title, sub, it["lesson"],
                              rows, starts, ends, speak, it["D"], EXIT)

    # ============================================================ guess / reverse
    def _build_guess(self, it):
        self._header_imgs(it)
        it["voice"], it["els"], it["fx"] = [], [], []
        P = self.P
        if it["question"]:
            prompt = it["question"]
        elif it["type"] == "reverse":
            prompt = "How do you say it in English?"
        elif self.group == "proverbs":
            prompt = self.L["vw_proverb_q"]
        elif self.group == "mistakes" and not it["word"]:
            prompt = "Which sentence is correct?"
        else:
            prompt = "What does it mean?"
        opts = it["options"]
        n = len(opts)
        slot, self.timer_dy = timer_slot(self.timer)
        for scale in SCALES:
            blocks = []
            pl, psz = fit_lines(prompt, int(54 * scale), "Bold", WIDE, 2, 30)
            pimg = lines_img(pl, psz, GREY, "Bold", shadow=True)
            blocks.append((pimg.height - 50, 18 * scale, dict(img=pimg, key="prompt")))
            if it["word"]:
                big = int(124 * scale)
                if text_width(it["word"], big, "Black") > 960:
                    wl, ws = fit_lines(it["word"], int(84 * scale), "Black", 960, 2, 62)
                    if len(wl) > 2:
                        wl, ws = fit_lines(it["word"], int(84 * scale), "Black", 960, 3, 40)
                else:
                    wl, ws = [it["word"]], big
                wimg = lines_img(wl, ws, WHITE, "Black", shadow=True, pitch=int(ws * 1.15))
                blocks.append((wimg.height - 50, 6 * scale, dict(img=wimg, key="word")))
            if it["ipa"]:
                ib = self._ipa_block(it["ipa"], int(50 * scale), 0, it)
                blocks.append((ib["h"], 10 * scale, dict(ipa=ib, key="ipa")))
            blocks[-1] = (blocks[-1][0], 44 * scale, blocks[-1][2])
            oimgs = [self._option(k, o, k == it["correct"], scale) for k, o in enumerate(opts)]
            for k, (plain, ok_img, h_opt, mark_x) in enumerate(oimgs):
                blocks.append((h_opt, (24 if k < n - 1 else 40) * scale,
                               dict(key="opt", k=k, img=plain, ok=ok_img, mark_x=mark_x)))
            blocks.append((slot, 0, dict(key="timer")))
            total = self._stack(it, blocks)
            if total <= BOTTOM - TOP + 1:
                break
        # timing
        end_w = self._voice(it, "w", 1.1) if it["clip_w"] else 0
        t_opts = max(1.6 if it["word"] else 1.0, end_w + 0.3)
        t_count = t_opts + 0.15 * n + 0.45
        R = t_count + self.guess_secs
        it["reveal"], it["count"] = R, t_count
        t = R + 0.9
        t_ex = None
        timer_y = blocks[-1][2]["y"] + self.timer_dy
        if it["example"]:
            t_ex = R + 0.8
            end_e = self._voice(it, "e", t_ex + 0.4) if it["clip_e"] else t_ex
            t = max(t_ex + (2.0 + 0.5 * bool(it["example_ar"])) * P, end_e + 0.7)
        else:
            t = R + 2.0 * P
        it["D"] = t + EXIT
        els = it["els"]
        for h, g, p in blocks:
            k = p["key"]
            if k == "prompt":
                els.append(self.el(p["img"], 0.2, "rise", y=p["y"]))
            elif k == "word":
                els.append(self.el(p["img"], 0.4, "slam", y=p["y"]))
            elif k == "ipa":
                ib = p["ipa"]
                ib["t"], ib["y"] = 1.0, p["y"]
                els.append(ib)
            elif k == "opt":
                j = p["k"]
                els.append(self.el(p["img"], t_opts + 0.15 * j, "slide", y=p["y"], opt=dict(
                    ok=p["ok"], correct=j == it["correct"], R=R, mark_x=p["mark_x"])))
        it["timer_y"] = timer_y
        if t_ex is not None:
            right = it["options"][it["correct"]]
            rich = Rich(it["example"], 50, WHITE, GREEN,
                        target=right if (it["type"] == "reverse" or not it["word"]) else it["word"])
            ar = None
            if it["example_ar"]:
                al, asz = fit_lines(it["example_ar"], 40, "SemiBold", WIDE - 40, 2, 28)
                ar = lines_img(al, asz, GREY, "SemiBold")
            rh = rich.img.height - 60
            ah = (ar.height - 60) if ar is not None else 0
            hh = rh + (14 + ah if ar is not None else 0)
            opt_bottom = blocks[-2][2]["y"] + blocks[-2][0] / 2
            y0 = max(opt_bottom + 34, min(timer_y - hh / 2, BOTTOM + 40 - hh))
            els.append(self.el(rich.img, t_ex, "rise", y=y0 + rh / 2, rich=rich, ul=t_ex + 0.4, ulcol=GREEN))
            if ar is not None:
                els.append(self.el(ar, t_ex + 0.9 * P, "fade", y=y0 + rh + 14 + ah / 2))
        it["snd"] = [("pop", 0.4, 0.4)] + [("click", t_opts + 0.15 * j + 0.02, 0.24) for j in range(n)]

    def _option(self, k, txt, correct, scale):
        """(plain card, revealed card, height, x of the ✔) for one option. Arabic options: letter on the right."""
        rtl = is_rtl(txt)
        letters = "أبجد" if rtl else "ABCD"
        size = int(50 * scale)
        lines, size = fit_lines(txt, size, "Bold", 600, 2, 30)
        timg = lines_img(lines, size, WHITE, "Bold")
        w, h = 860, max(int(112 * scale), timg.height - 60 + int(48 * scale))
        imgs = []
        for ok in (False, True):
            base = card(w, h, GREEN if ok else DIM, self.card_fill, alpha=250 if ok else 228, r=38,
                        width=5 if ok else 3, glow=GREEN if ok else None).copy()
            d = ImageDraw.Draw(base)
            cx = 40 + (w - 62 if rtl else 62)
            cy = 40 + h // 2
            d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=(GREEN if ok else (58, 70, 108)) + (255,))
            let = text_img(letters[k], 38, INK if ok else WHITE, "Black", shadow=False)
            base.alpha_composite(let, (int(cx - let.width / 2), int(cy - let.height / 2 - 3)))
            if rtl:
                base.alpha_composite(timg, (40 + w - 120 - timg.width + 30, cy - timg.height // 2))
            else:
                base.alpha_composite(timg, (40 + 120 - 30, cy - timg.height // 2))
            imgs.append(base)
        mark_x = 540 - w / 2 + 62 if rtl else 540 + w / 2 - 62
        return imgs[0], imgs[1], h, mark_x

    # ============================================================ common mistake
    def _build_mistake(self, it):
        self._header_imgs(it)
        it["voice"], it["els"], it["fx"] = [], [], []
        P, cf = self.P, self.card_fill
        title = it["question"] or self.L["vw_mistake"]
        for scale in SCALES:
            blocks = []
            tl, tsz = fit_lines(title, int(64 * scale), "Black", WIDE, 2, 34)
            timg = lines_img(tl, tsz, WHITE, "Black", shadow=True)
            blocks.append((timg.height - 50, 44 * scale, dict(img=timg, key="title")))
            # both sentences share one size, on one line when they fit (so the two cards look alike)
            one = int(96 * scale)
            while one > 64 * scale and max(text_width(x, one, "Black") for x in (it["wrong"], it["word"])) > 700:
                one = int(one * 0.95)
            fits = max(text_width(x, one, "Black") for x in (it["wrong"], it["word"])) <= 700
            for key, txt, col, tone in (("wrong", it["wrong"], RED, (255, 150, 150)),
                                        ("right", it["word"], GREEN, (160, 255, 200))):
                if fits:
                    sl, ssz = [" ".join(txt.split())], one
                else:
                    sl, ssz = fit_lines(txt, int(80 * scale), "Black", 700, 2, 36)
                simg = lines_img(sl, ssz, tone, "Black", shadow=True, pitch=int(ssz * 1.18))
                lab = baseline_img(self.L["vw_wrong" if key == "wrong" else "vw_right"], int(38 * scale), col)
                pad = 46 * scale
                lab_sz = int(38 * scale)  # ink height of the label ≈ 1.1 × its size
                ch = int((simg.height - 60) + 30 * scale + 1.1 * lab_sz + 2 * pad)
                blocks.append((ch, (40 if key == "wrong" else 50) * scale,
                               dict(key=key, img=simg, lab=lab, col=col, lines=sl, size=ssz, pad=pad, scale=scale)))
            if it["meaning"]:
                rl, rsz = fit_lines(it["meaning"], int(52 * scale), "Bold", WIDE, 2, 30)
                rimg = lines_img(rl, rsz, (245, 197, 66), "Bold", shadow=True)
                blocks.append((rimg.height - 50, 34 * scale, dict(img=rimg, key="rule")))
            if it["example"]:
                rich = Rich(it["example"], int(54 * scale), WHITE, GREEN, target=it["word"])
                blocks.append((rich.img.height - 50, 12 * scale, dict(img=rich.img, key="ex", rich=rich)))
                if it["example_ar"]:
                    al, asz = fit_lines(it["example_ar"], int(42 * scale), "SemiBold", WIDE - 40, 2, 28)
                    blocks.append((lines_img(al, asz, GREY, "SemiBold").height - 50, 0,
                                   dict(img=lines_img(al, asz, GREY, "SemiBold"), key="exar")))
            blocks[-1] = (blocks[-1][0], 0, blocks[-1][2])
            total = self._stack(it, blocks)
            if total <= BOTTOM - TOP + 1:
                break
        t_wrong = 0.8
        t_strike = t_wrong + 1.0 * P
        t_right = t_strike + 1.2 * P
        end_w = self._voice(it, "w", t_right + 0.55) if it["clip_w"] else t_right + 0.6
        t = max(t_right + 1.5 * P, end_w + 0.3)
        t_rule = t_ex = None
        if it["meaning"]:
            t_rule = t
            t += 1.1 * P
        if it["example"]:
            t_ex = t
            end_e = self._voice(it, "e", t_ex + 0.35) if it["clip_e"] else t_ex
            t = max(t_ex + (1.0 + 0.7 * bool(it["example_ar"])) * P, end_e + 0.3)
        it["D"] = t + 1.9 * P + EXIT
        it["reveal"] = None
        els = it["els"]
        for h, g, p in blocks:
            k = p["key"]
            if k == "title":
                els.append(self.el(p["img"], 0.3, "pop", y=p["y"]))
            elif k in ("wrong", "right"):
                ts = t_wrong if k == "wrong" else t_right
                col = p["col"]
                cimg = card(900, int(h), col, cf, glow=GREEN if k == "right" else None)
                side = -1 if k == "wrong" else 1
                lab, simg = p["lab"], p["img"]
                text_cx = 540 + 50
                top = p["y"] - h / 2 + p["pad"]
                txt_y = top + (simg.height - 60) / 2
                lab_sz = int(38 * p["scale"])
                lab_y = top + (simg.height - 60) + 30 * p["scale"] + 0.55 * lab_sz - 0.15 * lab_sz
                els.append(self.el(cimg, ts, "slide_in", y=p["y"], side=side,
                                   shake=(t_strike, t_strike + 0.45) if k == "wrong" else None))
                els.append(self.el(simg, ts, "slide_in", x=text_cx, y=txt_y, side=side,
                                   shake=(t_strike, t_strike + 0.45) if k == "wrong" else None,
                                   bump=(t_right + 0.4, t_right + 0.8) if k == "right" else None))
                els.append(self.el(lab, (t_strike + 0.15) if k == "wrong" else (t_right + 0.5), "fade", x=text_cx,
                                   y=lab_y))
                els.append(self.el(mark(k == "right"), t_strike if k == "wrong" else t_right + 0.4, "pop",
                                   x=540 - 450 + 70, y=p["y"],
                                   shake=(t_strike, t_strike + 0.45) if k == "wrong" else None))
                if k == "wrong":
                    nl = len(p["lines"])
                    pitch = int(p["size"] * 1.18)
                    for li, line in enumerate(p["lines"]):
                        lw = text_width(line, p["size"], "Black")
                        ly = txt_y + (li - (nl - 1) / 2) * pitch
                        it["fx"].append(dict(kind="strike", t=t_strike + 0.12 * li, x0=text_cx - lw / 2 - 14,
                                             x1=text_cx + lw / 2 + 14, y=ly + 4, col=RED,
                                             shake=(t_strike, t_strike + 0.45)))
            elif k == "rule":
                els.append(self.el(p["img"], t_rule, "pop", y=p["y"]))
            elif k == "ex":
                els.append(self.el(p["img"], t_ex, "rise", y=p["y"], rich=p["rich"], ul=t_ex + 0.4, ulcol=GREEN))
            elif k == "exar":
                els.append(self.el(p["img"], t_ex + 0.7 * P, "fade", y=p["y"]))
        it["snd"] = [("pop", 0.3, 0.3), ("thump", t_wrong, 0.6), ("buzz", t_strike, 0.45),
                     ("swish", t_right - 0.12, 0.35), ("ding", t_right + 0.4, 0.45)]
        if t_rule is not None:
            it["snd"].append(("pop", t_rule, 0.3))
        if t_ex is not None:
            it["snd"].append(("swish", t_ex - 0.1, 0.18))

    # ============================================================ proverb / idiom
    def _build_phrase(self, it):
        self._header_imgs(it)
        it["voice"], it["els"], it["fx"] = [], [], []
        P, acc, cf = self.P, it["acc"], self.card_fill
        idiom = it["type"] == "idiom"
        if it["equivalent"]:
            big_label, big_txt, small_txt = self.L["vw_equiv"], it["equivalent"], it["meaning"]
            big_col = (245, 197, 66)
        else:
            big_label = self.L["vw_real"]
            big_txt = it["meaning"]
            small_txt = it["note"]
            big_col = WHITE
        main_col = (245, 197, 66) if it["equivalent"] else acc
        for scale in SCALES:
            blocks = []
            pl, psz = fit_lines(it["word"], int(108 * scale), "Black", 960, 3, 44)
            wlines = [WordLine(l, psz, WHITE) for l in pl]
            pitch = int(psz * 1.14)
            ph = pitch * (len(pl) - 1) + wlines[0].img.height - 50
            blocks.append((ph, 8 * scale, dict(key="phrase", wl=wlines, pitch=pitch)))
            if it["ipa"]:
                ib = self._ipa_block(it["ipa"], int(46 * scale), 0, it)
                blocks.append((ib["h"], 10 * scale, dict(ipa=ib, key="ipa")))
            blocks[-1] = (blocks[-1][0], 40 * scale, blocks[-1][2])
            if it["literal"]:
                lab = text_img(self.L["vw_literal"], int(34 * scale), GREY, "Bold", shadow=False)
                ll, lsz = fit_lines(it["literal"], int(50 * scale), "Bold", WIDE - 60, 2, 28)
                limg = lines_img(ll, lsz, GREY, "Bold")
                pad = 30 * scale
                ch = int((lab.height - 60) + 12 + (limg.height - 60) + 2 * pad)
                blocks.append((ch, 34 * scale, dict(key="literal", lab=lab, img=limg, lines=ll, size=lsz, pad=pad)))
            lab = text_img(big_label, int(38 * scale), main_col, "Black", shadow=False)
            bl, bsz = fit_lines(big_txt, int(76 * scale if it["equivalent"] else 66 * scale), "Black", WIDE - 60, 2, 34)
            bimg = lines_img(bl, bsz, big_col if it["equivalent"] else WHITE, "Black", shadow=True)
            simg = None
            if small_txt:
                sl, ssz = fit_lines(small_txt, int(44 * scale), "Bold", WIDE - 60, 2, 26)
                simg = lines_img(sl, ssz, WHITE if it["equivalent"] else GREY, "Bold")
            pad = 38 * scale
            ch = int((lab.height - 60) + 16 + (bimg.height - 60) + ((simg.height - 60) + 14 if simg else 0) + 2 * pad)
            blocks.append((ch, 40 * scale, dict(key="main", lab=lab, img=bimg, small=simg, pad=pad)))
            if it["example"]:
                rich = Rich(it["example"], int(52 * scale), WHITE, acc, target=it["word"])
                blocks.append((rich.img.height - 50, 12 * scale, dict(img=rich.img, key="ex", rich=rich)))
                if it["example_ar"]:
                    al, asz = fit_lines(it["example_ar"], int(42 * scale), "SemiBold", WIDE - 40, 2, 28)
                    aimg = lines_img(al, asz, GREY, "SemiBold")
                    blocks.append((aimg.height - 50, 0, dict(img=aimg, key="exar")))
            blocks[-1] = (blocks[-1][0], 0, blocks[-1][2])
            total = self._stack(it, blocks)
            if total <= BOTTOM - TOP + 1:
                break
        nwords = sum(len(w.boxes) for w in blocks[0][2]["wl"])
        t_phrase = 0.35
        t_ipa = t_phrase + 0.16 * nwords + 0.25
        end_w = self._voice(it, "w", t_ipa + 0.1) if it["clip_w"] else 0
        t = max(t_ipa + 1.0 * P, end_w + 0.35)
        t_lit = t_strike = None
        if it["literal"]:
            t_lit = t
            t += 1.0 * P
            if idiom:
                t_strike = t
                t += 0.8 * P
        t_main = t
        t = t_main + 1.6 * P
        t_ex = None
        if it["example"]:
            t_ex = t
            end_e = self._voice(it, "e", t_ex + 0.35) if it["clip_e"] else t_ex
            t = max(t_ex + (1.0 + 0.8 * bool(it["example_ar"])) * P, end_e + 0.3)
        it["D"] = t + 2.0 * P + EXIT
        it["reveal"] = None
        els = it["els"]
        for h, g, p in blocks:
            k = p["key"]
            if k == "phrase":
                wl, pitch = p["wl"], p["pitch"]
                y0 = p["y"] - pitch * (len(wl) - 1) / 2
                c = 0
                for li, w in enumerate(wl):
                    x0 = 540 - w.img.width / 2
                    for (a, b), crop in zip(w.boxes, w.crops):
                        els.append(self.el(crop, t_phrase + 0.16 * c, "word", x=x0 + (a + b) / 2, y=y0 + li * pitch))
                        c += 1
            elif k == "ipa":
                ib = p["ipa"]
                ib["t"], ib["y"] = t_ipa, p["y"]
                els.append(ib)
            elif k == "literal":
                els.append(self.el(card(900, int(h), (110, 120, 150), cf, alpha=205), t_lit, "card", y=p["y"]))
                lab, limg = p["lab"], p["img"]
                ly = p["y"] - h / 2 + p["pad"] + (lab.height - 60) / 2
                ty = ly + (lab.height - 60) / 2 + 12 + (limg.height - 60) / 2
                els.append(self.el(lab, t_lit + 0.1, "fade", y=ly))
                els.append(self.el(limg, t_lit + 0.15, "rise", y=ty))
                if idiom:
                    nl = len(p["lines"])
                    pitch = int(p["size"] * 1.34)
                    for li, line in enumerate(p["lines"]):
                        lw = text_width(line, p["size"], "Bold")
                        it["fx"].append(dict(kind="strike", t=t_strike + 0.1 * li, x0=540 - lw / 2 - 10,
                                             x1=540 + lw / 2 + 10, y=ty + (li - (nl - 1) / 2) * pitch + 3,
                                             col=RED, width=7))
            elif k == "main":
                els.append(self.el(card(900, int(h), main_col, cf, glow=main_col), t_main, "card", y=p["y"]))
                lab, bimg, simg = p["lab"], p["img"], p["small"]
                y = p["y"] - h / 2 + p["pad"] + (lab.height - 60) / 2
                els.append(self.el(lab, t_main + 0.1, "fade", y=y))
                y += (lab.height - 60) / 2 + 16 + (bimg.height - 60) / 2
                els.append(self.el(bimg, t_main + 0.15, "pop", y=y))
                if simg is not None:
                    y += (bimg.height - 60) / 2 + 14 + (simg.height - 60) / 2
                    els.append(self.el(simg, t_main + 0.6, "fade", y=y))
            elif k == "ex":
                els.append(self.el(p["img"], t_ex, "rise", y=p["y"], rich=p["rich"], ul=t_ex + 0.45, ulcol=acc))
            elif k == "exar":
                els.append(self.el(p["img"], t_ex + 0.8 * P, "fade", y=p["y"]))
        it["snd"] = [("tap", t_phrase + 0.16 * c, 0.12) for c in range(nwords)]
        if t_lit is not None:
            it["snd"].append(("pop", t_lit, 0.28))
        if t_strike is not None:
            it["snd"].append(("buzz", t_strike, 0.2))
        it["snd"].append(("chime", t_main, 0.32))
        if t_ex is not None:
            it["snd"].append(("swish", t_ex - 0.1, 0.18))

    # ============================================================ recap
    def _recap_rows(self):
        """[(English, Arabic, struck-out mistake or None, accent)] — a word list gives one row per word."""
        rows = []
        for it in self.items:
            typ = it["type"]
            if typ == "list":
                rows += [(w["en"], _short(w["ar"]), None, it["acc"]) for w in it["words"]]
                continue
            en, ar, struck = it["word"], it["recap"], None
            if typ in ("guess", "reverse"):
                right = it["options"][it["correct"]]
                if typ == "reverse":
                    en, ar = right, it["recap"] or it["word"]
                else:
                    en = it["word"] or right
                    ar = it["recap"] or (right if it["word"] else "")
            elif typ == "mistake":
                en, struck = it["word"], it["wrong"]
                ar = it["recap"]
            elif typ == "proverb":
                ar = it["recap"] or it["equivalent"] or _short(it["meaning"])
            else:
                ar = it["recap"] or _short(it["meaning"])
            rows.append((en, ar, struck, it["acc"]))
        return rows

    def _build_recap(self, rows):
        n = len(rows)
        self.recap_title = text_img(self.L["vw_recap"], 72, WHITE, "Black", shadow=True, max_w=WIDE)
        avail = BOTTOM - TOP - 120
        self.recap_imgs, heights = [], []
        two = n <= 6
        if two:  # English on top (up to 2 lines), Arabic meaning (or the struck-out mistake) under it
            for k, (en, ar, struck, acc) in enumerate(rows):
                im, h = self._recap_row2(k, en, ar, struck, acc)
                self.recap_imgs.append(im)
                heights.append(h)
            gap = 18
            if sum(heights) + gap * (n - 1) > avail:
                two = False
                self.recap_imgs, heights = [], []
        if not two:  # one line per row: English on the left, Arabic on the right (lower rows when there are many)
            h1 = min(84, int((avail - 6 * (n - 1)) / n))
            for k, (en, ar, struck, acc) in enumerate(rows):
                im, h = self._recap_row1(k, en, ar, struck, acc, h1)
                self.recap_imgs.append(im)
                heights.append(h)
            gap = max(6, min(16, int((avail - sum(heights)) / max(1, n - 1))))
        block = 120 + sum(heights) + gap * (n - 1)
        y = TOP + max(0, (BOTTOM - TOP - block) / 2)
        self.recap_title_y = y + 40
        y += 120
        self.recap_y = []
        for h in heights:
            self.recap_y.append(y + h / 2)
            y += h + gap
        self.recap_step = 0.38 if n <= 6 else 0.25
        self.recap_len = 0.7 + self.recap_step * n + 2.2 * self.P

    def _recap_num(self, im, k, cy, acc, r=28):
        d = ImageDraw.Draw(im)
        cx = 40 + 52
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(acc) + (255,))
        num = text_img(str(k + 1), int(32 * r / 28), INK, "Black", shadow=False)
        im.alpha_composite(num, (cx - num.width // 2, int(cy - num.height // 2 - 2)))

    def _recap_line(self, im, cy, en, esz, side, ssz, struck, acc, right):
        """English on the left and the Arabic meaning (or the struck-out mistake) on the right, both on ONE
        baseline, so words of different heights (Sanctions / عقوبات) sit exactly level with the number."""
        base = cy + 0.3 * esz  # Latin capitals and Arabic letters both centre ~0.3 × size above the baseline
        e = baseline_img(en, esz, acc, "Black")
        im.alpha_composite(e, (40 + 104 - 20, int(base - esz * 1.2)))
        if side:
            a = baseline_img(side, ssz, (255, 140, 140) if struck else WHITE, "Bold")
            ax = right - (a.width - 20)
            im.alpha_composite(a, (int(ax), int(base - ssz * 1.2)))
            if struck:
                y = base - 0.3 * ssz
                ImageDraw.Draw(im).line([(ax + 14, y + 2), (ax + a.width - 14, y - 2)], fill=RED + (255,), width=4)

    def _recap_row2(self, k, en, ar, struck, acc):
        side = struck or ar
        if text_width(en, 48, "Black") + (text_width(side, 42, "Bold") + 60 if side else 0) <= 730:
            h = 100  # short enough: one line, English left, meaning right
            im = card(880, h, shade(acc, 0.85), self.card_fill, alpha=236, r=34, width=3).copy()
            self._recap_num(im, k, 40 + h / 2, acc)
            self._recap_line(im, 40 + h / 2, en, 48, side, 42, struck, acc, 40 + 880 - 40)
            return im, h
        el, esz = fit_lines(en, 48, "Black", 720, 2, 34)
        eimg = lines_img(el, esz, acc, "Black", align="l", pitch=int(esz * 1.22))
        side = struck or ar
        simg = None
        if side:
            sl, ssz = fit_lines(side, 40, "Bold", 720, 1, 28)
            simg = text_img(sl[0], ssz, (255, 140, 140) if struck else WHITE, "Bold", shadow=False)
        eh = eimg.height - 60
        sh = (simg.height - 60) if simg is not None else 0
        h = int(30 + eh + (14 + sh if simg is not None else 0) + 30)
        im = card(880, h, shade(acc, 0.85), self.card_fill, alpha=236, r=34, width=3).copy()
        self._recap_num(im, k, 40 + h / 2, acc)
        im.alpha_composite(eimg, (40 + 104 - 30, 40 + 30 - 30))
        if simg is not None:
            sy = 40 + 30 + eh + 14 - 30
            if is_rtl(side) and not struck:
                sx = 40 + 880 - 40 - simg.width + 30
            else:
                sx = 40 + 104 - 30
            im.alpha_composite(simg, (sx, sy))
            if struck:
                my = sy + simg.height / 2 + 2
                ImageDraw.Draw(im).line([(sx + 22, my + 2), (sx + simg.width - 22, my - 2)], fill=RED + (255,), width=5)
        return im, h

    def _recap_row1(self, k, en, ar, struck, acc, h=84):
        im = card(880, h, shade(acc, 0.85), self.card_fill, alpha=236, r=30, width=3).copy()
        cy = 40 + h // 2
        self._recap_num(im, k, cy, acc, min(28, int(h * 0.33)))
        e0, s0 = int(40 * min(1.0, h / 84)), int(36 * min(1.0, h / 84))
        en = ellipsize(en, e0, "Black", 400)
        esz = fit_lines(en, e0, "Black", 400, 1, 20)[1]
        side = struck or ar
        ssz = s0
        if side:
            side = ellipsize(side, s0, "Bold", 320)
            ssz = fit_lines(side, s0, "Bold", 320, 1, 18)[1]
        self._recap_line(im, cy, en, esz, side, ssz, struck, acc, 40 + 880 - 36)
        return im, h

    # ============================================================ render
    def render(self, t):
        frame = self.bg.copy()
        d = ImageDraw.Draw(frame)
        if self.stars:
            self.stars.draw(d, t, t * 25)
        if t < INTRO + 0.05:
            self._draw_intro(frame, t)
        for it in self.items:
            if it["t0"] - 0.01 <= t < it["t0"] + it["D"]:
                self._draw_item(frame, it, t - it["t0"])
        if self.recap_on and self.R0 <= t < self.E + 0.4:
            self._draw_recap(frame, t)
        draw_ending(frame, t, self.E, *self.ending, self.accent)
        global_fade(frame, t, self.dur)
        return frame.convert("RGB")

    def _draw_intro(self, frame, t):
        out = prog(t, INTRO - 0.4, INTRO - 0.05)
        k = 1 - out
        if self.ghost is not None:
            a = 0.08 * prog(t, 0.0, 0.8) * k
            paste(frame, self.ghost, 540 + 30 - t * 22, 1300, 1.0 + 0.03 * t, a)
        if self.title_fx is not None:
            fx = self.title_fx
            p = ease_out_back(prog(t, 0.2, 0.55))
            paste(frame, self.badge_img, 540, fx.t_badge_y, 0.6 + 0.4 * p, min(1, p * 2) * k)
            fx.draw(frame, t)
            if self.lesson_img is not None:
                pl = prog(t, fx.hit + 0.55, fx.hit + 0.9)
                y = (fx.sub_y + 100) if fx.sub is not None else fx.bar_y + 70
                paste(frame, self.lesson_img, 540, y + 20 * (1 - pl), 1, pl * k)
            return
        ty = 800
        p = ease_out_back(prog(t, 0.1, 0.45))
        paste(frame, self.badge_img, 540, ty - 170 - self.title_img.height / 2 + 60, 0.6 + 0.4 * p, min(1, p * 2) * k)
        p = ease_out_back(prog(t, 0.3, 0.75))
        paste(frame, self.title_img, 540, ty, 0.5 + 0.5 * p, min(1, p * 2) * k)
        y = ty + self.title_img.height / 2 + 40
        if self.sub_img is not None:
            p = prog(t, 0.65, 1.0)
            paste(frame, self.sub_img, 540, y + self.sub_img.height / 2 - 30 + 30 * (1 - p), 1, p * k)
            y += self.sub_img.height - 30
        if self.lesson_img is not None:
            p = prog(t, 0.95, 1.25)
            paste(frame, self.lesson_img, 540, y + 40, 1, p * k)

    def _draw_header(self, frame, it, u):
        D = it["D"]
        out = prog(u, D - EXIT, D)
        i = it["i"]
        prev = self.items[i - 1]["badge"] if i > 0 else None
        nxt = self.items[i + 1]["badge"] if i < len(self.items) - 1 else None
        # the group badge stays put between items of the same group; it fades only when it changes
        ab = (prog(u, 0.0, 0.3) if prev != it["badge"] else 1.0) * ((1 - out) if nxt != it["badge"] else 1.0)
        paste(frame, it["badge_img"], 540, 228, 1.0, ab)
        p = ease_out_back(prog(u, 0.0, 0.4))
        paste(frame, it["head"], 540, 305 - 50 * (1 - p), 0.8 + 0.2 * p, min(1, p * 2) * (1 - out))
        n = len(self.items)
        gap = 46 if n <= 7 else 36
        x0 = 540 - (n - 1) * gap / 2
        a = int(255 * (prog(u, 0.0, 0.3) if i == 0 else 1.0) * ((1 - out) if nxt is None else 1.0))
        d = ImageDraw.Draw(frame)
        grow = prog(u, 0.15, 0.55)
        for k in range(n):
            if k < it["i"]:
                col, r = self.items[k]["acc"], 8
            elif k == it["i"]:
                col = it["acc"] if grow > 0.01 else DIM
                r = 8 + 3 * grow + 4 * math.sin(math.pi * grow)
            else:
                col, r = DIM, 8
            x = x0 + k * gap
            d.ellipse([x - r, 372 - r, x + r, 372 + r], fill=tuple(col) + (a,))

    def _draw_item(self, frame, it, u):
        if it["type"] == "list":  # a full page of its own (background, title and rows)
            it["page"].draw(frame, u)
            return
        self._draw_header(frame, it, u)
        D = it["D"]
        out = ease_io(prog(u, D - EXIT, D))
        k = 1 - out
        dx = -420 * out
        d = ImageDraw.Draw(frame)
        for e in it["els"]:
            if u < e["t"]:
                continue
            kind = e.get("kind")
            if kind == "div":
                p = ease_io(prog(u, e["t"], e["t"] + 0.4))
                w = e["w"] / 2 * p
                d.line([(540 + dx - w, e["y"]), (540 + dx + w, e["y"])], fill=tuple(e["col"]) + (int(255 * k),), width=3)
                continue
            if kind == "ipa":
                self._draw_ipa(frame, it, e, u, dx, k)
                continue
            self._draw_el(frame, e, u, dx, k, it)
        for f in it["fx"]:
            if f["kind"] == "strike" and u >= f["t"]:
                p = ease_io(prog(u, f["t"], f["t"] + 0.28))
                sh = self._shake(u, f.get("shake"))
                x0 = f["x0"] + dx + sh
                d.line([(x0, f["y"]), (x0 + (f["x1"] - f["x0"]) * p, f["y"] - 8 * p)],
                       fill=tuple(f["col"]) + (int(255 * k),), width=f.get("width", 10))
        if it["type"] in ("guess", "reverse"):
            self._draw_timer(frame, it, u, k)

    @staticmethod
    def _shake(u, win):
        if not win or not (win[0] <= u < win[1]):
            return 0.0
        return math.sin((u - win[0]) * 70) * 16 * (1 - prog(u, win[0], win[1]))

    def _draw_el(self, frame, e, u, dx, k, it):
        t0, anim = e["t"], e["anim"]
        x, y = e["x"] + dx, e["y"]
        img = e["img"]
        sc, a = 1.0, 1.0
        if anim == "rise":
            p = prog(u, t0, t0 + 0.35)
            y += 30 * (1 - ease_io(p))
            a = p
        elif anim == "fade":
            a = prog(u, t0, t0 + 0.3)
        elif anim == "pop":
            p = ease_out_back(prog(u, t0, t0 + 0.4))
            sc, a = 0.6 + 0.4 * p, min(1, p * 2)
        elif anim == "slam":
            p = ease_out_back(prog(u, t0, t0 + 0.45))
            sc, a = 0.5 + 0.5 * p, min(1, p * 2)
        elif anim == "card":
            p = ease_out_back(prog(u, t0, t0 + 0.45))
            y += 70 * (1 - p)
            sc, a = 0.94 + 0.06 * p, min(1, p * 2)
        elif anim == "news":
            p = ease_out_back(prog(u, t0, t0 + 0.4))
            x += 0
            sc, a = 0.85 + 0.15 * p, min(1, p * 2.2)
        elif anim == "slide":
            p = ease_out_back(prog(u, t0, t0 + 0.4))
            x += 300 * (1 - p)
            a = min(1, p * 2)
        elif anim == "slide_in":
            p = ease_out_back(prog(u, t0, t0 + 0.45))
            x += e.get("side", 1) * 520 * (1 - p)
            a = min(1, p * 2)
        elif anim == "word":
            p = ease_out_back(prog(u, t0, t0 + 0.35))
            y += 26 * (1 - p)
            sc, a = 0.85 + 0.15 * p, min(1, p * 2.5)
        x += self._shake(u, e.get("shake"))
        if e.get("bump"):
            b0, b1 = e["bump"]
            sc *= 1 + 0.07 * math.sin(math.pi * prog(u, b0, b1))
        opt = e.get("opt")
        if opt:
            R = opt["R"]
            rv = prog(u, R, R + 0.3)
            if opt["correct"]:
                sc *= 1 + 0.045 * math.sin(math.pi * prog(u, R, R + 0.5))
                paste(frame, img, x, y, sc, a * k * (1 - rv))
                if rv > 0:
                    paste(frame, opt["ok"], x, y, sc, rv * k)
                pm = ease_out_back(prog(u, R + 0.1, R + 0.45))
                if pm > 0:
                    paste(frame, mark(True), opt["mark_x"] + dx, y, pm, min(1, pm * 2) * k)
            else:
                paste(frame, img, x, y, sc, a * k * (1 - 0.55 * rv))
            return
        paste(frame, img, x, y, sc, a * k)
        rich = e.get("rich")
        if rich is not None and e.get("ul") is not None and abs(sc - 1) < 0.01:
            p = ease_io(prog(u, e["ul"], e["ul"] + 0.45))
            if e.get("rich_xy"):  # the sentence sits inside the news card
                cx = x - img.width / 2 + e["rich_xy"][0]
                cy = y - img.height / 2 + e["rich_xy"][1]
            else:
                cx, cy = x, y
            rich.underline(frame, cx, cy, p, e["ulcol"], a * k)

    def _draw_ipa(self, frame, it, e, u, dx, k):
        a = prog(u, e["t"], e["t"] + 0.35) * k
        if a <= 0.01:
            return
        im, (body, w1, w2) = e["img"], e["spk"]
        x0 = 540 - e["w"] / 2 + dx
        y = e["y"] + 8 * (1 - prog(u, e["t"], e["t"] + 0.35))
        spk_x = x0 + 45
        paste(frame, body, spk_x + 15, y, 1, a)
        speak = it.get("speak")
        if speak and speak[0] <= u < speak[1] + 0.15:
            ph = (u - speak[0]) * 7
            a1 = 0.35 + 0.65 * max(0.0, math.sin(ph))
            a2 = 0.35 + 0.65 * max(0.0, math.sin(ph - 1.1))
        else:
            a1 = a2 = 1.0
        paste(frame, w1, spk_x + 15, y, 1, a * a1)
        paste(frame, w2, spk_x + 15, y, 1, a * a2)
        paste(frame, im, x0 + 100 + im.width / 2 - 30, y, 1, a)

    def _draw_timer(self, frame, it, u, k):
        c0, R = it["count"], it["reveal"]
        if not (c0 - 0.3 <= u < R + 0.3):
            return
        a = prog(u, c0 - 0.3, c0) * (1 - prog(u, R, R + 0.25)) * k
        if a <= 0.01:
            return
        T = self.guess_secs
        rem = 1 - prog(u, c0, R)
        left = max(0, math.ceil(R - u)) if u >= c0 else T
        col = RED if (R - u) <= 2 and u >= c0 else it["acc"]
        draw_timer(self.timer, frame, 540, it["timer_y"], rem, min(T, left), T, col, WHITE, max(0.0, u - c0), a,
                   False, self.timer_fx)

    def _draw_recap(self, frame, t):
        T = self.R0
        k = 1 - prog(t, self.E, self.E + 0.3)
        p = ease_out_back(prog(t, T + 0.05, T + 0.5))
        paste(frame, self.small_badge, 540, 228, 1, prog(t, T, T + 0.3) * k)
        paste(frame, self.recap_title, 540, self.recap_title_y, 0.6 + 0.4 * p, min(1, p * 2) * k)
        for j, im in enumerate(self.recap_imgs):
            ts = T + 0.6 + self.recap_step * j
            p = ease_out_back(prog(t, ts, ts + 0.4))
            paste(frame, im, 540 + (1 - p) * 420, self.recap_y[j], 1, min(1, p * 2) * k)

    # ============================================================ sound
    def sound(self, mx):
        mx.intro(0.05)
        if self.title_style == "Simple":
            mx.add(0.3, mx.pop(), 0.3)
        else:
            mx.add(0.25, mx.pop(), 0.22)
        if self.lesson_img is not None:
            mx.add(1.0, mx.click(), 0.18)
        tap = None
        for it in self.items:
            T = it["t0"]
            s, pn = mx.whoosh(0.7)
            mx.add(T - 0.25, s, 0.38, pn)
            mx.add(T + 0.05, mx.click(), 0.25)
            for kind, at, gain in it["snd"]:
                if kind == "pop":
                    sig = mx.pop()
                elif kind == "click":
                    sig = mx.click()
                elif kind == "ding":
                    sig = mx.ding()
                elif kind == "chime":
                    sig = mx.chime()
                elif kind == "buzz":
                    sig = mx.buzz()
                elif kind == "thump":
                    sig = mx.thump()
                elif kind == "news":
                    sig = mx.news_sting()
                elif kind == "tap":
                    if tap is None:
                        tap = mx.click() * 0.6
                    sig = tap
                else:  # swish
                    sig, pn2 = mx.whoosh(0.5)
                    mx.add(T + at, sig, gain, pn2)
                    continue
                mx.add(T + at, sig, gain)
            if it.get("reveal") is not None:
                c0, R = T + it["count"], T + it["reveal"]
                secs = self.guess_secs
                for j in range(secs):
                    hi = j >= secs - 2
                    mx.add(c0 + j, mx.tick(2400 if hi else 1500), 0.3 if hi else 0.22)
                if self.timer == "Fuse":
                    mx.add(c0, mx.sizzle(secs), 0.22)
                mx.add(R - 0.6, mx.drumroll(0.6), 0.32)
                mx.add(R, mx.ding(), 0.5)
                mx.add(R + 0.08, mx.sparkle(), 0.28)
        if self.recap_on:
            s, pn = mx.whoosh(0.7)
            mx.add(self.R0 - 0.25, s, 0.35, pn)
            mx.add(self.R0 + 0.05, mx.chime(), 0.2)
            for j in range(len(self.items)):
                mx.add(self.R0 + 0.6 + self.recap_step * j, mx.pop(), 0.24)
        mx.add(self.E + 0.2, mx.chime(), 0.3)
        for at, path in self.voices:
            mx.add_voice(path, at, self.audio_gain)


class VocabTitle(TitleIntro):
    """The Fancy opening title with an 'Aa' badge instead of the question mark."""

    def _badge(self, mark):
        return super()._badge("Aa")


# ------------------------------------------------------------------ editor helpers (app buttons)
SKELETONS = {
    "word": "type: word\nword: \nipa: \npos: noun • اسم\nmeaning: \nexample: \nexample_ar: \nalso: ",
    "guess": "type: guess\nword: \nipa: \n- \n- *\n- \n- \nexample: \nexample_ar: ",
    "reverse": "type: reverse\nword: \n- *\n- \n- \nexample: ",
    "mistake": "type: mistake\nwrong: \nright: \nmeaning: \nexample: \nexample_ar: ",
    "proverb": "type: proverb\nword: \nipa: \nliteral: \nequivalent: \nmeaning: \nexample: \nexample_ar: ",
    "idiom": "type: idiom\nword: \nipa: \nliteral: \nmeaning: \nnote: \nexample: \nexample_ar: ",
    "list": "type: list\ntitle: \nsubtitle: \n- English = العربية\n- English = العربية\n- English = العربية\n"
            "- English = العربية",
}


def add_item(text, typ):
    """Append an empty item of type `typ` to the items text."""
    body = str(text or "").rstrip()
    return (body + "\n\n" if body else "") + SKELETONS.get(typ, SKELETONS["word"])


def to_word_cards(text):
    """Turn every guess / reverse item into a word card (its correct option becomes the meaning).
    Returns (new text, how many items changed). Other types stay as they are."""
    items = parse_items(text)
    changed = 0
    for it in items:
        if it["type"] in ("guess", "reverse"):
            right = it["options"][it["correct"]]
            if it["type"] == "reverse":
                it["word"], it["meaning"] = right, it["word"]
            else:
                it["meaning"] = it["meaning"] or right
            if not it["word"]:
                continue
            it["type"], it["options"], it["correct"] = "word", [], None
            changed += 1
    return items_text(items), changed
