#!/usr/bin/env python3
"""portia/analysis/spark_report.py: plan 006: Muse Spark Open (Baseten) as the evidence-only adjudicator, per triple.

    python analysis/spark_report.py          # prints markdown; also writes runs/plan006_dev_report.md

For each investigator triple (development shards 3-4) it compares, on the contests the Spark run has finished:
  * the investigators' vote;
  * Spark Open's evidence-only verdicts (one sample);
  * the Glimmer evidence-only adjudicator: the mean over its finished samples on the same contests (plan 005).
Gains are accuracy minus the vote, in points. Costs come from runs/baseten_spend.jsonl (tracked locally).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIPLES = [("{5,6,7}", "t567", "fresh", ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"]),
           ("{8,9,10}", "t8910", "fresh", ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"]),
           ("{3,4,5}", "t345", "shares seeds 3-4", ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"]),
           ("{0,1,2}", "t012", "selection triple", ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_o1", "mg_adjev_sw",
                                                    "mg_adjev_r3", "mg_adjev_r4"]),
           ("{2,3,4}", "t234", "selection triple", ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"])]
N = {"s3": 94, "s4": 126}


def rows(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = ROOT / "runs" / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    out[r["key"]] = r
    return out


def costs() -> dict:
    by = defaultdict(lambda: [0, 0.0])
    p = ROOT / "runs" / "baseten_spend.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("tag") == "plan006_dev":
                    by[r.get("run", "")][0] += 1
                    by[r.get("run", "")][1] += r["usd"]
    return by


def main():
    C = costs()
    out = ["# Plan 006: Muse Spark Open as the evidence-only adjudicator (development shards 3-4)", "",
           "Gain = accuracy minus the vote of the same three investigators, on the contests the Spark run has finished. "
           "Glimmer = the mean over its finished evidence-only samples on the same contests (plan 005).", "",
           "| Triple | Relation | Contests (contested) | Vote | Spark Open | Spark gain | Spark fixed / broken | "
           "Glimmer mean gain (samples) | Spark cost |", "|---|---|---|---|---|---|---|---|---|"]
    tot = {"n": 0, "spark": 0, "vote": 0, "glim": 0.0, "adj": 0, "usd": 0.0}
    fresh = {"n": 0, "spark": 0, "vote": 0, "glim": 0.0}
    for label, tag, rel, glim_runs in TRIPLES:
        S = rows(f"mg_adjsp_{tag}")
        keys = [k for k, r in S.items() if r.get("verdict") is not None or r.get("how") == "unanimous"]
        if not keys:
            out.append(f"| {label} | {rel} | not run yet | | | | | | |")
            continue
        full = all((ROOT / "runs" / f"mg_adjsp_{tag}_{s}" / "summary.json").exists() for s in ("s3", "s4"))
        good = {k: S[k]["good_side"] for k in keys}
        vote = sum(bool(S[k].get("vote_correct")) for k in keys)
        spark = sum(S[k].get("verdict") == good[k] for k in keys)
        fixed = sum(S[k].get("verdict") == good[k] and not S[k].get("vote_correct") for k in keys)
        broken = sum(S[k].get("verdict") != good[k] and S[k].get("vote_correct") for k in keys)
        G = [rows(r) for r in glim_runs]
        G = [g for g in G if all(k in g for k in keys)]
        glim = (sum(sum(g[k].get("verdict") == good[k] for k in keys) for g in G) / len(G)) if G else None
        con = sum(bool(S[k].get("contested")) for k in keys)
        n_adj = sum(1 for k in keys if S[k].get("contested"))
        usd = sum(C[f"mg_adjsp_{tag}_{s}"][1] for s in ("s3", "s4"))
        n = len(keys)
        g_txt = f"{100 * (glim - vote) / n:+.1f} ({len(G)})" if glim is not None else "-"
        out.append(f"| {label}{'' if full else ' (partial)'} | {rel} | {n} ({con}) | {100 * vote / n:.1f} | {100 * spark / n:.1f} | "
                   f"**{100 * (spark - vote) / n:+.1f}** | {fixed} / {broken} | {g_txt} | ${usd:.2f} (${usd / max(n_adj, 1):.3f}/adj.) |")
        tot["n"] += n; tot["spark"] += spark; tot["vote"] += vote; tot["adj"] += n_adj; tot["usd"] += usd
        if glim is not None:
            tot["glim"] += glim
        if rel == "fresh":
            fresh["n"] += n; fresh["spark"] += spark; fresh["vote"] += vote; fresh["glim"] += glim or 0
    if tot["n"]:
        out += ["", f"All triples so far: Spark {100 * (tot['spark'] - tot['vote']) / tot['n']:+.1f} vs Glimmer "
                    f"{100 * (tot['glim'] - tot['vote']) / tot['n']:+.1f} (points over the vote, {tot['n']} contest-triples); "
                    f"{tot['adj']} Spark adjudications, ${tot['usd']:.2f} (${tot['usd'] / max(tot['adj'], 1):.3f} each)."]
    if fresh["n"]:
        out.append(f"Fresh triples only: Spark {100 * (fresh['spark'] - fresh['vote']) / fresh['n']:+.1f} vs Glimmer "
                   f"{100 * (fresh['glim'] - fresh['vote']) / fresh['n']:+.1f} over {fresh['n']} contest-triples.")
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan006_dev_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
