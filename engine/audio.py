"""Sound design: synthesized SFX, music beds, external music/voice loading and the final mix."""
import math
import os
import subprocess
import wave

import numpy as np

from .core import ffmpeg_exe

SR = 44100
MOODS = ["Tension", "Mystery", "Calm", "Pulse", "Quiz Show", "Bright Pop", "Lo-fi Chill", "Epic", "Ambient", "None"]
MUSIC_BEDS = ["Quiz Show", "Bright Pop", "Lo-fi Chill", "Epic", "Ambient"]  # real chords + rhythm
INTRO_SOUNDS = ["Bass hit", "Cinematic boom", "Swoosh + impact", "Game show jingle", "Sparkle", "Deep drums", "None"]
TICK_SOUNDS = ["Classic", "Clock", "Wood block", "Soft click", "Digital beep", "Heartbeat", "None"]


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
        self.tick_kind, self.tick_gain, self.intro_kind = "Classic", 1.0, "Bass hit"
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

    def tick(self, f=1900):
        """One tick. f >= 2000 is the 'urgent' tick (last seconds / alternate beat)."""
        kind = self.tick_kind if self.tick_kind in TICK_SOUNDS else "Classic"
        if kind == "Classic":
            x = np.arange(int(0.035 * SR)) / SR
            return np.sin(2 * np.pi * f * x) * np.exp(-x * 140) * self.tick_gain
        return _tick_sound(kind, f >= 2000, self.rng) * self.tick_gain

    def configure(self, settings):
        """Read the sound choices from a project's settings."""
        s = settings or {}
        self.tick_kind = s.get("tick_sound") or "Classic"
        g = s.get("tick_gain")
        self.tick_gain = 1.0 if g is None else float(g)
        self.intro_kind = s.get("intro_sound") or "Bass hit"
        return self

    def intro(self, t0=0.05):
        """The opening sound of a video."""
        kind = self.intro_kind if self.intro_kind in INTRO_SOUNDS else "Bass hit"
        if kind == "Bass hit":
            self.add(t0, self.hit(1.6), 0.55)
        elif kind == "None":
            return
        elif kind == "Swoosh + impact":
            self.add(t0, self.riser(0.45), 0.35)
            self.add(t0 + 0.42, _reverb(self.hit(1.4), self.rng, 1.6, 0.3), 0.6)
        else:
            self.add(t0, _intro_sound(kind, self.rng), 0.6)

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
        return self._sizzle(dur) * self.tick_gain

    def _sizzle(self, dur):
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
        if mood in MUSIC_BEDS:
            return self.music_bed(mood, silences, gain)
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

    def music_bed(self, mood, silences, gain=1.0):
        """Built-in music: a synthesized loop with chords, bass and drums (see MUSIC_BEDS)."""
        loop = _music_loop(mood, np.random.default_rng(17))
        reps = int(math.ceil(self.n / len(loop)))
        st = np.tile(loop, (reps, 1))[:self.n]
        self.bed += st * self.silence_env(silences)[:, None] * gain

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


def sound_demo(settings, out_path, dur=9.0):
    """A short sample of the chosen intro, music and ticking (for the app's Listen button)."""
    s = settings or {}
    mx = Mixer(dur).configure(s)
    mx.intro(0.05)
    for k in range(5):  # countdown: the last two ticks are the urgent ones
        hi = k >= 3
        mx.add(3.0 + k, mx.tick(2400 if hi else 1500), 0.32 if hi else 0.24)
    mx.add(8.0, mx.ding(), 0.55)
    gain = float(s.get("music_gain") if s.get("music_gain") is not None else 1.0)
    if s.get("music_file") and os.path.isfile(s["music_file"]):
        mx.music_file(s["music_file"], [], gain)
    else:
        mx.synth_bed(s.get("music") or "Tension", [], gain)
    mx.write(out_path)
    return out_path


# ====================================================================== instruments
def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def _norm(x, peak=1.0):
    m = np.abs(x).max()
    return x / m * peak if m > 0 else x


def _fade(x, a=0.003, r=0.02):
    n = len(x)
    env = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    env[:na] = np.linspace(0, 1, na)[:n]
    env[-nr:] = np.minimum(env[-nr:], np.linspace(1, 0, nr)[-n:])
    return x * env


def _lowpass(x, cutoff):
    """Brick-wall-ish low-pass via FFT (fine for short loops)."""
    spec = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    roll = np.clip(1 - (f - cutoff) / (cutoff * 0.5), 0, 1)
    spec *= roll[:, None] if spec.ndim == 2 else roll
    return np.fft.irfft(spec, len(x), axis=0)


def _pluck(f, dur=0.6, bright=1.0, parts=8):
    t = _t(dur)
    sig = sum((1.0 / k ** 1.15) * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (2.5 + 3.0 * k / bright))
              for k in range(1, parts + 1) if f * k < 12000)
    return _fade(sig, 0.002, 0.03)


def _keys(f, dur=1.6):
    t = _t(dur)
    sig = np.sin(2 * np.pi * f * t) * np.exp(-t * 1.6) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4.5) \
        + 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 9)
    return _fade(sig * (1 + 0.12 * np.sin(2 * np.pi * 4.8 * t)), 0.004, 0.2)


def _pad(freqs, dur, attack=0.5, release=0.8, parts=6):
    t = _t(dur)
    sig = np.zeros((len(t), 2))
    for f in freqs:
        for ch, det in ((0, 0.997), (1, 1.003)):  # detuned copies left/right = wide chorus
            for k in range(1, parts + 1):
                if f * k < 9000:
                    sig[:, ch] += (1.0 / k ** 1.4) * np.sin(2 * np.pi * f * det * k * t + k * ch)
    env = np.minimum(1, t / attack) * np.minimum(1, np.maximum(0, (dur - t) / release))
    return sig * env[:, None]


def _bass(f, dur=0.4):
    t = _t(dur)
    sig = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.1 * np.sin(2 * np.pi * 3 * f * t)
    return _fade(sig * np.exp(-t * 3.0), 0.004, 0.05)


def _kick(dur=0.32):
    t = _t(dur)
    f = 45 + 110 * np.exp(-t * 32)
    return _fade(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) + 0.15 * np.exp(-t * 300), 0.001, 0.02)


def _snare(rng, dur=0.22, clap=False):
    t = _t(dur)
    nz = np.diff(rng.standard_normal(len(t) + 1))
    if clap:  # three quick bursts
        env = sum(np.exp(-np.maximum(0, t - d) * 60) * (t >= d) for d in (0.0, 0.011, 0.022)) / 2
        return _fade(nz * env * np.exp(-t * 14), 0.001, 0.02)
    return _fade(nz * np.exp(-t * 22) * 0.8 + 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28), 0.001, 0.02)


def _hat(rng, dur=0.06, open_=False):
    t = _t(0.22 if open_ else dur)
    nz = np.diff(np.diff(rng.standard_normal(len(t) + 2)))
    return _fade(nz * np.exp(-t * (14 if open_ else 70)), 0.001, 0.01)


def _tom(f0=80, dur=0.7):
    t = _t(dur)
    f = f0 * (1 + 0.6 * np.exp(-t * 18))
    return _fade(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5), 0.001, 0.05)


def _reverb(x, rng, secs=1.6, mix=0.3):
    """Small hall reverb: convolve with a decaying, darkened noise tail (via FFT)."""
    t = _t(secs)
    ir = rng.standard_normal(len(t)) * np.exp(-t * 4.5 / secs)
    ir = np.convolve(ir, np.ones(12) / 12, mode="same")  # darker
    n = len(x) + len(ir)
    wet = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)
    wet = wet / (np.abs(wet).max() + 1e-9) * np.abs(x).max()
    out = np.zeros(n)
    out[:len(x)] += x * (1 - mix)
    return out + wet * mix


def _place(buf, t, sig, gain=1.0, pan=0.0):
    """Mix a mono (or stereo) signal into a stereo loop buffer, wrapping around the loop end."""
    i = int(t * SR) % len(buf)
    sig = np.asarray(sig) * gain
    if sig.ndim == 1:
        sig = np.stack([sig * np.sqrt((1 - pan) / 2), sig * np.sqrt((1 + pan) / 2)], axis=1) * np.sqrt(2)
    n = len(sig)
    end = min(len(buf), i + n)
    buf[i:end] += sig[:end - i]
    if i + n > len(buf):  # tail wraps to the loop start, so tiling is seamless
        buf[:i + n - len(buf)] += sig[end - i:end - i + i + n - len(buf)]


# ====================================================================== music beds
_LOOPS = {}
_TARGET_RMS = 0.042  # same loudness as the original drone beds


def _music_loop(mood, rng):
    if mood in _LOOPS:
        return _LOOPS[mood]
    make = {"Quiz Show": _quiz_show, "Bright Pop": _bright_pop, "Lo-fi Chill": _lofi, "Epic": _epic,
            "Ambient": _ambient}[mood]
    loop = make(rng)
    loop = loop / (np.sqrt((loop ** 2).mean()) + 1e-9) * _TARGET_RMS
    peak = np.abs(loop).max()
    if peak > 0.32:  # keep headroom for voice and effects
        loop *= 0.32 / peak
    _LOOPS[mood] = loop
    return loop


def _new(bpm, bars=4):
    beat = 60.0 / bpm
    return np.zeros((int(round(bars * 4 * beat * SR)), 2)), beat


def _quiz_show(rng):
    buf, b = _new(116)
    prog = [(48, [60, 64, 67]), (45, [57, 60, 64]), (41, [57, 60, 65]), (43, [59, 62, 67])]  # C Am F G
    kick, clap = _kick(), _snare(rng, clap=True)
    for bar, (root, chord) in enumerate(prog):
        t0 = bar * 4 * b
        _place(buf, t0, _pad([_hz(n) for n in chord], 4 * b, 0.3, 0.4), 0.10)
        for k in range(8):  # bouncy octave bass in 8ths
            _place(buf, t0 + k * b / 2, _bass(_hz(root + (12 if k % 2 else 0)), b / 2 * 0.9), 0.55)
        arp = chord + [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[0] + 24, chord[2] + 12]
        for k in range(8):  # plucked arpeggio
            _place(buf, t0 + k * b / 2, _pluck(_hz(arp[k] + 12), 0.45, 1.3), 0.16, -0.3 if k % 2 else 0.3)
        for k in range(4):
            if k in (0, 2):
                _place(buf, t0 + k * b, kick, 0.9)
            else:
                _place(buf, t0 + k * b, clap, 0.42, 0.05)
        for k in range(8):
            _place(buf, t0 + k * b / 2, _hat(rng), 0.10 if k % 2 else 0.05, 0.35)
    return buf


def _bright_pop(rng):
    buf, b = _new(122)
    prog = [(43, [67, 71, 74]), (38, [66, 69, 74]), (40, [67, 71, 76]), (36, [64, 67, 72])]  # G D Em C
    kick, clap = _kick(0.28), _snare(rng, clap=True)
    for bar, (root, chord) in enumerate(prog):
        t0 = bar * 4 * b
        _place(buf, t0, _pad([_hz(n - 12) for n in chord], 4 * b, 0.6, 0.6, parts=4), 0.07)
        for k in range(4):
            _place(buf, t0 + k * b, kick, 0.85)  # four on the floor
            _place(buf, t0 + k * b + b / 2, _bass(_hz(root), b / 2 * 0.85), 0.5)  # off-beat bass
            _place(buf, t0 + k * b + b / 2, _hat(rng, open_=True), 0.07, 0.3)
            for n in chord:  # off-beat chord stabs
                _place(buf, t0 + k * b + b / 2, _pluck(_hz(n), 0.25, 2.0, 6), 0.07, -0.2)
            if k in (1, 3):
                _place(buf, t0 + k * b, clap, 0.4)
        lead = [chord[2] + 12, chord[1] + 12, chord[0] + 12, chord[1] + 12]
        for k, n in enumerate(lead):  # small bell hook on each bar
            _place(buf, t0 + k * b, _pluck(_hz(n), 0.5, 3.0, 3), 0.06, 0.25)
    return buf


def _lofi(rng):
    buf, b = _new(78)
    prog = [(41, [53, 57, 60, 64]), (40, [52, 55, 59, 62]), (38, [50, 53, 57, 60]), (36, [48, 52, 55, 59])]
    kick, snare = _kick(0.3), _snare(rng)
    swing = 0.08 * b
    for bar, (root, chord) in enumerate(prog):  # Fmaj7 Em7 Dm7 Cmaj7
        t0 = bar * 4 * b
        for hit in (0, 1.5 * b):
            for j, n in enumerate(chord):
                _place(buf, t0 + hit + j * 0.012, _keys(_hz(n + 12), 2.2), 0.13, -0.2 + 0.13 * j)
        _place(buf, t0, _bass(_hz(root), 1.6 * b), 0.5)
        _place(buf, t0 + 2.5 * b, _bass(_hz(root + 7), 1.2 * b), 0.4)
        _place(buf, t0, kick, 0.7)
        _place(buf, t0 + 2.5 * b, kick, 0.55)
        for k in (1, 3):
            _place(buf, t0 + k * b, snare, 0.3)
        for k in range(8):
            _place(buf, t0 + k * b / 2 + (swing if k % 2 else 0), _hat(rng), 0.05, 0.3)
    buf = _lowpass(buf, 5200)
    crackle = (rng.random(len(buf)) > 0.9994) * rng.uniform(-1, 1, len(buf))  # vinyl
    buf += np.stack([crackle, np.roll(crackle, 37)], axis=1) * 0.05 + rng.standard_normal((len(buf), 2)) * 0.002
    return buf


def _epic(rng):
    buf, b = _new(90)
    prog = [(45, [57, 60, 64]), (41, [53, 57, 60]), (48, [55, 60, 64]), (43, [55, 59, 62])]  # Am F C G
    for bar, (root, chord) in enumerate(prog):
        t0 = bar * 4 * b
        _place(buf, t0, _pad([_hz(n) for n in chord] + [_hz(root)], 4 * b + 0.3, 1.2, 1.0, parts=8), 0.12)
        for k in range(8):  # driving low ostinato
            _place(buf, t0 + k * b / 2, _pluck(_hz(root), 0.3, 0.7, 6), 0.35 if k % 4 == 0 else 0.22)
        for pos, f, g in ((0, 70, 0.9), (1.5, 90, 0.5), (2, 70, 0.75), (3.5, 110, 0.4)):
            _place(buf, t0 + pos * b, _tom(f), g)
    _place(buf, 0, _reverb(_kick(0.9), rng, 2.0, 0.45), 0.7)
    return buf


def _ambient(rng):
    buf, b = _new(64)
    prog = [[48, 55, 62, 64, 71], [45, 52, 59, 60, 67], [41, 48, 55, 57, 64], [43, 50, 57, 59, 64]]
    for bar, chord in enumerate(prog):  # Cmaj9 Am9 Fmaj9 G6/9 — long swells
        t0 = bar * 4 * b
        _place(buf, t0, _pad([_hz(n) for n in chord], 4 * b + 1.2, 1.8, 1.6, parts=5), 0.11)
    scale = [72, 74, 76, 79, 81, 84]
    for k in range(10):  # sparse bell notes
        _place(buf, rng.uniform(0, len(buf) / SR), _pluck(_hz(scale[rng.integers(len(scale))]), 1.8, 4.0, 3),
               0.05, rng.uniform(-0.6, 0.6))
    return _lowpass(buf, 7000)


# ====================================================================== intros & ticks
def _intro_sound(kind, rng):
    if kind == "Cinematic boom":
        t = _t(3.0)
        sub = np.sin(2 * np.pi * np.cumsum(30 + 60 * np.exp(-t * 5)) / SR) * np.exp(-t * 1.3)
        nz = np.convolve(rng.standard_normal(len(t)), np.ones(40) / 40, mode="same") * np.exp(-t * 6) * 4
        return _norm(_reverb(sub + nz, rng, 2.5, 0.4))
    if kind == "Game show jingle":
        out = np.zeros(int(2.2 * SR))
        for k, n in enumerate([72, 76, 79, 84]):
            sig = _pluck(_hz(n), 0.6, 2.5)
            i = int(k * 0.09 * SR)
            out[i:i + len(sig)] += sig * 0.8
        i = int(0.38 * SR)
        for n in (72, 76, 79, 84, 88):
            sig = _pluck(_hz(n), 1.6, 3.0)
            out[i:i + len(sig)] += sig * 0.45
        return _norm(_reverb(out, rng, 1.4, 0.3))
    if kind == "Sparkle":
        out = np.zeros(int(2.5 * SR))
        for k, n in enumerate([84, 88, 91, 93, 96, 98, 100, 103]):
            sig = _pluck(_hz(n), 1.2, 5.0, 3)
            i = int(k * 0.055 * SR)
            out[i:i + len(sig)] += sig * (0.6 + 0.05 * k)
        return _norm(_reverb(out, rng, 2.0, 0.45))
    if kind == "Deep drums":
        out = np.zeros(int(2.4 * SR))
        for d, f, g in ((0.0, 62, 1.0), (0.2, 75, 0.7), (0.42, 58, 1.0)):
            sig, sn = _tom(f, 1.2), _snare(rng, 0.15)
            sig[:len(sn)] += sn * 0.15
            i = int(d * SR)
            out[i:i + len(sig)] += sig * g
        return _norm(_reverb(out, rng, 1.8, 0.35))
    return np.zeros(1)


def _tick_sound(kind, urgent, rng):
    if kind == "None":
        return np.zeros(1)
    if kind == "Clock":  # mechanical tick (urgent = higher 'tock')
        t = _t(0.06)
        f1, f2 = (3400, 1700) if urgent else (2600, 1250)
        click = np.diff(rng.standard_normal(len(t) + 1)) * np.exp(-t * 900)
        sig = click * 0.5 + np.sin(2 * np.pi * f1 * t) * np.exp(-t * 260) + 0.6 * np.sin(2 * np.pi * f2 * t) * np.exp(-t * 140)
    elif kind == "Wood block":
        t = _t(0.12)
        f = 1150 if urgent else 900
        sig = np.sin(2 * np.pi * f * t) * np.exp(-t * 55) + 0.45 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 95)
    elif kind == "Soft click":
        t = _t(0.03)
        sig = np.sin(2 * np.pi * (900 if urgent else 650) * t) * np.exp(-t * 260) \
            + 0.3 * np.convolve(rng.standard_normal(len(t)), np.ones(6) / 6, mode="same") * np.exp(-t * 500)
        sig *= 0.6
    elif kind == "Digital beep":
        t = _t(0.075)
        f = 1480 if urgent else 1000
        sig = sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 3, 5)) * 0.8
    else:  # Heartbeat: lub-dub
        t = _t(0.42)
        lub = (np.sin(2 * np.pi * 58 * t) + 0.5 * np.sin(2 * np.pi * 116 * t)) * np.exp(-t * 20)
        d = int(0.17 * SR)
        dub = np.zeros_like(t)
        dub[d:] = ((np.sin(2 * np.pi * 50 * t) + 0.4 * np.sin(2 * np.pi * 100 * t)) * np.exp(-t * 26))[:len(t) - d] * 0.7
        sig = (lub + dub) * (1.25 if urgent else 1.0)
        return _fade(sig, 0.002, 0.03) / 1.25
    return _norm(_fade(sig, 0.001, 0.01))
