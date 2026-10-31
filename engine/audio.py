"""Sound design: synthesized SFX, music beds, external music/voice loading and the final mix."""
import math
import os
import subprocess
import wave

import numpy as np

from .core import ffmpeg_exe

SR = 44100
MOODS = ["Tension", "Mystery", "Calm", "Pulse", "None"]


def load_audio(path):
    """Decode any audio file (mp3, wav, m4a…) to float stereo at 44.1 kHz."""
    p = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", path, "-f", "s16le", "-acodec", "pcm_s16le",
                        "-ac", "2", "-ar", str(SR), "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"Could not read audio file: {path}")
    return np.frombuffer(p.stdout, np.int16).reshape(-1, 2).astype(np.float64) / 32768.0


def _moving_avg(x, k):
    """Same result as np.convolve(x, np.ones(k) / k, mode="same"), but O(n) instead of O(n*k)
    (the direct convolution took minutes on long narrated videos)."""
    n = len(x)
    if k > n:  # tiny input: keep np.convolve's exact behaviour (output length k)
        return np.convolve(x, np.ones(k) / k, mode="same")
    c = np.concatenate(([0.0], np.cumsum(x)))
    j = np.arange(n) + (k - 1) // 2  # index into the full convolution
    hi = np.minimum(j, n - 1) + 1
    lo = np.maximum(j - k + 1, 0)
    return (c[hi] - c[lo]) / k


_len_cache = {}


def audio_length(path):
    """Length of an audio file in seconds (cached per file and modification time)."""
    key = (os.path.abspath(path), os.path.getmtime(path))
    if key not in _len_cache:
        _len_cache[key] = len(load_audio(path)) / SR
    return _len_cache[key]


class Mixer:
    def __init__(self, dur, seed=3):
        self.dur = dur
        self.n = int(SR * dur)
        self.sfx = np.zeros((self.n, 2))
        self.bed = np.zeros((self.n, 2))
        self.voice = np.zeros((self.n, 2))
        self.has_voice = False
        self.rng = np.random.default_rng(seed)

    # -------------------------------------------------- placement
    def add(self, t0, sig, gain=1.0, pan=0.0):
        i = int(t0 * SR)
        n = min(len(sig), self.n - i)
        if n <= 0 or i < 0:
            return
        pan = np.full(n, pan) if np.ndim(pan) == 0 else np.asarray(pan)[:n]
        self.sfx[i:i + n, 0] += sig[:n] * gain * np.sqrt((1 - pan) / 2)
        self.sfx[i:i + n, 1] += sig[:n] * gain * np.sqrt((1 + pan) / 2)

    # -------------------------------------------------- generators
    def _lp_sweep(self, noise, cut):
        out = np.empty_like(noise)
        y = 0.0
        a = 1 - np.exp(-2 * np.pi * cut / SR)
        for k in range(len(noise)):
            y += a[k] * (noise[k] - y)
            out[k] = y
        return out

    def whoosh(self, dur=1.0):
        n = int(dur * SR)
        x = np.linspace(0, 1, n)
        env = np.sin(np.pi * x) ** 2
        s = self._lp_sweep(self.rng.standard_normal(n), 250 + 3200 * np.sin(np.pi * x) ** 1.5) * env
        return s / (np.abs(s).max() + 1e-9), np.linspace(-0.7, 0.7, n)

    @staticmethod
    def tick(f=1900):
        x = np.arange(int(0.035 * SR)) / SR
        return np.sin(2 * np.pi * f * x) * np.exp(-x * 140)

    @staticmethod
    def pop():
        n = int(0.16 * SR)
        x = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(380 + 700 * x / 0.16) / SR) * np.exp(-x * 28)

    def hit(self, dur=2.2):
        n = int(dur * SR)
        x = np.arange(n) / SR
        f = 32 + 60 * np.exp(-x * 9)
        sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 1.6)
        nz = self._lp_sweep(self.rng.standard_normal(n), np.full(n, 900.0)) * np.exp(-x * 14) * 3
        s = sub + 0.35 * np.sin(2 * np.pi * np.cumsum(2 * f) / SR) * np.exp(-x * 3) + nz
        return s / np.abs(s).max()

    def riser(self, dur):
        n = int(dur * SR)
        x = np.linspace(0, 1, n)
        s = self._lp_sweep(self.rng.standard_normal(n), 200 + 7000 * x ** 2) * x ** 2
        return s / (np.abs(s).max() + 1e-9)

    def sizzle(self, dur):
        n = int(dur * SR)
        x = np.linspace(0, 1, n)
        nz = self.rng.standard_normal(n)
        hp = np.diff(nz, prepend=0.0)
        crackle = (self.rng.random(n) > 0.9993) * self.rng.uniform(0.5, 1.0, n)
        crackle = np.convolve(crackle, np.exp(-np.arange(300) / 40.0), mode="same")
        s = hp * 0.35 * (0.7 + 0.3 * np.sin(2 * np.pi * 7 * x)) + crackle * self.rng.choice([-1, 1], n)
        s *= np.clip(x * 20, 0, 1) * np.clip((1 - x) * 30, 0, 1)
        return s / (np.abs(s).max() + 1e-9)

    @staticmethod
    def ding():
        x = np.arange(int(1.2 * SR)) / SR
        a = np.sin(2 * np.pi * 1046.5 * x) * np.exp(-x * 5)
        k = int(0.09 * SR)
        b = np.zeros_like(x)
        b[k:] = np.sin(2 * np.pi * 1318.5 * x[:-k]) * np.exp(-x[:-k] * 4)
        s = 0.7 * a + b
        return s / np.abs(s).max()

    @staticmethod
    def chime():
        x = np.arange(int(2.5 * SR)) / SR
        s = sum(a * np.sin(2 * np.pi * f * x) * np.exp(-x * d)
                for f, a, d in [(880, 1, 2.2), (1320, .5, 3), (1760, .3, 4), (2640, .15, 5)])
        return s / np.abs(s).max()

    # -------------------------------------------------- beds
    def silence_env(self, silences):
        x = np.arange(self.n) / SR
        env = np.clip(x / 1.2, 0, 1) * np.clip((self.dur - x) / 1.0, 0, 1)
        for a, b in silences:
            g = np.ones(self.n)
            g = np.where((x >= a - 0.35) & (x < a), (a - x) / 0.35, g)
            g = np.where((x >= a) & (x < b + 0.55), 0.0, g)
            g = np.where((x >= b + 0.55) & (x < b + 1.55), (x - (b + 0.55)) / 1.0, g)
            env *= g
        return env

    def synth_bed(self, mood, silences, gain=1.0):
        if mood == "None":
            return
        x = np.arange(self.n) / SR
        presets = {
            "Tension": ([(73.4, 1, 0), (110, .6, 1), (146.8, .35, 2), (174.6, .18, 3)], 0.18, (60, 450), 0.35, 0),
            "Mystery": ([(55, 1, 0), (82.4, .55, 1), (103.8, .3, 2), (130.8, .2, 3)], 0.09, (40, 350), 0.55, 0),
            "Calm": ([(110, .8, 0), (164.8, .5, 1), (220, .35, 2), (277.2, .25, 3)], 0.12, (150, 800), 0.25, 0),
            "Pulse": ([(65.4, 1, 0), (98, .6, 1), (130.8, .3, 2)], 0.1, (60, 400), 0.3, 1.6),
        }
        tones, lfo, (lo, hi), pad_amt, pulse = presets.get(mood, presets["Tension"])
        drone = sum(a * np.sin(2 * np.pi * f * x + p) for f, a, p in tones)
        drone *= 0.75 + 0.25 * np.sin(2 * np.pi * lfo * x)
        if pulse:
            drone *= 0.55 + 0.45 * np.exp(-((x * pulse) % 1.0) * 6)
        drone /= np.abs(drone).max()
        st = np.zeros((self.n, 2))
        fr = np.fft.rfftfreq(self.n, 1 / SR)
        for ch in range(2):
            spec = np.fft.rfft(self.rng.standard_normal(self.n))
            spec[(fr < lo) | (fr > hi)] = 0
            pad = np.fft.irfft(spec, self.n)
            pad /= np.abs(pad).max() + 1e-9
            st[:, ch] = drone * 0.8 + pad * pad_amt
        self.bed += st * self.silence_env(silences)[:, None] * 0.16 * gain

    def music_file(self, path, silences, gain=1.0):
        a = load_audio(path)
        reps = int(math.ceil(self.n / len(a)))
        a = np.tile(a, (reps, 1))[:self.n]
        a /= np.abs(a).max() + 1e-9
        self.bed += a * self.silence_env(silences)[:, None] * 0.35 * gain

    def add_voice(self, path, offset=0.5, gain=1.0):
        v = load_audio(path)
        i = int(offset * SR)
        n = min(len(v), self.n - i)
        if n > 0:
            v = v / (np.abs(v).max() + 1e-9) * 0.9
            self.voice[i:i + n] += v[:n] * gain
            self.has_voice = True

    # -------------------------------------------------- final mix
    def write(self, path):
        bed = self.bed
        if self.has_voice:  # duck the music under the voice
            mono = np.abs(self.voice).mean(axis=1)
            k = int(0.25 * SR)
            env = _moving_avg(mono, k)
            ref = np.percentile(env[env > 1e-4], 95) if np.any(env > 1e-4) else 1.0
            duck = 1 - 0.6 * np.clip(env / (ref + 1e-9), 0, 1)
            bed = bed * duck[:, None]
        mix = self.sfx + bed + self.voice
        mix = np.tanh(mix * 1.3) / np.tanh(1.3)
        peak = np.abs(mix).max()
        if peak > 0:
            mix = mix / peak * 0.89
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((mix * 32767).astype(np.int16).tobytes())
