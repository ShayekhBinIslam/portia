#!/usr/bin/env python3
"""portia/analysis/spark_agent_cost.py: what would Muse Spark Open cost as the AGENT (not just the adjudicator)?

    python analysis/spark_agent_cost.py

Spark Open has never run as the agent, so this re-prices the logged Glimmer agent turns (tuned v4, finished dev runs on
shards 3-4) as Baseten requests. Measured constants:
  * 823 tokens per image for BOTH models (least squares on the adjudicators' first requests: Spark R2 .95 on 287,
    Glimmer R2 .97 on 2105; text ~5.6 characters per token for both): same vision encoder and tokenizer.
  * Baseten takes at most 8 images per request: pinned first-message images <= 6 and the agent's own looks fill the rest,
    newest first (the rule judge/adjudicate.py uses), instead of all pinned + the newest 12.
  * 28.4% of Spark's input was billed as cached in plan 006; Spark writes 1.35x Glimmer's output on the same 282
    adjudications.
"""
from __future__ import annotations

import glob
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOK_IMG = 823                                         # tokens per image, both models
P_IN, P_CACHED, P_OUT = 1.25e-6, 0.15e-6, 4.25e-6     # USD per token (Baseten)
CACHED = 0.284                                        # share of Spark input billed as cached in plan 006
OUT_RATIO = 1.35                                      # Spark / Glimmer output tokens on the same 282 adjudications


def n_img(c) -> int:
    return sum(1 for p in c if isinstance(p, dict) and p.get("type") == "image_url") if isinstance(c, list) else 0


def contest(T: dict) -> tuple:
    """Glimmer input, Spark input (images capped at 8 per request), output, requests, pinned images, Spark images/request."""
    m, steps = T["messages"], T["steps"]
    n_first = n_img(m[1]["content"])
    asst = [j for j, x in enumerate(m) if x.get("role") == "assistant"]
    g_in = s_in = 0
    s_imgs = []
    for i, s in enumerate(steps):
        u = (s.get("usage") or {}).get("prompt_tokens")
        if not u:
            continue
        own = sum(n_img(x["content"]) for x in m[2:asst[i] if i < len(asst) else len(m)])
        pin = min(n_first, 6)
        g_kept, s_kept = n_first + min(own, 12), pin + min(own, max(1, 8 - pin))
        g_in += u
        s_in += u - max(0, g_kept - s_kept) * TOK_IMG
        s_imgs.append(s_kept)
    out = sum((s.get("usage") or {}).get("completion_tokens") or 0 for s in steps)
    return g_in, s_in, out, len(steps), n_first, st.mean(s_imgs) if s_imgs else 0


def main():
    for label, pre in (("8-turn agent (standard)", "mg_v4t"), ("30-turn agent", "mg_v4t_t30")):
        G = []
        for s in ("s3", "s4"):
            for nm in [f"{pre}_{s}"] + [f"{pre}_r{i}_{s}" for i in range(1, 11)]:
                if (ROOT / "runs" / nm / "summary.json").exists():
                    for f in glob.glob(str(ROOT / "runs" / nm / "trajectories" / "*.json")):
                        T = json.loads(Path(f).read_text(encoding="utf-8")).get("trajectory") or {}
                        if T.get("messages") and T.get("steps"):
                            G.append(contest(T))
        g_in, s_in, out = (st.mean(x[i] for x in G) for i in range(3))
        usd_in, usd_out = s_in * ((1 - CACHED) * P_IN + CACHED * P_CACHED), out * OUT_RATIO * P_OUT
        hi = g_in * P_IN + usd_out                                        # no image-cap saving and nothing cached
        print(f"{label}: {len(G)} contest traces; requests {st.mean(x[3] for x in G):.1f}; first-message images "
              f"{st.mean(x[4] for x in G):.1f}; Spark images/request {st.mean(x[5] for x in G):.1f}\n"
              f"   input/contest Glimmer {g_in:,.0f} -> Spark {s_in:,.0f}; output {out:,.0f} -> {out * OUT_RATIO:,.0f}\n"
              f"   Spark per contest ${usd_in + usd_out:.3f} (input ${usd_in:.3f} + output ${usd_out:.3f}); upper bound ${hi:.3f}")


if __name__ == "__main__":
    main()
