"""Font library: the fonts that ship with the app (fonts/library), fonts the user adds in the app
(Documents/Video Studio/fonts) and a folder of their own anywhere on the computer.

A project's `settings.font_file` holds a font FAMILY NAME from this library (e.g. "Tajawal"), or — in projects saved
by older versions — a path to a .ttf/.otf file; empty = Cairo. core.set_font() resolves it with resolve(), and
core.get_font() picks the family's file / variable-font instance for each weight (Black, Bold, SemiBold…).
Text a font cannot write (English in an Arabic-only font, Quran marks…) is drawn in Cairo instead (core._font_for).

The scan is cached in Documents/Video Studio/fonts_index.json (by file size + date), so render processes and
large font folders stay fast."""
import json
import os
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY = os.path.join(ROOT, "fonts", "library")
DEFAULT = os.path.join(ROOT, "fonts", "Cairo.ttf")
DEFAULT_NAME = "Cairo"
EXT = (".ttf", ".otf")
MAX_FILES = 3000  # per folder (a folder of fonts can be huge)
AR_TEST = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
EN_TEST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_WEIGHTS = ["extrablack", "ultrablack", "black", "heavy", "extrabold", "ultrabold", "semibold", "demibold", "bold",
            "medium", "regular", "normal", "book", "light", "extralight", "ultralight", "thin", "hairline"]
_state = {"index": None, "families": None}


# ---------------------------------------------------------------- where things live
def data_dir():
    from .userdata import data_dir as dd
    return dd(ROOT)


def added_dir():
    """Fonts the user adds in the app are copied here."""
    path = os.path.join(data_dir(), "fonts")
    os.makedirs(path, exist_ok=True)
    return path


def _prefs_path():
    return os.path.join(data_dir(), "fonts.json")


def get_folder():
    try:
        with open(_prefs_path(), encoding="utf-8") as f:
            return json.load(f).get("folder", "")
    except Exception:
        return ""


def set_folder(path):
    path = str(path or "").strip().strip('"')
    try:
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump({"folder": path}, f, ensure_ascii=False)
    except OSError:
        pass
    _state["families"] = None
    return path


def add_files(paths):
    """Copy uploaded font files into the added-fonts folder; returns how many were added."""
    n = 0
    for p in paths or []:
        p = str(p)
        if p.lower().endswith(EXT) and os.path.isfile(p):
            shutil.copy2(p, os.path.join(added_dir(), os.path.basename(p)))
            n += 1
    _state["families"] = None
    return n


# ---------------------------------------------------------------- reading one font
def _norm_style(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _split_name(family, style):
    """('Tajawal Black', 'Regular') -> ('Tajawal', 'black'): some fonts put the weight in the family name."""
    st = _norm_style(style) or "regular"
    words = family.split()
    if st in ("regular", "normal", "book") and len(words) > 1:
        for k in (2, 1):
            tail = _norm_style("".join(words[-k:]))
            if len(words) > k and tail in _WEIGHTS:
                return " ".join(words[:-k]), tail
    return family, st


def _coverage(path):
    """(writes Arabic, writes English) for a font file."""
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(path, lazy=True, fontNumber=0).getBestCmap() or {}
        return all(ord(c) in cmap for c in AR_TEST), all(ord(c) in cmap for c in EN_TEST)
    except Exception:
        pass
    try:  # without fontTools: a missing letter draws the same box as a character no font has
        f = ImageFont.truetype(path, 32, layout_engine=ImageFont.Layout.BASIC)
        box = f.getmask("￿").tobytes()

        def has(ch):
            return f.getmask(ch).tobytes() != box
        return all(has(c) for c in AR_TEST[:8]), all(has(c) for c in EN_TEST[:8])
    except Exception:
        return False, False


def _read(path):
    try:
        f = ImageFont.truetype(path, 24)
        family, style = f.getname()
    except Exception:
        return None
    try:
        variable = bool(f.get_variation_axes())
    except Exception:
        variable = False
    family, style = _split_name(family or os.path.splitext(os.path.basename(path))[0], style or "Regular")
    ar, en = _coverage(path)
    return dict(path=path, family=family, style=style, variable=variable, arabic=ar, latin=en)


# ---------------------------------------------------------------- the library
def _index():
    if _state["index"] is None:
        try:
            with open(os.path.join(data_dir(), "fonts_index.json"), encoding="utf-8") as f:
                _state["index"] = json.load(f)
        except Exception:
            _state["index"] = {}
    return _state["index"]


def _save_index():
    try:
        with open(os.path.join(data_dir(), "fonts_index.json"), "w", encoding="utf-8") as f:
            json.dump(_state["index"], f, ensure_ascii=False)
    except OSError:
        pass


def _files(folder):
    out = []
    if folder and os.path.isdir(folder):
        for dirpath, dirs, names in os.walk(folder):
            dirs.sort()
            for n in sorted(names):
                if n.lower().endswith(EXT):
                    out.append(os.path.join(dirpath, n))
                    if len(out) >= MAX_FILES:
                        return out
    return out


def _sources():
    return [("built-in", LIBRARY), ("added", added_dir()), ("folder", get_folder())]


def families(refresh=False):
    """All families: [dict(name, styles={style: path}, main, arabic, latin, variable, source)], Cairo first."""
    if _state["families"] is not None and not refresh:
        return _state["families"]
    idx, changed = _index(), False
    fams = {DEFAULT_NAME: dict(name=DEFAULT_NAME, styles={"regular": DEFAULT}, main=DEFAULT, arabic=True, latin=True,
                               variable=True, source="built-in")}
    order = [DEFAULT_NAME]
    for source, folder in _sources():
        for p in _files(folder):
            try:
                st = os.stat(p)
            except OSError:
                continue
            stamp = f"{st.st_size}:{int(st.st_mtime)}"
            rec = idx.get(p)
            if not rec or rec.get("stamp") != stamp:
                info = _read(p)
                rec = dict(info or {}, stamp=stamp, bad=info is None)
                idx[p], changed = rec, True
            if rec.get("bad"):
                continue
            name = rec["family"]
            fam = fams.get(name)
            if fam is None:
                fam = fams[name] = dict(name=name, styles={}, main=p, arabic=False, latin=False, variable=False,
                                        source=source)
                order.append(name)
            elif fam["source"] != source:
                continue  # the same family in two places: the first one wins
            fam["styles"].setdefault(rec["style"], p)
            fam["arabic"] |= rec["arabic"]
            fam["latin"] |= rec["latin"]
            fam["variable"] |= rec["variable"]
    for fam in fams.values():  # the file used for the family's name: its boldest / variable file
        for want in ("black", "heavy", "extrabold", "bold", "semibold", "medium", "regular"):
            if want in fam["styles"]:
                fam["main"] = fam["styles"][want]
                break
        else:
            fam["main"] = next(iter(fam["styles"].values()))
    if changed:
        _save_index()
    rank = {"built-in": 0, "added": 1, "folder": 2}  # Cairo, then Arabic fonts A-Z, then English-only, per source
    rest = sorted((fams[n] for n in order if n != DEFAULT_NAME),
                  key=lambda f: (rank.get(f["source"], 3), not f["arabic"], f["name"].lower()))
    _state["families"] = [fams[DEFAULT_NAME]] + rest
    return _state["families"]


def find(name):
    for fam in families():
        if fam["name"] == name:
            return fam
    return None


def resolve(value):
    """A project's font setting -> the font file to load (Cairo when empty / missing)."""
    value = str(value or "").strip()
    if not value:
        return DEFAULT
    if os.path.isfile(value):
        return value
    fam = find(value) or (find(value) if families(refresh=True) else None)
    return fam["main"] if fam else DEFAULT


def family_files(path):
    """{style: file} of the family a font file belongs to (only that file when it is not in the library)."""
    for fam in families():
        if path in fam["styles"].values():
            return fam["styles"]
    return {}


def tags(fam):
    return " · ".join(t for t, ok in (("عربي", fam["arabic"]), ("English", fam["latin"])) if ok) or "?"


def choices():
    """Dropdown choices: (label, value); value '' = Cairo (default)."""
    out = [("Cairo — default · عربي · English", "")]
    where = {"built-in": "", "added": " · added", "folder": " · my folder"}
    for fam in families():
        if fam["name"] == DEFAULT_NAME:
            continue
        out.append((f"{fam['name']} · {tags(fam)}{where.get(fam['source'], '')}", fam["name"]))
    return out


# ---------------------------------------------------------------- preview cards
def card(fam, sample_ar, sample_en, selected=False):
    """A preview card: the family's name, then the samples written in it (its boldest weight)."""
    from .core import _prep, get_font
    w, h = 900, 300
    im = Image.new("RGB", (w, h), (24, 26, 40) if not selected else (40, 34, 12))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([3, 3, w - 4, h - 4], 22, outline=(255, 200, 60) if selected else (70, 74, 100), width=4)
    label = f"{fam['name']}   ·   {tags(fam)}"
    lf = get_font(30, "Bold", DEFAULT)
    d.text((30, 20), label, font=lf, fill=(255, 200, 60) if selected else (170, 176, 205))
    path = fam["main"]
    y = 82
    for txt, ok, col in ((sample_ar, fam["arabic"], (255, 255, 255)), (sample_en, fam["latin"], (150, 220, 255))):
        if not txt:
            continue
        if not ok:
            msg = "لا يكتب هذا الخط العربية — تُكتب بخط Cairo" if col == (255, 255, 255) else \
                "No English letters — written in Cairo instead"
            t2, kw = _prep(msg)
            d.text((w - 30, y + 24) if kw.get("direction") == "rtl" or t2 != msg else (30, y + 24), t2,
                   font=get_font(28, "SemiBold", DEFAULT), fill=(130, 130, 150),
                   anchor="ra" if (kw.get("direction") == "rtl" or t2 != msg) else "la", **kw)
            y += 100
            continue
        size = 70
        t2, kw = _prep(txt)
        f = get_font(size, "Black", path)
        while size > 30 and d.textlength(t2, font=f, **kw) > w - 60:
            size -= 4
            f = get_font(size, "Black", path)
        rtl = kw.get("direction") == "rtl" or (t2 != txt)
        d.text((w - 30, y) if rtl else (30, y), t2, font=f, fill=col, anchor="ra" if rtl else "la", **kw)
        y += 104
    return im


def gallery(sample_ar, sample_en, query="", only="all", selected="", limit=60):
    """[(card image, family name)] for a gr.Gallery, filtered by name / script."""
    q = str(query or "").strip().lower()
    out = []
    for fam in families():
        if q and q not in fam["name"].lower():
            continue
        if only == "arabic" and not fam["arabic"]:
            continue
        if only == "english" and not fam["latin"]:
            continue
        if only == "mine" and fam["source"] == "built-in":
            continue
        out.append((card(fam, sample_ar, sample_en, selected == (fam["name"] if fam["name"] != DEFAULT_NAME else "")),
                    fam["name"]))
        if len(out) >= limit:
            break
    return out
