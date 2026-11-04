#!/usr/bin/env python3
"""portia/analysis/plan019_e2.py: plan 019, experiment E2: do investigators that look around before answering (a
contact-sheet note at two turns left, --look-around) beat the same seeds without it? Pairs mg_v4tla_r<seed> with the
baseline mg_v4t_r<seed> on the contests both finished (development shards 3-4), then each triple's majority vote.

    python analysis/plan019_e2.py          # prints markdown; writes runs/plan019_e2.md
Pre-registered (audits/019_agent_24h.md): adopt only if per-agent accuracy rises on both triples and the pooled gain
over the six seed pairs is above +1 point.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
TRIPLES = [(41, 42, 43), (44, 45, 46)]


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


def main():
    lines = ["# Plan 019, E2: look-around investigators against the same seeds without the note", "",
             "| Seed | Contests | Baseline | Look-around | Fixed / broke | Answered on their own (base / look) |", "|---|---|---|---|---|---|"]
    tot = {"n": 0, "b": 0, "v": 0}
    per_triple = {}
    for tri in TRIPLES:
        pairs = []
        for seed in tri:
            b, v = load(f"mg_v4t_r{seed}"), load(f"mg_v4tla_r{seed}")
            keys = [k for k in b if k in v]
            if not keys:
                continue
            ok = lambda r, k: r[k].get("verdict") == r[k]["good_side"]       # noqa: E731
            nb, nv = sum(ok(b, k) for k in keys), sum(ok(v, k) for k in keys)
            fx = sum(ok(v, k) and not ok(b, k) for k in keys)
            br = sum(ok(b, k) and not ok(v, k) for k in keys)
            own = lambda r: sum(r[k].get("how") == "tool" for k in keys)     # noqa: E731
            lines.append(f"| {seed} | {len(keys)} | {100 * nb / len(keys):.1f} | {100 * nv / len(keys):.1f} | {fx} / {br} | "
                         f"{own(b)} / {own(v)} |")
            tot["n"] += len(keys); tot["b"] += nb; tot["v"] += nv
            pairs.append((b, v, keys))
        if len(pairs) == 3:
            keys = [k for k in pairs[0][2] if all(k in p[2] for p in pairs)]
            def vote(idx):
                c = 0
                for k in keys:
                    vs = [p[idx][k].get("verdict") for p in pairs]
                    m = max(("A", "B"), key=vs.count)
                    c += m == pairs[0][0][k]["good_side"]
                return 100 * c / len(keys)
            per_triple[tri] = (vote(0), vote(1), len(keys))
    if tot["n"]:
        lines += ["", f"Pooled over the finished seed pairs: baseline {100 * tot['b'] / tot['n']:.1f}%, look-around "
                      f"{100 * tot['v'] / tot['n']:.1f}% ({100 * (tot['v'] - tot['b']) / tot['n']:+.2f} points, {tot['n']} agent-contests)."]
    for tri, (vb, vv, n) in per_triple.items():
        lines.append(f"- Triple {tri}: vote {vb:.1f}% baseline, {vv:.1f}% look-around ({vv - vb:+.1f}, {n} contests).")
    text = "\n".join(lines)
    print(text)
    (RUNS / "plan019_e2.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
