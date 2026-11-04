#!/usr/bin/env python3
"""portia/analysis/spark13_report.py: plan 013: Muse Spark 1.3 Contributor (Meta Model API) as the evidence-only adjudicator.

    python analysis/spark13_report.py          # prints markdown; also writes runs/plan013_report.md

Per investigator triple (development shards 3-4), on the contests the Spark 1.3 run has finished: the vote, Spark 1.3
Contributor (mg_adjs13_*), Spark Open on Baseten (mg_adjsp_*, plan 006) and the mean of the Glimmer evidence-only
samples (plan 005). Gains are accuracy minus the vote; costs come from runs/meta_spend.jsonl (tag plan013_adj).
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIPLES = [("{5,6,7}", "t567", "fresh", ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"]),
           ("{8,9,10}", "t8910", "fresh", ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"]),
           ("{3,4,5}", "t345", "shares seeds 3-4", ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"]),
           ("{0,1,2}", "t012", "selection triple", ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_r3", "mg_adjev_r4"]),
           ("{2,3,4}", "t234", "selection triple", ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"])]


def rows(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = ROOT / "runs" / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            out.update({json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()})
    return out


def main():
    spend = [json.loads(l) for l in (ROOT / "runs" / "meta_spend.jsonl").read_text().splitlines() if l.strip()] \
        if (ROOT / "runs" / "meta_spend.jsonl").exists() else []
    out = ["# Plan 013: Muse Spark 1.3 Contributor as the evidence-only adjudicator (development shards 3-4)", "",
           "Gain = accuracy minus the vote of the same three Glimmer investigators, on the contests the Spark 1.3 run has finished.", "",
           "| Triple | Relation | Contests (splits) | Vote | Spark 1.3 Contributor | Spark Open (Baseten) | Glimmer (mean) | Spark 1.3 cost |",
           "|---|---|---|---|---|---|---|---|"]
    tot = {"n": 0, "v": 0, "s13": 0, "so": 0, "g": 0.0, "usd": 0.0, "adj": 0}
    for label, tag, rel, gl in TRIPLES:
        S = rows(f"mg_adjs13_{tag}")
        if not S:
            out.append(f"| {label} | {rel} | not run yet | | | | | |")
            continue
        O, G = rows(f"mg_adjsp_{tag}"), [rows(r) for r in gl]
        keys = [k for k in S if k in O and all(k in g for g in G)]
        if not keys:
            continue
        good = {k: S[k]["good_side"] for k in keys}
        n = len(keys)
        v = sum(bool(S[k].get("vote_correct")) for k in keys)
        s13 = sum(S[k].get("verdict") == good[k] for k in keys)
        so = sum(O[k].get("verdict") == good[k] for k in keys)
        g = st.mean(sum(x[k].get("verdict") == good[k] for k in keys) for x in G)
        adj = sum(bool(S[k].get("contested")) for k in keys)
        usd = sum(r["usd"] for r in spend if r.get("tag") == "plan013_adj" and r.get("run", "").startswith(f"mg_adjs13_{tag}_"))
        full = all((ROOT / "runs" / f"mg_adjs13_{tag}_{s}" / "summary.json").exists() for s in ("s3", "s4"))
        out.append(f"| {label}{'' if full else ' (partial)'} | {rel} | {n} ({adj}) | {100 * v / n:.1f} | **{100 * (s13 - v) / n:+.1f}** | "
                   f"{100 * (so - v) / n:+.1f} | {100 * (g - v) / n:+.1f} | ${usd:.3f} (${usd / max(adj, 1):.4f}/adj.) |")
        tot["n"] += n; tot["v"] += v; tot["s13"] += s13; tot["so"] += so; tot["g"] += g; tot["usd"] += usd; tot["adj"] += adj
    if tot["n"]:
        n = tot["n"]
        out += ["", f"All so far ({n} contest-triples, {tot['adj']} adjudications): Spark 1.3 Contributor "
                    f"{100 * (tot['s13'] - tot['v']) / n:+.1f}, Spark Open {100 * (tot['so'] - tot['v']) / n:+.1f}, Glimmer "
                    f"{100 * (tot['g'] - tot['v']) / n:+.1f} points over the vote; Spark 1.3 accuracy {100 * tot['s13'] / n:.1f}% "
                    f"(vote {100 * tot['v'] / n:.1f}%); cost ${tot['usd']:.3f} (${tot['usd'] / max(tot['adj'], 1):.4f} per adjudication)."]
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan013_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
