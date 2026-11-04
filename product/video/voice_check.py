"""Screen the voice samples in audio/samples: does ASR hear every word, how much does the pitch move, how many
phrase pauses, how fast.

  python -X utf8 voice_check.py        (qwen3-asr or qwentts env; needs audio/samples/text.txt from voice_samples.py)

Flat pitch and few pauses are the usual signs of a robotic voice: people reading aloud move about 2 to 4 semitones
(SD) and pause at phrase ends; the rejected OmniVoice narrator paused (>= 0.2 s) once in 35 s, against 8 to 10 times
for the others. This is a screen for broken or monotone voices only. Choose between good voices with the voice-judge
skill (an audio model as judge), not with these numbers.
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from asr_check import error_rate, load  # noqa: E402

SAMPLES = HERE / "audio" / "samples"


def prosody(wav, sr):
    """Pitch SD and 5-95% range in semitones around the median, and the number of pauses of 0.2 s or more."""
    import librosa
    f0, voiced, _ = librosa.pyin(wav, fmin=60, fmax=400, sr=sr, frame_length=1024)
    f0 = f0[voiced & np.isfinite(f0)]
    st = 12 * np.log2(f0 / np.median(f0))
    rms = librosa.feature.rms(y=wav, frame_length=1024, hop_length=256)[0]
    quiet = rms < 0.1 * np.median(rms[rms > 0])
    runs, n = [], 0
    for q in quiet:
        if q:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    pauses = sum(1 for r in runs if r * 256 / sr >= 0.2)
    return float(np.std(st)), float(np.percentile(st, 95) - np.percentile(st, 5)), pauses


def main():
    import torch
    from qwen_asr import Qwen3ASRModel
    ref = (SAMPLES / "text.txt").read_text(encoding="utf-8")
    model = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-1.7B", max_inference_batch_size=1, dtype=torch.bfloat16,
                                          device_map="cuda:0")
    print(f"{'voice':28s} {'ASR err':>7s} {'pitch SD':>8s} {'range':>6s} {'pauses':>6s} {'wpm':>4s}")
    for path in sorted(SAMPLES.glob("*.wav")):
        wav, sr = load(path)
        hyp = model.transcribe(audio=[(wav, sr)], language="English")[0].text
        sd, rng, pauses = prosody(wav, sr)
        wpm = len(ref.split()) / (len(wav) / sr) * 60
        print(f"{path.stem:28s} {error_rate(ref, hyp):7.3f} {sd:7.2f}st {rng:5.1f}st {pauses:6d} {wpm:4.0f}", flush=True)


if __name__ == "__main__":
    main()
