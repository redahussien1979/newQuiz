"""Video Studio — browser app for making animated Shorts.

Run:  python app.py   (opens http://127.0.0.1:7860 in your browser)
"""
import copy
import datetime as dt
import json
import os
import shutil

import gradio as gr

from engine.audio import MOODS
from engine.core import COLOR_NAMES, THEME_NAMES
from engine.icons import ICON_NAMES
from engine.mcq_styles import STYLE_NAMES
from engine.timers import TIMER_NAMES
from engine.render import render_clip, render_still, render_video
from engine.templates import TEMPLATES

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
MQ_KEYS = ["title", "subtitle", "questions", "think_seconds", "reveal_seconds", "accent", "style", "timer"]
KEYS = {"quiz": QZ_KEYS, "mcq": MQ_KEYS}
MEDIA_FIELDS = {"music_file", "voice_file", "font_file", "image", "answer_image"}

HELP = """
### How to use
1. Pick a tab (**Timeline Collision** or **Clue Quiz**), or press **Load example** to start from a finished video.
2. Fill in the fields. Use **Preview frame** with the time slider to check any moment instantly.
3. Press **Render video**. The MP4 appears on the right and is also saved in the `outputs` folder.
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

**Design styles:** Classic (uses your Theme), Neon, Glass, Game Show, Paper (light), Sunset.
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
- The preview picture **updates automatically** whenever you change anything. Move the **Preview time** slider to look at any moment.
- **▶️ Quick motion preview** makes a small 6-second clip, with sound, starting at the slider time. It's ready in a few seconds, so you can check the animation and timer before the full render.
- **🎬 Render video** makes the final full-quality MP4.

### Shorts safe zone
Tick **Show safe zone** in the preview: red areas are covered by YouTube/TikTok buttons and captions, so keep important text out of them.
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
        vals += [d.get(k) if k not in MEDIA_FIELDS or (d.get(k) and os.path.isfile(d.get(k))) else None
                 for k in KEYS[tpl]]
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


def _stamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


# ------------------------------------------------------------------ actions
def make_actions(tpl):
    def preview(t, safe, *vals):
        try:
            img, dur = render_still(values_to_project(tpl, vals), t, safe)
        except Exception as e:
            raise gr.Error(str(e))
        return img, f"Video length: **{dur:.1f} s**"

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
        return out, f"Saved to `{out}`"

    def save(*vals):
        p = values_to_project(tpl, vals)
        for k in ("music_file", "voice_file", "font_file"):
            p["settings"][k] = _keep_media(p["settings"].get(k))
        if tpl == "timeline":
            for ev in p["timeline"]["events"]:
                ev["image"] = _keep_media(ev.get("image"))
        elif tpl == "quiz":
            p["quiz"]["answer_image"] = _keep_media(p["quiz"].get("answer_image"))
        path = os.path.join(PROJ_DIR, f"{tpl}_{_stamp()}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        return path

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
def shared_panel():
    with gr.Accordion("🎨 Style, sound & ending", open=False):
        with gr.Row():
            theme = gr.Dropdown(THEME_NAMES, value="Night Sky", label="Theme")
            lang = gr.Radio([("العربية", "ar"), ("English", "en")], value="ar", label="Language of auto texts")
            fps = gr.Radio([30, 60], value=30, label="FPS")
        with gr.Row():
            music = gr.Dropdown(MOODS, value="Tension", label="Built-in music mood")
            music_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Music volume")
            music_file = gr.Audio(type="filepath", label="Or your own music (optional)")
        with gr.Row():
            voice_file = gr.Audio(type="filepath", label="Voiceover (optional)")
            with gr.Column():
                voice_offset = gr.Number(value=0.5, label="Voice starts at (seconds)")
                voice_gain = gr.Slider(0, 2, value=1.0, step=0.05, label="Voice volume")
        with gr.Row():
            handle = gr.Textbox(value="@Ma3loomaFast", label="Channel handle (ending)")
            font_file = gr.File(type="filepath", file_types=[".ttf", ".otf"], label="Custom font (optional)")
        gr.Markdown("**Ending card** — teases the next episode")
        with gr.Row():
            e_intro = gr.Textbox(label="Small intro line", rtl=True)
            e_q = gr.Textbox(lines=2, label="Question (1–3 lines, tags allowed)", rtl=True)
            e_cta = gr.Textbox(label="Call to action", rtl=True)
    return [theme, lang, music, music_gain, music_file, voice_file, voice_offset, voice_gain,
            handle, font_file, fps, e_intro, e_q, e_cta]


def action_bar(tpl, fields):
    preview, render, save, load, example, clip = make_actions(tpl)
    with gr.Row():
        ex_btn = gr.Button("✨ Load example")
        open_btn = gr.UploadButton("📂 Open project", file_types=[".json"])
        save_btn = gr.Button("💾 Save project")
    saved = gr.File(label="Saved project", visible=True)
    with gr.Row():
        t = gr.Slider(0, 60, value=3.0, step=0.1, label="Preview time (s)")
        safe = gr.Checkbox(value=False, label="Show safe zone")
    with gr.Row():
        pv_btn = gr.Button("🖼️ Preview frame")
        clip_btn = gr.Button("▶️ Quick motion preview (6 s)")
        rd_btn = gr.Button("🎬 Render video", variant="primary")
    auto = gr.Checkbox(value=True, label="Auto-refresh the preview picture when I change something")
    info = gr.Markdown()
    return dict(ex=ex_btn, open=open_btn, save=save_btn, saved=saved, t=t, safe=safe, pv=pv_btn, rd=rd_btn,
                clip=clip_btn, auto=auto, info=info, fns=(preview, render, save, load, example, clip))


def wire(bar, fields, img_out, vid_out):
    preview, render, save, load, example, clip = bar["fns"]
    pv_in = [bar["t"], bar["safe"]] + fields
    pv_out = [img_out, bar["info"]]

    def auto_preview(on, *args):
        if not on:
            return gr.update(), gr.update()
        try:
            return preview(*args)
        except Exception as e:  # half-typed input: keep the last good picture
            return gr.update(), f"⚠️ {e}"

    gr.on(triggers=[c.change for c in [bar["t"], bar["safe"]] + fields], fn=auto_preview,
          inputs=[bar["auto"]] + pv_in, outputs=pv_out, trigger_mode="always_last", show_progress="hidden")
    bar["ex"].click(example, None, fields)
    bar["open"].upload(load, bar["open"], fields)
    bar["save"].click(save, fields, bar["saved"])
    bar["pv"].click(preview, pv_in, pv_out)
    bar["clip"].click(clip, [bar["t"]] + fields, [vid_out, bar["info"]])
    bar["rd"].click(render, fields, [vid_out, bar["info"]])


def build_ui():
    tl_ex = TEMPLATES["timeline"][2]
    with gr.Blocks(title="Video Studio") as demo:
        gr.Markdown("# 🎬 Video Studio\nAnimated Shorts from your own facts — timeline collisions, clue quizzes and multiple-choice quizzes.")
        with gr.Tab("⏳ Timeline Collision"):
            with gr.Row():
                with gr.Column(scale=3):
                    shared_tl = shared_panel()
                    mode = gr.Radio([("Calendar years (BC = negative)", "calendar"), ("Years ago (deep time)", "ago")],
                                    value="calendar", label="Time mode")
                    ev_fields = []
                    for i in range(N_EVENTS):
                        with gr.Accordion(f"Event {i + 1}", open=i < 3):
                            with gr.Row():
                                en = gr.Checkbox(value=i < 3, label="Use", scale=1)
                                nm = gr.Textbox(label="Name", rtl=True, scale=3)
                                yr = gr.Number(label="Year", scale=2)
                            with gr.Row():
                                lb = gr.Textbox(label="Card subtitle (optional)", rtl=True)
                                cl = gr.Dropdown(COLOR_NAMES, value=["sand", "gold", "blue", "green", "pink"][i],
                                                 allow_custom_value=True, label="Color (name or #hex)")
                                ic = gr.Dropdown(ICON_NAMES, value="none", label="Icon")
                            im = gr.Image(type="filepath", label="Or a picture (optional, replaces the icon)", height=140)
                        ev_fields += [en, nm, yr, lb, cl, ic, im]
                    hook = gr.Textbox(lines=3, label="Hook (first 2.5 s) — the surprising claim", rtl=True)
                    hide_first = gr.Checkbox(value=True, label="Hide the oldest event in the hook, reveal it on zoom-out")
                    with gr.Row():
                        doubt = gr.Textbox(label="Doubt word", rtl=True)
                        doubt_sub = gr.Textbox(label="Doubt subtitle", rtl=True)
                    compare_title = gr.Textbox(label="Comparison title", rtl=True)
                    reveal = gr.Textbox(lines=2, label="Reveal (after the bass hit)", rtl=True)
                    tl_fields = shared_tl + [mode, hook, hide_first, doubt, doubt_sub, compare_title, reveal] + ev_fields
                    tl_bar = action_bar("timeline", tl_fields)
                with gr.Column(scale=2):
                    tl_img = gr.Image(label="Preview", type="pil", height=640)
                    tl_vid = gr.Video(label="Rendered video", height=640)
            wire(tl_bar, tl_fields, tl_img, tl_vid)

        with gr.Tab("❓ Clue Quiz"):
            with gr.Row():
                with gr.Column(scale=3):
                    shared_qz = shared_panel()
                    q_title = gr.Textbox(label="Title / question", rtl=True)
                    q_sub = gr.Textbox(label="Subtitle", rtl=True)
                    q_clues = gr.Textbox(lines=6, label="Clues — one per line, hardest first (max 8)", rtl=True)
                    q_secs = gr.Slider(2, 8, value=4, step=0.5, label="Seconds per clue")
                    with gr.Row():
                        q_ai = gr.Textbox(label="Answer intro", rtl=True)
                        q_ans = gr.Textbox(label="Answer", rtl=True)
                        q_asub = gr.Textbox(label="Answer subtitle", rtl=True)
                    with gr.Row():
                        q_img = gr.Image(type="filepath", label="Answer picture (optional)", height=160)
                        q_acc = gr.Dropdown(COLOR_NAMES, value="gold", allow_custom_value=True, label="Accent color")
                    qz_fields = shared_qz + [q_title, q_sub, q_clues, q_secs, q_ai, q_ans, q_asub, q_img, q_acc]
                    qz_bar = action_bar("quiz", qz_fields)
                with gr.Column(scale=2):
                    qz_img = gr.Image(label="Preview", type="pil", height=640)
                    qz_vid = gr.Video(label="Rendered video", height=640)
            wire(qz_bar, qz_fields, qz_img, qz_vid)

        with gr.Tab("✅ Multiple Choice"):
            with gr.Row():
                with gr.Column(scale=3):
                    shared_mq = shared_panel()
                    m_title = gr.Textbox(label="Title", rtl=True)
                    m_sub = gr.Textbox(label="Subtitle", rtl=True)
                    m_qs = gr.Textbox(lines=14, rtl=True, label="Questions — see format below",
                                      info="Question line, then 3 or 4 option lines. Put * after the correct option. "
                                           "Optional explanation line starting with >. Leave an EMPTY line between questions (max 10).")
                    with gr.Row():
                        m_think = gr.Slider(2, 10, value=5, step=0.5, label="Seconds to think (countdown)")
                        m_rev = gr.Slider(1.5, 5, value=2.8, step=0.1, label="Seconds to show the answer")
                        m_acc = gr.Dropdown(COLOR_NAMES, value="gold", allow_custom_value=True, label="Accent color")
                    with gr.Row():
                        m_style = gr.Dropdown(STYLE_NAMES, value="Game Show", label="Design style",
                                              info="Classic uses the Theme from 'Style, sound & ending'")
                        m_timer = gr.Dropdown(TIMER_NAMES, value="Ring", label="Timer type")
                    mq_fields = shared_mq + [m_title, m_sub, m_qs, m_think, m_rev, m_acc, m_style, m_timer]
                    mq_bar = action_bar("mcq", mq_fields)
                with gr.Column(scale=2):
                    mq_img = gr.Image(label="Preview", type="pil", height=640)
                    mq_vid = gr.Video(label="Rendered video", height=640)
            wire(mq_bar, mq_fields, mq_img, mq_vid)

        with gr.Tab("📘 Help"):
            gr.Markdown(HELP)

        demo.load(lambda: project_to_values(copy.deepcopy(tl_ex), "timeline"), None, tl_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["quiz"][2]), "quiz"), None, qz_fields)
        demo.load(lambda: project_to_values(copy.deepcopy(TEMPLATES["mcq"][2]), "mcq"), None, mq_fields)
    return demo


if __name__ == "__main__":
    build_ui().queue().launch(inbrowser=True)
