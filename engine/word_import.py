"""English Words — 📃 Word list from an Excel / CSV sheet, with the voice of every word made by ElevenLabs.

The sheet is one word per row: English | Arabic | IPA (optional). Headers are recognised in English or Arabic
(English / Word, Arabic / Meaning, IPA / Pronunciation); without a header row the columns are A = English,
B = Arabic, C = IPA. Any number of rows: `plan()` cuts them in order into pages of `per_page` words (one
`type: list` item each) and the pages into videos of `per_video` pages (vocab.MAX_ITEMS); only the last page / video
takes what is left. `voice_clips()` makes one clip per
word with the ElevenLabs settings saved in DATA_DIR/elevenlabs.json (cached in DATA_DIR/tts, so a word costs
credits only once) and copies it as w<page>_<word>.mp3, the names the English Words template reads."""
import os
import re
import shutil

from . import elevenlabs as el
from .batch import read_table
from .templates.vocab import LIST_MAX, MAX_ITEMS, clean_ipa, items_text, list_item

_HEAD = {"en": ("english", "word", "words", "wordphrase", "phrase", "term", "الكلمة", "الانجليزية", "الإنجليزية",
                "انجليزي", "إنجليزي", "كلمة"),
         "ar": ("arabic", "meaning", "translation", "arabicmeaning", "المعنى", "العربية", "الترجمة", "عربي", "معنى"),
         "ipa": ("ipa", "pronunciation", "phonetic", "phonetics", "النطق")}
_SEP = re.compile(r"[=|]")  # the separators of a word line in the editor: never inside a word


def _norm(s):
    return re.sub(r"[\s_/\-().:]+", "", str(s or "").strip().lower())


def _columns(row):
    """{'en': i, 'ar': i, 'ipa': i} if the row is a header row, else None."""
    found = {}
    for i, cell in enumerate(row):
        n = _norm(cell)
        for key, names in _HEAD.items():  # "IPA (optional)", "Arabic meaning" … count too
            if key not in found and n and any(n == a or (len(a) >= 3 and n.startswith(a)) for a in names):
                found[key] = i
                break
    return found if "en" in found and "ar" in found else None


def _clean(s):
    return " ".join(_SEP.sub(" ", str(s or "")).split())


def read_words(path, sheet=None):
    """([dict(en, ar, ipa, row)], [problems]) from the sheet."""
    rows = read_table(path, sheet)
    cols, start = None, 0
    for i, row in enumerate(rows[:10]):  # a header row may sit under a title row
        cols = _columns(row)
        if cols:
            start = i + 1
            break
    if cols is None:
        cols = {"en": 0, "ar": 1, "ipa": 2}
    words, problems = [], []
    for r, row in enumerate(rows[start:], start + 1):
        cell = lambda k: _clean(row[cols[k]]) if k in cols and cols[k] < len(row) else ""  # noqa: E731
        en, ar, ipa = cell("en"), cell("ar"), cell("ipa")
        if not en and not ar:
            continue
        if not en or not ar:
            problems.append(f"row {r}: {'the English word' if not en else 'the Arabic meaning'} is empty — left out")
            continue
        words.append(dict(en=en, ar=ar, ipa=clean_ipa(ipa) if ipa else "", row=r))
    return words, problems


def _chunks(seq, size):
    """seq cut in order into parts of exactly `size` (only the last part may be shorter)."""
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def plan(words, per_page=5, per_video=4):
    """[[page, page …] per video]: every page holds exactly per_page words and every video exactly per_video pages,
    in sheet order — only the last page / video takes what is left (7 words, 6 per page, 1 page per video ->
    a video of 6 words and a video of 1)."""
    per_page = max(1, min(LIST_MAX, int(per_page or 5)))
    per_video = max(1, min(MAX_ITEMS, int(per_video or 4)))
    return _chunks(_chunks(words, per_page), per_video)


def video_items(pages, title="", subtitle="", first_page=1):
    """The editor's Items text for one video. {n} in the title = the page number counted over the whole sheet."""
    items = []
    for k, page in enumerate(pages):
        n = str(first_page + k)
        items.append(list_item([dict(en=w["en"], ipa=w["ipa"], ar=w["ar"]) for w in page],
                               (title or "").replace("{n}", n), (subtitle or "").replace("{n}", n)))
    return items_text(items)


def _rows(video):
    a, b = video[0][0]["row"], video[-1][-1]["row"]
    return f"row {a}" if a == b else f"rows {a}–{b}"


def summary(words, problems, videos, per_page):
    n_pages = sum(len(v) for v in videos)
    if not words:
        return "⚠️ No words found." + (f" {problems[0]}" if problems else "")
    lines = [f"**{len(words)} words** → {n_pages} page{'s' if n_pages != 1 else ''} of {per_page} words → "
             f"**{len(videos)} video{'s' if len(videos) != 1 else ''}**"]
    if len(videos) > 1:
        lines.append(" · ".join(f"video {k}: {_rows(v)}" for k, v in enumerate(videos, 1)))
    if problems:
        lines.append(f"⚠️ {len(problems)} row{'s' if len(problems) != 1 else ''} left out: " + "; ".join(problems[:4])
                     + (" …" if len(problems) > 4 else ""))
    return "\n\n".join(lines)


def voice_ready(data_dir):
    """(ok, message) about the saved ElevenLabs settings."""
    s = el.load_settings(data_dir)
    if not s["api_key"]:
        return False, ("Add your ElevenLabs API key first: 📖 English Texts → ✍️ Paragraphs → 🔑 ElevenLabs voice "
                       "(it is saved on this computer and used here too).")
    return True, f"🎙️ Voice: **{s['voice_name'] or s['voice_id']}** (from 🔑 ElevenLabs voice in 📖 English Texts)"


def voice_clips(pages, data_dir, out_dir, progress=None):
    """One ElevenLabs clip per word as out_dir/w<page>_<word>.mp3 (page = item number in this video).
    Returns the clip paths. Raises RuntimeError with a clear message if ElevenLabs refuses."""
    ok, msg = voice_ready(data_dir)
    if not ok:
        raise RuntimeError(msg)
    s = el.load_settings(data_dir)
    cache = os.path.join(data_dir, "tts")
    os.makedirs(out_dir, exist_ok=True)
    total = sum(len(p) for p in pages) or 1
    paths, done = [], 0
    for i, page in enumerate(pages, 1):
        for k, w in enumerate(page, 1):
            if progress:
                progress(done / total, f"🎙️ Voice of “{w['en']}” ({done + 1} of {total})")
            mp3, _ = el.speak(w["en"], cache, s)
            dst = os.path.join(out_dir, f"w{i}_{k}.mp3")
            shutil.copyfile(mp3, dst)
            paths.append(dst)
            done += 1
    return paths


TEMPLATE_ROWS = [("English", "Arabic", "IPA (optional)"),
                 ("Ceasefire", "وقف إطلاق النار", "/ˈsiːsfaɪər/"),
                 ("Summit", "قمة", "/ˈsʌmɪt/"),
                 ("Treaty", "معاهدة", "/ˈtriːti/"),
                 ("Sanctions", "عقوبات", "/ˈsæŋkʃənz/"),
                 ("Election", "انتخابات", "/ɪˈlekʃən/"),
                 ("Deadline", "موعد نهائي", "")]


def write_template(path):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Words"
    for row in TEMPLATE_ROWS:
        ws.append(list(row))
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="251A66")
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for c in row:
            c.alignment = Alignment(horizontal="right", readingOrder=2)
    for col, w in zip("ABC", (28, 34, 24)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    wb.save(path)
