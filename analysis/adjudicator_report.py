#!/usr/bin/env python3
"""portia/analysis/adjudicator_report.py: plan 004's development numbers (audits/004_investigators_adjudicator.md).

    python analysis/adjudicator_report.py            # prints markdown; also writes runs/plan004_dev_report.md

For every adjudicator run on development shards 3-4 it compares the run with the vote of ITS OWN investigators on the
same contests (pooled over shards 3 and 4), and applies the go/no-go rule fixed in the plan: a variant qualifies when,
pooled over triples {0,1,2} and {2,3,4}, it beats the vote by >= 2 points and is not worse than the vote in either
triple. Diagnostics (other seeds, report order, --all, 8 turns, mixed team, replication triples) are reported but are
never candidates. Runs still in progress are reported on the contests they have finished, marked "partial".
"""
from __future__ import annotations

import json
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N = {"s3": 94, "s4": 126}
CANDIDATES = {"adjudicator": ("mg_adj", "mg_adj_t234"), "evidence": ("mg_adjev", "mg_adjev_t234"),
              "rebuttal": ("mg_adjrb", "mg_adjrb_t234")}
DIAGNOSTICS = [("evidence-only, seed 1", "mg_adjev_r1"), ("evidence-only, seed 2", "mg_adjev_r2"),
               ("evidence-only, view order 1", "mg_adjev_o1"), ("evidence-only on every contest (--all)", "mg_adjev_all"),
               ("evidence-only, 8 turns", "mg_adjev_k8"), ("POST-HACKATHON: evidence-only, mixed-model team (Muse 0, Qwen3.8 v4, Muse 1)", "mg_adjev_het"),
               ("evidence-only, replication triple {5,6,7}", "mg_adjev_t567"), ("evidence-only, replication triple {3,4,5}", "mg_adjev_t345"),
               ("adjudicator, replication triple {5,6,7}", "mg_adj_t567"), ("adjudicator, replication triple {3,4,5}", "mg_adj_t345"),
               ("POST-HACKATHON: adjudicator, mixed-model team (Muse 0, Qwen3.8 v4, Muse 1)", "mg_adj_het"),
               ("plan 005 B: evidence-only, answers swapped", "mg_adjev_sw"),
               ("plan 005 C: evidence-only, five investigators' looks (seeds 0-4)", "mg_adjev5"),
               ("plan 005 D: evidence-only, xhigh adjudicator", "mg_adjev_x"),
               ("plan 005 E: claim-by-claim rulings", "mg_adjev_claims"),
               ("plan 005 E: claim-by-claim rulings, seed 1", "mg_adjev_claims_r1"),
               ("plan 005 E: claim-by-claim rulings, seed 2", "mg_adjev_claims_r2"),
               ("evidence-only, seed 3", "mg_adjev_r3"), ("evidence-only, seed 4", "mg_adjev_r4"),
               ("plan 005 F: evidence-only, up to 6 looks per report", "mg_adjev_v6"),
               ("plan 005 C: five investigators, seed 1", "mg_adjev5_r1"), ("plan 005 C: five investigators, seed 2", "mg_adjev5_r2")]


def rows(run: str) -> dict:
    p = ROOT / "runs" / run / "results.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["key"]] = r
    return out


def mcnemar(b: int, c: int) -> float:
    n = b + c
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.0


def pooled(prefix: str) -> dict | None:
    """One run name prefix over shards 3 and 4: accuracy of the run and of its investigators' vote, same contests."""
    rs = []
    full = True
    for s in ("s3", "s4"):
        d = rows(f"{prefix}_{s}")
        full &= len(d) >= N[s]
        rs += list(d.values())
    if not rs:
        return None
    n = len(rs)
    ok = sum(bool(r.get("correct")) for r in rs)
    vote = sum(bool(r.get("vote_correct")) for r in rs)
    fixed = sum(bool(r.get("correct")) and not r.get("vote_correct") for r in rs)
    broken = sum(bool(r.get("vote_correct")) and not r.get("correct") for r in rs)
    con = [r for r in rs if r.get("contested")]
    mw = [r for r in con if r.get("vote") and not r.get("vote_correct")]
    mr = [r for r in con if r.get("vote") and r.get("vote_correct")]
    pct = lambda a, b: round(100 * a / b, 1) if b else None   # noqa: E731
    return {"n": n, "full": full, "acc": pct(ok, n), "vote": pct(vote, n), "gain": round(100 * (ok - vote) / n, 1),
            "fixed": fixed, "broken": broken, "p": round(mcnemar(fixed, broken), 3), "contested": len(con),
            "con_acc": pct(sum(bool(r.get("correct")) for r in con), len(con)),
            "con_vote": pct(sum(bool(r.get("vote_correct")) for r in con), len(con)),
            "herd_wrong": pct(sum(r.get("verdict") == r.get("vote") for r in mw), len(mw)),
            "keep_right": pct(sum(r.get("verdict") == r.get("vote") for r in mr), len(mr)),
            "no_verdict": sum(r.get("verdict") is None for r in rs),
            "changed": sum(int(r.get("changed") or 0) for r in rs),
            "how": dict(Counter(r.get("how") for r in rs))}


def line(label: str, x: dict | None) -> str:
    if not x:
        return f"| {label} | not run yet | | | | | | |"
    tag = "" if x["full"] else " (partial)"
    return (f"| {label}{tag} | {x['n']} | {x['acc']} | {x['vote']} | {x['gain']:+.1f} | {x['fixed']} / {x['broken']} (p {x['p']}) "
            f"| {x['contested']}: {x['con_acc']} vs {x['con_vote']} | {x['herd_wrong']} / {x['keep_right']} |")


def vote5() -> str:
    """Vote of 5 seeds on the development shards, the other cost-matched baseline (open question 1)."""
    out = []
    for s in ("s3", "s4"):
        runs = [rows(n) for n in ([f"mg_v4t_{s}"] + [f"mg_v4t_r{k}_{s}" for k in (1, 2, 3, 4)])]
        keys = set.intersection(*(set(r) for r in runs))
        ok = 0
        for k in keys:
            c = Counter(r[k].get("verdict") for r in runs if r[k].get("verdict") in ("A", "B")).most_common()
            top = c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else None
            ok += top == runs[0][k]["good_side"]
        out.append((s, len(keys), ok))
    n, ok = sum(x[1] for x in out), sum(x[2] for x in out)
    return f"Vote of 5 seeds (0-4), shards 3-4 pooled: {100 * ok / n:.1f}% over {n} contests."


def main():
    head = ("| Run | Contests | Accuracy | Vote of its 3 | Gain | Fixed / broken vs vote | Contested: run vs vote | "
            "Sided with a wrong / right majority |\n|---|---|---|---|---|---|---|---|")
    out = ["# Plan 004, development shards 3-4 (pooled)", "",
           "Each run is compared with the majority vote of its own three investigators on the same contests. "
           "Fixed / broken: contests the run gets right that the vote got wrong, and the reverse (exact McNemar p). "
           "Accuracy in %.", "", "## Candidates (go/no-go)", "", head]
    verdicts = []
    for var, (t012, t234) in CANDIDATES.items():
        a, b = pooled(t012), pooled(t234)
        out += [line(f"{var}, triple {{0,1,2}}", a), line(f"{var}, triple {{2,3,4}}", b)]
        if a and b:
            gain = round((a["gain"] * a["n"] + b["gain"] * b["n"]) / (a["n"] + b["n"]), 1)
            go = gain >= 2 and a["gain"] >= 0 and b["gain"] >= 0
            done = a["full"] and b["full"]
            verdicts.append(f"- **{var}:** pooled gain {gain:+.1f} points; triples {a['gain']:+.1f} / {b['gain']:+.1f} -> "
                            + ("QUALIFIES" if go else "does not qualify") + ("" if done else " (runs not finished: provisional)"))
        else:
            verdicts.append(f"- **{var}:** not enough runs yet")
    out += ["", "Go/no-go (plan 004: pooled gain >= +2 and no triple below the vote):", *verdicts, "",
            vote5(), "", "## Diagnostics (never candidates)", "", head]
    out += [line(lbl, pooled(p)) for lbl, p in DIAGNOSTICS]
    # a vote of the three evidence-only adjudicator samples (seeds 0, 1, 2) on triple {0,1,2}
    rs = [{**rows(f"mg_adjev{x}_s3"), **rows(f"mg_adjev{x}_s4")} for x in ("", "_r1", "_r2")]
    keys = set.intersection(*(set(r) for r in rs)) if all(rs) else set()
    if keys:
        ok = sum((Counter(r[k].get("verdict") for r in rs).most_common(1)[0][0] == rs[0][k]["good_side"]) for k in keys)
        vote = sum(bool(rs[0][k].get("vote_correct")) for k in keys)
        out += ["", f"Vote of 3 evidence-only adjudicator samples (seeds 0, 1, 2) on triple {{0,1,2}}: {100 * ok / len(keys):.1f}% vs the "
                    f"investigators' vote {100 * vote / len(keys):.1f}% over {len(keys)} contests."]
    # plan 005 idea B: both answer orders; where they agree that verdict stands, where they disagree the vote does
    o = [{**rows("mg_adjev_s3"), **rows("mg_adjev_s4")}, {**rows("mg_adjev_sw_s3"), **rows("mg_adjev_sw_s4")}]
    keys = set(o[0]) & set(o[1])
    if keys:
        pick = {k: (o[0][k].get("verdict") if o[0][k].get("verdict") == o[1][k].get("verdict") else o[0][k].get("vote")) for k in keys}
        ok = sum(pick[k] == o[0][k]["good_side"] for k in keys)
        vote = sum(bool(o[0][k].get("vote_correct")) for k in keys)
        con = [k for k in keys if o[0][k].get("contested")]
        agree = sum(o[0][k].get("verdict") == o[1][k].get("verdict") for k in con)
        out += [f"Both answer orders (plan 005 B; disagreement -> the vote): {100 * ok / len(keys):.1f}% vs the vote "
                f"{100 * vote / len(keys):.1f}% over {len(keys)} contests; the two orders agree on {agree} of {len(con)} contested."]
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan004_dev_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
