# 010: An adjudicator that may search when the investigators' looks fall short (Muse Glimmer)

Status: **done (development only): no meaningful gain; Portia keeps the look-only adjudicator**. Written by the Portia coding agent (Claude).

- **The user's question:** "can Adjudicator bring more tool calls by itself, if it finds 3 agent frames in
  sufficient?"
- **After the analysis below,** the user said: "let's stick to glimmer, spark for later". So Muse Glimmer only; no
  Baseten spend.

## Why

The evidence-only adjudicator (plan 004) already looks for itself. In 98% of splits it makes its own calls: Spark Open
about 8.7 per case, Glimmer about 5. But it has look-only tools (zoom, burst, contact sheet, view frames, transcript),
so it cannot find a moment that none of the three investigators reached.

On the logged Spark adjudications (development shards):

| Spark's ruling | Evidence clips the investigators' looks touched | No evidence clip at all |
|---|---|---|
| Wrong (48) | 29% | in 35% of cases |
| Right (239) | 36% | in 27% of cases |

So some errors are "the frames were not enough". For Glimmer, looking beyond the investigators' looks did not change
its accuracy (63.2% against 62.0%), so the expected gain is small. The test is free on our GPUs, and it answers the
question for Jury's default adjudicator.

## Design

- **`judge/adjudicate.py --search`:**
  - adds `search_video`, `search` and `grep_transcripts` to the adjudicator's tools (toolset `adj_search`);
  - gives its tool box the query encoder;
  - switches the system prompt's tool paragraph to: "look first; search only for a difference none of the images
    shows".
  - Without `--search` the prompts are byte-identical (checked by rendering both before and after the change).
- **Turns:** 6 instead of 4, since a search costs turns. The plan-005 run with 8 turns and no search did not help, so
  turns alone are not the variable.
- **Investigators and contests:** the same as plans 005 and 006. The 5 investigator triples ({0,1,2}, {2,3,4},
  {3,4,5}, {5,6,7}, {8,9,10}) on development shards 3-4; only split contests are adjudicated (282 in all).
- **Judged** as plan 005 judged Glimmer: the gain over the vote per triple, against the mean of the existing
  evidence-only Glimmer samples on the same contests. One sample per triple first; a second sample if the first looks
  positive.
- **Logged:** how often it searches, and whether a search reaches an evidence clip the looks missed.

## Revision log

- written.
- **built and smoke-tested; full runs started.**
  - Code:
    - `judge/adjudicate.py --search` (toolset `adj_search`, the query encoder in the tool box);
    - `prompts/adjudicator/system.j2` (a conditional tool paragraph).
    - Without `--search` all 7 system-prompt renders are byte-identical to before; the agent's golden-request test
      shows 0 differences in 1,840 requests.
  - **Smoke test:** the first 3 split contests of shard 3, triple {0, 1, 2}, 6 turns. All 3 were right, one of them
    against a wrong majority. Glimmer searches heavily from its first turn, despite "look first": 3 to 7 search or grep
    calls per case.
  - **Full runs:** tmux `p2x3`, GPU 3, 6 workers. The order is {5,6,7}, {8,9,10}, {3,4,5}, {0,1,2}, {2,3,4};
    each triple on shards 3 and 4. The runs are named `mg_adjsx_<triple>_<shard>`.
  - Plan 009's GPU 3 lane now waits for this lane too.
- **final: the search lets it find more, but it is no more accurate.** All 5 triples x 2 shards, one
  sample (1,100 contest-triples).

  | Triple | Relation | With search | Without search (mean of samples) |
  |---|---|---|---|
  | {5,6,7} | fresh | +1.8 | +0.6 |
  | {8,9,10} | fresh | +0.0 | -1.5 |
  | {3,4,5} | shares seeds 3-4 | +1.8 | +3.2 |
  | {0,1,2} | selection triple | +1.4 | +1.5 |
  | {2,3,4} | selection triple | +1.8 | +2.3 |

  - **Overall:** with search +1.4, without search +1.2 (points over the vote). Right on splits: 63.1% against about
    62.6%.
  - **Process:**
    - it searched in 95% of splits, with 4.0 search or grep calls on average;
    - its own calls reached an evidence clip the investigators' looks had missed in 12%.
    - That evidence did not turn into better verdicts, consistent with plan 009's E1: Glimmer is limited by
      judgement, not localisation.
  - **Decision:** Portia keeps the 4-turn look-only adjudicator, which is cheaper and faster with no search load on
    the shared encoder. The `--search` option stays in `judge/adjudicate.py` (off by default). A test with Spark Open,
    which reads evidence well, is left for later (the user: "spark for later").

