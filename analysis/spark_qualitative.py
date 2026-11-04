#!/usr/bin/env python3
"""portia/analysis/spark_qualitative.py: why Spark Open works as the adjudicator (plan 006), development shards 3-4.

    python analysis/spark_qualitative.py [--examples]

Over the 5 investigator triples (same contests, same investigators) it compares Spark Open's evidence-only verdicts
with Glimmer's (every finished evidence-only sample, plan 005) and with the report-reading Glimmer adjudicator where it
ran, on:
  * where the vote can be trusted: accuracy on unanimous vs contested contests;
  * herding: on contested contests whose majority is wrong, how often the adjudicator still sides with it;
  * process: turns, own looks and tools used;
  * ground truth: whether the adjudicator's text names a degradation of the worse answer (the dataset's changed
    details; the same matcher as the Ideas page), and by kind of degradation.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "analysis")]
from gt_match import gt_check                        # noqa: E402  (analysis/gt_match.py: dataset ground-truth matcher)
from judge.contests import DATASET, load_contests    # noqa: E402

TRIPLES = {"t567": ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"],
           "t8910": ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"],
           "t345": ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"],
           "t012": ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_o1", "mg_adjev_sw", "mg_adjev_r3", "mg_adjev_r4"],
           "t234": ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"]}
READER = {"t012": "mg_adj", "t234": "mg_adj_t234", "t567": "mg_adj_t567", "t345": "mg_adj_t345"}
SHARDS = {"s3": "shard3_15pct", "s4": "shard4_20pct"}


def rows(name: str) -> dict:
    p = ROOT / "runs" / name / "results.jsonl"
    return {json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()} if p.exists() else {}


def text_of(run: str, cid: str, r: dict) -> str:
    """Rationale + the reasoning of the last two turns (the rationale alone is short)."""
    f = ROOT / "runs" / run / "trajectories" / f"{cid}.json"
    st_ = ((json.loads(f.read_text(encoding="utf-8")).get("trajectory") or {}).get("steps") or []) if f.exists() else []
    return (r.get("rationale") or "") + "\n" + "\n".join((s.get("reasoning") or "") for s in st_[-2:])


def tools_of(r: dict) -> list:
    tc = r.get("tool_calls") or []
    if isinstance(tc, str):
        import ast
        try:
            tc = ast.literal_eval(tc)
        except (ValueError, SyntaxError):
            return []
    return [c.get("tool") for c in tc if isinstance(c, dict)]


def main(examples: bool):
    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    A = defaultdict(list)                               # metric -> list of values (one per contest-triple)
    proc = defaultdict(lambda: defaultdict(list))
    tools = {"spark": Counter(), "glimmer": Counter()}
    gt = defaultdict(lambda: [0, 0])                    # (who, right/wrong) -> [named worse degradation, n]
    cats = defaultdict(lambda: [0, 0])                  # degradation kind -> [Spark right, n] on contested
    ex = []
    for t, ev_runs in TRIPLES.items():
        for s, shard in SHARDS.items():
            cs = load_contests([shard])
            byk = {c.key: (i, c) for i, c in enumerate(cs)}
            S = rows(f"mg_adjsp_{t}_{s}")
            E = [x for x in (rows(f"{r}_{s}") for r in ev_runs) if len(x) >= 0.9 * len(S)]
            RD = rows(f"{READER[t]}_{s}") if t in READER else {}
            for k, r in S.items():
                good, vote = r["good_side"], r.get("vote")
                if not r.get("contested"):
                    A["unanimous_vote_ok"].append(vote == good)
                    continue
                i, c = byk[k]
                cid = f"{shard}_{i:03d}"
                inv = r.get("inv_verdicts") or []
                maj_wrong = vote != good
                A["contested_vote_ok"].append(vote == good)
                A["contested_spark_ok"].append(r.get("verdict") == good)
                eok = [x[k].get("verdict") == good for x in E if k in x]
                if eok:
                    A["contested_glimmer_ev_ok"].append(st.mean(eok))
                if k in RD:
                    A["contested_reader_ok"].append(RD[k].get("verdict") == good)
                    A["contested_spark_ok_where_reader"].append(r.get("verdict") == good)
                if maj_wrong and vote in ("A", "B"):
                    A["herd_spark"].append(r.get("verdict") == vote)
                    if eok:
                        A["herd_glimmer_ev"].append(st.mean(x[k].get("verdict") == vote for x in E if k in x))
                    if k in RD:
                        A["herd_reader"].append(RD[k].get("verdict") == vote)
                proc["spark"]["steps"].append(r.get("steps") or 0)
                proc["spark"]["own_images"].append(r.get("images_viewed") or 0)
                tools["spark"].update(tools_of(r))
                if E and k in E[0]:
                    g0 = E[0][k]
                    proc["glimmer"]["steps"].append(g0.get("steps") or 0)
                    proc["glimmer"]["own_images"].append(g0.get("images_viewed") or 0)
                    tools["glimmer"].update(tools_of(g0))
                # ground truth: does each text name a degradation of the worse answer?
                ev_name = f"{ev_runs[0]}_{s}"
                texts = {"spark": text_of(f"mg_adjsp_{t}_{s}", cid, r)}
                if E and k in E[0]:
                    texts["glimmer"] = text_of(ev_name, cid, E[0][k])
                g = gt_check(recs[c.qid], c, texts)
                for who in texts:
                    ok = (r.get("verdict") if who == "spark" else E[0][k].get("verdict")) == good
                    named = g["summary"][who]["worse_named"] > 0
                    gt[(who, ok)][0] += named
                    gt[(who, ok)][1] += 1
                kinds = {x for d in g["details"] if d["worse"] for x in d["cats"]}
                for kd in kinds:
                    cats[kd][0] += r.get("verdict") == good
                    cats[kd][1] += 1
                if examples and r.get("verdict") == good and maj_wrong and t in ("t567", "t8910"):
                    named = [d["element"] for d in g["details"] if d["worse"] and d["caught"]["spark"]]
                    if named:
                        ex.append({"cid": cid, "triple": t, "domain": c.domain, "pair": c.pair, "question": c.question[:300],
                                   "named": named[:3], "inv": inv, "vote": vote, "good": good,
                                   "spark": (r.get("rationale") or "")[:700],
                                   "glimmer_ev_ok": eok, "tools": tools_of(r)})
    pc = lambda xs: f"{100 * st.mean(xs):.1f}% (n={len(xs)})" if xs else "-"
    print("## Where the vote can be trusted")
    print(f"unanimous contests: vote right {pc(A['unanimous_vote_ok'])}")
    print(f"contested contests: vote right {pc(A['contested_vote_ok'])}")
    print("## Contested contests: who decides better")
    print(f"Spark evidence-only {pc(A['contested_spark_ok'])} | Glimmer evidence-only (mean of samples) {pc(A['contested_glimmer_ev_ok'])}")
    print(f"where the report-reading Glimmer adjudicator ran: it {pc(A['contested_reader_ok'])} vs Spark {pc(A['contested_spark_ok_where_reader'])}")
    print("## Herding: contested contests with a WRONG majority; share that sides with it anyway")
    print(f"Spark {pc(A['herd_spark'])} | Glimmer evidence-only {pc(A['herd_glimmer_ev'])} | Glimmer reading the reports {pc(A['herd_reader'])}")
    print("## Process on contested contests")
    for who in ("spark", "glimmer"):
        print(f"{who}: turns {st.mean(proc[who]['steps']):.1f}, own images {st.mean(proc[who]['own_images']):.1f}, tools "
              + ", ".join(f"{k} {v / len(proc[who]['steps']):.2f}" for k, v in tools[who].most_common(7)))
    print("## Ground truth: names a degradation of the worse answer (contested contests)")
    for who in ("spark", "glimmer"):
        for ok in (True, False):
            n_, d_ = gt[(who, ok)]
            print(f"{who} when {'right' if ok else 'wrong'}: {n_} of {d_} ({100 * n_ / max(d_, 1):.0f}%)")
    print("## Spark accuracy on contested contests by kind of degradation in the worse answer")
    for kd, (w, n) in sorted(cats.items(), key=lambda kv: -kv[1][1])[:10]:
        print(f"  {kd}: {w} of {n} ({100 * w / n:.0f}%)")
    if examples:
        print(f"## {len(ex)} fixed examples (fresh triples) where Spark's text names the changed detail")
        for e in ex[:8]:
            print(json.dumps(e, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main("--examples" in sys.argv)
