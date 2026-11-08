"""Video Studio — browser app for making animated Shorts.

Run:  python app.py   (opens http://127.0.0.1:7860 in your browser)
"""
import copy
import datetime as dt
import inspect
import json
import os
import shutil
import threading
import time
import zipfile

import gradio as gr

from engine.audio import INTRO_SOUNDS, MOODS, TICK_SOUNDS, sound_demo
from engine.core import COLOR_NAMES, THEME_NAMES
from engine.icons import ICON_NAMES
from engine.mcq_styles import STYLE_NAMES
from engine.timers import TIMER_FX, TIMER_NAMES
from engine.render import render_clip, render_cover, render_still, render_video
from engine.templates import TEMPLATES
from engine.header_fx import NUMBER_STYLES
from engine.layouts import LAYOUT_NAMES
from engine.quiz_fx import FX_KEYS, FX_OPTIONS
from engine.templates.mcq import HEADER_STYLES, TITLE_STYLES, narration_report, parse_questions
from engine.templates.vocab import GROUP_CHOICES, GROUPS, PACES, TYPE_CHOICES, add_item, clips_report, to_word_cards
from engine.templates.vocab import LIST_STYLES as VC_LIST_STYLES
from engine.templates.vocab import TITLE_STYLES as VC_TITLE_STYLES
from engine.templates.text import BAND_CHOICES as TX_BANDS, MARKER_CHOICES as TX_MARKERS, words_report
from engine.templates.text import LEVEL_CHOICES as TX_LEVELS, STYLE_CHOICES as TX_STYLES
from engine import batch
from engine import countries
from engine import tl_batch
from engine import userdata
from engine import fonts as fontlib
from engine import text_batch
from engine import vocab_batch
from engine.word_list import BOARD_CHOICES, CHALK_COLOR_CHOICES, HIGHLIGHTS, MARKS
from engine.know_country import video as kc_video

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_PROJ_DIR = os.path.join(ROOT, "projects")  # ships with the app: example projects + Excel templates
# Your own work lives outside the app folder (Documents/Video Studio), so a new download never deletes it.
DATA_DIR = userdata.data_dir(ROOT)
OUT_DIR = os.path.join(DATA_DIR, "outputs")
PROJ_DIR = os.path.join(DATA_DIR, "projects")
MEDIA_DIR = os.path.join(PROJ_DIR, "media")
for _d in (OUT_DIR, PROJ_DIR, MEDIA_DIR):
    os.makedirs(_d, exist_ok=True)

N_EVENTS = 5
COUNTRY_CHOICES = countries.choices()
SHARED_KEYS = [("settings", "theme"), ("settings", "language"), ("settings", "music"), ("settings", "music_gain"),
               ("settings", "music_file"), ("settings", "voice_file"), ("settings", "voice_offset"),
               ("settings", "voice_gain"), ("settings", "handle"), ("settings", "font_file"), ("settings", "fps"),
               ("ending", "intro"), ("ending", "question"), ("ending", "cta"),
               ("settings", "intro_sound"), ("settings", "tick_sound"), ("settings", "tick_gain")]
TL_KEYS = ["mode", "hook", "hide_first_in_hook", "doubt", "doubt_sub", "compare_title", "reveal", "unit",
           "maps", "guess", "guess_q", "intro", "map_style", "polish", "finish"]
EV_KEYS = ["enabled", "name", "year", "label", "color", "icon", "image", "country", "outline"]
QZ_KEYS = ["title", "subtitle", "clues", "clue_seconds", "answer_intro", "answer", "answer_sub", "answer_image", "accent"]
MQ_KEYS = ["title", "subtitle", "questions", "think_seconds", "reveal_seconds", "accent", "style", "timer",
           "colors", "narration", "narration_gain", "timer_fx", "title_style", "header_style", "fx", "number_style",
           "layout", "letters"]
VC_KEYS = ["group", "group_name", "title", "subtitle", "lesson", "lesson_n", "items", "accent", "background",
           "title_style", "hook", "pace", "guess_seconds", "timer", "timer_fx", "recap", "audio", "audio_gain",
           "list_style", "list_highlight", "chalk_board", "chalk_mark", "chalk_color"]
TX_KEYS = ["title", "subtitle", "tag", "words", "reading_audio", "audio_gain", "lead", "band", "marker", "style",
           "level", "translation"]
KEYS = {"quiz": QZ_KEYS, "mcq": MQ_KEYS, "vocab": VC_KEYS, "text": TX_KEYS}
MEDIA_FIELDS = {"music_file", "voice_file", "font_file", "image", "answer_image", "outline", "reading_audio"}
MEDIA_LISTS = {"narration", "audio"}  # fields holding several files
DEFAULTS = {"colors": "style", "narration_gain": 1.0, "timer_fx": [], "unit": "", "maps": False, "guess": False,
            "guess_q": "", "intro": "hook", "map_style": "auto", "polish": False, "finish": False,
            "intro_sound": "Bass hit", "tick_sound": "Classic", "tick_gain": 1.0, "title_style": "Fancy", "header_style": "Fancy", "fx": [], "number_style": "plain", "layout": "Standard", "letters": True,
            "group_name": "", "lesson": "", "lesson_n": 1, "accent": "group", "background": "group", "hook": False,
            "pace": "normal", "guess_seconds": 5, "timer": "Bar", "recap": True, "audio_gain": 1.0,
            "list_style": "Editorial", "list_highlight": "cream", "chalk_board": "green", "chalk_mark": "circle",
            "chalk_color": "pink", "tag": "", "lead": 1.0, "band": "teal", "marker": "yellow",
            "style": "textbook", "level": "", "translation": ""}  # for projects saved before these options existed

NARRATION_HELP = """**Read the questions aloud with your own recordings.** Name each clip after what it reads:
`q1` = question 1 · `q1a` `q1b` `q1c` `q1d` = its options (or `q1_1` … `q1_4`) · `q1e` = its explanation.
Any audio type works (mp3, wav, m4a…). Each question waits for its clips: options appear as they are read and
the countdown starts after the last one. The music gets quieter while a clip plays."""

HELP = """
### How to use
1. Pick a tab (**Timeline Collision**, **Clue Quiz**, **Multiple Choice** or **English Words**), or press **Load example** to start from a finished video.
2. Fill in the fields. They are grouped in small tabs on the left (content, 🎨 Style & sound, 🔚 Ending), so everything fits on one screen.
   The preview on the right **updates by itself** as you type. Move the time slider to check any moment.
3. Press **Render video**. The MP4 appears on the right (🎞️ Video tab) and is also saved in **Documents\\Video Studio\\outputs**.
4. **Save project** keeps everything (including your images and audio) as a `.json` file in
   **Documents\\Video Studio\\projects** that you can reopen later.
5. Your work is kept **outside the app folder** (the exact folder is shown at the top of the page), so you can replace the
   app with a new download without losing anything. Saved work found in the app's own `projects` / `outputs` folders
   (from older versions) is moved there when the app starts.

### Text tricks
- Multi-line fields: **one line per row**.
- Color a line by starting it with a tag: `[gold] text`, `[blue] text`, or any hex color like `[#ff7755] text`.
  Colors: """ + ", ".join(COLOR_NAMES) + """.

### Multiple Choice format
```
What is the largest planet?
Saturn
Jupiter *
Neptune
> It could hold more than 1,300 Earths
```
One question per block, 3 or 4 options, a `*` after the correct one, optional `>` explanation, and an empty line between questions.

**Design styles:** Classic (uses your Theme), Neon, Glass, Game Show, Paper (light), Sunset, Minimal, Luxury (black & gold), Clean Light (light), Tech HUD, Aurora, Blueprint.
**Themes:** Night Sky, Desert Night, Emerald, Deep Purple, Charcoal, Royal Blue, Ocean, Midnight Gold, Crimson, Slate, Aurora, Rose Wine, Cyber Night.
**Colours:** pick *Theme colours* (Design & timing) so any style follows your Theme; Classic always does.
**Excel batch:** in the 📊 Excel batch tab upload a sheet (get the template there), choose how many questions per video, and render all the videos at once (30 questions at 5 per video = 6 videos).
**Narration:** in the 🎙️ Narration tab upload clips named `q1` (question 1), `q1a`…`q1d` (its options) and `q1e` (its explanation). Each question waits for its clips.
**Timers:** Ring, Pie, Bar, Hourglass, Digital (00:05), Segments (battery blocks), Fuse (burning fuse and bomb, with a sizzle sound), Neon Ring, Dots, Flip Clock, Stopwatch, Liquid, Big Number.
**Timer effects** (Design & timing): Pulse on every tick, Glow, Ripple wave, Shake and Red flash in the last 3 seconds — any mix, with every timer.

### Timeline tips
- **Calendar years**: type BC years as negative numbers (2560 BC → `-2560`).
- **Years ago** mode is for deep time (dinosaurs, sharks, Earth): type `150000000` for 150 million years ago, `0` for today.
- **Number line** mode uses the same flying line for anything measurable: heights, distances, depths, temperatures, prices, speeds.
  Type plain numbers (negatives allowed, e.g. `-89.2`) and set the **Unit** (`km`, `متر`, `°C`). Put `{n}` where the number goes for units written before it: `${n}` → `$5`.
- **Countries:** pick a *Country* on an event: its name, flag (card icon) and map fill in automatically. Icon `map` shows the
  country's shape instead of the flag. Type the official area as the value (unit `كم²`).
- **🗺️ True-size map scene** (number line, values = areas): the countries are drawn at their real relative size and slide
  on top of each other, with a "× 2.1" badge. It replaces the comparison bars. Far overseas parts (e.g. French Guiana)
  are left out. Borders come from Natural Earth; upload your own *outline* (GeoJSON) to draw a country differently.
- **Map scene style:** *Overlay* (the smaller slides on top), *Tile fill* (copies of the smallest fill the largest
  while the badge counts up, for 2× to 400×), *Side by side* (on platforms, best for near-equal sizes).
  **Auto** picks: tile fill from 20× apart, side by side within 1.5×, overlay otherwise.
- **🌍 Globe intro** (about 8 s): a real-Earth globe (NASA Blue Marble) drifts in and settles on the countries, their
  borders draw on, callout tags name them one by one, then the Earth dims and each country flies into its card.
  The video gets about 5 s longer.
- **✨ Motion polish:** slow camera drift and push-ins on key moments. **🎬 Cinematic finish:** soft glow, vignette, film grain, light leaks on the hits.
  Both make rendering about 2× slower; switch them off for a quick test render.
- **⚔️ VS battle intro:** the two flags crash together with "VS" before the hook (first and last event).
- **📊 Excel batch** (Timeline tab): one row = one video. Download the template (10 ready country comparisons), edit it,
  upload it and press 🎬 Render all. Countries can be written in Arabic or English; empty hook / reveal cells are
  written automatically; card colours follow each country's flag.
- **🤔 Guess moment:** before the answer, 3 choices (× ratio) and a 3-second timer, so viewers comment their guess.
- 2 to 5 events; they are sorted by value automatically. The shortest gap gets the glowing highlight.
- Leave *Card subtitle* empty to show the year (or value with its unit) automatically.

### English Words tips
- Pick a **group** (General words, Political words, Proverbs, Idioms, Common mistakes or your own): it sets the badge,
  colour and background theme. Political words show the example as a **BREAKING NEWS** headline.
- Items are blocks of `key: value` lines (see the help above the Items box). Types: word card, guess the meaning,
  reverse guess, common mistake, proverb (with the Arabic equivalent) and idiom. Mix them freely.
- `ipa:` shows the pronunciation next to a 🔊 icon; upload clips `w1`, `w1e` in 🎙️ Audio to play your own voice.
- The word is highlighted in the example automatically; `*stars*` choose other words.
- Every render also saves a **cover picture** next to the video. 5 items ≈ 60 s at Normal pace; the preview warns
  above 60 s (Facebook Reels).
- **📊 Excel batch:** one item per row, one video per group (or in sheet order), lesson numbers count up.
- **Word list page** (`type: list`): up to 6 words with their Arabic meanings on one page, read one after another
  with clips `w1_1`, `w1_2` … — the word being read lights up. Two designs in ⏱️ Design & timing: **Editorial**
  (magazine page, 6 highlight colours) and **Chalkboard** (hand-written chalk; board, mark and chalk colour).
  In Excel: Type = list, one word per row with its Audio; "Words per list page" sets how many go on one page.

### English Texts tips
- Every tab of the workbook is one paragraph = one video. One spoken word per row: **B** word, **C** start, **D** end
  (the word timings from ElevenLabs), **E** highlighted words, **F** Arabic translation, and a **title** column.
- Upload the recordings (ElevenLabs names are fine: each goes to the tab whose reading length it matches; a file
  named like a tab, e.g. `paragraph1.mp3`, always goes to that tab), then 🎬 Render all — or 📥 load one tab to check it.
- A phrase: write the same text (e.g. `chase away`) in E on each of its rows; it flies as one piece.
- Four designs (⏱️ Design): Textbook page, Night studio, Exam passage (line numbers, red pen, LEARNED stamp), Notebook
  (handwriting, sticky notes). Lines are justified like a book (long words are hyphenated when it helps).
- Optional per tab: `level` (A1–C2 badge) and `paragraph translation` (Arabic translation shown after the reading).
- The text is sized to fill the Shorts safe area; long paragraphs turn into pages (the voice waits for the page
  turn) and end with a Word Bank recap. Each render also saves a cover picture.

### Sound
- Built-in music moods are generated, so there are no copyright issues. You can also upload your own music file.
- Upload a **voiceover** (mp3/wav/m4a): the music automatically lowers while you speak, and the video gets longer if your voice is longer.

### Previewing before you render
- The preview picture **updates automatically** whenever you change anything, and the **Preview time** slider always spans the
  whole video. Untick **Live update** if your computer is slow, then use **🔄 Refresh**.
- If a field is half-typed (for example a question without options), the last good picture stays and a ⚠️ note explains what is missing.
- **▶️ Quick motion** makes a small 6-second clip, with sound, starting at the slider time. It's ready in a few seconds, so you can check the animation and timer before the full render.
- **🎬 Render video** makes the final full-quality MP4.

### Shorts safe zone
Tick **Safe zone** under the preview: red areas are covered by YouTube/TikTok buttons and captions, so keep important text out of them.
"""


# ------------------------------------------------------------------ project <-> UI values
def project_to_values(p, tpl):
    vals = []
    for sec, k in SHARED_KEYS:
        vals.append(p.get(sec, {}).get(k, DEFAULTS.get(k)))
    if tpl == "timeline":
        d = p.get("timeline", {})
        vals += [d.get(k, DEFAULTS.get(k)) for k in TL_KEYS]
        evs = d.get("events", [])
        for i in range(N_EVENTS):
            ev = evs[i] if i < len(evs) else {}
            for k in EV_KEYS:
                v = ev.get(k)
                if k == "enabled":
                    v = bool(ev) and ev.get("enabled", True)
                if k in MEDIA_FIELDS:
                    v = v if v and os.path.isfile(v) else None
                vals.append(v if v is not None else ("" if k in ("name", "label", "country") else None))
    else:
        d = p.get(tpl, {})
        for k in KEYS[tpl]:
            v = d.get(k, DEFAULTS.get(k))
            if k in MEDIA_FIELDS:
                v = v if v and os.path.isfile(v) else None
            elif k in MEDIA_LISTS:
                v = [f for f in (v or []) if f and os.path.isfile(f)] or None
            vals.append(v)
    for i, (sec, k) in enumerate(SHARED_KEYS):
        if k in MEDIA_FIELDS and not (vals[i] and os.path.isfile(vals[i])):
            vals[i] = None
    return vals


def values_to_project(tpl, vals):
    vals = list(vals)
    p = {"template": tpl, "settings": {}, "ending": {}}
    for (sec, k), v in zip(SHARED_KEYS, vals[:len(SHARED_KEYS)]):
        p[sec][k] = v
    rest = vals[len(SHARED_KEYS):]
    if tpl == "timeline":
        d = dict(zip(TL_KEYS, rest[:len(TL_KEYS)]))
        ev_vals = rest[len(TL_KEYS):]
        d["events"] = []
        for i in range(N_EVENTS):
            ev = dict(zip(EV_KEYS, ev_vals[i * len(EV_KEYS):(i + 1) * len(EV_KEYS)]))
            if ev.get("enabled") and (str(ev.get("name") or "").strip() or ev.get("country")):
                d["events"].append(ev)
        p["timeline"] = d
    else:
        p[tpl] = dict(zip(KEYS[tpl], rest[:len(KEYS[tpl])]))
    s = p["settings"]
    s["fps"] = int(s.get("fps") or 30)
    return p


def _keep_media(path):
    if not path or not os.path.isfile(path):
        return ""
    if os.path.dirname(os.path.abspath(path)) == MEDIA_DIR:
        return path
    dst = os.path.join(MEDIA_DIR, os.path.basename(path))
    base, ext = os.path.splitext(dst)
    n = 1
    while os.path.exists(dst):
        dst = f"{base}_{n}{ext}"
        n += 1
    shutil.copy2(path, dst)
    return dst


def _keep_media_list(paths, folder):
    """Copy a group of files into one sub-folder of projects/media, keeping their names (they carry meaning)."""
    out = []
    for path in paths or []:
        if not path or not os.path.isfile(path):
            continue
        if os.path.abspath(path).startswith(MEDIA_DIR + os.sep):
            out.append(path)
            continue
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, os.path.basename(path))
        shutil.copy2(path, dst)
        out.append(dst)
    return out


def _msg(e):
    """Plain text of an exception (gr.Error keeps its text in .message)."""
    return str(getattr(e, "message", None) or e)


def _where(path):
    """Full path for messages (your work is outside the app folder)."""
    return os.path.abspath(path)


def _stamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


# ------------------------------------------------------------------ one video job at a time per browser tab
_jobs = {}
_jobs_lock = threading.Lock()
JOB_TIMEOUT = 3 * 3600  # a job that never reported back stops blocking after this many seconds


def _job_key(request):
    return getattr(request, "session_hash", None) or "local"


def _claim(request):
    now = time.time()
    with _jobs_lock:
        key = _job_key(request)
        if key in _jobs and now - _jobs[key] < JOB_TIMEOUT:
            return False
        _jobs[key] = now
        return True


def _release(request):
    with _jobs_lock:
        _jobs.pop(_job_key(request), None)


def _zip_videos(paths, out_dir):
    """Pack the finished videos into one .zip next to them (stored, not re-compressed: MP4 is already compressed)."""
    path = os.path.join(out_dir, os.path.basename(os.path.normpath(out_dir)) + ".zip")
    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for p in paths:
            z.write(p, os.path.basename(p))
            cover = os.path.splitext(p)[0] + " cover.png"
            if os.path.isfile(cover):
                z.write(cover, os.path.basename(cover))
    os.replace(tmp, path)
    return path


def _zip_update(paths, out_dir):
    try:
        zp = _zip_videos(paths, out_dir)
    except Exception as e:  # the videos themselves are fine; only the zip failed
        gr.Warning(f"Could not make the .zip: {_msg(e)}")
        return gr.update(value=None, visible=False)
    n = len(paths)
    return gr.update(value=zp, visible=True, label=f"📦 Download all {n} video{'s' if n != 1 else ''} (.zip)")


def _stream_batch(request, plan, progress):
    """Render a batch one video at a time and yield after each one, so every finished video shows up in the
    "Rendered videos" list (and the player) right away instead of only when the whole batch is done.

    plan() -> (out_dir, total, jobs) where jobs yields (file name without extension, project).
    Yields (player, message, files, zip, busy, tabs, clip, render, go) for the outputs of the batch button;
    the zip of all finished videos is offered at the end (also after an error, with the ones that finished)."""
    done, out_dir = [], None
    keep = (gr.update(),) * 5  # still working: leave busy / tabs / buttons as start() set them
    unlock = (False, gr.update(selected="vid"), gr.update(interactive=True), gr.update(interactive=True),
              gr.update(interactive=True))
    try:
        out_dir, total, jobs = plan()
        where = _where(out_dir)
        for k, (name, project) in enumerate(jobs, 1):
            with open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(project, f, ensure_ascii=False, indent=2)
            out = os.path.join(out_dir, name + ".mp4")
            progress((k - 1) / total, desc=f"Video {k} of {total}: preparing…")

            def cb(x, k=k):
                try:
                    progress((k - 1 + x) / total, desc=f"Video {k} of {total}: rendering frames…")
                except Exception:
                    pass
            render_video(project, out, cb)
            _save_cover(project, out)
            done.append(out)
            if k < total:
                yield (out, f"✅ {k} of {total} finished — download them below while video {k + 1} renders… "
                            f"(saved in `{where}`)", gr.update(value=list(done), visible=True), gr.update(), *keep)
        msg = (f"✅ {total} video{'s' if total != 1 else ''} saved in `{where}`"
               + (" — the player shows the last one" if total > 1 else ""))
        yield (done[-1], msg, gr.update(value=list(done), visible=True), _zip_update(done, out_dir), *unlock)
    except Exception as e:
        gr.Warning(_msg(e))
        got = f" ({len(done)} finished before the error)" if done else ""
        yield (done[-1] if done else gr.update(), f"⚠️ {_msg(e)}{got}",
               gr.update(value=list(done) or None, visible=bool(done)),
               _zip_update(done, out_dir) if done else gr.update(value=None, visible=False), *unlock)
    finally:
        _release(request)


def _save_cover(project, video_path):
    """Templates with a cover frame (English Words) also get '<video name> cover.png' next to the MP4,
    ready to upload as the Shorts / Reels thumbnail. A failed cover never fails the video."""
    try:
        return render_cover(project, os.path.splitext(video_path)[0] + " cover.png")
    except Exception:
        return None


def _progress_on(dep, comp):
    """Show the batch progress bar only on `comp` (not over the list of finished videos) when Gradio allows it."""
    try:
        ok = "show_progress_on" in inspect.signature(dep.success).parameters
    except (TypeError, ValueError):
        ok = False
    return {"show_progress_on": [comp]} if ok else {}


# ------------------------------------------------------------------ actions
def make_actions(tpl):
    def preview(t, safe, *vals):
        try:
            img, dur = render_still(values_to_project(tpl, vals), t, safe, cached=True)
        except Exception as e:
            raise gr.Error(str(e))
        msg = f"Video length: **{dur:.1f} s**"
        if tpl in ("vocab", "text") and dur > 60:
            msg += " — ⚠️ over 60 s: fine for YouTube Shorts and Instagram Reels, but keep Facebook Reels under 60 s"
        return img, msg, gr.update(maximum=max(1.0, round(dur, 1)))

    def clip(t, *vals):
        try:
            out = os.path.join(OUT_DIR, "_preview.mp4")
            _, dur = render_clip(values_to_project(tpl, vals), out, t, 6.0)
        except Exception as e:
            raise gr.Error(str(e))
        return out, f"Motion preview from {float(t):.1f} s (video length **{dur:.1f} s**)"

    def render(*vals, progress=gr.Progress()):
        try:
            project = values_to_project(tpl, vals)
            out = os.path.join(OUT_DIR, f"{tpl}_{_stamp()}.mp4")
            progress(0, desc="Preparing sound…")

            def cb(x):
                try:
                    progress(x, desc="Rendering frames…")
                except Exception:
                    pass
            render_video(project, out, cb)
            cover = _save_cover(project, out)
        except Exception as e:
            raise gr.Error(str(e))
        return out, f"✅ Video saved to `{_where(out)}`" + (" (+ cover picture)" if cover else "")

    def save(*vals):
        p = values_to_project(tpl, vals)
        for k in ("music_file", "voice_file"):
            p["settings"][k] = _keep_media(p["settings"].get(k))
        font = p["settings"].get("font_file") or ""  # a font name from the library, or (older projects) a file
        p["settings"]["font_file"] = _keep_media(font) if os.path.isfile(font) else font
        if tpl == "timeline":
            for ev in p["timeline"]["events"]:
                ev["image"] = _keep_media(ev.get("image"))
                ev["outline"] = _keep_media(ev.get("outline"))
        elif tpl == "quiz":
            p["quiz"]["answer_image"] = _keep_media(p["quiz"].get("answer_image"))
        elif tpl == "text":
            p["text"]["reading_audio"] = _keep_media(p["text"].get("reading_audio"))
        stamp = _stamp()
        if tpl == "vocab":
            p["vocab"]["audio"] = _keep_media_list(p["vocab"].get("audio"), os.path.join(MEDIA_DIR, f"words_audio_{stamp}"))
        if tpl == "mcq":
            p["mcq"]["narration"] = _keep_media_list(p["mcq"].get("narration"),
                                                     os.path.join(MEDIA_DIR, f"narration_{stamp}"))
        path = os.path.join(PROJ_DIR, f"{tpl}_{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        return f"💾 Project saved to `{_where(path)}`"

    def load(file):
        path = file if isinstance(file, str) else getattr(file, "name", None)
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        if p.get("template", "timeline") != tpl:
            raise gr.Error(f"This is a '{p.get('template')}' project — open it in its own tab.")
        # pictures / audio that moved (older versions kept them inside the app folder): find them by name
        userdata.relink(p, MEDIA_DIR, MEDIA_FIELDS | MEDIA_LISTS)
        return project_to_values(p, tpl)

    def example():
        return project_to_values(copy.deepcopy(TEMPLATES[tpl][2]), tpl)

    return preview, render, save, load, example, clip


# ------------------------------------------------------------------ UI
# One-page layout: editor sections in tabs on the left (each scrolls on its own if it is too tall),
# the live preview with all playback / render controls fixed on the right.
CSS = """
.gradio-container {max-width: 100% !important; padding: 4px 14px !important;}
footer {display: none !important;}
#app-title h2 {margin: 0; font-size: 1.2rem;}
.pane {max-height: calc(100vh - 225px); overflow-y: auto !important; overflow-x: hidden; flex-wrap: nowrap !important;
       padding-right: 6px;}
.pane > * {flex-shrink: 0 !important;}
.preview-col {position: sticky; top: 4px; align-self: flex-start; gap: 8px !important;}
.preview-col .row {gap: 8px !important;}
.preview-col .tabitem {padding: 4px 0 0 0 !important;}
.opt-row {align-items: center;}
.opt-row label {padding: 4px 6px !important; white-space: nowrap;}
.compact-btn button, button.compact-btn {min-width: 0 !important;}
button {user-select: none; -webkit-user-select: none;}
.info-line {height: 24px; overflow: hidden;}
.info-line p {margin: 0 !important; font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
@media (max-width: 900px) { .pane {max-height: none;} .preview-col {position: static;} }
.font-gal .thumbnail-item {aspect-ratio: 3 / 1 !important; height: auto !important;}  /* cards are 900 x 300 */
.font-gal .grid-wrap {height: auto !important; max-height: 640px;}
"""
PREVIEW_H = "calc(100vh - 404px)"


def project_bar():
    with gr.Row(equal_height=True):
        ex_btn = gr.Button("✨ Load example", size="sm", elem_classes="compact-btn")
        open_btn = gr.UploadButton("📂 Open project", file_types=[".json"], size="sm", elem_classes="compact-btn")
        save_btn = gr.Button("💾 Save project", size="sm", elem_classes="compact-btn")
    return dict(ex=ex_btn, open=open_btn, save=save_btn)


def style_tab():
    with gr.Tab("🎨 Style & sound"):
        with gr.Column(elem_classes="pane"):
            with gr.Row():
                theme = gr.Dropdown(THEME_NAMES, value="Night Sky", label="Theme")
                lang = gr.Radio([("العربية", "ar"), ("English", "en")], value="ar", label="Language of auto texts")
                fps = gr.Radio([30, 60], value=30, label="FPS")
            handle = gr.Textbox(value="@Ma3loomaFast", label="Channel handle (ending)")
            font = font_picker()
            font_file = font["font"]
            with gr.Row():
                music = gr.Dropdown(MOODS, value="Tension", label="Built-in music",
                                    info="Quiz Show, Bright Pop, Lo-fi Chill, Epic, Ambient = real chords and drums")
                music_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Music volume")
            with gr.Row():
                intro_sound = gr.Dropdown(INTRO_SOUNDS, value="Bass hit", label="Opening sound")
                tick_sound = gr.Dropdown(TICK_SOUNDS, value="Classic", label="Ticking sound")
                tick_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Ticking volume")
            with gr.Row(equal_height=True):
                listen = gr.Button("🔊 Listen: opening + music + ticking", scale=1, min_width=200)
                demo = gr.Audio(label="Sound preview", autoplay=True, interactive=False, scale=2)
            with gr.Row():
                voice_offset = gr.Number(value=0.5, label="Voice starts at (seconds)")
                voice_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Voice volume")
            with gr.Row():
                music_file = gr.Audio(type="filepath", label="Or your own music (optional)")
                voice_file = gr.Audio(type="filepath", label="Voiceover (optional)")
    def play(music_, gain_, file_, intro_, tick_, tgain_):
        settings = dict(music=music_, music_gain=gain_, music_file=file_, intro_sound=intro_, tick_sound=tick_,
                        tick_gain=tgain_)
        for old in os.listdir(OUT_DIR):  # keep only the newest sample
            if old.startswith("_sound_preview_"):
                try:
                    os.remove(os.path.join(OUT_DIR, old))
                except OSError:
                    pass
        return sound_demo(settings, os.path.join(OUT_DIR, f"_sound_preview_{_stamp()}.wav"))
    listen.click(play, [music, music_gain, music_file, intro_sound, tick_sound, tick_gain], demo)
    return dict(theme=theme, lang=lang, fps=fps, handle=handle, font_file=font_file, music=music,
                music_gain=music_gain, music_file=music_file, voice_offset=voice_offset, voice_gain=voice_gain,
                voice_file=voice_file, intro_sound=intro_sound, tick_sound=tick_sound, tick_gain=tick_gain)


FONT_HELP = """**Pick a font by clicking its card** — the live preview switches to it. Each card shows the font
writing your own sample text. ✓ عربي / English tell what a font can write; anything it can't (e.g. English words in an
Arabic-only font, or Quran marks) is drawn in Cairo automatically. Add your own fonts: point to your fonts folder
(sub-folders too) and press 🔄, or drop .ttf / .otf files below."""
FONT_SHOW = [("All", "all"), ("Arabic", "arabic"), ("English", "english"), ("My fonts", "mine")]


def font_picker():
    """Font dropdown + a clickable gallery of every font (built-in, added and the user's own folder)."""
    sample_ar0, sample_en0 = "اختبر معلوماتك! ١٢٣", "Test your knowledge 123"
    with gr.Accordion("🔤 Font — preview and pick", open=False):
        gr.Markdown(FONT_HELP)
        font = gr.Dropdown(fontlib.choices(), value="", allow_custom_value=True, label="Font",
                           info="Cairo is the default. Weights (Black, Bold…) come from the font family itself.")
        with gr.Row():
            ar = gr.Textbox(value=sample_ar0, label="Arabic sample", rtl=True)
            en = gr.Textbox(value=sample_en0, label="English sample")
        with gr.Row():
            query = gr.Textbox(label="Search fonts", placeholder="Tajawal, Kufi…", scale=2)
            only = gr.Radio(FONT_SHOW, value="all", label="Show", scale=3)
        gal = gr.Gallery(fontlib.gallery(sample_ar0, sample_en0), columns=2, height=560, object_fit="contain",
                         allow_preview=False, show_label=True, label="Click a font to use it", elem_classes="font-gal")
        with gr.Row(equal_height=True):
            folder = gr.Textbox(value=fontlib.get_folder(), label="My fonts folder (on this computer)",
                                placeholder=r"C:\Users\me\Documents\Fonts", scale=3)
            scan = gr.Button("🔄 Scan folder", scale=1, min_width=130)
        add = gr.File(file_count="multiple", file_types=[".ttf", ".otf"], label="…or add font files (.ttf / .otf)",
                      height=110)
        info = gr.Markdown(f"{len(fontlib.families())} fonts available.")

    def shown(q, only_):
        return [name for _, name in fontlib.gallery("", "", q, only_, limit=60)]

    def refresh(a, e, q, only_, sel):
        return fontlib.gallery(a, e, q, only_, selected=sel or "")

    def pick(q, only_, evt: gr.SelectData):
        names = shown(q, only_)
        name = names[evt.index] if 0 <= evt.index < len(names) else ""
        return "" if name == fontlib.DEFAULT_NAME else name

    def rescan(path, a, e, q, only_, sel):
        path = fontlib.set_folder(path)
        if path and not os.path.isdir(path):
            msg = f"⚠️ Folder not found: `{path}`"
        else:
            fontlib.families(refresh=True)
            mine = sum(1 for f in fontlib.families() if f["source"] == "folder")
            msg = f"✅ {len(fontlib.families())} fonts available" + (f" — {mine} from your folder." if path else ".")
        return gr.update(choices=fontlib.choices()), refresh(a, e, q, only_, sel), msg

    def added(files, a, e, q, only_, sel):
        n = fontlib.add_files(files)
        fontlib.families(refresh=True)
        return (gr.update(choices=fontlib.choices()), refresh(a, e, q, only_, sel),
                f"✅ Added {n} font file{'s' if n != 1 else ''} — they stay in the app (Documents › Video Studio › fonts).",
                None)

    look = [ar, en, query, only, font]
    gr.on(triggers=[ar.change, en.change, query.change, only.change, font.change], fn=refresh, inputs=look,
          outputs=gal, trigger_mode="always_last", show_progress="hidden")
    gal.select(pick, [query, only], font)
    scan.click(rescan, [folder] + look, [font, gal, info])
    folder.submit(rescan, [folder] + look, [font, gal, info])
    add.upload(added, [add] + look, [font, gal, info, add])
    return dict(font=font)


def ending_tab(note=""):
    with gr.Tab("🔚 Ending"):
        with gr.Column(elem_classes="pane"):
            gr.Markdown("**Ending card** — teases the next episode" + (f"\n\n{note}" if note else ""))
            e_intro = gr.Textbox(label="Small intro line", rtl=True)
            e_q = gr.Textbox(lines=3, max_lines=4, label="Question (1–3 lines, tags allowed)", rtl=True)
            e_cta = gr.Textbox(label="Call to action", rtl=True)
    return e_intro, e_q, e_cta


def shared_fields(st, ending):
    """Shared controls in SHARED_KEYS order."""
    return [st["theme"], st["lang"], st["music"], st["music_gain"], st["music_file"], st["voice_file"],
            st["voice_offset"], st["voice_gain"], st["handle"], st["font_file"], st["fps"], *ending,
            st["intro_sound"], st["tick_sound"], st["tick_gain"]]


def preview_panel(tpl):
    """Right column: live picture / video, time slider and all render buttons — always visible."""
    preview, render, save, load, example, clip = make_actions(tpl)
    with gr.Column(scale=2, min_width=340, elem_classes="preview-col"):
        with gr.Tabs(selected="pic") as out_tabs:
            with gr.Tab("🖼️ Live preview", id="pic"):
                img = gr.Image(label="Preview", type="pil", format="png", height=PREVIEW_H, show_label=False,
                               interactive=False)
            with gr.Tab("🎞️ Video", id="vid"):
                vid = gr.Video(label="Video", height=PREVIEW_H, show_label=False, autoplay=True)
        with gr.Row(equal_height=True, elem_classes="opt-row"):
            safe = gr.Checkbox(value=False, label="Safe zone", container=False, min_width=110)
            auto = gr.Checkbox(value=True, label="Live update", container=False, min_width=110)
            pv_btn = gr.Button("🔄 Refresh", size="sm", min_width=90)
        t = gr.Slider(0, 60, value=3.0, step=0.1, label="Preview time (s)")
        with gr.Row(equal_height=True):
            clip_btn = gr.Button("▶️ Quick motion (6 s)", min_width=130)
            rd_btn = gr.Button("🎬 Render video", variant="primary", min_width=130)
        info = gr.Markdown(elem_classes="info-line")
        busy = gr.State(False)  # True while a clip / video is being made
    return dict(busy=busy, img=img, vid=vid, tabs=out_tabs, t=t, safe=safe, auto=auto, pv=pv_btn, clip=clip_btn, rd=rd_btn,
                info=info, fns=(preview, render, save, load, example, clip))


def wire(proj, pv, fields):
    preview, render, save, load, example, clip = pv["fns"]
    pv_in = [pv["t"], pv["safe"]] + fields
    pv_out = [pv["img"], pv["info"], pv["t"], pv["tabs"]]

    def show_picture(*args):
        return (*preview(*args), gr.update(selected="pic"))

    def auto_preview(on, busy, *args):
        if not on:
            return gr.update(), gr.update(), gr.update(), gr.update()
        try:
            img, msg, slider, tab = show_picture(*args)
        except Exception as e:  # half-typed input: keep the last good picture
            return gr.update(), (gr.update() if busy else f"⚠️ {_msg(e)}"), gr.update(), gr.update()
        if busy:  # keep the video tab and the progress message while rendering
            return img, gr.update(), slider, gr.update()
        return img, msg, slider, tab

    btns = [pv["clip"], pv["rd"]]
    start_out = [pv["busy"], pv["tabs"], *btns, pv["info"]]
    work_out = [pv["vid"], pv["info"], pv["busy"], pv["tabs"], *btns]

    def start(label):
        def fn(request: gr.Request):
            if not _claim(request):  # double-click / second press while a video is being made
                raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
            return (True, gr.update(selected="vid"), gr.update(interactive=False), gr.update(interactive=False),
                    f"⏳ {label}… You can keep editing; it uses the settings from when you pressed the button.")
        return fn

    def run(fn, request, *args, **kw):
        """Run clip/render; whatever happens, unlock the buttons and say how it went."""
        try:
            out, msg = fn(*args, **kw)
            return out, msg, False, gr.update(selected="vid"), gr.update(interactive=True), gr.update(interactive=True)
        except Exception as e:
            gr.Warning(_msg(e))
            return (gr.update(), f"⚠️ {_msg(e)}", False, gr.update(selected="pic"), gr.update(interactive=True),
                    gr.update(interactive=True))
        finally:
            _release(request)

    def do_clip(request: gr.Request, *args):
        return run(clip, request, *args)

    def do_render(request: gr.Request, *args, progress=gr.Progress()):
        return run(render, request, *args, progress=progress)

    gr.on(triggers=[c.change for c in [pv["t"], pv["safe"], pv["auto"]] + fields], fn=auto_preview,
          inputs=[pv["auto"], pv["busy"]] + pv_in, outputs=pv_out, trigger_mode="always_last", show_progress="hidden")
    proj["ex"].click(example, None, fields)
    proj["open"].upload(load, proj["open"], fields)
    proj["save"].click(save, fields, pv["info"])
    pv["pv"].click(show_picture, pv_in, pv_out)
    # start() answers instantly (no queue) and refuses a second press; the work step always unlocks the buttons.
    pv["clip"].click(start("Making the 6-second motion preview"), None, start_out, queue=False) \
        .success(do_clip, [pv["t"]] + fields, work_out)
    pv["rd"].click(start("Rendering the full video"), None, start_out, queue=False) \
        .success(do_render, fields, work_out)


# ------------------------------------------------------------------ Excel batch (Multiple Choice)
COUNT_NOTE = ("Write `{count}` where the number of questions should appear — e.g. "
              "`حصلت عليها من {count}؟` — it becomes 5 in a 5-question video and 3 in a 3-question one. "
              "It also works in the Title and Subtitle.")

BATCH_HELP = """**Make many videos from one spreadsheet.** One question per row with the columns
`Question · Option A–D · Correct · Explanation` and, optionally, `Difficulty` (Easy / Medium / Hard — shows a
badge with stars) and `Question audio · A–D audio · Explanation audio`
(English or Arabic headers — get the **template** on the right). Every video uses the design, timer, music and ending
you set in the other tabs. In the title, `{n}` becomes the video number and `{total}` the number of videos
(leave it empty to use the Title from 📝 Questions)."""


def _template_path():
    path = os.path.join(APP_PROJ_DIR, "questions_template.xlsx")
    if not os.path.isfile(path):
        try:
            items = parse_questions(TEMPLATES["mcq"][2]["mcq"]["questions"])
            batch.write_template(path, [dict(it, n=i) for i, it in enumerate(items, 1)])
        except Exception:  # openpyxl missing: no template button
            return None
    return path


def batch_tab():
    with gr.Row(equal_height=True):
        gr.Markdown(BATCH_HELP)
        tpl = _template_path()
        gr.DownloadButton("⬇️ Excel template", value=tpl, visible=bool(tpl), size="sm", min_width=130, scale=0)
    with gr.Row():
        sheet = gr.File(type="filepath", file_types=[".xlsx", ".xlsm", ".csv"], label="Questions sheet (.xlsx or .csv)",
                        height=120)
        clips = gr.File(file_count="multiple", type="filepath", file_types=["audio"], height=120,
                        label="Audio clips named in the sheet (optional)")
    folder = gr.Textbox(label="…or the folder on this computer that holds the clips (optional)",
                        placeholder=r"C:\quiz\audio")
    tab, start, count = sheet_controls("questions")
    with gr.Row():
        per = gr.Slider(1, batch.MAX_PER_VIDEO, value=5, step=1, label="Questions per video")
        title = gr.Textbox(label="Title of each video (optional)", rtl=True,
                           placeholder="اختبر معلوماتك — الجزء {n} من {total}")
    with gr.Row(equal_height=True):
        info = gr.Markdown("Upload a sheet to see how many videos it makes.")
        go = gr.Button("🎬 Render all videos", variant="primary", interactive=False, min_width=230, scale=0)
    zipb = gr.DownloadButton("📦 Download all (.zip)", visible=False, variant="primary")
    files = gr.File(label="Rendered videos — each one appears here as soon as it finishes", file_count="multiple",
                    visible=False, height=320)
    with gr.Row(equal_height=True):
        part = gr.Dropdown([], label="Preview one video in the editor", scale=2)
        load = gr.Button("📥 Load into editor", scale=1, min_width=120)
    return dict(sheet=sheet, clips=clips, folder=folder, per=per, title=title, info=info, part=part, load=load,
                go=go, files=files, zip=zipb, tab=tab, start=start, count=count)


def sheet_controls(what="questions"):
    """Which tab of the workbook, and which of its rows, a batch uses."""
    one = what[:-1]
    with gr.Row():
        tab = gr.Dropdown([], label="Sheet (tab)", visible=False, scale=2,
                          info="The workbook's tabs — pick the one that holds your " + what + ".")
        start = gr.Number(value=1, precision=0, minimum=1, label=f"Start at {one} #", scale=1,
                          info=f"1 = the first {one} in the tab")
        count = gr.Number(value=0, precision=0, minimum=0, label=f"How many {what}", scale=1,
                          info="0 = all of them (from the start one)")
    return tab, start, count


def fill_tabs(sheet):
    """After an upload: list the workbook's tabs (hidden for a CSV file)."""
    names = batch.sheet_names(sheet) if sheet else []
    return gr.update(choices=names, value=names[0] if names else None, visible=len(names) > 1)


def range_note(items, what, start, count):
    s = max(1, int(start or 1))
    if s == 1 and not int(count or 0):
        return ""
    if not items:
        return f"_Nothing from {what[:-1]} #{s} on._\n\n"
    return f"_Using {what} {s}–{s + len(items) - 1}._\n\n"


def _read_batch(sheet, clips, folder, tab=None, start=1, count=0):
    if not sheet:
        raise ValueError("Upload a questions sheet first.")
    return batch.load_sheet(sheet, clips or [], folder or "", tab, start, count)


def wire_batch(xl, pv, fields, m_qs, m_narr, m_title):
    inputs = [xl["sheet"], xl["clips"], xl["folder"], xl["per"], xl["tab"], xl["start"], xl["count"]]

    def check(sheet, clips, folder, per, tab, start, count):
        off = gr.update(value="🎬 Render all videos", interactive=False)
        if not sheet:
            return "Upload a sheet to see how many videos it makes.", gr.update(choices=[], value=None), off
        try:
            items, problems = _read_batch(sheet, clips, folder, tab, start, count)
        except Exception as e:
            return f"⚠️ {_msg(e)}", gr.update(choices=[], value=None), off
        parts = batch.split(items, per)
        choices = [(f"Video {k} — {len(p)} questions (rows {p[0]['row']}–{p[-1]['row']})", k)
                   for k, p in enumerate(parts, 1)]
        n = len(parts)
        go = gr.update(value=f"🎬 Render all {n} video{'s' if n != 1 else ''}" if n else "🎬 Render all videos",
                       interactive=bool(n))
        return (range_note(items, "questions", start, count) + batch.summary(items, problems, per),
                gr.update(choices=choices, value=1 if choices else None), go)

    def load_part(sheet, clips, folder, per, tab, start, count, k, title_tpl, cur_title):
        try:
            items, _ = _read_batch(sheet, clips, folder, tab, start, count)
            parts = batch.split(items, per)
            k = int(k or 1)
            if not 1 <= k <= len(parts):
                raise ValueError("Pick a video to preview.")
            chunk = parts[k - 1]
            narr = batch.narration_files(chunk, os.path.join(OUT_DIR, "_batch_preview", f"video_{k:02d}"))
        except Exception as e:
            raise gr.Error(_msg(e))
        new_title = batch.fill_title(title_tpl, k, len(parts)) if str(title_tpl or "").strip() else cur_title
        gr.Info(f"Video {k} of {len(parts)} is in the editor. 🎬 Render video makes only this one — "
                f"use 🎬 Render all in 📊 Excel batch for all {len(parts)}.", duration=8)
        return batch.questions_text(chunk), narr or None, new_title

    def start(request: gr.Request):
        if not _claim(request):
            raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
        return (True, gr.update(selected="vid"), gr.update(interactive=False), gr.update(interactive=False),
                gr.update(interactive=False), "⏳ Rendering all videos… each one appears below as soon as it is done.",
                gr.update(value=None, visible=False), gr.update(value=None, visible=False))

    def render_all(request: gr.Request, sheet, clips, folder, per, tab, start, count, title_tpl, *vals,
                   progress=gr.Progress()):
        def plan():
            items, problems = _read_batch(sheet, clips, folder, tab, start, count)
            parts = batch.split(items, per)
            if not parts:
                raise ValueError("The sheet has no usable questions." + (f" First problem: {problems[0]}" if problems else ""))
            base = values_to_project("mcq", vals)
            out_dir = os.path.join(OUT_DIR, f"batch_{_stamp()}")
            os.makedirs(out_dir, exist_ok=True)
            total = len(parts)
            tpl = title_tpl if str(title_tpl or "").strip() else None

            def jobs():
                taken = set()
                for k, chunk in enumerate(parts, 1):
                    name = batch.video_name(chunk, k, taken)  # the first question's text
                    yield name, batch.part_project(base, chunk, k, total, os.path.join(out_dir, f"{name} audio"), tpl)
            return out_dir, total, jobs()

        yield from _stream_batch(request, plan, progress)

    xl["sheet"].change(fill_tabs, xl["sheet"], xl["tab"], show_progress="hidden")
    gr.on(triggers=[c.change for c in inputs], fn=check, inputs=inputs, outputs=[xl["info"], xl["part"], xl["go"]],
          trigger_mode="always_last", show_progress="hidden")
    xl["load"].click(load_part, inputs + [xl["part"], xl["title"], m_title], [m_qs, m_narr, m_title])
    dep = xl["go"].click(start, None, [pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"], pv["info"],
                                       xl["files"], xl["zip"]], queue=False)
    dep.success(render_all, inputs + [xl["title"]] + fields,
                [pv["vid"], pv["info"], xl["files"], xl["zip"], pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"]],
                **_progress_on(dep, pv["vid"]))


# ------------------------------------------------------------------ Excel batch (Timeline Collision)
TL_BATCH_HELP = """**One row = one video.** Write 2-5 countries (Arabic or English names) and their areas per row,
plus — optionally — the hook, doubt word («مستحيل؟») and its subtitle, comparison title, reveal, intro (`hook` / `vs`), map style (`auto` / `overlay` / `tiles` / `side`),
guess (`yes` / `no`) and the ending question. Empty hook / reveal cells are written automatically from the numbers.
Every video uses the theme, music, handle and ending you set in the other tabs. Get the **template** (10 ready
comparisons) on the right."""


def _tl_template_path():
    path = os.path.join(APP_PROJ_DIR, "countries_template.xlsx")
    if not os.path.isfile(path):
        try:
            tl_batch.write_template(path)
        except Exception:  # openpyxl missing: no template button
            return None
    return path


def tl_batch_tab():
    with gr.Row(equal_height=True):
        gr.Markdown(TL_BATCH_HELP)
        tpl = _tl_template_path()
        gr.DownloadButton("⬇️ Excel template", value=tpl, visible=bool(tpl), size="sm", min_width=130, scale=0)
    sheet = gr.File(type="filepath", file_types=[".xlsx", ".xlsm", ".csv"], label="Videos sheet (.xlsx or .csv)",
                    height=120)
    tab, start, count = sheet_controls("videos")
    with gr.Row(equal_height=True):
        info = gr.Markdown("Upload a sheet to see how many videos it makes.")
        go = gr.Button("🎬 Render all videos", variant="primary", interactive=False, min_width=230, scale=0)
    zipb = gr.DownloadButton("📦 Download all (.zip)", visible=False, variant="primary")
    files = gr.File(label="Rendered videos — each one appears here as soon as it finishes", file_count="multiple",
                    visible=False, height=320)
    with gr.Row(equal_height=True):
        part = gr.Dropdown([], label="Preview one video in the editor", scale=2)
        load = gr.Button("📥 Load into editor", scale=1, min_width=120)
    return dict(sheet=sheet, info=info, go=go, files=files, zip=zipb, part=part, load=load, tab=tab, start=start,
                count=count)


def wire_tl_batch(xl, pv, fields):
    inputs = [xl["sheet"], xl["tab"], xl["start"], xl["count"]]

    def read(sheet, tab, start, count):
        if not sheet:
            raise ValueError("Upload a videos sheet first.")
        return tl_batch.load_sheet(sheet, tab, start, count)

    def check(sheet, tab, start, count):
        off = gr.update(value="🎬 Render all videos", interactive=False)
        if not sheet:
            return "Upload a sheet to see how many videos it makes.", gr.update(choices=[], value=None), off
        try:
            specs, problems = read(sheet, tab, start, count)
        except Exception as e:
            return f"⚠️ {_msg(e)}", gr.update(choices=[], value=None), off
        choices = [(f"Video {k} — row {sp['row']}: {tl_batch.file_name(sp, k)[3:].replace('_', ' ')}", k)
                   for k, sp in enumerate(specs, 1)]
        n = len(specs)
        go = gr.update(value=f"🎬 Render all {n} video{'s' if n != 1 else ''}" if n else "🎬 Render all videos",
                       interactive=bool(n))
        return (range_note(specs, "videos", start, count) + tl_batch.summary(specs, problems),
                gr.update(choices=choices, value=1 if choices else None), go)

    def load_part(sheet, tab, start, count, k, *vals):
        try:
            specs, _ = read(sheet, tab, start, count)
            k = int(k or 1)
            if not 1 <= k <= len(specs):
                raise ValueError("Pick a video to preview.")
            project = tl_batch.to_project(values_to_project("timeline", vals), specs[k - 1])
        except Exception as e:
            raise gr.Error(_msg(e))
        gr.Info(f"Video {k} of {len(specs)} is in the editor. 🎬 Render video makes only this one — "
                f"use 🎬 Render all in 📊 Excel batch for all {len(specs)}.", duration=8)
        return project_to_values(project, "timeline")

    def start(request: gr.Request):
        if not _claim(request):
            raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
        return (True, gr.update(selected="vid"), gr.update(interactive=False), gr.update(interactive=False),
                gr.update(interactive=False), "⏳ Rendering all videos… each one appears below as soon as it is done.",
                gr.update(value=None, visible=False), gr.update(value=None, visible=False))

    def render_all(request: gr.Request, sheet, tab, start, count, *vals, progress=gr.Progress()):
        def plan():
            specs, problems = read(sheet, tab, start, count)
            if not specs:
                raise ValueError("The sheet has no usable rows." + (f" First problem: {problems[0]}" if problems else ""))
            base = values_to_project("timeline", vals)
            lang = base.get("settings", {}).get("language") or "ar"
            out_dir = os.path.join(OUT_DIR, f"batch_timeline_{_stamp()}")
            os.makedirs(out_dir, exist_ok=True)
            jobs = ((tl_batch.file_name(sp, k, lang), tl_batch.to_project(base, sp)) for k, sp in enumerate(specs, 1))
            return out_dir, len(specs), jobs

        yield from _stream_batch(request, plan, progress)

    xl["sheet"].change(fill_tabs, xl["sheet"], xl["tab"], show_progress="hidden")
    gr.on(triggers=[c.change for c in inputs], fn=check, inputs=inputs, outputs=[xl["info"], xl["part"], xl["go"]],
          trigger_mode="always_last", show_progress="hidden")
    xl["load"].click(load_part, inputs + [xl["part"]] + fields, fields)
    dep = xl["go"].click(start, None, [pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"], pv["info"],
                                       xl["files"], xl["zip"]], queue=False)
    dep.success(render_all, inputs + fields,
                [pv["vid"], pv["info"], xl["files"], xl["zip"], pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"]],
                **_progress_on(dep, pv["vid"]))


# ------------------------------------------------------------------ English Words
VC_ITEMS_HELP = """**One item per block, an empty line between items** (max 10). Start each line with a key:
`type:` word / guess / reverse / mistake / proverb / idiom / list (optional — worked out from the lines) ·
`word:` the word, phrase, proverb or idiom (`right:` the correct sentence of a mistake) · `ipa:` /prəˈnʌnsiˈeɪʃn/ ·
`pos:` noun • اسم · `meaning:` · `example:` (put \\*stars\\* around words to choose what is highlighted) ·
`example_ar:` · `also:` similar words, comma separated · `wrong:` the wrong sentence · `literal:` the literal meaning ·
`equivalent:` the Arabic proverb · `note:` · `question:` your own question · `recap:` short meaning for the recap ·
`group:` an item from another group (mixed videos).
Guess options are lines starting with `-`; put `*` after the correct one.
**Word list** (several words on one page, read one after another): `type: list`, optional `title:` / `subtitle:`,
then one line per word (up to 6): `- Airport = مطار` or `- Airport = /ˈeəpɔːt/ = مطار`."""
VC_AUDIO_HELP = """**Your own audio per item.** Name each clip after its item: `w1` = item 1 (the word, proverb or
correct sentence — it plays when it appears and the 🔊 icon animates) · `w1e` = item 1's example sentence ·
`w1_1`, `w1_2` … = word 1, word 2 … of a word list in item 1 (each word lights up while its clip plays).
Any audio type works (mp3, wav, m4a…). The item waits for its clips, and the music gets quieter while they play.
A voiceover for the whole video is in 🎨 Style & sound."""
VC_BATCH_HELP = """**Make many videos from one spreadsheet.** One item per row: `Group · Type · Word / Phrase · IPA ·
Part of speech · Meaning · Example · Example (Arabic) · Similar words · Option A–D · Correct · Wrong sentence ·
Literal meaning · Arabic equivalent · Note · Question · Recap · Audio · Example audio · Page title · Page subtitle`
(English or Arabic headers — get
the **template** on the right, it has an example of every group and type). Every video uses the design, timing,
music and ending you set in the other tabs, and the colour and theme of its own group. In the title, `{n}` becomes the
video number and `{total}` the number of videos (empty = automatic title per group)."""


def _vc_template_path():
    path = os.path.join(APP_PROJ_DIR, "words_template.xlsx")
    if not os.path.isfile(path):
        try:
            vocab_batch.write_template(path)
        except Exception:  # openpyxl missing: no template button
            return None
    return path


def vc_batch_tab():
    with gr.Row(equal_height=True):
        gr.Markdown(VC_BATCH_HELP)
        tpl = _vc_template_path()
        gr.DownloadButton("⬇️ Excel template", value=tpl, visible=bool(tpl), size="sm", min_width=130, scale=0)
    with gr.Row():
        sheet = gr.File(type="filepath", file_types=[".xlsx", ".xlsm", ".csv"], label="Words sheet (.xlsx or .csv)",
                        height=120)
        clips = gr.File(file_count="multiple", type="filepath", file_types=["audio"], height=120,
                        label="Audio clips named in the sheet (optional)")
    folder = gr.Textbox(label="…or the folder on this computer that holds the clips (optional)",
                        placeholder=r"C:\english\audio")
    tab, start, count = sheet_controls("items")
    with gr.Row():
        per = gr.Slider(1, vocab_batch.MAX_ITEMS, value=5, step=1, label="Items per video",
                        info="A word-list page counts as one item")
        lsize = gr.Slider(1, vocab_batch.LIST_MAX, value=4, step=1, label="Words per list page",
                          info="Type = list rows: one word per row, this many words on one page")
    split = gr.Radio(vocab_batch.SPLIT_MODES, value="group", label="Split")
    with gr.Row():
        title = gr.Textbox(label="Title of each video (optional)", placeholder="5 Political Words — Part {n}")
        lesson0 = gr.Number(value=1, precision=0, label="First lesson number (English Lesson #{n})")
    with gr.Row(equal_height=True):
        info = gr.Markdown("Upload a sheet to see how many videos it makes.")
        go = gr.Button("🎬 Render all videos", variant="primary", interactive=False, min_width=230, scale=0)
    zipb = gr.DownloadButton("📦 Download all (.zip)", visible=False, variant="primary")
    files = gr.File(label="Rendered videos — each one appears here as soon as it finishes (a cover picture is saved "
                          "next to each)", file_count="multiple", visible=False, height=320)
    with gr.Row(equal_height=True):
        part = gr.Dropdown([], label="Preview one video in the editor", scale=2)
        load = gr.Button("📥 Load into editor", scale=1, min_width=120)
    return dict(sheet=sheet, clips=clips, folder=folder, per=per, lsize=lsize, split=split, title=title, lesson0=lesson0,
                info=info,
                go=go, files=files, zip=zipb, part=part, load=load, tab=tab, start=start, count=count)


def wire_vc_batch(xl, pv, fields):
    inputs = [xl["sheet"], xl["clips"], xl["folder"], xl["per"], xl["split"], xl["tab"], xl["start"], xl["count"],
              xl["lsize"]]

    def read(sheet, clips, folder, per, split, tab, start, count, lsize, vals):
        if not sheet:
            raise ValueError("Upload a words sheet first.")
        items, problems = vocab_batch.load_sheet(sheet, clips or [], folder or "", tab, start, count, lsize or 4)
        base = values_to_project("vocab", vals)
        g = base["vocab"].get("group") or "general"
        videos = vocab_batch.split(items, per, split or "group", g)
        return items, problems, videos, base

    def check(sheet, clips, folder, per, split, tab, start, count, lsize, *vals):
        off = gr.update(value="🎬 Render all videos", interactive=False)
        if not sheet:
            return "Upload a sheet to see how many videos it makes.", gr.update(choices=[], value=None), off
        try:
            items, problems, videos, base = read(sheet, clips, folder, per, split, tab, start, count, lsize, vals)
        except Exception as e:
            return f"⚠️ {_msg(e)}", gr.update(choices=[], value=None), off
        g, gname = base["vocab"].get("group") or "general", base["vocab"].get("group_name") or ""
        choices = [(f"Video {k} — {vocab_batch.group_label(v, g, gname)}, {len(v['items'])} items "
                    f"(rows {v['items'][0]['row']}–{v['items'][-1].get('row_end', v['items'][-1]['row'])})", k)
                   for k, v in enumerate(videos, 1)]
        n = len(videos)
        go = gr.update(value=f"🎬 Render all {n} video{'s' if n != 1 else ''}" if n else "🎬 Render all videos",
                       interactive=bool(n))
        return (range_note(items, "items", start, count) + vocab_batch.summary(items, problems, videos, g, gname),
                gr.update(choices=choices, value=1 if choices else None), go)

    def load_part(sheet, clips, folder, per, split, tab, start, count, lsize, k, title_tpl, lesson0, *vals):
        try:
            items, problems, videos, base = read(sheet, clips, folder, per, split, tab, start, count, lsize, vals)
            k = int(k or 1)
            if not 1 <= k <= len(videos):
                raise ValueError("Pick a video to preview.")
            proj = vocab_batch.part_project(base, videos[k - 1], k, len(videos),
                                            os.path.join(OUT_DIR, "_batch_preview", f"words_{k:02d}"),
                                            lesson_n=int(lesson0 or 1) + k - 1, title=title_tpl or None)
        except Exception as e:
            raise gr.Error(_msg(e))
        gr.Info(f"Video {k} of {len(videos)} is in the editor. 🎬 Render video makes only this one — "
                f"use 🎬 Render all in 📊 Excel batch for all {len(videos)}.", duration=8)
        return project_to_values(proj, "vocab")

    def start(request: gr.Request):
        if not _claim(request):
            raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
        return (True, gr.update(selected="vid"), gr.update(interactive=False), gr.update(interactive=False),
                gr.update(interactive=False), "⏳ Rendering all videos… each one appears below as soon as it is done.",
                gr.update(value=None, visible=False), gr.update(value=None, visible=False))

    def render_all(request: gr.Request, sheet, clips, folder, per, split, tab, start, count, lsize, title_tpl, lesson0,
                   *vals, progress=gr.Progress()):
        def plan():
            items, problems, videos, base = read(sheet, clips, folder, per, split, tab, start, count, lsize, vals)
            if not videos:
                raise ValueError("The sheet has no usable rows." + (f" First problem: {problems[0]}" if problems else ""))
            g, gname = base["vocab"].get("group") or "general", base["vocab"].get("group_name") or ""
            out_dir = os.path.join(OUT_DIR, f"batch_words_{_stamp()}")
            os.makedirs(out_dir, exist_ok=True)
            total = len(videos)
            first = int(lesson0 or 1)

            def jobs():
                taken = set()
                for k, video in enumerate(videos, 1):
                    name = vocab_batch.video_name(video, k, g, gname, taken)
                    yield name, vocab_batch.part_project(base, video, k, total, os.path.join(out_dir, f"{name} audio"),
                                                         lesson_n=first + k - 1, title=title_tpl or None)
            return out_dir, total, jobs()

        yield from _stream_batch(request, plan, progress)

    xl["sheet"].change(fill_tabs, xl["sheet"], xl["tab"], show_progress="hidden")
    gr.on(triggers=[c.change for c in inputs], fn=check, inputs=inputs + fields,
          outputs=[xl["info"], xl["part"], xl["go"]], trigger_mode="always_last", show_progress="hidden")
    xl["load"].click(load_part, inputs + [xl["part"], xl["title"], xl["lesson0"]] + fields, fields)
    dep = xl["go"].click(start, None, [pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"], pv["info"],
                                       xl["files"], xl["zip"]], queue=False)
    dep.success(render_all, inputs + [xl["title"], xl["lesson0"]] + fields,
                [pv["vid"], pv["info"], xl["files"], xl["zip"], pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"]],
                **_progress_on(dep, pv["vid"]))


# ------------------------------------------------------------------ English Texts
TX_WORDS_HELP = ("One spoken word per line, like columns B–F of the sheet: `word | start | end | highlighted | arabic` "
                 "(times in seconds). Something in *highlighted* makes the word fly into the Word Bank; the same "
                 "several-word text on neighbouring lines (e.g. `chase away`) flies as one phrase.")
TX_BATCH_HELP = """**Every tab of the workbook = one video.** One spoken word per row:
`B word · C start · D end · E highlighted words · F arabic translation` (the word timings from ElevenLabs), plus a
**title** column (and optionally **subtitle**) with the text in its first cell. Upload the recordings: each goes to the tab
whose reading length it matches (or name it like the tab, `paragraph1.mp3`); the list below shows the match. The design, music and ending come from the other tabs."""


def _tx_template_path():
    path = os.path.join(APP_PROJ_DIR, "texts_template.xlsx")
    if not os.path.isfile(path):
        try:
            text_batch.write_template(path)
        except Exception:  # openpyxl missing: no template button
            return None
    return path


def tx_batch_tab():
    with gr.Row(equal_height=True):
        gr.Markdown(TX_BATCH_HELP)
        tpl = _tx_template_path()
        gr.DownloadButton("⬇️ Excel template", value=tpl, visible=bool(tpl), size="sm", min_width=130, scale=0)
    with gr.Row():
        sheet = gr.File(type="filepath", file_types=[".xlsx", ".xlsm", ".csv"], label="Paragraphs workbook (.xlsx)",
                        height=120)
        clips = gr.File(file_count="multiple", type="filepath", file_types=["audio"], height=120,
                        label="Recordings — one per tab (any names)")
    folder = gr.Textbox(label="…or the folder on this computer that holds the recordings (optional)",
                        placeholder=r"C:\english\readings")
    with gr.Row(equal_height=True):
        part = gr.Dropdown([], label="Tab to preview in the editor", scale=2)
        load = gr.Button("📥 Load into editor", scale=1, min_width=120)
    with gr.Row(equal_height=True):
        info = gr.Markdown("Upload a workbook to see its paragraphs.")
        go = gr.Button("🎬 Render all videos", variant="primary", interactive=False, min_width=230, scale=0)
    zipb = gr.DownloadButton("📦 Download all (.zip)", visible=False, variant="primary")
    files = gr.File(label="Rendered videos — each one appears here as soon as it finishes (a cover picture is saved "
                          "next to each)", file_count="multiple", visible=False, height=320)
    return dict(sheet=sheet, clips=clips, folder=folder, part=part, load=load, info=info, go=go, zip=zipb, files=files)


def wire_tx_batch(xl, pv, fields):
    inputs = [xl["sheet"], xl["clips"], xl["folder"]]

    def read(sheet, clips, folder):
        if not sheet:
            raise ValueError("Upload the paragraphs workbook first.")
        return text_batch.load_book(sheet, clips or [], folder or "")

    def check(sheet, clips, folder):
        off = gr.update(value="🎬 Render all videos", interactive=False)
        if not sheet:
            return "Upload a workbook to see its paragraphs.", gr.update(choices=[], value=None), off
        try:
            pars = read(sheet, clips, folder)
        except Exception as e:
            return f"⚠️ {_msg(e)}", gr.update(choices=[], value=None), off
        choices = [(f"{p['tab'] or 'Sheet'} — {p['title'] or '(no title)'}", k) for k, p in enumerate(pars) if p["rows"]]
        n = sum(1 for p in pars if p["rows"] and p["audio"])  # tabs without a recording are skipped
        go = gr.update(value=f"🎬 Render all {n} video{'s' if n != 1 else ''}" if n else "🎬 Render all videos",
                       interactive=bool(n))
        return text_batch.summary(pars), gr.update(choices=choices, value=choices[0][1] if choices else None), go

    def load_part(sheet, clips, folder, k, *vals):
        try:
            pars = read(sheet, clips, folder)
            if k is None or not 0 <= int(k) < len(pars) or not pars[int(k)]["rows"]:
                raise ValueError("Pick a tab to preview.")
            proj = text_batch.part_project(values_to_project("text", vals), pars[int(k)])
        except Exception as e:
            raise gr.Error(_msg(e))
        gr.Info("The paragraph is in the editor (📝 Text). 🎬 Render video makes only this one — "
                "🎬 Render all makes every tab.", duration=6)
        return project_to_values(proj, "text")

    def start(request: gr.Request):
        if not _claim(request):
            raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
        return (True, gr.update(selected="vid"), gr.update(interactive=False), gr.update(interactive=False),
                gr.update(interactive=False), "⏳ Rendering all videos… each one appears below as soon as it is done.",
                gr.update(value=None, visible=False), gr.update(value=None, visible=False))

    def render_all(request: gr.Request, sheet, clips, folder, *vals, progress=gr.Progress()):
        def plan():
            pars = [p for p in read(sheet, clips, folder) if p["rows"]]
            if not pars:
                raise ValueError("The workbook has no tabs with words.")
            silent = [p["tab"] for p in pars if not p["audio"]]
            pars = [p for p in pars if p["audio"]]
            if not pars:
                raise ValueError("No recordings found — upload the MP3s in 📊 Excel sheet (one per tab).")
            if silent:
                gr.Warning("Skipped (no recording): " + ", ".join(f"'{t}'" for t in silent[:6]), duration=8)
            base = values_to_project("text", vals)
            out_dir = os.path.join(OUT_DIR, f"batch_texts_{_stamp()}")
            os.makedirs(out_dir, exist_ok=True)

            def jobs():
                taken = set()
                for k, par in enumerate(pars, 1):
                    yield text_batch.video_name(par, k, taken), text_batch.part_project(base, par)
            return out_dir, len(pars), jobs()

        yield from _stream_batch(request, plan, progress)

    gr.on(triggers=[c.change for c in inputs], fn=check, inputs=inputs, outputs=[xl["info"], xl["part"], xl["go"]],
          trigger_mode="always_last", show_progress="hidden")
    xl["load"].click(load_part, inputs + [xl["part"]] + fields, fields)
    dep = xl["go"].click(start, None, [pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"], pv["info"],
                                       xl["files"], xl["zip"]], queue=False)
    dep.success(render_all, inputs + fields,
                [pv["vid"], pv["info"], xl["files"], xl["zip"], pv["busy"], pv["tabs"], pv["clip"], pv["rd"], xl["go"]],
                **_progress_on(dep, pv["vid"]))


# ------------------------------------------------------------------ Know a Country
KC_TEMPLATE = os.path.join(APP_PROJ_DIR, "know_country_template.xlsx")
KC_CACHE = os.path.join(DATA_DIR, "cache")
KC_ALL = "All rows"
KC_HELP = """**One Excel row = one video.** Download the template, fill one row per country — figures with their
dates and sources, facts, top exports, countries to compare with (true-size drag), cities for the distances —
then upload it here, pick a country (or *All rows*) and press **Render**.
Use **Quick check** first: it draws one picture in about half a minute, so you can catch a typo before the long
render. A video takes about 15–25 minutes (it is drawn on 2 processes); the sheet tab **guide** explains every
column, and the **areas** tab holds the areas used in the comparisons (green rows are verified)."""


def know_country_tab():
    with gr.Row(equal_height=True):
        gr.Markdown(KC_HELP)
        gr.DownloadButton("⬇️ Excel template", value=KC_TEMPLATE if os.path.isfile(KC_TEMPLATE) else None,
                          visible=os.path.isfile(KC_TEMPLATE), size="sm", min_width=130, scale=0)
    with gr.Row():
        sheet = gr.File(type="filepath", file_types=[".xlsx"], label="Countries sheet (.xlsx)", height=120, scale=2)
        pick = gr.Dropdown([], label="Country", info="A row of the sheet — or All rows", scale=1)
    with gr.Row():
        still = gr.Button("🖼️ Quick check (one picture)", interactive=False)
        go = gr.Button("🎬 Render video", variant="primary", interactive=False)
    info = gr.Markdown("Upload the countries sheet to start.")
    with gr.Row(equal_height=False):
        img = gr.Image(label="Quick check", height=560, visible=False, interactive=False)
        vid = gr.Video(label="Video", height=640, visible=False)
    files = gr.File(label="Rendered videos", file_count="multiple", visible=False, height=200)

    def loaded(path):
        if not path:
            return gr.update(choices=[], value=None), gr.update(interactive=False), gr.update(interactive=False), \
                "Upload the countries sheet to start."
        try:
            names = kc_video.countries_in(path)
        except Exception as e:
            raise gr.Error(f"Could not read the sheet: {e}")
        if not names:
            return gr.update(choices=[], value=None), gr.update(interactive=False), gr.update(interactive=False), \
                "The **countries** tab has no rows yet."
        choices = names + ([KC_ALL] if len(names) > 1 else [])
        return (gr.update(choices=choices, value=names[0]), gr.update(interactive=True), gr.update(interactive=True),
                f"Found {len(names)} countr{'y' if len(names) == 1 else 'ies'}: " + ", ".join(names))

    def quick(request: gr.Request, path, country, progress=gr.Progress()):
        if not path or not country:
            raise gr.Error("Upload the sheet and pick a country first.")
        country = kc_video.countries_in(path)[0] if country == KC_ALL else country
        if not _claim(request):
            raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
        try:
            progress(0.1, desc="Drawing one picture…")
            out = os.path.join(OUT_DIR, f"know_country_check_{_stamp()}.png")
            kc_video.preview(country, path, out, cache_dir=KC_CACHE)
            return gr.update(value=out, visible=True), f"Quick check of **{country}** — looks right? Press 🎬 Render video."
        except Exception as e:
            raise gr.Error(str(e))
        finally:
            _release(request)

    def render(request: gr.Request, path, country, progress=gr.Progress()):
        if not path or not country:
            raise gr.Error("Upload the sheet and pick a country first.")
        todo = kc_video.countries_in(path) if country == KC_ALL else [country]
        if not _claim(request):
            raise gr.Error("Already working on a video — please wait for it to finish.", duration=4)
        done = []
        try:
            for k, c in enumerate(todo):
                safe = "".join(ch if ch.isalnum() else "_" for ch in c).strip("_") or "country"
                out = os.path.join(OUT_DIR, f"know_country_{safe}_{_stamp()}.mp4")
                yield (gr.update(), gr.update(), f"⏳ Rendering **{c}** ({k + 1} of {len(todo)})… about 15–25 minutes.")

                def tick(f, text, k=k):
                    progress((k + f) / len(todo), desc=text)
                kc_video.render(c, out, path, cache_dir=KC_CACHE, workers=2, progress=tick)
                done.append(out)
                yield (gr.update(value=out, visible=True), gr.update(value=list(done), visible=True),
                       f"✅ {len(done)} of {len(todo)} done — saved in `{OUT_DIR}`")
        except Exception as e:
            raise gr.Error(f"{type(e).__name__}: {e}" if not isinstance(e, ValueError) else str(e))
        finally:
            _release(request)

    sheet.change(loaded, sheet, [pick, still, go, info], show_progress="hidden")
    still.click(quick, [sheet, pick], [img, info])
    go.click(render, [sheet, pick], [vid, files, info])


def build_ui():
    kw = {"css": CSS} if "css" in inspect.signature(gr.Blocks.__init__).parameters else {}
    with gr.Blocks(title="Video Studio", **kw) as demo:
        gr.Markdown("## 🎬 Video Studio <small>— the preview on the right updates live as you edit · "
                    f"💾 your projects and videos are saved in <code>{DATA_DIR}</code></small>",
                    elem_id="app-title")
        with gr.Tab("⏳ Timeline Collision"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=420):
                    tl_proj = project_bar()
                    with gr.Tabs():
                        with gr.Tab("📝 Story"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    mode = gr.Radio([("Calendar years (BC = negative)", "calendar"),
                                                     ("Years ago (deep time)", "ago"),
                                                     ("Number line (any unit)", "scale")],
                                                    value="calendar", label="Mode", scale=3)
                                    unit = gr.Textbox(label="Unit (number line only)", rtl=True, scale=1,
                                                      placeholder="كم²")
                                hook = gr.Textbox(lines=3, max_lines=5, rtl=True,
                                                  label="Hook (first 2.5 s) — the surprising claim")
                                hide_first = gr.Checkbox(value=True,
                                                         label="Hide the first (oldest / smallest) event in the hook, reveal it on zoom-out")
                                with gr.Row():
                                    doubt = gr.Textbox(label="Doubt word", rtl=True)
                                    doubt_sub = gr.Textbox(label="Doubt subtitle", rtl=True)
                                compare_title = gr.Textbox(label="Comparison title", rtl=True)
                                reveal = gr.Textbox(lines=2, max_lines=4, label="Reveal (after the bass hit)", rtl=True)
                                with gr.Row():
                                    maps = gr.Checkbox(value=False, label="🗺️ True-size map scene (values = areas of countries)")
                                    guess = gr.Checkbox(value=False, label="🤔 Guess moment (3 choices + 3 s timer)")
                                guess_q = gr.Textbox(lines=2, max_lines=3, rtl=True, label="Guess question (optional)",
                                                     placeholder="Empty = automatic. {a} = smaller, {b} = bigger")
                                with gr.Row():
                                    intro = gr.Radio([("Hook text", "hook"), ("⚔️ VS battle", "vs"), ("🌍 Globe", "globe")],
                                                     value="hook",
                                                     label="Intro")
                                    map_style = gr.Radio([("Auto", "auto"), ("Overlay", "overlay"),
                                                          ("Tile fill", "tiles"), ("Side by side", "side")],
                                                         value="auto", label="Map scene style")
                                with gr.Row():
                                    polish = gr.Checkbox(value=True, label="✨ Motion polish (camera drift, push-ins)")
                                    finish = gr.Checkbox(value=True, label="🎬 Cinematic finish (glow, grain, "
                                                                           "vignette, light leaks)")
                        with gr.Tab("🗓️ Events"):
                            ev_fields = []
                            with gr.Tabs():
                                for i in range(N_EVENTS):
                                    with gr.Tab(f"Event {i + 1}"):
                                        with gr.Column(elem_classes="pane"):
                                            with gr.Row():
                                                en = gr.Checkbox(value=i < 3, label="Use", scale=1, min_width=70)
                                                co = gr.Dropdown(COUNTRY_CHOICES, value="", filterable=True, scale=3,
                                                                 label="Country (optional: flag, map, name)")
                                            with gr.Row():
                                                nm = gr.Textbox(label="Name (empty = country name)", rtl=True, scale=3)
                                                yr = gr.Number(label="Year / value", scale=2)
                                            with gr.Row():
                                                lb = gr.Textbox(label="Card subtitle (optional)", rtl=True)
                                                cl = gr.Dropdown(COLOR_NAMES, value=["sand", "gold", "blue", "green", "pink"][i],
                                                                 allow_custom_value=True, label="Color (name or #hex)")
                                                ic = gr.Dropdown(ICON_NAMES + ["flag", "map"], value="none",
                                                                 label="Icon (flag / map for countries)")
                                            im = gr.Image(type="filepath", height=170,
                                                          label="Or a picture (optional, replaces the icon)")
                                            ol = gr.File(label="Own map outline (optional GeoJSON, replaces the border)",
                                                         file_types=[".geojson", ".json"], type="filepath", height=90)
                                    ev_fields += [en, nm, yr, lb, cl, ic, im, co, ol]
                        with gr.Tab("📊 Excel batch"):
                            with gr.Column(elem_classes="pane"):
                                tl_xl = tl_batch_tab()
                        tl_st = style_tab()
                        tl_end = ending_tab()
                    tl_fields = (shared_fields(tl_st, tl_end)
                                 + [mode, hook, hide_first, doubt, doubt_sub, compare_title, reveal, unit, maps, guess, guess_q,
                                    intro, map_style, polish, finish]
                                 + ev_fields)
                tl_pv = preview_panel("timeline")
            wire(tl_proj, tl_pv, tl_fields)
            wire_tl_batch(tl_xl, tl_pv, tl_fields)

        with gr.Tab("❓ Clue Quiz"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=420):
                    qz_proj = project_bar()
                    with gr.Tabs():
                        with gr.Tab("📝 Quiz"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    q_title = gr.Textbox(label="Title / question", rtl=True)
                                    q_sub = gr.Textbox(label="Subtitle", rtl=True)
                                q_clues = gr.Textbox(lines=6, max_lines=8, rtl=True,
                                                     label="Clues — one per line, hardest first (max 8)")
                                with gr.Row():
                                    q_secs = gr.Slider(2, 8, value=4, step=0.5, label="Seconds per clue")
                                    q_acc = gr.Dropdown(COLOR_NAMES, value="gold", allow_custom_value=True,
                                                        label="Accent color")
                        with gr.Tab("🏆 Answer"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    q_ai = gr.Textbox(label="Answer intro", rtl=True)
                                    q_ans = gr.Textbox(label="Answer", rtl=True)
                                q_asub = gr.Textbox(label="Answer subtitle", rtl=True)
                                q_img = gr.Image(type="filepath", label="Answer picture (optional)", height=220)
                        qz_st = style_tab()
                        qz_end = ending_tab()
                    qz_fields = shared_fields(qz_st, qz_end) + [q_title, q_sub, q_clues, q_secs, q_ai, q_ans, q_asub,
                                                                 q_img, q_acc]
                qz_pv = preview_panel("quiz")
            wire(qz_proj, qz_pv, qz_fields)

        with gr.Tab("✅ Multiple Choice"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=420):
                    mq_proj = project_bar()
                    with gr.Tabs():
                        with gr.Tab("📝 Questions"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    m_title = gr.Textbox(label="Title", rtl=True)
                                    m_sub = gr.Textbox(label="Subtitle", rtl=True)
                                m_qs = gr.Textbox(lines=12, max_lines=40, rtl=True, label="Questions — see format below",
                                                  info="Question line, then 3 or 4 option lines. Put * after the correct "
                                                       "option. Optional explanation line starting with >, optional "
                                                       "difficulty line: ! easy / ! medium / ! hard (or ! سهل / ! متوسط "
                                                       "/ ! صعب). Leave an EMPTY line between questions (max 10).")
                        with gr.Tab("⏱️ Design & timing"):
                            with gr.Column(elem_classes="pane"):
                                m_layout = gr.Radio(LAYOUT_NAMES, value="Standard", label="Layout",
                                                    info="Standard = cards in the Design style below. Exam paper = a "
                                                         "ruled exam sheet on a desk, a red pen marks the answer and "
                                                         "writes the explanation. Islamic = emerald and gold with a "
                                                         "mihrab-arch card. (Design style, header and number style "
                                                         "apply to Standard; timer type and animations to all.)")
                                m_letters = gr.Checkbox(value=True, label="Show option letters (أ ب ج د / A B C D)",
                                                        info="Off = the options without letters (centred on "
                                                             "Standard cards).")
                                with gr.Row():
                                    m_style = gr.Dropdown(STYLE_NAMES, value="Game Show", label="Design style")
                                    m_timer = gr.Dropdown(TIMER_NAMES, value="Ring", label="Timer type")
                                    m_acc = gr.Dropdown(COLOR_NAMES, value="gold", allow_custom_value=True,
                                                        label="Accent color")
                                with gr.Row():
                                    m_think = gr.Slider(2, 10, value=5, step=0.5, label="Seconds to think (countdown)")
                                    m_rev = gr.Slider(1.5, 5, value=2.8, step=0.1, label="Seconds to show the answer")
                                m_tstyle = gr.Radio(TITLE_STYLES, value="Fancy", label="Opening title",
                                                    info="Fancy = animated badge, 3D title slam, shockwave, sparks and "
                                                         "a light sweep (best with the 'Swoosh + impact' opening "
                                                         "sound). Simple = the classic pop-in. None = no title: the "
                                                         "first question stamps in on the first frame (best hook).")
                                m_hstyle = gr.Radio(HEADER_STYLES, value="Fancy", label="Question header",
                                                    info="Fancy = glass pill with a light sweep and ornaments, plus a "
                                                         "progress bar that fills during each question. Simple = flat "
                                                         "pill with dots.")
                                m_nstyle = gr.Dropdown(NUMBER_STYLES, value="coin", label="Question number style",
                                                       info="How the numbers in the Fancy header look: gold coin, "
                                                            "two circles, progress ring (fills as the quiz goes on), "
                                                            "hexagon gem, scoreboard (3/5 capsule) or plain text.")
                                m_fx = gr.CheckboxGroup(TIMER_FX, value=["pulse", "glow", "ripple", "shake"],
                                                        label="Timer effects while ticking",
                                                        info="Pick any mix — they work with every timer type.")
                                m_qfx = gr.CheckboxGroup(FX_OPTIONS, value=list(FX_KEYS), label="Animations",
                                                         info="Lock-in = options flash before the reveal, a ✔ draws on "
                                                              "the answer and the wrong ones shake with a ✖. Final "
                                                              "question = red ribbon + heartbeat on the last question. "
                                                              "Score-levels ending = Beginner / Expert / Genius cards "
                                                              "and a subscribe tap (uses the Ending question as title; "
                                                              "the ending lasts 5 s). Each comes with its own sound.")
                                m_colors = gr.Radio([("Style's own colours", "style"), ("Theme colours", "theme")],
                                                    value="style", label="Colours",
                                                    info="Theme colours = background and cards follow the Theme in "
                                                         "'🎨 Style & sound', with this style's shapes, borders and glow. "
                                                         "(Classic always uses the Theme.)")
                        with gr.Tab("🎙️ Narration"):
                            with gr.Column(elem_classes="pane"):
                                gr.Markdown(NARRATION_HELP)
                                m_narr = gr.File(file_count="multiple", type="filepath", file_types=["audio"],
                                                 label="Narration clips (select many at once)", height=170)
                                m_narr_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Narration volume")
                                m_narr_info = gr.Markdown("No narration clips yet.")
                        with gr.Tab("📊 Excel batch"):
                            with gr.Column(elem_classes="pane"):
                                xl = batch_tab()
                        mq_st = style_tab()
                        mq_end = ending_tab(COUNT_NOTE)
                    mq_fields = shared_fields(mq_st, mq_end) + [m_title, m_sub, m_qs, m_think, m_rev, m_acc, m_style,
                                                                 m_timer, m_colors, m_narr, m_narr_gain, m_fx,
                                                                 m_tstyle, m_hstyle, m_qfx, m_nstyle,
                                                                 m_layout, m_letters]
                mq_pv = preview_panel("mcq")
            wire(mq_proj, mq_pv, mq_fields)
            gr.on(triggers=[m_narr.change, m_qs.change], fn=narration_report, inputs=[m_narr, m_qs],
                  outputs=m_narr_info, trigger_mode="always_last", show_progress="hidden")
            wire_batch(xl, mq_pv, mq_fields, m_qs, m_narr, m_title)

            def theme_follows(style, colors):
                """Picking a Theme should visibly change the video: switch the style to Theme colours."""
                if style != "Classic" and colors != "theme":
                    gr.Info(f"Colours switched to “Theme colours” so the {style} style uses your theme "
                            f"(change it back in ⏱️ Design & timing).", duration=6)
                    return "theme"
                return gr.update()
            # .select = only when the user picks a theme (not when an example or project is loaded)
            mq_st["theme"].select(theme_follows, [m_style, m_colors], m_colors, show_progress="hidden")

        with gr.Tab("🔤 English Words"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=420):
                    vc_proj = project_bar()
                    with gr.Tabs():
                        with gr.Tab("📝 Items"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    v_group = gr.Dropdown(GROUP_CHOICES, value="politics", label="Group",
                                                          info="Sets the badge, colour and background of the video")
                                    v_gname = gr.Textbox(label="Badge text (optional)",
                                                         placeholder="Your own group's name, e.g. BUSINESS • أعمال",
                                                         info="Your own group: its name. Other groups: renames the badge")
                                with gr.Row():
                                    v_title = gr.Textbox(label="Title (empty = automatic)",
                                                         placeholder="{count} Political Words")
                                    v_sub = gr.Textbox(label="Subtitle (empty = automatic)", rtl=True)
                                with gr.Row():
                                    v_lesson = gr.Textbox(label="Lesson line (optional)", placeholder="English Lesson #{n}",
                                                          info="{n} = the lesson number")
                                    v_lesson_n = gr.Number(value=1, precision=0, label="Lesson number")
                                v_items = gr.Textbox(lines=16, max_lines=60, label="Items", info=VC_ITEMS_HELP)
                                with gr.Row(equal_height=True):
                                    v_type = gr.Dropdown(TYPE_CHOICES, value="word", label="New item type", scale=2)
                                    v_add = gr.Button("➕ Add item", scale=1, min_width=110)
                                    v_words = gr.Button("🔁 Make all word cards", scale=1, min_width=150)
                        with gr.Tab("⏱️ Design & timing"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    v_acc = gr.Dropdown(["group"] + COLOR_NAMES, value="group", allow_custom_value=True,
                                                        label="Accent colour", info="group = the group's own colour, "
                                                                                    "or a colour name / #hex")
                                    v_bg = gr.Radio([("Group's theme", "group"), ("Theme in 🎨 Style & sound", "theme")],
                                                    value="group", label="Background")
                                with gr.Row():
                                    v_tstyle = gr.Radio(VC_TITLE_STYLES, value="Fancy", label="Opening title",
                                                        info="Fancy = Aa badge, 3D title slam, shockwave and sparks "
                                                             "(best with the 'Swoosh + impact' opening sound). "
                                                             "Simple = clean pop-in. None = no title page: the "
                                                             "video starts with the first item.")
                                    v_hook = gr.Checkbox(value=True, label="Show the first word faintly behind the title")
                                with gr.Row():
                                    v_pace = gr.Radio(PACES, value="normal", label="Pace",
                                                      info="How long each line stays before the next one appears")
                                    v_recap = gr.Checkbox(value=True, label="Recap at the end (What did we learn today?)")
                                with gr.Row():
                                    v_secs = gr.Slider(2, 15, value=5, step=1, label="Guess countdown (seconds)")
                                    v_timer = gr.Dropdown(TIMER_NAMES, value="Bar", label="Guess timer")
                                v_tfx = gr.CheckboxGroup(TIMER_FX, value=["pulse", "glow"], label="Timer effects")
                                gr.Markdown("**Word-list page** (`type: list` items) — the word being read lights up")
                                with gr.Row():
                                    v_lstyle = gr.Radio(VC_LIST_STYLES, value="Editorial", label="Page design",
                                                        info="Editorial = magazine page · Chalkboard = hand-written "
                                                             "chalk")
                                    v_lhl = gr.Dropdown(HIGHLIGHTS, value="cream", label="Editorial: highlight",
                                                        info="How the row being read is marked")
                                with gr.Row():
                                    v_cboard = gr.Dropdown(BOARD_CHOICES, value="green", label="Chalkboard: board")
                                    v_cmark = gr.Dropdown(MARKS, value="circle", label="Chalkboard: mark",
                                                          info="Drawn live around the word being read")
                                    v_ccol = gr.Dropdown(CHALK_COLOR_CHOICES, value="pink",
                                                         label="Chalkboard: chalk colour")
                        with gr.Tab("🎙️ Audio"):
                            with gr.Column(elem_classes="pane"):
                                gr.Markdown(VC_AUDIO_HELP)
                                v_audio = gr.File(file_count="multiple", type="filepath", file_types=["audio"],
                                                  label="Audio clips (select many at once)", height=170)
                                v_again = gr.Slider(0, 2, value=1.0, step=0.05, label="Clips volume")
                                v_ainfo = gr.Markdown("No audio clips yet.")
                        with gr.Tab("📊 Excel batch"):
                            with gr.Column(elem_classes="pane"):
                                vxl = vc_batch_tab()
                        vc_st = style_tab()
                        vc_end = ending_tab()
                    vc_fields = shared_fields(vc_st, vc_end) + [v_group, v_gname, v_title, v_sub, v_lesson, v_lesson_n,
                                                                 v_items, v_acc, v_bg, v_tstyle, v_hook, v_pace, v_secs,
                                                                 v_timer, v_tfx, v_recap, v_audio, v_again,
                                                                 v_lstyle, v_lhl, v_cboard, v_cmark, v_ccol]
                vc_pv = preview_panel("vocab")
            wire(vc_proj, vc_pv, vc_fields)
            wire_vc_batch(vxl, vc_pv, vc_fields)
            gr.on(triggers=[v_audio.change, v_items.change], fn=clips_report, inputs=[v_audio, v_items],
                  outputs=v_ainfo, trigger_mode="always_last", show_progress="hidden")
            v_add.click(add_item, [v_items, v_type], v_items)

            def make_words(text):
                try:
                    new, n = to_word_cards(text)
                except ValueError as e:
                    raise gr.Error(f"Fix the items first: {e}")
                gr.Info(f"{n} guess item{'s' if n != 1 else ''} turned into word cards." if n else
                        "There are no guess items to turn into word cards.", duration=5)
                return new if n else gr.update()
            v_words.click(make_words, v_items, v_items)

            def group_theme(group, bg):
                """Picking a group shows its own theme in 🎨 Style & sound (used while Background = Group's theme)."""
                if bg == "group" and group in GROUPS:
                    return gr.update(value=GROUPS[group]["theme"])
                return gr.update()
            v_group.select(group_theme, [v_group, v_bg], vc_st["theme"], show_progress="hidden")

            def theme_picked(bg):
                if bg != "theme":
                    gr.Info("Background switched to the theme you picked (⏱️ Design & timing → Background).", duration=6)
                    return "theme"
                return gr.update()
            vc_st["theme"].select(theme_picked, v_bg, v_bg, show_progress="hidden")

        with gr.Tab("📖 English Texts"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=420):
                    tx_proj = project_bar()
                    with gr.Tabs():
                        with gr.Tab("📊 Excel sheet"):
                            with gr.Column(elem_classes="pane"):
                                txl = tx_batch_tab()
                        with gr.Tab("📝 Text"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    t_sub = gr.Textbox(label="Small line above the title", placeholder="UNIT 3 · READING")
                                    t_tag = gr.Textbox(label="Arabic tag (top right, optional)", rtl=True,
                                                       placeholder="اقرأ واستمع")
                                with gr.Row():
                                    t_title = gr.Textbox(label="Title", placeholder="Move Your Body, Lift Your Mood",
                                                         scale=4)
                                    t_level = gr.Dropdown(TX_LEVELS, value="", label="Level badge", scale=1,
                                                          info="A1 … C2 (optional)")
                                t_words = gr.Textbox(lines=16, max_lines=60, label="Words", info=TX_WORDS_HELP)
                                t_info = gr.Markdown()
                                t_audio = gr.Audio(type="filepath", label="Recording of the paragraph (mp3 / wav…)")
                                t_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Recording volume")
                                t_trans = gr.Textbox(lines=3, max_lines=8, rtl=True,
                                                     label="Arabic translation of the whole paragraph (optional)",
                                                     info="Shown on a card after the reading (Excel: a "
                                                          "'paragraph translation' column)")
                        with gr.Tab("⏱️ Design"):
                            with gr.Column(elem_classes="pane"):
                                t_style = gr.Radio(TX_STYLES, value="textbook", label="Design",
                                                   info="Textbook = colour band + highlighter · Night studio = dark, "
                                                        "gold glow, glass cards · Exam passage = line numbers, red pen, "
                                                        "LEARNED stamp · Notebook = handwriting, pen circles, sticky "
                                                        "notes")
                                gr.Markdown("Every design: the text inks in as it is read; highlighted words are "
                                            "marked, fly into the word bank and their Arabic writes in.")
                                with gr.Row():
                                    t_band = gr.Dropdown(TX_BANDS, value="teal", label="Textbook: page colour",
                                                         info="The title band, Word Bank and ticks")
                                    t_marker = gr.Dropdown(TX_MARKERS, value="yellow",
                                                           label="Textbook: highlighter colour")
                                t_lead = gr.Slider(0.3, 3, value=1.0, step=0.1, label="Reading starts at (seconds)",
                                                   info="Time for the page to appear before the voice starts")
                        tx_st = style_tab()
                        tx_end = ending_tab()
                    tx_fields = shared_fields(tx_st, tx_end) + [t_title, t_sub, t_tag, t_words, t_audio, t_gain,
                                                                 t_lead, t_band, t_marker, t_style, t_level, t_trans]
                tx_pv = preview_panel("text")
            wire(tx_proj, tx_pv, tx_fields)
            wire_tx_batch(txl, tx_pv, tx_fields)
            gr.on(triggers=[t_words.change, t_audio.change], fn=words_report, inputs=[t_words, t_audio],
                  outputs=t_info, trigger_mode="always_last", show_progress="hidden")

        with gr.Tab("🌍 Know a Country"):
            know_country_tab()

        with gr.Tab("📘 Help"):
            gr.Markdown(HELP)

        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["timeline"][2]), "timeline"), None, tl_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["quiz"][2]), "quiz"), None, qz_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["mcq"][2]), "mcq"), None, mq_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["vocab"][2]), "vocab"), None, vc_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["text"][2]), "text"), None, tx_fields)
    return demo


def launch_kwargs():
    """Gradio 6 takes css in launch(); Gradio 5 takes it in Blocks(). The data folder is outside the app folder,
    so the browser must be allowed to show the videos and pictures in it."""
    kw = {"css": CSS} if "css" in inspect.signature(gr.Blocks.launch).parameters else {}
    kw["allowed_paths"] = [DATA_DIR]
    return kw


def rescue_old_work():
    """Older versions saved inside the app folder: copy / move that work to the data folder once."""
    try:
        done = userdata.rescue(ROOT, DATA_DIR)
    except Exception as e:  # never stop the app over this
        print(f"Could not move older saved work: {e}")
        return
    if done:
        print(f"Moved {len(done)} saved item(s) from the app folder to {DATA_DIR}")


if __name__ == "__main__":
    rescue_old_work()
    print(f"Your projects and videos are saved in: {DATA_DIR}")
    build_ui().queue().launch(inbrowser=True, **launch_kwargs())
