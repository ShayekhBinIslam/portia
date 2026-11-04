#!/usr/bin/env python3
"""portia/analysis/heldout_021.py: audit 021's pre-registered held-out check (shards 5-6, 316 contests).

On the held-out investigator triple (tuned v4, seeds 0-2: mg_v4t, mg_v4t_r1, mg_v4t_r2), with the evidence-only Muse
Glimmer adjudicator on the splits (mg_adjev_ho, seed salt 0), exactly as on the development triples:
  1. accuracy of the majority vote and of Portia fully local, with 95% bootstrap intervals over contests;
  2. the same on held-out contests whose question does not occur in the development shards 3-4 (question leakage);
  3. the product's trust tiers (the development path table, the words-on-screen and position cap): each tier's
     held-out share and accuracy next to its development accuracy.

    python analysis/heldout_021.py        # prints markdown; writes runs/heldout_021.json
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "product"))
from judge import contests as C  # noqa: E402
import engine as E               # noqa: E402

INV, ADJ, SH = ["mg_v4t", "mg_v4t_r1", "mg_v4t_r2"], "mg_adjev_ho", ("s5", "s6")
DEV = {"vote": 74.0, "local": 75.2}                     # development figures (How page, 1,100 runs)


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
    inv, adj = [rows(r) for r in INV], rows(ADJ)
    dev_q = {c.question.strip() for c in C.load_contests(["shard3_15pct", "shard4_20pct"])}
    ho = {c.key: c for c in C.load_contests(["shard5_25pct", "shard6_25pct"])}
    T = json.loads((ROOT / "runs" / "trust_tiers.json").read_text(encoding="utf-8"))["glimmer"]
    dev_pct = {p["path"]: p["pct"] for p in T["paths"]}
    levels = {"accept": 85.0, "spot": 75.0}
    recs = []
    for k, c in ho.items():
        if not all(k in x for x in inv) or k not in adj:
            continue
        v = [x[k].get("verdict") for x in inv]
        forced = sum(x[k].get("how") == "forced" for x in inv)
        good = c.good_side
        agreed = len(set(v)) == 1 and v[0] in ("A", "B")
        vote = adj[k].get("vote") or max(("A", "B"), key=v.count)
        path = ("agreed_settled" if forced <= 1 else "agreed_turnlimit") if agreed else "split_glimmer"
        portia = v[0] if agreed else adj[k].get("verdict")
        pct = dev_pct[path]
        level = "accept" if pct >= levels["accept"] else "spot" if pct >= levels["spot"] else "review"
        kind = E.dispute_kind(c.answer_a, c.answer_b)
        if kind in ("text", "position") and level == "accept":
            level = "spot"
        recs.append({"key": k, "vote_ok": vote == good, "portia_ok": portia == good, "path": path, "level": level,
                     "kind": kind, "clean": c.question.strip() not in dev_q})
    n = len(recs)
    out = {"n": n, "dev": DEV, "groups": {}, "paths": {}, "tiers": {}}
    lines = [f"# Held-out check (audit 021): {n} contests, shards 5-6, the tuned v4 triple, Glimmer adjudicator", "",
             "| Contests | n | Majority vote | Portia fully local |", "|---|---|---|---|"]
    for name, sel in (("all held-out", recs), ("question not in shards 3-4", [r for r in recs if r["clean"]])):
        vo, po = boot([float(r["vote_ok"]) for r in sel]), boot([float(r["portia_ok"]) for r in sel], seed=1)
        out["groups"][name] = {"n": len(sel), "vote": [round(x, 1) for x in vo], "portia": [round(x, 1) for x in po]}
        lines.append(f"| {name} | {len(sel)} | {vo[0]:.1f}% [{vo[1]:.1f}, {vo[2]:.1f}] | {po[0]:.1f}% [{po[1]:.1f}, {po[2]:.1f}] |")
    lines.append(f"| development (for reference) | 1,100 runs | {DEV['vote']}% | {DEV['local']}% |")
    lines += ["", "| Path | Held-out share | Held-out right | Development right |", "|---|---|---|---|"]
    by = defaultdict(list)
    for r in recs:
        by[r["path"]].append(r["portia_ok"])
    for p in ("agreed_settled", "agreed_turnlimit", "split_glimmer"):
        xs = by.get(p, [])
        if xs:
            out["paths"][p] = {"share": round(100 * len(xs) / n, 1), "pct": round(100 * sum(xs) / len(xs), 1), "n": len(xs),
                               "dev_pct": dev_pct[p]}
            lines.append(f"| {p} | {100 * len(xs) / n:.1f}% ({len(xs)}) | {100 * sum(xs) / len(xs):.1f}% | {dev_pct[p]}% |")
    lines += ["", "| Trust tier (as the product assigns it) | Held-out share | Held-out right |", "|---|---|---|"]
    tb = defaultdict(list)
    for r in recs:
        tb[r["level"]].append(r["portia_ok"])
    for lv in ("accept", "spot", "review"):
        xs = tb.get(lv, [])
        if xs:
            out["tiers"][lv] = {"share": round(100 * len(xs) / n, 1), "pct": round(100 * sum(xs) / len(xs), 1), "n": len(xs)}
            lines.append(f"| {lv} | {100 * len(xs) / n:.1f}% ({len(xs)}) | {100 * sum(xs) / len(xs):.1f}% |")
    text = "\n".join(lines)
    print(text)
    (ROOT / "runs" / "heldout_021.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
