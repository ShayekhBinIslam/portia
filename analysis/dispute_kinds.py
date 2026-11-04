#!/usr/bin/env python3
"""portia/analysis/dispute_kinds.py: plan 019: how right Portia is by what the two answers disagree about.

    python analysis/dispute_kinds.py        # prints markdown; writes runs/dispute_kinds.json for the Proof page

Kinds come from product/engine.dispute_kind (quoted or on-screen text, counts, colours, positions, objects). Per kind:
its share of the 220 development cases, the local jury (Glimmer adjudicator on splits) over every investigator triple
with a Glimmer adjudication (14), the local "agreed on their own" path, and Muse Spark 1.3 checking every verdict over
the 4 triples of plan 014 (same contests, same investigators).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "product")); sys.path.insert(0, str(ROOT / "analysis"))
import engine as E          # noqa: E402
import local_rules as L     # noqa: E402

S13 = {"t012": "mg_adjev", "t345": "mg_adjev_t345", "t567": "mg_adjev_t567", "t8910": "mg_adjev_t8910"}
ORDER = ["object", "colour", "count", "position", "text"]
LABEL = {"object": "objects and other details", "colour": "colours", "count": "numbers and counts",
         "position": "where things are", "text": "words on screen"}


def main():
    lib = E.library()
    kind = {c.key: E.dispute_kind(c.answer_a, c.answer_b) for c in lib.values()}
    share = Counter(kind.values())
    loc, settled, contests = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(set)
    for t in L.triples():
        adj = L.load(f"mg_adjev{t}")
        invs = [L.load(n.rsplit("_s", 1)[0]) for n in next(iter(adj.values()))["investigators"]]
        for k, a in adj.items():
            if not all(k in x for x in invs):
                continue
            c, ok = kind[k[1]], a["verdict"] == a["good_side"]
            loc[c][0] += ok; loc[c][1] += 1
            if not a["contested"] and sum(x[k].get("how") == "forced" for x in invs) <= 1:
                settled[c][0] += ok; settled[c][1] += 1; contests[c].add(k[1])
    sp = defaultdict(lambda: [0, 0])
    for tag, g in S13.items():
        A, G = L.load(f"mg_adjs13all_{tag}"), L.load(g)
        for k, a in A.items():
            if k in G:
                sp[kind[k[1]]][0] += a["verdict"] == a["good_side"]; sp[kind[k[1]]][1] += 1
    pct = lambda x: round(100 * x[0] / x[1], 1) if x[1] else None       # noqa: E731
    rows = [{"kind": c, "label": LABEL[c], "share": round(100 * share[c] / len(lib), 1), "local": pct(loc[c]),
             "local_settled": pct(settled[c]), "settled_contests": len(contests[c]), "spark13all": pct(sp[c])} for c in ORDER]
    out = {"rows": rows, "triples_local": len(L.triples()), "triples_spark13all": len(S13), "cases": len(lib)}
    (ROOT / "runs" / "dispute_kinds.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    # plan 019 E3: the same kinds by contest key, for judge/adjudicate.py --kind-notes (no product import there)
    (ROOT / "runs" / "dispute_kind_by_key.json").write_text(json.dumps(kind, indent=0, ensure_ascii=False), encoding="utf-8")
    print("| What the answers disagree about | Share | Local jury | Local, agreed on their own | Spark 1.3 checking all |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['label']} | {r['share']}% | {r['local']}% | {r['local_settled']}% ({r['settled_contests']} contests) | {r['spark13all']}% |")


if __name__ == "__main__":
    main()
