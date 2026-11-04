#!/usr/bin/env python3
"""portia/judge/adjudicate.py: plan 004 (audits/004_investigators_adjudicator.md): investigators and an adjudicator.

    python -m judge.adjudicate --runs mg_v4t_s3,mg_v4t_r1_s3,mg_v4t_r2_s3 --shard shard3_15pct --name mg_adj_s3 \
        --model mg30 --local-url http://127.0.0.1:18660/v1 --local-thinking --max-tokens 16384 --workers 12

The investigators are EXISTING agent runs over the same contests (same keys, same A/B sides). When they agree, their
verdict stands (how "unanimous", no request). When they disagree, the contest goes to
  --variant adjudicator   one agent that reads the reports (verdict, rationale, and each investigator's own close looks
                          re-rendered from its logged tool calls) and re-checks the disputed moments with look-only tools;
  --variant evidence      the same agent shown only the investigators' close looks, without their verdicts or reasoning;
  --variant rebuttal      every investigator takes a second look that shows it the other reports; the majority of the
                          revised verdicts decides.
Prompts are in prompts/adjudicator/, the tools are toolset "adj" (tools/toolsets.yaml). No ground truth or dataset
metadata enters a prompt: good_side is read only to score a row. Outputs runs/<name>/ like judge/run.py (results.jsonl,
trajectories/ for the contests that were adjudicated, summary.json, run.log), resumable.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from judge import corpus, prompting                                               # noqa: E402
from judge.agent import IMAGE_DROPPED, _img_part, _loggable, _prune_images, _text_verdict       # noqa: E402
from judge.answer_diff import answer_diff                                          # noqa: E402
from judge.contests import load_contests                                           # noqa: E402
from judge.tools import Toolbox                                                    # noqa: E402

VISUAL = ("zoom", "burst", "contact_sheet", "view_frames")
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}    # "three" keeps plan 004's prompts byte-identical
FLIP = {"A": "B", "B": "A"}
ALLOWED = {"zoom", "burst", "contact_sheet", "view_frames", "read_transcript"}
CLOSE = {"zoom": 0, "burst": 0, "view_frames": 1, "contact_sheet": 2}      # closer looks first when choosing views
_T = r"\d{1,2}:\d{2}(?::\d{2})?|\d+(?:\.\d+)?"
_ATEM_PARAM = re.compile(r'<atem:parameter name="([A-Za-z_]+)">\s*([^<\n]*)')


_DIFF_ITEM = re.compile(r'^(\d+)\. A: (.*)\n   B: (.*)$', re.M)


def diff_items(contest, k: int = 8) -> tuple[list, str | None]:
    """Plan 005 idea E: the places where the answers differ, as the adjudicator saw them in the first message (judge/
    answer_diff.py), at most k. Returns (items, reason to skip): low-overlap pairs give long, noisy lists."""
    text = answer_diff(contest.answer_a, contest.answer_b)
    if "worded very differently" in text:
        return [], "low overlap"
    items = [(int(n), a, b) for n, a, b in _DIFF_ITEM.findall(text)][:k]
    return items, (None if items else "no differences")


def repair_args(name: str, args: dict) -> dict:
    """vLLM's muse_glimmer tool parser sometimes leaves ATEM markup inside an argument, e.g. a burst call parsed as
    {"burst": "\\n<atem:parameter name=\\"video\\">T9DOER8JmSc", "t": "40:03"} (9 of the first 426 adjudicator calls,
    all burst). Recover the parameters the markup swallowed and drop the bogus key named after the tool."""
    out = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and "<atem:parameter" in v:
            out.update({pk: pv.strip() for pk, pv in _ATEM_PARAM.findall(v) if pv.strip()})
            continue
        if k != name:
            out.setdefault(k, v)
    return out
# video@time, and the looser "video 08:33-09:03" / "video at 08:33" that rationales also use; a stray match is harmless
# because a citation only counts when it names a video and moment the investigator actually looked at
CITE = re.compile(rf"([A-Za-z0-9_-]{{11}})(?:@|\s+at\s+|\s+)({_T})(?:\s*[-–]\s*({_T}))?")


# ------------------------------------------------------------------ the investigators' evidence
def cites(text: str) -> list[tuple[str, float, float]]:
    """(video, t0, t1) for every video@time or video@time-time a rationale cites."""
    out = []
    for vid, a, b in CITE.findall(text or ""):
        t0 = corpus.parse_time(a)
        t1 = corpus.parse_time(b) if b else t0
        out.append((vid, min(t0, t1), max(t0, t1)))
    return out


def span(call: dict):
    """(video, t0, t1) that a logged visual tool call looked at, or None."""
    a = call.get("args") or {}
    try:
        if call["tool"] == "view_frames":
            vid, s = str(a.get("handle", "")).split("@")
            return vid, float(s), float(s) + 30
        m = re.fullmatch(r"\s*([A-Za-z0-9_-]{11})(?:@(\d+))?\s*", str(a.get("video", "")))
        if not m:
            return None
        vid, start = m.group(1), (float(m.group(2)) if m.group(2) else None)
        if call["tool"] == "contact_sheet":
            return vid, corpus.parse_time(a.get("start")), corpus.parse_time(a.get("end"))
        t = a.get("t")
        t = corpus.parse_time(t) if t is not None else (start + 15 if start is not None else None)
        return (vid, t, t) if t is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def pick_views(calls: list, rationale: str, k: int = 3, tol: float = 20.0) -> list:
    """An investigator's own closest looks at the moments its rationale cites: at most k, zoom and burst before strips
    and contact sheets, latest first, returned in the order it made them. If it cites no moment it looked at, its last
    two looks."""
    looks = [(i, c) for i, c in enumerate(calls or []) if c.get("tool") in VISUAL and c.get("images")]
    cs = cites(rationale)

    def hit(c):
        sp = span(c)
        return sp is not None and sp[1] is not None and any(v == sp[0] and sp[1] - tol <= t1 and t0 <= sp[2] + tol for v, t0, t1 in cs)

    pool = [(i, c) for i, c in looks if hit(c)] or looks[-2:]
    chosen = sorted(pool, key=lambda ic: (CLOSE[ic[1]["tool"]], -ic[0]))[:k]
    return [c for _, c in sorted(chosen, key=lambda ic: ic[0])]


def render_views(contest, calls: list, log=print) -> list[tuple]:
    """Re-run logged visual calls: the tools are deterministic, so these are the images the investigator saw."""
    box = Toolbox(contest, None, max_images=99, log=log, toolset="v2")
    out = []
    for c in calls:
        _, imgs = box.run(c["tool"], c.get("args") or {})
        out += imgs                                    # (PIL image, label)
    return out


def report_order(key: str, n: int, salt: int) -> list[int]:
    """Seeded order of the reports for one contest: which investigator is Report 1, 2, ..."""
    return sorted(range(n), key=lambda i: hashlib.sha1(f"{salt}|{key}|{i}".encode()).hexdigest())


# ------------------------------------------------------------------ the adjudicating agent
KINDS: dict = {}          # plan 019 E3: contest key -> dispute kind (runs/dispute_kind_by_key.json, analysis/dispute_kinds.py)


def first_content(contest, reports: list, variant: str, own, max_steps: int) -> list:
    parts = [{"type": "text", "text": prompting.render("adjudicator/first_message.j2", question=contest.question,
                                                         answer_a=contest.answer_a, answer_b=contest.answer_b,
                                                         diff=answer_diff(contest.answer_a, contest.answer_b),
                                                         variant=variant)}]
    if variant == "evidence":
        seen, views = set(), []
        for r in reports:
            for im, lab in r["views"]:
                if lab not in seen:
                    seen.add(lab)
                    views.append((im, lab))
        parts.append({"type": "text", "text": prompting.render("adjudicator/evidence.j2", labels=[lab for _, lab in views],
                                                             n_word=WORDS.get(len(reports), str(len(reports))))})
        parts += [_img_part(im) for im, _ in views]
    else:
        for j, r in enumerate(reports):
            parts.append({"type": "text", "text": prompting.render("adjudicator/report.j2", label=f"Report {j + 1}", own=(own == j), verdict=r["verdict"],
                rationale=r["rationale"] or "(no rationale given)", labels=[lab for _, lab in r["views"]])})
            parts += [_img_part(im) for im, _ in r["views"]]
    parts.append({"type": "text", "text": prompting.render("adjudicator/footer.j2", max_steps=max_steps)})
    return parts


def _step_log(resp: dict, msg: dict, calls: list, **extra) -> dict:
    return {"latency_s": resp.get("_latency_s"), "usage": resp.get("usage"), "finish_reason": resp["choices"][0].get("finish_reason"),
            "content": (msg.get("content") or "")[:2000], "reasoning_chars": len(msg.get("reasoning") or ""),
            "reasoning": (msg.get("reasoning") or "")[:20000],
            "tool_calls": [{"name": c["function"]["name"], "args": c["function"].get("arguments")} for c in calls], **extra}


def adjudicate(contest, reports: list, client, variant: str = "adjudicator", own: int | None = None, max_steps: int = 4,
               max_tokens: int = 16384, keep_images: int = 12, max_images: int = 16, max_per_request: int | None = None,
               search: bool = False, encoder=None, observe: bool = False, wide: bool = False, kind_note: str | None = None,
               log=print) -> dict:
    """One adjudicating agent (or, for the rebuttal, the second look of the investigator whose report is `own`).
    The loop mirrors judge/agent.py's tuned v4 settings: reasoning kept in the history, a turns-left note, the forced
    final answer at full reasoning strength, and the same two-level fallback when no verdict comes back."""
    t0 = time.time()
    # plan 010: search=True adds search_video / search / grep_transcripts (the tool box then needs the query encoder)
    box = Toolbox(contest, encoder if search else None, max_images=max_images, log=log, toolset="v2")
    tools = prompting.toolset("adj_search" if search else "adj")
    pvar = "evidence" if variant == "claims" else variant       # the claims variant sees exactly what evidence-only sees
    system = prompting.render("adjudicator/system.j2", variant=pvar, own=(own + 1) if own is not None else None,
                              n_word=WORDS.get(len(reports), str(len(reports))), **({"search": True} if search else {}),
                              **({"observe": True} if observe else {}),      # plan 012: describe each image before comparing
                              **({"wide": True} if wide else {}),            # plan 019: check a minute around each moment
                              **({"kind_note": kind_note} if kind_note else {}))   # plan 019 E3: a procedure for counts / text
    first = first_content(contest, reports, pvar, own, max_steps)
    if max_per_request:
        # an API that caps images per request (Baseten: 8): the pinned looks keep at most max_per_request - 2 images
        # (the last ones beyond that are dropped), and the adjudicator's own looks get the rest, newest first
        idx = [i for i, p in enumerate(first) if p.get("type") == "image_url"]
        for i in idx[max(1, max_per_request - 2):]:
            first[i] = {"type": "text", "text": IMAGE_DROPPED}
        n_first = min(len(idx), max(1, max_per_request - 2))
        keep_images = max(1, min(keep_images, max_per_request - n_first))
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": first}]
    steps, verdict, rationale, how, errors, recovered = [], None, "", None, [], 0
    for step in range(max_steps + 1):
        final = step == max_steps
        if final:
            messages.append({"role": "user", "content": prompting.render("agent/budget_final.j2")})
        tc = {"type": "function", "function": {"name": "answer"}} if final else "auto"
        roomy = {"max_tokens": max(max_tokens, 8192), "reasoning": {"effort": "low"}}
        try:
            send = _prune_images(messages, keep_images, pinned=2)      # the reports' images stay; older own looks drop
            resp = client.chat(send, tools=tools, tool_choice=tc, temperature=0.0,
                               max_tokens=max(max_tokens, 8192) if final else max_tokens)
            m0, ch0 = resp["choices"][0].get("message") or {}, resp["choices"][0]
            if not m0.get("content") and not m0.get("tool_calls") and ch0.get("finish_reason") == "length":
                recovered += 1
                resp = client.chat(send, tools=tools, tool_choice=tc, temperature=0.0, **roomy)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
            how = "error"
            break
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        steps.append(_step_log(resp, msg, calls, step=step))
        messages.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": calls} if calls else {}),
                         **({"reasoning": msg["reasoning"]} if msg.get("reasoning") else {})})
        if not calls:
            v = _text_verdict(msg.get("content") or "")
            if v:
                verdict, rationale, how = v, (msg.get("content") or "")[-600:], "text"
                break
            messages.append({"role": "user", "content": prompting.render("agent/nudge_use_tool.j2")})
            continue
        frames, done = [], False
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "answer":
                v = str(args.get("verdict", "")).strip().upper()[:1]
                if v in ("A", "B"):
                    verdict, rationale, how, done = v, str(args.get("rationale", "")), ("forced" if final else "tool"), True
                text = prompting.render("agent/answer_result.j2", recorded=done)
            elif name in ALLOWED:
                fixed = repair_args(name, args)
                text, imgs = box.run(name, fixed)
                if fixed != args:                       # the log keeps both, so a replay uses the repaired call
                    box.calls[-1]["repaired_from"] = args
                frames += [(c["id"], im, lab) for im, lab in imgs]
            else:                                       # logged like any call, so call indexes match the history
                text = prompting.render("adjudicator/not_available.j2", tool=name)
                box.calls.append({"tool": name, "args": args, "result_chars": len(text), "images": 0, "refused": True})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": text})
        if done:
            break
        note = prompting.render("agent/turn_note.j2", budget_note=True, look_first=False, left=max_steps - (step + 1),
                                n_text=0, n_look=0, text_streak=0).strip()
        if note and not frames:
            messages.append({"role": "user", "content": note})
        if frames:
            parts = [{"type": "text", "text": prompting.render("agent/images_message.j2", v2=True, note=note,
                                                             labels=[str(lab) for _, _, lab in frames])}]
            parts += [_img_part(im) for _, im, _ in frames]
            messages.append({"role": "user", "content": parts})
    fallback = False
    if verdict is None and how != "error" and steps:
        # as in judge/agent.py: vLLM does not enforce a named tool choice for ATEM calls, so first `answer` as the only
        # tool, then (local vLLM) no tools and a reply constrained to the letter A or B
        fallback = True
        params = {"max_tokens": max(max_tokens, 8192)}
        messages.append({"role": "user", "content": prompting.render("agent/fallback_answer_only.j2")})
        try:
            send = _prune_images(messages, keep_images, pinned=2)
            resp = client.chat(send, tools=[t for t in tools if t["function"]["name"] == "answer"],
                               tool_choice={"type": "function", "function": {"name": "answer"}}, temperature=0.0, **params)
            msg = resp["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            steps.append(_step_log(resp, msg, calls, step=len(steps), answer_fallback=True))
            messages.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": calls} if calls else {})})
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                v = str(args.get("verdict", "")).strip().upper()[:1]
                if c["function"]["name"] == "answer" and v in ("A", "B"):
                    verdict, rationale, how = v, str(args.get("rationale", "")), "forced"
                    break
            if verdict is None and _text_verdict(msg.get("content") or ""):
                verdict, rationale, how = _text_verdict(msg.get("content") or ""), (msg.get("content") or "")[-600:], "text"
            if verdict is None and getattr(client, "supports_choice", False):
                for c in calls:
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": prompting.render("agent/fallback_tool_closed.j2")})
                messages.append({"role": "user", "content": prompting.render("agent/fallback_choice.j2")})
                send = _prune_images(messages, keep_images, pinned=2)
                resp = client.chat(send, temperature=0.0, structured_outputs={"choice": ["A", "B"]}, **params)
                msg = resp["choices"][0]["message"]
                m = re.search(r"([AB])\s*$", msg.get("content") or "")
                v = m.group(1) if m else None
                steps.append(_step_log(resp, msg, [], step=len(steps), answer_fallback="choice"))
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                if v in ("A", "B"):
                    verdict, how = v, "forced"
                    rationale = "(tools closed; verdict constrained to A/B) " + (msg.get("reasoning") or "")[-600:]
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
    claims = None
    if variant == "claims" and how != "error":
        # one constrained A / B / U ruling per difference, each asked independently after the adjudicator's own looks
        # (same prefix, so the server's prefix cache serves most of each request); the answer with more supported
        # versions wins; a tie, or a skipped list, keeps the holistic verdict
        items, skip = diff_items(contest)
        claims = {"holistic": verdict, "skipped": skip, "rulings": []}
        base = _prune_images(messages, keep_images, pinned=2)
        for n, ta, tb in items:
            q = prompting.render("adjudicator/claim_question.j2", n=n, a=ta, b=tb)
            try:
                resp = client.chat(base + [{"role": "user", "content": q}], temperature=0.0, max_tokens=8192,
                                   structured_outputs={"choice": ["A", "B", "U"]})
                msg = resp["choices"][0]["message"]
                m = re.search(r"([ABU])\s*$", msg.get("content") or "")
                claims["rulings"].append({"n": n, "ruling": m.group(1) if m else None, "reasoning": (msg.get("reasoning") or "")[-1500:]})
                steps.append(_step_log(resp, msg, [], step=len(steps), claim=n))
            except Exception as e:
                claims["rulings"].append({"n": n, "ruling": None, "error": f"{type(e).__name__}: {e}"})
        sa = sum(r["ruling"] == "A" for r in claims["rulings"])
        sb = sum(r["ruling"] == "B" for r in claims["rulings"])
        claims.update(support_a=sa, support_b=sb)
        if sa != sb:
            verdict, how = ("A" if sa > sb else "B"), "claims"
            rationale = f"(claims: A's version supported on {sa}, B's on {sb}) " + rationale
        elif items:
            how = (how or "") + "+claims-tie"
    return {"verdict": verdict, "rationale": rationale, "how": how, "steps": len(steps), "tool_calls": box.calls, "claims": claims,
            "images_viewed": box.images_used, "errors": errors, "wall_s": round(time.time() - t0, 1),
            "recovered_truncations": recovered, "answer_fallback": fallback,
            "usage": {k: sum((s["usage"] or {}).get(k, 0) or 0 for s in steps) for k in ("prompt_tokens", "completion_tokens")},
            "trajectory": {"steps": steps, "messages": _loggable(messages)}}


# ------------------------------------------------------------------ runner
def majority(vs: list) -> str | None:
    c = Counter(v for v in vs if v in ("A", "B")).most_common()
    return c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else None


def load_rows(name: str) -> dict:
    p = ROOT / "runs" / name / "results.jsonl"
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["key"]] = r                         # a later row for the same contest (a redo) wins
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    acc = lambda rs, f: round(100 * sum(bool(f(r)) for r in rs) / len(rs), 2) if rs else None   # noqa: E731
    con = [r for r in rows if r["contested"]]
    mw = [r for r in con if r["vote"] and not r["vote_correct"]]                 # contested, majority wrong
    mr = [r for r in con if r["vote"] and r["vote_correct"]]                     # contested, majority right
    return {"n": n, "acc_pct": acc(rows, lambda r: r["correct"]), "vote_acc_pct": acc(rows, lambda r: r["vote_correct"]),
            "no_verdict": sum(r["verdict"] is None for r in rows), "contested": len(con),
            "contested_acc_pct": acc(con, lambda r: r["correct"]), "contested_vote_acc_pct": acc(con, lambda r: r["vote_correct"]),
            "fixed_vs_vote": sum(bool(r["correct"]) and not r["vote_correct"] for r in rows),
            "broken_vs_vote": sum(r["vote_correct"] and not r["correct"] for r in rows),
            "followed_wrong_majority_pct": acc(mw, lambda r: r["verdict"] == r["vote"]),
            "kept_right_majority_pct": acc(mr, lambda r: r["verdict"] == r["vote"]),
            "how": dict(Counter(r["how"] for r in rows)),
            "mean_wall_s_contested": round(sum(r["wall_s"] for r in con) / len(con), 1) if con else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", required=True, help="comma-separated investigator runs over the same shard (3 for plan 004)")
    ap.add_argument("--shard", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--variant", choices=["adjudicator", "evidence", "rebuttal", "claims"], default="adjudicator",
                    help="claims (plan 005 idea E): evidence-only, then one constrained ruling per difference decides")
    ap.add_argument("--all", action="store_true", help="also adjudicate contests the investigators agree on (a check)")
    ap.add_argument("--max-steps", type=int, default=4)
    ap.add_argument("--views", type=int, default=3, help="re-rendered close looks per report")
    ap.add_argument("--search", action="store_true", help="plan 010: the adjudicator may also search (search_video, search, grep)")
    ap.add_argument("--observe", action="store_true", help="plan 012: observe (describe each image) before comparing the claims")
    ap.add_argument("--wide", action="store_true", help="plan 019: check about a minute around each moment before ruling")
    ap.add_argument("--kind-notes", action="store_true", help="plan 019 E3: a procedure for count and on-screen-text disputes")
    ap.add_argument("--order-salt", type=int, default=0, help="a different seeded order of the reports")
    ap.add_argument("--backend", choices=["local", "baseten", "meta"], default="local",
                    help="baseten: Muse Spark Open on Baseten as the adjudicator (hackathon key; plan 006); investigators stay local runs")
    ap.add_argument("--budget-usd", type=float, default=2.0, help="baseten: stop before this run's logged spend exceeds it")
    ap.add_argument("--budget-tag", default=None, help="baseten: share one budget across runs (default: the run name)")
    ap.add_argument("--model", default="mg30")
    ap.add_argument("--local-url", default="http://127.0.0.1:18660/v1")
    ap.add_argument("--local-thinking", action="store_true")
    ap.add_argument("--reasoning-strength", default="high", choices=["low", "medium", "high", "xhigh"])
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--seed-salt", type=int, default=0, help="an independent sample of every request")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-contested", action="store_true", help="skip the contests the investigators agree on (smoke tests)")
    ap.add_argument("--swap", action="store_true", help="the adjudicator sees answers A and B exchanged (same looks); its "
                    "verdict is mapped back, so rows stay in the contest's own orientation (plan 005 idea B)")
    a = ap.parse_args()
    if a.kind_notes:
        KINDS.update(json.loads((Path(__file__).resolve().parents[1] / "runs" / "dispute_kind_by_key.json").read_text(encoding="utf-8")))

    runs = [r.strip() for r in a.runs.split(",") if r.strip()]
    out = ROOT / "runs" / a.name
    (out / "trajectories").mkdir(parents=True, exist_ok=True)
    logf = open(out / "run.log", "a", buffering=1, encoding="utf-8")

    def log(*m):
        s = " ".join(str(x) for x in m)
        print(s, flush=True)
        logf.write(s + "\n")

    contests = load_contests([a.shard])
    pos = {c.key: i for i, c in enumerate(contests)}            # positions in the FULL shard, as judge/run.py names files
    inv = [load_rows(r) for r in runs]
    contests = [c for c in contests if all(c.key in rows for rows in inv)]
    if a.only_contested:
        contests = [c for c in contests if len({rows[c.key].get("verdict") for rows in inv}) > 1]
    if a.limit:
        contests = contests[:a.limit]
    res_p = out / "results.jsonl"
    done = {json.loads(l)["key"] for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip()} if res_p.exists() else set()
    todo = [c for c in contests if c.key not in done]
    max_req = None
    if a.backend == "baseten":
        max_req = 8                                   # Baseten: "Too many images: 10 (max 8)"
        a.views = min(a.views, 2)
        from judge.baseten_client import BasetenClient, spent
        tag = a.budget_tag or a.name
        client = BasetenClient(log=log, strength=a.reasoning_strength, salt=a.seed_salt, budget_usd=a.budget_usd, tag=tag, run=a.name)
        log(f"[adj] adjudicator = Muse Spark Open on Baseten ({client.model}); spend so far for budget {tag}: ${spent(tag):.4f} "
            f"of ${a.budget_usd:.2f}")
    elif a.backend == "meta":                         # plan 013: Muse Spark 1.3 Contributor (no image cap per request)
        from judge.meta_client import MetaClient, spent as meta_spent
        tag = a.budget_tag or a.name
        client = MetaClient(log=log, strength=a.reasoning_strength, salt=a.seed_salt, budget_usd=a.budget_usd, tag=tag, run=a.name)
        log(f"[adj] adjudicator = Muse Spark 1.3 Contributor on the Meta Model API; spend so far for budget {tag}: "
            f"${meta_spent(tag):.4f} of ${a.budget_usd:.2f}")
    else:
        from judge.local_client import LocalClient
        client = LocalClient(a.model, a.local_url, log=log, thinking=a.local_thinking, strength=a.reasoning_strength, salt=a.seed_salt)
    log(f"[adj] {a.name} · {a.variant} · investigators {','.join(runs)} · {len(contests)} contest(s), {len(done)} already done"
        f" · max_steps {a.max_steps} · views {a.views} · order salt {a.order_salt} · seed salt {a.seed_salt}"
        + (" · may search" if a.search else "") + (" · observe first" if a.observe else ""))
    enc = None
    if a.search:                                       # plan 010: searching needs the query encoder (box CPU)
        from judge.embed_client import QueryEncoder
        enc = QueryEncoder(log=log)
    lock, counter = threading.Lock(), [len(done)]

    def one(c):
        vs = [rows[c.key].get("verdict") for rows in inv]
        vote = majority(vs)
        contested = len({v for v in vs if v in ("A", "B")}) != 1 or sum(v in ("A", "B") for v in vs) < 2
        order = report_order(c.key, len(runs), a.order_salt)
        row = {"key": c.key, "qid": c.qid, "pair": c.pair, "occurrence": c.occurrence, "shard": c.shard, "domain": c.domain,
               "gap": c.gap, "good_side": c.good_side, "variant": a.variant, "investigators": runs, "inv_verdicts": vs,
               "vote": vote, "vote_correct": vote == c.good_side, "contested": contested, "report_order": order,
               **({"seed_salt": a.seed_salt} if a.seed_salt else {}), **({"order_salt": a.order_salt} if a.order_salt else {}),
               **({"swapped": True} if a.swap else {})}
        if not contested and not a.all:
            r = {"verdict": vote, "rationale": "", "how": "unanimous", "steps": 0, "tool_calls": [], "images_viewed": 0,
                 "errors": [], "wall_s": 0.0, "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
            traj = None
        else:
            pc = dataclasses.replace(c, answer_a=c.answer_b, answer_b=c.answer_a, good_side=FLIP[c.good_side]) if a.swap else c
            reports = []
            for i in order:
                ir = inv[i][c.key]
                calls = pick_views(ir.get("tool_calls"), ir.get("rationale") or "", k=a.views)
                # a static judge's row has no rationale field and no tool calls: its report is the end of its analysis
                why = (ir.get("rationale") or "").strip() or (ir.get("output") or "").strip()[-1500:]
                v_in = ir.get("verdict") or "?"
                reports.append({"verdict": FLIP.get(v_in, v_in) if a.swap else v_in, "rationale": why,
                                "views": render_views(c, calls, log=log), "picked": calls})
            if a.variant == "rebuttal":
                sess = [adjudicate(pc, reports, client, variant="rebuttal", own=j, max_steps=a.max_steps,
                                   max_tokens=a.max_tokens, max_per_request=max_req, log=log) for j in range(len(reports))]
                if a.swap:
                    for x in sess:
                        x["verdict"] = FLIP.get(x["verdict"], x["verdict"])
                    for rep_ in reports:
                        rep_["verdict"] = FLIP.get(rep_["verdict"], rep_["verdict"])
                revised = [s["verdict"] or reports[j]["verdict"] for j, s in enumerate(sess)]
                v = majority(revised)
                r = {"verdict": v, "rationale": " | ".join(f"Report {j + 1}: {s['rationale'][:300]}" for j, s in enumerate(sess)),
                     "how": "rebuttal", "revised": revised, "changed": sum(x != reports[j]["verdict"] for j, x in enumerate(revised)),
                     "steps": sum(s["steps"] for s in sess), "tool_calls": [t for s in sess for t in s["tool_calls"]],
                     "images_viewed": sum(s["images_viewed"] for s in sess), "errors": [e for s in sess for e in s["errors"]],
                     "wall_s": round(sum(s["wall_s"] for s in sess), 1),
                     "usage": {k: sum(s["usage"][k] for s in sess) for k in ("prompt_tokens", "completion_tokens")}}
                traj = {"sessions": [{k: s[k] for k in ("verdict", "how", "rationale", "trajectory", "tool_calls")} for s in sess]}
            else:
                s = adjudicate(pc, reports, client, variant=a.variant, max_steps=a.max_steps, max_tokens=a.max_tokens,
                               max_per_request=max_req, search=a.search, encoder=enc, observe=a.observe, wide=a.wide,
                               kind_note=(KINDS.get(pc.key) if KINDS.get(pc.key) in ("count", "text") else None)
                               if a.kind_notes else None, log=log)
                if a.swap:                               # back to the contest's own A/B
                    s["verdict"] = FLIP.get(s["verdict"], s["verdict"])
                traj = s.pop("trajectory")
                r = s
            traj = {"picked_views": [rep["picked"] for rep in reports], **(traj or {})}
        row.update(r)
        row["correct"] = (row["verdict"] == c.good_side) if row["verdict"] else None
        with lock:
            counter[0] += 1
            if traj is not None:
                (out / "trajectories" / f"{c.shard}_{pos[c.key]:03d}.json").write_text(json.dumps({**row, "trajectory": traj}, ensure_ascii=False, indent=1), encoding="utf-8")
            with open(res_p, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        log(f"[adj] {counter[0]}/{len(contests)} {c.domain:11s} {c.pair:22s} good={c.good_side} inv={''.join(v or '-' for v in vs)} "
            f"vote={vote} verdict={row['verdict']} ({row['how']}) steps={row['steps']} {row['wall_s']}s"
            + (f" ERR {row['errors'][0][:120]}" if row["errors"] else ""))

    def safe(c):
        try:
            one(c)
        except Exception as e:                       # one broken contest must not stop the run; it is redone on resume
            log(f"[adj] FAILED {c.key}: {type(e).__name__}: {e}")

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        list(ex.map(safe, todo))
    rows = [json.loads(l) for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    s = {"name": a.name, "variant": a.variant, "investigators": runs, "max_steps": a.max_steps, **summarize(rows),
         "requests_sent_this_session": client.sent, "backend": a.backend}
    if a.backend == "baseten":
        from judge.baseten_client import spent
        s["baseten_usd_budget_group"] = round(spent(a.budget_tag or a.name), 4)
    (out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    log("[adj] summary: " + json.dumps(s))


if __name__ == "__main__":
    main()
