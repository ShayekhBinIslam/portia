# 016: Make Portia the product that wins

Status: **running (the user's go: "make portia as worlds best product... make the product perfect")**. Written
by the Portia coding agent (Claude). An independent judge-style review (a separate agent, read-only)
runs in parallel; its findings are merged below when they land.

## What the judges score

- **Impact** (30%): who pays, and why now.
- **Use of Meta AI tooling** (25%).
- **Technical depth** (20%).
- **Demo** (25%).
- **Stage 3** ranks the top 5 per track from the 3-minute video alone.

The video may show only hackathon work. Portia is already strong on Meta tooling and technical depth: three
routes to Meta models, multi-agent investigation, and about 1,100 measured runs.

The gaps are Impact and Demo:
- Impact needs a buyer, a workflow and a trust story.
- Demo needs one unforgettable moment.

## Plan, in order of expected score impact

1. **Know when to trust it: confidence tiers and human review** (Impact, Technical depth).
   - Every verdict path has a measured development track record:
     - agreed and confirmed by Spark 1.3: 86.9%;
     - agreed (local): 79.6%;
     - split ruled by Spark Open: 83.0%, by Spark 1.3: 76.6%;
     - agreed but overturned: 67.0%;
     - split ruled by Glimmer: 62.6%.
   - Portia turns these into a tier on every verdict: **auto-accept** or **send to a person**, with the cited frames
     attached so the person checks in seconds.
   - The Proof page gets an accuracy-versus-coverage view: what share of cases can be auto-accepted, at what accuracy.
     It is computed from the logged runs.
   - History gets a "needs review" filter.
2. **Batch audit and API: how a team plugs it in** (Impact).
   - An Audit page: paste or upload a CSV/JSONL of (collection, question, answer A, answer B). Portia queues the jobs,
     fills a live results table (verdict, tier, cost) and exports CSV/JSON.
   - An API section with curl examples (create a job, poll it, stream events).
3. **The unforgettable demo moment** (Demo, stage 3).
   - New footage built around library case 015: all three agents agree, Spark 1.3 re-checks their evidence, and
     Portia overturns them, correctly.
   - Then the Proof callout (82.0%), the trust tiers and the audit page.
   - A voice-over script timed to the footage.
4. **First impression** (Demo, Impact).
   - The home page says in ten seconds what Portia is, who it is for, and the three numbers that matter: 82% right,
     under half a cent per case, and every verdict cites its frames.
   - A primary call to action: "Watch Portia catch a mistake".
5. **Live runs during judging** (Demo).
   - The GPU queue stops (`runs/queue/STOP`) when the live link goes out, so live cases get both GPUs.
   - Quick mode is already 6 turns with lighter reasoning.
6. **Fixes from the independent review,** as they come.

## Rules

- **Defaults:** the default stays "fully GPU Glimmer-based" (user). Spark modes stay options, labelled with
  their cost.
- **Measured numbers only.** Every number shown is computed from logged development runs, with its basis stated.
- **The GPU queue** (`scripts/gpu_queue.py`) keeps running until the user wants the GPUs for live demos.

## Revision log

- written; independent review launched.
- **built so far.**
  1. **Trust tiers** (`analysis/trust_tiers.py` → `runs/trust_tiers.json`; `engine.trust_table()`, `trust_for()`):
     - every verdict gets "Safe to accept", "Spot-check" or "Send to a person", with its path's own track record;
     - History has a "Needs a person" filter;
     - the Proof page has "When to trust a verdict": local only, 28% of cases at 89.1%; Spark 1.3 checks all, 26% at
       93.4% (63.5% at 86.9% with spot-checks).
  2. **Batch audit and API:**
     - `/api/batches` (create, status, CSV export);
     - an Audit page: paste or upload CSV/JSONL, a 6-case library sample, a live table, CSV/JSON export, curl
       examples;
     - recorded samples: fully local (2 accept, 4 to a person) and Spark 1.3 checks all (2 accept, 4 spot-check).
  3. **Header fix:** the top bar no longer wraps at laptop widths.
  4. **Gallery:** it now includes recorded batches and the demo runs of new questions (`engine.SHOWCASE`).
  5. **Demo recorder rewritten:** the case 015 catch, the answer key, Proof (82% and trust), audit, a new question,
     and built-during.
- **the independent review landed** (a judge-style read-only review: 10 weaknesses, 3 additions).
  - **Verified and fixed:**
    - **Case 015 was right for a weak reason:** Spark 1.3 decided on quote punctuation; the real edit could not be
      verified. It is archived, and the demo now uses **case 071**. All three agents trusted a "Pearl spot fish"
      caption from another video; Spark 1.3 identified the fish as a silver pomfret (right).
    - **Tool-call tokens leaked** into rulings (`ame="rationale">`, `<|start|>…`): a `cleanText()` sanitizer.
    - **Spark 1.3 verdicts cited no frames:** fixed, with frames deduplicated and shown larger.
    - **Home page:** one buyer (video-AI eval teams), one catch card, 82%, about $4 per 1,000 cases.
    - **Cases:** "Case 071" labels and a "Disputed: silver pomfret vs pearl spot" line on every case, ranking factual
      edits first.
    - **Number consistency:** 839 videos everywhere; cost per case on every option; the "all the gain is on the
      splits" contradiction; the stepper on check-all runs; "1 video · 2 min".
    - **Trust wording:** the red tier is now "Needs review"; new questions are marked as calibrated on the library only.
    - **The disabled Muse Voice option** is removed.
    - **A "Meta stack" table** on How it works, with measured numbers (DFlash: 3.2 to 4.0 tokens per step).
    - **Test runs** are hidden from History and the gallery (`archived` marker files).
  - **New footage:** `demo_footage/portia_walkthrough.mp4` (1:58), a captioned copy, and `voiceover.srt`
    generated by `product/voiceover.py`. DEMO_SCRIPT and README are rewritten.
  - **Open, the user's call:**
    - a public repo and a live link (eligibility);
    - a held-out test, and Spark 1.3 alone at scale (credibility; paid);
    - the additions: check one answer, evidence clips, SAM outlines.
- **the live app is public through a Cloudflare quick tunnel** (the user: "yes, cloudflare tunnel makes
  sense").
  - **Tunnel:** `bin/cloudflared` runs in tmux `p2tun` and serves http://127.0.0.1:5250 at a
    trycloudflare.com URL (`logs/cloudflared.log`).
  - **Public mode** (`product/public.env`, read by `server.py`; kept out of the repo):
    - anything that starts work (runs, batches, uploads, YouTube links) needs the access code in `X-Portia-Code`;
      the UI asks once per device;
    - at most 12 unfinished runs at once (429 beyond), batches of at most 10, uploads of at most 400 MB.
  - **Checked through the tunnel:**
    - the page loads in about 1 s;
    - no code and a wrong code both get 401;
    - with the code, a run starts and its event stream (SSE) arrives live (104 events in 25 s).
  - **Open:**
    - **A stable URL:** a quick tunnel's address changes when cloudflared restarts. A named tunnel needs the user's
      Cloudflare login and a domain.
    - **Judging days:** stop the GPU queue (`runs/queue/STOP`) so live runs get both GPUs.
- **check one answer**, the review's addition B.
  - **How it works:**
    - `POST /api/jobs {"single": {domain, question, answer}}`;
    - the job's worker has Muse Glimmer (`engine.make_variant`, medium reasoning, JSON schema) write a variant with
      2 to 3 checkable details changed, validated to at least 75% word overlap and 1 to 6 changed places;
    - the user's answer is placed as A or B at random, the usual jury rules, and the final event carries
      `single.supported`.
  - **UI:** a New case toggle; the job page shows which side is yours and what changed; the verdict reads "The
    footage supports / contradicts your answer" with ✓/✗ per changed detail.
  - **First live test** (case 071's correct answer): the variant changed silver→gold, red→blue and narrow→wide; the
    answer was ruled supported in about 4 minutes.
  - **One investigator crashed** on a truncated overview sheet. The likely cause is a race: three agents build the
    same new sheets at once, and one read a file another was still writing.
- **hardened against half-written files** (that race, and power cuts):
  - overview sheets and the local, Meta and Baseten response caches are written atomically (temp file, then
    `os.replace`);
  - an unreadable cached file counts as a miss (rebuilt or re-requested);
  - the spend logs skip a half-written line.
- **second live test, case 071's wrong answer** ("pearl spot").
  - All three investigators finished, so the race fix works.
  - The variant changed pearl→catla, red→blue and deep→shallow, and the wrong answer "held up". The agents fell for
    the same caption, and "catla" is wrong too.
  - **Limitation:** a one-answer check tests the changed details against a changed copy; it does not prove every claim.
  - **The UI now says so:** "Your answer held up / did not hold up", with "Portia tests the details it changed, not
    every claim in the answer". The New case hint says the same.
  - Its trust tier (calibrated on library questions, so marked "≈") flags the run as needing review: all three
    agents answered at their turn limit.
- **evidence clips**, the review's addition C.
  - `engine.evidence_clip`: the moments the deciding text cites, ruling first and only videos the agents looked at;
    about 6 s each, captioned with time and title (non-Latin scripts dropped from the caption font), joined and
    cached; served at `/api/jobs/{id}/evidence.mp4`.
  - UI: "Watch the moments" opens a player with a Download button.
  - Gallery: clips for the featured and demo runs (10 clips; the site is 147 MB).
  - Case 071's clip ends on the "Pearl spot fish" caption from the other video.
  - **New footage (2:19)** with that scene, regenerated captions (327 words, 141 per minute), and the DEMO_SCRIPT
    timeline updated.
- **factual edits stand out** in the answer panels, the review's last case-readability note.
  - `diff_spans` flags each changed span as factual or not, using the same `_fact_score` as the "Disputed" line.
  - Factual edits keep the coloured highlight; rewording of filler words ("delves into" vs "explores") gets a light
    dotted underline.
  - Phone checks of the clip player, the one-answer card and the Audit page all fit at 390 px. The gallery was
    rebuilt.
- **stable public URL: https://portia.shayekh.tech** (the user's .tech domain on Cloudflare, a named
  tunnel).
  - The first 502 came from the Service URL; the dashboard needs `http://127.0.0.1:5250`.
  - **Checked through it:**
    - the page loads in 0.9 s;
    - no code gets 401;
    - with the code, a run streams 143 events in 25 s;
    - an evidence clip is served (4.8 MB).
  - The gallery's "Live app" button, the README and DEMO_SCRIPT point at it.
  - The connector still runs from the user's terminal. Saving the token as `product/.tunnel_token` lets tmux
    `p2tun` and `scripts/autostart.sh` run it instead.
