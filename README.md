# 🎬 Video Studio

A local app that turns your facts into animated vertical videos (YouTube Shorts, TikTok, Reels, 1080×1920) with Arabic or English text, motion, sound effects and music, all generated on your own computer. No subscriptions and no watermark.

Three ready templates:

| Template | What it makes |
|---|---|
| **⏳ Timeline Collision** | 2–5 events on a flying timeline, year counters, comparison bars, a bass-hit reveal and an ending teaser. Works with calendar years (BC/AD) or deep time ("150 million years ago"). |
| **✅ Multiple Choice** | Up to 10 questions with 3 or 4 options each, a countdown ring with ticking, then the correct answer turns green with a "ding" and an optional explanation. |
| **❓ Clue Quiz** | One mystery answer revealed after 1–8 clues, each with a countdown bar and ticking sound, then a big reveal with confetti and an optional photo. |

---

## 1. Install (once)

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/.
   On Windows, tick **"Add python.exe to PATH"** in the installer.
2. Unzip this folder anywhere, for example `Documents\VideoStudio`.

## 2. Run

- **Windows:** double-click `run_windows.bat`
- **Mac / Linux:** run `./run_mac_linux.sh` in a terminal

The first run takes a few minutes while it downloads the packages. After that, it opens in your browser at http://127.0.0.1:7860. Everything runs offline on your machine; the browser is only the screen.

## 3. Make a video

1. Choose a tab, then press **✨ Load example** to see a finished project.
2. Change the texts, years, colors, icons and pictures. The controls are grouped in small tabs on the left, so the whole studio fits on one screen without scrolling.
3. Watch the preview on the right: it **updates by itself** as you type. Move the time slider to check any moment. Tick **Safe zone** to see where YouTube's buttons will cover the screen.
4. Press **🎬 Render video**. A 30-second video takes about 1–2 minutes. It plays in the app and is saved in the `outputs` folder.
5. Press **💾 Save project** to keep everything, including your pictures and audio, as a `.json` file in `projects`. Use **📂 Open project** to continue later.

### Previewing before you render
- The preview picture **updates automatically** whenever you change anything, and the **Preview time** slider always spans the whole video. Moving the slider is instant. You can untick *Live update* if your computer is slow and use **🔄 Refresh** instead.
- **▶️ Quick motion** makes a small 6-second clip, with sound, starting at the slider time. It's ready in a few seconds, so you can check the animation and timer before the full render.
- **🎬 Render video** makes the final full-quality MP4.
- While a clip or video is being made, both buttons are locked (so a double-click can't start it twice) and you can keep editing. When it's ready it plays by itself in the **🎞️ Video** tab; if something is wrong, a warning tells you what and the buttons unlock.

### Text tricks
- Multi-line fields: one row per line.
- Color a line by starting it with a tag: `[gold] text`, `[blue] text`, or `[#ff7755] text`.
  Available names: white, grey, sand, gold, blue, green, pink, red, purple, orange, cyan.

### Multiple Choice format
Write each question as a block, with an empty line between questions:
```
ما أكبر كوكب في المجموعة الشمسية؟
زحل
المشتري *
نبتون
> يتسع حجمه لأكثر من 1300 كوكب بحجم الأرض
```
- The first line is the question, followed by 3 or 4 options.
- Put `*` after the correct option.
- A line starting with `>` is the explanation shown after the reveal (optional).

**Design styles** (dropdown in the Multiple Choice tab):

| Style | Look |
|---|---|
| Classic | Always uses the colour Theme you chose in the "🎨 Style & sound" tab |
| Neon | Black grid, glowing neon outlines, outlined letters |
| Glass | Frosted see-through cards over moving colour blobs |
| Game Show | Deep blue spotlight rays, gold hexagon answer bars |
| Paper | Light cream page, bold black borders with hard shadows |
| Sunset | Orange-pink-purple gradient, white pill cards, floating bokeh |
| Minimal | Calm charcoal with fine grain, flat cards, thin grey lines — clean and modern |
| Luxury | Black and gold: framed page, pinstripes, cut-corner cards, slowly rising gold dust |
| Clean Light | Bright white/grey page with soft blue and teal light, white cards, coloured badges |
| Tech HUD | Dark navy dot grid, corner brackets and a moving scan line, glowing cyan cut-corner bars |
| Aurora | Starry night with slowly moving green, blue and violet aurora ribbons, see-through cards |
| Blueprint | Engineering blueprint: blue grid paper, drafting circle, white outline cards |

**Themes** (🎨 Style & sound tab, used by all three templates): Night Sky, Desert Night, Emerald, Deep Purple, Charcoal, Royal Blue, Ocean, Midnight Gold, Crimson, Slate, Aurora, Rose Wine and Cyber Night. They are all dark so white text stays easy to read; several add a soft coloured glow behind the content.

**Colours:** each style has its own colours. Choose **Theme colours** (⏱️ Design & timing tab) to keep the style's shapes, borders and glow but take the background and cards from your Theme.

**Narration for each question** (🎙️ Narration tab): upload your recordings, all at once, named after what they read:

| File name | Plays |
|---|---|
| `q1.mp3` | question 1 |
| `q1a.mp3` … `q1d.mp3` (or `q1_1` … `q1_4`, `q1-b`) | options A–D of question 1, each option appears as it is read |
| `q1e.mp3` | the explanation of question 1, after the reveal |

Each question waits for its clips (the countdown starts after the last option is read), the music ducks under them, and the tab lists which clips matched and warns about names it doesn't recognise. Saving the project copies the clips into `projects/media`.

**Timer types:** Ring, Pie, Bar, Hourglass, Digital (00:05), Segments (battery blocks) and Fuse (a burning fuse running to a bomb, with a sizzle sound). All of them turn red with faster, higher ticks in the last 2 seconds.

### Sound
- **Built-in moods** (Tension, Mystery, Calm, Pulse) are generated from scratch, so there are no copyright claims.
- **Your own music**: upload any mp3/wav. It loops automatically and still goes silent before the reveal.
- **Voiceover**: upload your recording. The music lowers automatically while you speak, and the video gets longer if your voice is longer than the animation.

---

## Every tool used

| Tool | What it does here |
|---|---|
| **Python** | The programming language everything is written in. |
| **Pillow** (PIL) | Draws every frame: backgrounds, cards, icons, text, glow and shadows. |
| **NumPy** | Math for gradients and all sound synthesis (whoosh, ticks, bass hit, riser, chime, music beds). |
| **FFmpeg** (via `imageio-ffmpeg`) | Encodes frames and audio into the MP4 (H.264 + AAC) and reads your mp3/wav files. Installed automatically. |
| **Gradio** | The browser interface (forms, preview, video player). |
| **arabic-reshaper + python-bidi** | Correct joined, right-to-left Arabic text on systems without native text shaping (usually Windows). |
| **fontTools** | Checks which Arabic letter forms the font has, so no letters show as boxes. |
| **Cairo font** (Google Fonts, OFL licence) | The Arabic/Latin typeface. You can upload any other .ttf in the app. |

### How a video is made
1. The template turns your inputs into a **timeline of scenes**: camera moves, text pop-ins, counters and bars, all driven by easing curves.
2. For every frame (30 per second) it draws the picture with Pillow and sends it to FFmpeg.
3. The same timeline places the sound effects, so every whoosh, tick and hit lands exactly on the motion.
4. FFmpeg joins the picture and sound into one MP4.

---

## Command line (optional)

```
python render_cli.py projects/example_timeline.json                 -> outputs/example_timeline.mp4
python render_cli.py projects/example_quiz.json outputs/quiz.mp4
python render_cli.py projects/example_timeline.json --still 12.5    -> one preview PNG
```

## Adding your own animation template

1. Copy `engine/templates/quiz.py` to a new file, for example `engine/templates/facts.py`.
2. Keep the same structure: `NAME`, `EXAMPLE`, and a class with `base_duration`, `dur`, `fps`, `silences`, `render(t)` (returns one frame) and `sound(mixer)`.
3. Register it in `engine/templates/__init__.py`.
4. Render it with `render_cli.py` right away. To get a tab in the app, add one in `app.py` following the Clue Quiz tab.

Reusable building blocks in `engine/core.py`: `text_img`, `paste`, `draw_scene`, `draw_ending`, `make_bg`, `Stars`, the easing functions, and themes. `engine/icons.py` has the icon set and the event card. `engine/audio.py` has all the sound effects.

## Folder map

```
app.py               browser app
render_cli.py        command-line renderer
engine/core.py       drawing, text, themes, encoding
engine/audio.py      sound effects, music beds, voice, mixing
engine/icons.py      icons + event card
engine/strings.py    Arabic/English wording, year & number formatting
engine/templates/    timeline.py, quiz.py, mcq.py (add yours here)
fonts/               Cairo.ttf + licence
projects/            saved projects (+ media/ for your pictures/audio)
outputs/             rendered videos
```

## Troubleshooting
- **"Python is required"**: install Python 3.10+ and tick "Add to PATH", then run the launcher again.
- **Port already in use**: close the other Video Studio window, or run `python app.py` after stopping it.
- **Rendering is slow**: 60 FPS takes twice as long as 30 FPS. 30 FPS is standard for Shorts.
