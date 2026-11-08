"""Know a Country: synthesised sound design: music bed + sound effects (stereo, 44.1 kHz). No samples needed."""
import math
import numpy as np

SR = 44100
RNG = np.random.default_rng(11)


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _fft_filter(x, gain):
    """Zero-phase filtering in the frequency domain (gain = function of frequency in Hz)."""
    n = len(x)
    N = 1 << max(1, int(n - 1).bit_length())
    X = np.fft.rfft(x, N)
    f = np.fft.rfftfreq(N, 1 / SR)
    return np.fft.irfft(X * gain(f), N)[:n]


def lp(x, f, order=2):
    """Butterworth-shaped low-pass."""
    return _fft_filter(x, lambda fr: 1 / np.sqrt(1 + (fr / f) ** (2 * order)))


def hp(x, f, order=2):
    """Butterworth-shaped high-pass."""
    return _fft_filter(x, lambda fr: 1 / np.sqrt(1 + (f / np.maximum(fr, 1e-6)) ** (2 * order)))


def bp(x, f0, f1, order=2):
    return hp(lp(x, f1, order), f0, order)


def stereo(x, pan=0.0):
    """pan -1 (left) .. 1 (right); pan may be an array for movement."""
    a = (np.asarray(pan) + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


def sweep_noise(dur, f0, f1, width=0.6):
    """Noise whose spectral centre glides from f0 to f1 (log), via short-time FFT masking (overlap-add)."""
    n = int(dur * SR)
    nper, hop = 1024, 256
    x = RNG.standard_normal(n + nper)
    win = np.hanning(nper)
    f = np.fft.rfftfreq(nper, 1 / SR)
    logf = np.log(np.maximum(f, 1))
    out = np.zeros(len(x)); norm = np.zeros(len(x))
    for s0 in range(0, len(x) - nper + 1, hop):
        tt = min(1.0, max(0.0, (s0 + nper / 2) / SR / dur))
        c = math.exp(math.log(f0) + (math.log(f1) - math.log(f0)) * tt)
        mask = np.exp(-((logf - math.log(c)) ** 2) / (2 * width ** 2))
        y = np.fft.irfft(np.fft.rfft(x[s0:s0 + nper] * win) * mask, nper) * win
        out[s0:s0 + nper] += y
        norm[s0:s0 + nper] += win ** 2
    y = (out / np.maximum(norm, 1e-6))[:n]
    return y / (np.abs(y).max() + 1e-9)


# ---------------- effects ----------------
def whoosh(dur=0.65, up=True, gain=0.55):
    y = sweep_noise(dur, 250 if up else 3000, 3000 if up else 250, 0.55)
    tt = np.linspace(0, 1, len(y))
    env = np.sin(np.pi * tt ** 0.8) ** 2
    return stereo(y * env * gain, np.linspace(-0.6, 0.6, len(y)))


def whoosh_long(dur=1.5, gain=0.6):
    y = sweep_noise(dur, 180, 2600, 0.5)
    tt = np.linspace(0, 1, len(y))
    env = np.sin(np.pi * tt) ** 1.5
    rumble = lp(RNG.standard_normal(len(y)), 120, 4) * 3
    return stereo((y + rumble * 0.25) * env * gain, np.linspace(-0.8, 0.8, len(y)))


def impact(gain=0.9, depth=1.0):
    tt = _t(0.9)
    f = 38 + 55 * np.exp(-tt * 18)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 5.5)
    burst = lp(RNG.standard_normal(len(tt)), 900, 4) * np.exp(-tt * 28) * 1.6
    snap = hp(RNG.standard_normal(len(tt)), 3000) * np.exp(-tt * 120) * 0.25
    y = sub * depth + burst + snap
    return stereo(np.tanh(y * 1.3) * gain * 0.7)


def click(gain=0.22, pan=0.0):
    tt = _t(0.05)
    tone = np.sin(2 * np.pi * 1350 * tt) * np.exp(-tt * 140)
    tick = bp(RNG.standard_normal(len(tt)), 2500, 6000) * np.exp(-tt * 400) * 0.5
    return stereo((tone + tick) * gain, pan)


def pop(gain=0.35, pan=0.0):
    tt = _t(0.16)
    f = 260 + 520 * (1 - np.exp(-tt * 70))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 32)
    y = lp(y, 2400)
    return stereo(y * gain, pan)


def bell(f0=880.0, gain=0.22, dur=1.8, pan=0.0):
    tt = _t(dur)
    parts = [(1.0, 1.0, 1.6), (2.0, 0.45, 1.1), (2.76, 0.30, 0.8), (4.07, 0.16, 0.5), (5.43, 0.08, 0.35)]
    y = sum(a * np.sin(2 * np.pi * f0 * r * tt) * np.exp(-tt / d) for r, a, d in parts)
    y *= np.clip(tt / 0.004, 0, 1)
    return stereo(y * gain / 2, pan)


def shimmer(gain=0.18):
    out = np.zeros((int(1.4 * SR), 2))
    for k, (f, p) in enumerate([(1318.5, -0.5), (1568.0, 0.0), (1975.5, 0.5), (2637.0, 0.2)]):
        b = bell(f, gain, 1.2, p)
        i = int(k * 0.07 * SR)
        out[i:i + len(b)] += b[: len(out) - i]
    return out


def riser(dur=1.4, gain=0.35):
    y = sweep_noise(dur, 400, 6000, 0.45)
    tt = np.linspace(0, 1, len(y))
    tone = np.sin(2 * np.pi * np.cumsum(200 + 600 * tt ** 2) / SR) * 0.25
    return stereo((y + tone) * tt ** 2.2 * gain)


def pin_drop(gain=0.4):
    tt = _t(0.35)
    f = 1400 * np.exp(-tt * 6) + 300
    whistle = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(tt / 0.02, 0, 1) * np.exp(-tt * 9) * 0.25
    out = np.zeros((int(1.0 * SR), 2))
    out[: len(tt)] += stereo(whistle * gain)
    im = impact(gain * 0.6, depth=0.6)
    i = int(0.28 * SR)
    out[i:] += im[: len(out) - i]
    return out


def tick(gain=0.12, pan=0.0):
    tt = _t(0.03)
    y = np.sin(2 * np.pi * 2100 * tt) * np.exp(-tt * 260) + bp(RNG.standard_normal(len(tt)), 1500, 5000) * np.exp(-tt * 600) * 0.4
    return stereo(y * gain, pan)


def counter(dur=1.3, gain=0.12):
    """Rolling ticks that slow down, for numbers counting up."""
    out = np.zeros((int((dur + 0.1) * SR), 2))
    t, k = 0.0, 0
    while t < dur:
        tk = tick(gain * (1 - 0.5 * t / dur), pan=0.25 * np.sin(k))
        i = int(t * SR)
        out[i:i + len(tk)] += tk[: len(out) - i]
        t += 0.035 + 0.12 * (t / dur) ** 2
        k += 1
    return out


def swell(dur=0.9, gain=0.35):
    y = hp(RNG.standard_normal(int(dur * SR)), 2500)
    tt = np.linspace(0, 1, len(y))
    return stereo(y * tt ** 3 * gain * 0.6)


SFX = {"whoosh": whoosh, "whoosh_down": lambda: whoosh(up=False), "whoosh_long": whoosh_long, "impact": impact,
       "impact_soft": lambda: impact(0.5, 0.7), "click": click, "pop": pop, "bell": bell,
       "bell_low": lambda: bell(587.33, 0.2), "shimmer": shimmer, "riser": riser, "pin_drop": pin_drop,
       "counter": counter, "swell": swell, "tick": tick}


# ---------------- music ----------------
def music(total, bpm=96, gain=0.5):
    n = int(total * SR)
    beat = 60 / bpm
    out = np.zeros((n, 2))
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G (MIDI)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    bar = beat * 4
    nbars = int(total / bar) + 2
    pad = np.zeros(n)
    for b in range(nbars):
        ch = chords[b % 4]
        s0 = int(b * bar * SR)
        if s0 >= n:
            break
        L = min(n - s0, int((bar + 0.6) * SR))
        tt = np.arange(L) / SR
        env = np.clip(tt / 0.6, 0, 1) * np.clip((bar + 0.6 - tt) / 0.6, 0, 1)
        for m in ch:
            for det in (-0.08, 0.08):
                f = hz(m) * 2 ** (det / 12)
                for h in range(1, 6):
                    pad[s0:s0 + L] += np.sin(2 * np.pi * f * h * tt + h) / h * env * 0.022
        # bass on beats 1 and 3
        for bt in (0, 2):
            i = s0 + int(bt * beat * SR)
            if i >= n:
                continue
            Lb = min(n - i, int(beat * 1.8 * SR))
            tb = np.arange(Lb) / SR
            out[i:i + Lb] += stereo(np.sin(2 * np.pi * hz(ch[0] - 24) * tb) * np.exp(-tb * 2.2) * 0.16)
        # plucked arpeggio (8ths)
        for e in range(8):
            i = s0 + int(e * beat / 2 * SR)
            if i >= n:
                continue
            Lp = min(n - i, int(0.45 * SR))
            tp = np.arange(Lp) / SR
            f = hz(ch[[0, 1, 2, 1][e % 4]] + 12)
            y = (np.sin(2 * np.pi * f * tp) + 0.3 * np.sin(4 * np.pi * f * tp)) * np.exp(-tp * 9) * 0.05
            out[i:i + Lp] += stereo(y, 0.35 if e % 2 else -0.35)
    pad = lp(pad, 1600, 2)
    # drums: soft kick on 1 & 3, hats on off-beats, ducking the pad on kicks
    duck = np.ones(n)
    kick_t = _t(0.35)
    kick = np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-kick_t * 30)) / SR) * np.exp(-kick_t * 9) * 0.35
    hat_t = _t(0.05)
    hat = hp(RNG.standard_normal(len(hat_t)), 7000) * np.exp(-hat_t * 90) * 0.05
    t = 2 * bar  # drums enter after two bars
    k = 0
    while t < total - bar:
        i = int(t * SR)
        if k % 2 == 0:
            L = min(len(kick), n - i)
            out[i:i + L] += stereo(kick[:L])
            dl = min(int(0.3 * SR), n - i)
            duck[i:i + dl] = np.minimum(duck[i:i + dl], 0.55 + 0.45 * np.linspace(0, 1, dl))
        j = int((t + beat / 2) * SR)
        if j < n:
            L = min(len(hat), n - j)
            out[j:j + L] += stereo(hat[:L], 0.3)
        t += beat
        k += 1
    out += stereo(pad * duck)
    tt = np.arange(n) / SR
    fade = np.clip(tt / 1.0, 0, 1) * np.clip((total - tt) / 2.0, 0, 1)
    return out * fade[:, None] * gain


def mix(total, events, path):
    """events: list of (time_seconds, sfx_name). Writes a 16-bit stereo WAV."""
    import wave
    track = music(total)
    for t, name in events:
        s = SFX[name]()
        i = int(t * SR)
        if i >= len(track):
            continue
        L = min(len(s), len(track) - i)
        track[i:i + L] += s[:L]
    peak = np.abs(track).max()
    track = np.tanh(track / max(peak, 1e-6) * 1.4) / np.tanh(1.4) * 0.89
    pcm = (track * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
