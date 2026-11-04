# 006: Muse Spark Open as the adjudicator (Baseten)

Status: **development test done** ($18.80). The held-out test awaits the user's go (draft pre-registration `runs/PREREG_spark_adjudicator.json`, inactive). Written by the Portia coding agent (Claude). The user asked
for a 5-contest smoke test first ("let's smoke first in 5 samples to see intial improvment").

## Why

With Muse Glimmer as both investigator and adjudicator, adjudication did not beat the investigators' vote on fresh
investigator triples (plans 004-005): the same model misreads the same details. A **stronger adjudicator** was the
original upside of plans 001 and 004. Muse Spark Open is Meta's open-weights frontier model: 816B total parameters with
42B active, and the same vision-encoder design as Glimmer. It is hackathon-eligible: it is an open-weights model served
by a hackathon inference partner.

## Access and keys

- The user unlocked **only** `META_BASETEN_KEY`: "let's unlock baseten key only (keep meta api locked)".
  - The lock file records it.
  - `judge/meta_lock.py` `baseten_key()` returns that one variable, and only while the unlock line is in the lock
    file.
  - `META_DEV_KEY` and Meta's own API stay locked.
- Endpoint: Baseten, OpenAI-compatible, model `meta-models/muse-spark-open-1026`, the only model the hackathon key
  works with. Baseten gives $100 in credits and 2M tokens per minute.
- `judge/baseten_client.py`:
  - translates the local client's settings: reasoning strength becomes `reasoning_effort`; the structured A/B choice
    becomes a JSON-schema `response_format`;
  - caches every response;
  - logs each request's cost to `runs/baseten_spend.jsonl`;
  - stops at a per-run budget.
- **Price:** $1.25 / $0.15 (cached) / $4.25 per million tokens in / out. Expect about $0.04-0.08 per adjudication;
  only contested contests (about 26%) need one.

## Design

- Unchanged from plan 004's **evidence-only** variant: same prompts, same tools, same investigator runs (local
  Glimmer, tuned v4) and same re-rendered looks.
- Only the adjudicating model changes. Its reasoning effort is `high`, as Glimmer's strength was.
- Run with `judge/adjudicate.py --backend baseten --variant evidence`.

## Smoke test

- **Contests:** the first 5 contested contests of shard 3 (development), in shard order (no cherry-picking), with
  investigators = tuned-v4 seeds 0-2.
- **Budget:** a $2 cap.
- **Compared on the same 5 contests with:** the investigators' vote, and the Glimmer evidence-only adjudicator over
  its 5 samples (seeds 0-4).
- **Five contests show only whether it works, not whether it helps.** The questions are:
  - Do tool calls, images and verdicts parse?
  - What does an adjudication cost?
  - Is it in the right range?

## If the smoke works (not yet approved)

- **Development test:** the 5 investigator triples of plan 005, on shards 3-4. About 285 adjudications, about
  $11-22. Judged as plan 005 judged Glimmer: mean gain per triple, with the two fresh triples counted separately.
- **Held-out test:** only with a new pre-registration and the user's go.

## Development result: Spark Open as the adjudicator works on every triple

The evidence-only adjudicator with Spark Open, one sample per investigator triple, development shards 3-4 (220 contests
each). Gain = accuracy minus the vote of the same three Glimmer investigators; exact McNemar on fixed vs broken.

| Triple | Relation | Vote | Spark-adjudicated | Gain | Fixed / broken | p | Glimmer adjudicator (mean) |
|---|---|---|---|---|---|---|---|
| {5, 6, 7} | fresh | 73.6 | 80.9 | **+7.3** | 19 / 3 | 0.0009 | +0.6 |
| {8, 9, 10} | fresh | 75.5 | 79.5 | **+4.1** | 16 / 7 | 0.093 | -1.5 |
| {3, 4, 5} | shares seeds 3-4 | 71.8 | 79.5 | **+7.7** | 20 / 3 | 0.0005 | +3.2 |
| {0, 1, 2} | selection triple | 75.5 | 81.4 | **+5.9** | 18 / 5 | 0.011 | +2.1 |
| {2, 3, 4} | selection triple | 73.6 | 80.9 | **+7.3** | 19 / 3 | 0.0009 | +2.3 |

- **All 5 triples are positive.** The mean gain is +6.5 points over the vote, against +1.3 for the Glimmer adjudicator;
  on the two fresh triples it is +5.7 against -0.5.
- **The full system** (3 local Glimmer agents, then Spark Open on contested contests only) reaches 79.5-81.4% on
  development, against 71.8-75.5% for the agents' vote and about 73% for a single agent.
- **Cost:** 282 adjudications, $18.80 ($0.067 each). Only contested contests (about 26%) cost anything, about $0.017
  per contest.
- **Caveats:**
  - Development shards, one Spark sample per triple.
  - The prompts are the evidence-only ones written on shard 3.
  - The triples share the same 220 contests, so the per-triple tests are not independent of each other.
- **Next:** the pre-registered held-out test on shards 1, 2, 5, 6 (410 contests, investigators = tuned-v4 seeds 0-2;
  about 107 adjudications, about $7.2). The draft is `runs/PREREG_spark_adjudicator.json`; it is inactive until the
  user's go.

## Revision log

- written; key unlock and client done. A first call ("ready") cost $0.00017.
- **smoke test done.**
  - **Baseten caps a request at 8 images** ("Too many images: 10 (max 8)"). The first attempt failed after 1-3 turns
    per contest ($0.11 spent; the run is in `zarxiv/baseten_smoke_failed/`).
  - For the Baseten backend only:
    - at most 2 looks per report;
    - the pinned looks keep at most 6 images;
    - the adjudicator's own looks keep the newest images up to 8 per request; older ones are replaced by the
      "image dropped" note.
  - **Result:** on the first 5 contested shard-3 contests (triple {0, 1, 2}), Spark Open was right on 5 of 5. The
    investigators' vote was right on 4 of 5, and Glimmer evidence-only averaged 4.3 of 5 over its 7 samples (range 3-5).
    Too few contests to conclude anything; all verdicts parsed (3 as text, 2 forced).
  - **Cost:** $0.234 for 5 adjudications, $0.047 each (estimate: $0.04-0.08).
  - **Billing API:** the hackathon key cannot read Baseten's billing API (`GET /v1/billing/usage_summary` returns 403
    PERMISSION_DENIED). Spend is tracked locally from each response's exact token usage (`runs/baseten_spend.jsonl`;
    report: `python -m judge.baseten_client`). A hard total cap of $90 of the $100 credit applies across all runs.
  - **Total logged spend:** $0.35.
- **development test started** (the user approved, with a $15 cap).
  - **Runs:** 10, evidence-only with Spark Open on Baseten, on the 5 investigator triples × shards 3-4.
  - **Budget:** one shared group, `plan006_dev`. New requests stop at $14.50 so that requests in flight stay under $15.
  - **Order:** the fresh triples go first, so the most informative results finish before any budget stop.
    - tmux `p2sp1`: {5, 6, 7}, then {3, 4, 5}, then {2, 3, 4} shard 3.
    - tmux `p2sp2`: {8, 9, 10}, then {0, 1, 2}, then {2, 3, 4} shard 4.
  - Runs `mg_adjsp_<triple>_<shard>`; the 5 smoke contests of {0, 1, 2} shard 3 replay from the cache.
  - **Judged against** the vote of the same investigators (primary), and against the Glimmer evidence-only means per
    triple (plan 005). The comparison with Glimmer has one caveat: Baseten shows at most 2 looks per report, Glimmer 3.
- **cost re-projection.**
  - $0.016 per request, as in the smoke test. But about 4 requests per adjudication against 3 in the smoke, so about
    $0.065 per adjudication.
  - 283 contested adjudications are needed, about $18-19 in all. The $14.50 stop covers about 210-220: both fresh
    triples, {3, 4, 5} and most of {0, 1, 2}. Triple {2, 3, 4} would be cut.
  - Asked the user whether to raise the cap.
- **cap raised to $20** (the user: "it's fine let's raise to $20").
  - Both lanes restarted with new requests stopping at $19.50; they resumed through the response cache.
  - Spend at restart: $6.70.
  - All 10 runs are expected to finish, at about $18-19 in total.
- **interim result: Spark Open helps where Glimmer's adjudicator did not.** One Spark sample per
  triple; gain = accuracy minus the vote of the same investigators; exact McNemar on fixed vs broken.

  | Triple | Spark gain | Fixed / broken | p | Glimmer mean gain |
  |---|---|---|---|---|
  | {5, 6, 7} fresh | +7.3 | 19 / 3 | 0.0009 | +0.6 |
  | {8, 9, 10} fresh | +4.1 | 16 / 7 | 0.093 | -1.5 |
  | Both fresh triples | +5.7 | 35 / 10 | 0.0002 | -0.5 |
  | {3, 4, 5}, 124 of 220 contests | +5.6 | 7 / 0 | 0.016 | +1.3 |
  | {0, 1, 2}, 92 of 220 contests | +4.3 | 6 / 2 | 0.29 | +1.4 |

  - **Caveats:** development shards; one Spark sample per triple. The evidence pool is smaller than Glimmer's (2 looks per
    report against 3); the prompts are the evidence-only ones written on shard 3.
  - **Reading:** this matches the original hypothesis that the gain needs a stronger judge of the disputed details, not
    another look by the same model.
  - **If the final numbers hold:** a pre-registered held-out test (shards 1, 2, 5, 6; about 107 adjudications, about
    $7.4) is well motivated. It needs the user's go.
- development test done, all 10 runs complete ($18.80, no failures). See the development result above.
- **cost of the combination vs Spark Open doing the whole task** (the user asked). Estimate only:
  Spark has never run as the agent.
  - **Method:** the logged Glimmer agent turns are re-priced as Baseten requests (`analysis/spark_agent_cost.py`).
    - Both models use 823 tokens per image and about 5.6 characters per text token (least squares on the adjudicators'
      first requests).
    - Images are capped at 8 per request.
    - 28.4% of input is billed as cached, as in plan 006.
    - Spark writes 1.35 times Glimmer's output.

  | Setup | Spark API per contest | Local GPU per contest | 630 contests |
  |---|---|---|---|
  | **Ours:** 3 local Glimmer agents + Spark on contested contests only | **$0.017** (measured) | about 65-90 GPU-seconds | about $11 |
  | Spark as the agent, 1 per contest | about $0.27 (at most $0.38) | none | about $170 |
  | Spark as 3 agents + vote + Spark adjudicator | about $0.82 | none | about $520 |

  - **Savings:** the combination costs about 94% less than one Spark agent (16 times cheaper), and about 98% less than
    an all-Spark three-agent system.
  - **Where the agent's cost goes:** input, $0.25 of $0.27. That is 8.6 requests per contest, each re-sending the
    growing conversation (about 31,000 tokens per request).
  - **Unknowns:**
    - A Spark agent's accuracy is untested.
    - The 8-image cap would force a redesign: the agent pins 8 overview sheets, so it could keep only 6 of them plus 2
      of its own looks per request.

