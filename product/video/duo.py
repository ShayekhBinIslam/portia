"""Two narrators taking turns beat by beat (default: Qwen3-TTS Ryan and Kokoro af_heart, the best male and female
voices in our SpeechJudge comparison). Each voice keeps its own pace: Kokoro reads ~11% faster than Ryan, and slowing
or time-stretching it to match was rejected as robotic.

  python -X utf8 duo.py beats <voice>   the beats that voice reads, comma-separated (for tts_render.py --only)
  python -X utf8 duo.py assemble        fill VIDEO_AUDIO from finished single-voice takes in audio/takes/<voice>/

Typical run (each tts_render in its engine's env), then asr_check.py align on the assembled folder:
  tts_render.py render --engine qwen-ryan    --only $(duo.py beats qwen-ryan)    --out audio/takes/qwen-ryan
  tts_render.py render --engine kokoro-heart --only $(duo.py beats kokoro-heart) --out audio/takes/kokoro-heart
  VIDEO_AUDIO=audio_duo duo.py assemble
DUO_VOICES="a,b" picks other voices.
"""
import json
import os
import shutil
import sys

from project import AUDIO, TAKES, script

VOICES = tuple(os.environ.get("DUO_VOICES", "qwen-ryan,kokoro-heart").split(","))


def speakers():
    return {bid: VOICES[i % len(VOICES)] for i, (_, bid, _, _) in enumerate(script().beats())}


def assemble():
    AUDIO.mkdir(parents=True, exist_ok=True)
    spoken = {bid: sp for _, bid, _, sp in script().beats()}
    timing = {}
    for bid, voice in speakers().items():
        take = TAKES / voice
        t = json.loads((take / "timing.json").read_text(encoding="utf-8"))[bid]
        assert t["spoken"] == spoken[bid], f"{voice} take of {bid} is from an older script"
        shutil.copy(take / t["file"], AUDIO / t["file"])
        timing[bid] = t
    (AUDIO / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {v: sum(1 for x in speakers().values() if x == v) for v in VOICES}
    print(f"{len(timing)} clips into {AUDIO.name}: {counts}")


if __name__ == "__main__":
    if sys.argv[1] == "beats":
        print(",".join(bid for bid, v in speakers().items() if v == sys.argv[2]))
    elif sys.argv[1] == "assemble":
        assemble()
