# 009: Which lever limits the Muse Glimmer agent? (24-hour GPU window)

Status: **running (development only)**. Written by the Portia coding agent (Claude). The
user: "no, keep turning agents in gpu next 24 hours, keep gpu busy". The window lasts 24 hours.

## Why

Jury's default runs on Muse Glimmer alone. What we know:

- One tuned agent is right 72.9% of the time on development shards; three agents vote 74.0%.
- When the three agents split, at least one of them usually looked at the decisive moment.
- On those splits, Muse Spark Open judges their looks 83% right and Muse Glimmer 63%. Plan 005 found no Glimmer-only
  variant that closes this gap.
- Earlier oracle tests with other models were right about 90% when given the ground-truth evidence frames.
- Retrieval finds about half of the evidence clips in its top 64 segments (`analysis/retrieval_queries.py`).

Two levers could limit Glimmer:

- **Localisation:** finding the moments.
- **Judgement:** reading the details in them correctly.

They need different fixes, so the first experiment measures which one matters.

## Experiments (development shards 3-4 only; each idea judged on several seeds, as in plan 005)

### E1. Glimmer's oracle ceiling (diagnostic)

- `analysis/oracle_evidence.py` with Muse Glimmer: no tools; the question, both answers, the answer diff, and frames
  from the ground-truth evidence clips.
- Two seeds on shards 3 and 4.
- **Reading:**
  - If the ceiling is far above the agent (say above 85%), localisation is the lever: go to E2.
  - If it is near the agent (say below 78%), judgement is the lever: go to E3.

### E2. Localisation

These change only the agent's opening evidence pack.

1. **Offline first:** clip recall at 64 on dev for candidate packs, using the query encoder (CPU) and the dataset's
   evidence clips:
   - a hop-balanced pack (separate top segments for each scene the shared text describes);
   - a pack retrieved by each answer's own text;
   - a larger pack.
2. **Then agent runs:** only a pack that raises clip recall clearly gets them, with 3 seeds on each shard, against
   the 12 standard seeds.

### E3. Judgement

These are Glimmer-only ways to read the evidence better.

- A verification ledger in the investigator prompt: check each numbered difference, record verified or refuted with
  its moment, and decide by verified errors. This is Spark's style as an adjudicator, tried here in the investigator,
  not the adjudicator.
- Or showing the decisive frames at full resolution.

Each variant gets 3 seeds on each shard.

## Rules

- **Muse Glimmer only, on GPUs 0 and 3.** No paid API.
- **The development shards only.** No held-out shard is touched.
- **Lanes:**
  - GPU work never stops: the next run is queued before the current one ends.
  - An idle watcher stays armed.
  - Each GPU carries one heavy lane at a time.
- **Code:** changes to the agent are opt-in flags; the golden-request test must still show 0 differences.

## Revision log

- written. E1 starts first; the 8-turn baseline seeds 11 (shards 3 and 4) keep running.
- **E1 first half: judgement, not localisation, limits Glimmer.**
  - Given the ground-truth evidence frames (about 10 per contest, no tools), Muse Glimmer is right 77.7% on shard 3,
    against 74.7% for the tool agent. Shard 4 and a second seed are running.
  - **Two offline checks on logged runs** (no GPU):
    - **Majority of 3 Glimmer adjudicator samples on splits:** 62.3%, against 62.6% for one sample (282 splits). Its
      errors are systematic, so self-consistency does not help.
    - **Heterogeneous juries** (tools v5, look-first, xhigh, hi-res zoom or a swapped order mixed with tuned seeds):
      none beats three tuned seeds (75.5%); mixes score 70.9-75.5%.
  - **Conclusion so far:** the Glimmer-only accuracy levers are exhausted. The step up is Muse Spark Open (plan 006) or,
    later, training.
- **the window's GPU time goes to speed at equal accuracy,** which matters for Jury's live runs (about
  5 minutes per new case now).
  - **E4: fewer turns.** `--max-steps 4` and `--max-steps 6`, tuned flags otherwise, 3 seeds on each development shard.
  - **E6: lower reasoning effort.** `--reasoning-strength medium`, 3 seeds on each shard.
  - All are compared with the 12 standard 8-turn seeds on accuracy and on wall time per contest.
  - A setting that keeps accuracy within noise and cuts time clearly becomes Jury's "fast" option.
- **E1 seed 0 complete: given the evidence, Glimmer is no better than the tool agent.**
  - Oracle: shard 3 77.7% (agent 74.7%); shard 4 66.7% (agent 71.6%); pooled 71.4% against 72.9%.
  - The oracle's frames are 3 per evidence clip (25/50/75%) at 768 px, so they can miss the exact moment that the
    agent's zooms reach. Even so, handing over the right clips does not lift Glimmer.
  - The judgement reading stands. Seed 1 is running to confirm.
- **E1 done; E4 (4 turns) done.**
  - **E1, both seeds.** Glimmer given the evidence frames:
    - shard 3: 77.7 and 71.3 (mean 74.5), against the agent's 74.7;
    - shard 4: 66.7 and 69.8 (mean 68.3), against 71.6;
    - overall about 70.9 against 72.9.
    - **Judgement limits Glimmer, not localisation.**
  - **E4, 4 turns** (3 seeds per shard), against 8 turns (12 seeds):

    | Setting | Shard 3 | Shard 4 | Overall | Tokens per contest | Model calls |
    |---|---|---|---|---|---|
    | 8 turns | 74.1 | 71.6 | 72.7 | 289k | 8.6 |
    | 4 turns | 74.1 (77.7, 70.2, 74.5) | 68.5 (67.5, 65.9, 72.2) | **70.9 (-1.8)** | 170k (-41%) | 5.4 |

    About 40% less compute per agent for about 2 points. It suits a labelled "quick" option, not the default.
  - **E4, 6 turns (interim, 3 of 6 runs):** shard 3 75.0 over 2 seeds, shard 4 69.0 over 1; about 71.6 overall at
    231k tokens.
  - **Lanes rebalanced:** GPU 3 runs the rest of the 6-turn seeds; GPU 0 runs E6 (reasoning medium, seeds 0-2).

- **6 turns with medium reasoning is the best speed setting so far; lanes switched to it.**

  | Setting | Seeds | Right | Output tokens per contest |
  |---|---|---|---|
  | 8 turns, high | 12 | 72.7% | 3.4k |
  | 8 turns, medium | 3 | 72.6% | 2.7k |
  | 6 turns, high | 3 | 72.1% | 3.1k |
  | 6 turns, medium | 2 | 73.9% | 2.4k |
  | 4 turns, high (Portia's Quick) | 3 | 71.0% | 2.8k |

  - 6 turns medium beats 4 turns high on accuracy and tokens, so it may replace Quick, and perhaps the default, if
    more triples confirm it.
  - **GPU 0** (`p2k0`, `runs/m6med_lane.sh`): seeds 3-5 and their Glimmer adjudication, then the 8-turn medium seeds
    3-5.
  - **GPU 3** (`p2k3`): the adjudication of seeds 0-2 once seed 2 ends, seeds 6-8 and their adjudication, then the
    4-turn seeds 3-5. The interrupted 4-turn run resumes at 9 of 126.
  - E3's verification ledger is not run: the v4 investigator prompt already checks each listed difference, tallies
    verified errors on both sides and cites what it saw.
- **6 turns medium, first full triple: no better than 4 turns for the whole pipeline, but faster.**

  | Triple {0,1,2}, one Glimmer sample | Single | Vote | Pipeline | Glimmer on splits |
  |---|---|---|---|---|
  | 6 turns, medium | 72.7 | 74.5 | 73.6 | 57.1 |
  | 4 turns, high (Portia's Quick) | 70.9 | 72.7 | 73.6 | 62.9 |

  - **Speed:** run side by side under the same load, 6 turns medium takes about 175 s per contest, against about 220 s
    for 4 turns high, with 2.4k against 2.8k output tokens.
  - **Noise:** one adjudication sample moves the pipeline number by a few points. Second samples (`--seed-salt 1`) for
    every speed-mode triple are queued after the lanes (`runs/adj_samples_lane.sh`, tmux `p2t0` and `p2t3`).
  - **Decision rule unchanged:** Quick switches to 6 turns medium only if triple {3,4,5} confirms.
    Report: `analysis/mode_track.py`.
