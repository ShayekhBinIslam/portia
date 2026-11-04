#!/usr/bin/env python3
"""portia/analysis/local_compare.py: the local-judge arms side by side on the same contests (offline).

    python analysis/local_compare.py [--prefix q38] [--arms static v1 v2 v3] [--shards s1 s2 s3]

For each arm vs the same model's static arm: paired accuracy (a no-verdict counts as wrong), gain with a 95% CI,
exact McNemar; how runs ended; tool use; whether the agent viewed a ground-truth evidence segment. Nemotron's
tools-v1 and static runs on the same contests are shown for reference. Writes runs/<prefix>_DEV_RESULTS.json.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from judge import corpus                                                   # noqa: E402
from judge.contests import DATASET, load_contests                          # noqa: E402
from tool_failures import evidence_handles, trajectory_coverage            # noqa: E402

SHARD = {"s1": "shard1_5pct", "s2": "shard2_10pct", "s3": "shard3_15pct", "s4": "shard4_20pct", "s5": "shard5_25pct",
         "s6": "shard6_25pct"}


def mcnemar(b: int, c: int) -> float:
    n = b + c
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.0


def load(run: str) -> dict:
    p = ROOT / "runs" / run / "results.jsonl"
    return {r["key"]: r for r in map(json.loads, open(p))} if p.exists() else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="q38")
    ap.add_argument("--arms", nargs="+", default=["v1", "v2", "v3"])
    ap.add_argument("--shards", nargs="+", default=["s1", "s2", "s3"])
    a = ap.parse_args()
    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    out = {"prefix": a.prefix, "arms": {}}
    static = {}
    for s in a.shards:
        static.update(load(f"{a.prefix}_static_{s}"))
    nem = {}
    for s in a.shards:
        for k, r in load(f"nemotron_{s}").items():
            nem.setdefault(k, {})["v1"] = r
        for k, r in load(f"nemotron_static_{s}").items():
            nem.setdefault(k, {})["static"] = r
    contests = {c.key: c for c in load_contests([SHARD[s] for s in a.shards])}
    corpus.register(sorted({p for c in contests.values() for p in corpus.domain_playlists(c.domain)}))
    ok = lambda r: bool(r and r.get("correct"))                             # noqa: E731
    print(f"static ({a.prefix}): {len(static)} contests · {sum(ok(r) for r in static.values())} right "
          f"({100 * sum(ok(r) for r in static.values()) / max(len(static), 1):.1f}%)")
    print(f"{'arm':6s} {'n':>4s} {'tools':>7s} {'static':>7s} {'gain':>6s} {'95% CI':>15s} {'b/c':>7s} {'p':>6s}  "
          f"{'forced':>6s} {'steps':>5s} {'imgs':>5s} {'viewed ev':>9s}  tool calls/contest")
    for arm in a.arms:
        rows = {}
        for s in a.shards:
            run = f"{a.prefix}_{arm}_{s}"
            for k, r in load(run).items():
                tf = ROOT / "runs" / run / "trajectories"
                rows[k] = (r, tf)
        keys = [k for k in rows if k in static]
        if not keys:
            continue
        b = sum(1 for k in keys if ok(rows[k][0]) and not ok(static[k]))
        c = sum(1 for k in keys if ok(static[k]) and not ok(rows[k][0]))
        n, t, st = len(keys), sum(ok(rows[k][0]) for k in keys), sum(ok(static[k]) for k in keys)
        d = (b - c) / n
        se = math.sqrt(max((b + c) - (b - c) ** 2 / n, 0)) / n
        forced = sum(rows[k][0].get("how") == "forced" for k in keys)
        calls = collections.Counter(x["tool"] for k in keys for x in rows[k][0].get("tool_calls", []))
        viewed = 0
        for k in keys:
            r, tf = rows[k]
            c_ = contests.get(k)
            if not c_:
                continue
            pos = next((i for i, cc in enumerate(load_contests([r["shard"]])) if cc.key == k), None)
            f = tf / f"{r['shard']}_{pos:03d}.json" if pos is not None else None
            if f and f.exists():
                ev = {h for h in evidence_handles(recs[c_.qid]) if corpus.segment(h)}
                cov = trajectory_coverage(json.loads(f.read_text()), ev)
                viewed += cov["viewed_hit"] or (arm == "v3" and cov["initial_hit"])
        res = {"n": n, "tools": t, "static": st, "tools_pct": round(100 * t / n, 1), "static_pct": round(100 * st / n, 1),
               "gain": round(100 * d, 1), "ci": [round(100 * (d - 1.96 * se), 1), round(100 * (d + 1.96 * se), 1)],
               "tools_only": b, "static_only": c, "p": round(mcnemar(b, c), 3), "forced": forced,
               "mean_steps": round(sum(rows[k][0].get("steps") or 0 for k in keys) / n, 2),
               "mean_images": round(sum(rows[k][0].get("images_viewed") or 0 for k in keys) / n, 1),
               "viewed_evidence": viewed, "tool_calls_per_contest": {x: round(v / n, 2) for x, v in calls.most_common()}}
        nk = [k for k in keys if k in nem and "v1" in nem[k] and "static" in nem[k]]
        if nk:
            res["nemotron_same_contests"] = {"n": len(nk), "v1_pct": round(100 * sum(ok(nem[k]["v1"]) for k in nk) / len(nk), 1),
                                             "static_pct": round(100 * sum(ok(nem[k]["static"]) for k in nk) / len(nk), 1)}
        out["arms"][arm] = res
        print(f"{arm:6s} {n:4d} {res['tools_pct']:6.1f}% {res['static_pct']:6.1f}% {res['gain']:+6.1f} "
              f"{'[' + str(res['ci'][0]) + ', ' + str(res['ci'][1]) + ']':>15s} {f'{b}/{c}':>7s} {res['p']:6.3f}  "
              f"{forced:6d} {res['mean_steps']:5.1f} {res['mean_images']:5.1f} {viewed:4d}/{n:<4d}  "
              + ", ".join(f"{x} {v}" for x, v in list(res["tool_calls_per_contest"].items())[:6]))
        if nk:
            print(f"{'':6s} Nemotron on the same {len(nk)}: tools v1 {res['nemotron_same_contests']['v1_pct']}% · static {res['nemotron_same_contests']['static_pct']}%")
    (ROOT / "runs" / f"{a.prefix}_DEV_RESULTS.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
