# 004: a multi-agent judge, three investigators and an adjudicator

Status: **running (development only)**. Written by the Portia coding agent (Claude). The user approved
building it and running the development part before the outside review ("yes, build it and queue runs for next 24
hours for many checks"). **The confirmatory test still waits for the review** and its
pre-registration. Code: `judge/adjudicate.py`, `prompts/adjudicator/`, toolset `adj` in `tools/toolsets.yaml`.

## Goal

Test whether a multi-agent arrangement of Muse Glimmer agents beats the strongest cheap baseline we have: a
**majority vote of 3 independent tuned-v4 agents**. Every agent is Muse Glimmer (the user's decision for now; Muse
Spark can be tried later as the adjudicator).

## Why this design: the room above voting (development shards 3-4, existing runs)

Our literature report (`analysis/lit_tools.md`) found that majority voting explains most of the
published gains from debate and agent teams. That report's citations were not checked by hand. So the bar for any
multi-agent design is **the vote**, not the single agent. Five tuned-v4 seeds exist on shards 3-4, and they show
room above the vote:

| Shard 3 / shard 4 | Accuracy |
|---|---|
| Single agent (mean of 5 seeds) | 75.5 / 71.9 |
| Vote of 3 (seeds 0-2) | 78.7 / 73.0 |
| Vote of 5 | 76.6 / 73.8 |
| At least one of 3 seeds right | 87.2 / 84.9 |
| At least one of 5 seeds right | 92.6 / 86.5 |

- **Where the vote loses.** Across the 220 contests, the 3 seeds disagree on 60 (27%), and the majority is right on
  37 of those (62%). In **23 contests (10%) one seed found the right answer and was outvoted.** No vote can recover
  those, but an agent that checks the conflicting evidence can.
- **Where nothing here helps.** In 31 contests (14%) all three seeds are wrong. That needs better looking (plan
  001), not a better way to combine verdicts.
- **What the agents record.** Every saved trajectory has its tool calls with their arguments (video, time, region)
  and a final rationale that cites moments as `video@mm:ss`. So the exact views each seed saw can be re-rendered,
  and an adjudicator can be built on **existing runs**, with no new investigator runs.

## Design

| Role | Agents | What it does | When |
|---|---|---|---|
| Investigators | 3, independent | The tuned-v4 agent, seeds 0, 1 and 2. These are the existing runs, unchanged. | always |
| Adjudicator | 1 | Reads the 3 reports and re-checks the moments they disagree about, with tools. Gives the verdict. | only when the investigators disagree |
| - | - | A unanimous verdict stands. | otherwise |

**What the adjudicator sees:**
- the question and both answers, as in the contest;
- the 3 reports in a seeded random order, labelled Report 1-3 (never "seed" or "majority"). Each report has its
  verdict, its final rationale, and up to 3 of its own views re-rendered (the last zoom, burst or contact sheet at
  each moment its rationale cites).

**What it may do:**
- tools `zoom`, `burst`, `view_frames`, `contact_sheet`, `read_transcript` and `answer`; no `search`. It re-checks
  the cited moments; it does not start a new investigation;
- up to 4 turns, then the verdict with the existing two-level fallback.

**What the prompt asks:**
- list the observations on which the reports conflict;
- re-check each one in the frames;
- decide from the frames, not from how many reports agree.

**Variant B, a rebuttal round** (in the style of the multi-agent debate of Du et al., 2023, arXiv 2305.14325):
- On a contested contest, each investigator sees the other two reports and may re-check with the same tools (3
  turns), then gives a revised verdict.
- The majority of the revised verdicts decides.
- It tests whether peers correcting each other works better than one adjudicator.

**Runtime information only.** No prompt contains ground truth or dataset metadata (`hop_1`, `bridge`, `hop_2`,
clip ranges, degradation lists). The adjudicator sees what the investigators produced and the frames their own tool
calls fetched.

## Implementation outline, for the code review

- **`judge/adjudicate.py` (new):** `--runs <three run names> --shard <shard> --name <run> --variant
  adjudicator|rebuttal --max-steps 4`, plus `run.py`'s client flags. It reads `runs/<run>/results.jsonl` and
  `trajectories/`. It re-renders evidence through `judge/tools.py`'s `Toolbox`, the same path the explorer uses. It
  writes `runs/<name>/results.jsonl` and trajectories with `how` = `unanimous`, `adjudicated` or `fallback`.
- **Prompts** in `prompts/adjudicator/` (`system.md`, `first_message.j2`, `report.j2`; rebuttal templates for
  variant B). A toolset `adj` goes in `tools/toolsets.yaml`.
- **Checks:**
  - `tests/golden_requests.py` stays at 0 differences for every existing configuration.
  - On 5 contests, re-rendered views are compared with the originals through the existing replay, to confirm that the
    tools are deterministic.
- **Explorer:** an "Adjudicator" tab showing the 3 reports, the re-rendered evidence, the adjudicator's checks and
  its verdict.

## Evaluation

**Development** (shards 3-4, 220 contests):
- **Triples.** Seeds {0, 1, 2} is the main development triple. Seeds {2, 3, 4} replicate it; seeds 3 and 4 exist
  only on these shards.
- **Measures:**
  - accuracy against the vote of the same triple, and against the vote of 5;
  - accuracy on contested contests;
  - **herding**: how often it sides with a wrong majority;
  - calls and tokens.
- **Limits on iteration:**
  - bugs and format problems can be fixed freely;
  - at most 2 prompt revisions, each recorded in this file;
  - nothing on shards 1, 2, 5 or 6.

**Go/no-go, fixed now.** A variant goes to the held-out test only if it clears both conditions on development:
1. Over the two triples pooled, it beats the vote by at least 2 points.
2. It is not worse than the vote in either triple.

If more than one variant qualifies (adjudicator, evidence or rebuttal; see the revision log), the one with the
largest pooled gain goes. If none does, the null result is reported and this plan stops.

**Confirmatory test** (pre-registered in `runs/PREREG_adjudicator.json` before any adjudicator call on these shards):
- **Contests:** shards 1, 2, 5 and 6, 410 in all.
- **Investigators:** the existing tuned-v4 seeds 0-2. Shards 5-6 ran; shards 1-2 come from plan 002 today.
- **Primary:** the chosen variant against the vote of the same three runs, paired exact McNemar, alpha 0.05, no
  verdict counted as wrong.
- **Sensitivity, pre-registered:** the 238 contests whose question never appears in shards 3-4 (`000_context.md`).
- **Secondary:**
  - accuracy on contested contests;
  - the herding rate;
  - comparison with the static shared-text judge's vote (76.3% on shards 5-6).
- **Power:**
  - Verdicts can change only on contested contests, about 27%, or 110 of 410.
  - With an adjudicator right on 75% of them against the majority's 62%, the gain is about +14 contests (+3.4
    points), for example 24 vs 10, p ≈ 0.024.
  - At 70% it is about +9 (19 vs 10, p ≈ 0.14).
  - So confirmation needs about 73% or better on contested contests.

## Development result: the evidence-only variant qualifies

The rule was fixed before any run; every variant is compared with the vote of its own three investigators on the same
220 contests.

| Variant | Triple {0, 1, 2} | Triple {2, 3, 4} | Pooled | Sided with a wrong majority |
|---|---|---|---|---|
| Adjudicator (sees the reports) | +1.8 (77.3 vs 75.5; 12 fixed, 8 broken) | -0.5 (73.2 vs 73.6) | +0.7, does not qualify | 48% / 78% |
| **Evidence-only (sees only the looks)** | **+4.1 (79.5 vs 75.5; 18 / 9, p = 0.12)** | **+3.2 (76.8 vs 73.6; 14 / 7, p = 0.19)** | **+3.6, qualifies** | **22% / 39%** |
| Rebuttal (each agent re-checks after seeing the others) | +0.9 (76.4 vs 75.5; 9 / 7) | +0.5 (74.1 vs 73.6; 8 / 7) | +0.7, does not qualify | 61% / 65% |

- **On contested contests** the evidence-only adjudicator is right 77% and 67% of the time; the majority is right 62% and
  53%. It also beats a vote of 5 seeds (75.0%) on the same contests.
- **Reading:** showing the reports' verdicts and rationales let them steer the adjudicator. Shown only the investigators'
  looks, it judges the disputed details itself.
- **Caveats:** this is development data. Each triple alone is not significant, and the variant was picked as the best
  of three, so its development gain is optimistic. The replication triples (new seeds 5-7) and the held-out test
  address that.
- **All three variants are final** (rebuttal finished). Rebuttal second looks changed their verdict 45% of
  the time, with no net gain.
- **Diagnostics re-planned** for the chosen variant (never candidates): evidence-only with seeds 1 and 2 (noise, and a
  vote of 3 adjudicators), another view order, every contest (`--all`), 8 turns, and a mixed Muse/Qwen team. They are
  in tmux `p2b3` and `p2b0`; the unstarted adjudicator-variant diagnostics were dropped. The rebuttal runs resume and
  finish, since rebuttal is still a candidate.
- **Held-out test:** the draft pre-registration is `runs/PREREG_adjudicator.json`. It covers shards 1, 2, 5 and 6 (410
  contests, investigators = tuned-v4 seeds 0-2), with the 238 question-disjoint contests as the pre-registered
  sensitivity subset and SHA-256 prefixes of the code it runs. **It is inactive until the outside review and the user's
  go.** The test needs about 1 GPU-hour.

## Expected effect (honest prior)

**+1 to +4 points over the vote of 3.** Two failure modes are likely:
- **Herding:** the adjudicator follows whichever report sounds most confident.
- **Repeated misperception:** it misreads the frame the same way the wrong investigators did, since it is the same
  model.

Both are measured. The upside is the 23 outvoted-but-right contests on development (10%).

## How it relates to the other plans

- **001 (a verified single agent):** heavier, and aimed at the 14% that all seeds get wrong. 004 is cheap, and
  aimed at the 10% where one seed was right. They combine later: 001's gated agents could serve as 004's
  investigators.
- **002:** gives the shard 1-2 seeds that 004's confirmatory test needs.
- **003 (fine-tuning on Fireworks):** on hold by the user's decision.

## Cost

- **Development:** about 60 contested contests per triple, × 2 triples × 2 variants, is about 240 adjudications of
  up to 4 turns each. That's about 1-2 hours on one GPU.
- **Confirmatory test:** about 110 adjudications, under 1 hour.
- **Overall:** no API cost, GPUs 0 and 3 only, and no new investigator runs anywhere.

## Risks

- **Herding.** Mitigations: neutral report labels, a shuffled order, and the instruction to decide from the frames.
  It is measured directly.
- **Re-rendering differs from what the investigator saw.** The tools are deterministic, and the replay in
  `tests/golden_requests.py` already depends on that. Development checks 5 contests.
- **Single-sample noise.** The adjudicator samples at temperature 1.0. Taking a vote of 3 adjudicator samples is a
  secondary analysis.
- **Many comparisons across plans.** Each plan pre-registers one primary comparison.

## Open questions for the reviewer

1. Is the vote of the same 3 runs the right baseline? The adjudicated system costs a little more: about 3.3 agent
   runs. Should it also have to beat a vote of 5 on development, where 5 seeds exist?
2. Should the adjudicator see the investigators' verdicts, or only their observations, to reduce herding?
3. Is the go/no-go rule (at least +2 pooled, not worse in either triple) sensible for 220 development contests?
4. Should the primary test use all 410 contests or the 238 question-disjoint ones (as in plan 001, question 5)?

## Revision log

- first draft, after the user's "now lets focus on agents/multiagents".
- built. The golden-request check reports 0 differences over 240 runs and 1,840 requests.
  - **A third variant, `evidence`:** the adjudicator sees only the investigators' close looks, without their verdicts
    or rationales. This answers open question 2 by experiment. It joins the candidates for the go/no-go rule, which
    now picks the best of three variants (adjudicator, evidence, rebuttal) at their planned settings.
  - **Diagnostics,** queued for the 24-hour window. They **cannot be selected** for the held-out test; they only
    describe the method:
    - adjudicator seeds 1 and 2 on triple {0, 1, 2}: sampling noise, and a vote of 3 adjudicators;
    - another report order (`--order-salt 1`): order and herding effects;
    - adjudicating unanimous contests too (`--all`): does it break agreed verdicts?
    - 8 turns instead of 4;
    - a mixed team (agent seeds 0 and 1 plus static shared-text seed 0).
  - **Replication triples:** three new tuned-v4 seeds (5, 6, 7) on shards 3-4, started when plan 002 frees the GPUs.
    The adjudicator then runs on triples {5, 6, 7} and {3, 4, 5}. These are extra development evidence for the
    chosen variant, reported beside the two planned triples.
  - **Report text for static investigators:** their rows have no rationale, so the report uses the last 1,500
    characters of their written analysis.
- bug fixed. A call to a tool the adjudicator does not offer crashed that contest (a template
  argument clash), and the contest was not written. The two runs started before the fix (`mg_adj_s3`,
  `mg_adj_t234_s3`) are resumed after they finish, which redoes only the missing contests. Calls to tools that are not
  offered are now refused with a message and logged. The explorer has Adjudicator, Evidence-only and Rebuttal tabs that
  show each report's re-rendered looks.
- a format fix. vLLM's Muse tool parser sometimes leaves ATEM markup inside an argument. This
  happened in 9 of the first 426 adjudicator calls, all of them `burst`, and the garbled calls were wasted turns.
  `repair_args` now recovers the swallowed parameters and logs the original. It applies to every run started after
  the fix; the four adjudicator runs before that did not have it. If the adjudicator variant ends within 1 point of
  the go/no-go threshold, its contests with garbled calls are re-run with the repair before deciding.
- **the adjudicator variant does not qualify.**
  - Pooled over shards 3-4 the gain is +0.7: triple {0, 1, 2} +1.8 (12 fixed, 8 broken), triple {2, 3, 4} -0.5. It is
    1.3 points from the threshold, so the parser-repair re-run does not apply.
  - The evidence and rebuttal variants are still running.
  - A vote of 5 seeds (75.0%) is no better than a vote of 3, so Muse's remaining errors look systematic.
  - Existing runs show that teams mixing models have more room: Muse ×2 plus Qwen3.8 votes 77.3%.
  - Added a diagnostic (never a candidate): the Muse adjudicator over a mixed team of Muse seed 0, Qwen3.8 tools v4 and
    Muse seed 1, built from existing runs (`mg_adj_het`).
- the evidence-only variant on triple {2, 3, 4} is complete. Pooled it gains about +3 (shard 3
  even, shard 4 +5.6 with 10 fixed and 3 broken); triple {0, 1, 2} is still running. So the replication triples
  {5, 6, 7} and {3, 4, 5} also get evidence-only runs (tmux `p2v3`, `p2v0`; they wait for the new seeds), whichever
  variant the go/no-go rule picks.
- **the qualifying result looks largely like sampling luck.**
  - A second evidence-only sample (seed 2) on the same triple {0, 1, 2} gains only +0.5: 75.9 vs 75.5, 16 fixed and
    15 broken. The qualifying sample (seed 0) gained +4.1.
  - Seed 1 is -3.8 on its first 53 contests (partial).
  - So the mean single-sample gain is probably about +1, not +3.6. The go/no-go rule as written took one sample per
    triple, and this shows that one sample is not enough.
  - **Before any held-out test,** the candidate should be re-decided on more samples, for example a vote of 3
    adjudicator samples (plan 005 idea A). The draft pre-registration will be revised accordingly and stays inactive.
- **the hackathon is Muse-only** (the user). The mixed Muse/Qwen diagnostics (`mg_adj_het`,
  `mg_adjev_het`) are post-hackathon material. The adjudicator-variant one finished at +0.5; the evidence-only one was
  stopped at 66 of 94 shard-3 contests, and its GPU slot went to Muse-only samples on triple {2, 3, 4}.
  - Post-hackathon idea, kept for later: Muse ×2 plus Qwen3.8 agents vote 77.3% on shards 3-4, against 75.5% for Muse
    ×3. Different models make different mistakes.
- **does not replicate** (see plan 005).
  - On the two fully fresh investigator triples ({5, 6, 7} and {8, 9, 10}) the evidence-only adjudicator gains +0.6 and
    -1.4 on average. The +3.6 development result was a mix of a lucky sample and triples that overlap the selection
    seeds.
  - **Recommendation:** do not spend the held-out shards on this variant. `runs/PREREG_adjudicator.json` stays an
    inactive draft.
