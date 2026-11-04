# 018: The narrated demo video, built with the user's ai-skills

Status: **plan; environments installing; the narration waits for the user's OK on the voice (Qwen3-TTS)**. Written
by the Portia coding agent (Claude), after the user shared github.com/ShayekhBinIslam/ai-skills
(cloned to /data2/shayekh/ai-skills: narrated-explainer-video, tts-narration, voice-judge).

## Why

- Stage 3 picks the top 5 per track from the 3-minute video alone. Today's demo is a silent 2:19 screen walkthrough
  with captions; a narrated, captioned, chaptered video with a cold open is what judges remember (plan 017, idea E).
- The user's skills do the hard parts, tested on their own videos: one levelled clip per narration beat (Qwen3-TTS
  "Ryan"), an ASR check of every clip, word-level timing, manim scenes cued on spoken words, soft captions, one chapter
  per scene, -16 LUFS.

## What winning demos do (web research; the user: "search web like top hackathon winner")

- **The organiser's own rubric** (meta_hackathon/Details*.html): Demo asks "Is the demo video genuinely cool to
  watch?"; Meta tooling asks for capabilities "that surprised even us"; judges "must be able to clearly identify what
  was created during the Hackathon" or the project can be disqualified; Stage 3 judges watch the videos live; a $20K
  "Most Viral" prize goes to the most engagement on X.
- **Hook in the first 10-20 seconds, shown rather than told:** judges see 30 to 100 demos and decide in the first 30
  seconds; open with one surprising fact or number that makes the problem felt.
- **One sentence for what it is, then the product working:** the demo takes most of the time; only the core flow;
  no code editors, terminals or half-built features.
- **Clarity beats complexity:** "a strong project with a confusing demo loses to a simpler project that the judges
  understand". Plain words, one idea per sentence, every term defined (Johnathan Mo's `ste` skill says the same).
- **Proof, then stack and impact, then a clean close** with the name and a call to action; never over time; never
  speed up the voice; honesty about limits reads as confidence.
- **Claude Build Day winners:** first place (Tekton) made every part "traceable to its historical
  source" through evidence chains and graded its work with independent verifier agents; second place (Sim Francisco)
  proved itself with a measured number against reality (81.3% forecast vs 83.8% actual). Portia already has both:
  cited moments for every verdict, a second model checking the agents, and 82.0% measured.

Changes to the plan below: open on the surprise (all three agents agreed and were wrong) instead of the problem
statement; one plain sentence for what Portia is; a "built during the hackathon" label on screen for every new part
and a closing list; no jargon ("adjudicator", "contest-triples", "shards" become plain words); a 30-45 s cut of the
hook and the catch for X.

## The video (about 2:45, within the 3:00 limit)

| # | chapter | kind | what it shows |
|---|---|---|---|
| 1 | Cold open | footage | the search map of case 071 replaying: three agents' looks across 94.7 hours, then 3 squares ringed: "All three agreed. All three were wrong." |
| 2 | Portia | manim | title and the one-line promise: every verdict turns on a detail |
| 3 | The problem | manim | two answers that differ in one word (silver pomfret vs pearl spot); checking means finding seconds in hours |
| 4 | How it works | manim | three Muse Glimmer investigators on our GPUs, their tools, the vote, Muse Spark 1.3 checking every verdict, a verdict with a trust level and its moments |
| 5 | The catch | footage | case 071: the agents trust a caption from another video; Spark 1.3 overturns them; "needs review"; the answer key agrees |
| 6 | The moments | footage | the map's ringed squares, the close-up, the evidence clip (the fish, the misleading caption) |
| 7 | Proof | manim | 82.0% vs 74.1% for the vote on 880 development runs; a quarter of verdicts auto-accepted at 93.4%; $0.004 a case |
| 8 | For teams | footage | a batch audit and the API; a new question answered live (sped up, labelled) |
| 9 | Built on Meta | manim | Muse Glimmer (open weights, our GPUs, speculative decoding), Muse Spark 1.3 (Meta Model API), Muse Spark Open; the live link |

## How

- **Narration first, at the voice's own pace** (the skill's rule: never stretch a voice). The screen recording is then
  driven by the narration: product/record_demo.py gains a narrated mode that holds each scene for its beats' lengths
  (audio/timing.json) and clicks on the words that name the click (audio/words.json), marking where every beat starts.
- Footage scenes become MP4s with their beats mixed in at those marks, plus a cue log in the skill's format, so the
  skill's caption, chapter and loudness code handles footage and manim scenes alike (a small wrapper around
  build_video.py's caption_cues, srt and encode).
- Manim scenes use the skill's Slide base re-dressed in Portia's look: Instrument Serif headings, Inter text,
  JetBrains Mono numbers, the site's palette (brand violet, A blue, B orange, the investigators' colours).
- Every number on screen or in the narration is read from Portia's files (proof.json, trust tiers, the job's events).

## Compute and rules

- TTS and ASR on GPU 0 in the ~5.6 GB left beside the Muse server (fallback: CPU). GPUs 1 and 2 are not used.
- **The voice is the user's call.** Qwen3-TTS is not a Meta model; it voices the video only and is no part of Portia,
  whose pipelines stay Muse-only. The alternative is the user reading the same script.
- Gates (the skills' metrics.yaml): every clip's ASR letter error ≤ 0.04 or explained; no cue misses or late cues;
  -17 to -15 LUFS integrated, true peak ≤ -1.0 dBFS; length ≤ 3:00; contact sheets of every scene looked at before the
  final render; one finished sample to the user before anything is published.

## Deliverables

product/video/out/portia_demo.mp4 (+ .srt), previews and contact sheets in product/video/build/, the scripts in
product/video/. The old walkthrough stays as it is (product/demo_footage/).

## Revision: open with what came before; footage first

The hackathon Discord asks two things the 2:50.6 cut lacks. The organizers' FAQ: "Open your 3-minute video
with one line stating what was pre-existing and what you built this week". Office hours (Cerebral Valley account): the
video "should show the working product rather than slides... Most of it should be real footage of the
product running, with the live Meta model calls visible". The cut was 69 s of footage (40%) and 102 s of slides.
The user: "makes sense please go ahead".

- **New first chapter (s00, about 7 s):** one narrated line on a plain card: before the hackathon, the video database
  and its search index; everything else built during the hackathon.
- **Problem (s03), How (s04) and Proof (s07) become footage**, on the same narration (no new voice for them):
  - s03: case 038's page, the two answers with the differing words highlighted, the search space, then the
    unanimous-wrong figure as an overlay (132 of 647).
  - s04: a NEW question run live on the live app (port 5250; library cases replay from the response cache, so they
    are not live), recorded in real time and sped up to fit the narration, labelled as a sped-up live run. Every turn
    names its model (Muse Glimmer on our GPUs; Muse Spark 1.3 on the Meta Model API for the check).
  - s07: the How page's results table (majority vote 74.0%, Spark 1.3 checking every verdict 82.0% at $0.004), then
    the Proof page's trust tiers (a quarter of verdicts safe to accept at 93%).
- Cost: one live run with Spark 1.3 checking every verdict, about $0.004 of the Meta budget ($0.33 left).
- Gates as before; the new cut must stay at or under 3:00 (judges stop watching at 3:00).

Done: the live run (job 1103-034653-7b39: three Muse Glimmer investigators said 16, Muse Spark 1.3
confirmed, 138 s, no cached replies) is the How chapter at 21x / 5x / 3x, labelled. Recording it found a real bug: the
three investigators (threads of one process) raced on the first-look sheets' temp file, so a new question's run failed
(job 1103-034255-09d7); judge/overview.py now builds each sheet set once under a lock, with per-thread temp names.
