# 005: follow-ups to the evidence-only adjudicator (development only)

Status: **running (development only)**. Written by the Portia coding agent (Claude), after the
user's "keep running and try new ideas and keep gpu busy till tomorrow 3 pm". Every run here is on development
shards 3-4. Nothing touches shards 1, 2, 5 or 6. No idea here becomes a candidate for a held-out test without a
revised pre-registration and the user's go.

## Why

Plan 004's evidence-only adjudicator passed its development go/no-go (+3.6 over the investigators' vote, pooled
over two seed triples). Two findings since then limit how far that can be trusted:

- **A single adjudicator verdict is noisy.** On shard 3, a second sample (seed 2) scored 76.6% where the qualifying
  sample scored 79.8%. The two samples agree on only 19 of 26 contested contests.
- **Muse-only diversity adds little.** On shards 3-4, triples of different Muse configurations (look-first, tools v5,
  xhigh, 30 turns) vote 74.0% on average, against 74.6% for triples of seeds. At least one is right in 86.9% of
  contests, against 85.9%. Mixing in Qwen3.8 raised that to 88.6-92.7%, but the user has kept the agents Muse-only.

So the ideas below aim at the adjudicator's noise and at how it uses the evidence.

## Ideas and their runs

| # | Idea | What changes | Runs (shards 3-4, triple {0,1,2} unless noted) | Compared with |
|---|---|---|---|---|
| A | **Vote of adjudicator samples** | 3 evidence-only samples (seeds 0, 1, 2) vote | already queued in plan 004 (`mg_adjev`, `_r1`, `_r2`) | each sample; the investigators' vote |
| B | **Both answer orders** | the adjudicator also judges with A and B swapped (same looks); its verdict is mapped back. If the two orders agree, that verdict; if not, the investigators' vote | `mg_adjev_sw` (`--swap`) | A; one order alone |
| C | **Five investigators' looks** | the evidence pool comes from 5 tuned-v4 seeds (0-4), up to 15 looks; contested = not unanimous | `mg_adjev5` | the vote of the same 5 seeds (75.0%); the 3-seed evidence-only |
| D | **xhigh adjudicator** | reasoning strength xhigh for the adjudicator only | `mg_adjev_x` | the same at `high` |
| E | **Claim-by-claim verdict** | after its looks, the adjudicator rules on each place where the answers differ (which version the frames support, or unclear), each as a constrained A / B / unclear choice. The verdict is the answer with fewer unsupported claims; a tie goes to the investigators' vote | `mg_adjev_claims` | the evidence-only verdict |

Ideas A-D need small code changes (`--swap`, a report count that is no longer fixed at three). Idea E is a new
variant and goes last. Its design is checked on 5 contests before a full run.

## Rules

- **Development shards 3-4 only.**
- **Each idea is compared with its baseline on the same contests**, using the same paired counts (fixed / broken)
  as plan 004.
- **Prompt texts for three investigators stay byte-identical:** the new count only changes the words when there are
  more than three.
- **The held-out test is untouched.** If an idea clearly beats the plan-004 evidence-only variant on development
  (both shards, and its replication triples where they exist), the draft pre-registration is revised to it. The
  user then decides.

## Cost

About 1-2 GPU-hours per idea on shards 3-4; idea E takes about 2-3 times longer. All on GPUs 0 and 3, with no API
cost.

## Revision log

- written; ideas A-E.
- built and smoke-tested.
  - `--swap`, and a report count other than three: the prompts for three investigators are verified byte-identical.
  - `--variant claims`: its adjudication requests are identical to the evidence-only run's, so they replay from the
    response cache. The comparison therefore isolates the per-claim rule.
  - Runs started: claims and swapped order in tmux `p2c3`; five investigators and xhigh in `p2c0`.
- first results.
  - **Idea A, noise:** seed 2 gains +0.5 against seed 0's +4.1 on the same 220 contests; seed 1 is partial.
  - **Idea E, claims:** +5.0 over the vote (17 fixed, 6 broken; 219 of 220 contests). But its adjudication is seed 0's
    (replayed from the cache), so it inherits that luck. The per-claim rule itself changed 3 holistic verdicts, all
    3 for the better. Most rulings were "unclear" (131 of 200); the rule decided 29 of 48 eligible contested contests,
    and 11 were skipped for low overlap. To judge the rule on its own, it should also run on seeds 1 and 2.
- **more samples, since single adjudicator runs proved too noisy to judge.**
  - Evidence-only seeds 3 and 4 on triple {0, 1, 2} (tmux `p2e3`). With seeds 0-2 that makes 5 samples, enough for a
    reliable mean gain and for offline rules such as "override the vote only when most adjudicator samples agree".
  - Five-investigator seeds 1 and 2 (tmux `p2e0`).
  - Both lanes start when the current plan-005 lanes on their GPU finish.
- added evidence-only samples 1-2 on triple {2, 3, 4} (tmux `p2g0`) and on the fresh triple
  {5, 6, 7} (`p2g3`), to test the vote-of-samples and unanimous-override rules on independent data.
  - The hackathon is Muse-only (the user), so no mixed-model run is queued here.

## Post-hackathon ideas (not for the hackathon: it is Muse-only)

- Mixed-model investigators: Muse plus Qwen3.8-27B, plus Nemotron. Existing runs show more room above the vote
  (at least one right 88.6-92.7%, against 85.9% for Muse alone) and a better vote (77.3% vs 75.5%).
- A Qwen3.8 or other adjudicator over Muse investigators.
- **ideas B and C finished; the pooled sample picture is stable on triple {0, 1, 2}.**
  - **B, answers swapped (one sample):** +3.6 (20 fixed, 12 broken); it sides with a wrong majority only 13% of the
    time. Combined with the original order (agree -> that verdict, disagree -> the vote): +4.0. The two orders agree
    on 47 of 60 contested contests.
  - **C, five investigators' looks:** +1.8 over the vote of 5 (75.0%), no better than three investigators.
  - **Five independent evidence-only runs** on triple {0, 1, 2}: seeds 0-2, view order 1, swapped. Gains +4.1, +2.3,
    +0.5, +3.2, +3.6 (mean +2.7, sd 1.3; all positive). A vote of 3 adjudicator samples gives +3.5 (mean over the
    10 subsets); a vote of 5 gives +3.6; overriding the vote only when at least 4 of 5 samples go against it gives
    +5.0.
  - **Next test:** whether this holds on triples {2, 3, 4} and {5, 6, 7} (samples running). If it does, the
    held-out candidate becomes "evidence-only, vote of 3 adjudicator samples": a fixed, simple rule.
- **D, xhigh adjudicator (one sample):** +3.6 (17 fixed, 9 broken). That is within the range of the high-strength
  samples (+0.5 to +4.1), so there is no clear benefit.
- **Triple {2, 3, 4}, two evidence-only samples:** +3.2 and +1.8 (mean +2.5), consistent with triple {0, 1, 2}
  (mean +2.7 over five runs). The effect carries over to a second investigator triple.
- **E, claims rule over 3 samples:** +5.5, +2.3, +0.0 (mean +2.6). The same samples without the rule average +2.3 on
  these runs, and the rule changes very few verdicts. **It adds nothing reliable; dropped.**
- **mixed news.**
  - **Triple {2, 3, 4}, 3 samples:** +3.2, +1.8, +1.8 (mean +2.3). A vote of 3 samples gives +3.2; the "all 3 against"
    override only +1.8.
    - So the vote of 3 adjudicator samples is the stable rule: +3.5 and +3.2 on the two triples.
    - The unanimous or 4-of-5 override does not replicate (+5.0 on {0, 1, 2}, +1.8 on {2, 3, 4}).
  - **Fresh triple {5, 6, 7}, shard 4 only, one sample:** evidence-only -2.4 (72.2 vs 74.6; 7 fixed, 10 broken); the
    adjudicator variant -0.8.
    - This is the only triple sharing no seed with the others. One sample on 126 contests has an SE of about 3
      points, so it is not decisive, but it caps the claim.
    - Shard 3 waits for seed 7; samples 1-2 for this triple are queued.
- GPU 0 ran out of queued work, so it got new runs.
  - **Static question seed 2, shard 4 (plan 002):** moved to GPU 0. The GPU 3 lane was stopped and its shard-3 run
    resumed alone (91 of 94 kept), so nothing runs twice.
  - **Idea F, a larger evidence pool:** up to 6 looks per report instead of 3 (`--views 6`), triple {0, 1, 2}
    (`mg_adjev_v6`). Five investigators' looks did not help; this tests more looks from the same three investigators.
  - **Also done:**
    - Evidence-only on every contest (shard 3) equals the vote: 10 fixed, 10 broken. On unanimous contests it fixed 3
      and broke 4.
    - Fresh triple {5, 6, 7}, shard 4: two samples, -2.4 and +0.8.
    - Triple {3, 4, 5}, shard 4: +2.4 from one sample.
- **a second fully fresh triple, {8, 9, 10}.**
  - Why: the only triple sharing no seed with the others ({5, 6, 7}) is the one where evidence-only shows no gain.
  - Tuned-v4 seeds 8 and 9 run on GPU 0 after idea F (tmux `p2j0`), and seed 10 runs on GPU 3 (`p2j3`). Then three
    evidence-only samples on {8, 9, 10}, shards 3-4 (`p2j0`).
  - Together with {5, 6, 7}, this decides whether the effect holds on investigators unrelated to the triples it was
    found on.
- **the effect depends on the investigator triple.** Evidence-only vs the vote of the same
  three investigators, development shards 3-4:

  | Triple | Samples | Mean single-sample gain | Vote of 3 adjudicator samples |
  |---|---|---|---|
  | {0, 1, 2} | 7 (seeds 0-4, view order 1, swapped) | +2.1 (sd 1.5; range +0.5 to +4.1) | +2.8 (mean over 35 subsets) |
  | {2, 3, 4} | 3 | +2.3 | +3.2 |
  | {3, 4, 5} | 1 on both shards (+2.3); 3 on shard 4 | shard 4: +3.7 | shard 4: +3.2 |
  | {5, 6, 7} (fresh) | 1 on both shards (-0.5); 3 on shard 4 | shard 4: -2.4 | shard 4: -4.0 |

  - **Overall:** a modest positive effect (about +1.5 to +2) that varies strongly between investigator triples. The one
    fully fresh triple shows none.
  - The report-reading adjudicator was +4.1 on {3, 4, 5} (13 fixed, 4 broken) and 0.0 on {5, 6, 7}. So
    "evidence-only beats the report-reading adjudicator" is also not uniform.
  - **Not independent samples:**
    - Idea F (up to 6 looks) reproduced seed 0 exactly. Investigators rarely have more than 3 matching looks, so the
      requests were identical and came from the response cache.
    - `--all` matches seed 0 on contested contests, for the same reason.
  - **Pending:** the second fresh triple {8, 9, 10}, and samples 1-2 of {5, 6, 7} on shard 3.
- **Fresh triple {5, 6, 7}, 3 samples on both shards:** -0.5, +2.7, -0.5 (mean +0.6); a vote of 3 adjudicator samples
  gives +0.5. Small and not negative, so the shard-4-only view had overstated the drop.
- **8 turns instead of 4 (one sample, 208 of 220 contests):** -2.9 (10 fixed, 16 broken). Longer adjudication does
  not help and may hurt.
- **Running mean single-sample gain per triple:** {0, 1, 2} +2.1, {2, 3, 4} +2.3, {3, 4, 5} about +3 (shard 3
  pending), {5, 6, 7} +0.6. The second fresh triple {8, 9, 10} is still running.
- **triple {3, 4, 5}, 3 samples on both shards:** +2.3, +3.2, +4.1 (mean +3.2); a vote of 3
  samples gives +2.7.

  | Triple | Mean single-sample gain | Vote of 3 adjudicator samples |
  |---|---|---|
  | {0, 1, 2} | +2.1 (7 runs) | +2.8 |
  | {2, 3, 4} | +2.3 | +3.2 |
  | {3, 4, 5} | +3.2 | +2.7 |
  | {5, 6, 7} (fresh) | +0.6 | +0.5 |

  - Averaged over the four triples: about +2.0 per sample and +2.3 for the vote of 3.
  - The first three triples share seeds. {8, 9, 10}, which shares none, is still running.
- **idea G, divided investigators** (new; development only).
  - **What:** three tuned-v4 agents, each told to check a different third of the answer differences first and most
    carefully (`--focus-part k/3`: items k+1, k+4, ...). Each still gives a verdict on the whole contest. The
    evidence-only adjudicator then pools their looks, which now cover every difference in depth.
  - **Why:** the bottleneck is how carefully each disputed detail is looked at, not the number of opinions. Three
    seeds of the same agent tend to look at the same moments; division of labour should spread the close looks.
  - **Compared with:** the vote of the three divided investigators, and evidence-only over them (3 samples), each
    against the standard seed triples.
  - **Code:**
    - `judge/agent.py` takes `focus_part`, and `prompts/agent/first_message.j2` gets a "Your assignment" block shown
      only when it is set. The golden test still reports 0 differences.
    - A smoke test on one contest showed the assignment in the prompt.
  - **Runs:** agents `mg_v4t_f0..2_s3/s4` (tmux `p2l3`, `p2l0`), then adjudication `mg_adjev_tf*` (`p2m0`, `p2m3`).
- **the effect does not replicate on fully fresh investigators.**
  - Second fresh triple {8, 9, 10}, both shards: evidence-only samples -0.9 and -1.8 (mean -1.4; a third sample is
    running). Its investigators: singles 75.9, 69.1, 73.2; vote 75.5; at least one right 84.5.

  | Triple | Shares seeds with the selection triples? | Mean single-sample gain |
  |---|---|---|
  | {0, 1, 2} | is a selection triple | +2.1 |
  | {2, 3, 4} | is a selection triple | +2.3 |
  | {3, 4, 5} | yes (3, 4) | +3.2 |
  | {5, 6, 7} | no | +0.6 |
  | {8, 9, 10} | no | -1.4 (2 samples) |

  - **Reading:** the gain is concentrated in triples built from seeds 0-5, which include the two triples evidence-only was
    selected on. On the two fully independent triples it is about zero (mean about -0.4). The plan-004 development
    result was optimistic: selection on one sample per triple, and investigator triples that overlap.
  - **Recommendation for the held-out test:** do not run it as a confirmatory test of evidence-only. Its expected effect
    on fresh investigators is about 0 to +1 point, far below what 410 contests can detect. The draft pre-registration
    stays inactive; the user decides.
- **{8, 9, 10} is final:** -0.9, -1.8, -1.8 (mean -1.5); a vote of 3 adjudicator samples gives -2.7. The
  non-replication is confirmed.
- **Voting curve over 11 tuned-v4 seeds:** single 72.9, then a vote of 3 gives 74.3 (69.1-78.2 across triples), 5
  gives 74.8, 7 gives 75.1, 9 gives 75.3, 11 gives 75.5.
- **Applying the lesson to idea G:** a second independent set of divided investigators (seed salt 1, `mg_v4t_f*_r1`)
  is queued after the first (tmux `p2n3`, `p2n0`). Then 2 evidence-only samples over it. Idea G is judged on both
  sets against the distribution of 3-seed votes, not on one triple.
- **Idea G at the investigator level: no gain.** The divided triple votes 73.6% on shards 3-4 (220 contests). That is at
  the 32nd percentile of the 165 standard 3-seed triples (mean 74.3; 5th-95th percentile 70.9-77.3). At least one of
  the three is right in 84.5% of contests, against 85.4% for standard triples. Its singles look like ordinary seeds.
- The replication of G was stopped (its partial runs are in `zarxiv/ideaG_replication_stopped/`). The evidence-only
  adjudication over the first G set still runs (`p2m0`, `p2m3`).
- **Idea H, hi-res zoom for the investigators** (new; development only). Tuned v4 with `--zoom-side 1792`: the zoom tool
  returns crops up to 1792 px with the hi-res description (`tools/toolsets.yaml` zoom.hires). This was built for Muse,
  whose encoder takes up to 4096 visual tokens per image, but never run.
  - It targets perception directly.
  - 3 seeds × shards 3-4 (`mg_v4tz*`, tmux `p2z3`, `p2z0`), judged against the 11 standard seeds: singles mean 72.9,
    3-seed vote mean 74.3.
- **Idea G is a null.** Two evidence-only samples over the divided triple both equal its vote, 73.6% (+0.0); a third
  is finishing.
- **Idea H, early (2 of 6 runs):** one run is below the standard range on shard 3 (69.1 against 70.2-80.9) and one is
  above it on shard 4 (75.4 against 66.7-74.6). Mixed so far.
- **idea I, a proper multi-seed test of 30 turns** (development only).
  - Background: the 30-turn agent ran 3 times: 77.7 and 77.7 on shard 3, 74.6 on shard 4. The 11 standard
    8-turn seeds now available give shard 3 mean 74.7 (range 70.2-80.9) and shard 4 mean 71.6 (range 66.7-74.6), so the
    30-turn runs sit near the top. It was "the only remaining hint".
  - New seeds with the same flags (`--max-steps 30 --max-images 90`): shard 3 seeds 2-3, shard 4 seeds 1-3 (tmux
    `p2t0`, `p2t3`). That gives 4 seeds on each shard, judged against the 11-seed distribution.
  - It is an agent-level change, Muse-only, and would be a simple upgrade for the hackathon agent if it holds.
- **Idea G final, a null.** Evidence-only over the divided triple: +0.0, +1.4, +0.0 (mean +0.5); a vote of 3 samples
  gives +1.4. That is in line with the fresh triples (about 0).
- **Idea H interim, no gain.** With 2 of 3 seeds per shard:
  - shard 3: 69.1 and 72.3 (mean 70.7) against standard 74.7 ± 3.2;
  - shard 4: 68.3 and 75.4 (mean 71.8) against 71.6 ± 2.2.
  - Larger zoom crops do not improve Muse's judgements, and may hurt on shard 3.
- **idea I interim.**
  - **Shard 4, 4 seeds of the 30-turn agent:** 74.6, 71.4, 75.4, 69.8 (mean 72.8) against 71.6 ± 2.2 for the 11 8-turn
    seeds (+1.2). A vote of 3 gives 74.2 against 73.5.
  - **Shard 3:** the two older seeds (77.7, 77.7) against 74.7 ± 3.2; new seeds 2-3 are running.
  - The +2.5 hint shrinks on shard 4 with more seeds.
  - Scheduling lesson: one heavy agent lane per GPU. Two lanes of 30-turn agents thrashed the prefix cache.
- interim:
  - **Idea I (30 turns):** shard 4 now has 4 seeds (74.6, 71.4, 75.4, 69.8; mean 72.8) against the 11 standard seeds'
    71.6 ± 2.2: +1.2, and the three new seeds alone average +0.6. Shard 3 still has only the two older seeds (77.7
    each, +3.0); seeds 2-3 are running. The earlier "+2.5" hint is shrinking toward a small effect.
  - **Idea H (hi-res zoom):** shard 3 mean 72.3 over 3 seeds (-2.3); shard 4 mean 71.8 over 2 seeds (+0.3). **No
    gain.**
- **Idea I (30 turns): a modest gain.**
  - Shard 3, 5 seeds (77.7, 77.7, 76.6, 77.7, 81.9): mean 78.3 against the 11 standard seeds' 74.7 ± 3.2; +3.6, SE
    about 1.4.
  - Shard 4, 4 seeds (74.6, 71.4, 75.4, 69.8): mean 72.8 against 71.6 ± 2.2; +1.2, SE about 1.1.
  - Pooled: about +2 points per single agent, stronger on shard 3, the shard the agent was tuned on.
  - A fifth shard-4 seed runs now (GPU 3).
- **Idea H (hi-res zoom) final: no gain.** Shard 3 -2.3, shard 4 -0.1, over 3 seeds each.
- **idea I, shard 4's fifth seed: 69.8.**
  - Shard 4, 5 seeds (74.6, 71.4, 75.4, 69.8, 69.8): mean 72.2 against 71.6 ± 2.3; **+0.6, SE about 1.4**. A vote of 3
    (mean over all 3-seed combinations) gives 73.0 against 73.4.
  - Shard 3 is unchanged: +3.6 for single agents; a vote of 3 gives 80.7 against 75.3.
  - **Reading:** the 30-turn gain sits on shard 3, the shard the agent and its prompts were tuned on. On shard 4 it is
    about zero so far. Seeds 5-7 on shard 4 run now (GPUs 0 and 3) to settle it.
  - Report: `analysis/turns_report.py` (writes `runs/idea_i_report.md`); only finished runs are counted.
- **idea I, shard 4 with 7 seeds: no general gain.**
  - Shard 4 (74.6, 71.4, 75.4, 69.8, 69.8, 73.0, 71.4): mean 72.2 against 71.6 ± 2.3 for the 11 standard seeds,
    **+0.6, SE 1.1**. A vote of 3 gives 73.6 against 73.4.
  - Shard 3, where the agent and its prompts were tuned: +3.6 (SE 1.4) over 5 seeds; a vote of 3 gives 80.7 against 75.3.
  - **Verdict so far:** 30 turns help on the tuning shard and not measurably on the other one, at about 2.6 times the
    tokens. Keep 8 turns.
  - Seeds 7-8 on shard 4 run past the window (GPUs 3 and 0); `analysis/turns_report.py` updates the numbers.
- **idea I, shard 4 complete with 9 seeds: no gain.**
  - Seeds 7 and 8 scored 70.6 and 61.9. Seed 8 has no errors or missing verdicts, so its score is a genuine low run.
  - Shard 4 (74.6, 71.4, 75.4, 69.8, 69.8, 73.0, 71.4, 70.6, 61.9): mean 70.9 against 71.6 ± 2.3, **-0.7, SE 1.5**.
    Without seed 8, +0.4.
  - A vote of 3 gives 72.0 against 73.4.
  - 30 turns help only on shard 3, where the agent was tuned. Keep 8 turns.
  - The 30-turn runs also vary more between seeds than the 8-turn ones.
  - Shard 3 seeds 5-6 are finishing; they do not change the decision.
- **idea I final: 9 seeds of the 30-turn agent per shard; no general gain, keep 8 turns.**
  - Shard 3 (the tuning shard): 77.7, 77.7, 76.6, 77.7, 81.9, 77.7, 76.6, 83.0, 76.6; mean 78.4 against 74.7 ± 3.3,
    **+3.7 (SE 1.3)**. A vote of 3 gives 79.5 against 75.3.
  - Shard 4: mean 70.9 against 71.6 ± 2.3, **-0.7 (SE 1.5)**. A vote of 3 gives 72.0 against 73.4.
  - The gain appears only on the shard where the agent and its prompts were tuned, at about 2.6 times the tokens.
  - Report: `runs/idea_i_report.md`.
  - The 8-turn baseline is being extended to 12 seeds per shard (seed 11, 4 workers per GPU) only to keep the GPUs
    busy.

