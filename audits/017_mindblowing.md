# 017: From solid to unforgettable

Status: **plan; A starts now (no cost); B and C wait for the user's OK (paid)**. Written by the Portia coding agent (Claude). The user: "find new ideas to make the project absolutely mindblowing for judges".

## What judges remember

- Stage 3 picks the top 5 per track from the 3-minute video alone, so one visual that only a video product can show
  is worth more than another feature.
- Stage 2 rewards Impact, which needs believable numbers and a workflow, and Technical depth, which needs proof that
  holds out of sample.

## Ideas, ranked

| | Idea | Why judges care | Cost | Effort |
|---|---|---|---|---|
| **A** | **Search map: "720 hours, 6 seconds"** | Video-native wow; the demo's hook shot | $0 | 4 to 6 h |
| **B** | **Out-of-sample proof of the 82%** | Turns "development numbers" into a held-out result | about $1.3 Meta API | 1 h |
| **C** | **Portia against a frontier model alone** | "Does the jury beat one big model?" is every judge's question | about $1.1 Meta API | 1 h |
| D | **CI integration** (`portia audit eval.csv` + a GitHub Action posting a report) | Industry judges see it in their own pipeline | $0 | 2 h |
| E | **Final demo cut**: a 10-second cold open, title cards, a chaptered ready-to-upload video | Polished even if there is no time to edit | $0 | 2 to 3 h |
| F | **Verification receipts**: one shareable page per verdict (clip, frames, tier, inputs hash) | Media and compliance buyers | $0 | 3 h |

### A. Search map

- One strip stands for the whole searchable collection (for case 071, the Life domain's 94.8 hours, videos end to
  end).
- During an investigation, every search hit, contact sheet, transcript read and zoom appears on it live, coloured by
  investigator.
- When the verdict lands, the cited moments glow; the strip then zooms into the decisive video and its few seconds.
- The data already exists: the tool events and the corpus's segment durations. It works live, in replays and in the
  static gallery.

### B. Held-out check

- Spark 1.3 checking every verdict on the shard 5-6 investigator triple: 316 contests, already run and
  never used to design plan 014. It needs no GPU.
- A pre-registration is written before running: the claim, the metric (accuracy, and gain over the vote), and the
  decision rule.
- The Meta API cap needs about $1.5 more.

### C. Spark 1.3 alone

- Spark 1.3 as the whole agent on 100 development contests, against Portia's jury on the same contests.
- About $1.1 at the measured $0.011 per contest.

## Rules

Measured numbers only, development and held-out results labelled, Muse models only, GPUs 0 and 3.
