"""portia/judge/contests.py: the 630 contests of the 3_inference FINAL campaign, rebuilt exactly.

Same contest set and the same seeded A/B sides as every judge on the benchmark's leaderboard, so a
tool-using judge's score sits directly beside theirs:
  * shards: data/final_all_shards/shard{1..6}_*.jsonl (md5-identical copies of the alpha pod's
    runs_eval/pair_sampler/final_all/selections/splits/), keyed (qid, pair, occurrence);
  * answer texts rebuilt from the dataset (1_lib/dataset_sampled_each50/final_all.jsonl) through the
    campaign's own normalisation, never trusted from the shard file;
  * A/B side: the campaign's sha256 coin flip over "<seed>|<qid>|<pair>|<occurrence>" (seed 0).
The functions below are VERBATIM ports of 3_inference (pod) schemas/mcq.py:norm_block/strip_citations,
evaluator/reward_eval.py:_candidates and evaluator/order.py:better_first/seed_key.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from judge.paths import DATASET, SHARDS  # noqa: E402  (the benchmark: env, paths.local.json, or data/)
SHARD_NAMES = ["shard1_5pct", "shard2_10pct", "shard3_15pct", "shard4_20pct", "shard5_25pct", "shard6_25pct"]
SEED = 0
CAND_RANK = {"gold": 5, "rating_4": 4, "rating_3": 3, "rating_2": 2, "rating_1": 1}
_CITE_RE = re.compile(r"\s*\(\s*\d+\s*@[^)]*\)")


def norm_block(s: str) -> str:
    lines = [" ".join(ln.split()) for ln in (s or "").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def strip_citations(text: str) -> str:
    return _CITE_RE.sub("", text or "").strip()


def candidates(rec: dict) -> dict:
    """{name: (rank, text)} for gold + ratings 4..1, citation-stripped (campaign _candidates)."""
    out = {}
    g = norm_block(strip_citations(rec.get("reference_answer") or rec.get("answer")))
    if g:
        out["gold"] = (CAND_RANK["gold"], g)
    for rt in (4, 3, 2, 1):
        t = norm_block(strip_citations((rec.get(f"rating_{rt}") or {}).get("response", "")))
        if t:
            out[f"rating_{rt}"] = (rt, t)
    return out


def seed_key(seed, cid: str, pair: str, occurrence: int = 0) -> str:
    return f"{seed}|{cid}|{pair}|{occurrence}"


def better_first(key: str) -> bool:
    return not (hashlib.sha256(key.encode("utf-8")).digest()[0] & 1)


@dataclass
class Contest:
    qid: str
    pair: str
    occurrence: int
    shard: str
    domain: str
    playlist: str
    gap: int
    question: str
    answer_a: str
    answer_b: str
    good_side: str                 # "A" or "B": where the better answer was placed
    rec: dict = field(repr=False, default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.qid}|{self.pair}|{self.occurrence}"


def load_records() -> dict:
    by_id = {}
    for i, l in enumerate(DATASET.read_text(encoding="utf-8").splitlines()):
        if l.strip():
            r = json.loads(l)
            by_id[r.get("id") or r.get("gen_key") or f"sample_{i}"] = r
    return by_id


def load_contests(shards: list[str] | None = None) -> list[Contest]:
    recs = load_records()
    out = []
    for sh in shards or SHARD_NAMES:
        for line in (SHARDS / f"{sh}.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rec = recs[row["qid"]]
            cands = candidates(rec)
            better, worse = row["pair"].split("_vs_")
            hi, lo = cands[better][1], cands[worse][1]
            occ = int(row.get("occurrence", 0) or 0)
            first = better_first(seed_key(SEED, row["qid"], row["pair"], occ))
            out.append(Contest(qid=row["qid"], pair=row["pair"], occurrence=occ, shard=sh,
                               domain=rec.get("domain", ""), playlist=rec.get("playlist", ""),
                               gap=int(row.get("gap", 0) or 0), question=(rec.get("question") or "").strip(),
                               answer_a=hi if first else lo, answer_b=lo if first else hi,
                               good_side="A" if first else "B", rec=rec))
    return out
