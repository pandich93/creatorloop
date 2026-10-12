"""Original soundtrack for the reel, synthesised from scratch (no samples, no third-party audio).

Reads src/timeline.json (bpm, scenes, drop, sfx) so music and animation share one beat grid.
Writes public/track.wav (48 kHz stereo, -14 LUFS integrated, true peak <= -1 dBTP).

    python music/compose.py            # full mix
    python music/compose.py --no-sfx   # music only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
TL = json.loads((ROOT / "src" / "timeline.json").read_text())
SR = 48_000
BPM = TL["bpm"]
BEAT = 60 / BPM
TOTAL_BEATS = TL["totalBeats"]
DROP = TL["dropBeat"]
N = int(TOTAL_BEATS * BEAT * SR)
rng = np.random.default_rng(7)

CHORDS = {  # pad voicing (midi), bass root (midi)
    "Am": ([57, 60, 64, 69], 33),
    "F": ([53, 57, 60, 65], 29),
    "C": ([55, 60, 64, 67], 36),
    "G": ([55, 59, 62, 67], 31),
}
PROG = TL["chords"]
FINAL = TL.get("finalBeat", 60)  # groove stops, the final card rings out
OUTRO = TL.get("outroBeat", 56)  # second impact (conclusion line)
BREAK = tuple(TL.get("breakBeats") or (0, 0))  # optional breakdown without kick, e.g. [48, 52]
RISE = max(0, DROP - 4)  # riser + snare roll into the drop
PULSE = max(0, DROP - 8)  # quiet heartbeat before the riser


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def t_(beat: float) -> int:
    return int(round(beat * BEAT * SR))


def bus() -> np.ndarray:
    return np.zeros((N, 2))


def add(dst: np.ndarray, x: np.ndarray, start: int, gain: float = 1.0, pan: float = 0.0) -> None:
    """Mix mono or stereo x into dst at sample `start` with constant-power pan (-1..1)."""
    if start >= N:
        return
    x = x[: N - start]
    if x.ndim == 1:
        a = (pan + 1) * np.pi / 4
        x = np.stack([x * np.cos(a), x * np.sin(a)], axis=1)
    dst[start : start + len(x)] += x * gain


def saw(f: float, n: int, phase: float = 0.0) -> np.ndarray:
    """Band-limited sawtooth by additive synthesis."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, int(min(48, 18_000 / f)) + 1):
        out += np.sin(2 * np.pi * k * f * t + k * phase) / k
    return out * (2 / np.pi)


def env_adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    sus_n = max(n - a_n - d_n - r_n, 0)
    e = np.concatenate([np.linspace(0, 1, a_n, endpoint=False), np.linspace(1, s, d_n, endpoint=False),
                        np.full(sus_n, s), np.linspace(s, 0, r_n)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]


def lowpass_sweep(x: np.ndarray, cut: np.ndarray, q_order: int = 2, block: int = 256) -> np.ndarray:
    """Time-varying low-pass: filter coefficients updated every `block` samples, state carried over."""
    y = np.zeros_like(x)
    zi = None
    for i in range(0, len(x), block):
        c = float(np.clip(cut[min(i, len(cut) - 1)], 40, SR / 2.2))
        sos = signal.butter(q_order, c, "low", fs=SR, output="sos")
        if zi is None:
            zi = np.zeros((sos.shape[0], 2))
        y[i : i + block], zi = signal.sosfilt(sos, x[i : i + block], zi=zi)
    return y


def bandpass(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(signal.butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def highpass(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(signal.butter(order, f, "high", fs=SR, output="sos"), x, axis=0)


def reverb(x: np.ndarray, seconds: float = 2.2, wet: float = 0.3) -> np.ndarray:
    n = int(seconds * SR)
    decay = np.exp(-np.linspace(0, 7, n))
    out = x.copy()
    for ch in range(2):
        ir = rng.standard_normal(n) * decay
        ir = signal.sosfilt(signal.butter(1, 6000, "low", fs=SR, output="sos"), ir)
        ir /= np.sqrt(np.sum(ir**2))
        out[:, ch] += wet * signal.fftconvolve(x[:, ch], ir)[: len(x)]
    return out


def delay(x: np.ndarray, beats: float = 0.75, fb: float = 0.35, wet: float = 0.3) -> np.ndarray:
    d = int(beats * BEAT * SR)
    out = x.copy()
    tap = x.copy()
    for i in range(1, 6):
        tap = np.roll(tap, d, axis=0) * fb
        tap[:d] = 0
        tap = tap[:, ::-1]  # ping-pong
        out += wet * tap
    return out


# ---------------------------------------------------------------- arrangement helpers
def chord_at(beat: float) -> str:
    return PROG[int(beat // 4) % len(PROG)]


def in_drop(beat: float) -> bool:
    return DROP <= beat < FINAL


def sidechain_env() -> np.ndarray:
    """Gain curve ducking pad/bass under every kick in the groove section."""
    g = np.ones(N)
    rel = np.exp(-np.arange(int(0.22 * SR)) / (0.07 * SR))
    for b in range(DROP, FINAL):
        s = t_(b)
        seg = 1 - 0.65 * rel[: N - s]
        g[s : s + len(seg)] = np.minimum(g[s : s + len(seg)], seg)
    return g


# ---------------------------------------------------------------- instruments
def kick() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t / 0.035)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16)
    click = bandpass(rng.standard_normal(n), 2000, 7000) * np.exp(-t / 0.004) * 0.35
    return np.tanh(1.6 * (body + click))


def clap() -> np.ndarray:
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    noise = bandpass(rng.standard_normal(n), 900, 5000)
    e = np.exp(-t / 0.09)
    for off in (0.0, 0.011, 0.022):
        e += 0.6 * np.exp(-np.maximum(t - off, 0) / 0.006) * (t >= off)
    return noise * e * 0.6


def hat(open_: bool = False) -> np.ndarray:
    n = int((0.22 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    return highpass(rng.standard_normal(n), 8000) * np.exp(-t / (0.07 if open_ else 0.012))


def impact() -> np.ndarray:
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t / 0.08)) / SR) * np.exp(-t / 0.7)
    crash = highpass(rng.standard_normal(n), 3500) * np.exp(-t / 0.55) * 0.35
    return np.tanh(1.3 * boom) + crash


def pluck(m: int, length: float = 0.24) -> np.ndarray:
    n = int(length * SR)
    t = np.arange(n) / SR
    x = 0.6 * saw(hz(m), n) + 0.4 * saw(hz(m) * 1.004, n, 0.7)
    cut = 600 + 5200 * np.exp(-t / 0.06)
    return lowpass_sweep(x, cut) * np.exp(-t / 0.11)


def build_music() -> dict[str, np.ndarray]:
    stems = {k: bus() for k in ("drums", "bass", "pad", "pluck", "fx")}
    duck = sidechain_env()[:, None]

    # --- pad: whole song, filter opens through the intro, rings out at the end
    for bar in range(TOTAL_BEATS // 4):
        b0 = bar * 4
        notes, _ = CHORDS[chord_at(b0)]
        n = t_(4) + int(0.6 * SR)
        x = np.zeros(n)
        for m in notes:
            for det, ph in ((-0.07, 0.0), (0.0, 1.3), (0.07, 2.1)):
                x += saw(hz(m + det), n, ph)
        x *= env_adsr(n, 0.35, 0.3, 0.8, 0.6) / (len(notes) * 3)
        t_rel = np.arange(n) / SR + b0 * BEAT
        marks = [0, DROP * BEAT, OUTRO * BEAT, FINAL * BEAT, TOTAL_BEATS * BEAT]
        cut = np.interp(t_rel, marks, [350 if DROP > 4 else 900, 2600, 2600, 1400, 700])
        x = lowpass_sweep(x, cut)
        add(stems["pad"], x, t_(b0), 0.55, pan=-0.25 if bar % 2 else 0.25)
    stems["pad"] = reverb(stems["pad"], 2.6, 0.35)

    # --- intro pulse (PULSE..DROP): quiet sub heartbeat + rising 16th hats
    for b in np.arange(PULSE, DROP, 1.0):
        n = int(0.3 * SR)
        tt = np.arange(n) / SR
        add(stems["bass"], np.sin(2 * np.pi * 55 * tt) * np.exp(-tt / 0.12), t_(b), 0.35 * (0.6 + (b - PULSE) / 20))
    for s in np.arange(PULSE, DROP, 0.25):
        add(stems["drums"], hat(), t_(s), 0.05 + 0.12 * (s - PULSE) / max(DROP - PULSE, 1), pan=0.3)

    # --- riser + snare roll into the drop (no volume dip before it)
    rn = t_(DROP) - t_(RISE)
    tt = np.arange(rn) / SR
    riser = lowpass_sweep(rng.standard_normal(rn), np.interp(tt, [0, tt[-1]], [400, 9000]))
    riser *= np.linspace(0.05, 0.5, rn) ** 1.5
    tone = np.sin(2 * np.pi * np.cumsum(np.interp(tt, [0, tt[-1]], [220, 880])) / SR) * np.linspace(0, 0.12, rn)
    add(stems["fx"], np.stack([riser + tone, riser * 0.9 + tone], 1), t_(RISE), 1.0)
    roll = list(np.arange(RISE, DROP - 2, 0.5)) + list(np.arange(DROP - 2, DROP - 1, 0.25)) + list(np.arange(DROP - 1, DROP, 0.125))
    for i, b in enumerate(roll):
        add(stems["drums"], clap(), t_(b), 0.25 + 0.5 * i / len(roll))

    # --- groove section (DROP..FINAL)
    for b in range(DROP, FINAL):
        if not BREAK[0] <= b < BREAK[1]:
            add(stems["drums"], kick(), t_(b), 0.95)
            if b % 2 == 1:
                add(stems["drums"], clap(), t_(b), 0.55)
        add(stems["drums"], hat(open_=True), t_(b + 0.5), 0.16, pan=0.35)
        for q in (0.25, 0.75):
            add(stems["drums"], hat(), t_(b + q), 0.07, pan=-0.3)
    accents = sorted({DROP, OUTRO, *[c for c in TL.get("cuts", []) if DROP < c < FINAL]})
    for b in accents:
        add(stems["fx"], impact(), t_(b), 0.75 if b in (DROP, OUTRO) else 0.3)
    add(stems["fx"], impact(), 0, 0.3)  # soft hit under the hook so the very first frame has weight
    # mini riser + snare fill into the conclusion accent (out of the break if there is one)
    fill_from = BREAK[1] if BREAK[1] else OUTRO - 4
    rn = t_(OUTRO) - t_(fill_from)
    tt = np.arange(rn) / SR
    r2 = lowpass_sweep(rng.standard_normal(rn), np.interp(tt, [0, tt[-1]], [600, 8000])) * np.linspace(0.02, 0.3, rn) ** 1.5
    add(stems["fx"], np.stack([r2, r2], 1), t_(fill_from), 1.0)
    for i, b in enumerate(np.arange(OUTRO - 1, OUTRO, 0.125)):
        add(stems["drums"], clap(), t_(b), 0.25 + 0.04 * i)

    # bass: off-beat 8ths on the chord root (classic pumping), octave jump on the last 8th of each bar
    for b in range(DROP, FINAL):
        _, root = CHORDS[chord_at(b)]
        m = root + 12 if b % 4 == 3 else root
        n = int(0.45 * BEAT * SR)
        x = saw(hz(m), n) + 0.5 * np.sin(2 * np.pi * hz(m) * np.arange(n) / SR)
        tt = np.arange(n) / SR
        x = lowpass_sweep(x, 300 + 900 * np.exp(-tt / 0.05)) * env_adsr(n, 0.004, 0.05, 0.8, 0.03)
        add(stems["bass"], x, t_(b + 0.5), 0.3 if BREAK[0] <= b < BREAK[1] else 0.55)

    # pluck arp: syncopated 16ths over chord tones, octave 5
    pattern = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1]
    order = [0, 2, 1, 3, 2, 1, 3, 2]
    step = 0
    for s in np.arange(DROP, FINAL, 0.25):
        idx = int(round((s - DROP) * 4)) % 16
        if pattern[idx]:
            notes, _ = CHORDS[chord_at(s)]
            m = notes[order[step % len(order)]] + 12
            step += 1
            add(stems["pluck"], pluck(m), t_(s), 0.22, pan=0.4 * np.sin(step))
    stems["pluck"] = reverb(delay(stems["pluck"], 0.75, 0.38, 0.35), 1.8, 0.25)

    # --- outro: last chord swell + bell on the final card
    for m in (69, 72, 76, 81):
        n = int(4.0 * SR)
        tt = np.arange(n) / SR
        bell = (np.sin(2 * np.pi * hz(m) * tt) + 0.3 * np.sin(2 * np.pi * hz(m) * 2.01 * tt)) * np.exp(-tt / 1.1)
        add(stems["pluck"], bell, t_(FINAL) + int((m - 69) * 0.012 * SR), 0.07, pan=(m - 74) / 12)

    # ducking + groove-only processing
    stems["pad"] *= np.where(np.arange(N)[:, None] < t_(DROP), 1.0, duck * 0.9 + 0.1)
    stems["bass"] *= duck
    return stems


# ---------------------------------------------------------------- sound design
def sfx_bus() -> np.ndarray:
    out = bus()
    for ev in TL["sfx"]:
        for b in ev["beats"]:
            kind = ev["type"]
            if kind == "type":
                n = int(0.03 * SR)
                tt = np.arange(n) / SR
                x = bandpass(rng.standard_normal(n), 1800, 6500) * np.exp(-tt / 0.006)
                x += 0.4 * np.sin(2 * np.pi * rng.uniform(1500, 2300) * tt) * np.exp(-tt / 0.004)
                add(out, x, t_(b), 0.22, pan=rng.uniform(-0.3, 0.3))
            elif kind == "whoosh":
                n = int(0.5 * SR)
                tt = np.arange(n) / SR
                x = lowpass_sweep(rng.standard_normal(n), np.interp(tt, [0, 0.4, 0.5], [300, 5000, 2000]))
                x *= np.interp(tt, [0, 0.38, 0.5], [0, 1, 0]) ** 2
                add(out, np.stack([x, np.roll(x, 400)], 1), t_(b), 0.3)
            elif kind == "click":
                n = int(0.04 * SR)
                tt = np.arange(n) / SR
                x = np.sin(2 * np.pi * 2400 * tt) * np.exp(-tt / 0.006) + 0.3 * highpass(rng.standard_normal(n), 4000) * np.exp(-tt / 0.003)
                add(out, x, t_(b), 0.16)
            elif kind == "delete":
                n = int(0.12 * SR)
                tt = np.arange(n) / SR
                f = np.interp(tt, [0, tt[-1]], [900, 260])
                x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-tt / 0.04)
                add(out, lowpass_sweep(x, np.full(n, 2500.0)), t_(b), 0.12)
            elif kind == "confirm":
                for k, m in enumerate((76, 81)):
                    n = int(0.9 * SR)
                    tt = np.arange(n) / SR
                    x = np.sin(2 * np.pi * hz(m) * tt) * np.exp(-tt / 0.35)
                    add(out, x, t_(b) + int(k * 0.09 * SR), 0.18)
            # "impact" is part of the music bus
    return reverb(out, 1.2, 0.15)


# ---------------------------------------------------------------- master
def limiter(x: np.ndarray, ceiling_db: float = -1.2) -> np.ndarray:
    ceil = 10 ** (ceiling_db / 20)
    peak = np.max(np.abs(x), axis=1)
    need = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    look = int(0.005 * SR)
    # attack: min over a 5 ms look-ahead window; release: one-pole 80 ms
    win = np.lib.stride_tricks.sliding_window_view(np.pad(need, (0, look), constant_values=1), look + 1).min(axis=1)
    g = np.empty_like(win)
    a = np.exp(-1 / (0.08 * SR))
    cur = 1.0
    for i, v in enumerate(win):
        cur = v if v < cur else a * cur + (1 - a) * v
        g[i] = cur
    return x * g[:, None]


def true_peak_db(x: np.ndarray) -> float:
    up = signal.resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.max(np.abs(up)) + 1e-12)


def master(mix: np.ndarray) -> np.ndarray:
    mix = highpass(mix, 28)
    mix = np.tanh(mix * 1.15) / 1.15  # gentle glue saturation
    fade = np.ones(N)
    fade[-int(1.6 * SR):] = np.linspace(1, 0, int(1.6 * SR)) ** 1.5
    mix *= fade[:, None]
    meter = pyln.Meter(SR)
    for _ in range(4):
        mix *= 10 ** ((-14.0 - meter.integrated_loudness(mix)) / 20)
        mix = limiter(mix, -1.3)
    return mix


def main() -> None:
    stems = build_music()
    mix = stems["drums"] * 0.9 + stems["bass"] + stems["pad"] + stems["pluck"] + stems["fx"] * 0.8
    if "--no-sfx" not in sys.argv:
        mix += sfx_bus() * 0.8
    out = master(mix)
    lufs = pyln.Meter(SR).integrated_loudness(out)
    tp = true_peak_db(out)
    (ROOT / "public").mkdir(exist_ok=True)
    sf.write(ROOT / "public" / "track.wav", out.astype(np.float32), SR, subtype="PCM_16")
    print(f"track.wav  {N / SR:.2f}s  {lufs:.1f} LUFS  true peak {tp:.1f} dBTP")


if __name__ == "__main__":
    main()
