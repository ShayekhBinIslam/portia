#!/usr/bin/env python3
"""portia/judge/compare.py: a Portia run vs every leaderboard judge (and other Portia runs), SAME contests.

    python -m judge.compare --name nemotron_s1 [--with nemotron_static_s1] [--shard shard1_5pct]

Reference verdicts: data/reference/leaderboard_<shard>.json (extracted read-only from the alpha pod's main
retrieved arm by data/reference/extract_lb_shard.py). Scoring follows the leaderboard: a no-verdict counts
as half a point. Contests are paired, so each row carries an exact McNemar p-value against the main run
(b = main right & other wrong, c = the reverse; no-verdicts count as wrong for the pairing).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def score(v: dict, keys: list[str]) -> tuple[float, float | None, int]:
    """(leaderboard-style accuracy %, balanced % over decided, n decided). v: key -> (verdict, good_side)."""
    pts, dec = 0.0, []
    for k in keys:
        verdict, good = v[k]
        if verdict in ("A", "B"):
            pts += verdict == good
            dec.append((good, verdict == good))
        else:
            pts += 0.5
    a = [ok for g, ok in dec if g == "A"]
    b = [ok for g, ok in dec if g == "B"]
    bal = round(50 * (sum(a) / len(a) + sum(b) / len(b)), 1) if a and b else None
    return 100 * pts / max(len(keys), 1), bal, len(dec)


def load_run(name: str, shard: str) -> dict:
    rows = [json.loads(l) for l in (ROOT / "runs" / name / "results.jsonl").read_text().splitlines() if l.strip()]
    return {r["key"]: (r.get("verdict"), r["good_side"]) for r in rows if r["shard"] == shard}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--with", dest="others", action="append", default=[], help="other Portia runs to include")
    ap.add_argument("--shard", default="shard1_5pct")
    ap.add_argument("--subset", metavar="RUN:HOW", help="only contests where RUN ended as HOW (e.g. nemotron_s2:forced)")
    a = ap.parse_args()
    main_v = load_run(a.name, a.shard)
    keys = sorted(main_v)
    if a.subset:
        run, how = a.subset.split(":")
        hows = {r["key"]: r["how"] for r in map(json.loads, (ROOT / "runs" / run / "results.jsonl").read_text().splitlines()) if r}
        keys = [k for k in keys if hows.get(k) == how]
    right = lambda v, k: v[k][0] == v[k][1]                     # noqa: E731
    main_v = {k: main_v[k] for k in keys}
    entries = [(f"portia: {a.name}", main_v)]
    entries += [(f"portia: {o}", load_run(o, a.shard)) for o in a.others]
    ref = json.loads((ROOT / "data" / "reference" / f"leaderboard_{a.shard}.json").read_text())
    for judge, d in ref.items():
        entries.append((judge, {k: (v[0], "A" if v[1] else "B") for k, v in d["verdicts"].items()}))
    rows = []
    for name, v in entries:
        ks = [k for k in keys if k in v]
        acc, bal, dec = score(v, ks)
        if name == f"portia: {a.name}":
            rows.append((name, acc, bal, len(ks), dec, None, None))
            continue
        b = sum(1 for k in ks if right(main_v, k) and not right(v, k))
        c = sum(1 for k in ks if right(v, k) and not right(main_v, k))
        rows.append((name, acc, bal, len(ks), dec, (b, c), mcnemar(b, c)))
    rows.sort(key=lambda r: -r[1])
    print(f"{a.shard}: {len(keys)} contests in {a.name}" + (f" (subset {a.subset})" if a.subset else "") + "\n")
    print(f"{'judge':44s} {'acc':>7s} {'balanced':>9s} {'n':>4s} {'decided':>8s}   vs main: b / c   McNemar p")
    for name, acc, bal, n, dec, bc, p in rows:
        print(f"{name[:44]:44s} {acc:6.1f}% {bal if bal is not None else '-':>9} {n:4d} {dec:8d}   "
              + (f"{bc[0]:>5d} / {bc[1]:<5d}  {p:.3f}" if bc else "      (main)"))


if __name__ == "__main__":
    main()
