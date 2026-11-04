# 013: Muse Spark 1.3 Contributor on the Meta Model API

Status: **done: both steps run (user-approved, including benchmark content); $1.29 of the $2 cap spent**. Written by the Portia coding
agent (Claude).

## Why

The user, on the Contributor pricing card: "it looks cheap, could we smoke and check cost in meta api", then "please
unlock cap $2".

- **Price** (dev.meta.ai pricing): $0.10 per million input tokens, $0.002 cached, $0.20 output. Standard Spark 1.3,
  and Spark Open on Baseten, cost $1.25 / $0.15 / $4.25.
- **Rate limits:** 150 requests and 3M tokens per minute.
- **Data use:** "content may be used to train future Meta models".

## Access

- **The narrow unlock:** `meta_hackathon/.meta_locked` carries "UNLOCKED: META_DEV_KEY for model
  muse-spark-1.3-contributor only".
- **Code:** `judge/meta_lock.dev_key()` returns that one variable. `check()` allows `https://api.meta.ai/v1` and still
  refuses every other Meta host.
- **Spend:** logged per request in `runs/meta_spend.jsonl`, with a $2 cap (`META_DEV_CAP_USD`).
- **No benchmark content** (the dataset's questions and answers) is sent without the user's separate OK, since the
  tier may train on it.

## Smoke (`analysis/meta_api_smoke.py`): $0.0004 in all

- **Access from Korea works.** The model answered all three requests in 2.7-9 s.
- **Images:** three 320x240 frames of the public "Me at the zoo" clip cost about 110 tokens each. With them, the model
  answered a made-up A/B question correctly: "A — Behind the man, elephants with visible trunks and tusks stand in the
  fenced enclosure."
- **It reasons by default:** 160 output tokens for "Reply with the single word OK".
- **Caution:** asked the same question with no images at all, it answered "The frames show elephants…". It asserts
  visual evidence it never received.

## Estimated cost on our pipeline

Our logged Spark Open token counts at the Contributor rates; Spark 1.3 may tokenize images differently:

| Use | Contributor | Baseten Spark Open |
|---|---|---|
| Adjudicator, per adjudication | $0.0046 | $0.067 |
| Portia's hybrid, per question | $0.0012 | $0.017 |
| Spark as the whole agent, per question | $0.013 | $0.185 |

## Next, only with the user's OK

1. **A realistic cost check** with no benchmark content: Spark 1.3 as Portia's adjudicator or agent on a question
   written by us over public footage. A few cents.
2. **Accuracy on development cases.** Plan 006's evidence-only adjudications with Spark 1.3 Contributor: about 282
   adjudications, about $1.3, within the cap. It would show whether Spark 1.3 adjudicates as well as Spark Open (83%
   on splits). It **sends benchmark questions and answers, which Meta may then train on.**

## Revision log

- written after the smoke, which the user had asked for directly.
- **the user approved both next steps and the data use:** "it's fine, they may train; my call,
  try both 1 and 2, it's cheap !!". Recorded in the lock file.
  - **Step 1 becomes Spark 1.3 as the whole agent on plan 007's 10 contests** (shard 4 positions 0, 13, ..., 117),
    for a like-for-like comparison with the Spark Open agent: $0.185 and 6 of 10 right.
  - **Step 2 is plan 006 with Spark 1.3 Contributor as the evidence-only adjudicator.** Fresh triples go first, and
    the cost of the first run is checked before the rest go ahead.
  - The $2 cap holds for both.
- **capabilities and client.**
  - **Capability probe:**
    - tool calls work;
    - a named `tool_choice` is refused (only "auto"), so `judge/meta_client.py` emulates forcing by offering only the
      named tool;
    - structured A/B output works;
    - there is no per-request image cap (16 images fine), unlike Baseten's 8;
    - about 974 tokens per 1024x768 image.
  - **Backends:** `judge/run.py --backend meta` and `judge/adjudicate.py --backend meta`. The golden-request test shows
    0 differences.
- **step 1 done: Spark 1.3 Contributor as the whole agent, 8 of 10 right, $0.0113 per contest.**
  - **Contests:** plan 007's 10 contests (shard 4 positions 0, 13, ..., 117), with the tuned agent's settings.
  - **Comparison:** the Spark Open agent got 6 of 10 at $0.185; a Glimmer agent averages 6.8 (12 seeds).
  - **Its two misses** are the two contests that all 12 Glimmer seeds also miss; Spark Open misses them too.
  - **Usage:** 70 requests (7 per contest); 243k input tokens per contest, 63% billed as cached; 9.6k output.
  - Ten contests cannot rank designs, but this is the first measured "frontier as the whole agent" result that is
    both cheap and strong.
  - **Step 2** (the adjudicator over the 5 triples) is running in tmux `p2m2`/`p2m3`.

- **step 2 done: Spark 1.3 Contributor as the evidence-only adjudicator, +4.8 points over the vote
  on all five triples.** 282 adjudications, no errors (`analysis/spark13_report.py`, `runs/plan013_report.md`).

  | Triple | Relation | Vote | Spark 1.3 | Spark Open | Glimmer (mean) |
  |---|---|---|---|---|---|
  | {5,6,7} | fresh | 73.6 | +4.5 | +7.3 | +0.6 |
  | {8,9,10} | fresh | 75.5 | +2.7 | +4.1 | -1.5 |
  | {3,4,5} | shares seeds 3-4 | 71.8 | +6.4 | +7.7 | +3.2 |
  | {0,1,2} | selection | 75.5 | +4.5 | +5.9 | +1.5 |
  | {2,3,4} | selection | 73.6 | +5.9 | +7.3 | +2.3 |

  - **Overall:** 78.8% (vote 74.0%, Glimmer adjudicator 75.2%, Spark Open 80.5%). On the 282 splits: 76.6% (vote
    57.8%, Glimmer 62.6%, Spark Open 83.0%).
  - **Cost:** $1.166 in all, $0.0041 per adjudication, about $0.001 per contest: 16 times cheaper than Spark Open
    ($0.067 per adjudication) for about three quarters of its gain.
  - **Reading:** Spark 1.3 beats the vote and the Glimmer adjudicator on every triple, and Spark Open beats it on
    every triple.
- **in Portia.**
  - Track record for "split, decided by Spark 1.3": 76.6% (282 development cases).
  - A fifth series on the Proof page, the How it works table, the README and the demo script.
  - Portia's live budget for this route is `PORTIA_META_BUDGET_USD` (default $0.30) inside the $2 cap.
