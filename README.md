# 🎬 Video Studio

A local app that turns your facts into animated vertical videos (YouTube Shorts, TikTok, Reels, 1080×1920) with Arabic or English text, motion, sound effects and music, all generated on your own computer. No subscriptions and no watermark.

Four ready templates:

| Template | What it makes |
|---|---|
| **⏳ Timeline Collision** | 2–5 events on a flying timeline, year counters, comparison bars, a bass-hit reveal and an ending teaser. Works with calendar years (BC/AD), deep time ("150 million years ago") or a **number line in any unit** (km², metres, °C, $…). Pick a **country** per event for its flag and map, add a **true-size map scene** (countries drawn at their real relative size) and a **guess moment** (3 choices + timer). **📊 Excel batch:** one row per video — render many country comparisons at once from `projects/countries_template.xlsx`. |
| **✅ Multiple Choice** | Up to 10 questions with 2–4 options each, a countdown timer with ticking, then the correct answer turns green with a "ding" and an optional explanation. Optional narration clips, and many videos at once from an Excel sheet. |
| **❓ Clue Quiz** | One mystery answer revealed after 1–8 clues, each with a countdown bar and ticking sound, then a big reveal with confetti and an optional photo. |
| **🔤 English Words** | English lessons for Arabic speakers in groups (General words, Political words, Proverbs, Idioms, Common mistakes or your own), each with its own badge, colour and theme. Word cards with IPA, guess-the-meaning quizzes, common mistakes, proverbs with their Arabic equivalent and idioms, your own pronunciation audio per word, a recap and a cover picture. **📊 Excel batch:** one row per word, split into one video per group. |
| **📰 English in News** | Upload a short news clip: ElevenLabs writes its transcript, you click the key words and type their Arabic meanings. The video shows big word-by-word subtitles, a card with each key word and its meaning when it is said, and a recap of all the words. Five looks (Pop, Breaking, Studio, TV broadcast, Newspaper). Landscape clips work best. |

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
4. Press **🎬 Render video**. A 30-second video takes about 1–2 minutes. It plays in the app and is saved in **Documents\Video Studio\outputs**.
5. Press **💾 Save project** to keep everything, including your pictures and audio, as a `.json` file in **Documents\Video Studio\projects**. Use **📂 Open project** to continue later.

### Where your work is saved
Your projects, their pictures and audio, and your videos are kept **outside the app folder**, in your Documents folder:
```
Documents\Video Studio\projects\        saved projects (.json)
Documents\Video Studio\projects\media\  pictures and audio, copied in when you save a project
Documents\Video Studio\outputs\          videos, cover pictures and Excel batches
```
So you can **delete the app folder and unzip a new version** at any time: nothing of yours is lost. The exact folder is shown at the top of the app and in the black window when it starts.
- **Updating from a version that saved inside the app folder (one time only):** copy the old app folder's `projects` and `outputs` folders into the new app folder before you start it. On start it copies your saved projects, pictures and audio and moves your videos to `Documents\Video Studio` (the example projects stay). From then on, updates never touch your work.
- **📂 Open project** finds the pictures and audio of a project by name in `projects\media` if they are no longer where the project remembers them.
- To use another folder (for example on another drive), set the environment variable `VS_DATA` to it.

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

Each question waits for its clips (the countdown starts after the last option is read), the music ducks under them, and the tab lists which clips matched and warns about names it doesn't recognise. Saving the project copies the clips into `Documents\Video Studio\projects\media`.

**Many videos from an Excel sheet** (📊 Excel batch tab):
1. Press **⬇️ Excel template** (also in `projects/questions_template.xlsx`) and fill one question per row:
   `Question · Option A · Option B · Option C · Option D · Correct · Explanation`, plus optional audio columns
   `Question audio · A audio · B audio · C audio · D audio · Explanation audio`. Arabic headers (السؤال، الخيار أ، الإجابة الصحيحة، الشرح، صوت السؤال …) work too.
   - **Correct**: A/B/C/D, أ/ب/ج/د, 1–4, or the exact text of the right option.
   - **Audio cells**: the clip's file name. Upload the clips in the tab, or type the folder that holds them (or put full paths in the cells).
2. Upload the sheet, choose **Questions per video** (1–10). 30 questions at 5 per video → 6 videos; a smaller remainder becomes the last video.
3. Optional **Title of each video** with `{n}` and `{total}`, e.g. `اختبر معلوماتك — الجزء {n} من {total}`.
   In the Title, Subtitle and Ending texts, `{count}` becomes the number of questions in that video (e.g. `حصلت عليها من {count}؟`).
4. Pick a video and press **📥 Load into editor** to preview it, then **🎬 Render all videos**. They are saved in `Documents\Video Studio\outputs\batch_<date>\` together with a project file for each video, which you can open later to change one video.
Rows with problems (no question, fewer than 2 options, unclear correct answer) are skipped and listed; a missing audio file is reported and the question is kept without it.

**Timer types:** Ring, Pie, Bar, Hourglass, Digital (00:05), Segments (battery blocks), Fuse (a burning fuse running to a bomb, with a sizzle sound), Neon Ring (glowing arc with a bright tip), Dots (a clock of 12 dots going dark), Flip Clock (cards that flip every second), Stopwatch (sweeping hand), Liquid (a glass draining with a wavy surface and bubbles) and Big Number (a huge number that pops in each second). All of them turn red with faster, higher ticks in the last 2 seconds.

**Timer effects** (⏱️ Design & timing, any mix, with every timer type): **Pulse** on every tick, **Glow** halo, **Ripple** wave from each tick, **Shake** in the last 3 seconds and a **Red flash** of the screen edges in the last 3 seconds.

### English Words
Pick a **group** (it sets the badge, colour and background) and write the items, one block each with an empty line
between them:
```
type: word
word: Sanctions
ipa: /ˈsæŋkʃənz/
pos: noun • اسم
meaning: عقوبات (على دولة أو جهة)
example: UN imposes new sanctions on the regime
example_ar: فرضت الأمم المتحدة عقوبات جديدة على النظام
also: embargo, penalties

type: guess
word: Ceasefire
- إعلان الحرب
- وقف إطلاق النار *
- انتخابات مبكرة
example: Both sides agreed to a ceasefire last night
```
| Type | What it shows |
|---|---|
| `word` | Word card: the word, 🔊 IPA, part of speech, Arabic meaning, example (the word is highlighted and underlined) with its translation, similar words. In **Political words** the example is a **BREAKING NEWS** headline with a news sting. |
| `guess` | Guess the meaning: 2–4 options, a countdown (any timer type), the right one lights up with a ding, then the example. In Proverbs it asks for the Arabic proverb, in Common mistakes "Which one is correct?". |
| `reverse` | The same, Arabic shown and English options ("How do you say it in English?"). |
| `mistake` | `wrong:` sentence struck out with a buzz → `right:` sentence with a ✔ → the rule (`meaning:`) → example. |
| `proverb` | The English proverb appears word by word → `literal:` translation → `equivalent:` the Arabic proverb in a gold card → `meaning:` → example. |
| `idiom` | The idiom → `literal:` meaning crossed out → the real `meaning:` (+ `note:`) → example. |

- **Type** can be left out: options make a guess, `wrong:` a mistake, `equivalent:` a proverb, `literal:` an idiom, anything else a word card. **➕ Add item** inserts an empty item of the chosen type; **🔁 Make all word cards** turns every guess into a word card.
- **Highlight:** the word is found in the example by itself (also *studies*, *procrastinated*…); put `*stars*` around other words to choose.
- **Audio (🎙️ tab):** clips named `w1` (item 1: the word, proverb or correct sentence) and `w1e` (its example). Each item waits for its clips, the 🔊 icon animates while the word plays and the music gets quieter.
- **Opening:** automatic title per group ("5 Political Words — كلمات تسمعها في الأخبار كل يوم!"), or your own (`{count}` = number of items), an optional lesson line (`English Lesson #{n}`) and, if you like, the first word shown faintly behind the title.
- **Ending:** a **recap** ("What did we learn today?") then your ending card. **Pace** (Slow / Normal / Fast) sets how long each line stays; 5 items take about 60 s at Normal.
- **Cover picture:** every render also saves `<video name> cover.png` (the opening title) for the Shorts / Reels thumbnail.
- **Excel batch:** download the template (an example row of every group and type), one item per row. **One group per video** makes separate videos for each group (15 political rows + 10 proverb rows at 5 per video = 3 + 2 videos); **In sheet order** keeps the rows in order and lets groups mix (every item keeps its own badge and colour). Lesson numbers count up from the number you choose.
- The videos are 1080 × 1920 MP4 (H.264 + AAC, fast start): ready for YouTube Shorts, Instagram Reels, Facebook Reels and TikTok. The preview warns when a video is longer than 60 s (keep Facebook Reels under 60 s).

### 🌍 Know a Country
A map-first explainer (about 90 s) made from **one Excel row**: a 3D globe flies to the country, then location and
neighbours (each neighbour outlined, with a flashing dot and its name), the capital, straight-line distances from
cities you choose, area and population (with their dates and sources), a **true-size comparison** (the country's
real outline is dragged onto 4–5 other countries), language and currency, top exports, and your facts.
- Download **⬇️ Excel template** in the tab. The **guide** sheet explains every column; the **areas** sheet holds the
  areas used in the comparisons (green rows are verified — check any other row before using it); the **cities**
  sheet holds the cities for the distances (add your own).
- Upload the sheet, pick a country (or **All rows**), press **🖼️ Quick check** for one picture, then
  **🎬 Render video**. A video takes about 15–25 minutes; it is saved in `Documents/Video Studio/outputs/`.
- Accuracy is yours: every figure shown comes from your sheet, with the date and source you type. Distances are
  calculated (great-circle, rounded to 10 km). Borders follow Natural Earth; use the **nearby** column to choose
  the neighbours yourself.
- The first render builds a world map cache (~70 MB) in `Documents/Video Studio/cache/`.

### Sound
- **Built-in music** is generated from scratch, so there are no copyright claims. **Quiz Show**, **Bright Pop**, **Lo-fi Chill**, **Epic** and **Ambient** are real music loops (chords, bass and drums); Tension, Mystery, Calm and Pulse are the original atmospheric drones.
- **Opening sound**: Bass hit, Cinematic boom, Swoosh + impact, Game show jingle, Sparkle, Deep drums or None.
- **Ticking sound** for every countdown: Classic, Clock, Wood block, Soft click, Digital beep, Heartbeat or None, with its own **Ticking volume** (0 = silent, 2 = double).
- Press **🔊 Listen** in 🎨 Style & sound to hear the opening, music and ticking together before rendering.
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
| **openpyxl** | Reads your Excel question sheets and writes the Excel template (Excel batch). |
| **Cairo font** (Google Fonts, OFL licence) | The Arabic/Latin typeface. You can upload any other .ttf in the app. |
| **Noto Sans Bold** (Google, OFL licence) | The IPA pronunciation in English Words (Cairo has no IPA letters). |

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
engine/countries.py  country names, flags, outlines, true-size map drawing
engine/tl_batch.py   Timeline videos from an Excel sheet (one row = one video)
engine/vocab_batch.py English Words videos from an Excel sheet (one row = one item, split per group)
engine/globe.py      real-Earth globe intro (data/earth.jpg)
engine/finish.py     motion polish (camera drift, push-ins) + cinematic finish (glow, grain, vignette, light leaks)
engine/strings.py    Arabic/English wording, year & number formatting
engine/templates/    timeline.py, quiz.py, mcq.py, vocab.py, text.py, news.py (add yours here)
engine/news_words.py 📰 English in News transcript editor (key words, phrases, Arabic meanings)
engine/know_country/ 🌍 Know a Country: video.py (scenes), globe.py (3D map), sound.py, template.py, data/
fonts/               Cairo.ttf, NotoSans-Bold.ttf (IPA) + licences
data/                countries.json (outlines) + flags/ — rebuilt with tools/build_countries.py
engine/userdata.py   where your work is saved (Documents/Video Studio) + moving it from older versions
projects/            example projects + Excel templates (shipped with the app)
outputs/             videos made with render_cli.py

Documents/Video Studio/projects/   your saved projects (+ media/ for their pictures/audio)
Documents/Video Studio/outputs/    videos rendered in the app
```

## Troubleshooting
- **"Python is required"**: install Python 3.10+ and tick "Add to PATH", then run the launcher again.
- **Port already in use**: close the other Video Studio window, or run `python app.py` after stopping it.
- **Rendering is slow**: 60 FPS takes twice as long as 30 FPS. 30 FPS is standard for Shorts. ✨ Motion polish and
  🎬 Cinematic finish roughly double the render time — switch them off for quick test renders. Videos are drawn on
  several CPU cores at once; set the environment variable `VS_WORKERS=1` to use a single core.

## Credits
- Country outlines: [Natural Earth](https://www.naturalearthdata.com) (public domain). Borders follow Natural Earth's
  choices; upload your own GeoJSON outline on an event to draw a country differently.
- Flags: [flagcdn.com](https://flagcdn.com) (public-domain flag images).
- Know a Country: map data from [world-atlas](https://github.com/topojson/world-atlas) (Natural Earth 1:50m,
  public domain), country facts from [mledoze/countries](https://github.com/mledoze/countries) (ODbL), flags from
  [flag-icons](https://github.com/lipis/flag-icons) (MIT), icons from [Tabler Icons](https://tabler.io/icons) (MIT).
- Earth image for the globe intro: NASA Earth Observatory, *Blue Marble: Next Generation* (public domain).
