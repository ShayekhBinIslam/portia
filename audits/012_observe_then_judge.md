# 012: Observe, then judge: a Glimmer adjudicator that describes before it compares

Status: **done (development only): a null; Portia keeps the plain evidence-only adjudicator**. Written by the Portia coding agent (Claude), inside
the 24-hour GPU window: the user's "keep turning agents in gpu next 24 hours, keep gpu busy".

## Why

Plan 009 showed that Muse Glimmer is limited by **judgement**, not localisation:

- given the ground-truth evidence frames it is no better than the agent;
- an adjudicator that may search finds missed evidence but is no more accurate (plan 010).

Its errors are systematic: a majority of 3 samples does not help.

One known source of systematic misreading is **confirmation**. The model reads an image while holding the claim it is
checking, and "sees" the claim. Spark Open's adjudications, which are right 83% on splits, read like audits: each
claim, then what the frame shows, then a tally. Glimmer's often decide first and look second.

## Design

- **The variant:** `judge/adjudicate.py --observe`, on top of the evidence-only adjudicator. The default stays
  byte-identical, checked by rendering. Its system prompt adds a required first stage:
  1. **Observe:** for each image, write what is literally visible that bears on the numbered differences (on-screen
     text and numbers verbatim, counts, colours, objects, who is where), without mentioning either answer's wording.
  2. **Compare:** then, for each difference, say which answer's claim the observations support, contradict or leave
     open.
  3. **Tally.**
  - The adjudicator's own looks follow the same rule.
- **Everything else as plan 005:** the 5 investigator triples on development shards 3-4, 4 turns, Muse Glimmer, one
  sample per triple first.
- **Judged against the vote** and against the existing evidence-only Glimmer samples on the same contests.
- **If** it beats them by at least 2 points over the vote on the fresh triples and does not lose elsewhere, a second
  sample follows. Otherwise it is recorded as a null.

## Revision log

- written.
- **final: a null.** All 5 triples x 2 shards, one sample (1,100 contest-triples).

  | Triple | Relation | Observe-then-judge | Plain evidence-only (mean of samples) |
  |---|---|---|---|
  | {5,6,7} | fresh | +1.4 | +0.6 |
  | {8,9,10} | fresh | -0.5 | -1.5 |
  | {3,4,5} | shares seeds 3-4 | +2.7 | +3.2 |
  | {0,1,2} | selection triple | +2.7 | +1.5 |
  | {2,3,4} | selection triple | +0.9 | +2.3 |

  - **Overall:** +1.5 against +1.2 (points over the vote). Right on splits: 63.5% against about 62.6%.
  - **The bar is not met:** +2 over the vote on the fresh triples. The early interim (+1.6 against +0.1 on 119 splits)
    faded with more data.
  - **Reading:** describing the images first does not fix Glimmer's misreadings either. Together with plans 009-010,
    the Glimmer-only adjudication levers are exhausted. The step up is a stronger reader: Spark Open (plan 006), or
    Spark 1.3 Contributor (plan 013, running).

