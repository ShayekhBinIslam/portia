#!/usr/bin/env python3
"""portia/analysis/pack_coverage.py: plan 009 E2: which opening evidence pack covers the evidence clips? (offline, CPU)

The tuned agent opens with an overview pack: the 64 domain segments that best match question + shared text (tools v4).
Here candidate packs are scored on the development shards (3-4) against the dataset's evidence clips (clip_ranges):
  clip_rec   fraction of a contest's evidence clips with at least one segment in the pack
  all_clips  the pack covers every evidence clip of the contest (both hops)
Packs (64 segments unless noted): v4 (current) · answer A · answer B · A/B union (top 32 of each) · hop-split (question +
first / second half of the shared text, top 32 each) · RRF fusion of all queries · v4 at 96 and 128 segments.

    python analysis/pack_coverage.py          # writes analysis/pack_coverage.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "analysis")]

from judge import corpus                                   # noqa: E402
from judge.answer_diff import retrieval_text, shared_text  # noqa: E402
from judge.contests import load_contests                   # noqa: E402
from judge.embed_client import QueryEncoder               # noqa: E402
from retrieval_queries import clips                        # noqa: E402

SHARDS = ["shard3_15pct", "shard4_20pct"]


def halves(text: str) -> tuple[str, str]:
    """The shared text cut into its two scenes: at a sentence that announces the second one, else at the middle."""
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sents) < 2:
        return text, text
    cue = re.compile(r"\b(second|later|then|transition|subsequent|another|meanwhile|afterward|next)\b", re.I)
    cut = next((i for i, s in enumerate(sents) if i > 0 and cue.search(s)), len(sents) // 2)
    return " ".join(sents[:cut]), " ".join(sents[cut:])


def ranked(E: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.argsort(-(E @ v))


def main():
    contests = load_contests(SHARDS)
    corpus.register(sorted({p for c in contests for p in corpus.domain_playlists(c.domain)}))
    dom = {}
    for d in sorted({c.domain for c in contests}):
        segs = [s for pl in corpus.domain_playlists(d) for s in corpus.index(pl)["segs"]]
        E = np.concatenate([corpus.index(pl)["emb"] for pl in corpus.domain_playlists(d)])
        dom[d] = ([s["handle"] for s in segs], E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12))
    plan, texts = [], set()
    for c in contests:
        sh = shared_text(c.answer_a, c.answer_b)
        h1, h2 = halves(sh)
        q = {"v4": retrieval_text(c.question, c.answer_a, c.answer_b), "A": c.answer_a, "B": c.answer_b,
             "h1": c.question + " " + h1, "h2": c.question + " " + h2}
        plan.append((c, q))
        texts |= set(q.values())
    texts = sorted(texts)
    enc = QueryEncoder(log=lambda *m: None)
    vec = {}
    for i in range(0, len(texts), 32):
        for t, v in zip(texts[i:i + 32], enc.encode(texts[i:i + 32])):
            vec[t] = v / (np.linalg.norm(v) + 1e-12)
        print(f"encoded {min(i + 32, len(texts))}/{len(texts)}", flush=True)
    agg = {}
    for c, q in plan:
        H, E = dom[c.domain]
        cl = clips(c.rec)
        if not cl:
            continue
        r = {k: ranked(E, vec[t]) for k, t in q.items()}

        def top(order, k):
            return [H[i] for i in order[:k]]

        def union(*parts):
            out = []
            for p in parts:
                out += [h for h in p if h not in out]
            return out

        rrf = np.zeros(len(H))
        for o in r.values():
            rrf[o[:400]] += 1.0 / (60 + np.arange(len(o[:400])))
        packs = {"v4 (current) @64": top(r["v4"], 64), "answer A @64": top(r["A"], 64), "answer B @64": top(r["B"], 64),
                 "A/B union 32+32": union(top(r["A"], 32), top(r["B"], 32)),
                 "hop split 32+32": union(top(r["h1"], 32), top(r["h2"], 32)),
                 "v4 32 + hop split 16+16": union(top(r["v4"], 32), top(r["h1"], 16), top(r["h2"], 16)),
                 "RRF fusion @64": [H[i] for i in np.argsort(-rrf)[:64]],
                 "v4 @96": top(r["v4"], 96), "v4 @128": top(r["v4"], 128)}
        for name, pk in packs.items():
            s = set(pk)
            a = agg.setdefault(name, {"n": 0, "size": 0, "clip_rec": 0.0, "all_clips": 0})
            a["n"] += 1
            a["size"] += len(pk)
            got = [bool(s & h) for h in cl]
            a["clip_rec"] += sum(got) / len(got)
            a["all_clips"] += all(got)
    print(f"\n{'pack (dev shards 3-4)':28s} {'n':>4s} {'size':>5s} {'clip recall':>12s} {'all clips':>10s}")
    for name, a in agg.items():
        print(f"{name:28s} {a['n']:4d} {a['size'] / a['n']:5.0f} {100 * a['clip_rec'] / a['n']:11.1f}% {100 * a['all_clips'] / a['n']:9.1f}%")
    (ROOT / "analysis" / "pack_coverage.json").write_text(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
