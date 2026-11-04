#!/usr/bin/env python3
"""portia/analysis/turns_report.py: idea I (plan 005): the 30-turn agent against the standard 8-turn agent.

    python analysis/turns_report.py          # prints markdown; also writes runs/idea_i_report.md

Per development shard (3, 4):
  * single agents: each finished 30-turn seed (mg_v4t_t30[_rN]) against the 11 finished 8-turn seeds (mg_v4t[_rN]);
  * a vote of 3: the mean accuracy over every 3-seed combination of each pool (a tie or no verdict counts as wrong,
    as in plan 004's vote).
Runs without summary.json are still running; they are listed but left out of the numbers.
"""
from __future__ import annotations

import itertools
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARDS = {"s3": 94, "s4": 126}


def runs(prefix: str, shard: str) -> list[str]:
    names = [f"{prefix}_{shard}"] + [f"{prefix}_r{i}_{shard}" for i in range(1, 30)]
    return [n for n in names if (ROOT / "runs" / n / "results.jsonl").exists()]


def rows(name: str) -> dict:
    out = {}
    for line in (ROOT / "runs" / name / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["key"]] = r
    return out


def majority(vs: list) -> str | None:
    c = Counter(v for v in vs if v in ("A", "B")).most_common()
    return c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else None


def vote3(pool: list[dict], keys: list[str]) -> float:
    accs = []
    for trio in itertools.combinations(pool, 3):
        ok = sum(majority([t[k].get("verdict") for t in trio]) == trio[0][k]["good_side"] for k in keys)
        accs.append(100 * ok / len(keys))
    return statistics.mean(accs) if accs else float("nan")


def main():
    out = ["# Idea I: the 30-turn agent against the standard 8-turn agent (development shards 3-4)", "",
           "Single agent = accuracy of one seed; the 8-turn pool is the 11 standard tuned-v4 seeds. Vote of 3 = mean over "
           "every 3-seed combination within a pool. Gain = 30-turn mean minus 8-turn mean; SE from the two pools' spreads.",
           "", "| Shard | 30-turn seeds | 30-turn mean | 8-turn mean ± sd (seeds) | Gain (SE) | Vote of 3: 30-turn / 8-turn |",
           "|---|---|---|---|---|---|"]
    pend = []
    for s, n in SHARDS.items():
        t30 = [r for r in runs("mg_v4t_t30", s) if (ROOT / "runs" / r / "summary.json").exists()]
        pend += [r for r in runs("mg_v4t_t30", s) if r not in t30]
        std = [r for r in runs("mg_v4t", s) if (ROOT / "runs" / r / "summary.json").exists()]
        R30, RST = [rows(r) for r in t30], [rows(r) for r in std]
        keys = sorted(set.intersection(*(set(x) for x in R30 + RST)))
        a30 = [100 * sum(x[k]["correct"] is True for k in keys) / len(keys) for x in R30]
        ast = [100 * sum(x[k]["correct"] is True for k in keys) / len(keys) for x in RST]
        se = (statistics.variance(a30) / len(a30) + statistics.variance(ast) / len(ast)) ** 0.5 if len(a30) > 1 else float("nan")
        out.append(f"| {s[1]} ({len(keys)} contests) | {', '.join(f'{a:.1f}' for a in a30)} | {statistics.mean(a30):.1f} | "
                   f"{statistics.mean(ast):.1f} ± {statistics.stdev(ast):.1f} ({len(ast)}) | "
                   f"**{statistics.mean(a30) - statistics.mean(ast):+.1f}** ({se:.1f}) | "
                   f"{vote3(R30, keys):.1f} / {vote3(RST, keys):.1f} |")
    if pend:
        out += ["", "Still running (not counted): " + ", ".join(f"{p} ({len(rows(p))}/{SHARDS[p[-2:]]})" for p in pend) + "."]
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "idea_i_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
