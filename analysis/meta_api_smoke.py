#!/usr/bin/env python3
"""portia/analysis/meta_api_smoke.py: does Muse Spark 1.3 Contributor work from here, and what does a request cost?

    python analysis/meta_api_smoke.py

User: "please unlock cap $2" (judge/meta_lock.py dev_key). No benchmark content is sent: the
contributor tier may train on inputs and outputs. Two requests:
  1. a text ping;
  2. three frames of a public YouTube clip ("Me at the zoo", ingested by Portia) with a made-up A/B question, as an
     adjudication-like request, to measure image token billing.
Each response's exact usage is priced at the contributor rates and appended to runs/meta_spend.jsonl; a request is
refused once the logged total reaches the cap.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge import meta_lock  # noqa: E402

SPEND = ROOT / "runs" / "meta_spend.jsonl"
PRICE = {"in": 0.10e-6, "cached": 0.002e-6, "out": 0.20e-6}      # muse-spark-1.3-contributor, dev.meta.ai pricing
CLIP = ROOT / "product" / "collections" / "test_zoo" / "clips" / "jNQXAC9IVRw-0-0-19.mp4"


def spent() -> float:
    return sum(json.loads(l)["usd"] for l in SPEND.read_text().splitlines() if l.strip()) if SPEND.exists() else 0.0


def frames(n: int = 3) -> list[str]:
    from decord import VideoReader, cpu
    from PIL import Image
    vr = VideoReader(str(CLIP), ctx=cpu(0))
    out = []
    for i in [int((k + 0.5) / n * len(vr)) for k in range(n)]:
        im = Image.fromarray(vr[i].asnumpy())
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        out.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    return out


def call(tag: str, messages: list, key: str) -> dict:
    if spent() >= meta_lock.META_DEV_CAP_USD:
        raise SystemExit(f"cap reached: ${spent():.4f} >= ${meta_lock.META_DEV_CAP_USD}")
    url = meta_lock.META_API_URL + "/chat/completions"
    meta_lock.check(url)
    t = time.time()
    r = requests.post(url, timeout=300, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"model": meta_lock.META_DEV_MODEL, "messages": messages, "max_tokens": 2048})
    dt = time.time() - t
    if r.status_code != 200:
        print(f"[{tag}] HTTP {r.status_code} in {dt:.1f}s: {r.text[:500]}")
        return {}
    j = r.json()
    u = j.get("usage") or {}
    pt = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
    ct = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
    cached = int(((u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}).get("cached_tokens")) or 0)
    usd = (pt - cached) * PRICE["in"] + cached * PRICE["cached"] + ct * PRICE["out"]
    with open(SPEND, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": "meta_smoke", "run": tag, "model": j.get("model"),
                            "prompt": pt, "cached": cached, "completion": ct, "usd": round(usd, 8)}) + "\n")
    msg = ((j.get("choices") or [{}])[0].get("message") or {})
    print(f"[{tag}] OK in {dt:.1f}s · model {j.get('model')} · prompt {pt} (cached {cached}) · completion {ct} · ${usd:.6f}")
    print(f"    answer: {(msg.get('content') or '')[:300]!r}")
    if msg.get("reasoning_content") or msg.get("reasoning"):
        print(f"    reasoning returned: {len(msg.get('reasoning_content') or msg.get('reasoning') or '')} chars")
    return {"pt": pt, "ct": ct, "usd": usd}


def main():
    key = meta_lock.dev_key()                                     # never printed
    a = call("ping", [{"role": "user", "content": "Reply with the single word OK."}], key)
    q = ("Two answers describe this short video. Which one matches the frames?\n"
         "A: A young man stands in front of elephants at a zoo and remarks on their long trunks.\n"
         "B: A young man stands in front of giraffes at a zoo and remarks on their long necks.\n"
         "Reply with the letter and one sentence of evidence from the frames.")
    content = [{"type": "text", "text": q}] + [{"type": "image_url", "image_url": {"url": u}} for u in frames(3)]
    b = call("3 frames + question", [{"role": "user", "content": content}], key)
    t = call("question only (no images)", [{"role": "user", "content": q}], key)
    if b and t:
        print(f"image tokens: about {(b['pt'] - t['pt']) / 3:.0f} per frame ({CLIP.name}, native size)")
    print(f"total logged: ${spent():.6f} of the ${meta_lock.META_DEV_CAP_USD:.0f} cap")


if __name__ == "__main__":
    main()
