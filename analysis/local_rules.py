#!/usr/bin/env python3
"""portia/analysis/local_rules.py: plan 019: which fully local (Muse Glimmer only) decision rule is best, judged
across every investigator triple the GPU queue has finished, each triple a replicate (development shards 3-4).

    python analysis/local_rules.py [--split explore|confirm|all]      # prints markdown; writes runs/plan019_rules.md

For each triple with a Glimmer evidence-only adjudication (mg_adjev_<tag>_{s3,s4}, and the second sample _r1 when
there is one), on the contests every run of the triple has finished, it scores:
  vote        majority of the three investigators
  adj         the Glimmer adjudicator rules every split (Portia's local default)
  adj2        two adjudication samples: their verdict when they agree, else the vote
  self-w      on a split, an agent that answered on its own ("tool") outweighs one forced at the turn limit
  looked-w    on a split, an agent that viewed frames outweighs one that did not
  adj+self    the adjudicator on a split, unless its two samples disagree, then self-w
Triples are split in two halves by their order (explore = 1st, 3rd, ...; confirm = 2nd, 4th, ...) so a rule picked on
one half can be checked on the other. Per rule: mean gain over the vote across triples, its spread, and on how many
triples it gains (a sign count), plus the pooled accuracy.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def load(run: str) -> dict:
    out = {}
    for s in ("s3", "s4"):
        p = RUNS / f"{run}_{s}" / "results.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    out[(s, r["key"])] = r
    return out


def triples() -> list[str]:
    """Adjudication tags with both shards finished, in seed order (t012 is mg_adjev itself)."""
    tags = set()
    for d in RUNS.glob("mg_adjev*_s3"):
        m = re.fullmatch(r"mg_adjev(_t\d+)?_s3", d.name)
        if m and (RUNS / d.name.replace("_s3", "_s4") / "summary.json").exists() and (d / "summary.json").exists():
            tags.add(m.group(1) or "")
    def first_seed(t):
        r = load(f"mg_adjev{t}")
        inv = next(iter(r.values()))["investigators"] if r else ["x_r0"]
        m = re.search(r"_r(\d+)_s", inv[0])
        return int(m.group(1)) if m else 0
    return sorted(tags, key=first_seed)


def weighted(verdicts, weights):
    a = sum(w for v, w in zip(verdicts, weights) if v == "A")
    b = sum(w for v, w in zip(verdicts, weights) if v == "B")
    return "A" if a > b else "B" if b > a else None


def score(tag: str) -> dict | None:
    adj, adj1 = load(f"mg_adjev{tag}"), load(f"mg_adjev{tag}_r1")
    if not adj:
        return None
    inv_names = next(iter(adj.values()))["investigators"]
    invs = [load(n.rsplit("_s", 1)[0]) for n in inv_names]
    keys = [k for k in adj if all(k in x for x in invs) and (not adj1 or k in adj1)]
    rules = {r: 0 for r in ("vote", "adj", "adj2", "self-w", "looked-w", "adj+self")}
    n_split = 0
    for k in keys:
        a, good = adj[k], adj[k]["good_side"]
        vote = a["vote"]
        verdicts = [x[k].get("verdict") for x in invs]
        selfw = [1.5 if x[k].get("how") == "tool" else 1.0 for x in invs]
        lookw = [1.5 if (x[k].get("images_viewed") or 0) > 0 else 1.0 for x in invs]
        split = a["contested"]
        n_split += split
        pick = {"vote": vote}
        pick["adj"] = a["verdict"] if split else vote
        if adj1:
            b = adj1[k]["verdict"]
            pick["adj2"] = (a["verdict"] if a["verdict"] == b else vote) if split else vote
            pick["adj+self"] = (a["verdict"] if a["verdict"] == b else (weighted(verdicts, selfw) or vote)) if split else vote
        else:
            pick["adj2"] = pick["adj+self"] = pick["adj"]
        pick["self-w"] = (weighted(verdicts, selfw) or vote) if split else vote
        pick["looked-w"] = (weighted(verdicts, lookw) or vote) if split else vote
        for r in rules:
            rules[r] += pick[r] == good
    n = len(keys)
    return {"tag": tag or "_t012", "n": n, "splits": n_split, "two_samples": bool(adj1),
            "acc": {r: 100 * v / n for r, v in rules.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["explore", "confirm", "all"])
    a = ap.parse_args()
    rows = [r for r in (score(t) for t in triples()) if r and r["n"] >= 200]
    if a.split != "all":
        rows = rows[0::2] if a.split == "explore" else rows[1::2]
    lines = [f"# Plan 019: local decision rules across {len(rows)} investigator triples ({a.split})", "",
             "| Triple | Contests | Splits | 2nd sample | vote | adj | adj2 | self-w | looked-w | adj+self |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r["acc"]
        lines.append(f"| {r['tag'][1:]} | {r['n']} | {r['splits']} | {'yes' if r['two_samples'] else 'no'} | "
                     + " | ".join(f"{c[k]:.1f}" for k in ("vote", "adj", "adj2", "self-w", "looked-w", "adj+self")) + " |")
    lines += ["", "| Rule | Pooled accuracy | Mean gain over the vote | SD across triples | Triples with a gain / loss |",
              "|---|---|---|---|---|"]
    for rule in ("adj", "adj2", "self-w", "looked-w", "adj+self"):
        use = [r for r in rows if rule in ("adj", "self-w", "looked-w") or r["two_samples"]]
        gains = [r["acc"][rule] - r["acc"]["vote"] for r in use]
        pooled = sum(r["acc"][rule] * r["n"] for r in use) / max(1, sum(r["n"] for r in use))
        lines.append(f"| {rule} ({len(use)} triples) | {pooled:.1f} | {statistics.mean(gains):+.2f} | "
                     f"{statistics.pstdev(gains):.2f} | {sum(g > 0 for g in gains)} / {sum(g < 0 for g in gains)} |")
    vote_pooled = sum(r["acc"]["vote"] * r["n"] for r in rows) / max(1, sum(r["n"] for r in rows))
    lines += ["", f"Vote, pooled over all {len(rows)} triples: {vote_pooled:.1f}%."]
    text = "\n".join(lines)
    print(text)
    (RUNS / f"plan019_rules_{a.split}.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
