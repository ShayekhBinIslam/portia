"""Transcribe the narration clips with Qwen3-ASR and compare each with what it should say; align words for cues.

A synthetic voice sometimes swallows, repeats or garbles words, or mispronounces a name. This flags clips whose
transcript drifts from the script. The score is a letter error rate: edit distance over letters only (spaces and
punctuation ignored, numbers in words on both sides), divided by the script's letter count. Run in the qwen3-asr (or
qwentts) env with nothing else on the GPU (ASR + aligner fill ~12 GB):

  python -X utf8 asr_check.py beats [s02_1,s04_2]   every clip in <audio>/timing.json (or those) -> <audio>/asr.json
  python -X utf8 asr_check.py align                 word start/end times for every clip -> <audio>/words.json

`align` runs Qwen3-ForcedAligner on the script's own spoken words, so scenes can start a visual on the word that names
it and captions can follow the voice. Run it again after any clip is re-rendered: the word times move.
"""
import json
import re
import sys
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project import AUDIO  # noqa: E402
from spoken_numbers import numbers_to_words  # noqa: E402

FLAG = 0.04  # letter error rate above which a clip is worth a listen or a re-render
LANGUAGE = "English"


def letters(text):
    """Letters only, numbers in words, and "zero point" as "point" (whether to say the leading zero is style)."""
    return re.sub(r"[^a-z]", "", numbers_to_words(text).lower()).replace("zeropoint", "point")


def error_rate(ref, hyp):
    a, b = letters(ref), letters(hyp)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1] / max(1, len(a))


def load(path):
    """16 kHz mono float32, the rate both Qwen3 audio models expect."""
    import librosa
    wav, sr = sf.read(path, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return librosa.resample(wav, orig_sr=sr, target_sr=16000), 16000


def timing():
    return json.loads((AUDIO / "timing.json").read_text(encoding="utf-8"))


def align():
    import torch
    from qwen_asr.inference.qwen3_forced_aligner import Qwen3ForcedAligner
    aligner = Qwen3ForcedAligner.from_pretrained("Qwen/Qwen3-ForcedAligner-0.6B", dtype=torch.bfloat16,
                                                 device_map="cuda:0")
    words = {}
    for bid, t in timing().items():
        result = aligner.align(audio=load(AUDIO / t["file"]), text=t["spoken"], language=LANGUAGE)[0]
        words[bid] = [{"w": it.text, "s": round(float(it.start_time), 3), "e": round(float(it.end_time), 3)}
                      for it in result.items]
        last = words[bid][-1]["e"] if words[bid] else 0
        print(f"{bid}: {len(words[bid])} words, last ends {last:.2f} s of {t['duration']:.2f} s", flush=True)
    (AUDIO / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")


def check(only=None):
    import torch
    from qwen_asr import Qwen3ASRModel
    jobs = [(bid, AUDIO / t["file"], t["spoken"]) for bid, t in timing().items() if only is None or bid in only]
    model = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-1.7B", max_inference_batch_size=1, dtype=torch.bfloat16,
                                          device_map="cuda:0")
    path = AUDIO / "asr.json"
    results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    flagged = []
    for name, wav, ref in jobs:
        hyp = model.transcribe(audio=[load(wav)], language=LANGUAGE)[0].text
        rate = error_rate(ref, hyp)
        results[name] = {"error_rate": round(rate, 4), "heard": hyp}
        mark = "CHECK" if rate > FLAG else "ok"
        print(f"{name:8s} {mark:5s} {rate:6.3f}  {hyp[:120]}", flush=True)
        if rate > FLAG:
            flagged.append(name)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(flagged)} of {len(jobs)} flagged: {','.join(flagged)}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "beats"
    if what == "align":
        align()
    else:
        check(set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None)
