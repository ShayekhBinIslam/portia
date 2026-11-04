#!/usr/bin/env python3
"""portia/judge/replay_check.py: 0-quota check that a finished run replays byte-exactly from the response cache.

    python -m judge.replay_check --run nemotron_s2 --shard shard2_10pct --extend 8 --out nemotron_s2_ext8

Every contest of --run is re-judged with all network calls refused (OpenRouter and the pod encoder). A contest
that answered within the budget must reproduce its verdict, steps and tool calls. A forced one must first miss
the cache exactly at the budget step, which is where an --extend run starts sending. Anything else means the
replay diverged, and the extension would not be "the original agent plus extra turns".
Writes runs/<out>/replay_check.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge.agent import judge                        # noqa: E402
from judge.contests import load_contests             # noqa: E402
from judge.embed_client import QueryEncoder          # noqa: E402
from judge.openrouter import Client                  # noqa: E402
from judge.run import MODEL                          # noqa: E402


class CacheOnlyClient:
    """The real Client's request hashing, with no keys and no network: every call is cache_only."""

    def __init__(self, model: str):
        self._c = Client.__new__(Client)              # skip __init__: it contacts OpenRouter for key info
        self._c.model, self._c.cached, self._c.sent = model, 0, 0

    def chat(self, messages, **kw):
        return Client.chat(self._c, messages, cache_only=True, **kw)


def _offline_ensure():
    raise RuntimeError("EncoderMiss: query not in the local cache (replay would have to call the encoder)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--shard", required=True)
    ap.add_argument("--out", required=True, help="the extension run this check vouches for")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--extend", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    orig = {r["key"]: r for r in map(json.loads, (ROOT / "runs" / a.run / "results.jsonl").read_text().splitlines())
            if r["shard"] == a.shard}
    contests = [c for c in load_contests([a.shard]) if c.key in orig]
    enc = QueryEncoder(log=lambda *m: None)
    enc.ensure = _offline_ensure
    client = CacheOnlyClient(MODEL)
    sig = lambda calls: [(c["tool"], c["args"]) for c in calls]          # noqa: E731

    def one(c):
        o = orig[c.key]
        try:
            r = judge(c, client, enc, max_steps=a.max_steps, extend=a.extend, log=lambda *m: None)
        except Exception as e:
            return {"key": c.key, "orig_how": o["how"], "ok": False, "why": f"{type(e).__name__}: {e}"[:200]}
        miss = bool(r["errors"]) and r["errors"][0].startswith("CacheMiss")
        if o["how"] == "forced":
            ok = miss and r["steps"] == a.max_steps and sig(r["tool_calls"]) == sig(o["tool_calls"])
            why = "" if ok else f"steps {r['steps']} errors {r['errors'][:1]}"
        else:
            ok = (not r["errors"] and r["verdict"] == o["verdict"] and r["steps"] == o["steps"]
                  and sig(r["tool_calls"]) == sig(o["tool_calls"]))
            why = "" if ok else f"verdict {r['verdict']} vs {o['verdict']} · steps {r['steps']} vs {o['steps']} · errors {r['errors'][:1]}"
        return {"key": c.key, "orig_how": o["how"], "ok": ok, "why": why[:300]}

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(one, contests))
    bad = [r for r in res if not r["ok"]]
    s = {"run": a.run, "shard": a.shard, "extend": a.extend, "n": len(res),
         "replayed_exactly": sum(r["ok"] and r["orig_how"] != "forced" for r in res),
         "forced_diverge_exactly_at_budget": sum(r["ok"] and r["orig_how"] == "forced" for r in res),
         "mismatches": bad, "openrouter_cache_hits": client._c.cached, "pod_calls": enc.pod_calls}
    out = ROOT / "runs" / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "replay_check.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in s.items() if k != "mismatches"}), f"· {len(bad)} mismatch(es)")
    for r in bad:
        print("  MISMATCH", r)


if __name__ == "__main__":
    main()
