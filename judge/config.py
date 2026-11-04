"""portia/judge/config.py: Portia's settings, one YAML file per topic in configs/ (models, budgets, agent, product, proof,
queue). Environment variables still override the keys whose comments name one; the code reads those."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    return yaml.safe_load((CONFIGS / f"{name}.yaml").read_text(encoding="utf-8")) or {}
