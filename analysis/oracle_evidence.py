#!/usr/bin/env python3
"""portia/analysis/oracle_evidence.py: how well does the judge do when it is GIVEN the evidence? (local model)

No tools: the judge sees the question, both answers, the answer diff, and frames from the ground-truth evidence
moments (dataset clip_ranges: 3 frames per clip at 25/50/75%, native frames downsized to 768 px, at most 12).
If this scores far above the tool agent, finding the moment is the bottleneck; if not, perception is.

    python analysis/oracle_evidence.py --shards shard1_5pct shard2_10pct shard3_15pct --name q38_oracle
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge import corpus, prompting                        # noqa: E402
from judge.answer_diff import answer_diff                  # noqa: E402
from judge.contests import DATASET, load_contests          # noqa: E402
from judge.local_client import LocalClient                 # noqa: E402

# the prompt is prompts/oracle.j2 (judge/prompting.py)


def frames_for(rec: dict, max_frames: int = 12, side: int = 768) -> list[tuple]:
    out = []
    for cr in rec.get("clip_ranges", []):
        vid, _, a, b = rec[f"chunk_{cr['clip_id']}_filename"][:-4].rsplit("_", 3)
        a, b = int(a), int(b)
        s, e = cr["start_time"], cr["end_time"]
        if e <= (b - a) + 5:
            s, e = a + s, a + e
        for f in (0.25, 0.5, 0.75):
            fr = corpus.frame_at(vid, s + f * (e - s))
            if fr:
                im, t = fr
                sc = side / max(im.size)
                out.append((im.resize((int(im.width * sc), int(im.height * sc))), vid, t, cr.get("qa_reference", "")))
    return out[:max_frames]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", nargs="+", default=["shard1_5pct", "shard2_10pct", "shard3_15pct"])
    ap.add_argument("--name", default="q38_oracle")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--backend", choices=["local", "openrouter"], default="local")
    ap.add_argument("--local-thinking", action="store_true", help="local judge thinks (16k tokens)")
    # plan 009: Muse Glimmer as the oracle judge; the defaults keep the earlier Qwen runs unchanged
    ap.add_argument("--model", default="q38", help="local model name (mg30 = Muse Glimmer)")
    ap.add_argument("--local-url", default="http://127.0.0.1:18650/v1")
    ap.add_argument("--reasoning-strength", default="high", choices=["low", "medium", "high", "xhigh"])
    ap.add_argument("--seed-salt", type=int, default=0, help="an independent sample of every request")
    a = ap.parse_args()
    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    contests = load_contests(a.shards)
    corpus.register(sorted({p for c in contests for p in corpus.domain_playlists(c.domain)}))
    out = ROOT / "runs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    res_p = out / "results.jsonl"
    # rows that failed (provider/transport errors) are re-done on resume
    done = {r["key"] for r in map(json.loads, open(res_p)) if not r["output"].startswith("ERROR")} if res_p.exists() else set()
    if res_p.exists():
        keep = [l for l in open(res_p) if not json.loads(l)["output"].startswith("ERROR")]
        open(res_p, "w").writelines(keep)
    if a.backend == "openrouter":
        from judge.openrouter import Client
        client = Client("nvidia/nemotron-3.5-super-vl:free")
    else:
        client = LocalClient(a.model, a.local_url, thinking=a.local_thinking, strength=a.reasoning_strength, salt=a.seed_salt)

    def one(c):
        if c.key in done:
            return
        fr = frames_for(recs[c.qid])
        listing = "\n".join(f"- image {i + 1}: video {vid} at {corpus.mmss(t)} ({ref[:80]})" for i, (_, vid, t, ref) in enumerate(fr))
        text = prompting.render("oracle.j2", question=c.question, a=c.answer_a, b=c.answer_b,
                                diff=answer_diff(c.answer_a, c.answer_b), frames=listing or "(none)")
        parts = [{"type": "text", "text": text}]
        for im, *_ in fr:
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=88)
            parts.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}})
        t0 = time.time()
        try:
            r = client.chat([{"role": "user", "content": parts}], temperature=0.0, max_tokens=(16384 if a.local_thinking else 4096) if a.backend == "local" else 16384,
                            **({"stream": True} if a.backend == "openrouter" else {}))
            txt = r["choices"][0]["message"].get("content") or ""
        except Exception as e:
            if type(e).__name__ == "QuotaExhausted":         # the daily cap: leave the contest for a later resume
                return
            txt = f"ERROR {type(e).__name__}: {e}"
        m = re.findall(r"VERDICT:\s*\**\s*([AB])\b", txt)
        v = m[-1] if m else None
        row = {"key": c.key, "shard": c.shard, "pair": c.pair, "good_side": c.good_side, "verdict": v,
               "correct": (v == c.good_side) if v else None, "n_frames": len(fr), "wall_s": round(time.time() - t0, 1),
               "output": txt}
        with open(res_p, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, contests))
    rows = [json.loads(l) for l in open(res_p)]
    dec = [r for r in rows if r["verdict"]]
    print(f"{a.name}: {len(rows)} contests · decided {len(dec)} · accuracy {100 * sum(r['correct'] for r in dec) / max(len(rows), 1):.1f}% "
          f"(no-verdict = wrong) · mean frames {sum(r['n_frames'] for r in rows) / max(len(rows), 1):.1f}")


if __name__ == "__main__":
    main()
