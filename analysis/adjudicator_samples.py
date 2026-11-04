#!/usr/bin/env python3
"""portia/analysis/adjudicator_samples.py: plan 005: how much of the adjudicator's gain survives sampling noise?

    python analysis/adjudicator_samples.py          # prints markdown; also writes runs/plan005_samples.md

For a configuration with several adjudicator samples (seeds) over the same contests (development shards 3-4), it
reports, against the investigators' vote on the same contests:
  * each sample's gain, and their mean and spread;
  * a vote of k adjudicator samples;
  * a cautious override: keep the investigators' vote unless at least m of the k samples go against it.
Only contests that every listed sample has finished are used, so partial runs are compared like with like.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {
    "evidence-only, triple {0,1,2}": ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_r3", "mg_adjev_r4"],
    # every independent run of the same evidence-only method on triple {0,1,2}: other seeds, another view order, and
    # the answers swapped (its verdicts are already mapped back to the contest's own A/B)
    "evidence-only, triple {0,1,2}, all independent runs": ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_o1",
                                                            "mg_adjev_sw", "mg_adjev_r3", "mg_adjev_r4"],
    "evidence-only, triple {2,3,4}": ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"],
    "evidence-only, replication triple {5,6,7}": ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"],
    "evidence-only, replication triple {3,4,5}": ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"],
    "evidence-only, second fresh triple {8,9,10}": ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"],
    "idea G: evidence-only over divided investigators": ["mg_adjev_tf", "mg_adjev_tf_r1", "mg_adjev_tf_r2"],
    "idea G (replication, seed salt 1): evidence-only over divided investigators": ["mg_adjev_tf1", "mg_adjev_tf1_r1"],
    "evidence-only, five investigators (seeds 0-4)": ["mg_adjev5", "mg_adjev5_r1", "mg_adjev5_r2"],
    "claims rule, triple {0,1,2}": ["mg_adjev_claims", "mg_adjev_claims_r1", "mg_adjev_claims_r2"],
}


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


def shard4_only(label: str, runs: list) -> list[str]:
    """A replication triple whose shard 3 is not ready: its shard-4 samples alone (126 contests)."""
    R = []
    for r in runs:
        p = ROOT / "runs" / f"{r}_s4" / "results.jsonl"
        if p.exists():
            d = {json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}
            if len(d) >= 126:
                R.append((r, d))
    if not R:
        return []
    keys = sorted(set.intersection(*(set(d) for _, d in R)))
    vote = sum(R[0][1][k].get("vote_correct") for k in keys)
    lines = [f"### {label}, shard 4 only ({len(R)} finished samples, {len(keys)} contests; vote {100 * vote / len(keys):.1f}%)", ""]
    gains = []
    for r, d in R:
        g = 100 * (sum(d[k].get("verdict") == d[k]["good_side"] for k in keys) - vote) / len(keys)
        gains.append(g)
        lines.append(f"- {r}: {g:+.1f}")
    if len(R) >= 3:
        ok = 0
        for k in keys:
            c = Counter(d[k].get("verdict") for _, d in R[:3] if d[k].get("verdict") in ("A", "B")).most_common()
            top = c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else R[0][1][k].get("vote")
            ok += top == R[0][1][k]["good_side"]
        lines.append(f"- vote of 3 adjudicator samples: {100 * (ok - vote) / len(keys):+.1f}")
    lines.append(f"- mean of single samples: {statistics.mean(gains):+.1f}")
    return lines + [""]


def main():
    out = ["# Plan 005: adjudicator gains across samples (development shards 3-4)", ""]
    for label, runs in CONFIGS.items():
        named = [(r, rows(r)) for r in runs]
        pending = [f"{r} ({len(x)}/220)" for r, x in named if 0 < len(x) < 220]
        named = [(r, x) for r, x in named if len(x) >= 220]   # only finished samples (both shards); names stay paired
        runs = [r for r, _ in named]
        R = [x for _, x in named]
        if pending:
            out.append(f"<!-- {label}: pending samples {', '.join(pending)} -->")
        if len(R) < 2:
            out += [f"## {label}", "", f"Only {len(R)} finished sample(s) so far" + (f"; pending: {', '.join(pending)}" if pending else "") + ".", ""]
            continue
        keys = sorted(set.intersection(*(set(x) for x in R)))
        n = len(keys)
        good = {k: R[0][k]["good_side"] for k in keys}
        vote = {k: R[0][k].get("vote") for k in keys}
        vote_ok = sum(vote[k] == good[k] for k in keys)
        gains = [100 * (sum(x[k].get("verdict") == good[k] for k in keys) - vote_ok) / n for x in R]
        out += [f"## {label}", "",
                f"{len(R)} finished samples over the same {n} contests; the investigators' vote is right on {100 * vote_ok / n:.1f}%."
                + (f" Pending: {', '.join(pending)}." if pending else ""), "",
                "| Rule | Accuracy | Gain over the vote |", "|---|---|---|"]
        for i, (x, g) in enumerate(zip(R, gains)):
            out.append(f"| sample {i} ({runs[i]}) | {100 * (vote_ok / n) + g:.1f} | {g:+.1f} |")
        out.append(f"| **mean of single samples** | | **{statistics.mean(gains):+.1f}** (sd {statistics.pstdev(gains):.1f}) |")
        k = len(R)
        if k >= 3:
            for kk in sorted({3, k}):
                accs = []
                for combo in combinations(range(k), kk):
                    ok = 0
                    for key in keys:
                        c = Counter(R[i][key].get("verdict") for i in combo if R[i][key].get("verdict") in ("A", "B")).most_common()
                        top = c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else vote[key]
                        ok += top == good[key]
                    accs.append(100 * ok / n)
                out.append(f"| vote of {kk} adjudicator samples (mean over {len(accs)} subsets) | {statistics.mean(accs):.1f} | "
                           f"{statistics.mean(accs) - 100 * vote_ok / n:+.1f} |")
            for m in range(2, k + 1):
                ok = 0
                for key in keys:
                    against = sum(R[i][key].get("verdict") not in (None, vote[key]) for i in range(k))
                    pick = next((R[i][key].get("verdict") for i in range(k) if R[i][key].get("verdict") not in (None, vote[key])), None) \
                        if against >= m else vote[key]
                    ok += pick == good[key]
                out.append(f"| override the vote only if >= {m} of {k} samples go against it | {100 * ok / n:.1f} | "
                           f"{100 * (ok - vote_ok) / n:+.1f} |")
        con = [key for key in keys if R[0][key].get("contested")]
        if con:
            dist = Counter(sum(R[i][key].get("verdict") == good[key] for i in range(k)) for key in con)
            out += ["", f"Contested contests ({len(con)}): how many of the {k} samples are right: "
                        + ", ".join(f"{j}/{k}: {dist.get(j, 0)}" for j in range(k + 1)) + "."]
        out.append("")
    out += ["## Replication triples, shard 4 only (shard 3 waits for seed 7)", ""]
    out += shard4_only("evidence-only, triple {5,6,7}", ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"])
    out += shard4_only("evidence-only, triple {3,4,5}", ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"])
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan005_samples.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
