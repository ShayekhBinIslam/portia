"""Voice the narration in script.py: one WAV per beat, plus <audio>/timing.json with each clip's length and text.

  python -X utf8 tts_render.py render [--engine qwen-ryan] [--force] [--only s02_1,s02_2] [--out audio/takes/x]

Run it in the engine's env (tts_engines.py). With --out, a candidate take goes to its own folder; adopt it by copying
its wavs and timing.json into audio/ (or assemble two voices with duo.py). A clip is rendered again only when its
spoken text, the engine or the engine's instruction (tts_engines.instruction) changed, or with --force (sampling then
gives a new take, which is the fix for a garbled or mispronounced clip).

Every clip is trimmed (audio below -45 dB of the clip's peak at either end, 60 ms kept), levelled to -20 dBFS RMS
with the peak capped at -1.5 dBFS, resampled to 48 kHz and written as 16-bit mono WAV. Speed is never changed after
rendering: stretched or slowed voices sounded robotic.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project import AUDIO, script  # noqa: E402

TARGET_RMS_DB, PEAK_DB, FLOOR_DB, KEEP_S = -20.0, -1.5, -45.0, 0.06
OUT_SR = 48000


def tidy(wav, sr):
    """Trim silence at both ends (keep 60 ms), then level to the target loudness without clipping."""
    wav = np.asarray(wav, dtype=np.float32).squeeze()
    env = np.convolve(np.abs(wav), np.ones(int(sr * 0.02)) / int(sr * 0.02), mode="same")
    loud = np.flatnonzero(env > 10 ** (FLOOR_DB / 20) * max(1e-9, float(np.max(np.abs(wav)))))
    if loud.size:
        pad = int(sr * KEEP_S)
        wav = wav[max(0, loud[0] - pad): loud[-1] + pad]
    rms = float(np.sqrt(np.mean(wav ** 2))) or 1e-9
    wav = wav * (10 ** (TARGET_RMS_DB / 20) / rms)
    peak = float(np.max(np.abs(wav))) or 1e-9
    if peak > 10 ** (PEAK_DB / 20):
        wav = wav * (10 ** (PEAK_DB / 20) / peak)
    return wav


def resample(wav, sr, target=OUT_SR):
    """librosa where the engine's env has it, else scipy's polyphase filter (the Kokoro env has only scipy)."""
    if sr == target:
        return wav
    try:
        import librosa
        return librosa.resample(wav, orig_sr=sr, target_sr=target)
    except ImportError:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr, target)
        return resample_poly(wav, target // g, sr // g).astype(np.float32)


def render(args):
    from tts_engines import instruction, load
    out = Path(args.out) if args.out else AUDIO
    out.mkdir(parents=True, exist_ok=True)
    timing_path = out / "timing.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else {}
    only = set(args.only.split(",")) if args.only else None
    instruct = instruction(args.engine)
    todo = []
    for sid, bid, text, spoken in script().beats():
        key = hashlib.md5(f"{spoken}|{args.engine}|{instruct}".encode()).hexdigest()[:10]
        done = timing.get(bid, {}).get("key") == key and (out / f"{bid}.wav").exists()
        if (only is None or bid in only) and (args.force or not done):
            todo.append((sid, bid, text, spoken, key))
    print(f"{len(todo)} clips to render with {args.engine}", flush=True)
    if not todo:
        return
    synth = load(args.engine)
    for sid, bid, text, spoken, key in todo:
        try:
            wav, sr = synth(spoken)
            wav = tidy(wav, sr)
        except Exception as exc:  # keep going; the clip stays missing and the next run retries it
            print(f"{bid}: FAILED {exc}", flush=True)
            continue
        wav = resample(wav, sr)
        sf.write(out / f"{bid}.wav", wav, OUT_SR, subtype="PCM_16")
        timing[bid] = {"scene": sid, "file": f"{bid}.wav", "duration": round(len(wav) / OUT_SR, 3), "key": key,
                       "engine": args.engine, "text": text, "spoken": spoken}
        timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")  # after every clip
        print(f"{bid}: {timing[bid]['duration']:.2f} s  {len(spoken.split()) / timing[bid]['duration'] * 60:.0f} wpm",
              flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--engine", default="qwen-ryan")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out")
    render(ap.parse_args())


if __name__ == "__main__":
    main()
