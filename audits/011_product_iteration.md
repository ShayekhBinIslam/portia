# 011: Jury, iterating toward the judges' rubric

Status: **in progress**. Written by the Portia coding agent (Claude). The user: "keep iterating
the product side as well, we need to convince our proejct to industry judge to get the money, we must win".

## The target (from the participant guide, meta_hackathon/Details*.html)

- **Deadline:** the end of the building period.
- **What to submit:**
  - a public repository;
  - a **3-minute demo video** showing only what was built during the hackathon;
  - the live product.
- **Stage 1:** pass/fail on fitting the theme and using Meta models.
- **Stage 2 rubric, 0-10 each:**

  | Criterion | Weight | What it asks |
  |---|---|---|
  | Impact | 30% | Real-world potential; who benefits |
  | Use of Meta AI tooling | 25% | Creative use; beyond a basic integration |
  | Technical depth & execution | 20% | Sound engineering, craft |
  | Demo | 25% | Working, impressive, "genuinely cool to watch" |

- **Stage 3:** the top 5 per track are ranked from their videos, live.
- **Bonus prizes Jury fits:**
  - Best Build on Meta Open Weight Models ($10K): Muse Glimmer and Muse Spark Open on our own hardware or a partner's.
  - Best Agentic Use-Case ($5K).
- **Rules:**
  - The demo may show only new work, which must be clearly identified (`meta_hackathon/NEW_WORK.md`).
  - "Basic RAG applications" and "simple image analyzers" are named anti-projects. Jury must read as multi-agent
    verification, not retrieval.

## Work items, in order of rubric value

1. **Demo (25%)**
   - A cinematic replay of a recorded run: events paced so the investigators visibly think, look and zoom, then the
     vote, the adjudicator and the verdict. Speed control.
   - A verdict-first summary: the verdict, how it was reached, its track record, and the **evidence it cites** (the
     frames matching the video@time citations in the deciding rationale).
2. **Impact (30%)**
   - The landing page reframed around the problem: AI answers about hours of video cannot be trusted without someone
     watching the footage.
   - Who uses it:
     - teams evaluating video AI;
     - media and compliance teams auditing AI summaries of footage.
   - A **Proof** page: Jury's track record over the 220 library cases, by domain and by how the verdict was reached,
     with time and cost. Built from the recorded runs.
3. **Use of Meta tooling (25%)**
   - An "Under the hood" view: which Muse model does what, where it runs (our GPUs, vLLM + DFlash; Baseten), tokens
     and cost per verdict.
   - The cascade itself is the creative part: Glimmer investigates and Spark Open only breaks splits.
4. **Hackathon rules**
   - A visible "Built during the hackathon" section listing the new work.
5. **For the user, not code:** a 3-minute demo-video script and a pitch outline.

## Questions only the user can answer (asked, not assumed)

- **Public access for judges:** judges cannot reach our GPUs.
  - A static replay gallery of recorded cases needs a public host (for example GitHub Pages on the public repository).
- **Bring your own video:**
  - ingesting new footage needs transcripts and an index;
  - Muse Voice Transcribe on the Meta Model API would also add Meta tooling breadth;
  - but `META_DEV_KEY` stays locked unless the user unlocks it.
- **Track:** Indie Developer or Startups.
- **Name:** "Jury" is a working name.

## Revision log

- written; starting item 1.
- **items 1-4 shipped.**
  - **Cinematic replay** (`#/job/<id>?play=2`): paced events at 1, 2 or 4 times speed, "skip to verdict", an honest
    "replaying a recorded investigation" bar.
  - **Verdict first,** with the evidence its deciding rationale cites. A live run shows 6 cited frames, the zooms of
    the ship's "16" and the bridge's two pylons.
  - **Home reframed:**
    - the problem;
    - three "who it is for" cards;
    - the proof numbers (75% local, 80.5% with Spark Open);
    - "Watch a case", which plays a recorded featured run (`#/demo`).
  - **Proof page** (`#/proof`):
    - 1,100 pooled development runs: one agent 72.9%, vote 74.0%, Jury 75.2%, Jury + Spark Open 80.5%; on splits
      62.6% against 83.0%;
    - a dot plot by domain on an ordinal ramp that passes the dataviz validator in light and dark;
    - a table view.
  - **How it works:** "Built during the hackathon" listed apart from what existed before (the hackathon rule).
  - **Robustness: each job now runs in its own worker process** (`engine.py run <id>`). In-process jobs had stalled
    the web server: 5 runs took minutes and requests timed out. Now a featured case finishes in about 15 s and the API
    answers in 3-5 ms during a run. The 5 stalled runs were moved to `product/zarxiv_jobs/`.
- **renamed Portia** (the user picked it from a shortlist drawn from English and French literature). It is Shakespeare's advocate who wins the trial on one exact detail; the tagline is "Every verdict turns on a detail." "Convene the jury" stays as the action. The environment variables are now `PORTIA_SPARK_BUDGET_USD` and `PORTIA_MAX_JOBS`.-: **the user's decisions.**
  - **Access for judges:** a static site plus a live link.
  - **New videos:** YouTube captions by default, with Muse Voice Transcribe kept as an option (off while
    `META_DEV_KEY` stays locked).
  - **Track:** Indie Developer.
  - **Name:** Portia.
  - **Next:**
    1. YouTube ingestion: yt-dlp video and captions, 30-second segments, transcript embeddings on the box encoder, and
       a per-video collection the agents search unchanged. Up to 30 minutes per video, so the whole video fits in
       the agents' 64-segment overview.
    2. The static gallery export for GitHub Pages.
    3. The live link during judging.
- **your own video, built** (`product/ingest.py`; server `/api/collections`, `/api/collections/upload`;
  New case page "Your own video").
  - **Pipeline:**
    - a YouTube link (yt-dlp: video at most 720p, English captions only) or an uploaded file (with optional .vtt/.srt
      captions);
    - exact 30-second clips (ffmpeg);
    - per-clip transcripts from the caption cues;
    - text embeddings on the box encoder;
    - a collection in the corpus's own format, registered by `engine.install_collections()` so the unchanged tools
      search it.
  - **YouTube:** a 19-second video ingested in about 9 s. But YouTube refuses the download of some videos (HTTP 403;
    "Big Buck Bunny" failed even at 360p).
    - The ingester then says so and points to "Upload a file".
    - An attempt to work around YouTube's download protection with other player clients was **refused by the
      permission system (bot-check circumvention) and dropped**. Portia only uses standard yt-dlp.
  - **Upload:** a 2-minute test video (four corpus clips of the USS Lexington, with an .srt) was indexed in about
    20 s: 4 caption cues, 4 clips (a near-empty fifth tail clip is now set aside), and a thumbnail. A live
    one-investigator run on it is in progress.
  - **Test collections to set aside before recording:** "Me at the zoo", "Upload test: USS Lexington".
- **the static gallery and two fixes.**
  - **The gallery** (`product/build_static.py` -> `product/site/`) is the same app in static mode
    (`window.PORTIA_STATIC`). It contains:
    - the 220 cases with their answer keys, the proof and the corpus statistics;
    - every recorded default-setup run, with images at 960 px.
  - **First build:** 5 recordings in 22 MB.
  - **Served locally as plain files,** the home, Proof and case pages work. "Watch a case" replays recording 041 to
    the correct verdict with 2 cited frames; New case points to the live app. There are no page errors.
  - **In the gallery:** recorded cases are marked (▶), and the library opens on "Recorded".
  - **More recordings:** 19 library cases are being recorded, chosen without hand-picking: the first, middle and last
    case of each domain, plus featured 107.
  - **Fix 1, a queue deadlock:** waiting workers counted each other as running, so 20 queued jobs waited forever.
    Now only started pipelines count and the queue is first in, first out. The 20 stuck jobs were stopped and moved to
    `product/zarxiv_jobs/`, then re-queued.
  - **Upload, checked live:** a one-investigator run on the uploaded video: A (correct, "16") in 51 s, citing
    the upload's own id and time.
- **24 recorded runs in the gallery; demo footage.**
  - **The 19 new recordings** were chosen without hand-picking: 16 right, 3 wrong.
  - **The gallery:** 220 cases, 24 recordings, 941 images, 85 MB.
  - **Footage:** `product/record_demo.py` drives a headless browser through home -> "Watch a case" (replay at 2x) ->
    verdict -> answer key -> Proof -> "Built during the hackathon". The result is `product/demo_footage/portia_walkthrough.mp4`
    (1:25, 1920x1080) plus `chapters.txt`.
    - The page is zoomed 1.5x at 1920x1080, so text reads well in a video.
    - Earlier takes are in `product/zarxiv_site/demo_footage_v*`.
  - **Fixes found while recording:**
    - A CSS class collision (`.who`) broke the investigator headers; the home section is now `.whofor`.
    - Replays hide the per-turn "replayed" tags, and the verdict's Run field says "recorded, replayed".
- **report and negative results.**
  - **"Download report (PDF)"** on every run: the browser's print dialog with a print stylesheet. The result is a
    4-page audit record:
    - the question;
    - the verdict and track record, the run facts, the cited frames and the answer key;
    - both answers;
    - each agent's and the adjudicator's reasoning.
    - Checked by rendering run 027 to PDF.
  - **How it works:** "What we tried that did not help", the measured negative results of plans 004-010 (oracle
    evidence, report-reading adjudicator, more votes, repeated adjudication, adjudicator search, 30 turns, hi-res
    zoom). This is technical-depth evidence for the judges.
  - Gallery rebuilt.
- **the "Effort: Quick (4 turns)" option.**
  - Jury-level check, Glimmer evidence-only adjudicator over each speed setting's seeds 0-2, one sample:

    | Setting | Jury accuracy | Vote |
    |---|---|---|
    | 4 turns | 73.6% | 72.7% |
    | 6 turns | 74.5% | |
    | medium reasoning | 75.5% | |
    | standard (5 triples pooled) | 75.2% | 74.0% |

  - **What the option does:** each investigator gets 4 turns (about 40% less compute). The verdict shows its own
    measured track record: unanimous 77.8%; splits 59.7% by vote, 62.9% by the Glimmer adjudicator. Spark Open's
    number is labelled as measured with 8-turn investigators.
  - **Library cases** in quick mode replay from the recorded 4-turn runs: case 027 took 6 s, all 22 turns cached, a
    split ruled A (correct).
- **a third adjudicator option: "Spark 1.3 · Meta API"** (Muse Spark 1.3 Contributor, plan 013).
  - It uses the Meta Model API through `judge/meta_client.py`, with the product's share of the user's $2 cap
    (`PORTIA_META_BUDGET_USD`, default $0.3).
  - The UI says the Contributor tier may train on what is sent.
  - **First live check, case 027:** Glimmer split B, B, A, and Spark 1.3 ruled A (correct), citing the dessert
    topping at kwR0x_NIHys@20:31. $0.0066, 74 s.
  - Its track record reads "being measured" until plan 013's development result is in.
  - Portia now uses three routes to Meta models: Muse Glimmer open weights on our GPUs (vLLM + DFlash), Muse Spark
    Open on Baseten, and Muse Spark 1.3 on the Meta Model API.

- **"Convene the jury" on a new question seemed not to reply** (user report). No job reached the server.
  Replayed in a headless browser, both sources (collection and uploaded video) send the request and open the job page.
  The likely cause was a quiet message: errors showed as small grey text beside the button (for example, "Your own
  video" selected with no video card clicked).
  - **Errors** now show in a red banner, scrolled into view.
  - **The button** reads "Starting the jury…" while the request is in flight.
  - **Validation errors** (HTTP 422) read as text.
  - **The server** logs every write and every error response to `product/server.log` (`[req]` lines), so the next
    failure can be traced.
- **"Spark 1.3 checks all" (resolve `spark13all`), from plan 014.** Spark 1.3 adjudicates every case,
  agreed ones too.
  - **Engine:**
    - track records "agreed and confirmed" (86.9%, 559 dev cases) and "agreed but overturned" (67.0%, 88);
    - splits use Spark 1.3's 76.6%;
    - the run falls back to Glimmer, with a notice, when the Meta key or budget is out.
  - **UI:**
    - the option group is now "Adjudication";
    - the vote panel says Spark 1.3 double-checks an agreed verdict;
    - verdict texts for confirm and overturn;
    - a cost label for Spark calls replayed from cache.
  - **Proof page:** a callout computed from the runs (`check_all_stats()`): 82.0% on 880 runs; 59 fixed, 29 broken.
  - **How it works:** a table row and a "built during" line.
  - **Gallery:** it now includes check-all recordings, so 25 runs, including case 015: all three agents agree on A
    and Spark 1.3 overturns them to B, the right answer. That run replayed from cache in 24 s at $0.
