# 002: full-dataset baselines (Muse on shards 1 and 2)

Status: **done**. Approved by the user ("yes, fire"), before the audit
workflow began. Four tmux lanes, two per GPU: `p2f0a` and `p2f0b` on GPU 0 (port 18661), `p2f3a` and `p2f3b` on
GPU 3 (port 18660). Seed-0 runs go first.

## Goal

Give each Muse setup an accuracy over **all 630 contests**. So far Muse has judged 536 of them (shards 3-6). Shards
1 and 2 (31 + 63 = 94 contests) were never judged by Muse.

## Runs

Three setups, three seeds each (`--seed-salt 0, 1, 2`), on both shard 1 and shard 2: 18 runs, 846 judgements in all.

| Setup | Command, per shard and seed |
|---|---|
| Static, question retrieval | `judge/static_baseline.py --payload data/static_payload_rebuild/<shard>_question.jsonl` |
| Static, shared-text retrieval | `judge/static_baseline.py --payload data/static_payload_rebuild/<shard>_shared.jsonl` |
| Tool agent, tuned v4 | `judge/run.py --tools v4 --keep-reasoning --budget-note --final-full-reasoning` |

All runs use Muse Glimmer (`mg30`), reasoning strength `high`, `--max-tokens 16384`, and the same sampling as before.
Run names follow the existing pattern: `mg_static_qu{,_r1,_r2}_s1`, `mg_static_sh{...}_s1`, `mg_v4t{...}_s1`, and
the same for `s2`.

## What comes out

For each setup: a single-run (seed 0) accuracy and a vote-of-3 accuracy, over all 630 contests, with per-shard rows.

The report will label shards 3-4 as development and 5-6 as held-out. The agent was tuned on shard 3, so its
630-contest number is slightly optimistic.

## Interaction with plan 001

Plan 001 proposes shards 1 and 2 as part of its confirmatory test. These baseline runs touch those shards, so:

- **Only aggregate scores** from these runs are reported.
- **No per-contest result** from shards 1-2 is inspected or used for any design decision.
- **Plan 001's pre-registration is written before any v6 run.**

If the reviewer judges that even aggregate baselines contaminate shards 1-2, plan 001 can drop them from its test set
and use shards 5-6 alone (316 contests).

## Cost

About 4 hours on GPUs 0 and 3. The static runs are the slow part: 128 frames per request.

## Results (aggregate only)

All 18 runs on shards 1-2 finished with no errors. Seed 0 / vote of 3 seeds, % correct:

Seed 0 / vote of 3 seeds, % correct (a missing verdict counts as wrong). Shards 3-4 = development, 5-6 = held-out,
1-2 = new (plan 001/004 test sets: aggregate only).

| Setup | shard 1 | shard 2 | shard 3 | shard 4 | shard 5 | shard 6 | **All 630** |
|---|---|---|---|---|---|---|---|
| Static, question retrieval | 71.0 / 71.0 | 60.3 / 68.3 | 68.1 / 68.1 | 61.9 / 62.7 | 64.6 / 68.4 | 74.1 / 72.8 | **66.8 / 68.4** |
| Static, shared-text retrieval | 71.0 / 67.7 | 77.8 / 71.4 | 71.3 / 70.2 | 62.7 / 65.1 | 73.4 / 74.1 | 72.8 / 78.5 | **71.1 / 72.2** |
| Tool agent, tuned v4 | 83.9 / 74.2 | 68.3 / 65.1 | 76.6 / 78.7 | 72.2 / 73.0 | 72.2 / 75.9 | 72.8 / 74.7 | **73.2 / 74.3** |

- **Over all 630 contests:** the tool agent (73.2 / 74.3) is ahead of static shared-text retrieval (71.1 / 72.2), which
  is ahead of static question retrieval (66.8 / 68.4).
- **Question retrieval's vote of 3** over all 630 contests is 68.4%. Its seeds 1-2 on shards 3-4 were run for this plan
  overnight.
- **Caveats:** shards 1-2 are small (31 and 63 contests), so their per-shard numbers swing widely between seeds. The
  agent was tuned on shard 3, so its 630-contest number is slightly optimistic.

## Revision log

- written after the user's approval, to record it under the new audit workflow.
- running. The servers had stalled on a slow disk. Fixed by reading the checkpoint into the page
  cache once, sequentially, then starting the servers one at a time.
- plan 003 (fine-tuning) proposes question-grouped folds over all 630 contests. Its aggregate-only rule for
  shards 1, 2, 5 and 6 matches this plan's.
- static shared-text and the tool agent are complete over all 630 contests (aggregate only):
  shared-text seed 0 71.1%, vote of 3 72.2%; tuned v4 seed 0 73.2%, vote of 3 74.3%. Static question retrieval seed 0
  is 66.8% over 630. Its vote of 3 needs seeds 1-2 on shards 3-4, which were never run there; they are queued (tmux
  `p2q0`, `p2q3`; 4 static runs) to complete this plan's deliverable. Shard 1-2 seeds 1-2 of static question are still
  finishing.
- done. Static question seeds 1-2 on shards 3-4 finished; full-630 vote of 3 = 68.4%.
