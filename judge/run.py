#!/usr/bin/env python3
"""portia/judge/run.py: run the tool-using judge over final-campaign contests.

    python -m judge.run --shard shard1_5pct --limit 3 --name smoke     # 3 contests, live model
    python -m judge.run --shard shard1_5pct --limit 1 --dry            # scripted model: tests tools, 0 quota
    python -m judge.run --name smoke                                   # resume: skips contests already judged

Outputs runs/<name>/: results.jsonl (one row per contest), trajectories/<n>.json (full conversation without
image bytes), summary.json (the leaderboard's metrics: raw + balanced accuracy, position bias, no-verdict),
run.log. Resumable by design: the free tier stops a run at 50 requests/day, and the next day picks it up.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge.agent import judge                       # noqa: E402
from judge.contests import load_contests            # noqa: E402
from judge.embed_client import QueryEncoder         # noqa: E402
from judge.openrouter import Client, QuotaExhausted  # noqa: E402

from judge.config import load as _config  # noqa: E402
MODEL = _config("models")["openrouter"]["model"]


class ScriptedClient:
    """No network: replays a fixed tool plan so the tools, pod encoder and logging can be tested for free."""
    sent = cached = 0
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def __init__(self, contest):
        q = contest.question.split("?")[0][:80]
        self.plan = [("search", {"query": q, "k": 4}), ("grep_transcripts", {"pattern": "the", "max_hits": 3}),
                     ("read_transcript", {"handles": [], "context": 1}), ("view_frames", {"handle": "", "n": 2}),
                     ("answer", {"verdict": "A", "rationale": "scripted dry run"})]
        self.i = 0

    def chat(self, messages, tools=None, tool_choice=None, **kw):
        name, args = self.plan[min(self.i, len(self.plan) - 1)]
        if name in ("read_transcript", "view_frames"):     # reuse a handle from the last tool output
            import re
            prior = [m for m in messages if m.get("role") == "tool"]
            h = re.findall(r"- (\S+@\d+) \|", prior[0]["content"] if prior else "") or ["?@0"]
            args = {**args, ("handles" if name == "read_transcript" else "handle"): ([h[0]] if name == "read_transcript" else h[0])}
        self.i += 1
        return {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": f"call_{self.i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}],
            "usage": {}, "_latency_s": 0.0}


def summarize(rows: list[dict]) -> dict:
    dec = [r for r in rows if r["verdict"] in ("A", "B")]
    acc = lambda rs: round(100 * sum(r["correct"] for r in rs) / len(rs), 2) if rs else None   # noqa: E731
    a_good, b_good = [r for r in dec if r["good_side"] == "A"], [r for r in dec if r["good_side"] == "B"]
    bal = round((acc(a_good) + acc(b_good)) / 2, 2) if a_good and b_good else None
    tools = {}
    for r in rows:
        for c in r["tool_calls"]:
            tools[c["tool"]] = tools.get(c["tool"], 0) + 1
    return {"n": len(rows), "decided": len(dec), "no_verdict": len(rows) - len(dec),
            "raw_acc_pct": acc(dec), "balanced_pct": bal,
            "posA": round(sum(r["verdict"] == "A" for r in dec) / len(dec), 3) if dec else None,
            "mean_steps": round(sum(r["steps"] for r in rows) / len(rows), 2) if rows else None,
            "mean_images": round(sum(r["images_viewed"] for r in rows) / len(rows), 2) if rows else None,
            "tool_calls": tools, "how": {h: sum(r["how"] == h for r in rows) for h in {r["how"] for r in rows}},
            "mean_wall_s": round(sum(r["wall_s"] for r in rows) / len(rows), 1) if rows else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", action="append", help="shard name(s); default shard1_5pct")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-pos", default="", help="comma-separated contest positions within the shard (smoke tests)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--backend", choices=["openrouter", "local", "baseten", "meta"], default="openrouter",
                    help="local: the vLLM server of scripts/serve_local_judge.sh (no quota)")
    ap.add_argument("--local-url", default="http://127.0.0.1:18650/v1")
    ap.add_argument("--budget-usd", type=float, default=3.0,
                    help="baseten: new requests stop once the spend logged under --budget-tag reaches this (plan 007)")
    ap.add_argument("--budget-tag", default="", help="baseten: the spend group (default: the run name)")
    ap.add_argument("--local-thinking", action="store_true", help="local backend: let Qwen think (slow)")
    ap.add_argument("--reasoning-strength", default="high", choices=["low", "medium", "high", "xhigh"],
                    help="Muse Glimmer (local, served as mg*): reasoning strength; --local-thinking keeps it on")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=4096, help="per turn; thinking runs need ~16k")
    ap.add_argument("--keep-images", type=int, default=12,
                    help="images kept in context; = max images (24) never prunes, so local prefix caching works")
    ap.add_argument("--max-images", type=int, default=24, help="images the tools may return per contest (24 = 3 per turn at 8 turns)")
    ap.add_argument("--seed-salt", type=int, default=0, help="local Muse: an independent sample of every request (0 = the usual seeds)")
    ap.add_argument("--swap", action="store_true", help="exchange answers A and B in every contest (position bias)")
    ap.add_argument("--look-first", action="store_true", help="look-first prompt (prompts/system_v4look.md) + a search/look tally after each turn")
    ap.add_argument("--inspect", action="store_true", help="after each zoom/burst, an independent look in a fresh context (local vLLM only)")
    ap.add_argument("--tools", default="v1", choices=["v1", "v2", "v3", "v4", "v5"], help="v2: + search_video/contact_sheet/zoom, answer diff, system_v2.md; v3: v2 + overview pack")
    ap.add_argument("--redo-noverdict", action="store_true", help="judge again the contests whose row has no verdict (old rows kept aside)")
    ap.add_argument("--zoom-side", type=int, default=1024, help="zoom output size (long side, px); != 1024 also swaps in the hi-res zoom description")
    ap.add_argument("--budget-note", action="store_true", help="tell the model after each tool turn how many turns are left")
    ap.add_argument("--look-around", action="store_true", help="plan 019: with two turns left, check a minute around the key moment")
    ap.add_argument("--final-full-reasoning", action="store_true", help="the forced final answer keeps the run's reasoning strength (not low)")
    ap.add_argument("--keep-reasoning", action="store_true", help="send each turn's reasoning back in the history (interleaved thinking)")
    ap.add_argument("--extend", type=int, default=0, help="extra turns granted at the budget instead of forcing")
    ap.add_argument("--strict-replay", action="store_true",
                    help="turns before the budget must come from the response cache (0 quota); a miss skips the contest")
    ap.add_argument("--redo-forced", metavar="RUN", default=None,
                    help="judge only the contests RUN was forced on; carry RUN's other rows over unchanged "
                         "(an --extend run never reaches them, so they are exactly what it would produce)")
    ap.add_argument("--daily-cap", type=int, default=None, help="per-key cap; default 50 free-tier / 1000 with credits")
    ap.add_argument("--dry", action="store_true", help="scripted model, no OpenRouter calls")
    ap.add_argument("--workers", type=int, default=1, help="contests judged in parallel (keys rotate across them)")
    ap.add_argument("--focus-part", default=None, help="plan 005 idea G: 'k/n' = check differences k+1, k+1+n, ... first "
                    "(one of n divided investigators; needs tools v2+)")
    a = ap.parse_args()

    name = a.name or ("dry" if a.dry else time.strftime("run_%Y%m%d_%H%M"))
    out = ROOT / "runs" / name
    (out / "trajectories").mkdir(parents=True, exist_ok=True)
    logf = open(out / "run.log", "a", buffering=1, encoding="utf-8")

    def log(*m):
        s = " ".join(str(x) for x in m)
        print(s, flush=True)
        logf.write(s + "\n")

    contests = load_contests(a.shard or ["shard1_5pct"])
    by_shard: dict = {}
    for c in contests:
        by_shard.setdefault(c.shard, []).append(c.key)
    pos = {k: i for keys in by_shard.values() for i, k in enumerate(keys)}   # positions in the FULL shard
    if a.only_pos:
        want = {int(x) for x in a.only_pos.split(",")}
        contests = [c for i, c in enumerate(contests) if i in want]
    if a.limit:
        contests = contests[:a.limit]
    if a.swap:                       # answers A and B exchanged (position-bias check); keys stay the same for pairing
        contests = [dataclasses.replace(c, answer_a=c.answer_b, answer_b=c.answer_a, good_side="B" if c.good_side == "A" else "A")
                    for c in contests]
    res_p = out / "results.jsonl"
    if a.redo_noverdict and res_p.exists():
        # rows without a verdict are judged again; the old rows and their trajectories move aside (nothing deleted)
        rows = [json.loads(l) for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip()]
        bad = [r for r in rows if not r.get("verdict")]
        if bad:
            tag = time.strftime("%Y%m%d_%H%M")
            (out / f"results_noverdict_{tag}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in bad), encoding="utf-8")
            side = out / f"trajectories_noverdict_{tag}"
            side.mkdir(exist_ok=True)
            for r in bad:
                tf = out / "trajectories" / f"{r['shard']}_{pos[r['key']]:03d}.json"
                if tf.exists():
                    tf.rename(side / tf.name)
            res_p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows if r.get("verdict")), encoding="utf-8")
            print(f"[run] redo {len(bad)} no-verdict row(s); old rows in {out.name}/results_noverdict_{tag}.jsonl", flush=True)
    done = {json.loads(l)["key"] for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip()} \
        if res_p.exists() else set()
    if a.redo_forced:
        base = [json.loads(l) for l in (ROOT / "runs" / a.redo_forced / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        base = {r["key"]: r for r in base if r["key"] in {c.key for c in contests}}
        carry = [r for r in base.values() if r["how"] != "forced" and r["key"] not in done]
        with open(res_p, "a", encoding="utf-8") as f:
            for r in carry:
                f.write(json.dumps({**r, "carried_from": a.redo_forced}, ensure_ascii=False) + "\n")
        done |= {r["key"] for r in carry}
        contests = [c for c in contests if c.key in base]
    todo = [c for c in contests if c.key not in done]
    enc = QueryEncoder(log=log)
    if a.backend == "local":
        from judge.local_client import LocalClient
        a.model = "q38" if a.model == MODEL else a.model
        client = LocalClient(a.model, a.local_url, log=log, thinking=a.local_thinking, strength=a.reasoning_strength,
                             salt=a.seed_salt)
    elif a.backend == "baseten":                         # plan 007: Muse Spark Open as the whole agent (the hackathon key)
        from judge.baseten_client import BasetenClient
        client = BasetenClient(log=log, strength=a.reasoning_strength, salt=a.seed_salt, budget_usd=a.budget_usd,
                               tag=a.budget_tag or name, run=name)
        a.model = client.model
    elif a.backend == "meta":                            # plan 013: Muse Spark 1.3 Contributor on the Meta Model API
        from judge.meta_client import MetaClient
        client = MetaClient(log=log, strength=a.reasoning_strength, salt=a.seed_salt, budget_usd=a.budget_usd,
                            tag=a.budget_tag or name, run=name)
        a.model = client.model
    else:
        client = None if a.dry else Client(a.model, daily_cap=a.daily_cap, log=log)
    log(f"[run] {name} · {a.model if not a.dry else 'DRY (scripted)'} · {len(contests)} contest(s), "
        f"{len(done)} already done · tools {a.tools} · max_steps {a.max_steps}" + (f" + {a.extend} on extension" if a.extend else "")
        + (" · strict replay" if a.strict_replay else "")
        + ("" if a.dry else f" · quota used today {client.used_today()}/{client.cap_today()} over {len(client.keys)} key(s)"))
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock, stop, counter = threading.Lock(), threading.Event(), [len(done)]

    def one(c):
        if stop.is_set():
            return
        cl = ScriptedClient(c) if a.dry else client
        try:
            r = judge(c, cl, enc, max_steps=a.max_steps, extend=a.extend, strict_replay=a.strict_replay,
                      toolset=a.tools, max_tokens=a.max_tokens, keep_images=a.keep_images, keep_reasoning=a.keep_reasoning,
                      budget_note=a.budget_note, final_low=not a.final_full_reasoning, zoom_side=a.zoom_side,
                      inspect=a.inspect, look_first=a.look_first, max_images=a.max_images,
                      focus_part=tuple(int(x) for x in a.focus_part.split("/")) if a.focus_part else None,
                      max_per_request=8 if a.backend == "baseten" else None, look_around=a.look_around,
                      log=log)    # Baseten: at most 8 images
        except QuotaExhausted as e:
            stop.set()
            log(f"[run] stopped: {e}; rerun with --name {name} tomorrow to resume")
            return
        if r["errors"] and "QuotaExhausted" in r["errors"][0]:
            stop.set()                                   # unfinished: not written, so a resume redoes it
            log(f"[run] daily quota reached mid-contest ({c.key}); resume tomorrow with --name {name}")
            return
        if r["errors"] and "BudgetExceeded" in r["errors"][0]:
            stop.set()                                   # unfinished: not written; its spend stays in the log
            log(f"[run] budget stop mid-contest ({c.key}): {r['errors'][0][:160]}")
            return
        if r["errors"] and r["errors"][0].startswith("CacheMiss"):
            log(f"[run] SKIPPED {c.key}: replay diverged at step {r['steps']} ({r['errors'][0][:120]}); nothing sent")
            return                                       # unfinished: not written
        with lock:
            counter[0] += 1
            n = counter[0]
            # named by the contest's stable position in its shard, never by finishing order: a resumed run
            # must not overwrite trajectories the first pass wrote
            (out / "trajectories" / f"{c.shard}_{pos[c.key]:03d}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
            with open(res_p, "a", encoding="utf-8") as f:
                f.write(json.dumps({**{k: v for k, v in r.items() if k != "trajectory"}, "strict_replay": a.strict_replay,
                                    **({"swapped": True} if a.swap else {}), **({"seed_salt": a.seed_salt} if a.seed_salt else {})},
                                   ensure_ascii=False) + "\n")
        log(f"[run] {n}/{len(contests)} {c.domain:11s} {c.pair:22s} good={c.good_side} verdict={r['verdict']} "
            f"({r['how']}) steps={r['steps']} tools={len(r['tool_calls'])} imgs={r['images_viewed']} "
            f"{r['wall_s']}s" + (f" ERR {r['errors'][0][:120]}" if r["errors"] else ""))

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        list(ex.map(one, todo))
    rows = [json.loads(l) for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    s = {"name": name, "model": a.model if not a.dry else "dry", "tools": a.tools, "max_steps": a.max_steps, "extend": a.extend,
         "extended": sum(bool(r.get("extended")) for r in rows), **summarize(rows),
         "requests_sent_this_session": getattr(client, "sent", 0), "encoder_pod_calls": enc.pod_calls}
    (out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    log("[run] summary: " + json.dumps(s))


if __name__ == "__main__":
    main()
