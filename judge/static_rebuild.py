#!/usr/bin/env python3
"""portia/judge/static_rebuild.py: rebuild the static judge's payload with a chosen retrieval query.

The campaign's static payload holds the top-64 segments retrieved by the QUESTION. analysis/retrieval_queries.py
found that the answers' shared text retrieves the evidence far better (evidence clips in the top 64: 29% -> 49%).
This rebuilds the payload line by line, keeping the campaign's prompt text verbatim. Only the
<transcript> block and the 128 frames (2 per segment, 640x480 stretched like the campaign's, detail "low") come from
the chosen retrieval. Mode "question" rebuilds the campaign's own selection with the same code, so a question/shared
comparison differs ONLY in the query.

    python -m judge.static_rebuild --shard shard1_5pct --mode shared      -> data/static_payload_rebuild/<shard>_<mode>.jsonl
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge import corpus, overview                         # noqa: E402
from judge.answer_diff import retrieval_text               # noqa: E402
from judge.contests import load_contests                   # noqa: E402
from judge.embed_client import QueryEncoder                # noqa: E402

OUT = ROOT / "data" / "static_payload_rebuild"


def _resize(im, size: str):
    """640x480 (default): stretched like the campaign's payload. 'native': each frame keeps its own aspect ratio at the
    same pixel budget (~307k px, so about the same number of visual tokens) instead of squashing 16:9 into 4:3."""
    if size == "native":
        w, h = im.size
        sc = (640 * 480 / (w * h)) ** 0.5
        return im.resize((max(1, round(w * sc)), max(1, round(h * sc))))
    W, H = (int(x) for x in size.split("x"))
    return im.resize((W, H))


def build(job: tuple) -> dict:
    line, segs, size = job
    vids, tx, parts = {}, [], []
    for s in segs:
        n = vids.setdefault(s["vid"], len(vids) + 1)
        tx.append(f"[Video {n} @ {corpus.mmss(s['start'])}] {' '.join(corpus.transcript(s).split()) or '(no speech)'}")
        for im, _ in corpus.frames(s, n=2, max_side=1280):
            b = io.BytesIO()
            _resize(im.convert("RGB"), size).save(b, "JPEG", quality=85)
            parts.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode(),
                                                            "detail": "low"}})
    msg = line["body"]["messages"][0]
    text = re.sub(r"<transcript>.*?</transcript>", lambda _: "<transcript>\n" + "\n".join(tx) + "\n</transcript>",
                  msg["content"][0]["text"], count=1, flags=re.S)
    return {"custom_id": line["custom_id"], "segments": [s["handle"] for s in segs],
            "body": {**line["body"], "messages": [{"role": "user", "content": [{"type": "text", "text": text}] + parts}]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", required=True)
    ap.add_argument("--mode", choices=["question", "shared"], required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--size", default="640x480", help="WxH (stretched, the campaign's 640x480) or 'native' (own aspect, same pixel budget)")
    a = ap.parse_args()
    contests = load_contests([a.shard])
    corpus.register(sorted({p for c in contests for p in corpus.domain_playlists(c.domain)}))
    lines = [json.loads(l) for l in open(ROOT / "data" / "static_payload" / f"{a.shard}_retrieved_input.jsonl")]
    enc = QueryEncoder(log=lambda *m: None)
    jobs = []
    for ln in lines:
        c = contests[int(re.fullmatch(r"p(\d+)-gold[AB]", ln["custom_id"]).group(1))]
        q = c.question if a.mode == "question" else retrieval_text(c.question, c.answer_a, c.answer_b)
        segs = overview.segments(enc.encode([q])[0], corpus.domain_playlists(c.domain), k=64)
        jobs.append((ln, [{k: s[k] for k in ("vid", "start", "end", "handle", "dir", "stem")} for s in segs], a.size))
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / (f"{a.shard}_{a.mode}.jsonl" if a.size == "640x480" else f"{a.shard}_{a.mode}_{a.size}.jsonl")
    with ProcessPoolExecutor(a.workers) as ex, open(p, "w") as f:
        for row in ex.map(build, jobs, chunksize=1):
            f.write(json.dumps(row) + "\n")
    print(f"wrote {p} ({len(jobs)} lines)")


if __name__ == "__main__":
    main()
