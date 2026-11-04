#!/usr/bin/env python3
"""portia/analysis/adjsearch_report.py: plan 010: the Glimmer evidence-only adjudicator that may also search.

    python analysis/adjsearch_report.py          # prints markdown; also writes runs/plan010_report.md

Per investigator triple (development shards 3-4, split contests only), against the vote of the same investigators:
the search adjudicator's gain (one sample, mg_adjsx_<triple>) and the mean gain of the existing evidence-only Glimmer
samples without search (plan 005). Process: how often it searched, and whether its own calls reached an evidence clip
(the dataset's clip_ranges) that the investigators' looks had missed.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "analysis")]
from judge import corpus                              # noqa: E402
from judge.adjudicate import span                     # noqa: E402
from judge.contests import load_contests              # noqa: E402
from retrieval_queries import clips                   # noqa: E402

TRIPLES = [("{5,6,7}", "t567", "fresh", ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"]),
           ("{8,9,10}", "t8910", "fresh", ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"]),
           ("{3,4,5}", "t345", "shares seeds 3-4", ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"]),
           ("{0,1,2}", "t012", "selection triple", ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_r3", "mg_adjev_r4"]),
           ("{2,3,4}", "t234", "selection triple", ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"])]
SEARCH = {"search", "search_video", "grep_transcripts"}


def rows(run: str) -> dict:
    p = ROOT / "runs" / run / "results.jsonl"
    return {json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()} if p.exists() else {}


def touched(calls: list, cl: list) -> set:
    """indexes of the evidence clips any of these calls looked at"""
    out = set()
    for j, h in enumerate(cl):
        segs = [(x.split("@")[0], float(x.split("@")[1])) for x in h]
        for c in calls:
            sp = span({"tool": c.get("tool"), "args": c.get("args") or {}})
            if sp and sp[1] is not None and any(v == sp[0] and sp[1] <= s + 30 and s <= sp[2] for v, s in segs):
                out.add(j)
    return out


def main():
    cs = {c.key: c for c in load_contests(["shard3_15pct", "shard4_20pct"])}
    corpus.register(sorted({p for c in cs.values() for p in corpus.domain_playlists(c.domain)}))
    out = ["# Plan 010: the Glimmer evidence-only adjudicator that may also search (development shards 3-4)", "",
           "Gain = accuracy minus the vote of the same three investigators, on the contests both runs finished. "
           "Without search = mean of the existing evidence-only Glimmer samples (4 turns, plan 005).", "",
           "| Triple | Relation | Splits | Vote | With search | Gain with search | Fixed / broken | Gain without search (samples) |",
           "|---|---|---|---|---|---|---|---|"]
    tot = {"n": 0, "x": 0, "v": 0, "g": 0.0}
    proc = {"cases": 0, "searched": 0, "search_calls": [], "new_clip": 0, "split_right": [], "split_right_searched": []}
    for label, tag, rel, ev_runs in TRIPLES:
        X = {**rows(f"mg_adjsx_{tag}_s3"), **rows(f"mg_adjsx_{tag}_s4")}
        if not X:
            out.append(f"| {label} | {rel} | not run yet | | | | | |")
            continue
        full = all((ROOT / "runs" / f"mg_adjsx_{tag}_{s}" / "summary.json").exists() for s in ("s3", "s4"))
        E = [{**rows(f"{r}_s3"), **rows(f"{r}_s4")} for r in ev_runs]
        keys = [k for k in X if all(k in e for e in E)]
        good = {k: X[k]["good_side"] for k in keys}
        vote = sum(bool(X[k].get("vote_correct")) for k in keys)
        acc = sum(X[k].get("verdict") == good[k] for k in keys)
        fixed = sum(X[k].get("verdict") == good[k] and not X[k].get("vote_correct") for k in keys)
        broken = sum(X[k].get("verdict") != good[k] and X[k].get("vote_correct") for k in keys)
        g = st.mean(sum(e[k].get("verdict") == good[k] for k in keys) for e in E)
        n = len(keys)
        splits = sum(bool(X[k].get("contested")) for k in keys)
        out.append(f"| {label}{'' if full else ' (partial)'} | {rel} | {splits} | {100 * vote / n:.1f} | {100 * acc / n:.1f} | "
                   f"**{100 * (acc - vote) / n:+.1f}** | {fixed} / {broken} | {100 * (g - vote) / n:+.1f} ({len(E)}) |")
        tot["n"] += n; tot["x"] += acc; tot["v"] += vote; tot["g"] += g
        for k in keys:
            r = X[k]
            if not r.get("contested"):
                continue
            calls = r.get("tool_calls") or []
            ns = sum(c.get("tool") in SEARCH for c in calls)
            proc["cases"] += 1
            proc["searched"] += ns > 0
            proc["search_calls"].append(ns)
            proc["split_right"].append(r.get("verdict") == good[k])
            if ns:
                proc["split_right_searched"].append(r.get("verdict") == good[k])
            cl = clips(cs[k].rec) if k in cs else []
            if cl:
                tf = ROOT / "runs" / f"mg_adjsx_{tag}_{'s3' if cs[k].shard.startswith('shard3') else 's4'}" / "trajectories"
                picked = []
                for f in tf.glob("*.json"):
                    t = json.loads(f.read_text(encoding="utf-8"))
                    if t.get("key") == k:
                        picked = [c for rep in ((t.get("trajectory") or {}).get("picked_views") or []) for c in rep]
                        break
                proc["new_clip"] += bool(touched(calls, cl) - touched(picked, cl))
    if tot["n"]:
        out += ["", f"All triples so far: with search {100 * (tot['x'] - tot['v']) / tot['n']:+.1f} vs without search "
                    f"{100 * (tot['g'] - tot['v']) / tot['n']:+.1f} (points over the vote, {tot['n']} contest-triples)."]
    if proc["cases"]:
        out.append(f"Process on {proc['cases']} splits: searched in {100 * proc['searched'] / proc['cases']:.0f}% "
                   f"(mean {st.mean(proc['search_calls']):.1f} search/grep calls); its own calls reached an evidence clip the "
                   f"investigators' looks had missed in {100 * proc['new_clip'] / proc['cases']:.0f}%; right on splits "
                   f"{100 * st.mean(proc['split_right']):.1f}%.")
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan010_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
