"""Download voice weights into plain folders under $TTS_WEIGHTS (default ~/.cache/tts), retrying on timeouts.
Plain folders, because Windows refused the Hugging Face cache's symlinks for one of the Qwen repos (WinError 1314);
tts_engines.py looks there first. Any env with huggingface_hub:

  HF_HUB_DISABLE_XET=1 HF_HUB_DOWNLOAD_TIMEOUT=60 python -X utf8 fetch_voices.py qwen [qwen-design] [chatterbox]

Kokoro and OmniVoice fetch their own weights through the normal cache on first use; the Qwen3-ASR models too.
"""
import os
import sys
import time
from pathlib import Path

from huggingface_hub import snapshot_download

TTS = Path(os.environ.get("TTS_WEIGHTS", Path.home() / ".cache" / "tts"))
REPOS = {
    "qwen": [("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", None)],
    "qwen-design": [("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", None)],
    "chatterbox": [("ResembleAI/chatterbox", ["ve.safetensors", "t3_cfg.safetensors", "s3gen.safetensors",
                                              "tokenizer.json", "conds.pt"]),
                   ("ResembleAI/chatterbox-turbo", ["*.safetensors", "*.json", "*.txt", "*.pt", "*.model"])],
}

for group in sys.argv[1:]:
    for repo, patterns in REPOS[group]:
        dest = TTS / repo.split("/")[1]
        for attempt in range(1, 9):
            try:
                snapshot_download(repo, local_dir=dest, allow_patterns=patterns)
                print(f"{repo}: ok -> {dest}", flush=True)
                break
            except Exception as exc:  # CDN timeouts; the next attempt resumes where this one stopped
                print(f"{repo}: attempt {attempt} failed ({type(exc).__name__}: {str(exc)[:120]})", flush=True)
                time.sleep(5)
        else:
            print(f"{repo}: GAVE UP", flush=True)
