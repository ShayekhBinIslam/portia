"""Freeze one OmniVoice speaker so every clip, today's and future ones, sounds like the same person.

OmniVoice invents a new speaker for each clip when given only a description (measured 296, 121 and 157 Hz on three
consecutive words), and even its voice-design mode drifts. So render one reference sentence several times from the
description, keep the take with the most typical pitch and the steadiest delivery, and save it as a voice-clone
prompt; tts_engines.py "omni" then clones from voice/narrator.pt for every clip. omnivoice env:

  python -X utf8 make_frozen_voice.py [--instruct "female, young adult, moderate pitch, american accent"] [--takes 5]

`instruct` is a closed vocabulary of comma-separated tokens, not free text (free descriptions are rejected): e.g.
female, male, young adult, middle-aged, elderly, moderate pitch, whisper, american accent, british accent.
Writes voice/take<k>.wav, voice/narrator_ref.wav, voice/narrator.pt and voice/narrator.json.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from tts_render import tidy

HERE = Path(__file__).resolve().parent
VOICE = HERE / "voice"
REF_TEXT = ("Every fixed stretch of time, a memory loses the same fraction of what is left. "
            "That is what a half-life means, and it is the heart of the first model.")


def pitch_stats(wav, sr, female):
    """Median and SD of f0 in Hz. pYIN's floor must fit the voice: fmin=70 pins short female clips to the floor."""
    import librosa
    y = librosa.resample(wav, orig_sr=sr, target_sr=16000)
    f0, voiced, prob = librosa.pyin(y, fmin=120 if female else 70, fmax=450 if female else 300, sr=16000)
    f0 = f0[voiced & (prob > 0.5)]
    return (float(np.median(f0)), float(np.std(f0))) if f0.size else (float("nan"), float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instruct", default="female, young adult, moderate pitch, american accent")
    ap.add_argument("--takes", type=int, default=5)
    ap.add_argument("--ref-text", default=REF_TEXT)
    args = ap.parse_args()
    import torch
    from omnivoice import OmniVoice
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda", dtype=torch.float16)
    sr, female = model.sampling_rate, "female" in args.instruct
    VOICE.mkdir(parents=True, exist_ok=True)
    takes = []
    for k in range(1, args.takes + 1):
        wav = tidy(model.generate(text=args.ref_text, instruct=args.instruct, num_step=32, guidance_scale=2.0)[0], sr)
        med, sd = pitch_stats(wav, sr, female)
        sf.write(VOICE / f"take{k}.wav", wav, sr)
        takes.append((med, sd, wav, k))
        print(f"take {k}: {len(wav) / sr:.1f} s, pitch {med:.0f} Hz, sd {sd:.0f}", flush=True)
    typical = float(np.nanmedian([t[0] for t in takes]))
    med, sd, wav, k = min(takes, key=lambda t: abs(t[0] - typical) + 0.5 * t[1])  # typical pitch, steady
    sf.write(VOICE / "narrator_ref.wav", wav, sr)
    audio = torch.from_numpy(np.asarray(wav, dtype=np.float32)).unsqueeze(0)
    model.create_voice_clone_prompt(ref_audio=(audio, sr), ref_text=args.ref_text).save(str(VOICE / "narrator.pt"))
    (VOICE / "narrator.json").write_text(json.dumps({"instruct": args.instruct, "take": k, "pitch_hz": round(med),
                                                    "pitch_sd": round(sd), "ref_text": args.ref_text}, indent=1),
                                         encoding="utf-8")
    print(f"kept take {k} (pitch {med:.0f} Hz, sd {sd:.0f}) -> voice/narrator.pt")


if __name__ == "__main__":
    main()
