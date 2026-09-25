"""Synthesize the demo video's sound cues: soft taps, four event sounds and the outro swell.

The cues are generated in code with numpy so they need no licence. The music bed is a separate
track (docs/demo/music/, Kevin MacLeod, CC BY 4.0) that scripts/record_demo.py mixes under the cues.

    uv run python scripts/demo_audio.py <seconds> <cues.json> <out.wav>

cues.json is a list of {"t": seconds, "kind": "tap" | "whoosh" | "chime" | "connect" | "confirm" | "approve" | "deny" | "swell"}.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((n / SR - t) / max(release, 1e-4), 0, 1)
    return np.minimum(a, r)


def _note(freq: float, seconds: float, gain: float, harmonics=(1.0, 0.35, 0.12)) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    y = sum(g * np.sin(2 * np.pi * freq * k * t) for k, g in enumerate(harmonics, start=1))
    return gain * y * _env(n, 0.02, seconds * 0.6)


def _seq(parts: list[tuple[float, float]], seconds: float, gain: float, harmonics=(1.0, 0.3)) -> np.ndarray:
    """Notes at offsets, each played to the end of its own envelope so nothing is cut mid-ring."""
    n = int((max(off for _, off in parts) + seconds) * SR)
    y = np.zeros(n)
    for f, off in parts:
        note = _note(f, seconds, gain, harmonics)
        s0 = int(off * SR)
        y[s0:s0 + len(note)] += note[: n - s0]
    return y


def cue(kind: str) -> np.ndarray:
    if kind == "tap":
        n = int(0.06 * SR)
        t = np.arange(n) / SR
        # Quiet: a tap marks the pointer, it is not an event.
        return 0.2 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 120) + 0.1 * np.sin(2 * np.pi * 900 * t) * np.exp(-t * 90)
    if kind == "whoosh":
        # Camera moves are silent; a short soft pitch rise reads as motion without noise.
        n = int(0.3 * SR)
        t = np.arange(n) / SR
        f = 520 + 260 * t / 0.3
        return 0.035 * np.sin(2 * np.pi * f * t) * _env(n, 0.05, 0.22)
    if kind == "chime":
        return _seq([(1174.66, 0.0), (1567.98, 0.07)], 0.5, 0.3)
    if kind == "deny":
        # Two low, hollow notes falling a semitone: reads as a no, nothing like the reward sounds.
        return _seq([(196.0, 0.0), (185.0, 0.17)], 0.3, 0.42, (1.0, 0.0, 0.5, 0.0, 0.22))
    if kind == "connect":
        # Soft two-note pop: the agent is paired.
        return _seq([(783.99, 0.0), (1046.5, 0.09)], 0.3, 0.28, (1.0, 0.25))
    if kind == "confirm":
        # Three-note rise: the plan is authorized.
        return _seq([(659.25, 0.0), (830.61, 0.11), (1046.5, 0.22)], 0.45, 0.3, (1.0, 0.3, 0.08))
    if kind == "approve":
        # The reward: a bright major arpeggio with a shimmer on top, purchase approved.
        y = _seq([(523.25, 0.0), (659.25, 0.09), (783.99, 0.18), (1046.5, 0.27), (1318.5, 0.42)], 0.7, 0.2, (1.0, 0.35, 0.1))
        n = len(y)
        t = np.arange(n) / SR
        shimmer = 0.06 * np.sin(2 * np.pi * 2093.0 * t) * np.sin(2 * np.pi * 6 * t) * _env(n, 0.4, 0.5)
        return y + shimmer
    if kind == "swell":
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        y = sum(0.16 * np.sin(2 * np.pi * f * t) for f in (293.66, 369.99, 440.0, 587.33))
        return y * _env(n, 0.9, 0.6)
    raise ValueError(f"unknown cue {kind}")


def render(seconds: float, cues: list[dict]) -> np.ndarray:
    n = int(seconds * SR)
    mix = np.zeros(n)
    for c in cues:
        y = cue(c["kind"])
        s = int(c["t"] * SR)
        e = min(n, s + len(y))
        if s < n:
            mix[s:e] += y[: e - s]
    peak = float(np.max(np.abs(mix)))
    if peak > 0.98:
        mix *= 0.98 / peak
    return mix


def write_wav(path: Path, y: np.ndarray) -> None:
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    stereo = np.repeat(pcm, 2)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


if __name__ == "__main__":
    seconds = float(sys.argv[1])
    cues = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3])
    write_wav(out, render(seconds, cues))
    print(f"wrote {out} ({seconds:.1f} s, {len(cues)} cues)")
