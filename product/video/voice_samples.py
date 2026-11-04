"""Read the same beats with each candidate voice, for a quick screen (voice_check.py) or for the user to hear.

  python -X utf8 voice_samples.py <engine> [<engine> ...] [--beats s02_1,s04_2]   (each engine in its own env)

Writes audio/samples/<engine>.wav (the beats joined by a 0.6 s pause, peak-normalized) and audio/samples/text.txt
(what they read), and prints length and speaking rate. For choosing the narrator, render real takes of 8 or more
beats instead (tts_render.py --out audio/takes/<engine>) and judge them (the voice-judge skill).
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project import script  # noqa: E402
from tts_engines import load  # noqa: E402

OUT = HERE / "audio" / "samples"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engines", nargs="+")
    ap.add_argument("--beats", help="default: the first two beats")
    args = ap.parse_args()
    all_beats = [(bid, sp) for _, bid, _, sp in script().beats()]
    pick = args.beats.split(",") if args.beats else [b for b, _ in all_beats[:2]]
    lines = [(b, sp) for b, sp in all_beats if b in pick]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "text.txt").write_text(" ".join(sp for _, sp in lines), encoding="utf-8")
    for name in args.engines:
        t0 = time.time()
        synth = load(name)
        parts, sr = [], None
        for _, sp in lines:
            wav, sr = synth(sp)
            parts += [np.asarray(wav, dtype=np.float32), np.zeros(int(sr * 0.6), dtype=np.float32)]
        wav = np.concatenate(parts[:-1])
        wav = wav / max(1e-6, float(np.max(np.abs(wav)))) * 0.89
        sf.write(OUT / f"{name}.wav", wav, sr, subtype="PCM_16")
        words = sum(len(sp.split()) for _, sp in lines)
        print(f"{name}: {len(wav) / sr:.1f} s, {words / (len(wav) / sr) * 60:.0f} wpm, made in {time.time() - t0:.0f} s",
              flush=True)


if __name__ == "__main__":
    main()
