"""Multiple Choice from a spreadsheet: read questions (and their audio clips) from Excel/CSV,
split them into several videos and build one ordinary MCQ project per video.

Sheet layout (first row = headers, English or Arabic, any order; see write_template()):
    Question | Option A | Option B | Option C | Option D | Correct | Difficulty | Explanation |
    Question audio | A audio | B audio | C audio | D audio | Explanation audio

- Difficulty (optional): Easy / Medium / Hard (or سهل / متوسط / صعب, or 1-3) -> badge with stars on the question.

- Correct: A/B/C/D, أ/ب/ج/د, 1-4, or the exact text of the right option (or end that option with *).
- Audio cells: a file name of an uploaded clip, a path relative to the audio folder, or a full path.
"""
import copy
import csv
import math
import os
import re
import shutil

from .strings import level_key

AUDIO_SLOTS = ["q", "a", "b", "c", "d", "e"]  # question, options A-D, explanation
MAX_PER_VIDEO = 10


# ------------------------------------------------------------------ headers
def _norm(s):
    s = str(s or "").strip().lower()
    s = re.sub(r"[إأآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[\s_\-.:()\[\]/#]+", "", s)


_ALIASES = {
    "question": ["question", "q", "questiontext", "السؤال", "سؤال", "نصالسؤال"],
    "opt0": ["optiona", "a", "choicea", "answera", "option1", "choice1", "الخيارا", "خيارا", "ا", "الخيار1", "خيار1"],
    "opt1": ["optionb", "b", "choiceb", "answerb", "option2", "choice2", "الخيارب", "خيارب", "ب", "الخيار2", "خيار2"],
    "opt2": ["optionc", "c", "choicec", "answerc", "option3", "choice3", "الخيارج", "خيارج", "ج", "الخيار3", "خيار3"],
    "opt3": ["optiond", "d", "choiced", "answerd", "option4", "choice4", "الخيارد", "خيارد", "د", "الخيار4", "خيار4"],
    "correct": ["correct", "correctanswer", "answer", "right", "rightanswer", "key", "الاجابه", "الاجابهالصحيحه",
                "الصحيح", "الجواب", "الجوابالصحيح"],
    "diff": ["difficulty", "level", "difficultylevel", "hardness", "الصعوبه", "مستويالصعوبه", "المستوي", "مستوي",
             "درجهالصعوبه"],
    "expl": ["explanation", "explain", "note", "fact", "info", "الشرح", "شرح", "التفسير", "تفسير", "معلومه"],
    "aud_q": ["questionaudio", "qaudio", "audio", "audioquestion", "questionsound", "صوتالسؤال", "صوت"],
    "aud_a": ["optionaaudio", "aaudio", "audioa", "choiceaaudio", "option1audio", "صوتا", "صوتالخيارا", "صوت1"],
    "aud_b": ["optionbaudio", "baudio", "audiob", "choicebaudio", "option2audio", "صوتب", "صوتالخيارب", "صوت2"],
    "aud_c": ["optioncaudio", "caudio", "audioc", "choicecaudio", "option3audio", "صوتج", "صوتالخيارج", "صوت3"],
    "aud_d": ["optiondaudio", "daudio", "audiod", "choicedaudio", "option4audio", "صوتد", "صوتالخيارد", "صوت4"],
    "aud_e": ["explanationaudio", "eaudio", "audioexplanation", "explainaudio", "صوتالشرح", "صوتالتفسير"],
}
_LOOKUP = {_norm(a): key for key, names in _ALIASES.items() for a in names}
# column order used when the sheet has no header row
_POSITIONAL = ["question", "opt0", "opt1", "opt2", "opt3", "correct", "expl",
               "aud_q", "aud_a", "aud_b", "aud_c", "aud_d", "aud_e", "diff"]
TEMPLATE_HEADERS = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct", "Difficulty", "Explanation",
                    "Question audio", "A audio", "B audio", "C audio", "D audio", "Explanation audio"]
LEVEL_NAMES = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


# ------------------------------------------------------------------ reading
def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).replace("\r", "\n").split())  # one line, single spaces


def sheet_names(path):
    """The tabs of an Excel workbook ([] for a CSV file or anything unreadable)."""
    if os.path.splitext(str(path))[1].lower() not in (".xlsx", ".xlsm"):
        return []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        try:  # hidden tabs (like the templates' dropdown lists) are left out
            return [ws.title for ws in wb.worksheets if getattr(ws, "sheet_state", "visible") == "visible"]
        finally:
            wb.close()
    except Exception:
        return []


def worksheet(wb, sheet=None):
    """The tab called `sheet`, or the first one when it is empty or not in this workbook."""
    return wb[sheet] if sheet and sheet in wb.sheetnames else wb.worksheets[0]


def pick(items, start=1, count=0):
    """Items start..start+count-1 (1-based); count 0 = all from start."""
    s = max(1, int(start or 1)) - 1
    n = max(0, int(count or 0))
    return items[s:s + n] if n else items[s:]


def pick_problems(problems, all_items, items):
    """Only the problems of the rows the chosen range covers (rows between the first and last kept item)."""
    if len(items) == len(all_items) or not items:
        return problems
    lo, hi = items[0]["row"], items[-1]["row"]
    out = []
    for p in problems:
        m = re.match(r"Row (\d+)", p)
        if not m or lo <= int(m.group(1)) <= hi:
            out.append(p)
    return out


def read_table(path, sheet=None):
    """Rows of one sheet of an .xlsx (the first, or the tab called `sheet`) or of a CSV file, as lists of strings."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError as e:
            raise RuntimeError("Reading Excel needs the 'openpyxl' package: run run_windows.bat again "
                               "(it installs it) or `pip install openpyxl`.") from e
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = worksheet(wb, sheet)
            rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
        return rows
    if ext in (".csv", ".txt", ".tsv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            text = f.read()
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [[_cell(v) for v in row] for row in csv.reader(text.splitlines(), dialect)]
    if ext == ".xls":
        raise ValueError("Old .xls files are not supported — in Excel use File › Save As › Excel Workbook (.xlsx).")
    raise ValueError(f"Unsupported file type '{ext}'. Use .xlsx or .csv.")


def _columns(header):
    cols = {}
    for i, h in enumerate(header):
        key = _LOOKUP.get(_norm(h))
        if key and key not in cols:
            cols[key] = i
    return cols


# ------------------------------------------------------------------ audio lookup
class AudioFinder:
    """Find a clip named in a cell: uploaded files (by name), the audio folder, or a full path."""

    def __init__(self, uploads=(), folder=""):
        self.by_name, self.by_stem = {}, {}
        for p in uploads or []:
            if p and os.path.isfile(str(p)):
                base = os.path.basename(str(p)).lower()
                self.by_name.setdefault(base, str(p))
                self.by_stem.setdefault(os.path.splitext(base)[0], str(p))
        self.folder = str(folder or "").strip().strip('"')

    def find(self, cell):
        name = str(cell or "").strip().strip('"')
        if not name:
            return None
        base = os.path.basename(name.replace("\\", "/")).lower()
        if base in self.by_name:
            return self.by_name[base]
        if base in self.by_stem:  # "q1" matches an uploaded "q1.mp3"
            return self.by_stem[base]
        for cand in ([os.path.join(self.folder, name)] if self.folder else []) + [name]:
            if os.path.isfile(cand):
                return cand
        if self.folder and os.path.isdir(self.folder):  # name without extension inside the folder
            for f in os.listdir(self.folder):
                if os.path.splitext(f)[0].lower() == base:
                    return os.path.join(self.folder, f)
        return None


# ------------------------------------------------------------------ parsing
_LETTERS = {"a": 0, "b": 1, "c": 2, "d": 3, "ا": 0, "ب": 1, "ج": 2, "د": 3, "1": 0, "2": 1, "3": 2, "4": 3}


def _clean_option(o):
    star = o.startswith("*") or o.endswith("*")
    o = o.strip("*").strip()
    while o.startswith((">", "»")):  # would read as an explanation line in the editor format
        o = o[1:].strip()
    return o, star


def parse_rows(rows, finder=None):
    """Turn sheet rows into questions. Returns (items, problems). Bad rows are skipped and reported."""
    finder = finder or AudioFinder()
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return [], ["The sheet is empty."]
    cols = _columns(rows[0])
    if "question" in cols:
        start = 1
    else:
        cols, start = {k: i for i, k in enumerate(_POSITIONAL)}, 0
    items, problems = [], []
    if not any(f"opt{k}" in cols for k in range(4)):
        return [], ["No option columns found — the first row should have headers like "
                    "Question, Option A, Option B, Option C, Option D, Correct (download the template)."]

    def get(row, key):
        i = cols.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    for n, row in enumerate(rows[start:], start + 1):
        where = f"Row {n}"
        q = get(row, "question")
        if not q:
            problems.append(f"{where}: no question text — skipped")
            continue
        opts, stars, slots = [], [], []
        for k in range(4):
            raw = get(row, f"opt{k}")
            if raw:
                o, star = _clean_option(raw)
                opts.append(o)
                stars.append(star)
                slots.append(k)
        if len(opts) < 2:
            problems.append(f"{where}: needs at least 2 options — skipped")
            continue
        correct = None
        key = get(row, "correct")
        if key:
            kn = _norm(key)
            if kn in _LETTERS and _LETTERS[kn] in slots:
                correct = slots.index(_LETTERS[kn])
            else:
                for i, o in enumerate(opts):
                    if _norm(o) == kn:
                        correct = i
                        break
        elif stars.count(True) == 1:
            correct = stars.index(True)
        if correct is None:
            problems.append(f"{where}: can't tell which option is correct "
                            f"({'“' + key + '”' if key else 'Correct column is empty'}) — skipped")
            continue
        audio, missing = {}, []
        wanted = [("q", "aud_q")] + [("abcd"[i], f"aud_{'abcd'[k]}") for i, k in enumerate(slots)] + [("e", "aud_e")]
        for slot, colkey in wanted:  # option clips follow the option's final position
            cell = get(row, colkey)
            if cell:
                path = finder.find(cell)
                if path:
                    audio[slot] = path
                else:
                    missing.append(cell)
        if missing:
            problems.append(f"{where}: audio not found: {', '.join(missing)} — question kept without "
                            f"{'it' if len(missing) == 1 else 'them'}")
        level = None
        try:
            level = level_key(get(row, "diff"))
        except ValueError as e:
            problems.append(f"{where}: {e} — shown without a difficulty badge")
        items.append(dict(row=n, q=q, opts=opts, correct=correct, expl=get(row, "expl"), level=level, audio=audio))
    return items, problems


def load_sheet(path, uploads=(), folder="", sheet=None, start=1, count=0):
    """Questions of one tab; only questions start..start+count-1 are kept (count 0 = all from start)."""
    all_items, problems = parse_rows(read_table(path, sheet), AudioFinder(uploads, folder))
    items = pick(all_items, start, count)
    return items, pick_problems(problems, all_items, items)


# ------------------------------------------------------------------ splitting
def split(items, per_video):
    per = max(1, min(MAX_PER_VIDEO, int(per_video or 5)))
    return [items[i:i + per] for i in range(0, len(items), per)]


def questions_text(items):
    """The editor's text format for a list of items."""
    blocks = []
    for it in items:
        lines = [it["q"]] + [o + (" *" if i == it["correct"] else "") for i, o in enumerate(it["opts"])]
        if it.get("level"):
            lines.append("! " + LEVEL_NAMES[it["level"]].lower())
        if it["expl"]:
            lines.append("> " + it["expl"])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def narration_files(items, folder):
    """Copy the part's clips into `folder` named q1, q1a … q1e so the MCQ template matches them."""
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    out = []
    for n, it in enumerate(items, 1):
        for slot, src in it["audio"].items():
            os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, f"q{n}{'' if slot == 'q' else slot}{os.path.splitext(src)[1].lower()}")
            shutil.copy2(src, dst)
            out.append(dst)
    return out


def fill_title(text, n, total):
    return str(text or "").replace("{n}", str(n)).replace("{total}", str(total))


NAME_MAX = 80  # characters; keeps full paths well under the Windows limit
_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f_]+')  # not allowed in Windows file names (+ underscores)
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def video_name(items, n, taken=None):
    """File name (no extension) for one video: the text of its first question, as plain text.

    Colour tags like '[gold]' and characters Windows does not allow (and underscores) are removed,
    `{count}` becomes the number of questions, the name is cut at a word to NAME_MAX characters, and
    a repeated name gets ' (2)', ' (3)' … (`taken` is a set of names already used, updated in place)."""
    q = str(items[0]["q"] if items else "").replace("{count}", str(len(items)))
    lines = [re.sub(r"^\s*\[[^\]]+\]\s*", "", line) for line in q.splitlines()]
    name = " ".join(_BAD_NAME_CHARS.sub(" ", " ".join(lines)).split())
    if len(name) > NAME_MAX:
        cut = name[:NAME_MAX + 1].rsplit(" ", 1)[0]
        name = cut if len(cut) >= NAME_MAX // 2 else name[:NAME_MAX]
    name = name.rstrip(" .")
    if not name or name.split(".")[0].strip().lower() in _RESERVED:
        name = f"Video {n}" + (f" {name}" if name else "")
    if taken is not None:
        base, k = name, 2
        while name.lower() in taken:
            name, k = f"{base} ({k})", k + 1
        taken.add(name.lower())
    return name


def part_project(base, items, n, total, audio_dir, title=None, subtitle=None):
    """A normal MCQ project for part n of total, built from the editor's settings."""
    p = copy.deepcopy(base)
    m = p.setdefault("mcq", {})
    m["questions"] = questions_text(items)
    m["narration"] = narration_files(items, audio_dir)
    if title:
        m["title"] = fill_title(title, n, total)
    if subtitle:
        m["subtitle"] = fill_title(subtitle, n, total)
    return p


def summary(items, problems, per_video):
    if not items:
        return "⚠️ No usable questions." + ("\n\n" + "  \n".join("⚠️ " + p for p in problems[:30]) if problems else "")
    parts = split(items, per_video)
    sizes = [len(p) for p in parts]
    clips = sum(len(it["audio"]) for it in items)
    txt = (f"**{len(items)} questions → {len(parts)} video{'s' if len(parts) != 1 else ''}** "
           f"({' + '.join(map(str, sizes)) if len(set(sizes)) > 1 else f'{sizes[0]} each'}) · "
           f"{clips} audio clip{'s' if clips != 1 else ''} found")
    if len(sizes) > 1 and sizes[-1] < sizes[0]:
        txt += f"  \nThe last video has only {sizes[-1]} question{'s' if sizes[-1] != 1 else ''}."
    if problems:
        more = f"  \n…and {len(problems) - 30} more" if len(problems) > 30 else ""
        txt += "\n\n" + "  \n".join("⚠️ " + p for p in problems[:30]) + more
    return txt


# ------------------------------------------------------------------ template
def add_dropdowns(wb, ws, lists, rows=500):
    """Dropdown lists on columns of `ws`. lists = [(header names, values, strict, prompt)].
    The values go to a hidden 'Lists' sheet (Excel limits inline lists to 255 characters).
    strict=False still suggests the values but lets the user type anything else."""
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    headers = [c.value for c in ws[1]]
    ls = wb.create_sheet("Lists")
    for k, (names, values, strict, prompt) in enumerate(lists, 1):
        col = get_column_letter(k)
        for i, v in enumerate(values, 1):
            ls.cell(row=i, column=k, value=v)
        dv = DataValidation(type="list", formula1=f"=Lists!${col}$1:${col}${len(values)}", allow_blank=True,
                            showErrorMessage=strict, errorTitle="Not in the list",
                            error="Pick one of the choices from the dropdown list.",
                            showInputMessage=bool(prompt), prompt=prompt or None)
        ws.add_data_validation(dv)
        for name in names:
            c = get_column_letter(headers.index(name) + 1)
            dv.add(f"{c}2:{c}{rows}")
    ls.sheet_state = "hidden"


def write_template(path, example_items=None):
    """An .xlsx with the headers and a few example rows."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(TEMPLATE_HEADERS)
    for it in example_items or []:
        opts = (it["opts"] + ["", "", "", ""])[:4]
        n = it.get("n", 1)
        ws.append([it["q"], *opts, "ABCD"[it["correct"]], LEVEL_NAMES.get(it.get("level"), ""), it.get("expl", ""),
                   f"q{n}.mp3", f"q{n}a.mp3", f"q{n}b.mp3", f"q{n}c.mp3" if opts[2] else "",
                   f"q{n}d.mp3" if opts[3] else "", f"q{n}e.mp3" if it.get("expl") else ""])
    head = PatternFill("solid", fgColor="1F3A68")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
        c.alignment = Alignment(horizontal="center", vertical="center")
    for col, w in zip("ABCDEFGHIJKLMN", [46, 18, 18, 18, 18, 9, 12, 40, 16, 12, 12, 12, 12, 18]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.sheet_view.rightToLeft = False
    notes = wb.create_sheet("How to fill")
    for line in [
        "One question per row. Keep the header row (English or Arabic headers both work, in any order).",
        "Correct has a dropdown list: click the cell and pick A, B, C or D (or أ ب ج د).",
        "Options: 2 to 4. Leave Option C / D empty for fewer options.",
        "Correct: A, B, C or D (or أ ب ج د, or 1-4, or the exact text of the right option).",
        "Difficulty: optional — pick Easy, Medium or Hard (or سهل، متوسط، صعب) from the dropdown. It shows a badge",
        "with 1-3 stars above the question. Leave it empty for no badge.",
        "Explanation: optional, shown after the answer is revealed.",
        "Audio columns are optional. Write the clip's file name (q1.mp3) and upload the clips in the app,",
        "or write a path relative to the 'Audio folder' you set in the app, or a full path (C:\\quiz\\q1.mp3).",
        "In the app choose how many questions go in each video: 30 rows with 5 per video makes 6 videos.",
    ]:
        notes.append([line])
    notes.column_dimensions["A"].width = 110
    add_dropdowns(wb, ws, [(["Correct"], ["A", "B", "C", "D", "أ", "ب", "ج", "د"], True,
                            "Pick the right option: A, B, C or D"),
                           (["Difficulty"], ["Easy", "Medium", "Hard", "سهل", "متوسط", "صعب"], False,
                            "Optional: Easy, Medium or Hard")])
    wb.save(path)
    return path


def parts_count(n_items, per_video):
    per = max(1, min(MAX_PER_VIDEO, int(per_video or 5)))
    return math.ceil(n_items / per) if n_items else 0
