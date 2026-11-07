# Video Studio

Gradio app (`app.py`) that renders 1080x1920 animated Shorts (YouTube Shorts / TikTok / Reels) with Pillow + NumPy + FFmpeg.

## Layout
- `engine/templates/` — `timeline.py` (Timeline Collision), `quiz.py` (Clue Quiz), `mcq.py` (Multiple Choice); registered in `engine/templates/__init__.py`
- `engine/core.py` — drawing, text (Arabic shaping), themes, easing, encoding
- `engine/audio.py` — synthesized SFX, music beds, voiceover ducking, mixing
- `engine/mcq_styles.py` — MCQ design styles; `engine/timers.py` — countdown timer designs
- `engine/title_fx.py` — MCQ animated opening title (`mcq.title_style`: `Fancy` default / `Simple` = classic pop-in)
- `engine/header_fx.py` — MCQ "Question i of n" header (`mcq.header_style`: `Fancy` default = glass pill + filling progress bar / `Simple` = flat pill + dots); `mcq.number_style` decorates its numbers (`plain` / `coin` / `circles` / `ring` / `gem` / `score`)
- `engine/quiz_fx.py` — MCQ extra animations, `mcq.fx` list: `lockin`, `confetti`, `wipe`, `final` (last question
  starts `FINAL_LEN` later via `q["pre"]`), `levels` (score-levels ending, ending lasts `LEVELS_END`); plus the
  per-question difficulty badge (`! easy|medium|hard` line in the questions text / `Difficulty` column in Excel)
- `engine/layouts.py` — MCQ screen layouts (`mcq.layout`): `Standard` (cards, drawn in mcq.py), `Exam paper`
  (ruled sheet on a desk, red-pen marking), `Islamic` (emerald/gold, mihrab-arch card); a layout draws background +
  question + timer, mcq.py `_layout_question` adds the shared overlays (difficulty, confetti, final ribbon)
- `engine/icons.py` — icons + event card; `engine/strings.py` — Arabic/English wording
- `engine/countries.py` — country names/flags/outlines (`data/`, built by `tools/build_countries.py`), true-size maps
- Timeline modes: `calendar`, `ago`, `scale` (number line with `unit`); options `maps` (true-size map scene) and `guess`
- `engine/batch.py` — MCQ from an Excel/CSV sheet: parse rows + audio, split into N-question videos
- `engine/tl_batch.py` — Timeline from an Excel/CSV sheet: one row = one video (countries + values + texts);
  template `projects/countries_template.xlsx`
- Timeline options `intro` (`hook` / `vs` / `globe`), `map_style` (`auto` / `overlay` / `tiles` / `side`),
  `polish` and `finish` (`engine/finish.py`: camera drift / push-ins; glow, grain, vignette, light leaks)
- `engine/globe.py` — real-Earth globe intro from `data/earth.jpg` (NASA Blue Marble, public domain); in
  `timeline.py` the globe intro lasts `GLOBE_LEN` and the rest of the video is shifted by `self.off` (frames + sounds)
- `engine/render.py` renders frames on several processes (`frame_stream`); templates' `render(t)` must depend only on t
- `engine/render.py` — build / render_still / render_clip / render_video
- `projects/example_*.json` — example projects (same format the app saves)

## Rules
- Arabic text must stay right-to-left and correctly joined (RAQM when available, else arabic-reshaper + python-bidi fallback in `core._prep`).
- Keep changes minimal and consistent with the existing structure.
- The user runs it on Windows via `run_windows.bat` (venv + `requirements.txt`); avoid heavy new dependencies.
- A new template needs: `NAME`, `EXAMPLE`, a class with `base_duration`, `dur`, `fps`, `silences`, `render(t)` and `sound(mixer)`, plus a tab in `app.py`.

## Testing a change
```
python render_cli.py projects/example_mcq.json --still 6      # one frame -> outputs/
python render_cli.py projects/example_timeline.json           # full MP4
```
Look at rendered frames to check layout, especially Arabic text.
