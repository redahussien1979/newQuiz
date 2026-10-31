# Video Studio

Gradio app (`app.py`) that renders 1080x1920 animated Shorts (YouTube Shorts / TikTok / Reels) with Pillow + NumPy + FFmpeg.

## Layout
- `engine/templates/` — `timeline.py` (Timeline Collision), `quiz.py` (Clue Quiz), `mcq.py` (Multiple Choice); registered in `engine/templates/__init__.py`
- `engine/core.py` — drawing, text (Arabic shaping), themes, easing, encoding
- `engine/audio.py` — synthesized SFX, music beds, voiceover ducking, mixing
- `engine/mcq_styles.py` — MCQ design styles; `engine/timers.py` — countdown timer designs
- `engine/icons.py` — icons + event card; `engine/strings.py` — Arabic/English wording
- `engine/batch.py` — MCQ from an Excel/CSV sheet: parse rows + audio, split into N-question videos
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
