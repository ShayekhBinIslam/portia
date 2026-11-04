# 000: Portia context for reviewers

Status: **reference** (kept current). Written by the Portia coding agent (Claude).

## What Portia is

Portia is a **judge for two-hop questions about long videos.** A two-hop question links two moments, often in
different videos, through a bridge entity or event. Two models answered each question. The judge sees the question
and both answers, investigates a library of long videos, and decides which answer is better (A or B).

- **The two answers are near-copies.** One is better (the gold answer or a higher-rated one). The other differs in a
  few degraded visual details: colour, object identity, position, count, setting, on-screen text.
- **Data:** 630 contests from the final campaign (`judge/contests.py`, `DATASET`), split into six shards.
- **Purpose:** the project is being submitted to the Meta Global AI Developer Hackathon (`meta_hackathon/`; new work
  is listed in `meta_hackathon/NEW_WORK.md`).

## What each shard has been used for

| Shard | Contests | Use so far |
|---|---|---|
| 1 | 31 | Nemotron pilot (tools v1), Qwen v1-v3 development. **Muse: being run now as baselines only (plan 002).** |
| 2 | 63 | Nemotron pre-registered test (tools vs static: not confirmed), Qwen static. **Muse: as shard 1.** |
| 3 | 94 | Muse development and tuning: every Muse design decision was made here. Also Qwen and Nemotron work. |
| 4 | 126 | Pre-registered retrieval tests (Nemotron: confirmed; Qwen: not). Muse replication and development comparisons. |
| 5 | 158 | Pre-registered Muse test (tuned agent vs static: not confirmed). Then 3 seeds each of three setups. |
| 6 | 158 | Pre-registered Muse test (vote of 3 agents vs vote of 3 static: not confirmed). Then 3 seeds each. |

**No shard is untouched any more.** Shards 1-2 have never been judged by Muse. Shards 5-6 were used only for
evaluation, never to choose a design. Plans must not tune on per-contest results from shards 1, 2, 5 or 6.

**The shards were split by contest, not by question**. The 630 contests come from 343 questions,
each with 5 candidate answers: the gold answer and 4 graded degradations (`rating_4` to `rating_1`). A question can
appear in several shards with different answer pairs. It then shares its videos and gold answer across those shards.

- 172 of the 410 contests in shards 1, 2, 5 and 6 (42%) share a question with shards 3-4. 77 of them (19%) share one
  with shard 3, where Muse was tuned.
- The questions barely share videos with each other. The 343 questions form 334 groups linked by a shared video, and
  only 9 videos are used by two questions.
- **For prompt and tool design**, the overlap is a small risk. **For anything that trains weights**, it is direct
  leakage: splits must be by question (grouped by shared video), never by shard.

## The judge model and serving

- **Muse Glimmer 30B** (Meta open weights), served locally on the box's RTX PRO 6000 GPUs 0 and 3 by vLLM 0.32 with
  DFlash speculative decoding. The server is `scripts/serve_muse.sh`, running in venv `.venv-muse`, served as `mg30`
  on ports 18660 (GPU 3) and 18661 (GPU 0).
- **Sampling** is temperature 1.0, top-p 0.95, top-k 64, with a seed derived from the request body
  (`judge/local_client.py`). Reasoning strength is `high`.
- **Earlier judges:** Nemotron on OpenRouter, and Qwen3.8-27B locally.
- **The Meta API credits (`meta_hackathon/meta_hack.env`) are LOCKED.** `judge/meta_lock.py` refuses Meta-hosted
  endpoints. The verifier model Muse Spark is planned for later, on the user's go.

## The two judging setups

1. **Static** (`judge/static_baseline.py`): one request with 128 frames, 2 each from the top 64 retrieved
   segments, plus their transcripts and the campaign rubric. Payloads come from `judge/static_rebuild.py`. Retrieval
   is either by the question alone or by the question plus the text both answers share ("answer-grounded").
2. **Tool agent** (`judge/run.py`, `judge/agent.py`, `judge/tools.py`): up to N turns with tools for search,
   transcripts, frame strips, contact sheets and zoom. Toolsets v1-v5 exist.
   - The best agent is **"tuned v4"**: `--tools v4 --keep-reasoning --budget-note --final-full-reasoning`.
   - It includes a two-level verdict fallback: first `answer` as the only tool, then a structured A/B choice.

**Prompts and tool definitions live in files**: `prompts/`, `tools/` and `judge/prompting.py`, mapped in
`prompts/README.md`. `tests/golden_requests.py` proves that a refactor leaves every request byte-identical.

## Results so far (Muse Glimmer)

Held-out shards 5 and 6, 316 contests, three seeds per setup, verdicts by vote:

| Setup | Accuracy | Paired comparison |
|---|---|---|
| Static, question retrieval | 70.6% | the simple baseline |
| Static, shared-text retrieval | 76.3% | vs question: 35 vs 17, p = 0.018 |
| Tool agent, tuned v4 | 75.3% | vs question: p = 0.11; vs shared-text static: 25 vs 28, p = 0.78 |

- **Things that gave no gain beyond noise:** `xhigh` reasoning, tools v5, the look-first prompt, blind inspect
  (a second look by the same model), native-aspect frames, votes of 5, and 15 to 25 turns.
- **30 turns** came out about +2.5 points in all 3 runs; that is not significant.
- **Voting** over 3 seeds: about +2 points. A vote of 5 is no better than a vote of 3 (75.0% vs 75.5% on shards 3-4).
- **Plan 004 (development, shards 3-4):** an adjudicator that sees only the three agents' looks (not their verdicts) beats their vote by +3.6 pooled. An adjudicator that also sees the reports gains +0.7. The held-out test is pending review (`runs/PREREG_adjudicator.json`, draft).
- **The ground-truth meta-analysis:** the losing judge usually found the same disputed detail as the winner and then
  judged it the wrong way. The bottleneck is how well Muse judges what it sees, not finding the moment.

## Where things are

- **Per-run results:** `runs/<name>/results.jsonl` and `runs/<name>/trajectories/`.
- **Pre-registrations and their outcomes:** `runs/PREREG_*.json`.
- **The running log:** `runs/LOG_24h.md`.
- **The trace explorer:** `viz/` (http://127.0.0.1:5240). Its Ideas tabs have per-case ground-truth analyses.

## Standing rules

- **The hackathon uses Muse models only** (the user): Muse Glimmer now, and Muse Spark later if the user unlocks the Meta credits. Qwen, Nemotron and other models are for after the hackathon. Plans put mixed-model ideas in a "post-hackathon" section.
- No `rm` or other deletion without the user's permission; old material moves to `zarxiv/`.
- GPUs 0 and 3 only. Never use the H200 beta pod.
- Process titles are `shayekh-<id>`.
- The Meta API keys are never read or printed.
