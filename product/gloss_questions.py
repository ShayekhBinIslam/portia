#!/usr/bin/env python3
"""portia/product/gloss_questions.py: a one-line plain version of every library question, written by Muse Glimmer.

The benchmark's questions are long two-hop riddles written to be hard to search ("Rank the technical sophistication of
the conceptual drawings contained within the bound volume shown during the speech at the tiered seating installation
..."). The app shows this short version first, labelled as Muse Glimmer's, and the full question one click away
(Fable's review). Runs on the local Muse Glimmer servers (scripts/serve_muse.sh); writes product/glosses.json.

    python product/gloss_questions.py [--workers 12] [--force]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402

OUT = HERE / "glosses.json"
PROMPT = """Here is a long question about a video, written to be hard to search. Rewrite it as one short, plain
question a viewer would ask, at most 14 words, keeping the thing it asks about and what has to be found out. Do not
answer it and do not add details. Reply with JSON only: {{"short": "<the short question>"}}

Question: {q}"""


def gloss(q: str, url: str) -> str | None:
    body = {"model": "mg30", "messages": [{"role": "user", "content": PROMPT.format(q=q)}], "max_tokens": 1200,
            "temperature": 1.0, "top_p": 0.95, "top_k": 64, "seed": random.randint(0, 10**6),   # Muse must not run greedy
            "chat_template_kwargs": {"reasoning_strength": "low"}}
    for _ in range(4):
        try:
            r = requests.post(url, json=body, timeout=180)
            text = (r.json()["choices"][0]["message"].get("content") or "").strip()
            m = re.search(r'"short"\s*:\s*"([^"]{8,160})"', text)
            if m and len(m.group(1).split()) <= 18:
                return m.group(1).strip()
        except (requests.RequestException, KeyError, ValueError):
            time.sleep(2)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    have = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() and not a.force else {}
    todo = [(cid, c.question) for cid, c in E.library().items() if cid not in have]
    urls = [f"{u}/chat/completions" for u, _ in E.SERVERS]
    print(f"{len(todo)} questions to shorten on {len(urls)} Muse Glimmer servers", flush=True)

    def one(k_item):
        k, (cid, q) = k_item
        return cid, gloss(q, urls[k % len(urls)])

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for n, (cid, g) in enumerate(pool.map(one, enumerate(todo)), 1):
            if g:
                have[cid] = g
            if n % 20 == 0 or n == len(todo):
                OUT.write_text(json.dumps(have, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
                print(f"{n}/{len(todo)} done, {len(have)} shortened", flush=True)
    OUT.write_text(json.dumps(have, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
