#!/usr/bin/env python3
"""portia/judge/static_baseline.py: the SAME model WITHOUT tools, on the leaderboard's exact static payload.

Ablation for the tool-using judge: without it, the agent's score cannot be credited to its tools. The
payload is not rebuilt; it is REPLAYED. data/static_payload/<shard>_retrieved_input.jsonl is the verbatim
api/input.jsonl of a final-campaign run on the alpha pod: the campaign rubric (judge_pairwise_notie_html,
forced choice, [[A]]/[[B]]), the transcript and the 128 frames (top-64 retrieved segments x 2, 640x480 JPEG)
every leaderboard judge received, on the same seeded A/B sides. It was copied line by line and md5-verified.
Only the model name changes. Verdicts use the campaign's strict parse_verdict (last [[A]]/[[B]] token wins).

    python -m judge.static_baseline --shard shard1_5pct --name nemotron_static_s1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge.contests import load_contests                 # noqa: E402
from judge.openrouter import Client, QuotaExhausted      # noqa: E402
from judge.run import summarize                          # noqa: E402

VERDICT_TOKEN_RE = re.compile(r"\[\[\s*(A|B|TIE)\s*\]\]", re.I)     # verbatim from the campaign's judge.py


def parse_verdict(text: str) -> str | None:
    tok = VERDICT_TOKEN_RE.findall(text or "")
    if not tok:
        return None
    last = tok[-1].upper()
    return "Tie" if last == "TIE" else last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", default="shard1_5pct")
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", default="nvidia/nemotron-3.5-super-vl:free")
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stream", action="store_true", help="SSE streaming (avoids provider idle timeouts on long generations)")
    ap.add_argument("--backend", choices=["openrouter", "local"], default="openrouter")
    ap.add_argument("--payload", default=None, help="payload JSONL (default: the campaign's data/static_payload/<shard>_retrieved_input.jsonl)")
    ap.add_argument("--local-url", default="http://127.0.0.1:18650/v1")
    ap.add_argument("--local-thinking", action="store_true", help="local backend: let Qwen think (slow)")
    ap.add_argument("--seed-salt", type=int, default=0, help="local Muse: an independent sample of every request (0 = the usual seeds)")
    ap.add_argument("--reasoning-strength", default="high", choices=["low", "medium", "high", "xhigh"],
                    help="Muse Glimmer (local, served as mg*): reasoning strength; --local-thinking keeps it on")
    a = ap.parse_args()

    out = ROOT / "runs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "run.log", "a", buffering=1, encoding="utf-8")

    def log(*m):
        s = " ".join(str(x) for x in m)
        print(s, flush=True)
        logf.write(s + "\n")

    contests = load_contests([a.shard])
    lines = [json.loads(l) for l in (Path(a.payload) if a.payload else ROOT / "data" / "static_payload" / f"{a.shard}_retrieved_input.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    # custom_id "p<index>-gold<A|B>": index = the contest's position in the shard, suffix = the better side
    pairs = []
    for ln in lines:
        m = re.fullmatch(r"p(\d+)-gold([AB])", ln["custom_id"])
        c = contests[int(m.group(1))]
        if c.good_side != m.group(2):
            raise SystemExit(f"{ln['custom_id']}: payload side {m.group(2)} != contest side {c.good_side}")
        pairs.append((c, ln))
    if a.limit:
        pairs = pairs[:a.limit]
    res_p = out / "results.jsonl"
    done = {json.loads(l)["key"] for l in res_p.read_text().splitlines() if l.strip()} if res_p.exists() else set()
    if a.backend == "local":
        from judge.local_client import LocalClient
        a.model = "q38" if a.model == "nvidia/nemotron-3.5-super-vl:free" else a.model
        client = LocalClient(a.model, a.local_url, log=log, thinking=a.local_thinking, strength=a.reasoning_strength,
                             salt=a.seed_salt)
    else:
        client = Client(a.model, log=log)
    log(f"[static] {a.name} · {a.model} · {len(pairs)} contest(s) ({len(done)} done) · payload sides verified "
        f"against the contest rebuild · quota {client.used_today()}/{client.cap_today()}")

    def one(cl):
        c, ln = cl
        if c.key in done:
            return
        msgs = ln["body"]["messages"]
        n_img = sum(1 for p in msgs[0]["content"] if p.get("type") == "image_url")
        t = time.time()
        try:
            for attempt in range(3):              # finish_reason "error" = provider hiccup: retry (not cached)
                r = client.chat(msgs, temperature=0.0, max_tokens=a.max_tokens, **({"stream": True} if a.stream else {}))
                ch = r["choices"][0]
                if ch.get("finish_reason") != "error":
                    break
                time.sleep(20 * (attempt + 1))
            text = (ch.get("message") or {}).get("content") or ""
            reasoning = (ch.get("message") or {}).get("reasoning") or ""
            err, fin, usage = None, ch.get("finish_reason"), r.get("usage")
        except QuotaExhausted as e:
            log(f"[static] quota: {e}")
            return
        except Exception as e:
            text, reasoning, err, fin, usage = "", "", f"{type(e).__name__}: {e}", None, None
        v = parse_verdict(text)
        v = v if v in ("A", "B") else None
        row = {"key": c.key, "qid": c.qid, "pair": c.pair, "occurrence": c.occurrence, "shard": c.shard,
               "domain": c.domain, "gap": c.gap, "good_side": c.good_side, "verdict": v,
               "correct": (v == c.good_side) if v else None, "how": "static" if v else ("error" if err else "unparsed"),
               "steps": 1, "tool_calls": [], "images_viewed": n_img, "wall_s": round(time.time() - t, 1),
               "finish_reason": fin, "usage": usage, "errors": [err] if err else [], "output": text,
               **({"reasoning": reasoning[:20000]} if reasoning else {})}
        with open(res_p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        log(f"[static] {c.domain:11s} {c.pair:22s} good={c.good_side} verdict={v} ({fin}) {row['wall_s']}s "
            f"{n_img} frames" + (f" ERR {err[:160]}" if err else ""))

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, pairs))
    rows = [json.loads(l) for l in res_p.read_text().splitlines() if l.strip()]
    s = {"name": a.name, "model": a.model, "arm": "static (no tools), campaign payload replayed", **summarize(rows),
         "finish_reasons": {f: sum(r["finish_reason"] == f for r in rows) for f in {r["finish_reason"] for r in rows}}}
    (out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    log("[static] summary: " + json.dumps(s))


if __name__ == "__main__":
    main()
