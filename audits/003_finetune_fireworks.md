# 003: fine-tuning Muse Glimmer on Fireworks (free LoRA SFT)

Status: **on hold** (the user: "lets keep fireworks/finetune for later"). Written by the Portia coding
agent (Claude). Nothing has been uploaded to Fireworks, and no Fireworks command has been run. A review is welcome
but not urgent. The free SFT offer runs past the hackathon.

## Goal

The user has a Fireworks account and wants fine-tuned models in the Portia pipeline, as the judge or as helpers.
Fireworks trains **LoRA SFT on Muse Glimmer 30B for free**. This plan uses it to train adapters and
measures each against the base model on contests whose questions it never saw.

- **First target: the judge's verdict.** The ground-truth analysis found that a losing judge usually located the same
  disputed detail as the winner and then judged it wrongly (`000_context.md`).
- **The recipe is "self-taught judge" SFT:** sample the base judge, keep only its verdicts that ground truth marks
  right, and fine-tune on them. This is rejection-sampling fine-tuning. It is the recipe of Self-Taught Evaluators
  (Wang et al., 2024, arXiv 2408.02666), which trained a text judge on its own correct judgements of pairs whose
  better answer was known by construction. Our degraded answers are such pairs.

## What Fireworks offers (checked against public pages)

| Fact | Source |
|---|---|
| "Muse Glimmer 30B SFT is free via UI and Serverless Training API" for LoRA SFT jobs started before the offer ends; "No credit card required". | docs.fireworks.ai/fine-tuning/training-api/cookbook/muse-glimmer; fireworks.ai/blog/train-muse-glimmer-for-free |
| "RL, DPO, full-parameter training, deployments, and inference outside the training run are not covered." Paid prices: LoRA SFT $3 and LoRA DPO $6 per 1M training tokens; on-demand GPUs $8-13 an hour. | same cookbook page; fireworks.ai/pricing |
| **Conflict:** the user's dashboard says "Train on any dataset for DPO at no cost". The public pages say DPO is not covered. The plan treats DPO as paid until the user confirms otherwise. | dashboard screenshot |
| Managed DPO accepts only text ("content: a string") and only one-turn conversations. | docs.fireworks.ai/fine-tuning/dpo-fine-tuning |
| SFT accepts images as base64 data URIs on user messages (and, for Muse, on tool messages); multi-turn conversations; `tools`, tool calls and tool messages; a per-message `weight`; and reasoning in `reasoning_content`. | docs.fireworks.ai/fine-tuning/fine-tuning-models; fw-ai/cookbook `training/renderer/muse_glimmer.py` |
| Training context up to 131,072 tokens (LoRA on 1 B200). The default maximum length is 2,048, so it must be raised. Image tokens count toward it. LoRA rank defaults to 8. | docs.fireworks.ai/fine-tuning/models; cookbook page |
| At most 1 concurrent job on the free model (the dashboard's "0/1"). Web uploads are capped at 1 GB; the `firectl` upload limit is not documented. | dashboard; changelog |
| A trained LoRA "cannot be served on serverless inference", and base Glimmer left serverless. `firectl model download` returns a PEFT adapter, which Fireworks warns may target a base that differs from the public weights. | cookbook page; docs.fireworks.ai/fine-tuning/deploying-loras |
| Uploaded data is "never used to train Fireworks-owned or shared models". Datasets stay until deleted; checkpoints are kept 30 days. | docs.fireworks.ai/guides/security_compliance/secure_training |

**Consequences.** Training runs on Fireworks; **all inference stays local.** Downloaded adapters are served by our
vLLM 0.32, whose `MuseGlimmerForCausalLM` declares LoRA support (applied to the language model, not the vision
encoder). Nothing paid is used: no DPO, deployments, Training-API RL or Fireworks inference without the user's
approval.

## The data problem, and the fix: folds by question

- **The shards cannot be the train/test split.** The 630 contests come from 343 questions, and the shards were cut by
  contest, not by question. 139 of the 187 questions in development shards 3-4 also appear in shards 1, 2, 5 or 6
  (`000_context.md`). An adapter trained on shards 3-4 would have seen the videos and gold answers of 42% of the test
  contests.
- **Questions barely share videos.** The 343 questions form 334 groups linked by a shared video; only 9 videos are
  used by two questions.
- **So: question-grouped 3-fold cross-fitting.** The 334 groups are dealt into 3 folds, stratified by domain, in a
  fixed order (sha1 of the group id). Adapter *k* trains only on questions outside fold *k* and judges only fold
  *k*'s contests. Every one of the 630 contests is then judged by an adapter that never saw its question, its videos
  or any of its answers.

| Fold | Questions held out | Campaign contests held out | Training questions |
|---|---|---|---|
| 0 | 118 | 220 | 225 |
| 1 | 114 | 206 | 229 |
| 2 | 111 | 204 | 232 |

## Experiment 1: self-taught SFT of the static judge

**Why the static judge first.** Its prompt is one fixed request per contest: 128 frames from shared-text retrieval,
transcripts, the rubric, the question and both answers. Seeds answer the same request, so samples can be filtered
without rebuilding anything. It is the best simple setup (76.3% by vote on shards 5-6).

### Training examples for adapter *k* (training questions only, existing samples only)

- **Source:** the base model's own static shared-text samples, already on disk. Shards 3-4 have 4 seeds and shards 5-6
  have 3; plan 002 adds 3 on shards 1-2. Contests of fold *k*'s questions are excluded.
- **Filter:** keep samples whose verdict matches ground truth, and drop any whose answer came from a fallback (no
  verdict of its own).
- **How many per contest:** every training contest with a right sample gives 1 example, chosen by a fixed hash.
  Contests with both right and wrong samples give 2, because they carry the most signal. Contests with no right sample
  give none.
- **Example format:** the exact request the static judge sent (system, user with 128 images, reasoning-strength
  setting), followed by the assistant message with `reasoning_content` and the final text. It is rendered with
  Fireworks' Muse renderer.
- **Expected size:** about 380-420 examples per fold. Over shards 3-6, 431 of 536 contests have a right sample and 110
  are mixed; shards 1-2 add their share. Each example is about 62k tokens and 7 MB, so about 2.7-3 GB and 25M
  tokens per fold.

Ground truth is used only to filter training samples, and only for training questions.

### Training settings (fixed now; no tuning on held-out folds)

LoRA rank 16, 1 epoch, Fireworks' automatic learning rate, maximum length 65,536 tokens, default batch size. A
setting may change only for a mechanical reason found in the pilot (a job that fails, a length that does not fit).

### Stages

| Stage | What | Gate to continue |
|---|---|---|
| 0. Pilot | One SFT job on 20 examples from fold 0's training contests, uploaded with `firectl` | Total spend stays at $0. The upload size works. The adapter downloads, and its `adapter_config.json` targets only language-model modules. The adapter serves locally (DFlash on if vLLM allows it, else off). Its verdicts parse on 20 of fold 0's *training* prompts. Fireworks' renderer and the local chat template give the same tokens for one example. |
| 1. Training | 3 SFT jobs, one per fold, one at a time | Each job finishes at $0 total spend |
| 2. Evaluation | One local server holds all 3 adapters (`--enable-lora`, `--max-lora-rank 16`). Each adapter judges its held-out contests, 3 seeds (salts 0, 1, 2), with byte-identical prompts and the same sampling as the base runs. | - |

### Evaluation (pre-registered in `runs/PREREG_ft_static_sft.json` before stage 2)

- **Primary:** adapter seed 0 vs base static shared-text seed 0, over all 630 contests, paired exact McNemar, alpha
  0.05, a missing verdict counted as wrong.
- **Secondary:**
  - vote of 3 vs vote of 3, and adapter seed 0 vs the base's vote of 3 (does SFT put the vote's gain into one sample?);
  - each fold separately;
  - side balance;
  - reasoning length.
- **Power:** with about 18% discordance, 630 contests give about 113 discordant pairs. That detects about 4 points
  (69 vs 44, p ≈ 0.02) but not reliably 3 (66 vs 47, p ≈ 0.09).

### Expected effect (honest prior)

| Source of gain | Expected Δ (single run) |
|---|---|
| Sharpening toward the model's own majority behaviour: voting 3 seeds gave about +2 | +1 to +2 |
| Fixing systematic weighing errors that the right samples avoid | 0 to +2 |
| Contests the base never gets right (20%): SFT on right samples alone does not reach them | about 0 |
| Perception itself | about 0 |
| **Total** | **+1 to +3 over the base static judge.** A null result is quite possible. |

Self-Taught Evaluators reported large gains on text. Here the main error is perceptual, so expectations stay low. The
adapter is still a hackathon result: a Meta open model fine-tuned as a video judge, measured on unseen questions.

## Later experiments (each gets its own plan file before it runs)

| # | Adapter | Training data (training questions only) | Free on Fireworks? |
|---|---|---|---|
| 2 | **Agent SFT** (the user's "agentic pipeline"): the tuned-v4 agent, multi-turn with tool calls and tool images | its own right trajectories; the exact requests are rebuilt with the existing replay used by `tests/golden_requests.py`; only assistant turns weighted | yes (SFT supports tools, tool messages, images) |
| 3 | **Claim verifier** for plan 001: one frame or crop + one claim → supported / not / unclear | gold vs degraded attributes (`attribute_degradations`), with frames from the ground-truth clip ranges | yes; examples are small |
| 4 | **Decomposer** for plan 001: question + answers → hop 1, bridge, hop 2, claims | the dataset's `hop_1`, `bridge`, `hop_2` as targets (text only) | yes |
| 5 | **Search-query writer**: question + answers → queries | queries whose results hit the ground-truth clip ranges (text only) | yes |
| 6 | **Round 2 of Experiment 1:** the adapter samples the 1,771 answer pairs the campaign did not use, then SFT again | right samples only | yes, but about 20 GPU-hours of local sampling |
| - | DPO variants (verdict, decomposer) | right vs wrong samples | only text-only; free only if the user's dashboard is right |

**Outside Portia** (to discuss with the user):
- **1_lib question generation:** a local Muse gate distilled from the logged decisions of the pipeline's paid gates.
  This would make generating more questions cheaper.
- **3_inference:** a cheaper evaluator for future campaigns.

## Fairness rules, specific to this plan

- Adapter *k* never sees any part of a fold-*k* question: not its contests, unused answer pairs, frames,
  transcripts or samples.
- At test time the adapter's inputs are byte-identical to the base judge's. Labels and dataset metadata never enter
  a prompt.
- Settings are fixed before training, and nothing is tuned on held-out results.
- **Protecting plan 001.** Shards 1, 2, 5 and 6 are plan 001's test set.
  - Results on their contests are reported only in aggregate until plan 001's test has run.
  - These adapters are not used in plan 001's confirmatory test, since each one trained on some of those contests.

## Cost, compute and data leaving the box

- **Fireworks:** 4 SFT jobs (pilot plus 3 folds), free under the published offer. The UI's cost line must read
  "Free" before each submission. Total spend is checked after each job and must stay at $0. No DPO, deployments or
  Training-API RL without the user's go.
- **Local GPUs 0 and 3:** no new sampling for Experiment 1. Evaluation is 630 contests × 3 seeds ≈ 1,900 static
  requests, about 6 hours (longer if DFlash must be off).
- **Upload:** about 3 GB per fold plus the pilot (about 9-10 GB in all). It holds frames from the dataset's YouTube
  videos, transcripts, questions, answers and Muse's outputs. **Nothing is uploaded without the user's OK.**
  Uploaded datasets stay on Fireworks until the user decides to delete them.
- **Credentials:** the Fireworks key comes from an env file the user names. It is never printed or logged, and
  `meta_hackathon/meta_hack.env` stays locked.
- **Timing:** about 2 days from approval (the pilot, 3 jobs one at a time, then 6 hours of evaluation). That is
  before the hackathon deadline and well before the offer ends.

## Risks

- **The base model may differ.** Fireworks may train against a different copy of the base model, for example
  quantized. The pilot checks that the downloaded adapter loads and behaves sensibly. If it targets vision-encoder
  modules, vLLM would ignore them, and the experiment stops for review.
- **Rendering mismatch.** Training uses Fireworks' Muse renderer and inference uses the Hugging Face chat template in
  vLLM. If their tokens differ (system prompt, the reasoning turn, the image placeholders), the adapter learns a
  different format. The pilot compares the two on one example.
- **Upload limits.** If `firectl` also caps uploads near 1 GB, each fold keeps about 140 examples. The mixed
  contests go in first.
- **DFlash with an adapter.** The drafter was trained against the base model, so fewer drafted tokens may be
  accepted. The outputs are still exact, since the adapted model checks every token. If vLLM refuses the
  combination, evaluation runs without speculation.
- **Small data:** about 400 examples per fold. LoRA rank 16 and 1 epoch limit overfitting, and side balance and
  reasoning length are reported.
- **Many comparisons:** plans 001 and 003 test on overlapping contests. Each pre-registers one primary comparison,
  and the reports state how many were made.

## Open questions for the reviewer

1. Is question-grouped 3-fold cross-fitting over all 630 contests an acceptable confirmatory design? Every shard has
   already been touched by prompt and tool design, though never by weight training.
2. Should contests with both right and wrong samples count twice, or should every contest count once?
3. Is comparing against the existing base runs sound, or should the base be re-run under the adapter's serving
   configuration (for example, if DFlash has to be turned off)?
4. For contests the base never gets right (20%), should "rationalised" answers be allowed: the model told the
   right verdict and asked to justify it, as in STaR? This is excluded for now, because such answers can mention the
   hint.

## Questions for the user

1. Where is the Fireworks API key? (An env file path; it will never be printed.)
2. May the training data (about 10 GB: video frames, transcripts, questions, answers, Muse outputs) be uploaded to
   Fireworks?
3. Your dashboard says DPO is free; the public docs say only SFT is. Should DPO stay out unless the job page shows
   "Free" for that exact job?

## Revision log

- first draft (DPO-first), written before the Fireworks facts were checked.
- rewritten around free LoRA SFT. The public pages say DPO is not covered by the offer, and managed
  DPO takes only text in one turn, so the image-heavy judge cannot be trained with it. SFT takes images, tools and
  reasoning. Experiment 1 now needs no new sampling. The fold design is unchanged.
