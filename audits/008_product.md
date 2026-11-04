# 008: Jury, a working product built on our best pipeline

Status: **building** (the user asked: "as per hackathon, we need a working product,
please make beatiful product our of our best pipeline (keep it fully GPU glimmer-based by default)"). Written by the Portia coding agent (Claude). "Jury" is a working name.

## What it is

A web app that answers: **which of two answers does the video actually support?** A user brings a question and two
candidate answers about a long video collection, for example two models' answers, or a model answer and an edited one.
The app shows the whole investigation live:

1. **Three investigators.** Three Muse Glimmer agents (the tuned v4 agent, seeds 0-2) search hours of footage
   independently, on our own GPUs. They run on both local servers, GPU 3 (port 18660) and GPU 0 (port 18661), and the
   app streams every turn: reasoning, tool calls and the frames each agent looks at.
2. **Agreement.** If all three agree, that is the verdict. On development shards, unanimous verdicts are right 79.6% of
   the time.
3. **Disagreement** (about one contest in four). An evidence-only adjudicator checks the disputed details on the
   investigators' looks, without seeing their verdicts. The adjudicator model is a choice:
   - **Muse Glimmer (default):** local, free, on the same GPUs. On development data it is about as accurate as the
     majority vote (+1.3 points).
   - **Muse Spark Open (optional):** on Baseten, about $0.07 per adjudication. On development data it is +6.5 points
     over the vote (plan 006).
   - **Majority vote:** instant.

   The default is fully GPU-based with Muse Glimmer, as the user asked.
4. **The verdict card.** It gives the verdict and how it was reached; a confidence from the development numbers; the
   evidence frames; the time; and the cost (local GPU or Baseten dollars).

## Scope and data discipline

- **Case library: the 220 development contests (shards 3-4) only.**
  - Held-out shards 1, 2, 5 and 6 are not offered, so no held-out result is produced outside a pre-registered test.
  - After a verdict, library cases can reveal the ground truth: which answer is the original, and what was changed in
    the other.
- **Library cases replay through the response caches,** so a demo is fast and free:
  - the same agent settings give byte-identical requests;
  - the Spark adjudications of plan 006 also replay.
- **New cases:** the user picks a domain, writes a question and two answers, and the agents search that domain's
  videos live.
  - New videos cannot be added yet: the segment index and transcripts are built offline.
- **Spark Open runs only when the user picks it.**
  - Its spend goes through `judge/baseten_client.py`: logged, capped, and under the plan-006 total cap.
  - It is off whenever the Baseten key is locked.

## Build

- `product/engine.py`: the pipeline (`judge.agent.judge`, `judge.adjudicate.adjudicate`) with tracing. The research
  code is unchanged:
  - a client wrapper and a Toolbox subclass record each turn and save each image;
  - jobs run in threads and append events to `product/jobs/<id>/events.jsonl`.
- `product/server.py`: FastAPI on port 5250. Static UI, case library, corpus stats, jobs, a server-sent event stream,
  media, health.
- `product/static/`: a single-page UI (HTML, CSS, JS; no build step), light and dark.
- `make product` (tmux `p2prod`), and `product/README.md`.
- Entries in `meta_hackathon/NEW_WORK.md`: the product is new work.

## Checks before calling it done

- A library case end-to-end from the caches. Its verdicts must equal the logged runs (seeds 0-2 and the adjudications).
- A new case live on the GPUs.
- Screenshots of every page at desktop and phone width.
- No held-out contest is reachable.
- No key is printed or sent to the browser.

## Revision log

- written.
- **built** (`product/engine.py`, `product/server.py`, `product/static/`, `make product`; port
  5250).
- **checks.**
  - **Library case shard3_15pct_027** (featured; three agents, Glimmer adjudicator), end-to-end through the API in
    11.7 s:
    - all 35 model turns replayed from the cache;
    - the investigators said B, B, A, as the logged seed 0-2 runs;
    - the Glimmer adjudicator ruled A, as the logged plan-004 run;
    - A is the dataset's better answer.
  - **Spark Open path on the same case,** with the Baseten client in cache-only mode: 5 of 5 requests cached, nothing
    sent, $0. It ruled A, the same as plan 006.
  - **Screenshots of every page,** desktop (1440 px) and phone (390 px): no page errors, no horizontal overflow. Fixes
    made: grid columns at narrow widths; the diagram labels; the table headers.
  - **A new case runs live** on the GPUs (job 1030-064048-0741). Its turns take about 38 s each, because both GPUs are
    also serving the batch runs.
- **the live new case finished: unanimous A in 5 minutes 4 seconds, correct.**
  - The case: case 018's question; A = the original answer; B = the same with the ship's number changed from sixteen
    to eighteen.
  - All 21 model turns ran live, none from the cache, at a mean 19 s per turn while the batch runs shared both GPUs.
  - Each investigator found the "16" on the USS Lexington's island at g8GpWhs-QZo 31:11.
  - Tokens: 603,000 in and 8,000 out, all local; $0.
- **the default holds up offline: on a split, the Glimmer adjudicator beats adding more Glimmer
  agents.**
  - Data: the logged runs, 282 split contests over the 5 investigator triples of development shards 3-4.
  - Right on splits:
    - majority of 3: 57.8%;
    - adding 2 more agent seeds, majority of 5: 59.9%;
    - adding 4 more, majority of 7: 60.3%;
    - the Glimmer evidence-only adjudicator: 64.2% (its first sample per triple);
    - Spark Open: 83.0%.
  - So among Glimmer-only options the adjudicator is the best way to break a split. Escalating to more agents would
    cost 17-35% more GPU time for less.
- **renamed Portia** (the user picked it from a shortlist drawn from English and French literature). It is Shakespeare's advocate who wins the trial on one exact detail; the tagline is "Every verdict turns on a detail." "Convene the jury" stays as the action. The environment variables are now `PORTIA_SPARK_BUDGET_USD` and `PORTIA_MAX_JOBS`.
