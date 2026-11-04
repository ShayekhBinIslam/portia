#!/usr/bin/env python3
"""portia/analysis/trust_tiers.py: plan 016: when can a Portia verdict be trusted without a person looking?

    python analysis/trust_tiers.py            # prints the tables; also writes runs/trust_tiers.json for the product

Every verdict reaches Portia by a path: the three investigators agree or split, an adjudicator rules (or re-checks
an agreement), and each investigator either answered on its own or was forced to answer at its turn limit. Each path
has a measured accuracy on the development shards (3-4). Per adjudication mode:
  * glimmer   Portia's default: agreed -> the agreed answer; split -> the Glimmer evidence-only adjudicator
              (5 triples of plans 005-006 plus the GPU queue's 9 later triples, plan 019; Glimmer samples averaged
              within a triple);
  * spark     Muse Spark Open on splits (5 triples, plan 006);
  * spark13   Muse Spark 1.3 on splits (5 triples, plan 013);
  * spark13all Muse Spark 1.3 re-checks every verdict (4 triples, plan 014).
Agreed paths are split by how many investigators were forced to answer (0-1 = they settled it themselves, 2-3 = they
ran out of turns). Output: for each mode, each path's share of cases and accuracy, and the accuracy-coverage curve
when paths are auto-accepted from the most to the least reliable.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = {"t012": (0, 1, 2), "t234": (2, 3, 4), "t345": (3, 4, 5), "t567": (5, 6, 7), "t8910": (8, 9, 10)}
GLIMMER = {"t012": ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_r3", "mg_adjev_r4"],
           "t234": ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"],
           "t345": ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"],
           "t567": ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"],
           "t8910": ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"]}
# plan 019: the GPU queue's later triples, each with its Glimmer adjudication (and a second sample where there is one);
# they add to the glimmer mode only, so the Spark modes stay on the runs they were measured on
EXTRA = {f"t{a}{a + 1}{a + 2}": (a, a + 1, a + 2) for a in (11, 14, 17, 20, 23, 26, 29, 32, 35, 38, 41, 44)}
LABEL = {"agreed_settled": "agreed, and they settled it themselves",
         "agreed_turnlimit": "agreed, but at least two ran out of turns",
         "split_glimmer": "split, ruled by the Glimmer adjudicator", "split_spark": "split, ruled by Spark Open",
         "split_spark13": "split, ruled by Spark 1.3",
         "s13_confirm_settled": "agreed and Spark 1.3 confirmed; they settled it themselves",
         "s13_confirm_turnlimit": "agreed and Spark 1.3 confirmed; at least two ran out of turns",
         "s13_overturn": "agreed, but Spark 1.3 overturned them"}


def rows(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = ROOT / "runs" / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            out.update({json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()})
    return out


def seed(i: int) -> dict:
    return rows("mg_v4t" if i == 0 else f"mg_v4t_r{i}")


def main():
    S = {i: seed(i) for i in range(47)}
    acc = {m: defaultdict(lambda: [0.0, 0.0]) for m in ("glimmer", "spark", "spark13", "spark13all")}   # path -> [right, n]

    def add(mode, path, right, w=1.0):
        acc[mode][path][0] += w * right
        acc[mode][path][1] += w

    for tag, tr in INV.items():
        G = [rows(r) for r in GLIMMER[tag]]
        O, T = rows(f"mg_adjsp_{tag}"), rows(f"mg_adjs13_{tag}")
        A = rows(f"mg_adjs13all_{tag}")
        for k in S[0]:
            inv = [S[i].get(k) for i in tr]
            if not all(inv):
                continue
            good = inv[0]["good_side"]
            v = [x.get("verdict") for x in inv]
            forced = sum(x.get("how") == "forced" for x in inv)
            agreed = len(set(v)) == 1 and v[0] in ("A", "B")
            if agreed:
                p = "agreed_settled" if forced <= 1 else "agreed_turnlimit"
                for m in ("glimmer", "spark", "spark13"):
                    add(m, p, v[0] == good)
            else:
                gs = [g[k]["verdict"] == good for g in G if k in g]
                if gs:
                    add("glimmer", "split_glimmer", sum(gs) / len(gs))
                if k in O:
                    add("spark", "split_spark", O[k]["verdict"] == good)
                if k in T:
                    add("spark13", "split_spark13", T[k]["verdict"] == good)
            if k in A:
                a = A[k]
                if a["contested"]:
                    p = "split_spark13"
                elif a["verdict"] == a["vote"]:
                    p = "s13_confirm_settled" if forced <= 1 else "s13_confirm_turnlimit"
                else:
                    p = "s13_overturn"
                add("spark13all", p, a["verdict"] == good)

    for tag, tr in EXTRA.items():
        G = [g for g in (rows(f"mg_adjev_{tag}"), rows(f"mg_adjev_{tag}_r1")) if g]
        if not G or not all(S[i] for i in tr):
            continue
        for k in S[tr[0]]:
            inv = [S[i].get(k) for i in tr]
            if not all(inv):
                continue
            good = inv[0]["good_side"]
            v = [x.get("verdict") for x in inv]
            forced = sum(x.get("how") == "forced" for x in inv)
            if len(set(v)) == 1 and v[0] in ("A", "B"):
                add("glimmer", "agreed_settled" if forced <= 1 else "agreed_turnlimit", v[0] == good)
            else:
                gs = [g[k]["verdict"] == good for g in G if k in g]
                if gs:
                    add("glimmer", "split_glimmer", sum(gs) / len(gs))

    out = {}
    for mode, paths in acc.items():
        n_all = sum(n for _, n in paths.values())
        if not n_all:
            continue
        ps = sorted(({"path": p, "label": LABEL[p], "share": round(100 * n / n_all, 1), "pct": round(100 * r / n, 1),
                      "n": round(n)} for p, (r, n) in paths.items()), key=lambda x: -x["pct"])
        curve, cr, cn = [], 0.0, 0.0
        for x in ps:
            r, n = paths[x["path"]]
            cr, cn = cr + r, cn + n
            curve.append({"through": x["path"], "coverage": round(100 * cn / n_all, 1), "pct": round(100 * cr / cn, 1)})
        out[mode] = {"n": round(n_all), "overall": round(100 * sum(r for r, _ in paths.values()) / n_all, 1), "paths": ps, "curve": curve}
        print(f"\n## {mode}: {round(n_all)} contest-triples, {out[mode]['overall']}% right overall")
        print("| Path | Share | Right | Auto-accept through here: coverage / accuracy |")
        print("|---|---|---|---|")
        for x, c in zip(ps, curve):
            print(f"| {x['label']} | {x['share']}% | {x['pct']}% | {c['coverage']}% / {c['pct']}% |")
    (ROOT / "runs" / "trust_tiers.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
