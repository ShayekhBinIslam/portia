#!/usr/bin/env python3
"""portia/analysis/plan019_e1.py: plan 019, experiment E1: does the wider-looking Glimmer adjudicator beat the standard
one? Paired per triple: mg_adjwide_<triple> against the standard mg_adjev<triple> (same investigators, seed salt 0,
same splits). Explore and confirm halves are the triples in seed order (1st, 3rd, ... / 2nd, 4th, ...), as fixed in
audits/019_agent_24h.md before any E1 result was seen.

    python analysis/plan019_e1.py          # prints markdown; writes runs/plan019_e1.md
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
ORDER = ["_t012", "_t234", "_t345", "_t567", "_t8910", "_t111213", "_t141516", "_t171819", "_t202122", "_t232425",
         "_t262728", "_t293031", "_t323334", "_t353637"]


def load(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = RUNS / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    out[(s, r["key"])] = r
    return out


def finished(run: str) -> bool:
    return all((RUNS / f"{run}_{s}" / "summary.json").exists() for s in ("s3", "s4"))


def main():
    # the explore/confirm halves follow local_rules.py's seed order of the standard adjudications
    std_tags = [t for t in ORDER if finished("mg_adjev" + ("" if t == "_t012" else t))]
    halves = {t: ("explore" if i % 2 == 0 else "confirm") for i, t in enumerate(std_tags)}
    rows = []
    for t in std_tags:
        if not finished(f"mg_adjwide{t}"):
            continue
        std, wide = load("mg_adjev" + ("" if t == "_t012" else t)), load(f"mg_adjwide{t}")
        keys = [k for k in std if k in wide]
        good = {k: std[k]["good_side"] for k in keys}
        acc = lambda r: 100 * sum(r[k]["verdict"] == good[k] for k in keys) / len(keys)      # noqa: E731
        split = [k for k in keys if std[k]["contested"]]
        sacc = lambda r: 100 * sum(r[k]["verdict"] == good[k] for k in split) / max(1, len(split))    # noqa: E731
        fixed = sum(std[k]["verdict"] != good[k] and wide[k]["verdict"] == good[k] for k in split)
        broke = sum(std[k]["verdict"] == good[k] and wide[k]["verdict"] != good[k] for k in split)
        vote = 100 * sum(std[k]["vote"] == good[k] for k in keys) / len(keys)
        rows.append({"t": t[1:], "half": halves[t], "n": len(keys), "splits": len(split), "vote": vote, "std": acc(std),
                     "wide": acc(wide), "std_s": sacc(std), "wide_s": sacc(wide), "fixed": fixed, "broke": broke})
    lines = ["# Plan 019, E1: the wider-looking adjudicator against the standard one (paired per triple)", "",
             "| Triple | Half | Contests | Splits | Vote | Standard | Wider | On splits: standard / wider | Wider fixed / broke |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['t']} | {r['half']} | {r['n']} | {r['splits']} | {r['vote']:.1f} | {r['std']:.1f} | {r['wide']:.1f} | "
                     f"{r['std_s']:.1f} / {r['wide_s']:.1f} | {r['fixed']} / {r['broke']} |")
    lines.append("")
    for half in ("explore", "confirm", "all"):
        use = [r for r in rows if half == "all" or r["half"] == half]
        if not use:
            continue
        gains = [r["wide"] - r["std"] for r in use]
        up, down = sum(g > 0 for g in gains), sum(g < 0 for g in gains)
        fx, br = sum(r["fixed"] for r in use), sum(r["broke"] for r in use)
        lines.append(f"- **{half}** ({len(use)} triples): mean gain of the wider adjudicator over the standard "
                     f"{statistics.mean(gains):+.2f} points (sd {statistics.pstdev(gains):.2f}); triples up / down {up} / {down}; "
                     f"on splits it fixed {fx} and broke {br}.")
    ex = [r["wide"] - r["std"] for r in rows if r["half"] == "explore"]
    co = [r["wide"] - r["std"] for r in rows if r["half"] == "confirm"]
    if len(ex) == 7 and len(co) == 7:
        ok1 = statistics.mean(ex) > 0.5 and sum(g > 0 for g in ex) >= 5
        ok2 = statistics.mean(co) > 0 and sum(g > 0 for g in co) > sum(g < 0 for g in co)
        lines += ["", f"Pre-registered rule: explore {'PASSES' if ok1 else 'fails'}, confirm {'PASSES' if ok2 else 'fails'} -> "
                      f"**{'ADOPT' if ok1 and ok2 else 'do not adopt'}** the wider adjudicator for Portia's local mode."]
    text = "\n".join(lines)
    print(text)
    (RUNS / "plan019_e1.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
