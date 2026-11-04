# Portia audits

Every plan for Portia is written here **before** it is implemented. An outside verifier agent
reviews each plan, reads the code it touches, and writes feedback. The user decides; implementation starts only
after the review, unless the user says otherwise.

## Files

| File | Written by | Content |
|---|---|---|
| `000_context.md` | Claude (Portia coding agent) | The state of the project: what exists, what was found, the rules. Read this first. |
| `NNN_<slug>.md` | Claude | One plan: goal, design, fairness rules, evaluation, expected effect, risks, open questions. |
| `NNN_<slug>.review.md` | the verifier agent | Feedback on plan NNN: problems found, required changes, verdict. |

`NNN` counts up in creation order and is never reused.

## A plan's status

Each plan starts with a status line, one of:

- **draft**: written, not yet reviewed
- **revised**: changed after a review; the revision log at the end says what changed and why
- **approved**: the user approved it after review
- **running**: implemented and running
- **done**: finished; the results section is filled in
- **dropped**: abandoned; the reason is stated
- **on hold**: parked by the user's decision; it may be picked up later as written

## Rules every plan follows

- **No ground-truth leakage.** The judge never sees the dataset's labels or metadata. That includes the better
  side, the degradation lists, `hop_1` / `bridge` / `hop_2` and the evidence clip ranges. Ground truth is used only
  to score runs and in analysis afterwards.
- **Held-out data.** A confirmatory test is pre-registered in `runs/PREREG_*.json` before any of its runs. Its
  shards must not have informed the design.
- **Claims are paired.** Accuracy claims compare setups on the same contests, with an exact McNemar test, and count
  a missing verdict as wrong. Single runs vary by about ±3 points between seeds, so effects are reported with that
  noise in mind.
- **Reproducible.** Every change to prompts or tools keeps earlier requests byte-identical unless the plan says
  otherwise (`tests/golden_requests.py`).
