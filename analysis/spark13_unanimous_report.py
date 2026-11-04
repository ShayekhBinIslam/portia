#!/usr/bin/env python3
"""portia/analysis/spark13_unanimous_report.py: plan 014: can Muse Spark 1.3 overturn a unanimous wrong verdict?

    python analysis/spark13_unanimous_report.py      # prints markdown; also writes runs/plan014_report.md

Per investigator triple (development shards 3-4), on the contests the Spark 1.3 --all run has finished
(mg_adjs13all_<triple>_*):
  * unanimous contests: wrong verdicts Spark 1.3 fixes and right ones it breaks, overall and split by a free risk flag
    (all three investigators were forced to answer: they used every turn);
  * pipeline accuracy for: the vote; Spark 1.3 on splits only (plan 013's design); Spark 1.3 on splits plus the flagged
    unanimous contests; Spark 1.3 on every contest;
  * triple {0,1,2} also has the Glimmer evidence-only adjudicator on every contest (mg_adjev_all, plan 005);
  * cost per unanimous adjudication (runs/meta_spend.jsonl, tag plan014_unan).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIPLES = [("{0,1,2}", "t012", ("mg_v4t", "mg_v4t_r1", "mg_v4t_r2"), "selection"),
           ("{5,6,7}", "t567", ("mg_v4t_r5", "mg_v4t_r6", "mg_v4t_r7"), "fresh"),
           ("{8,9,10}", "t8910", ("mg_v4t_r8", "mg_v4t_r9", "mg_v4t_r10"), "fresh"),
           ("{3,4,5}", "t345", ("mg_v4t_r3", "mg_v4t_r4", "mg_v4t_r5"), "shares seeds")]
DESIGNS = ["vote", "splits", "splits+forced", "all"]


def rows(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = ROOT / "runs" / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            out.update({json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()})
    return out


def tally(keys, adj, base) -> dict:
    t = {"right": 0, "wrong": 0, "fixed": 0, "broken": 0}
    for k in keys:
        before = base[k]["vote"] == base[k]["good_side"]
        after = adj[k].get("verdict") == adj[k]["good_side"]
        t["right" if before else "wrong"] += 1
        t["fixed"] += (not before) and after
        t["broken"] += before and not after
    return t


def triple_stats(tag: str, inv_runs) -> dict | None:
    S = rows(f"mg_adjs13all_{tag}")
    inv = [rows(r) for r in inv_runs]
    keys = [k for k in S if all(k in x for x in inv)]
    if not keys:
        return None
    forced = {k: all(x[k].get("how") == "forced" for x in inv) for k in keys}
    un = [k for k in keys if not S[k]["contested"]]
    pick = {"vote": lambda k: S[k]["vote"],
            "splits": lambda k: S[k]["verdict"] if S[k]["contested"] else S[k]["vote"],
            "splits+forced": lambda k: S[k]["verdict"] if S[k]["contested"] or forced[k] else S[k]["vote"],
            "all": lambda k: S[k]["verdict"]}
    calls = {"vote": 0, "splits": len(keys) - len(un), "splits+forced": len(keys) - len(un) + sum(forced[k] for k in un),
             "all": len(keys)}
    out = {"n": len(keys), "un": tally(un, S, S), "forced": tally([k for k in un if forced[k]], S, S),
           "rest": tally([k for k in un if not forced[k]], S, S),
           "right": {d: sum(pick[d](k) == S[k]["good_side"] for k in keys) for d in DESIGNS}, "calls": calls,
           "full": all((ROOT / "runs" / f"mg_adjs13all_{tag}_{s}" / "summary.json").exists() for s in ("s3", "s4"))}
    if tag == "t012":
        G = rows("mg_adjev_all")
        gk = [k for k in un if k in G]
        out["glimmer_un"] = tally(gk, G, S)
    return out


def main():
    spend = [json.loads(l) for l in (ROOT / "runs" / "meta_spend.jsonl").read_text().splitlines() if l.strip()]
    usd = sum(r["usd"] for r in spend if r.get("tag") == "plan014_unan")
    st = {label: (rel, triple_stats(tag, inv)) for label, tag, inv, rel in TRIPLES}
    st = {k: v for k, v in st.items() if v[1]}
    out = ["# Plan 014: Muse Spark 1.3 Contributor on unanimous contests (development shards 3-4)", "",
           "## Unanimous contests: wrong verdicts fixed / right verdicts broken", "",
           "| Triple | Relation | Unanimous (wrong) | Spark 1.3 fixed / broken (net) | All three forced: fixed / broken | The rest: fixed / broken |",
           "|---|---|---|---|---|---|"]
    pool = {"un": {"right": 0, "wrong": 0, "fixed": 0, "broken": 0}, "forced": {"right": 0, "wrong": 0, "fixed": 0, "broken": 0},
            "rest": {"right": 0, "wrong": 0, "fixed": 0, "broken": 0}, "n": 0, "right": {d: 0 for d in DESIGNS},
            "calls": {d: 0 for d in DESIGNS}}
    for label, (rel, s) in st.items():
        u, f, r = s["un"], s["forced"], s["rest"]
        out.append(f"| {label}{'' if s['full'] else ' (partial)'} | {rel} | {u['right'] + u['wrong']} ({u['wrong']}) | "
                   f"{u['fixed']} / {u['broken']} (**{u['fixed'] - u['broken']:+d}**) | {f['fixed']} / {f['broken']} | {r['fixed']} / {r['broken']} |")
        for part in ("un", "forced", "rest"):
            for k in pool[part]:
                pool[part][k] += s[part][k]
        pool["n"] += s["n"]
        for d in DESIGNS:
            pool["right"][d] += s["right"][d]
            pool["calls"][d] += s["calls"][d]
    u, f, r = pool["un"], pool["forced"], pool["rest"]
    out.append(f"| **All** | | {u['right'] + u['wrong']} ({u['wrong']}) | {u['fixed']} / {u['broken']} (**{u['fixed'] - u['broken']:+d}**) | "
               f"{f['fixed']} / {f['broken']} | {r['fixed']} / {r['broken']} |")
    if "{0,1,2}" in st and "glimmer_un" in st["{0,1,2}"][1]:
        g = st["{0,1,2}"][1]["glimmer_un"]
        out += ["", f"Glimmer evidence-only adjudicator on the same unanimous contests of {{0,1,2}}: fixed {g['fixed']}, broke {g['broken']} "
                    f"(net {g['fixed'] - g['broken']:+d})."]
    out += ["", "## Pipeline accuracy", "",
            "| Triple | Contests | Vote | Spark 1.3 on splits only | + on unanimous where all three were forced | on every contest |",
            "|---|---|---|---|---|---|"]
    for label, (rel, s) in st.items():
        n = s["n"]
        out.append(f"| {label} | {n} | " + " | ".join(f"{100 * s['right'][d] / n:.1f}%" for d in DESIGNS) + " |")
    n = pool["n"]
    out.append(f"| **All** | {n} | " + " | ".join(f"**{100 * pool['right'][d] / n:.1f}%**" for d in DESIGNS) + " |")
    out.append(f"| Spark 1.3 calls per contest | | " + " | ".join(f"{pool['calls'][d] / n:.2f}" for d in DESIGNS) + " |")
    nu = u["right"] + u["wrong"]
    out += ["", f"Cost of the unanimous adjudications so far: ${usd:.3f} (${usd / max(nu, 1):.4f} each)."]
    text = "\n".join(out) + "\n"
    (ROOT / "runs" / "plan014_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
