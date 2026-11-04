"""portia/analysis/gt_match.py: does a judge's text name the detail that separates the two answers? (dataset ground truth)

The degradations that separate the two answers come from the benchmark's records (analysis/tool_failures.py);
gt_check says, per degradation, which answer carries it and whether each judge's rationale names it. Used by
analysis/spark_qualitative.py (plan 006). No model call.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tool_failures import detail_categories, differing_details  # noqa: E402


STOP = set("the a an of in on at to and or for with from by is are was were be as that this its their his her into than "
           "then also only actual both each other which while where when what who whom over under between".split())


def _norm(t: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(t or "")).split())


def _phrases(element: str) -> list[str]:
    """The changed content a degradation names: its quoted phrases, else its content words."""
    q = re.findall(r"['‘“\"]([^'’”\"]{3,80})['’”\"]", element or "")
    return [_norm(x) for x in q if _norm(x)] or [" ".join(w for w in _norm(element).split() if w not in STOP and len(w) > 3)]


def _caught(phrases: list[str], text: str) -> bool:
    t = _norm(text)
    for ph in phrases:
        if ph and ph in t:
            return True
        ws = [w for w in ph.split() if w not in STOP and len(w) > 3]
        if len(ws) >= 2 and sum(w in t.split() for w in ws) / len(ws) >= 0.6:
            return True
    return False


def gt_check(rec: dict, c, texts: dict) -> dict:
    """Every degradation that separates the two answers (dataset ground truth), on which answer (A/B) it sits, and
    whether each judge's text (rationale / output / reasoning) names it."""
    better, worse = c.pair.split("_vs_")
    label = {better: c.good_side, worse: "B" if c.good_side == "A" else "A"}
    rows = []
    for d in differing_details(rec, c.pair):
        ph = _phrases(d.get("element"))
        rows.append({"answer": label.get(d["side"], "?"), "worse": d["side"] == worse, "element": d.get("element"),
                     "cats": detail_categories(d), "caught": {k: _caught(ph, v) for k, v in texts.items()}})
    summ = {k: {"worse_named": sum(r["caught"][k] for r in rows if r["worse"]), "worse_n": sum(r["worse"] for r in rows),
                "any_named": sum(r["caught"][k] for r in rows)} for k in texts}
    return {"details": rows, "summary": summ}
