"""English Words — 📃 Word list from an Excel / CSV sheet, with the voice of every word made by ElevenLabs.

The sheet is one word per row: English | Arabic | IPA (optional) | Sample sentence (optional: shown after the word,
highlighted, read with its own clip) | Title | Subtitle (optional: written once, they go on to the next pages until
a new title; a page takes the one in effect at its first word). Headers are recognised in English or Arabic
(English / Word, Arabic / Meaning, IPA / Pronunciation); without a header row the columns are A = English,
B = Arabic, C = IPA. An optional English meaning column (English meaning / Definition /
التعريف) gives a word or idiom its meaning in English too (used by the image posts, word_posts.py). Any number of rows: `plan()` cuts them in order into pages of `per_page` words (one
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

_HEAD = {  # "def" first: "English meaning" must not be taken for the English word column
         "def": ("englishmeaning", "meaninginenglish", "meaningenglish", "englishdefinition", "definition",
                 "explanation", "enmeaning", "التعريف", "الشرح", "المعنىبالإنجليزية", "المعنىبالانجليزية",
                 "المعنىبالانكليزية"),
         "en": ("english", "word", "words", "wordphrase", "phrase", "term", "idiom", "idioms", "expression",
                "التعبير", "المصطلح", "الكلمة", "الانجليزية", "الإنجليزية", "انجليزي", "إنجليزي", "كلمة"),
         "ar": ("arabic", "meaning", "translation", "arabicmeaning", "المعنى", "العربية", "الترجمة", "عربي", "معنى"),
         "ipa": ("ipa", "pronunciation", "phonetic", "phonetics", "النطق"),
         "emoji": ("emoji", "icon", "ايموجي", "إيموجي", "رمز"),
         "ex": ("samplesentence", "sentence", "example", "examplesentence", "sample", "usage", "مثال", "جملة",
                "الجملة", "المثال"),
         # page title / subtitle (subtitle first: "العنوان الفرعي" also starts like "العنوان")
         "sub": ("subtitle", "pagesubtitle", "العنوانالفرعي", "عنوانفرعي"),
         "title": ("title", "pagetitle", "heading", "العنوان", "عنوان")}
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
        cols = {"en": 0, "ar": 1, "ipa": 2, "ex": 3, "title": 4, "sub": 5}
    words, problems = [], []
    title = sub = ""  # a title / subtitle goes on until the next one (it may also sit on a row of its own)
    for r, row in enumerate(rows[start:], start + 1):
        cell = lambda k: _clean(row[cols[k]]) if k in cols and cols[k] < len(row) else ""  # noqa: E731
        en, ar, ipa, ex = cell("en"), cell("ar"), cell("ipa"), cell("ex")
        dfn = cell("def")
        emo = cell("emoji")
        if cell("title"):
            title, sub = cell("title"), cell("sub")  # a new title starts with its own subtitle (or none)
        elif cell("sub"):
            sub = cell("sub")
        if not en and not ar:
            continue
        if not en or not ar:
            problems.append(f"row {r}: {'the English word' if not en else 'the Arabic meaning'} is empty — left out")
            continue
        # several meanings in one cell, split by "|" (متين | مُعمّر | دائم): kept apart for the image posts (`alts`),
        # joined with an Arabic comma for the videos (a "|" would split the editor's word line)
        raw = row[cols["ar"]] if "ar" in cols and cols["ar"] < len(row) else ""
        alts = [p for p in (_clean(x) for x in str(raw or "").split("|")) if p]
        if len(alts) > 1:
            ar = "، ".join(alts)
        words.append(dict(en=en, ar=ar, ipa=clean_ipa(ipa) if ipa else "", ex=ex, row=r, title=title, sub=sub,
                          **({"def": dfn} if dfn else {}), **({"emoji": emo} if emo else {}), **({"alts": alts} if len(alts) > 1 else {})))
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
    """The editor's Items text for one video. A page takes the sheet's title / subtitle in effect at its first word,
    else the ones typed in the app; {n} = the page number counted over the whole sheet."""
    items = []
    for k, page in enumerate(pages):
        n = str(first_page + k)
        t = page[0].get("title") or title or ""
        st = (page[0].get("sub") if page[0].get("title") else "") or subtitle or ""
        items.append(list_item([dict(en=w["en"], ipa=w["ipa"], ar=w["ar"], ex=w.get("ex", "")) for w in page],
                               t.replace("{n}", n), st.replace("{n}", n)))
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
    """One ElevenLabs clip per word as out_dir/w<page>_<word>.mp3 (page = item number in this video), and one per
    sample sentence as w<page>_<word>e.mp3 (read without the *stars*). Returns the clip paths. Raises
    RuntimeError with a clear message if ElevenLabs refuses."""
    ok, msg = voice_ready(data_dir)
    if not ok:
        raise RuntimeError(msg)
    s = el.load_settings(data_dir)
    cache = os.path.join(data_dir, "tts")
    os.makedirs(out_dir, exist_ok=True)
    jobs = []
    for i, page in enumerate(pages, 1):
        for k, w in enumerate(page, 1):
            jobs.append((w["en"], f"w{i}_{k}.mp3", f"“{w['en']}”"))
            if w.get("ex"):
                jobs.append((" ".join(w["ex"].replace("*", "").split()), f"w{i}_{k}e.mp3",
                             f"the sentence of “{w['en']}”"))
    paths = []
    for done, (text, name, what) in enumerate(jobs):
        if progress:
            progress(done / len(jobs), f"🎙️ Voice of {what} ({done + 1} of {len(jobs)})")
        mp3, _ = el.speak(text, cache, s)
        dst = os.path.join(out_dir, name)
        shutil.copyfile(mp3, dst)
        paths.append(dst)
    return paths


def word_voices(words, data_dir, out_dir, progress=None):
    """🎬 Words video: one ElevenLabs clip per word as out_dir/w<k>.mp3 and one per sample sentence as
    w<k>e.mp3 (k = the word's number in the video; read without the *stars*). Returns the clip paths."""
    ok, msg = voice_ready(data_dir)
    if not ok:
        raise RuntimeError(msg)
    s = el.load_settings(data_dir)
    cache = os.path.join(data_dir, "tts")
    os.makedirs(out_dir, exist_ok=True)
    jobs = []
    for k, w in enumerate(words, 1):
        jobs.append((w["en"], f"w{k}.mp3", f"“{w['en']}”"))
        if w.get("ex"):
            jobs.append((" ".join(w["ex"].replace("*", "").split()), f"w{k}e.mp3", f"the sentence of “{w['en']}”"))
    paths = []
    for done, (text, name, what) in enumerate(jobs):
        if progress:
            progress(done / len(jobs), f"🎙️ Voice of {what} ({done + 1} of {len(jobs)})")
        mp3, al = el.speak(text, cache, s)
        dst = os.path.join(out_dir, name)
        shutil.copyfile(mp3, dst)
        if name.endswith("e.mp3") and al:  # the sentence: keep when each word is spoken (the video lights it then)
            try:
                from .templates.words_video import save_timings
                words, spans, pos = text.split(), [], 0
                for wd in words:
                    a = text.index(wd, pos)
                    spans.append((a, a + len(wd)))
                    pos = a + len(wd)
                save_timings(dst, words, el.word_times(spans, text, al))
            except Exception:
                pass  # without them the words are spread over the clip
        paths.append(dst)
    return paths


def _sentence(text):
    """A phrase as a finished sentence for the voice: a full stop at the end (a phrase without one is read like an
    unfinished label — flat, robotic)."""
    text = " ".join(str(text or "").split())
    return text if not text or text[-1] in ".!?…\"'”’)" else text + "."


def phrase_jobs(items):
    """What 🃏 Idiom cards' voice reads: [(clip, text, label, before, after)] — clip 'w<k>' = the k-th card's English,
    'w<k>e' = its English meaning. Each phrase is read as a sentence, inside a context (ElevenLabs previous_text /
    next_text, not spoken): the idiom as the next item of a lesson, followed by its meaning; the meaning right after
    the idiom — so the voice sounds like a teacher presenting it, not a dictionary reading a label."""
    jobs = []
    for k, it in enumerate(items, 1):
        en, df = _sentence(it["en"]), _sentence(it.get("df") or "")
        jobs.append((f"w{k}", en, it["en"], "Here is the next one to learn.", df or None))
        if df:
            jobs.append((f"w{k}e", df, f"meaning of {it['en']}", en, None))
    return jobs


def _voice_settings(data_dir, voice_id=None):
    """The saved ElevenLabs settings, with another voice when one is given (🃏 Idiom cards' own Voice menu)."""
    s = el.load_settings(data_dir)
    if voice_id:
        s["voice_id"] = str(voice_id).strip()
    return s


def phrase_voices(items, data_dir, out_dir, progress=None, voice_id=None):
    """🃏 Idiom cards: one ElevenLabs clip per job of `phrase_jobs` as out_dir/<clip>.mp3 (the current take of each;
    cached, so a clip costs credits only once), in voice_id (empty = the saved voice). Returns the clip paths."""
    from .core import check_stop
    ok, msg = voice_ready(data_dir)
    if not ok:
        raise RuntimeError(msg)
    s = _voice_settings(data_dir, voice_id)
    cache = os.path.join(data_dir, "tts")
    os.makedirs(out_dir, exist_ok=True)
    jobs = phrase_jobs(items)
    paths = []
    for done, (clip, text, label, before, after) in enumerate(jobs):
        check_stop()  # ⏹ Stop between two clips
        if progress:
            progress(done / len(jobs), f"🎙️ Voice of “{label}” ({done + 1} of {len(jobs)})")
        mp3, _ = el.speak(text, cache, s, before, after)
        dst = os.path.join(out_dir, clip + ".mp3")
        shutil.copyfile(mp3, dst)
        paths.append(dst)
    return paths


def _take_files(job, data_dir, s):
    """(current mp3, current json, previous mp3, previous json) of a phrase job's voice with settings s."""
    clip, text, label, before, after = job
    base = os.path.join(data_dir, "tts", el.speak_key(text, s, before, after))
    return base + ".mp3", base + ".json", base + ".prev.mp3", base + ".prev.json"


def phrase_take(items, clip, data_dir, out_dir, mode="listen", voice_id=None):
    """One 🃏 Idiom cards clip ('w3' / 'w3e'): mode 'listen' = the current take if it is made (never calls
    ElevenLabs), 'make' = the current take, made if missing (charged once), 'new' = ElevenLabs reads it again (only
    this phrase is charged; the take it replaces is kept as the previous take), 'back' = swap with the previous take
    (no credits; press again to come back). voice_id = another voice than the saved one. Returns (path — the cached
    take for 'listen' / 'make', a fresh copy in out_dir otherwise — or None, has a previous take)."""
    job = next((j for j in phrase_jobs(items) if j[0] == clip), None)
    if job is None:
        raise RuntimeError("That clip is not in the cards any more.")
    return _job_take(job, data_dir, out_dir, mode, voice_id)


def _job_take(job, data_dir, out_dir, mode, voice_id, on_take=None):
    """phrase_take for one job (clip, text, label, before, after); on_take(mp3, alignment json) is called for the
    current take after it is made or swapped (📄 Torn pad keeps the word timings of a sentence)."""
    clip = job[0]
    s = _voice_settings(data_dir, voice_id)
    cm, cj, pm, pj = _take_files(job, data_dir, s)
    have = lambda m, j: os.path.isfile(m) and os.path.isfile(j)  # noqa: E731
    if mode == "new":
        ok, msg = voice_ready(data_dir)
        if not ok:
            raise RuntimeError(msg)
        if have(cm, cj):
            os.replace(cm, pm)
            os.replace(cj, pj)
        try:
            el.speak(job[1], os.path.join(data_dir, "tts"), s, job[3], job[4])
        except Exception:
            if have(pm, pj) and not have(cm, cj):  # ElevenLabs failed: keep the take we had
                os.replace(pm, cm)
                os.replace(pj, cj)
            raise
    elif mode == "make" and not have(cm, cj):
        ok, msg = voice_ready(data_dir)
        if not ok:
            raise RuntimeError(msg)
        el.speak(job[1], os.path.join(data_dir, "tts"), s, job[3], job[4])
    elif mode == "back":
        if not have(pm, pj):
            raise RuntimeError("There is no previous take of this clip yet — 🔄 New take makes one.")
        tm, tj = cm + ".swap", cj + ".swap"
        if have(cm, cj):
            os.replace(cm, tm)
            os.replace(cj, tj)
        os.replace(pm, cm)
        os.replace(pj, cj)
        if have(tm, tj):
            os.replace(tm, pm)
            os.replace(tj, pj)
    if not have(cm, cj):
        return None, have(pm, pj)
    if on_take and mode != "listen":
        on_take(cm, cj)
    if mode in ("listen", "make"):
        return cm, have(pm, pj)
    os.makedirs(out_dir, exist_ok=True)  # a fresh file: the video and the player both see the new take
    dst = os.path.join(out_dir, clip + ".mp3")
    shutil.copyfile(cm, dst)
    return dst, have(pm, pj)


# ------------------------------------------------------------------ 📄 Torn pad: two voices
def pad_jobs(items, word_by="12", sent_by="12"):
    """What 📄 Torn pad's two voices read: [(clip, text, label, before, after, voice)] — 'w<k>' / 'w<k>e' = Voice 1
    reads word k / its sentence, 'w<k>_v2' / 'w<k>e_v2' = Voice 2. The word is read as a sentence inside a context
    (not spoken, not charged) so it sounds presented, not like a label; the sentence follows the word."""
    from .templates.torn_pad import clip_name, needed, spoken
    jobs = []
    for k, kind, v in needed(items, word_by, sent_by):
        it = items[k - 1]
        word, ex = _sentence(it["en"]), spoken(it.get("ex"))
        if kind == "w":
            jobs.append((clip_name(k, "w", v), word, it["en"], "Here is the next word to learn.", ex or None, v))
        else:
            jobs.append((clip_name(k, "e", v), ex, f"sentence of {it['en']}", word, None, v))
    return jobs


def _pad_timings(text):
    """on_take for a sentence clip: keep when each word is spoken (by the audio's content, so copies find it)."""
    def fn(mp3, js):
        import json
        from .templates.words_video import save_timings
        try:
            with open(js, encoding="utf-8") as f:
                al = json.load(f)
            words, spans, pos = text.split(), [], 0
            for wd in words:
                a = text.index(wd, pos)
                spans.append((a, a + len(wd)))
                pos = a + len(wd)
            save_timings(mp3, words, el.word_times(spans, text, al))
        except Exception:
            pass  # without them the words are spread over the clip
    return fn


def _pad_voice(job, voices):
    """The voice id of a job's reader (voices = {1: id, 2: id}; empty = the saved voice)."""
    return (voices or {}).get(job[5]) or None


def pad_voices(items, data_dir, out_dir, voices=None, word_by="12", sent_by="12", skip=(), progress=None):
    """📄 Torn pad: the clips of `pad_jobs` that are not in `skip` (clip names) as out_dir/<clip>.mp3, each in its
    reader's voice (cached: a clip costs credits only once). Returns the clip paths."""
    from .core import check_stop
    ok, msg = voice_ready(data_dir)
    if not ok:
        raise RuntimeError(msg)
    jobs = [j for j in pad_jobs(items, word_by, sent_by) if j[0] not in set(skip)]
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for done, job in enumerate(jobs):
        check_stop()  # ⏹ Stop between two clips
        if progress:
            progress(done / len(jobs), f"🎙️ Voice {job[5]}: “{job[2]}” ({done + 1} of {len(jobs)})")
        on = _pad_timings(job[1]) if "e" in job[0].split("_")[0] else None
        mp3, _ = _job_take(job[:5], data_dir, out_dir, "make", _pad_voice(job, voices), on)
        dst = os.path.join(out_dir, job[0] + ".mp3")
        shutil.copyfile(mp3, dst)
        paths.append(dst)
    return paths


def pad_take(items, clip, data_dir, out_dir, mode="listen", voices=None, word_by="12", sent_by="12"):
    """phrase_take for one 📄 Torn pad clip ('w3', 'w3e_v2' …), in its reader's voice."""
    job = next((j for j in pad_jobs(items, word_by, sent_by) if j[0] == clip), None)
    if job is None:
        raise RuntimeError("That clip is not in the video any more.")
    on = _pad_timings(job[1]) if "e" in clip.split("_")[0] else None
    return _job_take(job[:5], data_dir, out_dir, mode, _pad_voice(job, voices), on)


def is_made_clip(path, data_dir):
    """True when the file is a take ElevenLabs made (a copy of a cached clip in DATA_DIR/tts), False for your own
    recording."""
    import hashlib
    try:
        size = os.path.getsize(path)
        cache = os.path.join(data_dir, "tts")
        same = [os.path.join(cache, f) for f in os.listdir(cache)
                if f.endswith(".mp3") and os.path.getsize(os.path.join(cache, f)) == size]
        if not same:
            return False
        digest = lambda f: hashlib.md5(open(f, "rb").read()).digest()  # noqa: E731
        mine = digest(path)
        return any(digest(f) == mine for f in same)
    except OSError:
        return False


TEMPLATE_ROWS = [("English", "Arabic", "IPA (optional)", "Sample sentence (optional)", "Title (optional)",
                  "Subtitle (optional)", "English meaning (optional)"),
                 ("Tip of the iceberg", "قمة جبل الجليد", "", "This scandal is only the tip of the iceberg.",
                  "Idioms You Should Know", "تعابير يجب أن تعرفها", "a small sign of a much bigger problem"),
                 ("Uphill battle", "معركة شاقة", "", "Getting the new law passed was an uphill battle.", "", "",
                  "a struggle against many difficulties"),
                 ("Cornerstone", "حجر الزاوية", "/ˈkɔːnəstəʊn/", "Trust is the cornerstone of every friendship.",
                  "", "", "the most important part of something"),
                 ("Litmus test", "المحك الحاسم", "", "The election will be a litmus test for the new party.", "",
                  "", "a test that shows clearly what something is really like"),
                 ("Wake-up call", "جرس الإنذار", "", "The storm was a wake-up call for the whole city.", "", "",
                  "an event that makes people notice a problem"),
                 ("Deadline", "موعد نهائي", "/ˈdedlaɪn/", "", "", "", "the time by which something must be done")]


# 2nd tab: a ready sheet for the 🖼️ Image posts — several Arabic meanings in one cell split by "|" (a bar between
# them on the posts; Torn paper / Clouds), an English meaning for each idiom
POSTS_ROWS = [("English", "Arabic", "IPA (optional)", "English meaning (optional)", "Title (optional)",
               "Subtitle (optional)"),
              ("Paper Tiger", "نمر من ورق | قوة ظاهرية بلا فعل", "", "something that looks strong but is weak",
               "Political Idioms", "تعابير سياسية"),
              ("Smoke-filled Room", "الغرفة المغلقة | صفقات تُعقد في السر", "",
               "a private place where secret deals are made"),
              ("Bamboo Curtain", "الستار الخيزراني | عزلة الصين الشيوعية", "",
               "the political barrier around communist China"),
              ("Scapegoat", "كبش الفداء | من يُحمّل ذنب الآخرين", "/ˈskeɪpɡəʊt/",
               "a person blamed for the mistakes of others"),
              ("Durable", "متين | مُعمّر | دائم", "/ˈdjʊərəbl/", "", "Word Power", "كلمات قوية"),
              ("Foundational", "تأسيسي | أساسي | جوهري", "/faʊnˈdeɪʃənl/", ""),
              ("Genocide", "إبادة جماعية", "/ˈdʒenəsaɪd/", ""),
              ("Infinitely", "إلى ما لا نهاية | بلا حدود", "/ˈɪnfɪnətli/", ""),
              ("Intellectual", "فكري | مُثقّف، مُفكّر", "/ˌɪntəˈlektʃuəl/", "")]


def _style_sheet(ws, rtl_cols, widths):
    from openpyxl.styles import Alignment, Font, PatternFill
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="251A66")
    for col in rtl_cols:  # the Arabic columns read right to left
        for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            for c in row:
                c.alignment = Alignment(horizontal="right", readingOrder=2)
    for col, w in zip("ABCDEFG", widths):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"


def write_template(path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Words"
    for row in TEMPLATE_ROWS:
        ws.append(list(row))
    _style_sheet(ws, (2, 6), (28, 34, 24, 60, 30, 30, 50))
    ws = wb.create_sheet("Image posts")
    for row in POSTS_ROWS:
        ws.append(list(row))
    _style_sheet(ws, (2, 6), (24, 44, 22, 46, 22, 22))
    wb.save(path)
