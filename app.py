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

import gradio as gr

from engine.audio import MOODS
from engine.core import COLOR_NAMES, THEME_NAMES
from engine.icons import ICON_NAMES
from engine.mcq_styles import STYLE_NAMES
from engine.timers import TIMER_NAMES
from engine.render import render_clip, render_still, render_video
from engine.templates import TEMPLATES
from engine.templates.mcq import narration_report

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "outputs")
PROJ_DIR = os.path.join(ROOT, "projects")
MEDIA_DIR = os.path.join(PROJ_DIR, "media")
for _d in (OUT_DIR, PROJ_DIR, MEDIA_DIR):
    os.makedirs(_d, exist_ok=True)

N_EVENTS = 5
SHARED_KEYS = [("settings", "theme"), ("settings", "language"), ("settings", "music"), ("settings", "music_gain"),
               ("settings", "music_file"), ("settings", "voice_file"), ("settings", "voice_offset"),
               ("settings", "voice_gain"), ("settings", "handle"), ("settings", "font_file"), ("settings", "fps"),
               ("ending", "intro"), ("ending", "question"), ("ending", "cta")]
TL_KEYS = ["mode", "hook", "hide_first_in_hook", "doubt", "doubt_sub", "compare_title", "reveal"]
EV_KEYS = ["enabled", "name", "year", "label", "color", "icon", "image"]
QZ_KEYS = ["title", "subtitle", "clues", "clue_seconds", "answer_intro", "answer", "answer_sub", "answer_image", "accent"]
MQ_KEYS = ["title", "subtitle", "questions", "think_seconds", "reveal_seconds", "accent", "style", "timer",
           "colors", "narration", "narration_gain"]
KEYS = {"quiz": QZ_KEYS, "mcq": MQ_KEYS}
MEDIA_FIELDS = {"music_file", "voice_file", "font_file", "image", "answer_image"}
MEDIA_LISTS = {"narration"}  # fields holding several files
DEFAULTS = {"colors": "style", "narration_gain": 1.0}  # for projects saved before these options existed

NARRATION_HELP = """**Read the questions aloud with your own recordings.** Name each clip after what it reads:
`q1` = question 1 · `q1a` `q1b` `q1c` `q1d` = its options (or `q1_1` … `q1_4`) · `q1e` = its explanation.
Any audio type works (mp3, wav, m4a…). Each question waits for its clips: options appear as they are read and
the countdown starts after the last one. The music gets quieter while a clip plays."""

HELP = """
### How to use
1. Pick a tab (**Timeline Collision**, **Clue Quiz** or **Multiple Choice**), or press **Load example** to start from a finished video.
2. Fill in the fields. They are grouped in small tabs on the left (content, 🎨 Style & sound, 🔚 Ending), so everything fits on one screen.
   The preview on the right **updates by itself** as you type. Move the time slider to check any moment.
3. Press **Render video**. The MP4 appears on the right (🎞️ Video tab) and is also saved in the `outputs` folder.
4. **Save project** keeps everything (including your images and audio) as a `.json` file you can reopen later.

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
**Narration:** in the 🎙️ Narration tab upload clips named `q1` (question 1), `q1a`…`q1d` (its options) and `q1e` (its explanation). Each question waits for its clips.
**Timers:** Ring, Pie, Bar, Hourglass, Digital (00:05), Segments (battery blocks), Fuse (burning fuse and bomb, with a sizzle sound).

### Timeline tips
- **Calendar years**: type BC years as negative numbers (2560 BC → `-2560`).
- **Years ago** mode is for deep time (dinosaurs, sharks, Earth): type `150000000` for 150 million years ago, `0` for today.
- 2 to 5 events; they are sorted by date automatically. The shortest gap gets the glowing highlight.
- Leave *Card subtitle* empty to show the year automatically.

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
        vals.append(p.get(sec, {}).get(k))
    if tpl == "timeline":
        d = p.get("timeline", {})
        vals += [d.get(k) for k in TL_KEYS]
        evs = d.get("events", [])
        for i in range(N_EVENTS):
            ev = evs[i] if i < len(evs) else {}
            for k in EV_KEYS:
                v = ev.get(k)
                if k == "enabled":
                    v = bool(ev) and ev.get("enabled", True)
                if k in MEDIA_FIELDS:
                    v = v if v and os.path.isfile(v) else None
                vals.append(v if v is not None else ("" if k in ("name", "label") else None))
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
            if ev.get("enabled") and str(ev.get("name") or "").strip():
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


# ------------------------------------------------------------------ actions
def make_actions(tpl):
    def preview(t, safe, *vals):
        try:
            img, dur = render_still(values_to_project(tpl, vals), t, safe, cached=True)
        except Exception as e:
            raise gr.Error(str(e))
        return img, f"Video length: **{dur:.1f} s**", gr.update(maximum=max(1.0, round(dur, 1)))

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
            progress(0, desc="Rendering…")

            def cb(x):
                try:
                    progress(x, desc="Rendering frames…")
                except Exception:
                    pass
            render_video(project, out, cb)
        except Exception as e:
            raise gr.Error(str(e))
        return out, f"✅ Video saved to `{os.path.relpath(out, ROOT)}`"

    def save(*vals):
        p = values_to_project(tpl, vals)
        for k in ("music_file", "voice_file", "font_file"):
            p["settings"][k] = _keep_media(p["settings"].get(k))
        if tpl == "timeline":
            for ev in p["timeline"]["events"]:
                ev["image"] = _keep_media(ev.get("image"))
        elif tpl == "quiz":
            p["quiz"]["answer_image"] = _keep_media(p["quiz"].get("answer_image"))
        stamp = _stamp()
        if tpl == "mcq":
            p["mcq"]["narration"] = _keep_media_list(p["mcq"].get("narration"),
                                                     os.path.join(MEDIA_DIR, f"narration_{stamp}"))
        path = os.path.join(PROJ_DIR, f"{tpl}_{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        return f"💾 Project saved to `{os.path.relpath(path, ROOT)}`"

    def load(file):
        path = file if isinstance(file, str) else getattr(file, "name", None)
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        if p.get("template", "timeline") != tpl:
            raise gr.Error(f"This is a '{p.get('template')}' project — open it in its own tab.")
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
            with gr.Row():
                handle = gr.Textbox(value="@Ma3loomaFast", label="Channel handle (ending)")
                font_file = gr.File(type="filepath", file_types=[".ttf", ".otf"], label="Custom font (optional)")
            with gr.Row():
                music = gr.Dropdown(MOODS, value="Tension", label="Built-in music mood")
                music_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Music volume")
            with gr.Row():
                voice_offset = gr.Number(value=0.5, label="Voice starts at (seconds)")
                voice_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Voice volume")
            with gr.Row():
                music_file = gr.Audio(type="filepath", label="Or your own music (optional)")
                voice_file = gr.Audio(type="filepath", label="Voiceover (optional)")
    return dict(theme=theme, lang=lang, fps=fps, handle=handle, font_file=font_file, music=music,
                music_gain=music_gain, music_file=music_file, voice_offset=voice_offset, voice_gain=voice_gain,
                voice_file=voice_file)


def ending_tab():
    with gr.Tab("🔚 Ending"):
        with gr.Column(elem_classes="pane"):
            gr.Markdown("**Ending card** — teases the next episode")
            e_intro = gr.Textbox(label="Small intro line", rtl=True)
            e_q = gr.Textbox(lines=3, max_lines=4, label="Question (1–3 lines, tags allowed)", rtl=True)
            e_cta = gr.Textbox(label="Call to action", rtl=True)
    return e_intro, e_q, e_cta


def shared_fields(st, ending):
    """Shared controls in SHARED_KEYS order."""
    return [st["theme"], st["lang"], st["music"], st["music_gain"], st["music_file"], st["voice_file"],
            st["voice_offset"], st["voice_gain"], st["handle"], st["font_file"], st["fps"], *ending]


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


def build_ui():
    kw = {"css": CSS} if "css" in inspect.signature(gr.Blocks.__init__).parameters else {}
    with gr.Blocks(title="Video Studio", **kw) as demo:
        gr.Markdown("## 🎬 Video Studio <small>— the preview on the right updates live as you edit</small>",
                    elem_id="app-title")
        with gr.Tab("⏳ Timeline Collision"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=420):
                    tl_proj = project_bar()
                    with gr.Tabs():
                        with gr.Tab("📝 Story"):
                            with gr.Column(elem_classes="pane"):
                                mode = gr.Radio([("Calendar years (BC = negative)", "calendar"),
                                                 ("Years ago (deep time)", "ago")], value="calendar", label="Time mode")
                                hook = gr.Textbox(lines=3, max_lines=5, rtl=True,
                                                  label="Hook (first 2.5 s) — the surprising claim")
                                hide_first = gr.Checkbox(value=True,
                                                         label="Hide the oldest event in the hook, reveal it on zoom-out")
                                with gr.Row():
                                    doubt = gr.Textbox(label="Doubt word", rtl=True)
                                    doubt_sub = gr.Textbox(label="Doubt subtitle", rtl=True)
                                compare_title = gr.Textbox(label="Comparison title", rtl=True)
                                reveal = gr.Textbox(lines=2, max_lines=4, label="Reveal (after the bass hit)", rtl=True)
                        with gr.Tab("🗓️ Events"):
                            ev_fields = []
                            with gr.Tabs():
                                for i in range(N_EVENTS):
                                    with gr.Tab(f"Event {i + 1}"):
                                        with gr.Column(elem_classes="pane"):
                                            with gr.Row():
                                                en = gr.Checkbox(value=i < 3, label="Use", scale=1, min_width=70)
                                                nm = gr.Textbox(label="Name", rtl=True, scale=3)
                                                yr = gr.Number(label="Year", scale=2)
                                            with gr.Row():
                                                lb = gr.Textbox(label="Card subtitle (optional)", rtl=True)
                                                cl = gr.Dropdown(COLOR_NAMES, value=["sand", "gold", "blue", "green", "pink"][i],
                                                                 allow_custom_value=True, label="Color (name or #hex)")
                                                ic = gr.Dropdown(ICON_NAMES, value="none", label="Icon")
                                            im = gr.Image(type="filepath", height=170,
                                                          label="Or a picture (optional, replaces the icon)")
                                    ev_fields += [en, nm, yr, lb, cl, ic, im]
                        tl_st = style_tab()
                        tl_end = ending_tab()
                    tl_fields = (shared_fields(tl_st, tl_end)
                                 + [mode, hook, hide_first, doubt, doubt_sub, compare_title, reveal] + ev_fields)
                tl_pv = preview_panel("timeline")
            wire(tl_proj, tl_pv, tl_fields)

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
                                                       "option. Optional explanation line starting with >. Leave an EMPTY "
                                                       "line between questions (max 10).")
                        with gr.Tab("⏱️ Design & timing"):
                            with gr.Column(elem_classes="pane"):
                                with gr.Row():
                                    m_style = gr.Dropdown(STYLE_NAMES, value="Game Show", label="Design style")
                                    m_timer = gr.Dropdown(TIMER_NAMES, value="Ring", label="Timer type")
                                    m_acc = gr.Dropdown(COLOR_NAMES, value="gold", allow_custom_value=True,
                                                        label="Accent color")
                                with gr.Row():
                                    m_think = gr.Slider(2, 10, value=5, step=0.5, label="Seconds to think (countdown)")
                                    m_rev = gr.Slider(1.5, 5, value=2.8, step=0.1, label="Seconds to show the answer")
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
                        mq_st = style_tab()
                        mq_end = ending_tab()
                    mq_fields = shared_fields(mq_st, mq_end) + [m_title, m_sub, m_qs, m_think, m_rev, m_acc, m_style,
                                                                 m_timer, m_colors, m_narr, m_narr_gain]
                mq_pv = preview_panel("mcq")
            wire(mq_proj, mq_pv, mq_fields)
            gr.on(triggers=[m_narr.change, m_qs.change], fn=narration_report, inputs=[m_narr, m_qs],
                  outputs=m_narr_info, trigger_mode="always_last", show_progress="hidden")

        with gr.Tab("📘 Help"):
            gr.Markdown(HELP)

        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["timeline"][2]), "timeline"), None, tl_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["quiz"][2]), "quiz"), None, qz_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["mcq"][2]), "mcq"), None, mq_fields)
    return demo


def launch_kwargs():
    """Gradio 6 takes css in launch(); Gradio 5 takes it in Blocks()."""
    return {"css": CSS} if "css" in inspect.signature(gr.Blocks.launch).parameters else {}


if __name__ == "__main__":
    build_ui().queue().launch(inbrowser=True, **launch_kwargs())
