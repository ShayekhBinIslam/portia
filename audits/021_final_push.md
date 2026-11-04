# 021: The last 39 hours: what wins, in order (draft v2)

Status: **draft for the user's decisions.** Written by the Portia coding agent (Claude) after the user: "let's stop discord
extraction; could we plan what is the best we can do", then "firework can do sft on image-text data ... could we use
this for routing or something like that?". v2 adds an outside review (a separate agent read this plan, the official
rules and the office-hours rulings; every quote below was checked against the Discord export).

After the submission deadline there are no edits: "the repo is frozen at the deadline".
Judges "work mainly from the 3-minute video and the public repo"; "a hosted demo isn't required". The top 5 per track
are judged live at the closing ceremony.

## Where we stand

- **Video: done.** `product/video/out/Portia.mp4` (2:56.3, opens with what came before, 76% product footage,
  a labelled live run); X cut `Portia_x.mp4` (38 s).
- **Live app:** https://portia.shayekh.tech; gallery of 37 recorded runs; the new-question race fixed today.
- **Missing:** the public repo, a hosted video link, the submission form.

## The biggest risk: the one non-Meta model

Office hours (thread "Embedding and reranking models"): "every model your project calls at runtime has to be
a Meta model. Organizers have since updated the rule, so open-source non-Meta models can no longer run alongside
Meta's models." The user's "keep qwen" predates this. Qwen3-VL-Embedding-8B embeds every agent search query
at runtime (`judge/embed_client.py`) and every newly added video (`product/ingest.py`).

- **Ask tonight** (the user's organizer DM, or office hours). Draft: "Quick rules check for Portia
  (Indie): every reasoning and judging call is a Meta model (Muse Glimmer on our GPUs, Muse Spark 1.3 on the Meta
  Model API, Muse Spark Open on Baseten). Our video search uses an index we built before the hackathon with an open
  embedding model (Qwen3-VL-Embedding), and at runtime the agents' search queries are embedded with that same model.
  Given the update, is this query encoder allowed, or must we switch search to Meta's Perception Encoder?"
- **Prepare the fallback in parallel:** a Meta-only search mode from plan 015 (Perception Encoder for frames, BM25 for
  transcripts; BM25 is not a model). Measured retrieval: the evidence in the top 8 for 57.7% of cases against 78.2%
  for Qwen, so accuracy will drop. Tonight the GPUs measure the agent with it on a development subset, so a switch
  would ship with honest numbers. The video's numbers were measured with Qwen search; if search changes, the README
  and the form say so.

## Must do (eligibility)

| # | What | Who | Time | When |
|---|---|---|---|---|
| 1 | **Settle the runtime-model rule** (above). | User: DM. Me: fallback. | 15 min + 4-6 h GPU | Tonight |
| 2 | **Open the submission form now** and list every question ("a decent amount of questions"); I draft all answers. No access codes in it: "there is no private field or channel for judge credentials". | User: open and paste. Me: drafts. | 1-2 h | Tonight |
| 3 | **Public repo** (create it now; it freezes at the deadline). "The project has to run from the public repo's setup instructions": `.env.example` (Meta Model API and Baseten keys), how to serve Muse Glimmer (vLLM + DFlash), no `/data2` paths, and a judge path with committed recorded runs ("recorded sample runs and an offline mode with committed results are accepted"). Copy from an allowlist, then scan for secrets. Never in it: `meta_hack.env`, `public.env`, tokens, `runs/`, `.cache/`, `analysis/detector_test`, any video or frame (`product/site`, `product/jobs/*/img`, `product/collections`, `demo_footage`, `data/`, `logs/`, `pod/`). README: what came before, each Meta model and where it runs, the measured results and their sources, NEW_WORK.md as the contribution log, the data terms. | User: create the empty repo, name and license. Me: everything else. | 5-6 h | Start tonight |
| 4 | **Data rights.** "You must have the rights to any data you use, and that includes evaluation." The README states the benchmark's license and terms, that videos are not redistributed, and that frames appear only as cited evidence. | User: the dataset's license. Me: text. | 30 min | With 3 |
| 5 | **Video hosted tonight** on YouTube; Content ID may flag the drama and documentary footage, so keep a fallback host off this box (e.g. Vimeo or Google Drive). | User | 20 min | Tonight |
| 6 | **YouTube-link ingest off on the public site** (it downloads with yt-dlp: a platform-policy risk, and the user's rule). File uploads stay. | Me | 20 min | Tonight |

## Should do (score)

| # | What | Why | Cost |
|---|---|---|---|
| 7 | **Judges' path without credentials:** the gallery already replays every recorded run openly; optionally an open, rate-limited, Glimmer-only mode for new questions (it must never spend the Spark budget: a spent budget returns HTTP 409). | "A gated demo needs a way to verify features without credentials" | $0 |
| 8 | **Most Viral ($20K):** the 38 s cut with a short thread (I draft); the user posts it and puts the link in the form. | A separate $20K | $0 |
| 9 | **Held-out check, Glimmer arm only:** the held-out investigator triple exists (`runs/mg_v4t{,_r1,_r2}_s5/_s6`, 316 contests); pre-register, adjudicate with Glimmer on our GPUs, report it. No Spark 1.3 on held-out: its tier trains on what it is sent. | "Is this held out?" | $0 |
| 10 | **Fireworks, the user's idea (stretch, after 1-6):** a Muse Glimmer LoRA (image + text SFT, free) trained on our development runs to flag verdicts that are likely wrong, so Spark 1.3 runs only there: a learned router replacing audit 020's hand rule. Training: the dev triples with answer keys (question-grouped folds, [[question leakage]]); test: the held-out triple with answer keys, no API calls. If Qwen must go, the same machinery could train a Glimmer reranker over the Meta-only search instead. Uploading benchmark frames and questions to Fireworks is the user's call. | Use of Meta tooling: a fine-tuned Muse model in the loop | $0 (free SFT); serving locally |

## Judging days

- **Tunnel:** it runs only from the user's terminal; with the token saved in `product/.tunnel_token` (never printed),
  `scripts/autostart.sh` restarts the stable https://portia.shayekh.tech on the box.
- **GPUs:** keep the queue running (never-idle rule) or stop it so live runs get both GPUs: the user's call.
- **Hide the failed run** `1103-034255-09d7` from History (an `archived` marker, reversible).

## Dropped

- **Audit 020 router:** no time, and Spark 1.3 on new data sends it to a tier that trains on it.
- **More agent prompt experiments** (three nulls in plan 019); **more Discord** (the token died).

## Decisions for the user

1. Runtime model: send the DM tonight? Prepare the Meta-only fallback on the GPUs tonight?
2. Repo: its name, the license, and the benchmark's license or terms.
3. Fireworks (10): the router as a stretch after the must-dos, the reranker only if Qwen must go, or skip?
4. Held-out (9), Glimmer arm only: go?
5. Judges' path (7): the gallery only, or also an open Glimmer-only mode?
6. Hide the failed run; delete the dead Discord token file?

## User decisions

Keep Qwen (disclosed in the README as the one non-Meta model); Fireworks router after the must-dos (uploading benchmark
frames and questions to Fireworks is OK); held-out check with Glimmer only; disable YouTube-link ingest; hide the
failed run. Not now: deleting the dead Discord token, an open Glimmer-only demo mode.

## Pre-registration: held-out check (before any adjudication)

- **Data:** the held-out investigator triple, untouched: the tuned v4 agent, seeds 0, 1, 2 (`mg_v4t`,
  `mg_v4t_r1`, `mg_v4t_r2`) on shard5_25pct and shard6_25pct, 316 contests. No Spark model is called.
- **Run:** the evidence-only Muse Glimmer adjudicator exactly as on the development triples (`judge/adjudicate.py
  --variant evidence --seed-salt 0 --model mg30 --local-thinking --max-tokens 16384`), outputs `mg_adjev_ho_s5` and
  `mg_adjev_ho_s6`, as GPU queue extras.
- **Report, whatever comes out:**
  1. Accuracy of the majority vote and of Portia fully local (the vote, the adjudicator on splits) on the 316
     contests, with 95% bootstrap intervals over contests, next to the development figures (74.0%, 75.2%).
  2. The same on the held-out contests whose question does not occur in shards 3-4 (question leakage).
  3. Trust tiers: every held-out verdict gets the tier the product assigns (the development path table, the
     words-on-screen and position cap); each tier's held-out share and accuracy against its development accuracy.
- No success threshold: this is a confirmation. The numbers go on the Proof page and in the form as held-out results.
- **Cutoff:** before the submission; if unfinished, report what finished and say so.

## Held-out result (`analysis/heldout_021.py`, `runs/heldout_021.json`)

| Contests | n | Majority vote | Portia fully local |
|---|---|---|---|
| All held-out | 316 | 75.3% [70.6, 80.1] | **81.0% [76.6, 85.1]** |
| Question not in shards 3-4 | 179 | 76.0% [69.3, 82.1] | 81.0% [75.4, 86.6] |
| Development (reference) | 1,100 runs | 74.0% | 75.2% |

| Path | Held-out share | Held-out right | Development right |
|---|---|---|---|
| Agreed, settled it themselves | 30.4% | 89.6% | 88.7% |
| Agreed, two or more ran out of turns | 42.4% | 77.6% | 73.8% |
| Split, Glimmer adjudicator | 27.2% | 76.7% | 63.7% |

Trust tiers as the product assigns them: safe to accept 27.8% of cases at 88.6% right (development 88.7%); spot-check
2.5% at 100% (8 cases); needs review 69.6% at 77.3%.

- **Confirmed:** the jury generalizes, and the "safe to accept" tier is calibrated on unseen contests.
- **Above development:** Portia's 81.0% exceeds its 75.2% because the Glimmer adjudicator ruled 76.7% of the 86
  held-out splits right against 63.7% on development; with 86 splits some of that is chance. Report both, as measured.
- Not measured on held-out, by choice: the Spark modes (the Spark 1.3 Contributor tier trains on what it is sent).
