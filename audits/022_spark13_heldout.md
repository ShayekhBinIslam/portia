# 022: Muse Spark 1.3 on the held-out shards (pre-registered)

The user raised the hackathon's Meta API cap to $30 ("for hackathon i raise the cap to 30 USD; make final
tests"). Every Spark 1.3 number in the README and on the Proof page comes from the development shards 3-4. This test
runs the same two Spark 1.3 modes once on the held-out shards 5-6, which no choice has used, and reports the result
whatever it is.

## What runs

- Investigators: the triple already fixed by audit 021, `mg_v4t_s5`, `mg_v4t_r1_s5`, `mg_v4t_r2_s5` and the same three
  on shard 6 (158 contests each, 316 in all). No new investigator runs.
- Adjudicator: Muse Spark 1.3 Contributor on the Meta Model API with the development settings of plan 014, unchanged:
  `judge/adjudicate.py --backend meta --variant evidence --all` (max 4 steps, 3 views, order salt 0, seed salt 0).
  Runs `mg_adjs13all_ho_s5` and `mg_adjs13all_ho_s6`; stop at $5.
- One run per shard. No retries except for API errors, no prompt or setting changes after the first result.

## What is reported

Computed by `analysis/heldout_022.py` with the method of audit 021 (95% bootstrap intervals over contests):

1. Spark 1.3 checking every verdict (`spark13all`): accuracy on all 316 contests and on the 179 whose question never
   appears in development.
2. Spark 1.3 on splits only (`spark13`): Spark's ruling on the contested contests, the unanimous vote elsewhere. Same
   run, so no extra requests.
3. Against the same contests: the majority vote (75.3%) and Portia on Muse Glimmer alone (81.0%) from audit 021.
4. On unanimous contests: how many wrong unanimous verdicts Spark 1.3 fixed and how many right ones it broke.

Development values to compare with: check-all 82.0% (880 runs), splits only 78.8%, fixed 59 and broke 29.

## Decision rule

None for the product: the default stays Muse Glimmer alone. The README and the Proof page report the held-out
numbers next to the development ones, including a drop if there is one.

## Result (one run each, $1.18)

From `analysis/heldout_022.py` (writes `runs/heldout_022.json`):

| contests | n | majority vote | Portia on Muse Glimmer alone | Spark 1.3 on splits | Spark 1.3 checking every verdict |
|---|---|---|---|---|---|
| all held-out | 316 | 75.3% [70.6, 80.1] | 81.0% [76.6, 85.1] | 81.3% [76.9, 85.8] | 81.6% [77.2, 85.8] |
| question not in shards 3-4 | 179 | 76.0% [69.3, 82.1] | 81.0% [75.4, 86.6] | 82.1% [76.5, 87.7] | 79.3% [73.2, 84.9] |
| development | | 74.0% | 75.2% | 78.8% | 82.0% |

On held-out data the two Spark 1.3 modes are as accurate as Muse Glimmer alone; all three intervals overlap almost
completely. Of the 230 unanimous verdicts, 40 were wrong: Spark 1.3 fixed 16 and broke 15, a net gain of one contest,
against 59 fixed and 29 broken over 880 development runs. The development gain of the check-all mode came mostly
from splits the Glimmer adjudicator got wrong (63.7% right in development, 76.7% on these held-out splits) and from
the re-check of agreed verdicts, which did not repeat here. As pre-registered, the product default stays Muse Glimmer
alone, and the README, the Proof page and the How page now show both sets of numbers.
