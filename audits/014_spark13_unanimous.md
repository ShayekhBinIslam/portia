# 014: Can Muse Spark 1.3 overturn a unanimous wrong verdict?

Status: **running**. Written by the Portia coding agent (Claude). The user, after the
unanimous-wrong numbers: "cool, could you try spark 1.3 on unanimous cases?"

## Why

`analysis/unanimous_report.py`, development shards 3-4, Portia's five investigator triples (1,100 contest-triples):

- **All three investigators agree on the wrong answer in 15.2% of cases.** That is 61% of Portia's errors, and 78%
  with Spark Open on splits. The adjudicator never sees these cases: it runs on splits only.
- **The Glimmer adjudicator cannot overturn them.** It ran on every contest of triple {0,1,2} (`mg_adjev_all`). On the
  160 unanimous contests it fixed 8 of 31 wrong verdicts and broke 9 of 129 right ones: net -1.
- **Spark 1.3 is untested on unanimous contests.** Some unanimous-wrong contests split in another triple, where it was
  right on 66% of them. On the hardest contests (at most 3 of 12 Glimmer seeds right) it was right on 33%.

## Design

- **What runs:** Spark 1.3 Contributor, the plan 013 evidence-only adjudicator with identical settings, plus `--all`.
  - Triple {0,1,2}, shards 3 and 4: `mg_adjs13all_t012_s3`, `mg_adjs13all_t012_s4`.
  - The 60 split contests send the same requests as plan 013 (`mg_adjs13_t012_*`), so they replay from the cache.
  - Only the 160 unanimous contests are new.
- **Cost:** about $0.0041 per adjudication, so about $0.66 in all.
  - Budget tag `plan014_unan`, stopping at $0.70.
  - The $2 cap holds ($0.71 left before this run).
  - Portia's live Spark 1.3 option keeps only what is left under the cap.
- **Data:** benchmark content goes to the Contributor tier. The user's OK is recorded in `meta_hackathon/.meta_locked`.

## Measures

- **Main measure, unanimous contests:** the wrong verdicts Spark 1.3 fixes and the right ones it breaks, against
  Glimmer's 8 fixed and 9 broken on the same contests.
- **Pipeline accuracy** for two designs:
  - Spark 1.3 on splits only: plan 013's design;
  - Spark 1.3 on every contest: it overrules unanimity.
- **The same two numbers on two subsets:**
  - unanimous contests where all three investigators were forced to answer (27.7% wrong);
  - the remaining unanimous contests.
- **Reading:** one triple, about 31 unanimous-wrong contests. A net gain of a few contests is noise. Only a clear gain
  justifies a replication on another triple, which would need a higher cap.

## Revision log

- written and started (tmux `p2u`).
- **triple {0,1,2} done: Spark 1.3 overturns unanimous wrong verdicts; Glimmer does not.**

  | Unanimous contests | Contests | Right / wrong | Spark 1.3 fixed / broken | Glimmer fixed / broken |
  |---|---|---|---|---|
  | All | 160 | 129 / 31 | 15 / 4 (+11) | 8 / 9 (-1) |
  | All three forced to answer | 64 | 45 / 19 | 12 / 2 (+10) | 5 / 6 (-1) |
  | The rest | 96 | 84 / 12 | 3 / 2 (+1) | 3 / 3 (0) |

  - **Pipeline on the 220 contests:**
    - vote 75.5%;
    - Spark 1.3 on splits only 80.0%;
    - on splits plus the "all forced" unanimous contests 84.5% (0.56 calls per contest);
    - on every contest 85.0%.
  - **Cost:** $0.695, $0.0043 per unanimous adjudication.
- **the user raised the cap to $4:** "let's use a $2 more to get fuller run".
  - Triples {5,6,7}, {8,9,10} and {3,4,5} run with `--all` (tmux `p2u2`), with tag `plan014_unan` stopping at $2.50
    cumulative.
  - One triple can mislead: plan 004's +3.6 did not replicate. These decide.
- **replicated on both fresh triples:** {5,6,7} net +8, {8,9,10} net +7 (`runs/plan014_report.md`).
  - **Three triples pooled** (660 contest-triples, 485 unanimous, 99 of them wrong):
    - Spark 1.3 fixed 44 and broke 18 (+26; two-sided sign test p = 0.001; contest-triples share contests, so the
      effective sample is smaller);
    - all three forced: 28 fixed, 8 broken;
    - the rest: 16 fixed, 10 broken.
  - **Pipeline:**
    - vote 74.8%;
    - Spark 1.3 on splits only 78.8%;
    - plus the "all forced" unanimous contests 81.8% (0.55 calls per contest);
    - Spark 1.3 on every contest **82.7%**.
  - **Against Spark Open:** on splits only, on the same 660 contest-triples, it reaches 80.6%. Spark 1.3 checking every
    verdict beats it at about a quarter of the cost: about $0.004 per contest against $0.017.
  - **Cost:** $0.0037 per unanimous adjudication.
  - Triple {3,4,5} is running.
- **final, four triples.** {3,4,5} adds +4 (15 fixed, 11 broken). Its "all forced" subset breaks
  even (7 / 7).
  - **Pooled** (880 contest-triples, 647 unanimous, 132 of them wrong):
    - Spark 1.3 fixed 59 and broke 29: +30 (sign test p = 0.002);
    - all three forced: 35 / 15;
    - the rest: 24 / 14.
  - **Pipeline:**
    - vote 74.1%;
    - Spark 1.3 on splits only 78.6%;
    - plus the "all forced" unanimous contests 80.9% (0.55 calls per contest);
    - **Spark 1.3 on every contest 82.0%** (1 call per contest).
    - Spark Open on splits only, same runs: 80.3%.
  - **Track records for Portia:**
    - agreed and confirmed by Spark 1.3: 486 / 559 = 86.9% right;
    - agreed but overturned by Spark 1.3: 59 / 88 = 67.0% right.
  - **Cost:** $2.378 for 647 unanimous adjudications, $0.0037 each. Total Meta spend $3.67 of the $4 cap.
  - **Decision:** "Spark 1.3 checks every verdict" is the best measured design, and the cheapest frontier option, at
    about $0.004 per case. The "all forced" shortcut is not reliable (one triple breaks even).
