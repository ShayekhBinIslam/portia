#!/usr/bin/env python3
"""portia/analysis/retrieval_queries.py: which query finds the evidence moments? (offline; pod query encoder only)

The oracle test says the judge decides ~90% right when it is shown the evidence frames, so localisation is the
lever. The judge's search scope is the contest's whole DOMAIN (every playlist). For each contest this ranks all
domain segments by several queries built only from what the judge sees, and scores:
  hit@8      an evidence segment among the top 8 (the initial evidence list)
  clip_rec@64  fraction of the ground-truth evidence clips with a segment in the top 64 (the static/overview pack)
Queries: the question · answer A · the text both answers share (the disputed details removed) · question + shared
text · per-sentence multi-query (each sentence of the shared text, results merged by best rank).
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from judge import corpus                               # noqa: E402
from judge.contests import DATASET, load_contests      # noqa: E402
from judge.embed_client import QueryEncoder            # noqa: E402

SH = ["shard1_5pct", "shard2_10pct", "shard3_15pct"]


def shared_text(a: str, b: str) -> str:
    wa, wb = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    return " ".join(" ".join(wa[i1:i2]) for op, i1, i2, _, _ in sm.get_opcodes() if op == "equal")


def clips(rec: dict) -> list[set]:
    out = []
    for cr in rec.get("clip_ranges", []):
        vid, _, a, b = rec[f"chunk_{cr['clip_id']}_filename"][:-4].rsplit("_", 3)
        a, b = int(a), int(b)
        s, e = cr["start_time"], cr["end_time"]
        if e <= (b - a) + 5:
            s, e = a + s, a + e
        hs = {f"{vid}@{t}" for t in range(int(s // 30) * 30, int(e), 30) if corpus.segment(f"{vid}@{t}")}
        if hs:
            out.append(hs)
    return out


def main():
    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    contests = load_contests(SH)
    corpus.register(sorted({p for c in contests for p in corpus.domain_playlists(c.domain)}))
    enc = QueryEncoder(log=lambda *m: None)
    dom = {}
    for d in sorted({c.domain for c in contests}):
        segs = [s for pl in corpus.domain_playlists(d) for s in corpus.index(pl)["segs"]]
        E = np.concatenate([corpus.index(pl)["emb"] for pl in corpus.domain_playlists(d)])
        dom[d] = ([s["handle"] for s in segs], E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12))
    plan, texts = [], set()
    for c in contests:
        sh = shared_text(c.answer_a, c.answer_b)
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", sh) if len(s.split()) >= 6][:8]
        q = {"question": [c.question], "answer A": [c.answer_a], "shared text": [sh],
             "question + shared": [c.question + " " + sh], "per-sentence (shared)": sents or [sh]}
        plan.append((c, q))
        texts |= {t for v in q.values() for t in v}
    texts = sorted(texts)
    vec = {}
    for i in range(0, len(texts), 64):
        for t, v in zip(texts[i:i + 64], enc.encode(texts[i:i + 64])):
            vec[t] = v / (np.linalg.norm(v) + 1e-12)
    agg = {}
    for c, q in plan:
        H, E = dom[c.domain]
        cl = clips(recs[c.qid])
        if not cl:
            continue
        ev = set().union(*cl)
        for name, qs in q.items():
            if len(qs) == 1:
                order = np.argsort(-(E @ vec[qs[0]]))
            else:                                         # multi-query: each segment keeps its best rank
                best = np.full(len(H), 10 ** 9)
                for t in qs:
                    o = np.argsort(-(E @ vec[t]))[:200]
                    best[o] = np.minimum(best[o], np.arange(len(o)))
                order = np.argsort(best)
            top8, top64 = {H[i] for i in order[:8]}, {H[i] for i in order[:64]}
            r = agg.setdefault(name, {"n": 0, "hit8": 0, "clip_rec64": 0.0, "hit64": 0})
            r["n"] += 1
            r["hit8"] += bool(top8 & ev)
            r["hit64"] += bool(top64 & ev)
            r["clip_rec64"] += sum(bool(top64 & h) for h in cl) / len(cl)
    print(f"{'query (domain-wide search)':26s} {'n':>4s} {'hit@8':>7s} {'any@64':>7s} {'clip recall@64':>15s}")
    for name, r in agg.items():
        print(f"{name:26s} {r['n']:4d} {100 * r['hit8'] / r['n']:6.1f}% {100 * r['hit64'] / r['n']:6.1f}% {100 * r['clip_rec64'] / r['n']:14.1f}%")
    (ROOT / "analysis" / "retrieval_queries.json").write_text(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
