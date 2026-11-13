"""ElevenLabs text-to-speech for English Texts: speech + the time of every letter, turned into word timings.

- The API key and voice choices are kept on this computer only (DATA_DIR/elevenlabs.json), never in projects/videos.
- Every recording is cached (DATA_DIR/tts/<hash>.mp3 + .json): the same text with the same voice and settings is never
  paid for twice.
- Uses the "text to speech with timestamps" endpoint, which returns the audio and, for every character of the text,
  its start / end time; word_times() turns them into word timings. The text that is spoken may differ from the text
  on screen ("say it differently": COP29 -> cop twenty-nine): each screen word knows its span in the spoken text.
Only the Python standard library is used (urllib), so nothing new to install.
"""
import base64
import difflib
import hashlib
import json
import os
import urllib.error
import urllib.request

API = "https://api.elevenlabs.io"
MODELS = [("Multilingual v2 (best quality)", "eleven_multilingual_v2"),
          ("Turbo v2.5 (faster, half the credits)", "eleven_turbo_v2_5"),
          ("Flash v2.5 (fastest, half the credits)", "eleven_flash_v2_5")]
DEFAULTS = {"api_key": "", "voice_id": "UpphzPau5vxibPYV2NeV", "voice_name": "joe inglewood",
            "model": "eleven_multilingual_v2", "speed": 1.0, "stability": 0.5, "similarity": 0.75}


# ------------------------------------------------------------------ settings (this computer only)
def _settings_path(data_dir):
    return os.path.join(data_dir, "elevenlabs.json")


def load_settings(data_dir):
    s = dict(DEFAULTS)
    try:
        with open(_settings_path(data_dir), encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return s


def save_settings(data_dir, **kw):
    s = load_settings(data_dir)
    s.update({k: v for k, v in kw.items() if k in DEFAULTS and v is not None})
    os.makedirs(data_dir, exist_ok=True)
    with open(_settings_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    return s


# ------------------------------------------------------------------ HTTP
def _request(path, key, body=None, timeout=180):
    if not key:
        raise RuntimeError("Add your ElevenLabs API key first (🔑 ElevenLabs voice).")
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": key, "Content-Type": "application/json",
                                          "Accept": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
            msg = detail.get("message") if isinstance(detail, dict) else detail
        except Exception:
            msg = ""
        if e.code == 401:
            raise RuntimeError("ElevenLabs refused the API key, or your credits / plan do not allow this "
                               f"({msg or 'unauthorized'}).") from e
        if e.code == 404:
            raise RuntimeError(f"ElevenLabs does not know this voice ID ({msg or 'not found'}).") from e
        if e.code == 429:
            raise RuntimeError("ElevenLabs is busy or your quota is used up — try again in a minute "
                               f"({msg or 'too many requests'}).") from e
        raise RuntimeError(f"ElevenLabs error {e.code}: {msg or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach ElevenLabs — check the internet connection ({e.reason}).") from e


def list_voices(key):
    """[(name — category, voice_id)] of every voice in the account (premade, cloned, library voices you added)."""
    data = _request("/v1/voices", key)
    out = []
    for v in data.get("voices", []):
        cat = v.get("category") or ""
        out.append((f"{v.get('name', '?')}" + (f" — {cat}" if cat else ""), v.get("voice_id")))
    return sorted(out, key=lambda x: x[0].lower())


def synthesize(text, key, voice_id, model, speed=1.0, stability=0.5, similarity=0.75):
    """(mp3 bytes, alignment) for text. alignment = dict(characters, character_start_times_seconds,
    character_end_times_seconds) for the text exactly as sent."""
    if not voice_id:
        raise RuntimeError("Choose a voice (or paste its voice ID).")
    body = {"text": text, "model_id": model or DEFAULTS["model"],
            "voice_settings": {"stability": float(stability), "similarity_boost": float(similarity),
                               "speed": float(speed), "use_speaker_boost": True}}
    data = _request(f"/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128", key, body)
    audio = base64.b64decode(data.get("audio_base64") or "")
    al = data.get("alignment") or data.get("normalized_alignment")
    if not audio or not al:
        raise RuntimeError("ElevenLabs sent no audio or no timings back.")
    return audio, al


# ------------------------------------------------------------------ cache
def cache_key(text, voice_id, model, speed, stability, similarity):
    raw = json.dumps([text, voice_id, model, round(float(speed), 3), round(float(stability), 3),
                      round(float(similarity), 3)], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def cached(cache_dir, key):
    mp3, js = os.path.join(cache_dir, key + ".mp3"), os.path.join(cache_dir, key + ".json")
    if os.path.isfile(mp3) and os.path.isfile(js):
        try:
            with open(js, encoding="utf-8") as f:
                return mp3, json.load(f)
        except (OSError, ValueError):
            return None
    return None


def speak(text, cache_dir, settings):
    """(mp3 path, alignment) — from the cache, or made by ElevenLabs (and cached)."""
    s = settings
    k = cache_key(text, s["voice_id"], s["model"], s["speed"], s["stability"], s["similarity"])
    hit = cached(cache_dir, k)
    if hit:
        return hit
    audio, al = synthesize(text, s["api_key"], s["voice_id"], s["model"], s["speed"], s["stability"], s["similarity"])
    os.makedirs(cache_dir, exist_ok=True)
    mp3 = os.path.join(cache_dir, k + ".mp3")
    with open(mp3 + ".part", "wb") as f:
        f.write(audio)
    os.replace(mp3 + ".part", mp3)
    with open(os.path.join(cache_dir, k + ".json"), "w", encoding="utf-8") as f:
        json.dump(al, f)
    return mp3, al


# ------------------------------------------------------------------ letters -> words
def _char_times(spoken, al):
    """(start, end) for every character of `spoken`, from the alignment (which may differ slightly: ElevenLabs can
    normalise some characters). Characters it has no time for get the time of their neighbours."""
    chars = al.get("characters") or []
    st = al.get("character_start_times_seconds") or []
    en = al.get("character_end_times_seconds") or []
    n = len(spoken)
    times = [None] * n
    if "".join(chars) == spoken:
        times = list(zip(st, en))
    else:
        sm = difflib.SequenceMatcher(None, spoken, "".join(chars), autojunk=False)
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                times[a + k] = (st[b + k], en[b + k])
    last = (0.0, 0.0)
    for i in range(n):  # fill the gaps from the nearest timed character before
        if times[i] is None:
            times[i] = (last[1], last[1])
        last = times[i]
    return times


def word_times(spans, spoken, al):
    """[(start, end)] seconds for each screen word, given its (a, b) span in the spoken text."""
    ct = _char_times(spoken, al)
    out = []
    for a, b in spans:
        seg = [ct[i] for i in range(a, b) if not spoken[i].isspace()] or [ct[min(a, len(ct) - 1)]]
        s = min(x[0] for x in seg)
        e = max(x[1] for x in seg)
        out.append((round(s, 3), round(max(e, s + 0.05), 3)))
    for k in range(1, len(out)):  # keep them in order (a rare alignment hiccup)
        if out[k][0] < out[k - 1][0]:
            out[k] = (out[k - 1][0], max(out[k][1], out[k - 1][0] + 0.05))
    return out


# ------------------------------------------------------------------ speech to text (📰 English in News)
STT_MODELS = [("Scribe v1", "scribe_v1"), ("Scribe v2 (newer — if your account has it)", "scribe_v2")]
STT_LANGS = [("Detect automatically", ""), ("English", "en")]


def _file_hash(path, extra=""):
    h = hashlib.sha1(extra.encode("utf-8"))
    h.update(str(os.path.getsize(path)).encode())
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:20]


def _multipart(fields, file_field, file_name, file_bytes, mime):
    boundary = "----VideoStudio" + hashlib.sha1(file_bytes[:4096] + os.urandom(8)).hexdigest()[:16]
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode("utf-8")
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{file_name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode("utf-8")
    out += file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _audio_for_stt(path):
    """The sound of a video as a small mono MP3 (uploads fast; the speech is all ElevenLabs needs)."""
    import subprocess
    from .core import ffmpeg_exe
    p = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
                        "-f", "mp3", "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("This video has no sound track (or FFmpeg could not read it).")
    return p.stdout


def transcribe(path, cache_dir, key, model="scribe_v1", language=""):
    """[dict(text, start, end)] — every spoken word of a video / audio file with its time in seconds, from ElevenLabs
    speech-to-text. Cached per file content + model + language (DATA_DIR/stt): the same video is never paid twice."""
    if not path or not os.path.isfile(path):
        raise RuntimeError("Upload a video first.")
    model = model or "scribe_v1"
    k = _file_hash(path, f"{model}|{language}")
    js = os.path.join(cache_dir, k + ".json")
    if os.path.isfile(js):
        try:
            with open(js, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    if not key:
        raise RuntimeError("Add your ElevenLabs API key first (🔑 ElevenLabs).")
    fields = {"model_id": model, "timestamps_granularity": "word", "tag_audio_events": "false", "diarize": "false"}
    if language:
        fields["language_code"] = language
    body, ctype = _multipart(fields, "file", "audio.mp3", _audio_for_stt(path), "audio/mpeg")
    req = urllib.request.Request(API + "/v1/speech-to-text", data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": ctype, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
            msg = detail.get("message") if isinstance(detail, dict) else detail
        except Exception:
            msg = ""
        if e.code == 401:
            raise RuntimeError("ElevenLabs refused the API key — it may not have the Speech to Text permission, or "
                               f"your plan / credits do not allow it ({msg or 'unauthorized'}).") from e
        if e.code in (400, 422):
            raise RuntimeError(f"ElevenLabs could not transcribe this file ({msg or e.reason}). If you chose Scribe "
                               "v2, try Scribe v1.") from e
        if e.code == 429:
            raise RuntimeError("ElevenLabs is busy or your quota is used up — try again in a minute.") from e
        raise RuntimeError(f"ElevenLabs error {e.code}: {msg or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach ElevenLabs — check the internet connection ({e.reason}).") from e
    words = []
    for w in data.get("words") or []:
        if w.get("type", "word") != "word":
            continue
        t = str(w.get("text") or "").strip()
        if not t:
            continue
        s = float(w.get("start") or 0.0)
        words.append(dict(text=t, start=round(s, 3), end=round(max(float(w.get("end") or s), s + 0.05), 3)))
    if not words:
        raise RuntimeError("ElevenLabs heard no words in this video.")
    os.makedirs(cache_dir, exist_ok=True)
    with open(js, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)
    return words
