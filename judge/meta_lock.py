"""portia/judge/meta_lock.py: the Meta hackathon API credits stay LOCKED until the user unlocks them.

User: "we received 250 USD api credits, but don't use it, we will use later. keep both those
meta_hack.env keys locked". While meta_hackathon/.meta_locked exists, no client may target a Meta-hosted API or
load meta_hack.env; the judge iterates on the local Muse Glimmer (box RTX) instead. Only the user deletes the lock.

User: "let's unlock baseten key only (keep meta api locked)". The lock file now carries the line
"UNLOCKED: META_BASETEN_KEY": baseten_key() returns that one variable (never any other) while the line is there.
META_DEV_KEY and Meta-hosted endpoints stay locked.
User: "it looks cheap, could we smoke and check cost in meta api" (muse-spark-1.3-contributor), then
"please unlock cap $2". The lock file now also carries "UNLOCKED: META_DEV_KEY for model muse-spark-1.3-contributor
only": dev_key() returns that one variable, and check() lets META_API_URL through, while the line is there. Every
other Meta host stays refused. Spend is logged in runs/meta_spend.jsonl and capped at $2 (META_DEV_CAP_USD).
"""
from __future__ import annotations

import os
from pathlib import Path

from judge.config import load as _config

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "meta_hackathon" / ".meta_locked"
# hosts of Meta's model API (and anything else that would spend the credits)
META_HOSTS = ("llama.com", "llama-api", "meta.ai", "meta.com", "facebook.com", "fbcdn")
ENV = ROOT / "meta_hackathon" / "meta_hack.env"
_M, _B = _config("models"), _config("budgets")                 # configs/models.yaml, configs/budgets.yaml
BASETEN_URL = _M["muse_spark_open"]["api_url"]
BASETEN_MODEL = _M["muse_spark_open"]["model"]   # the only model the hackathon key works with
META_API_URL = _M["muse_spark_13"]["api_url"]                   # the Meta Model API (OpenAI-compatible)
META_DEV_MODEL = os.environ.get("PORTIA_SPARK13_MODEL", _M["muse_spark_13"]["model"])   # the unlock's model
# the user's total cap: first $2, then $4, now $30 for the hackathon + $75 for the PlaylistEval re-judge
META_DEV_CAP_USD = float(os.environ.get("PORTIA_META_CAP_USD", _B["meta_api"]["total_cap_usd"]))
HACKATHON_CAP_USD = float(_B["meta_api"]["hackathon_cap_usd"])  # every tag except PLAYLISTEVAL_TAG
PLAYLISTEVAL_TAG, PLAYLISTEVAL_CAP_USD = _B["meta_api"]["playlisteval"]["tag"], float(_B["meta_api"]["playlisteval"]["cap_usd"])
DEV_UNLOCK = "UNLOCKED: META_DEV_KEY for model muse-spark-1.3-contributor only"


def check(target: str) -> None:
    """Raise if `target` (a base URL or a file path) would use the locked Meta credits."""
    if not LOCK.exists():
        return
    t = str(target).lower()
    if t.startswith(META_API_URL) and DEV_UNLOCK in LOCK.read_text(encoding="utf-8"):
        return                                          # the unlock: the Meta Model API, for the contributor model
    if "meta_hack" in t or any(h in t for h in META_HOSTS):
        raise SystemExit(f"Meta API credits are LOCKED by the user ({LOCK.relative_to(ROOT)}): refusing {target!r}. "
                         "Use the local Muse Glimmer server instead.")


def baseten_key() -> str:
    """The Baseten hackathon key (META_BASETEN_KEY), and nothing else from meta_hack.env, if the user has unlocked it.
    The value is returned to the caller only: never printed, logged or written anywhere."""
    if LOCK.exists() and "UNLOCKED: META_BASETEN_KEY" not in LOCK.read_text(encoding="utf-8"):
        raise SystemExit(f"META_BASETEN_KEY is locked ({LOCK.relative_to(ROOT)}); the user has not unlocked it.")
    return _key(("BASETEN_API_KEY", "META_BASETEN_KEY"))


def _key(names: tuple[str, ...]) -> str:
    """The first of `names` found in the environment, then the repo's .env (see .env.example), then meta_hack.env.
    Returned to the caller only: never printed, logged or written anywhere."""
    for n in names:
        if os.environ.get(n, "").strip():
            return os.environ[n].strip()
    for f in (ROOT / ".env", ENV):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("export "):
                s = s[len("export "):].strip()
            for n in names:
                if s.startswith(f"{n}="):
                    v = s.split("=", 1)[1].strip().strip("'").strip('"')
                    if v:
                        return v
    raise SystemExit(f"{names[0]} not set: put it in .env (see .env.example) or the environment")


def has_key(names: tuple[str, ...]) -> bool:
    """Whether one of `names` is set somewhere _key() looks, without raising (for the app's availability flags)."""
    try:
        _key(names)
        return True
    except SystemExit:
        return False


def dev_key() -> str:
    """META_DEV_KEY, for muse-spark-1.3-contributor only, if the user has unlocked it (never printed or logged)."""
    if LOCK.exists() and DEV_UNLOCK not in LOCK.read_text(encoding="utf-8"):
        raise SystemExit(f"META_DEV_KEY is locked ({LOCK.relative_to(ROOT)}); the user has not unlocked it.")
    return _key(("META_MODEL_API_KEY", "META_DEV_KEY"))

