#!/usr/bin/env python3
"""portia/analysis/spark_agent_report.py: plan 007: Muse Spark Open as the whole agent, measured on 10 dev contests.

    python analysis/spark_agent_report.py          # prints markdown; also writes runs/plan007_report.md

Costs per contest come from the trajectories (each request's Baseten usage, cached input included) at Baseten's prices;
the run total also comes from runs/baseten_spend.jsonl (tag plan007_spark_agent), which includes any unfinished contest.
Accuracy is descriptive only (10 contests): the Spark agent's verdict next to each of the 11 Glimmer agent seeds and the
plan-006 system (three Glimmer agents + Spark on contested contests) for the 5 investigator triples, same contests.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge.contests import load_contests  # noqa: E402

RUN, SHARD, TAG = "sp_v4t_s4p10", "shard4_20pct", "plan007_spark_agent"
P_IN, P_CACHED, P_OUT = 1.25e-6, 0.15e-6, 4.25e-6
GLIMMER = ["mg_v4t_s4"] + [f"mg_v4t_r{i}_s4" for i in range(1, 11)]
TRIPLES = ["t567", "t8910", "t345", "t012", "t234"]
ESTIMATE = (0.269, 0.376)                       # analysis/spark_agent_cost.py: central, upper bound
COMBINATION = 18.80 / 1100                      # plan 006: Spark spend over 5 triples x 220 contests


def rows(name: str) -> dict:
    p = ROOT / "runs" / name / "results.jsonl"
    return {json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()} if p.exists() else {}


def cost(usage: dict) -> float:
    pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    cached = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
    return (pt - cached) * P_IN + cached * P_CACHED + ct * P_OUT


def main():
    cs = load_contests([SHARD])
    pos = {c.key: i for i, c in enumerate(cs)}
    S = rows(RUN)
    G = [rows(g) for g in GLIMMER]
    sysv = []                                    # plan 006 system verdicts per triple: Spark if contested, else the vote
    for t in TRIPLES:
        R = rows(f"mg_adjsp_{t}_s4")
        sysv.append({k: (r.get("verdict") if r.get("contested") else r.get("vote")) for k, r in R.items()})
    out = ["# Plan 007: Muse Spark Open as the whole agent (10 development contests, shard 4)", "",
           "| Contest | Domain | Requests | Input tokens (cached) | Output tokens | Spark cost | Wall | Spark agent | "
           "Glimmer agent seeds right | Combination triples right |", "|---|---|---|---|---|---|---|---|---|---|"]
    usd, req, pin, cin, outt, wall, ok = [], [], [], [], [], [], 0
    for k, r in sorted(S.items(), key=lambda kv: pos[kv[0]]):
        f = ROOT / "runs" / RUN / "trajectories" / f"{SHARD}_{pos[k]:03d}.json"
        steps = ((json.loads(f.read_text(encoding="utf-8")).get("trajectory") or {}).get("steps") or []) if f.exists() else []
        us = [s.get("usage") or {} for s in steps]
        c = sum(cost(u) for u in us)
        p_ = sum(int(u.get("prompt_tokens") or 0) for u in us)
        ca = sum(int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0) for u in us)
        o_ = sum(int(u.get("completion_tokens") or 0) for u in us)
        usd.append(c); req.append(len(us)); pin.append(p_); cin.append(ca); outt.append(o_); wall.append(r.get("wall_s") or 0)
        right = r.get("verdict") == r["good_side"]
        ok += right
        g_ok = sum(g[k].get("verdict") == r["good_side"] for g in G if k in g)
        g_n = sum(k in g for g in G)
        s_ok = sum(v.get(k) == r["good_side"] for v in sysv if k in v)
        s_n = sum(k in v for v in sysv)
        out.append(f"| {SHARD}_{pos[k]:03d} | {r['domain']} | {len(us)} | {p_:,} ({ca:,}) | {o_:,} | ${c:.3f} | {r.get('wall_s', 0):.0f} s | "
                   f"{'right' if right else 'wrong'} ({r.get('how')}) | {g_ok} of {g_n} | {s_ok} of {s_n} |")
    if not usd:
        print("no finished contests yet")
        return
    spend = [json.loads(l) for l in (ROOT / "runs" / "baseten_spend.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    total = sum(x["usd"] for x in spend if x.get("tag") == TAG)
    n = len(usd)
    g_mean = st.mean(sum(g[k].get("verdict") == S[k]["good_side"] for k in S if k in g) / n for g in G if all(k in g for k in S))
    s_mean = st.mean(sum(v.get(k) == S[k]["good_side"] for k in S) / n for v in sysv if all(k in v for k in S))
    out += ["", f"**Measured: ${st.mean(usd):.3f} per contest** (range ${min(usd):.3f}-${max(usd):.3f}; {st.mean(req):.1f} requests, "
                f"{st.mean(pin):,.0f} input tokens of which {100 * sum(cin) / max(sum(pin), 1):.0f}% cached, {st.mean(outt):,.0f} output; "
                f"{st.mean(wall) / 60:.1f} min per contest). Estimate was ${ESTIMATE[0]:.2f} (at most ${ESTIMATE[1]:.2f}).",
            f"Against the combination's measured ${COMBINATION:.3f} per contest: the Spark agent costs "
            f"{st.mean(usd) / COMBINATION:.0f} times as much ({100 * (1 - COMBINATION / st.mean(usd)):.0f}% saved by the combination).",
            f"Run total from the spend log: ${total:.2f} for {n} finished contest(s).",
            f"Accuracy on these {n} contests (descriptive only): Spark agent {ok} of {n}; a Glimmer agent {100 * g_mean:.0f}% "
            f"(mean of {len(G)} seeds); the combination {100 * s_mean:.0f}% (mean of {len(sysv)} triples)."]
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan007_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
