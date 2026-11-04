#!/usr/bin/env python3
"""portia/analysis/unanimous_report.py: when all three investigators agree on the WRONG answer (development shards 3-4).

    python analysis/unanimous_report.py

  1. How often the three agree, and how often they agree on the wrong answer, pooled over the five investigator
     triples of Portia's Proof page (8 turns, high), with the share of the pipeline's remaining errors this causes.
  2. Is a unanimous wrong verdict bad luck or the case itself? For each contest, the share of the 12 investigator
     seeds (mg_v4t, mg_v4t_r1 ... r11) that get it right.
  3. Can an adjudicator overturn it? mg_adjev_all_* ran the Glimmer evidence-only adjudicator on EVERY contest of
     triple {0,1,2} (plan 005 diagnostic): on unanimous contests, how many wrong verdicts it fixed and right ones it broke.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIPLES = {"{0,1,2}": (0, 1, 2), "{2,3,4}": (2, 3, 4), "{3,4,5}": (3, 4, 5), "{5,6,7}": (5, 6, 7), "{8,9,10}": (8, 9, 10)}
SPLIT_RIGHT = {"vote": 57.8, "Glimmer": 62.6, "Spark 1.3": 76.6, "Spark Open": 83.0}     # Proof page, 282 splits


def rows(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = ROOT / "runs" / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            out.update({json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()})
    return out


def main():
    seeds = {i: rows("mg_v4t" if i == 0 else f"mg_v4t_r{i}") for i in range(12)}
    keys = sorted(set.intersection(*(set(r) for r in seeds.values())))
    good = {k: seeds[0][k]["good_side"] for k in keys}
    p_right = {k: sum(seeds[i][k].get("verdict") == good[k] for i in seeds) / len(seeds) for k in keys}

    # 1. agreement over the five triples
    n = agree = agree_wrong = 0
    uw_keys = Counter()
    for name, tr in TRIPLES.items():
        for k in keys:
            v = [seeds[i][k].get("verdict") for i in tr]
            n += 1
            if len(set(v)) == 1 and v[0] in ("A", "B"):
                agree += 1
                if v[0] != good[k]:
                    agree_wrong += 1
                    uw_keys[k] += 1
    split = n - agree
    print(f"## 1. Agreement ({n} contest-triples: 5 triples x {len(keys)} contests)\n")
    print(f"- All three agree: {100 * agree / n:.1f}% of cases; right {100 * (agree - agree_wrong) / agree:.1f}% of those.")
    print(f"- **All three agree on the WRONG answer: {100 * agree_wrong / n:.1f}% of all cases** "
          f"({agree_wrong} of {n}).")
    print(f"- Split: {100 * split / n:.1f}% of cases.\n")
    print("| Adjudicator on splits | Pipeline errors | from unanimous-wrong | from splits | unanimous-wrong share of errors |")
    print("|---|---|---|---|---|")
    uw = 100 * agree_wrong / n
    for name, r in SPLIT_RIGHT.items():
        se = 100 * split / n * (1 - r / 100)
        print(f"| {name} | {uw + se:.1f}% | {uw:.1f} | {se:.1f} | {100 * uw / (uw + se):.0f}% |")

    # 2. luck or the case?
    print(f"\n## 2. Unanimous-wrong cases: bad luck or the case itself?\n")
    ks = list(uw_keys)
    hist = Counter(round(12 * p_right[k]) for k in ks)
    print(f"- {len(ks)} distinct contests were unanimously wrong in at least one triple.")
    print(f"- Seeds (of 12) that get those contests right: " + ", ".join(f"{h}: {hist[h]}" for h in sorted(hist)))
    hard = sum(1 for k in ks if p_right[k] <= 3 / 12)
    print(f"- {hard} of them ({100 * hard / len(ks):.0f}%) are right for at most 3 of 12 seeds: the case itself fools Glimmer.")
    exp = sum(5 * (1 - p_right[k]) ** 3 for k in keys)
    print(f"- If seeds erred independently at each contest's own rate, expect {exp:.0f} unanimous-wrong contest-triples; "
          f"observed {agree_wrong}.")
    dom = Counter(seeds[0][k]["domain"] for k in ks)
    print("- By domain: " + ", ".join(f"{d} {c}" for d, c in dom.most_common()))

    # 3. can an adjudicator overturn a unanimous verdict?
    A = rows("mg_adjev_all")
    fixed = broken = kept_r = kept_w = 0
    for k, a in A.items():
        v = a.get("inv_verdicts") or []
        if len(set(v)) != 1:
            continue
        right_before = v[0] == a["good_side"]
        right_after = a.get("verdict") == a["good_side"]
        if right_before and right_after:
            kept_r += 1
        elif right_before:
            broken += 1
        elif right_after:
            fixed += 1
        else:
            kept_w += 1
    tot = fixed + broken + kept_r + kept_w
    print(f"\n## 3. Glimmer adjudicator on unanimous contests (triple {{0,1,2}}, mg_adjev_all, {tot} contests)\n")
    print(f"- Unanimous right: {kept_r + broken} -> it broke {broken}.")
    print(f"- Unanimous wrong: {fixed + kept_w} -> it fixed {fixed}.")
    print(f"- Net: {fixed - broken:+d} contests ({100 * (fixed - broken) / max(tot, 1):+.1f} points on the unanimous cases).")


if __name__ == "__main__":
    main()
