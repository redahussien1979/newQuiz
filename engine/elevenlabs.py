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
