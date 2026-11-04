"""Write the short sound cues the scenes use: no music, only struck tones well under the narration (clips sit at
-20 dBFS RMS; these peak at -15 to -24 dBFS).

  chime.wav   two-note marimba-like chime for the title card
  tick.wav    soft woodblock tick for each countdown second
  tock.wav    lower tick that ends a countdown
  reveal.wav  gentle rising pair of notes for a reveal

  python sounds.py      (`video` env) -> audio/*.wav at 48 kHz stereo
"""
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project import SOUNDS  # noqa: E402

SR = 48000


def struck(freq, length, partials=((1.0, 1.0, 0.55), (3.9, 0.22, 0.12), (9.2, 0.06, 0.04))):
    """A struck bar: decaying partials (ratio, amplitude, decay seconds) with a 4 ms attack so it does not click."""
    t = np.arange(int(SR * length)) / SR
    tone = sum(amp * np.exp(-t / tau) * np.sin(2 * np.pi * freq * ratio * t) for ratio, amp, tau in partials)
    return tone * np.minimum(1, t / 0.004)


def mix(notes, peak_db):
    n = max(int(SR * start) + len(sig) for start, sig, _ in notes)
    out = np.zeros(n)
    for start, sig, gain in notes:
        out[int(SR * start): int(SR * start) + len(sig)] += gain * sig
    return out * 10 ** (peak_db / 20) / np.max(np.abs(out))


def save(name, mono):
    SOUNDS.mkdir(parents=True, exist_ok=True)
    wavfile.write(SOUNDS / name, SR, (np.stack([mono, mono], axis=1) * 32767).astype(np.int16))
    print(f"wrote {name} ({mono.size / SR:.2f} s)")


def main():
    save("chime.wav", mix([(0.0, struck(659.25, 1.8), 1.0), (0.14, struck(987.77, 1.8), 0.8)], -15))  # E5, B5
    wood = ((1.0, 1.0, 0.035), (2.7, 0.35, 0.015), (5.4, 0.1, 0.008))
    save("tick.wav", mix([(0.0, struck(1250, 0.18, wood), 1.0)], -24))
    save("tock.wav", mix([(0.0, struck(820, 0.3, wood), 1.0)], -21))
    save("reveal.wav", mix([(0.0, struck(523.25, 1.6), 1.0), (0.12, struck(783.99, 1.6), 0.85)], -19))  # C5, G5


if __name__ == "__main__":
    main()
