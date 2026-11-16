"""Arabic meanings of key words, filled automatically by Claude (the Anthropic API).

Each key word / phrase is translated AS IT IS USED in its sentence ("opening" in "Cities are opening cooling centres"
-> تفتح, not افتتاح), as a short dictionary-style meaning in Modern Standard Arabic.
- The API key and model choice are kept on this computer only (DATA_DIR/anthropic.json), never in projects/videos.
- Every answer is cached (DATA_DIR/meanings_cache.json, per model + word + sentence): a word is never paid for twice.
- One request per batch of words; the answer comes back through a forced tool call, so it is always clean JSON.
Only the Python standard library is used (urllib), so nothing new to install.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

API = "https://api.anthropic.com/v1/messages"
MODELS = [("Claude Opus 5.5 — best translations (≈ 1 cent per clip)", "claude-opus-5-5"),
          ("Claude Sonnet 5.5 — almost as good, half the price", "claude-sonnet-5-5"),
          ("Claude Haiku 5.5 — cheapest, fine for common words", "claude-haiku-5-5")]
DEFAULTS = {"api_key": "", "model": "claude-opus-5-5", "auto": True}
# USD per million tokens (input, output) — platform.claude.com/docs/en/about-claude/pricing (Haiku: prompts up to
# 100,000 tokens, which these always are)
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
BATCH = 40          # words per request

SYSTEM = (
    "You are an expert English-Arabic translator writing glossary entries for an English-learning channel whose "
    "viewers are Arabic speakers. For every item you get an English key word or phrase and the sentence it was "
    "spoken in. Give its Arabic meaning AS USED IN THAT SENTENCE:\n"
    "- Modern Standard Arabic, the natural equivalent a good bilingual dictionary would give for this sense.\n"
    "- Short: usually 1-3 words, at most 5. No explanations, no transliteration, no English, no quotes.\n"
    "- Match the part of speech and form in the sentence (a verb as a verb, a plural as a plural; phrasal verbs and "
    "idioms by their meaning, not word by word).\n"
    "- Names of people, places and organisations: their usual Arabic spelling.\n"
    "- Diacritics only where they prevent a misreading (a shadda or one vowel), otherwise none.\n"
    "Return exactly one meaning per item, in the same order.")

TOOL = {
    "name": "give_meanings",
    "description": "Return the Arabic meaning of every item, in order.",
    "input_schema": {
        "type": "object",
        "properties": {"meanings": {"type": "array", "items": {"type": "string"},
                                    "description": "One Arabic meaning per item, same order as the items."}},
        "required": ["meanings"],
    },
}


# ------------------------------------------------------------------ settings (this computer only)
def _settings_path(data_dir):
    return os.path.join(data_dir, "anthropic.json")


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


# ------------------------------------------------------------------ cache
_lock = threading.Lock()


def _cache_path(data_dir):
    return os.path.join(data_dir, "meanings_cache.json")


def _cache_load(data_dir):
    try:
        with open(_cache_path(data_dir), encoding="utf-8") as f:
            c = json.load(f)
            return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_save(data_dir, cache):
    os.makedirs(data_dir, exist_ok=True)
    tmp = _cache_path(data_dir) + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, _cache_path(data_dir))


def _key(model, word, sentence):
    raw = json.dumps([model, " ".join(word.lower().split()), " ".join(sentence.split())], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


# ------------------------------------------------------------------ HTTP
def _post(body, key, timeout=120):
    if not key:
        raise RuntimeError("Add your Anthropic API key first (🤖 Automatic Arabic meanings).")
    req = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8")).get("error") or {}
                msg = err.get("message") or ""
            except Exception:
                msg = ""
            if e.code in (429, 500, 502, 503, 529) and attempt < 2:   # busy / overloaded: wait and try again
                time.sleep(2 + 3 * attempt)
                continue
            if e.code == 401:
                raise RuntimeError("Anthropic refused the API key — check it in 🤖 Automatic Arabic meanings.") from e
            if e.code == 403:
                raise RuntimeError(f"This API key may not use that model ({msg or 'forbidden'}).") from e
            if e.code == 404:
                raise RuntimeError(f"Unknown model — pick another one ({msg or 'not found'}).") from e
            if e.code == 400 and "credit" in msg.lower():
                raise RuntimeError("Your Anthropic account has no credit left (console.anthropic.com → Billing).") from e
            if e.code == 429:
                raise RuntimeError("Anthropic: too many requests or the usage limit is reached — try again soon.") from e
            raise RuntimeError(f"Anthropic error {e.code}: {msg or e.reason}") from e
        except urllib.error.URLError as e:
            if attempt < 2:
                time.sleep(2)
                continue
            raise RuntimeError(f"Could not reach Anthropic — check the internet connection ({e.reason}).") from e
    raise RuntimeError("Anthropic did not answer — try again.")


def _ask(items, key, model):
    """[(word, sentence)] -> [arabic] from one request."""
    lines = "\n".join(f"{k}. key word: {w}\n   sentence: {s}" for k, (w, s) in enumerate(items, 1))
    body = {"model": model or DEFAULTS["model"], "max_tokens": 200 + 60 * len(items), "system": SYSTEM,
            "tools": [TOOL], "tool_choice": {"type": "tool", "name": TOOL["name"]},
            "messages": [{"role": "user", "content": f"{len(items)} items:\n{lines}"}]}
    data = _post(body, key)
    cost = cost_of(model, data.get("usage"))
    for block in data.get("content") or []:
        if block.get("type") == "tool_use":
            out = (block.get("input") or {}).get("meanings")
            if isinstance(out, list) and len(out) == len(items):
                return [" ".join(str(x or "").split()) for x in out], cost
    raise RuntimeError("Claude's answer did not have one meaning per word — try again.")


def meanings(items, data_dir, settings):
    """([arabic] for every (word, sentence), exact cost in USD): from the cache (free), else asked in batches and
    cached."""
    model, key = settings.get("model") or DEFAULTS["model"], (settings.get("api_key") or "").strip()
    with _lock:
        cache = _cache_load(data_dir)
    keys = [_key(model, w, s) for w, s in items]
    todo = []
    for i, k in enumerate(keys):
        if not cache.get(k) and all(keys[j] != k for j, _ in todo):
            todo.append((i, k))
    spent = 0.0
    for a in range(0, len(todo), BATCH):
        part = todo[a:a + BATCH]
        got, cost = _ask([items[i] for i, _ in part], key, model)
        spent += record(data_dir, cost)
        with _lock:
            cache = _cache_load(data_dir)
            cache.update({k: ar for (_, k), ar in zip(part, got) if ar})
            _cache_save(data_dir, cache)
    return [cache.get(k, "") for k in keys], spent


# ------------------------------------------------------------------ exact cost (from the tokens Anthropic reports)
def cost_of(model, usage):
    """USD of one answer from its usage block (input + output tokens, cache reads/writes at their own rates)."""
    pin, pout = PRICES.get(model, PRICES[DEFAULTS["model"]])
    u = usage or {}
    tokens_in = (u.get("input_tokens") or 0) + 1.25 * (u.get("cache_creation_input_tokens") or 0) \
        + 0.1 * (u.get("cache_read_input_tokens") or 0)
    return (tokens_in * pin + (u.get("output_tokens") or 0) * pout) / 1e6


def _usage_path(data_dir):
    return os.path.join(data_dir, "anthropic_usage.json")


def usage(data_dir):
    """{"total": USD spent so far from this computer, "requests": n}."""
    try:
        with open(_usage_path(data_dir), encoding="utf-8") as f:
            u = json.load(f)
            return {"total": float(u.get("total") or 0), "requests": int(u.get("requests") or 0)}
    except (OSError, ValueError):
        return {"total": 0.0, "requests": 0}


def record(data_dir, cost):
    """Add one request's cost to the running total (kept on this computer). Returns the cost."""
    with _lock:
        u = usage(data_dir)
        u["total"] += cost
        u["requests"] += 1
        os.makedirs(data_dir, exist_ok=True)
        with open(_usage_path(data_dir), "w", encoding="utf-8") as f:
            json.dump(u, f)
    return cost


def money(usd):
    """$0.0512 / $1.24 — enough digits to see a fraction of a cent."""
    return f"${usd:.4f}" if usd < 1 else f"${usd:.2f}"


def cost_line(data_dir, spent):
    return f"cost {money(spent)} · total so far {money(usage(data_dir)['total'])}"


# ------------------------------------------------------------------ another meaning for one word
ALT_TOOL = {
    "name": "give_options",
    "description": "Return 3 different Arabic meanings for the item.",
    "input_schema": {
        "type": "object",
        "properties": {"options": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                                   "description": "3 different Arabic meanings, the most fitting first."}},
        "required": ["options"],
    },
}


def alternatives(word, sentence, rejected, hint, data_dir, settings):
    """(3 other Arabic meanings of a word in its sentence — never the rejected one(s), following the hint, exact
    cost). Not cached: every press asks again."""
    model, key = settings.get("model") or DEFAULTS["model"], (settings.get("api_key") or "").strip()
    rejected = [r for r in rejected if r]
    ask = f"key word: {word}\nsentence: {sentence}\n"
    if rejected:
        ask += "Rejected meanings (do NOT give these or near-copies of them): " + " | ".join(rejected) + "\n"
    if hint and hint.strip():
        ask += f"The user's wish for the meaning: {hint.strip()}\n"
    ask += "Give 3 different good Arabic meanings for this word as used in this sentence, the most fitting first."
    body = {"model": model, "max_tokens": 300, "system": SYSTEM, "tools": [ALT_TOOL],
            "tool_choice": {"type": "tool", "name": ALT_TOOL["name"]},
            "messages": [{"role": "user", "content": ask}]}
    data = _post(body, key)
    cost = record(data_dir, cost_of(model, data.get("usage")))
    for block in data.get("content") or []:
        if block.get("type") == "tool_use":
            opts = [" ".join(str(x or "").split()) for x in (block.get("input") or {}).get("options") or []]
            seen, out = set(rejected), []
            for o in opts:
                if o and o not in seen:
                    seen.add(o)
                    out.append(o)
            if out:
                return out[:3], cost
    raise RuntimeError("Claude gave no other meaning — try again (or add a hint).")
