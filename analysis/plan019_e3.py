#!/usr/bin/env python3
"""portia/analysis/plan019_e3.py: plan 019, experiment E3: does a procedure for count and on-screen-text disputes
(judge/adjudicate.py --kind-notes) help the Glimmer adjudicator on those splits? Paired per triple against the
standard adjudication (same investigators, seed salt 0); every other split replays the standard prompt.

    python analysis/plan019_e3.py          # prints markdown; writes runs/plan019_e3.md
Pre-registered (audits/019_agent_24h.md): adopt only if the mean gain on the count and text splits is above +3 points
with at least 9 of 14 triples up.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
TAGS = ["_t012", "_t234", "_t345", "_t567", "_t8910", "_t111213", "_t141516", "_t171819", "_t202122", "_t232425",
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
    kind = json.loads((RUNS / "dispute_kind_by_key.json").read_text(encoding="utf-8"))
    lines = ["# Plan 019, E3: a procedure for count and on-screen-text disputes (paired per triple)", "",
             "| Triple | Count + text splits | Standard | With the procedure | Fixed / broke | Other splits unchanged |",
             "|---|---|---|---|---|---|"]
    gains, fx_all, br_all = [], 0, 0
    for t in TAGS:
        if not finished(f"mg_adjkind{t}"):
            continue
        std, new = load("mg_adjev" + ("" if t == "_t012" else t)), load(f"mg_adjkind{t}")
        keys = [k for k in std if k in new and std[k]["contested"]]
        target = [k for k in keys if kind.get(k[1]) in ("count", "text")]
        other = [k for k in keys if k not in target]
        if not target:
            continue
        ok = lambda r, k: r[k]["verdict"] == r[k]["good_side"]       # noqa: E731
        a, b = sum(ok(std, k) for k in target), sum(ok(new, k) for k in target)
        fx = sum(ok(new, k) and not ok(std, k) for k in target)
        br = sum(ok(std, k) and not ok(new, k) for k in target)
        same = sum(std[k]["verdict"] == new[k]["verdict"] for k in other)
        g = 100 * (b - a) / len(target)
        gains.append(g); fx_all += fx; br_all += br
        lines.append(f"| {t[1:]} | {len(target)} | {100 * a / len(target):.1f} | {100 * b / len(target):.1f} | {fx} / {br} | "
                     f"{same} of {len(other)} |")
    if gains:
        up, down = sum(g > 0 for g in gains), sum(g < 0 for g in gains)
        lines += ["", f"- {len(gains)} triples: mean gain on the count and text splits {statistics.mean(gains):+.2f} points "
                      f"(sd {statistics.pstdev(gains):.2f}); triples up / down {up} / {down}; fixed {fx_all}, broke {br_all}."]
        if len(gains) == 14:
            ok_ = statistics.mean(gains) > 3 and up >= 9
            lines.append(f"- Pre-registered rule: **{'ADOPT' if ok_ else 'do not adopt'}** the procedure for Portia's local mode.")
    text = "\n".join(lines)
    print(text)
    (RUNS / "plan019_e3.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
