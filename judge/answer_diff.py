"""portia/judge/answer_diff.py: where do the two answers differ? (deterministic, no model call)

The degraded answers in this benchmark are near-copies of each other (median 91% word overlap) with a few
details changed: almost always VISUAL ones (a colour, a position, an object, a count, on-screen text). The v1
agent tended to check the first difference it noticed and stop, so the v2 agent is handed the full list
up front: a word-level alignment of A and B, nearby changes merged, each shown in both versions with context.
"""
from __future__ import annotations

import difflib


def answer_diff(a: str, b: str, max_items: int = 24, ctx: int = 6, merge_gap: int = 3) -> str:
    wa, wb = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    blocks = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if blocks and i1 - blocks[-1][1] <= merge_gap and j1 - blocks[-1][3] <= merge_gap:
            blocks[-1] = (blocks[-1][0], i2, blocks[-1][2], j2)         # merge with the previous change
        else:
            blocks.append((i1, i2, j1, j2))
    overlap = sm.ratio()
    if not blocks:
        return "The two answers are word-for-word identical."
    head = (f"{len(blocks)} place(s) where the answers differ (word overlap {100 * overlap:.0f}%). Changed words are in "
            "[brackets]; everything else is identical. Check EVERY item: each side may contain errors.")
    if overlap < 0.5:
        head += (" The answers are worded very differently, so this list is long and noisy: compare them claim by "
                 "claim as well.")
    out = [head]
    for n, (i1, i2, j1, j2) in enumerate(blocks[:max_items], 1):
        pa, qa = " ".join(wa[max(0, i1 - ctx):i1]), " ".join(wa[i2:i2 + ctx])
        pb, qb = " ".join(wb[max(0, j1 - ctx):j1]), " ".join(wb[j2:j2 + ctx])
        out.append(f"{n}. A: \"…{pa} [{' '.join(wa[i1:i2]) or '(nothing)'}] {qa}…\"\n"
                   f"   B: \"…{pb} [{' '.join(wb[j1:j2]) or '(nothing)'}] {qb}…\"")
    if len(blocks) > max_items:
        out.append(f"(+{len(blocks) - max_items} more differences not shown)")
    return "\n".join(out)


def shared_text(a: str, b: str) -> str:
    """The words both answers share, in order: the scene descriptions without the disputed details. As a search
    query it finds the evidence moments far better than the question (analysis/retrieval_queries.py: evidence clips
    covered by the top 64 segments 29% -> 49%)."""
    wa, wb = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    return " ".join(" ".join(wa[i1:i2]) for op, i1, i2, _, _ in sm.get_opcodes() if op == "equal")


def retrieval_text(question: str, a: str, b: str) -> str:
    """v4's retrieval query: the question plus the answers' shared text."""
    return question + " " + shared_text(a, b)

