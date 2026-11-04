"""portia/judge/paths.py: where Portia finds what predates the hackathon (the benchmark, its videos, its search index)
and a few machine-specific tools. Each path comes from, in order: an environment variable of the same name;
`paths.local.json` at the repo root (machine-specific, never committed); else a default under the repo's `data/`.

    PORTIA_DATASET     the benchmark's questions and answers (final_all.jsonl)
    PORTIA_SHARDS      the benchmark's contests split into shards (final_all_shards/<shard>.jsonl)
    PORTIA_VIDEOS      the video database (database_v3.json, the videos and their transcripts)
    PORTIA_INDEX       the segment search index (Qwen3-VL-Embedding-8B vectors, built before the hackathon)
    PORTIA_EXTRA_ENV   an extra KEY=VALUE file for OpenRouter keys (optional; research baselines only)
    PORTIA_NODE        node, the JavaScript runtime yt-dlp uses (optional; YouTube links are off by default)
    PORTIA_YT_COOKIES  a cookies file for yt-dlp (optional; YouTube links are off by default)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOCAL = ROOT / "paths.local.json"
_CFG = json.loads(_LOCAL.read_text(encoding="utf-8")) if _LOCAL.exists() else {}


def get(key: str, default: str | None) -> Path | None:
    v = os.environ.get(key) or _CFG.get(key)
    if v:
        return Path(v)
    return ROOT / default if default else None


DATASET = get("PORTIA_DATASET", "data/benchmark/final_all.jsonl")
SHARDS = get("PORTIA_SHARDS", "data/final_all_shards")
VIDEOS = get("PORTIA_VIDEOS", "data/videos_list")
INDEX = get("PORTIA_INDEX", "data/index/Qwen--Qwen3-VL-Embedding-8B")
EXTRA_ENV = get("PORTIA_EXTRA_ENV", None)
NODE = get("PORTIA_NODE", None)
YT_COOKIES = get("PORTIA_YT_COOKIES", None)
