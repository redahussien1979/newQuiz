# Video Studio

Gradio app (`app.py`) that renders 1080x1920 animated Shorts (YouTube Shorts / TikTok / Reels) with Pillow + NumPy + FFmpeg.

## Layout
- `engine/templates/` — `timeline.py` (Timeline Collision), `quiz.py` (Clue Quiz), `mcq.py` (Multiple Choice),
  `vocab.py` (English Words); registered in `engine/templates/__init__.py`
- `engine/core.py` — drawing, text (Arabic shaping), themes, easing, encoding
- `engine/audio.py` — synthesized SFX, music beds, voiceover ducking, mixing
- `engine/mcq_styles.py` — MCQ design styles; `engine/timers.py` — countdown timer designs
- `engine/title_fx.py` — MCQ animated opening title (`mcq.title_style`: `Fancy` default / `Simple` = classic pop-in / `None` = no title: `q0` = 0, the first question stamps in at `SLAM` with a thud, no fade-in)
- `engine/header_fx.py` — MCQ "Question i of n" header (`mcq.header_style`: `Fancy` default = glass pill + filling progress bar / `Simple` = flat pill + dots); `mcq.number_style` decorates its numbers (`plain` / `coin` / `circles` / `ring` / `gem` / `score`)
- `engine/quiz_fx.py` — MCQ extra animations, `mcq.fx` list: `lockin`, `confetti`, `wipe`, `final` (last question
  starts `FINAL_LEN` later via `q["pre"]`), `levels` (score-levels ending, ending lasts `LEVELS_END`); plus the
  per-question difficulty badge (`! easy|medium|hard` line in the questions text / `Difficulty` column in Excel)
- `engine/layouts.py` — MCQ screen layouts (`mcq.layout`): `Standard` (cards, drawn in mcq.py), `Exam paper`
  (ruled sheet on a desk, red-pen marking), `Islamic` (emerald/gold, mihrab-arch card); a layout draws background +
  question + timer, mcq.py `_layout_question` adds the shared overlays (difficulty, confetti, final ribbon)
- `engine/fonts.py` — font library: bundled `fonts/library/<Family>/` (OFL, Arabic+Latin and Latin display fonts),
  fonts added in the app (`DATA_DIR/fonts`) and the user's own folder (`DATA_DIR/fonts.json`); scan cached in
  `DATA_DIR/fonts_index.json`. `settings.font_file` = a family name (older projects: a file path; empty = Cairo).
  `core.get_font(size, weight, path)` picks the family file / variable instance per weight; `core._font_for(txt)`
  falls back to Cairo for text the font can't write. App: "🔤 Font" gallery in Style & sound (click a card)
- Excel batches: `batch.sheet_names` / `read_table(path, sheet)` / `pick(items, start, count)` — every batch tab has
  Sheet (tab) + Start at # + How many
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
- `engine/render.py` — build / render_still / render_clip / render_video / render_cover (templates with `cover_time`)
- `engine/templates/vocab.py` — English Words: groups (`GROUPS`: badge, colour, theme, `news` headline style) and item
  types `word` / `guess` / `reverse` / `mistake` / `proverb` / `idiom` written as `key: value` blocks (`parse_items`,
  `items_text`); an item may carry its own `group:`. Clips `w1` / `w1e` per item (scenes wait for them). Each scene
  is a list of elements laid out by `_stack` at the biggest of `SCALES` that fits between `TOP` and `BOTTOM` (Shorts
  safe area); IPA uses `fonts/NotoSans-Bold.ttf`. `engine/vocab_batch.py` — Excel rows -> items, split per group
  (template `projects/words_template.xlsx`)
- Vocab item type `list` = one page of 1-6 words (`- English = /ipa/ = Arabic` lines, optional `title:` /
  `subtitle:`), read in turn with clips `w<i>_<k>`; drawn by `engine/word_list.py` (`ListPage`): designs
  `list_style` Editorial (`list_highlight`) / Chalkboard (`chalk_board`, `chalk_mark`, `chalk_color`;
  font `fonts/library/PatrickHand`). Excel: Type = list, one word per row with its Audio;
  `vocab_batch.merge_lists` joins rows into pages (`list_size` words, a new Page title starts a page)
- `engine/templates/text.py` — 📖 English Texts (Textbook page): one paragraph read aloud from the user's recording
  (ElevenLabs word timings); words ink in as spoken (`vs`/`ve` per word), highlighted words get a marker swipe, fly
  into the Word Bank, Arabic writes in right-to-left. `text.words` = lines `word | start | end | highlighted | arabic`
  (same as Excel columns B-F); neighbouring rows with the same multi-word highlight = one phrase. Long text → pages
  (sentence breaks, per-page size, recording cut and delayed for the page turn: `shifts` / `cuts`) + recap page.
  Designs `text.style`: `textbook` (TextVideo = the shared engine) / `studio` / `exam` / `notebook` (subclasses only
  override look hooks: `_style`, `_background`, `_header`, `_band_layer`, `_make_mark`/`_draw_mark`, `_bank_rows`/
  `_draw_slot`, `_fly_back`, `_draw_final`); `make_video(project)` picks the class. Lines: `_break` = DP over word
  pieces (pyphen hyphenation, optional) for even justified lines, `_justify` adds a little letter-spacing;
  `_page_size` trades size against word-gap width. Optional `level` badge and `translation` card after the reading
  (Arabic justified with kashida: `_ar_justified`). A page = `base` (still parts) + `faded` / `ink` paragraph layers;
  per frame: focus band + dim of the other lines (`_focus`/`_dim`), the spoken word breathes (`_breathe`), flight
  trail, landing spring (`_spring`) + per-design `_burst`, camera push-in (`_camera`), waveform progress
  (`_build_wave`, real loudness or from the timings), page curl (`_turn`, numpy cylinder warp). Textbook only:
  `DROPCAP`, `SUP` (footnote numbers = bank numbers), textured multiply highlighter, page edges + `TAB`.
  Brand: `text.logo` (default `projects/brand/logolept_logo.png`), `brand_name`, `logo_shape` circle/plain →
  `_apply_brand` turns the small line into the brand row (`_Brand`: logo + name + small line + badge) on every page of
  every design and moves the page down; `logo_intro` = `_sting` (STING s, the whole timeline starts later via `lead`),
  `logo_end` = logo over the ending card. Page colour `brand` = Logolept red. Fonts: each design has `TITLE` /
  `BODY` / `ar_font`; the font picked in 🎨 Style & sound (`settings.font_file`) replaces them (`_apply_font`; Arabic
  only if the font has Arabic letters). The text starts under the waveform (`page_off` small; spare room at the bottom).
  Font `fonts/library/Literata`. `engine/text_batch.py` — workbook: every tab = one video (title / subtitle columns,
  recording named like the tab); template `projects/texts_template.xlsx`
- `engine/know_country/` — 🌍 Know a Country tab (not a template class: its own renderer). `video.py` = one Excel
  row -> one MP4 (scenes = list of (name, dur, cam_fn, draw_fn, sound cues); `render()` draws scenes on a spawn
  Pool, the main process only reads the row), `globe.py` = orthographic globe + vector borders (world raster cached
  in `DATA_DIR/cache`), `sound.py` = numpy-only SFX/music, `util.py` = text/chips/pins, `topo.py` = TopoJSON reader,
  `template.py` builds `projects/know_country_template.xlsx`; `data/` = countries.json, countries-50m.json, PNG flags/icons
- `projects/example_*.json` — example projects (same format the app saves); `projects/*_template.xlsx` — Excel templates
- `engine/userdata.py` — the user's work lives OUTSIDE the app folder (the user updates by replacing the folder with a
  new zip): `DATA_DIR` = Documents/Video Studio (or env `VS_DATA`) holds `projects/` (+ `media/`) and `outputs/`;
  `APP_PROJ_DIR` (app `projects/`) only holds shipped files. `rescue()` moves work older versions saved inside the app
  folder; `relink()` finds a project's media by name; `launch(allowed_paths=[DATA_DIR])` lets the browser show it

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
