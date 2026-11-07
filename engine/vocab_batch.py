"""English Words from a spreadsheet: one row = one item (word, guess, mistake, proverb, idiom), split into videos.

Sheet layout (first row = headers, English or Arabic, any order; see write_template()):
    Group | Type | Word / Phrase | IPA | Part of speech | Meaning | Example | Example (Arabic) | Similar words |
    Option A | Option B | Option C | Option D | Correct | Wrong sentence | Literal meaning | Arabic equivalent |
    Note | Question | Recap | Audio | Example audio

- Group: General / Political / Proverbs / Idioms / Mistakes (or سياسة، أمثال …) or any name of your own;
  empty = the group chosen in the app.
- Type: word / guess / reverse / mistake / proverb / idiom; empty = worked out from the row (options -> guess,
  wrong sentence -> mistake, Arabic equivalent -> proverb, literal meaning -> idiom, otherwise a word card).
- Correct: A-D (أ-د, 1-4) or the text of the right option. Audio cells: a file name of an uploaded clip,
  a path relative to the audio folder, or a full path.
- Split "by group": every group gets its own videos (5 political rows + 5 proverb rows at 5 per video = 2 videos).
  "In sheet order": consecutive rows, groups may mix (each item keeps its own badge and colour).
"""
import copy
import os
import re
import shutil

from .batch import AudioFinder, _norm, add_dropdowns, read_table
from .templates.vocab import GROUPS, MAX_ITEMS, group_key, items_text, parse_items

SPLIT_MODES = [("One group per video (recommended)", "group"), ("In sheet order (groups may mix)", "order")]

_ALIASES = {
    "group": ["group", "category", "series", "المجموعه", "مجموعه", "الفئه", "فئه", "التصنيف"],
    "type": ["type", "kind", "itemtype", "النوع", "نوع"],
    "word": ["word", "wordphrase", "phrase", "term", "proverb", "idiom", "correctsentence", "rightsentence", "الكلمه",
             "كلمه", "العباره", "الكلمهالعباره", "المصطلح", "المثل", "التعبير", "الجملهالصحيحه"],
    "ipa": ["ipa", "pronunciation", "phonetic", "phonetics", "النطق", "نطق"],
    "pos": ["partofspeech", "pos", "wordtype", "class", "نوعالكلمه"],
    "meaning": ["meaning", "arabicmeaning", "rule", "المعني", "معني", "القاعده"],
    "example": ["example", "sentence", "examplesentence", "المثال", "مثال"],
    "example_ar": ["examplearabic", "examplear", "exampletranslation", "translation", "ترجمهالمثال", "الترجمه"],
    "also": ["similarwords", "synonyms", "similar", "also", "related", "مرادفات", "كلماتمشابهه"],
    "opt0": ["optiona", "a", "choicea", "option1", "الخيارا", "خيارا"],
    "opt1": ["optionb", "b", "choiceb", "option2", "الخيارب", "خيارب"],
    "opt2": ["optionc", "c", "choicec", "option3", "الخيارج", "خيارج"],
    "opt3": ["optiond", "d", "choiced", "option4", "الخيارد", "خيارد"],
    "correct": ["correct", "answer", "correctanswer", "الاجابه", "الاجابهالصحيحه", "الصحيح"],
    "wrong": ["wrongsentence", "wrong", "mistake", "الجملهالخاطئه", "الخطا"],
    "literal": ["literalmeaning", "literal", "الترجمهالحرفيه", "المعنيالحرفي", "حرفي"],
    "equivalent": ["arabicequivalent", "equivalent", "arabicproverb", "المثلالعربي", "المقابل", "المثلالمقابل"],
    "note": ["note", "extra", "ملاحظه"],
    "question": ["question", "prompt", "السؤال", "سؤال"],
    "recap": ["recap", "summary", "الملخص", "ملخص"],
    "aud_w": ["audio", "wordaudio", "sound", "voice", "الصوت", "صوت", "صوتالكلمه"],
    "aud_e": ["exampleaudio", "audioexample", "examplesound", "صوتالمثال"],
}
_LOOKUP = {_norm(a): k for k, names in _ALIASES.items() for a in names}
HEADERS = ["Group", "Type", "Word / Phrase", "IPA", "Part of speech", "Meaning", "Example", "Example (Arabic)",
           "Similar words", "Option A", "Option B", "Option C", "Option D", "Correct", "Wrong sentence",
           "Literal meaning", "Arabic equivalent", "Note", "Question", "Recap", "Audio", "Example audio"]
WIDTHS = [12, 10, 30, 22, 16, 30, 44, 44, 22, 22, 22, 22, 22, 9, 26, 30, 30, 26, 26, 22, 14, 14]
_TEXT_KEYS = ["word", "ipa", "pos", "meaning", "example", "example_ar", "also", "wrong", "literal", "equivalent",
              "note", "question", "recap"]


def _columns(header):
    cols = {}
    for i, h in enumerate(header):
        key = _LOOKUP.get(_norm(h))
        if key and key not in cols:
            cols[key] = i
    return cols


def parse_rows(rows, finder=None):
    """Sheet rows -> (items, problems). Each item is a parsed vocab item plus row, group key/name and audio."""
    finder = finder or AudioFinder()
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return [], ["The sheet is empty."]
    cols = _columns(rows[0])
    if "word" not in cols and "wrong" not in cols and "question" not in cols:
        return [], ["No “Word / Phrase” column found — keep the header row of the template (download it on the right)."]
    items, problems = [], []

    def get(row, key):
        i = cols.get(key)
        return " ".join(str(row[i]).split()) if i is not None and i < len(row) else ""

    for n, row in enumerate(rows[1:], 2):
        lines = []
        typ = get(row, "type")
        if typ:
            lines.append(f"type: {typ}")
        for key in _TEXT_KEYS:
            val = get(row, key)
            if val:
                lines.append(f"{key}: {val}")
        opts = [(k, get(row, f"opt{k}")) for k in range(4)]
        opts = [(k, o.strip("*").strip()) for k, o in opts if o.strip("*").strip()]
        correct = get(row, "correct")
        for k, o in opts:
            lines.append(f"- {o}")
        if opts:
            if correct:
                letter = _norm(correct)
                pos = {"a": 0, "b": 1, "c": 2, "d": 3, "ا": 0, "ب": 1, "ج": 2, "د": 3, "1": 0, "2": 1, "3": 2, "4": 3}
                if letter in pos:  # the letter names a column; options may skip an empty column
                    slots = [k for k, _ in opts]
                    if pos[letter] in slots:
                        lines.append(f"answer: {'abcd'[slots.index(pos[letter])]}")
                    else:
                        problems.append(f"Row {n}: Correct is “{correct}” but that option is empty — skipped")
                        continue
                else:
                    lines.append(f"answer: {correct}")
        if not any(get(row, k) for k in ("word", "wrong", "question")) and not opts:
            if any(get(row, k) for k in _TEXT_KEYS):
                problems.append(f"Row {n}: no Word / Phrase — skipped")
            continue
        try:
            it = parse_items("\n".join(lines))[0]
        except ValueError as e:
            problems.append(f"Row {n}: " + str(e).replace("Item 1: ", "").replace("Item 1 ", ""))
            continue
        g_cell = get(row, "group")
        gk = group_key(g_cell) if g_cell else ""
        it.update(row=n, gkey=gk if gk is not None else "custom", gname="" if gk else g_cell, audio={})
        missing = []
        for slot, colkey in (("w", "aud_w"), ("e", "aud_e")):
            cell = get(row, colkey)
            if cell:
                path = finder.find(cell)
                if path:
                    it["audio"][slot] = path
                else:
                    missing.append(cell)
        if missing:
            problems.append(f"Row {n}: audio not found: {', '.join(missing)} — kept without "
                            f"{'it' if len(missing) == 1 else 'them'}")
        items.append(it)
    return items, problems


def load_sheet(path, uploads=(), folder=""):
    return parse_rows(read_table(path), AudioFinder(uploads, folder))


# ------------------------------------------------------------------ splitting
def split(items, per_video, mode="group", default_group="general"):
    """-> list of videos: dict(gkey, gname, items). gkey '' (empty Group cell) means the app's group."""
    per = max(1, min(MAX_ITEMS, int(per_video or 5)))
    if mode == "order":
        chunks = [items[i:i + per] for i in range(0, len(items), per)]
        out = []
        for c in chunks:
            first = c[0]
            out.append(dict(gkey=first["gkey"], gname=first["gname"], items=c))
        return out
    groups, order = {}, []
    for it in items:
        key = (it["gkey"] or default_group, _norm(it["gname"]))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(it)
    out = []
    for key in order:
        rows = groups[key]
        for i in range(0, len(rows), per):
            c = rows[i:i + per]
            out.append(dict(gkey=key[0], gname=c[0]["gname"], items=c))
    return out


def group_label(video, default_group="general", default_name=""):
    g = video["gkey"] or default_group
    if g == "custom":
        return video["gname"] or default_name or "My words"
    return GROUPS.get(g, GROUPS["general"])["label"]


def _item_text(video, it, default_group):
    """The item as editor text; an item from another group than its video keeps its own group line."""
    vg = video["gkey"] or default_group
    ig = it["gkey"] or default_group
    same = ig == vg and _norm(it["gname"]) == _norm(video["gname"])
    d = dict(it)
    d["group"] = "" if same else (it["gname"] if ig == "custom" else ig)
    return d


def clip_files(items, folder):
    """Copy the video's clips into `folder` as w1, w1e … so the template matches them to its items."""
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    out = []
    for n, it in enumerate(items, 1):
        for slot, src in it["audio"].items():
            os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, f"w{n}{'' if slot == 'w' else 'e'}{os.path.splitext(src)[1].lower()}")
            shutil.copy2(src, dst)
            out.append(dst)
    return out


def part_project(base, video, n, total, audio_dir, lesson_n=None, title=None, subtitle=None):
    """A normal vocab project for video n of total, built from the editor's settings."""
    p = copy.deepcopy(base)
    v = p.setdefault("vocab", {})
    default_group = v.get("group") or "general"
    if video["gkey"]:
        v["group"] = video["gkey"]
        v["group_name"] = video["gname"] if video["gkey"] == "custom" else ""
        if video["gkey"] != default_group:  # another group: its own colour and theme
            v["accent"] = "group"
            v["background"] = "group"
    v["items"] = items_text([_item_text(video, it, default_group) for it in video["items"]])
    v["audio"] = clip_files(video["items"], audio_dir)
    if lesson_n is not None:
        v["lesson_n"] = lesson_n
    for key, txt in (("title", title), ("subtitle", subtitle)):
        if txt:
            v[key] = str(txt).replace("{n}", str(n)).replace("{total}", str(total))
    return p


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f_]+')


def video_name(video, k, default_group="general", default_name="", taken=None):
    """'Political words 1 — Sanctions, Referendum, Ceasefire' (safe for Windows, unique within `taken`)."""
    label = group_label(video, default_group, default_name)
    words = []
    for it in video["items"]:
        w = it["word"] or it["question"] or it["wrong"]
        if w:
            words.append(w)
    name = f"{k:02d} {label} — " + ", ".join(words)
    name = " ".join(_BAD.sub(" ", name).split())
    if len(name) > 80:
        cut = name[:81].rsplit(" ", 1)[0]
        name = (cut if len(cut) > 40 else name[:80]).rstrip(" ,—") + "…"
    name = name.rstrip(" .")
    if taken is not None:
        base, j = name, 2
        while name.lower() in taken:
            name, j = f"{base} ({j})", j + 1
        taken.add(name.lower())
    return name


def summary(items, problems, videos, default_group="general", default_name=""):
    if not items:
        return "⚠️ No usable rows." + ("\n\n" + "  \n".join("⚠️ " + p for p in problems[:30]) if problems else "")
    clips = sum(len(it["audio"]) for it in items)
    by = {}
    for v in videos:
        lab = group_label(v, default_group, default_name)
        by[lab] = by.get(lab, 0) + 1
    parts = ", ".join(f"{lab}: {c}" for lab, c in by.items())
    txt = (f"**{len(items)} items → {len(videos)} video{'s' if len(videos) != 1 else ''}** ({parts}) · "
           f"{clips} audio clip{'s' if clips != 1 else ''} found")
    if problems:
        more = f"  \n…and {len(problems) - 30} more" if len(problems) > 30 else ""
        txt += "\n\n" + "  \n".join("⚠️ " + p for p in problems[:30]) + more
    return txt


# ------------------------------------------------------------------ template
EXAMPLE_ROWS = [
    dict(Group="Political", Type="word", **{"Word / Phrase": "Sanctions", "IPA": "/ˈsæŋkʃənz/",
         "Part of speech": "noun • اسم", "Meaning": "عقوبات (على دولة أو جهة)",
         "Example": "UN imposes new sanctions on the regime",
         "Example (Arabic)": "فرضت الأمم المتحدة عقوبات جديدة على النظام", "Similar words": "embargo, penalties"}),
    dict(Group="Political", Type="word", **{"Word / Phrase": "Referendum", "IPA": "/ˌrefəˈrendəm/",
         "Part of speech": "noun • اسم", "Meaning": "استفتاء شعبي",
         "Example": "Voters reject the referendum by a narrow margin",
         "Example (Arabic)": "الناخبون يرفضون الاستفتاء بفارق ضئيل", "Similar words": "vote, ballot"}),
    dict(Group="Political", Type="guess", **{"Word / Phrase": "Ceasefire", "IPA": "/ˈsiːsfaɪər/",
         "Option A": "إعلان الحرب", "Option B": "وقف إطلاق النار", "Option C": "انتخابات مبكرة",
         "Option D": "تحالف عسكري", "Correct": "B", "Example": "Both sides agreed to a ceasefire last night",
         "Example (Arabic)": "اتفق الطرفان على وقف إطلاق النار الليلة الماضية"}),
    dict(Group="Political", Type="word", **{"Word / Phrase": "Coalition", "IPA": "/ˌkəʊəˈlɪʃn/",
         "Part of speech": "noun • اسم", "Meaning": "ائتلاف • تحالف",
         "Example": "The new coalition government takes office",
         "Example (Arabic)": "حكومة الائتلاف الجديدة تتسلم السلطة", "Similar words": "alliance, union"}),
    dict(Group="Political", Type="guess", **{"Word / Phrase": "Veto", "IPA": "/ˈviːtəʊ/",
         "Option A": "حق النقض (الرفض)", "Option B": "حق التصويت", "Option C": "حصانة دبلوماسية",
         "Option D": "قرار ملزم", "Correct": "A", "Example": "Russia uses its veto at the Security Council",
         "Example (Arabic)": "روسيا تستخدم حق النقض في مجلس الأمن"}),
    dict(Group="Proverbs", Type="proverb", **{"Word / Phrase": "Actions speak louder than words",
         "IPA": "/ˈækʃənz spiːk ˈlaʊdər ðæn wɜːrdz/", "Literal meaning": "الأفعال تتكلم بصوت أعلى من الكلمات",
         "Arabic equivalent": "الأفعال أبلغ من الأقوال", "Meaning": "ما تفعله يكشف حقيقتك أكثر مما تقوله",
         "Example": "He said sorry, but actions speak louder than words.",
         "Example (Arabic)": "اعتذر، لكن الأفعال أبلغ من الأقوال."}),
    dict(Group="Proverbs", Type="guess", **{"Word / Phrase": "Don't count your chickens before they hatch",
         "Option A": "الصبر مفتاح الفرج", "Option B": "لا تقل فول حتى يصير في المكيول",
         "Option C": "العجلة من الشيطان", "Correct": "B",
         "Example": "We may win, but don't count your chickens before they hatch."}),
    dict(Group="Proverbs", Type="proverb", **{"Word / Phrase": "Every cloud has a silver lining",
         "Arabic equivalent": "رُبَّ ضارةٍ نافعة", "Meaning": "في كل مصيبة جانب إيجابي",
         "Example": "I lost my job, but every cloud has a silver lining."}),
    dict(Group="Idioms", Type="idiom", **{"Word / Phrase": "Break the ice", "IPA": "/breɪk ði aɪs/",
         "Literal meaning": "يكسر الثلج", "Meaning": "يبدأ الحديث ويُذيب التوتر", "Note": "مع أشخاص لا يعرفهم",
         "Example": "A joke can break the ice.", "Example (Arabic)": "النكتة تكسر الحاجز بين الناس."}),
    dict(Group="Idioms", Type="reverse", **{"Word / Phrase": "يكلّف ثروة", "Option A": "It costs an arm and a leg",
         "Option B": "It costs a piece of cake", "Option C": "It's a bargain", "Correct": "A",
         "Example": "This phone costs an arm and a leg."}),
    dict(Group="Mistakes", Type="mistake", **{"Word / Phrase": "I agree", "Wrong sentence": "I am agree",
         "Meaning": "agree فعل، فلا نضع قبله am", "Example": "I totally agree with you.",
         "Example (Arabic)": "أنا أتفق معك تمامًا."}),
    dict(Group="Mistakes", Type="guess", **{"Question": "Which sentence is correct?", "Option A": "I have 25 years",
         "Option B": "I am 25 years old", "Option C": "I have 25 years old", "Correct": "B",
         "Example": "I am 25 years old."}),
    dict(Group="General", Type="word", **{"Word / Phrase": "Resilient", "IPA": "/rɪˈzɪliənt/",
         "Part of speech": "adjective • صفة", "Meaning": "صامد • يتعافى بسرعة", "Example": "Children are very resilient.",
         "Example (Arabic)": "الأطفال قادرون جدًا على التعافي.", "Similar words": "tough, strong, flexible"}),
    dict(Group="General", Type="guess", **{"Word / Phrase": "Procrastinate", "IPA": "/prəˈkræstɪneɪt/",
         "Option A": "يُسرِع في العمل", "Option B": "يؤجِّل ويماطل", "Option C": "يحتفل", "Option D": "يتذكّر",
         "Correct": "B", "Example": "I always procrastinate on Mondays."}),
]
HOW_TO = [
    "One item per row. Keep the header row (English or Arabic headers both work, in any order).",
    "Group: pick General, Political, Proverbs, Idioms or Mistakes from the dropdown — or type any name for your own",
    "group (it gets its own badge and colour). Empty = the group chosen in the app.",
    "Type: word, guess, reverse, mistake, proverb or idiom (dropdown). Empty = a word card (or worked out from the row:",
    "options → guess, wrong sentence → mistake, Arabic equivalent → proverb, literal meaning → idiom).",
    "",
    "word     : Word / Phrase, Meaning (+ IPA, Part of speech, Example, Example (Arabic), Similar words).",
    "           In the Political group the example is shown as a BREAKING NEWS headline.",
    "guess    : Word / Phrase (or Question), Option A–D, Correct (A–D) (+ IPA, Example, Example (Arabic)).",
    "reverse  : the same with Arabic in Word / Phrase and English options.",
    "mistake  : Word / Phrase = the correct sentence, Wrong sentence, Meaning = the rule (+ Example).",
    "proverb  : Word / Phrase = the English proverb, Arabic equivalent and/or Meaning (+ Literal meaning, IPA, Example).",
    "idiom    : Word / Phrase = the idiom, Literal meaning, Meaning = the real meaning (+ Note, IPA, Example).",
    "",
    "IPA: write it with or without the slashes (/rɪˈzɪliənt/). It shows next to a speaker icon.",
    "Example: the word is highlighted automatically; put *stars* around other words to choose what is highlighted.",
    "Recap: optional short meaning for the 'What did we learn today?' list at the end (empty = automatic).",
    "Audio / Example audio: optional clip file names (sanctions.mp3). Upload the clips in the app, or write a path",
    "relative to the 'Audio folder' you set in the app, or a full path (C:\\english\\audio\\sanctions.mp3).",
    "The item waits for its clip: the word clip plays when the word appears, the example clip with the example.",
    "",
    "In the app choose how many items go in each video and how to split: one group per video (recommended) or in",
    "sheet order. 15 political rows + 10 proverb rows at 5 per video = 3 political videos + 2 proverb videos.",
]


def write_template(path):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Items"
    ws.append(HEADERS)
    for row in EXAMPLE_ROWS:
        ws.append([row.get(h, "") for h in HEADERS])
    head = PatternFill("solid", fgColor="1F3A68")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
        c.alignment = Alignment(horizontal="center", vertical="center")
    from openpyxl.utils import get_column_letter
    for i, w in enumerate(WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "C2"
    notes = wb.create_sheet("How to fill")
    for line in HOW_TO:
        notes.append([line])
    notes.column_dimensions["A"].width = 120
    add_dropdowns(wb, ws, [(["Group"], ["General", "Political", "Proverbs", "Idioms", "Mistakes",
                                        "عام", "سياسة", "أمثال", "تعابير", "أخطاء شائعة"], False,
                            "Pick a group, or type a name of your own"),
                           (["Type"], ["word", "guess", "reverse", "mistake", "proverb", "idiom"], True,
                            "word, guess, reverse, mistake, proverb or idiom (empty = word card)"),
                           (["Correct"], ["A", "B", "C", "D", "أ", "ب", "ج", "د"], True,
                            "For guess rows: the right option, A, B, C or D")])
    wb.save(path)
    return path
