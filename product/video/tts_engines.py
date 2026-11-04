"""Narration voices. load(name) returns synth(text) -> (float32 mono waveform, sample rate). Each engine runs in its
own conda env (see ../env), so imports happen inside the loaders.

  qwen-ryan (default)          Qwen3-TTS 1.7B CustomVoice, English male preset "Ryan" + a delivery instruction  qwentts
  qwen-aiden                   the same model, English male preset "Aiden"                                     qwentts
  qwen-design                  Qwen3-TTS 1.7B VoiceDesign: a voice described in words (DESIGN)                 qwentts
  kokoro-heart, kokoro-michael Kokoro 82M presets af_heart (US female) and am_michael (US male)                kokoro
  omni                         OmniVoice cloning the frozen narrator voice/narrator.pt (make_frozen_voice.py)  omnivoice
  chatterbox, chatterbox-turbo Chatterbox (Resemble AI) built-in voice; "-narrator" clones voice/narrator_ref.wav  chatterbox

Weights come from a plain folder $TTS_WEIGHTS/<repo name> (fetch_voices.py) if there is one, else the Hugging Face
cache, else a download. TTS_INSTRUCT replaces the Qwen delivery instruction, TTS_LANGUAGE the language (English).
"""
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VOICE = HERE / "voice"
LOCAL = Path(os.environ.get("TTS_WEIGHTS", Path.home() / ".cache" / "tts"))
LANGUAGE = os.environ.get("TTS_LANGUAGE", "English")

# the instruction every Qwen narration so far used (DS641 proposal, literature and game videos)
DELIVERY = os.environ.get("TTS_INSTRUCT", ("Speak naturally and warmly, like a graduate student presenting their research to classmates: relaxed, "
    "conversational pace, natural pauses, light emphasis on the key numbers. Not like a newsreader."))
DESIGN = ("A friendly young woman with a clear, warm American English voice, presenting her research to classmates. "
          "Relaxed and conversational, with natural pauses and lively intonation, not like a newsreader.")


def weights(repo):
    local = LOCAL / repo.split("/")[1]
    if local.exists():
        return str(local)
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo, local_files_only=True)
    except Exception:  # not cached yet
        return snapshot_download(repo)


def _qwen(repo, **kw):
    import torch
    from qwen_tts import Qwen3TTSModel
    dev = os.environ.get("TTS_DEVICE", "cuda:0")          # "cpu" when no GPU has room (float32 there)
    if dev == "cpu":
        torch.set_num_threads(int(os.environ.get("TTS_THREADS", "32")))
    model = Qwen3TTSModel.from_pretrained(weights(repo), device_map=dev,
                                          dtype=torch.float32 if dev == "cpu" else torch.bfloat16, attn_implementation="sdpa")
    custom = "CustomVoice" in repo

    def synth(text):
        if custom:
            wavs, sr = model.generate_custom_voice(text=text, language=LANGUAGE, **kw)
        else:
            wavs, sr = model.generate_voice_design(text=text, language=LANGUAGE, **kw)
        return np.asarray(wavs[0], dtype=np.float32).squeeze(), sr
    return synth


def _kokoro(voice, speed=1.0):
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="a")  # "a" = American English, "b" = British

    def synth(text):
        return np.concatenate([np.asarray(a, dtype=np.float32) for _, _, a in pipe(text, voice=voice, speed=speed)]), 24000
    return synth


def _omni(speed=0.88):
    import torch
    from omnivoice import OmniVoice, VoiceClonePrompt
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda", dtype=torch.float16)
    prompt = VoiceClonePrompt.load(str(VOICE / "narrator.pt"))

    def synth(text):
        wav = model.generate(text=text, voice_clone_prompt=prompt, speed=speed, num_step=32, guidance_scale=2.0)[0]
        return np.asarray(wav, dtype=np.float32).squeeze(), model.sampling_rate
    return synth


def _chatterbox(ref=None, turbo=False, exaggeration=0.5, cfg_weight=0.5):
    if turbo:
        from chatterbox.tts_turbo import ChatterboxTurboTTS as Model
        local, kw = LOCAL / "chatterbox-turbo", {}
    else:
        from chatterbox.tts import ChatterboxTTS as Model
        local, kw = LOCAL / "chatterbox", {"exaggeration": exaggeration, "cfg_weight": cfg_weight}
    model = Model.from_local(local, "cuda") if local.exists() else Model.from_pretrained(device="cuda")

    def synth(text):
        wav = model.generate(text, audio_prompt_path=str(ref) if ref else None, **kw)
        return wav.squeeze().detach().cpu().numpy().astype(np.float32), model.sr
    return synth


ENGINES = {
    "qwen-ryan": lambda: _qwen("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", speaker="Ryan", instruct=DELIVERY),
    "qwen-aiden": lambda: _qwen("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", speaker="Aiden", instruct=DELIVERY),
    "qwen-design": lambda: _qwen("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", instruct=DESIGN),
    "kokoro-heart": lambda: _kokoro("af_heart"),
    "kokoro-michael": lambda: _kokoro("am_michael"),
    "omni": lambda: _omni(),
    "chatterbox": lambda: _chatterbox(),
    "chatterbox-narrator": lambda: _chatterbox(VOICE / "narrator_ref.wav"),
    "chatterbox-turbo": lambda: _chatterbox(turbo=True),
    "chatterbox-turbo-narrator": lambda: _chatterbox(VOICE / "narrator_ref.wav", turbo=True),
}


def load(name):
    return ENGINES[name]()


def instruction(name):
    """The text instruction an engine reads with; part of tts_render.py's cache key, so editing it re-renders."""
    return DESIGN if name == "qwen-design" else DELIVERY if name.startswith("qwen") else ""
