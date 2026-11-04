"""portia/judge/agent.py: the tool-using judge loop for ONE contest.

    messages = system rubric + (question, answer A, answer B, initial evidence)
    repeat <= max_steps:   model -> tool calls -> execute -> tool results (+ frames as a user message)
    stop on `answer`;  at the budget, one last call with tool_choice forced to `answer`

Every request is one OpenRouter call (free tier: 50/day); the step budget is therefore also the
per-contest quota budget. The full trajectory (messages without image bytes, tool calls, timings,
usage) is returned for logging.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from pathlib import Path

from judge import corpus, prompting
from judge.answer_diff import answer_diff, retrieval_text
from judge.tools import TOOLS, TOOLS_V2, Toolbox, hires_tools, v5_tools

ROOT = Path(__file__).resolve().parents[1]
# Every prompt and message lives in a file (prompts/README.md is the map); judge/prompting.py loads them.
SYSTEM = prompting.system("system.md")
SYSTEM_V2 = prompting.system("system_v2.md")
SYSTEM_V3 = prompting.system("system_v3.md")
SYSTEM_V5 = prompting.system("system_v5.md")
# Look-first: the tuned agent made ~6.6 text-tool calls per contest vs ~3.5 visual ones, and 11% of contests
# never looked at the right video. This prompt makes looking the rule; the agent loop adds a running tally.
SYSTEM_LOOK = prompting.system("system_v4look.md")
TEXT_TOOLS = {"search", "search_video", "grep_transcripts", "read_transcript", "list_videos"}
LOOK_TOOLS = {"zoom", "view_frames", "contact_sheet", "burst"}

# "Blind" inspect (idea 1 of analysis/lit_tools.md, after Deep Video Discovery's frame inspection and
# Chain-of-Verification): 31 of the tuned agent's 57 dev errors came AFTER it looked at the evidence moment. After each
# zoom or burst, Muse answers neutral questions about the disputed details in a fresh context that holds only that
# image: no question, no answers, no trace, so neither answer's wording can steer what it reports seeing.
INSPECT_SYS = prompting.render("inspect/system.j2")
INSPECT_NOTE = prompting.render("inspect/note.j2")
QSCHEMA = prompting.schema("questions.schema.json")
ASCHEMA = prompting.schema("answers.schema.json")
IMAGE_DROPPED = prompting.render("agent/image_dropped.j2")


def judge_setup(toolset: str, zoom_side: int = 1024, look_first: bool = False, inspect: bool = False) -> tuple[str, list]:
    """(system prompt, tool list) of a run with these options; inspect=True means the contest got its questions."""
    v2, v3, v5 = toolset in ("v2", "v3", "v4", "v5"), toolset in ("v3", "v4", "v5"), toolset == "v5"
    tools = v5_tools() if v5 else TOOLS_V2 if v2 else TOOLS
    if zoom_side != 1024 and not v5:               # hi-res zoom: bigger images + a description that asks for regions
        tools = hires_tools(tools)
    system = SYSTEM_LOOK if look_first and v3 and not v5 else SYSTEM_V5 if v5 else SYSTEM_V3 if v3 else SYSTEM_V2 if v2 else SYSTEM
    return system + (INSPECT_NOTE if inspect else ""), tools


def _json_obj(text: str):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def _inspect_questions(client, contest, temperature: float) -> list[str]:
    prompt = prompting.render("inspect/questions.j2", question=contest.question, diff=answer_diff(contest.answer_a, contest.answer_b))
    r = client.chat([{"role": "user", "content": prompt}], temperature=temperature, max_tokens=4096,
                    reasoning={"effort": "low"}, structured_outputs={"json": QSCHEMA})
    content = r["choices"][0]["message"].get("content") or ""
    d = _json_obj(content)
    qs = [str(q).strip() for q in (d or {}).get("questions", []) if str(q).strip()]
    if not qs:                    # Muse answered with plain lines (bulleted, numbered or bare) instead of the JSON schema
        qs = [re.sub(r"^(?:[-*\u2022]|\d+[.)])\s+", "", ln.strip()) for ln in content.splitlines()]
        qs = [q for q in qs if q.endswith("?")]
    return qs[:6]


def _inspect(client, questions: list[str], images: list, temperature: float) -> str:
    parts = [_img_part(im) for im in images]
    parts.append({"type": "text", "text": prompting.render("inspect/ask.j2", questions=questions)})
    r = client.chat([{"role": "system", "content": INSPECT_SYS}, {"role": "user", "content": parts}], temperature=temperature,
                    max_tokens=4096, reasoning={"effort": "low"}, structured_outputs={"json": ASCHEMA})
    d = _json_obj(r["choices"][0]["message"].get("content"))
    lines = []
    for a in (d or {}).get("answers", []):
        try:
            q = questions[int(a.get("q")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        lines.append(f"- {q} -> {str(a.get('answer', '')).strip()}" + ("" if a.get("visible") else " (not visible here)"))
    if not lines:                 # not JSON: pass the plain answer through
        lines = [ln.rstrip() for ln in (r["choices"][0]["message"].get("content") or "").strip().splitlines()[:14] if ln.strip()]
    return prompting.render("inspect/result.j2", lines=lines)


def _img_part(im) -> dict:
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=85)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()}}


def _prune_images(messages: list, keep: int, pinned: int = 0) -> list:
    """Send only the most recent `keep` images; older ones become a text stub (they are still in the log).
    The first `pinned` messages are never pruned (v3 pins its overview sheets in the first user message)."""
    seen, out = 0, []
    for j, m in reversed(list(enumerate(messages))):
        if j >= pinned and isinstance(m.get("content"), list):
            parts = []
            for p in reversed(m["content"]):
                if p.get("type") == "image_url":
                    seen += 1
                    parts.append(p if seen <= keep else {"type": "text", "text": IMAGE_DROPPED})
                else:
                    parts.append(p)
            m = {**m, "content": list(reversed(parts))}
        out.append(m)
    return list(reversed(out))


def _loggable(messages: list) -> list:
    """The conversation without image bytes."""
    out = []
    for m in messages:
        if isinstance(m.get("content"), list):
            m = {**m, "content": [p if p.get("type") != "image_url" else {"type": "image_url", "image_url": "<jpeg>"}
                                  for p in m["content"]]}
        out.append(m)
    return out


def _text_verdict(text: str) -> str | None:
    m = re.findall(r"\[\[([AB])\]\]|\bverdict\W{0,3}([AB])\b", text or "", re.I)
    return (m[-1][0] or m[-1][1]).upper() if m else None


def judge(contest, client, encoder, max_steps: int = 8, max_images: int = 24, keep_images: int = 12,
          initial_k: int = 8, temperature: float = 0.0, max_tokens: int = 4096, extend: int = 0,
          strict_replay: bool = False, toolset: str = "v1", keep_reasoning: bool = False, budget_note: bool = False,
          final_low: bool = True, zoom_side: int = 1024, inspect: bool = False, look_first: bool = False,
          focus_part: tuple | None = None, max_per_request: int | None = None, look_around: bool = False,
          log=print) -> dict:
    """extend > 0: a contest that reaches the budget is granted `extend` more turns instead of being forced.
    Its first max_steps turns are byte-identical to the plain agent's, so they replay from the response cache;
    strict_replay makes any cache miss before the extension raise CacheMiss instead of sending a request.
    toolset "v2": + search_video / contact_sheet / zoom, prompts/system_v2.md, and the answer diff up front.
    keep_reasoning: each assistant turn goes back into the history WITH its reasoning (interleaved thinking; Muse
    Glimmer's template renders it as the to=self channel), so the model keeps its plan across tool turns.
    budget_note: after each tool turn the model is told how many turns are left (Muse used all 8 every time).
    final_low=False: the forced final answer keeps the run's reasoning strength instead of dropping to low effort
    (the low-effort final turn was a fix for Nemotron/Qwen truncating; a truncated turn is still retried at low)."""
    v2, v3 = toolset in ("v2", "v3", "v4", "v5"), toolset in ("v3", "v4", "v5")     # v3 = v2 + the overview pack (judge/overview.py)
    v4 = toolset in ("v4", "v5")  # v4 = v3 retrieved by question + the answers' shared text instead of the question
    v5 = toolset == "v5"          # v5 = v4 + zoom shown next to the whole frame + burst (judge/tools.py)
    rq = retrieval_text(contest.question, contest.answer_a, contest.answer_b) if v4 else contest.question
    _, tools = judge_setup(toolset, zoom_side=zoom_side, look_first=look_first)
    t0 = time.time()
    box = Toolbox(contest, encoder, max_images=max_images, log=log, toolset="v5" if v5 else "v2" if v2 else "v1", zoom_side=zoom_side)
    questions, n_inspect = [], 0
    if inspect and getattr(client, "supports_choice", False):
        try:
            questions = _inspect_questions(client, contest, temperature)
        except Exception as e:                       # no questions: the run goes on without the independent look
            log(f"[inspect] questions failed: {type(e).__name__}: {e}")
    init, _ = box.search(rq, k=initial_k)          # v1-v3: the question, the same first step a static judge gets
    diff = answer_diff(contest.answer_a, contest.answer_b) if v2 else None
    # plan 005 idea G ("divided investigators"): focus_part = (k, n) asks this agent to check the differences numbered
    # k+1, k+1+n, ... first; without it the first message is byte-identical to before (tests/golden_requests.py)
    focus = None
    if focus_part and diff:
        k, n_of = focus_part
        focus = [int(x) for x in re.findall(r"^(\d+)\. A: ", diff, re.M) if (int(x) - 1) % n_of == k] or None
    user = prompting.render("agent/first_message.j2", question=contest.question, answer_a=contest.answer_a,
                            answer_b=contest.answer_b, diff=diff, focus=focus, focus_of=(focus_part or (0, 0))[1],
                            n_playlists=len(box.playlists), grounded=v4, init=init, max_steps=max_steps, parallel=v2)
    first = user
    if v3:
        from judge import overview
        segs = overview.segments(encoder.encode([rq])[0], box.playlists, k=64)
        sh = overview.sheets(segs)
        first = [{"type": "text", "text": prompting.render("agent/overview.j2", first=user, grounded=v4,
                                                         transcripts=overview.transcript_block(segs), n_sheets=len(sh))}]
        first += [_img_part(im) for im, _ in sh]
    system, _ = judge_setup(toolset, zoom_side=zoom_side, look_first=look_first, inspect=bool(questions))
    if max_per_request:
        # an API that caps images per request (Baseten: 8), as in judge/adjudicate.py: the pinned overview sheets keep at
        # most max_per_request - 2 images (the last ones beyond that are dropped), and the agent's own looks get the rest
        n_first = 0
        if isinstance(first, list):
            idx = [i for i, p in enumerate(first) if p.get("type") == "image_url"]
            for i in idx[max(1, max_per_request - 2):]:
                first[i] = {"type": "text", "text": IMAGE_DROPPED}
            n_first = min(len(idx), max(1, max_per_request - 2))
        keep_images = max(1, min(keep_images, max_per_request - n_first))
    n_text, n_look, text_streak = 0, 0, 0
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": first}]
    steps, verdict, rationale, how, errors, recovered = [], None, "", None, [], 0
    for step in range(max_steps + extend + 1):
        final = step == max_steps + extend
        if final:
            messages.append({"role": "user", "content": prompting.render("agent/budget_final.j2")})
        elif extend and step == max_steps:
            messages.append({"role": "user", "content": prompting.render("agent/budget_extend.j2", max_steps=max_steps, extend=extend)})
        replay = {"cache_only": True} if strict_replay and step < max_steps else {}
        tc = {"type": "function", "function": {"name": "answer"}} if final else "auto"
        # The model's hidden reasoning can eat the whole output budget on a long context (seen: ~17k chars,
        # finish_reason "length", EMPTY message, no tool call -> no verdict). The final turn only has to commit,
        # so it runs at low reasoning effort with room to spare; any turn that comes back empty and truncated
        # is retried once the same way.
        roomy = {"max_tokens": max(max_tokens, 8192), "reasoning": {"effort": "low"}}
        try:
            send = _prune_images(messages, keep_images, pinned=2 if v3 else 0)
            last = roomy if final_low else {"max_tokens": roomy["max_tokens"]}
            resp = client.chat(send, tools=tools, tool_choice=tc, temperature=temperature,
                               **(last if final else {"max_tokens": max_tokens}), **replay)
            m0, ch0 = resp["choices"][0].get("message") or {}, resp["choices"][0]
            if not m0.get("content") and not m0.get("tool_calls") and ch0.get("finish_reason") == "length":
                recovered += 1
                resp = client.chat(send, tools=tools, tool_choice=tc, temperature=temperature, **roomy, **replay)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
            how = "error"
            break
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        steps.append({"step": step, "latency_s": resp.get("_latency_s"), "usage": resp.get("usage"),
                      "finish_reason": resp["choices"][0].get("finish_reason"),
                      "content": (msg.get("content") or "")[:2000],
                      "reasoning_chars": len(msg.get("reasoning") or ""), "reasoning": (msg.get("reasoning") or "")[:20000],
                      "tool_calls": [{"name": c["function"]["name"], "args": c["function"].get("arguments")} for c in calls]})
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         **({"tool_calls": calls} if calls else {}),
                         **({"reasoning": msg["reasoning"]} if keep_reasoning and msg.get("reasoning") else {})})
        if not calls:                                   # plain text: accept an explicit verdict, else nudge
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
            else:
                text, imgs = box.run(name, args)
                if questions and name in LOOK_TOOLS and imgs:     # every tool that shows images (Muse zooms rarely)
                    try:
                        text += "\n\n" + _inspect(client, questions, [im for im, _ in imgs], temperature)
                        n_inspect += 1
                    except Exception as e:
                        log(f"[inspect] failed: {type(e).__name__}: {e}")
                frames += [(c["id"], im, ts) for im, ts in imgs]
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": text})
        if done:
            break
        left = max_steps + extend - (step + 1)
        names = [c["function"]["name"] for c in calls]
        n_text += sum(n in TEXT_TOOLS for n in names)
        n_look += sum(n in LOOK_TOOLS for n in names)
        text_streak = 0 if any(n in LOOK_TOOLS for n in names) else text_streak + 1
        note = prompting.render("agent/turn_note.j2", budget_note=budget_note, look_first=look_first, left=left,
                                n_text=n_text, n_look=n_look, text_streak=text_streak,
                                look_around=look_around).strip()          # plan 019: only when two turns are left
        if note and not frames:
            messages.append({"role": "user", "content": note})
        if frames:                                       # images go back as ONE user message after the tool results
            label = lambda ts: corpus.mmss(ts) if isinstance(ts, (int, float)) else str(ts)      # noqa: E731
            parts = [{"type": "text", "text": prompting.render("agent/images_message.j2", v2=v2, note=note,
                                                         labels=[label(ts) for _, _, ts in frames])}]
            parts += [_img_part(im) for _, im, _ in frames]
            messages.append({"role": "user", "content": parts})
    fallback = False
    if verdict is None and how != "error" and steps:
        # The forced turn names `answer` in tool_choice, but vLLM does not enforce a named tool choice for every tool
        # format: with Muse Glimmer's ATEM calls, 7 of 94 shard-3 contests called search_video there and ended
        # without a verdict. One more request in which `answer` is the only tool.
        fallback = True
        messages.append({"role": "user", "content": prompting.render("agent/fallback_answer_only.j2")})
        params = {"max_tokens": max(max_tokens, 8192), **({"reasoning": {"effort": "low"}} if final_low else {})}
        try:
            send = _prune_images(messages, keep_images, pinned=2 if v3 else 0)
            resp = client.chat(send, tools=[t for t in tools if t["function"]["name"] == "answer"],
                               tool_choice={"type": "function", "function": {"name": "answer"}}, temperature=temperature, **params)
            msg = resp["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            steps.append({"step": len(steps), "latency_s": resp.get("_latency_s"), "usage": resp.get("usage"),
                          "finish_reason": resp["choices"][0].get("finish_reason"), "content": (msg.get("content") or "")[:2000],
                          "reasoning_chars": len(msg.get("reasoning") or ""), "reasoning": (msg.get("reasoning") or "")[:20000],
                          "tool_calls": [{"name": c["function"]["name"], "args": c["function"].get("arguments")} for c in calls],
                          "answer_fallback": True})
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
                # Muse still called tools that were not offered (view_frames, search, ...: 7 of 94 tuned contests), and
                # vLLM's parser accepted them. Last resort on a local vLLM: no tools, and after its reasoning the reply
                # is constrained to the single letter A or B (structured outputs).
                for c in calls:                          # the history needs a result for every call it made
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": prompting.render("agent/fallback_tool_closed.j2")})
                messages.append({"role": "user", "content": prompting.render("agent/fallback_choice.j2")})
                send = _prune_images(messages, keep_images, pinned=2 if v3 else 0)
                resp = client.chat(send, temperature=temperature, structured_outputs={"choice": ["A", "B"]}, **params)
                msg = resp["choices"][0]["message"]
                # the constrained letter ends the reply; Muse may first open a tool message (" <|start|>assistant
                # to=search_video<|message|><atem:function_calls>\nA"), so read the letter at the end
                m = re.search(r"([AB])\s*$", msg.get("content") or "")
                v = m.group(1) if m else None
                steps.append({"step": len(steps), "latency_s": resp.get("_latency_s"), "usage": resp.get("usage"),
                              "finish_reason": resp["choices"][0].get("finish_reason"), "content": (msg.get("content") or "")[:2000],
                              "reasoning_chars": len(msg.get("reasoning") or ""), "reasoning": (msg.get("reasoning") or "")[:20000],
                              "tool_calls": [], "answer_fallback": "choice"})
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                if v in ("A", "B"):
                    verdict, how = v, "forced"
                    rationale = "(tools closed; verdict constrained to A/B) " + (msg.get("reasoning") or "")[-600:]
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
    good = contest.good_side
    return {"key": contest.key, "qid": contest.qid, "pair": contest.pair, "occurrence": contest.occurrence,
            "shard": contest.shard, "domain": contest.domain, "gap": contest.gap,
            "good_side": good, "verdict": verdict, "correct": (verdict == good) if verdict else None,
            "how": how, "rationale": rationale, "steps": len(steps), "tool_calls": box.calls,
            "images_viewed": box.images_used, "errors": errors, "wall_s": round(time.time() - t0, 1),
            "recovered_truncations": recovered, "extended": bool(extend) and len(steps) > max_steps, "answer_fallback": fallback,
            "inspect_questions": questions, "inspect_calls": n_inspect, **({"focus": focus} if focus_part else {}),
            "usage": {k: sum((s["usage"] or {}).get(k, 0) or 0 for s in steps) for k in ("prompt_tokens", "completion_tokens")},
            "trajectory": {"steps": steps, "messages": _loggable(messages)}}
