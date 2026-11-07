"""Where the user's own work lives: saved projects, their pictures / audio, and rendered videos.

They are kept OUTSIDE the app folder, in Documents/Video Studio (or the folder in the VS_DATA environment
variable), so replacing the app with a newer download never deletes them:

    Documents/Video Studio/projects/         saved projects (.json)
    Documents/Video Studio/projects/media/   pictures and audio copied in when a project is saved
    Documents/Video Studio/outputs/          rendered videos, cover pictures and Excel batches

The app folder keeps only what ships with the app (example projects, Excel templates)."""
import json
import os
import shutil

DATA_ENV = "VS_DATA"
DATA_NAME = "Video Studio"


def documents_dir():
    """The user's Documents folder (on Windows the real one, also when it is moved to OneDrive or another drive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                            ("Data4", ctypes.c_ubyte * 8)]
            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path and os.path.isdir(path):
                    return path
        except Exception:
            pass
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    return docs if os.path.isdir(docs) else home


def data_dir(app_root):
    """The folder for the user's work; falls back to the app folder if it can't be created."""
    path = os.environ.get(DATA_ENV) or os.path.join(documents_dir(), DATA_NAME)
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return os.path.abspath(path)
    except OSError:
        return os.path.abspath(app_root)


def _retarget(value, old_root, new_root):
    """Paths inside a project that point into the old media folder now point into the new one."""
    if isinstance(value, dict):
        return {k: _retarget(v, old_root, new_root) for k, v in value.items()}
    if isinstance(value, list):
        return [_retarget(v, old_root, new_root) for v in value]
    if isinstance(value, str) and value:
        norm = os.path.normcase(os.path.abspath(value)) if not value.startswith(("http:", "https:")) else ""
        old = os.path.normcase(os.path.abspath(old_root))
        if norm == old or norm.startswith(old + os.sep):
            return os.path.join(new_root, os.path.relpath(os.path.abspath(value), os.path.abspath(old_root)))
    return value


def rescue(app_root, data):
    """One-time move of work that older versions saved INSIDE the app folder into the data folder, so it
    survives the next update. Saved projects and media are copied (with their file links updated); videos in
    the app's outputs folder are moved. Nothing that already exists in the data folder is overwritten.
    Returns a short list of what was done (for the console)."""
    if os.path.normcase(os.path.abspath(app_root)) == os.path.normcase(os.path.abspath(data)):
        return []
    done = []
    old_proj, old_media = os.path.join(app_root, "projects"), os.path.join(app_root, "projects", "media")
    new_proj, new_media = os.path.join(data, "projects"), os.path.join(data, "projects", "media")
    old_out, new_out = os.path.join(app_root, "outputs"), os.path.join(data, "outputs")
    for d in (new_proj, new_media, new_out):
        os.makedirs(d, exist_ok=True)
    # pictures / audio first, so the projects can point at their new copies
    if os.path.isdir(old_media):
        for name in os.listdir(old_media):
            if name.startswith("."):
                continue
            src, dst = os.path.join(old_media, name), os.path.join(new_media, name)
            if os.path.exists(dst):
                continue
            try:
                (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
                done.append(f"media/{name}")
            except OSError:
                pass
    if os.path.isdir(old_proj):
        for name in os.listdir(old_proj):
            if not name.lower().endswith(".json") or name.startswith("example_"):
                continue  # example projects ship with the app
            src, dst = os.path.join(old_proj, name), os.path.join(new_proj, name)
            if os.path.exists(dst):
                continue
            try:
                with open(src, encoding="utf-8") as f:
                    p = json.load(f)
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(_retarget(p, old_media, new_media), f, ensure_ascii=False, indent=2)
                done.append(name)
            except (OSError, ValueError):
                pass
    if os.path.isdir(old_out):
        for name in os.listdir(old_out):
            if name.startswith((".", "_")):  # .keep and the app's own preview scratch files
                continue
            src, dst = os.path.join(old_out, name), os.path.join(new_out, name)
            if os.path.exists(dst):
                continue
            try:
                shutil.move(src, dst)
                done.append(f"outputs/{name}")
            except OSError:
                pass
    return done


def find_media(path, media_dir):
    """A media file of a saved project that is not where the project says (the project was moved, or saved by
    an older version inside the app folder): look for it in the media folder by its name. Returns a path or
    the original value."""
    if not path or not isinstance(path, str) or os.path.isfile(path):
        return path
    norm = path.replace("\\", "/").rstrip("/")
    base = norm.rsplit("/", 1)[-1]
    parent = norm.rsplit("/", 2)[-2] if norm.count("/") >= 1 else ""
    for cand in ([os.path.join(media_dir, parent, base)] if parent and parent != "media" else []) + \
            [os.path.join(media_dir, base)]:
        if os.path.isfile(cand):
            return cand
    return path


def relink(project, media_dir, keys):
    """find_media() on every media field of a project (keys = field names that hold one file or a list)."""
    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in keys:
                    v[k] = [find_media(i, media_dir) for i in x] if isinstance(x, list) else find_media(x, media_dir)
                else:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(project)
    return project
