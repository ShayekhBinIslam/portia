# 001: a verified judge (verification layer on the Muse agent)

Status: **draft**. Written by the Portia coding agent (Claude). Not implemented: it waits for review.

## Goal

Add a verification layer, modelled on Meta's legal-agent workshop (github.com/meta-models/legal-agent-workshop),
to the tuned Muse agent, and measure whether it helps.

- **What the workshop is:** one agent plus checks the agent cannot skip. The tools run the checks at fixed points. A
  failed check refuses the step with feedback; repeated failures escalate.
- **What we test:** whether this makes Muse Glimmer's verdicts more accurate. Independently of accuracy, it makes
  them auditable: every verdict rests on a table of claims, each with a cited frame.
- **Verifier model:** Muse Glimmer, the same model as the agent, for this run (the user's decision). A
  stronger verifier, Muse Spark via the locked Meta API credits, is a later plan.

## Fairness rules, specific to this plan

- **The decomposition is derived at runtime.** Hop 1, the bridge, hop 2 and the list of disputed claims come only
  from the question and the two answers. The dataset's `hop_1`, `bridge`, `hop_2`, `clip_ranges` and degradation
  lists are never read by the judge (user).
- **The claim checklist's coverage check uses the answer diff** (`judge/answer_diff.py`), which is computed from the
  two answers alone. This differs from the workshop, which checks coverage against a ground-truth checklist; doing
  that here would leak the labels.
- **Ground truth is used only to score runs, and in analysis afterwards.**

## Design

| Stage | What the agent does | Gate (outside the agent's control) | On failure |
|---|---|---|---|
| 0. Retrieval | Answer-grounded overview of the 64 best segments, as in tuned v4 | - | - |
| 1. Plan | Calls `set_plan`: hop 1, the bridge and hop 2 in its own words, plus a claim checklist. Each claim says what A states, what B states, and which hop it concerns. | **Coverage:** every item of the answer diff is referenced by at least one claim. Deterministic. | Refused, naming the uncovered diff items. After 3 tries the plan is accepted and flagged. |
| 2. Investigate | Uses the tuned-v4 tools, plus a new `record_observation(claim, video, t, region?, observation)` | **Evidence:** `(video, t)` must lie inside a visual tool output this agent actually received (zoom within ±2 s, a burst window, a contact-sheet range, a view_frames segment). Checked against the toolbox call log. | Refused: "look at that moment first" |
| 3. Verify | (the harness) For each recorded observation, a **fresh-context Muse Glimmer call** sees only the frame re-rendered at `(video, t, region)` and the observation text. It does not see the question or the answers. It replies `supported / not supported / unclear` as a structured choice. | **Support**, as in the workshop's `verify_claims` | The observation is marked unverified, and the agent is told so in its next tool result |
| 4. Verdict | Calls `answer`, now with a per-claim table: which answer each verified observation supports | **Rules:** the verdict must follow from the table. The answer with fewer verified errors wins, and unverified claims count for neither side. | Refused once with the tally ("your table gives A 2 verified errors and B 0"). Then the rule's verdict stands. |
| Escalation | - | Any gate refused 3 times, or no claim was verified | The contest takes the **static shared-text judge's verdict** (seed 0, already on disk) and is flagged `escalated`. |

**How stage 3 differs from the failed "blind inspect" (tools v5).** Inspect asked generic neutral questions after
every look. This verifier checks one specific, cited observation against its frame. It is closer to the workshop's
claim check. Because it is the same model, its errors may still correlate with the agent's; see "Expected effect".

## Implementation outline, for the code review

- **New toolset `v6`:** v4 plus `set_plan`, `record_observation`, and a claim table in `answer`. Definitions go in
  `tools/*.yaml` and `tools/toolsets.yaml`.
- **New prompt** `prompts/system_v6.md`.
- **Gate feedback** as templates in `prompts/verify/*.j2`.
- **Gates** in `judge/verify/`, one file each with one entry point `run(ctx, work) -> {passed, feedback}`, as in the
  workshop: `coverage.py`, `evidence.py`, `support.py`, `rules.py`.
- **Flags:** `--tools v6 --verify`. Everything is opt-in, and the golden-request test must stay at 0 differences for
  every existing configuration.
- **Logging:** the trajectory records the plan, every observation with its gate results, refusals and the
  escalation. The explorer shows the claim table.

## Evaluation

1. **Development** on shards 3 and 4 (220 contests), where 5 seeds of tuned v4 and 4 of static exist. One run of
   v6. Only obvious failures get fixed: gates that loop, a parser that fails. Prompts are not tuned on
   per-contest results.
2. **Confirmatory test**, pre-registered in `runs/PREREG_verified_judge.json` before any v6 run on these shards:
   - **Contests:** shards 1, 2, 5 and 6, 410 in total. None informed any Muse design.
   - **Primary comparison:** v6 seed 0 against tuned v4 seed 0, paired exact McNemar, alpha 0.05, no verdict counted
     as wrong.
   - **Secondary measures:** v6 against static shared-text seed 0; the escalation rate; accuracy on the contests
     that were not escalated; how often each gate refused.
   - **Power:** 410 contests with about 20% discordance gives about 80 discordant pairs. That detects about 5 points
     (50 vs 30, p ≈ 0.03) but not 3 points (46 vs 34, p ≈ 0.2).

## Expected effect (honest prior)

| Component | Error it targets | Expected Δ |
|---|---|---|
| Evidence gate | Verdicts reached without looking: 11% of contests never looked at the relevant video, and those were 60% right | +1 to +2 |
| Rule-based verdict | Wrong aggregation of correctly judged details | 0 to +2 |
| Glimmer verifier | Misjudged details, the main bottleneck | about 0 (the same model; inspect gave nothing) |
| Escalation to static | Contests where the agent cannot ground any claim | +1 to +2 |
| **Total** | | **0 to +3 over tuned v4.** The chance of reaching significance on 410 contests is low, about 20-30%. |

Beyond accuracy, the plan gives:
- an auditable claim table with cited frames for every verdict;
- an abstention signal (escalations), so accuracy at a given coverage can be reported;
- the harness that a stronger verifier (Muse Spark) plugs into later. That is where a +3 to +8 gain is plausible.

## Risks

- **A wrong bridge in stage 1** sends every hop-2 claim to the wrong moment. Mitigation: the plan names the bridge,
  and the evidence gate requires a looked-at moment for hop-2 claims.
- **Gate loops can waste turns.** Mitigation: at most 3 refusals per gate. The turn budget is 12, up from 8, to
  cover the extra calls. Turns 8 to 30 showed no accuracy cost.
- **The verifier may reject true observations,** which leads to more unverified claims and more escalations. The
  escalation rate is reported.
- **Cost:** about 1.5 to 2 times as many calls as tuned v4. Development takes about 2-3 hours and the confirmatory
  run about 5-6 hours, both on two GPUs.

## Open questions for the reviewer

1. Is checking coverage against the answer diff enough, or can the agent satisfy the gate while leaving real
   differences unchecked?
2. Should a contest with no verified claims escalate to static, or should it abstain and be reported separately?
3. Is v6 seed 0 vs tuned v4 seed 0 the right primary comparison, or should it compare votes of 3 seeds (3 times the
   compute)?
4. Does running plan 002's baselines on shards 1-2 (aggregate scores only) contaminate them as a test set? See plan
   002.
5. Found after drafting: 172 of the 410 test contests (42%) share a question with development shards 3-4. Shard 3,
   where Muse was tuned, accounts for 77 of them (19%). See `000_context.md`. Should the pre-registration add a
   sensitivity analysis on the 238 test contests whose question never appears in shards 3-4, or make that subset the
   primary test?

## Revision log

- first draft.
- later: added open question 5 (question overlap between test and development shards). The design is
  unchanged.
