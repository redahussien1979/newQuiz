"""Build a video from a project dict (the same JSON the app saves)."""
import json
import os
import threading
from collections import OrderedDict

from .audio import SR, Mixer, load_audio
from .core import draw_safe_zone, encode, set_font
from .templates import TEMPLATES


def build(project):
    key = project.get("template", "timeline")
    if key not in TEMPLATES:
        raise ValueError(f"Unknown template: {key}")
    s = project.get("settings", {})
    set_font(s.get("font_file"))
    video = TEMPLATES[key][1](project)
    voice = s.get("voice_file")
    if voice and os.path.isfile(voice):
        length = len(load_audio(voice)) / SR
        video.dur = max(video.base_duration, float(s.get("voice_offset") or 0) + length + 0.8)
    return video


_cache = OrderedDict()
_cache_lock = threading.Lock()


def _project_key(project):
    key = json.dumps(project, sort_keys=True, ensure_ascii=False, default=str)
    stamps = []

    def walk(v):  # re-build if an uploaded file was replaced on disk
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and 0 < len(v) < 1024 and "\n" not in v and os.path.isfile(v):
            stamps.append(os.path.getmtime(v))
    walk(project)
    return key + repr(stamps)


def build_cached(project, size=6):
    """Like build(), but re-uses the last few built videos so scrubbing the preview time is instant."""
    key = _project_key(project)
    with _cache_lock:
        video = _cache.get(key)
        if video is not None:
            _cache.move_to_end(key)
    if video is None:
        video = build(project)
        with _cache_lock:
            _cache[key] = video
            while len(_cache) > size:
                _cache.popitem(last=False)
    else:
        set_font(project.get("settings", {}).get("font_file"))
    return video


def render_still(project, t, safe_zone=False, cached=False):
    video = build_cached(project) if cached else build(project)
    t = max(0.0, min(float(t), video.dur - 1.0 / video.fps))
    img = video.render(t).convert("RGBA")
    if safe_zone:
        draw_safe_zone(img)
    return img.convert("RGB"), video.dur


def render_video(project, out_path, progress=None):
    video = build(project)
    s = project.get("settings", {})
    silences = getattr(video, "silences", [])
    mx = Mixer(video.dur)
    video.sound(mx)
    music_file = s.get("music_file")
    if music_file and os.path.isfile(music_file):
        mx.music_file(music_file, silences, float(s.get("music_gain") or 1.0))
    else:
        mx.synth_bed(s.get("music") or "Tension", silences, float(s.get("music_gain") or 1.0))
    voice = s.get("voice_file")
    if voice and os.path.isfile(voice):
        mx.add_voice(voice, float(s.get("voice_offset") or 0), float(s.get("voice_gain") or 1.0))
    wav = os.path.splitext(out_path)[0] + "_audio.wav"
    mx.write(wav)
    try:
        encode(video.render, int(round(video.dur * video.fps)), video.fps, wav, out_path, progress)
    finally:
        if os.path.exists(wav):
            os.remove(wav)
    return out_path, video.dur


def render_clip(project, out_path, t0=0.0, secs=6.0, fps=15, scale=3):
    """Fast low-resolution motion preview (with sound) of a few seconds starting at t0."""
    import subprocess

    from PIL import Image

    from .core import H, W, ffmpeg_exe
    video = build(project)
    s = project.get("settings", {})
    t0 = max(0.0, min(float(t0), max(0.0, video.dur - 1.0)))
    secs = min(float(secs), video.dur - t0)
    mx = Mixer(video.dur)
    video.sound(mx)
    silences = getattr(video, "silences", [])
    music_file = s.get("music_file")
    if music_file and os.path.isfile(music_file):
        mx.music_file(music_file, silences, float(s.get("music_gain") or 1.0))
    else:
        mx.synth_bed(s.get("music") or "Tension", silences, float(s.get("music_gain") or 1.0))
    voice = s.get("voice_file")
    if voice and os.path.isfile(voice):
        mx.add_voice(voice, float(s.get("voice_offset") or 0), float(s.get("voice_gain") or 1.0))
    wav = os.path.splitext(out_path)[0] + "_audio.wav"
    mx.write(wav)
    w, h = W // scale // 2 * 2, H // scale // 2 * 2
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-ss", f"{t0:.3f}", "-t", f"{secs:.3f}", "-i", wav,
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out_path]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(int(secs * fps)):
            ff.stdin.write(video.render(t0 + i / fps).resize((w, h), Image.BILINEAR).tobytes())
        ff.stdin.close()
    except BrokenPipeError:
        pass
    err = ff.stderr.read().decode(errors="ignore")
    code = ff.wait()
    if os.path.exists(wav):
        os.remove(wav)
    if code != 0:
        raise RuntimeError("FFmpeg failed: " + err[-500:])
    return out_path, video.dur
