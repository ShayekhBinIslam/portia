#!/usr/bin/env python3
"""portia/analysis/tool_failures.py: where does the tool-using judge fail? (offline, 0 quota)

For every judged contest it joins three things:
  * the GROUND TRUTH of the dataset record: the evidence moments (clip_ranges -> 30 s segment handles) and
    the exact details each degraded answer changed (attribute_degradations, with their modality);
  * the agent's TRAJECTORY: which handles it was shown (initial evidence, search/grep results), which it
    read (read_transcript) and which it looked at (view_frames);
  * both arms' VERDICTS (tools run + static run on the same contests).

    python analysis/tool_failures.py --runs nemotron_s1:nemotron_static_s1 nemotron_s2:nemotron_static_s2 \
        nemotron_s3:nemotron_static_s3 --out analysis/tool_failures.json
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge import corpus                                       # noqa: E402
from judge.contests import DATASET, load_contests              # noqa: E402

HANDLE = re.compile(r"([A-Za-z0-9_-]{11})@(\d+)")
# keyword buckets for the perceptual kind of a separating detail (element text + attribute name)
CATS = [("text/number on screen", r"\b(text|written|reads|inscription|sign|label|caption|display|screen|title card|logo|letter|word|digit|number|value|price|date|jersey|banner|subtitle|ocr|truncat|spelling|typo)\b"),
        ("color", r"\b(colou?r|red|blue|green|yellow|white|black|silver|gold|golden|orange|purple|pink|brown|gr[ae]y|beige|teal)\b"),
        ("count/quantity", r"\b(count|number of|quantit|two|three|four|five|six|seven|eight|nine|ten|dozen|single|pair|dual)\b"),
        ("spatial/position", r"\b(left|right|above|below|behind|front|beside|next to|top|bottom|stack|position|location|placed|arrang|spatial|layout|orientation|facing|profile)\b"),
        ("clothing/appearance", r"\b(wear|wearing|shirt|dress|coat|vest|hat|jacket|uniform|hair|beard|glasses|outfit|suit|costume|apron)\b"),
        ("action/pose", r"\b(action|gesture|pose|posture|holding|sitting|standing|walking|running|pointing|raising|seated|kneel|motion|movement)\b"),
        ("setting/environment", r"\b(environment|setting|background|room|vault|gallery|forest|grove|landscape|interior|exterior|street|sky|weather|indoor|outdoor|scene)\b"),
        ("object identity", r"\b(object|substitut|replac|hallucinat|invent|instead of|swap|species|animal|vehicle|instrument|tool|item)\b")]


def detail_categories(d: dict) -> list[str]:
    t = f"{d.get('element', '')} {d.get('attribute', '')}".lower()
    return [c for c, rx in CATS if re.search(rx, t)] or ["other"]



def evidence_handles(rec: dict) -> dict:
    """clip_ranges -> {handle: [clip refs]} of every 30 s segment overlapping an evidence moment."""
    out = collections.defaultdict(list)
    for c in rec.get("clip_ranges", []):
        fn = rec[f"chunk_{c['clip_id']}_filename"][:-4]
        vid, _, a, b = fn.rsplit("_", 3)
        a, b = int(a), int(b)
        s, e = c["start_time"], c["end_time"]
        if e <= (b - a) + 5:                    # chunk-relative (1604 of 1645 clips)
            s, e = a + s, a + e
        elif not (a <= s <= b):                 # neither relative nor absolute inside the chunk: unusable
            continue
        for t in range(int(s // 30) * 30, int(e), 30):
            out[f"{vid}@{t}"].append(c.get("qa_reference", "")[:80])
    return dict(out)


def differing_details(rec: dict, pair: str) -> list[dict]:
    """The details that separate the two answers: every degradation of each non-gold side."""
    out = []
    for side in pair.split("_vs_"):
        if side == "gold":
            continue
        for a in (rec.get(side) or {}).get("attribute_degradations", []):
            for e in a.get("degradation_by_elements", []):
                out.append({"side": side, "attribute": a.get("attribute_name"), "element": e.get("element"),
                            "modality": e.get("modality")})
    return out


def trajectory_coverage(traj: dict, ev: set) -> dict:
    msgs = traj["trajectory"]["messages"]
    first = msgs[1]["content"] if len(msgs) > 1 else ""
    if isinstance(first, list):                  # v3: text + the pinned overview sheets
        first = " ".join(x.get("text", "") for x in first if x.get("type") == "text")
    shown_initial = set(m.group(0) for m in HANDLE.finditer(first))
    shown, read, viewed, view_calls = set(shown_initial), set(), set(), 0
    for m in msgs[2:]:
        if m.get("role") == "tool" and isinstance(m.get("content"), str):
            shown |= set(x.group(0) for x in HANDLE.finditer(m["content"]))
        for c in m.get("tool_calls") or []:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "view_frames":
                view_calls += 1
                h = str(args.get("handle", ""))
                if HANDLE.fullmatch(h):
                    viewed.add(h)
            elif name == "read_transcript":
                ctx = int(args.get("context") or 0)
                for h in args.get("handles") or []:
                    mm = HANDLE.fullmatch(str(h))
                    if mm:
                        for d in range(-ctx, ctx + 1):
                            read.add(f"{mm.group(1)}@{int(mm.group(2)) + 30 * d}")
    vids_ev = {h.split("@")[0] for h in ev}
    return {"initial_hit": bool(ev & shown_initial), "shown_hit": bool(ev & shown), "read_hit": bool(ev & read),
            "viewed_hit": bool(ev & viewed), "viewed_n": len(viewed), "view_calls": view_calls,
            "viewed_ev_n": len(ev & viewed), "ev_n": len(ev),
            "viewed_right_video": bool({h.split("@")[0] for h in viewed} & vids_ev)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="tools_run:static_run pairs")
    ap.add_argument("--out", default=str(ROOT / "analysis" / "tool_failures.json"))
    a = ap.parse_args()
    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    rows = []
    for pair in a.runs:
        tn, sn = pair.split(":")
        T = {r["key"]: r for r in map(json.loads, open(ROOT / "runs" / tn / "results.jsonl"))}
        S = {r["key"]: r for r in map(json.loads, open(ROOT / "runs" / sn / "results.jsonl"))}
        shard = next(iter(T.values()))["shard"]
        contests = load_contests([shard])
        corpus.register(sorted({p for c in contests for p in corpus.domain_playlists(c.domain)}))
        for i, c in enumerate(contests):
            if c.key not in T:
                continue
            f = ROOT / "runs" / tn / "trajectories" / f"{shard}_{i:03d}.json"
            if not f.exists():
                continue
            rec = recs[c.qid]
            ev = evidence_handles(rec)
            ev_known = {h for h in ev if corpus.segment(h)}
            cov = trajectory_coverage(json.load(open(f)), ev_known)
            dd = differing_details(rec, c.pair)
            t, s = T[c.key], S.get(c.key) or {}
            rows.append({"key": c.key, "shard": shard, "pos": i, "domain": c.domain, "pair": c.pair, "gap": c.gap,
                         "good_side": c.good_side, "tools_ok": bool(t.get("correct")), "tools_how": t.get("how"),
                         "static_ok": bool(s.get("correct")) if s.get("verdict") else None,
                         "steps": t.get("steps"), "images": t.get("images_viewed"),
                         "ev_handles": sorted(ev_known), "ev_unindexed": sorted(set(ev) - ev_known), **cov,
                         "diff_modalities": dict(collections.Counter(d["modality"] for d in dd)),
                         "diff_details": dd, "rationale": t.get("rationale", "")})
    Path(a.out).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")

    n = len(rows)
    acc = lambda rs, k="tools_ok": (sum(bool(r[k]) for r in rs), len(rs))            # noqa: E731
    fmt = lambda x: f"{x[0]}/{x[1]} = {100 * x[0] / x[1]:.0f}%" if x[1] else "-"     # noqa: E731
    print(f"{n} contests · tools {fmt(acc(rows))} · static {fmt(acc([r for r in rows if r['static_ok'] is not None], 'static_ok'))}")
    mods = collections.Counter(m for r in rows for m, k in r["diff_modalities"].items() for _ in range(k))
    print("modality of the details that separate the answers:", dict(mods))
    print("\nevidence coverage by the agent (ground-truth evidence segments):")
    for k, label in (("initial_hit", "in the initial top-8"), ("shown_hit", "ever shown (initial or a search/grep result)"),
                     ("read_hit", "transcript read"), ("viewed_right_video", "frames viewed in the right video"),
                     ("viewed_hit", "frames viewed of an evidence segment")):
        yes = [r for r in rows if r[k]]
        no = [r for r in rows if not r[k]]
        print(f"  {label:48s} {len(yes):3d}/{n} ({100 * len(yes) / n:.0f}%) · tools acc when yes {fmt(acc(yes))}, when no {fmt(acc(no))}")
    print("\nfunnel (exclusive):")
    stages = collections.OrderedDict()
    for r in rows:
        st = ("1 never shown" if not r["shown_hit"] else "2 shown, never viewed" if not r["viewed_hit"] else "3 viewed")
        stages.setdefault(st, []).append(r)
    for st, rs in sorted(stages.items()):
        print(f"  {st:24s} {len(rs):3d} contests · tools {fmt(acc(rs))} · static {fmt(acc([r for r in rs if r['static_ok'] is not None], 'static_ok'))}")
    print("\nmean frames viewed:", round(sum(r["images"] or 0 for r in rows) / n, 1),
          "· contests with 0 frames:", sum(1 for r in rows if not r["images"]))
    zero = [r for r in rows if not r["images"]]
    print("  tools acc with 0 frames viewed:", fmt(acc(zero)), "· with >0:", fmt(acc([r for r in rows if r["images"]])))


if __name__ == "__main__":
    main()
