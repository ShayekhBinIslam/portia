#!/usr/bin/env python3
"""portia/analysis/muse_errors.py: where does the tuned Muse agent go wrong? (dev shards 3 + 4)

Per contest: right/wrong, how it ended (answered itself / forced), whether any visual call (zoom, contact_sheet,
view_frames) looked at a ground-truth evidence moment or only at the right video, tool counts, and the kinds of
detail that separate the two answers (tool_failures.detail_categories). Paired against Muse static on the same
contests. Read-only: results and trajectories on disk.

    python analysis/muse_errors.py [--agent mg_v4t] [--static mg_static_sh]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from judge.contests import DATASET, load_contests                 # noqa: E402
from tool_failures import detail_categories, differing_details    # noqa: E402

SHARDS = (("s3", "shard3_15pct"), ("s4", "shard4_20pct"))


def parse_t(t):
    if isinstance(t, (int, float)):
        return float(t)
    try:
        return float(sum(float(x) * 60 ** i for i, x in enumerate(reversed(str(t).split(":")))))
    except ValueError:
        return None


def clips_of(rec):
    out = []
    for cr in rec.get("clip_ranges", []):
        vid, _, a0, b0 = rec[f"chunk_{cr['clip_id']}_filename"][:-4].rsplit("_", 3)
        a0, b0 = int(a0), int(b0)
        s0, e0 = cr["start_time"], cr["end_time"]
        if e0 <= (b0 - a0) + 5:
            s0, e0 = a0 + s0, a0 + e0
        out.append({"vid": vid, "start": s0, "end": e0})
    return out


def at_evidence(call: dict, clips: list) -> str:
    """'moment' if a visual call looks at a ground-truth evidence moment, 'video' if only at the right video."""
    a = call.get("args") or {}
    vid = str(a.get("video") or a.get("handle") or "").split("@")[0]
    same = [cl for cl in clips if cl["vid"] == vid]
    if not same:
        return ""
    if call["tool"] == "view_frames" and "@" in str(a.get("handle", "")):
        t0 = int(str(a["handle"]).split("@")[1])
        return "moment" if any(cl["end"] >= t0 and cl["start"] <= t0 + 30 for cl in same) else "video"
    if call["tool"] == "zoom":
        t = parse_t(a.get("t")) if a.get("t") is not None else None
        return "moment" if t is not None and any(cl["start"] - 15 <= t <= cl["end"] + 15 for cl in same) else "video"
    if call["tool"] == "contact_sheet":
        s0, e0 = parse_t(a.get("start")), parse_t(a.get("end"))
        return "moment" if s0 is not None and e0 is not None and any(cl["end"] >= s0 and cl["start"] <= e0 for cl in same) else "video"
    return "video"


def load(run):
    p = ROOT / "runs" / run / "results.jsonl"
    return {r["key"]: r for r in map(json.loads, open(p))} if p.exists() else {}


def pct(a, n):
    return f"{100 * a / n:5.1f}% ({a}/{n})" if n else "   -"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="mg_v4t")
    ap.add_argument("--static", default="mg_static_sh")
    a = ap.parse_args()
    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    rows = []
    for tag, shard in SHARDS:
        A, S = load(f"{a.agent}_{tag}"), load(f"{a.static}_{tag}")
        for c in load_contests([shard]):
            if c.key not in A:
                continue
            r, rec = A[c.key], recs[c.qid]
            cl = clips_of(rec)
            vis = [x for x in (r.get("tool_calls") or []) if x["tool"] in ("zoom", "contact_sheet", "view_frames")]
            hits = {at_evidence(x, cl) for x in vis}
            stage = "moment" if "moment" in hits else "video" if "video" in hits else "neither"
            cats = sorted({k for d in differing_details(rec, c.pair) for k in detail_categories(d)})
            rows.append({"shard": tag, "ok": bool(r.get("correct")), "how": r.get("how"), "steps": r.get("steps"),
                         "stage": stage, "n_vis": len(vis), "cats": cats or ["other"],
                         "tools": collections.Counter(x["tool"] for x in r.get("tool_calls") or []),
                         "static_ok": bool(S.get(c.key, {}).get("correct")) if c.key in S else None})
    n = len(rows)
    print(f"{a.agent} on shards 3+4: {n} contests, {pct(sum(r['ok'] for r in rows), n)} right")
    print("\nby how it ended:")
    for h in ("tool", "forced", "text"):
        sub = [r for r in rows if r["how"] == h]
        print(f"  {h:7s} {len(sub):4d} contests  accuracy {pct(sum(r['ok'] for r in sub), len(sub))}")
    print("\nby what it looked at (zoom / contact_sheet / view_frames vs the ground-truth evidence clips):")
    for s in ("moment", "video", "neither"):
        sub = [r for r in rows if r["stage"] == s]
        print(f"  {s:8s} {len(sub):4d} contests ({100 * len(sub) / n:4.1f}%)  accuracy {pct(sum(r['ok'] for r in sub), len(sub))}")
    print("\nby the kind of detail that separates the answers (a contest can have several):")
    cc = collections.Counter(k for r in rows for k in r["cats"])
    for k, m in cc.most_common():
        sub = [r for r in rows if k in r["cats"]]
        st_ = [r for r in sub if r["static_ok"] is not None]
        print(f"  {k:28s} {m:4d}  agent {pct(sum(r['ok'] for r in sub), len(sub))}   static {pct(sum(r['static_ok'] for r in st_), len(st_))}")
    pairs = [r for r in rows if r["static_ok"] is not None]
    b = sum(1 for r in pairs if r["ok"] and not r["static_ok"])
    c = sum(1 for r in pairs if r["static_ok"] and not r["ok"])
    print(f"\nagent vs static, paired: {len(pairs)} contests · agent-only right {b} · static-only right {c}")
    for s in ("moment", "video", "neither"):
        sub = [r for r in pairs if r["stage"] == s]
        print(f"  {s:8s}: agent-only {sum(1 for r in sub if r['ok'] and not r['static_ok'])}, static-only {sum(1 for r in sub if r['static_ok'] and not r['ok'])}")
    tot = collections.Counter()
    for r in rows:
        tot.update(r["tools"])
    print("\ntool calls per contest:", ", ".join(f"{t} {v / n:.2f}" for t, v in tot.most_common()))
    wrong_moment = [r for r in rows if not r["ok"] and r["stage"] == "moment"]
    print(f"\nwrong although it looked at an evidence moment: {len(wrong_moment)} of {sum(not r['ok'] for r in rows)} wrong verdicts")


if __name__ == "__main__":
    main()
