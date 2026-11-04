"""Judge inputs for the GPU-pronunciation question (gpujudge.py): the same written lines read with three spellings of
"GPUs" (audio/takes/gj_<variant>), as 16 kHz mono WAVs, and targets.json with the WRITTEN text. The skill's
prep_judge_clips.py keeps only lines every voice read with identical spoken text; here the spellings differ on
purpose, and the judge should hear each reading against the line as written ("...our own GPUs...").

    python prep_gpu_judge.py build/gpujudge        (qwentts env: numpy, scipy, soundfile)
"""
import json
import sys
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
RATE = 16000


def main():
    out = Path(sys.argv[1])
    (out / "wav").mkdir(parents=True, exist_ok=True)
    targets = {}
    for v in ("orig", "a", "b"):
        d = HERE / "audio" / "takes" / f"gj_{v}"
        for bid, t in json.loads((d / "timing.json").read_text(encoding="utf-8")).items():
            wav, sr = sf.read(d / t["file"], dtype="float32")
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            g = gcd(RATE, sr)
            sf.write(out / "wav" / f"{v}__{bid}.wav", resample_poly(wav, RATE // g, sr // g).astype(np.float32), RATE)
            targets[bid] = t["text"]
    (out / "targets.json").write_text(json.dumps(targets, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(targets)} lines x 3 spellings -> {out}")


if __name__ == "__main__":
    main()
