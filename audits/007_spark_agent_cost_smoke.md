# 007: Muse Spark Open as the whole agent: a measured cost (10-contest smoke)

Status: **done** ($1.85 of the $3). Approved by the user: "cool, let's get a nubmer of $3 then, we need good
pitch". Written by the Portia coding agent (Claude).

## Why

The hackathon pitch compares two designs:

- **Ours:** three local Muse Glimmer agents; Spark Open on Baseten decides only the contested contests. Measured cost:
  $0.017 per contest, from plan 006.
- **Spark Open alone:** the obvious alternative. Estimated at about $0.27 per contest by re-pricing the logged Glimmer
  agent turns (`analysis/spark_agent_cost.py`; plan 006 revision log).

An estimate is weak in a pitch. This run measures the second design on real contests.

## Design

- **The agent is unchanged:** the tuned v4 agent our Glimmer investigators use. Same prompts, tools and flags:
  - 8 turns;
  - reasoning kept across turns;
  - turns-left note;
  - full-strength final answer.
- **Only the model changes**, to Spark Open (Baseten, `reasoning_effort` high).
- **Baseten takes at most 8 images per request.** The agent uses the rule of plan 006's adjudicator:
  - the first message keeps at most 6 of its 8 overview sheets;
  - the agent's own looks get the rest, newest first.
  - The estimate assumed the same rule.
- **Sent-back reasoning is rendered by Baseten.** Checked on plan 006's 902 consecutive Spark requests: 0.175 input
  tokens per reasoning character, against 0.179 if fully counted. So keeping reasoning across turns works as with Glimmer.
- **Contests:** 10 development contests, shard 4 positions 0, 13, 26, …, 117.
  - Evenly spaced, because the shard is ordered by domain. They cover 7 domains.
  - No held-out shard is touched.
- **Budget:** $3, the user's figure. New requests stop at $2.80, so that requests in flight stay under $3.
  - Spend is logged per request as in plan 006 (`runs/baseten_spend.jsonl`, tag `plan007_spark_agent`).
  - If the cap stops the run early, the cost per contest is reported from the finished contests.

## What is reported

1. **Measured Spark cost per contest:**
   - its mean and range;
   - requests per contest;
   - input, cached input and output tokens.
   - Against the estimate of $0.27 (at most $0.38) and the combination's measured $0.017.
2. **Accuracy, descriptive only:** 10 contests cannot rank designs. Reported:
   - Spark's verdicts against each of the 11 Glimmer agent seeds on the same 10 contests;
   - the combination's verdicts on those contests (plan 006 triples).
3. **Latency per contest.**

## Code changes

- `judge/agent.py`: `max_per_request`, the same cap as `judge/adjudicate.py`. With the default (`None`) every request is
  byte-identical to before; checked with `tests/golden_requests.py`.
- `judge/run.py`:
  - `--backend baseten` (with `--budget-usd` and `--budget-tag`);
  - a budget stop ends the run cleanly, like a quota stop.

## Revision log

- written.
- first contest as a check.
  - Tool calls and the forced final answer parse.
  - It cost $0.183 for 9 requests, 277,000 input tokens (58% billed as cached) and 3,400 output tokens.
- **done; all 10 contests finished, $1.85 in total** (`runs/plan007_report.md`;
  `analysis/spark_agent_report.py`).
  - **Measured cost of Spark Open as the agent: $0.185 per contest.**
    - Range $0.054-$0.259; 7.6 requests; 235,000 input tokens, 51% billed as cached; 5,700 output tokens.
    - About 2.1 minutes per contest.
    - Below the $0.27 estimate, because more input was cached than in plan 006 (51% against 28%).
  - **Against the combination's measured $0.017 per contest,** one Spark agent costs about 11 times as much: the
    combination saves 91%.
    - Three Spark agents with a vote would cost about $0.57 per contest, about 33 times as much.
  - **Accuracy on these 10 contests (descriptive only):**
    - Spark agent: 6 of 10.
    - A Glimmer agent: 68% (mean of 11 seeds).
    - The combination: 72% (mean of 5 triples).
    - Two contests defeated every system: all 11 Glimmer seeds, all 5 combination triples and Spark.
    - Ten contests cannot rank designs; the combination's development accuracy is 80.4% over 1,100 contest-triples.
  - **Latency:** the Spark agent is faster per contest (about 2 minutes on Baseten) than the local Glimmer agents (about
    4-5 minutes each with 12 contests sharing a GPU). The combination also waits for the adjudication on contested
    contests.

