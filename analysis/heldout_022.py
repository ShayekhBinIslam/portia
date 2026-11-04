#!/usr/bin/env python3
"""portia/analysis/heldout_022.py: audit 022's pre-registered held-out check of the Muse Spark 1.3 modes (shards 5-6).

The investigator triple and the Glimmer jury are audit 021's (mg_v4t, mg_v4t_r1, mg_v4t_r2; mg_adjev_ho). Muse Spark 1.3
ruled on every held-out contest once, with the development settings (mg_adjs13all_ho: evidence-only, --all). From that
one run:
  1. check-all: Spark 1.3's ruling on every contest;
  2. splits only: Spark 1.3's ruling where the investigators split, their unanimous verdict elsewhere;
next to the majority vote and Portia on Muse Glimmer alone, with 95% bootstrap intervals over contests (as audit 021),
on all contests and on those whose question never appears in development; and on unanimous contests, how many wrong
verdicts Spark 1.3 fixed and how many right ones it broke.

    python analysis/heldout_022.py        # prints markdown; writes runs/heldout_022.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge import contests as C  # noqa: E402

INV, GLIMMER, SPARK, SH = ["mg_v4t", "mg_v4t_r1", "mg_v4t_r2"], "mg_adjev_ho", "mg_adjs13all_ho", ("s5", "s6")
DEV = {"vote": 74.0, "glimmer": 75.2, "spark13": 78.8, "spark13all": 82.0, "fixed": 59, "broke": 29}   # README, How page


def rows(run: str) -> dict:
    out = {}
    for s in SH:
        p = ROOT / "runs" / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            out.update({json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()})
    return out


def boot(xs: list[float], n: int = 4000, seed: int = 0) -> tuple[float, float, float]:
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n))
    return 100 * sum(xs) / len(xs), 100 * means[int(0.025 * n)], 100 * means[int(0.975 * n) - 1]


def main():
    inv, glim, spark = [rows(r) for r in INV], rows(GLIMMER), rows(SPARK)
    dev_q = {c.question.strip() for c in C.load_contests(["shard3_15pct", "shard4_20pct"])}
    ho = {c.key: c for c in C.load_contests(["shard5_25pct", "shard6_25pct"])}
    recs = []
    for k, c in ho.items():
        if not all(k in x for x in inv) or k not in glim or k not in spark or spark[k].get("verdict") not in ("A", "B"):
            continue
        v = [x[k].get("verdict") for x in inv]
        good = c.good_side
        agreed = len(set(v)) == 1 and v[0] in ("A", "B")
        vote = glim[k].get("vote") or max(("A", "B"), key=v.count)
        s13 = spark[k]["verdict"]
        recs.append({"key": k, "clean": c.question.strip() not in dev_q, "agreed": agreed, "agreed_ok": agreed and v[0] == good,
                     "vote_ok": vote == good, "glimmer_ok": (v[0] if agreed else glim[k].get("verdict")) == good,
                     "spark13_ok": (v[0] if agreed else s13) == good, "spark13all_ok": s13 == good, "s13_ok": s13 == good})
    out = {"n": len(recs), "dev": DEV, "groups": {}}
    lines = [f"# Held-out check (audit 022): Muse Spark 1.3 on shards 5-6, {len(recs)} contests", "",
             "| Contests | n | Majority vote | Portia on Muse Glimmer alone | Spark 1.3 on splits | Spark 1.3 checking every verdict |",
             "|---|---|---|---|---|---|"]
    for name, sel in (("all held-out", recs), ("question not in shards 3-4", [r for r in recs if r["clean"]])):
        cells, g = [], {"n": len(sel)}
        for i, col in enumerate(("vote_ok", "glimmer_ok", "spark13_ok", "spark13all_ok")):
            m, lo, hi = boot([float(r[col]) for r in sel], seed=i)
            g[col[:-3]] = [round(m, 1), round(lo, 1), round(hi, 1)]
            cells.append(f"{m:.1f}% [{lo:.1f}, {hi:.1f}]")
        out["groups"][name] = g
        lines.append(f"| {name} | {len(sel)} | " + " | ".join(cells) + " |")
    lines.append(f"| development (for reference) | | {DEV['vote']}% | {DEV['glimmer']}% | {DEV['spark13']}% | {DEV['spark13all']}% |")
    un = [r for r in recs if r["agreed"]]
    fixed = sum(1 for r in un if not r["agreed_ok"] and r["s13_ok"])
    broke = sum(1 for r in un if r["agreed_ok"] and not r["s13_ok"])
    out["unanimous"] = {"n": len(un), "wrong": sum(1 for r in un if not r["agreed_ok"]), "fixed": fixed, "broke": broke}
    lines += ["", f"Unanimous contests: {len(un)}, of which {out['unanimous']['wrong']} wrong. Spark 1.3 fixed {fixed} and broke "
              f"{broke} (development: fixed {DEV['fixed']}, broke {DEV['broke']} over 880 runs)."]
    print("\n".join(lines))
    (ROOT / "runs" / "heldout_022.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
