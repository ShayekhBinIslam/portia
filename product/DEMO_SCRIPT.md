# Portia: the 3-minute demo video and the pitch

For whoever presents the hackathon demo (the narrated video as built; the hackathon Discord's rules on demo videos).

## Rules that shape the video

- Show only work from the hackathon. The long-video tools and their multi-turn use, Portia, the jury, the Spark 1.3 and Spark Open
  adjudicators, the trust tiers, batch audits and the Glimmer serving all qualify.
  - Only the video database of our playlist-eval paper (videos, questions, answer keys) and its segment index existed
    before.
  - The index uses Qwen3-VL-Embedding-8B, the only non-Meta model. Say so if asked, and that a Meta Perception Encoder
    index was tested and found less accurate (plan 015).
- Scoring: stage 2 scores Demo (25%), Impact (30%), Use of Meta tooling (25%) and Technical depth (20%).
- Stage 3 ranks the top 5 per track from the videos alone, so the video must work with no other context.
- From the hackathon Discord:
  - Open with one line on what existed before and what was built during the event (chapter 1 does).
  - Most of the video should be real footage of the product running, with the live Meta model calls visible (about
    three quarters is; every turn on screen names its model).
  - At most 3:00: judges stop watching there. An AI voice-over in English is fine; music must be licensed (there is
    none).
  - Judges assess the video, the code and the live product, so the live app stays up.

## The video (`product/video/out/Portia.mp4`)

The narrated demo, 2:55.9 at 1920x1080 and 50 fps, with captions (a soft track and `Portia.srt`),
one chapter per scene and -16 LUFS sound. 7 of its 10 chapters are screen footage of the product, about three
quarters of the running time; the How chapter is a new question run live on the live app and sped up, with the speed on
screen. The voice is Qwen3-TTS Ryan (presentation only; Portia's own pipelines are Muse-only). An X cut of the hook,
the moments and the Meta models card, with Portia's end card joining it, is `Portia_x.mp4` (43 s), with captions
burned in for muted autoplay.

Built from `product/video/` (audits 018 and its revision): `script.py` is the narration (every number traced in
its docstring), `scenes.py` the three animated chapters, `record_narrated.py` the footage from the gallery,
`record_live.py` the live run, `portia_build.py` the join. Rebuild:

    python portia_build.py render --quality final --only S00_Before,S02_Title,S09_Built      (video env)
    python record_narrated.py                      (gallery on port 5260)
    python record_live.py record && ... record_live.py cut   (live app, port 5250)
    python portia_build.py compile --quality final && python portia_build.py xcut

## The story in one breath

Case 038: two answers disagree on what a notebook in a TV drama holds, sketches of human ears or cubes. All three
Muse Glimmer agents look at a page of app wireframes and say ears. Muse Spark 1.3 checks their evidence, looks a little
earlier in the scene, finds cubes, boxes and a page labelled BOX, and overturns all three; Portia flags the verdict
for a person to check, and the answer key agrees.

## Script (376 words; times are the chapters of the built video)

| Time | Chapter | On screen | Voice-over |
|---|---|---|---|
| 0:00 | Before and during the hackathon (manim) | A card: before the hackathon, the video database and its search index; built during it, everything else | "Before the hackathon, we had a video database and its search index. Everything else, we built during the hackathon." |
| 0:09 | Three agents, one wrong answer (footage) | Case 038's search map replays the three agents' search; ballots: all three said ears, all three wrong | "Three AI agents searched over a hundred hours of video for one detail. All three agreed. All three were wrong." |
| 0:20 | Portia (manim) | Title card: the wordmark, the two cited frames, the three trust levels | "This is Portia, a judge for AI answers about video. Every verdict shows the moments it rests on, and how far to trust it." |
| 0:30 | The problem (footage) | Case 038's page: the two answers with their differing words highlighted (ears / cubes), the 109-hour search space, then "1 in 5 unanimous verdicts were wrong" | "Teams that build video AI compare answers like these every day. They differ in one detail: does the notebook hold sketches of human ears, or of cubes? Checking means scrubbing through hours of footage. And agreement proves nothing: in our tests, one unanimous verdict in five was wrong." |
| 0:51 | How Portia works (footage) | A new question run live on the live app: the click, three Muse Glimmer investigators turn by turn (each turn names its model), Muse Spark 1.3's check, the verdict; sped up 21x / 5x / 3x and labelled | "Portia sends three Muse Glimmer agents to investigate on their own, turn by turn, with video tools we built: they search the footage, read the transcripts and zoom into frames. Then Muse Spark 1.3, on the Meta Model API, checks their evidence and rules." |
| 1:11 | The catch (footage) | Case 038's verdict page: the agents' evidence, Spark 1.3's turns, the overturn to B, "Needs review", the answer key | "In this case, all three agents found the notebook, looked at a page of app sketches, and went with ears. Spark 1.3 checked their evidence, then looked a little earlier in the scene: cubes, boxes, and a page labelled BOX. It overturned all three, and flagged the verdict for a person to check. The answer key agrees." |
| 1:37 | The moments (footage) | The search map over 109 hours; the two cited moments; the evidence clip (the cubes, then the flowcharts) | "Here is everything they could search, over a hundred hours. Each square is thirty seconds, colored where each agent looked. The verdict rests on two moments in one video. Click, and you see them: the cubes, and the flowcharts on the next page." |
| 1:57 | Proof (footage) | The How page's development table, each row lit as the voice names it: majority vote 74.0%, Muse Glimmer adjudicator 75.2%, Muse Spark Open adjudicator (Baseten) 80.5%, Muse Spark 1.3 checking every verdict 82.0% at $0.004 a case | "On our development set, a majority vote of three agents is right 74% of the time. A Muse Glimmer adjudicator raises that to 75%, at no API cost. Muse Spark Open on Baseten gets 80.5%, and Spark 1.3 checking every verdict 82%, for under half a cent a case." |
| 2:19 | For evaluation teams (footage) | A finished batch audit with trust levels and costs; the live question's verdict | "Teams upload a whole run as a spreadsheet, or call the API, and get a verdict, a trust level and a cost for every case. It answers new questions live, too." |
| 2:32 | Built on Meta's models (manim) | Built on Meta's models: Muse Glimmer 30B (deployed on Modal and Fireworks), Muse Spark 1.3 (Meta Model API), Muse Spark Open (open weights on Baseten); new in the hackathon / from before; the end card with portia.shayekh.tech | "We built Portia and its video tools during the hackathon, on Meta's models: Muse Glimmer deployed on Modal and Fireworks, Muse Spark 1.3 on the Meta Model API, and Muse Spark Open on Baseten. Portia. Every verdict turns on a detail." |

## The live app

https://portia.shayekh.tech, through a Cloudflare named tunnel to this box. Browsing is open; starting work
needs the access code (`product/public.env`). Put the link and the code in the submission.

## Before recording anything live

1. Pause the batch queue: `touch runs/queue/STOP`. The queue workers finish their current run and stop. A live case then
   takes about 2-3 minutes instead of about 5. Remove the file to restart the queue (`scripts/gpu_queue.py`).
2. Quick mode (6 turns, lighter reasoning) is about 2 points less accurate (73.2% against 75.2%) and noticeably
   faster.
3. Browser: a 1440 px wide window at 100-110% zoom, light theme, recorded at 1080p or higher.

## Pitch outline (submission text, judges' questions)

- Problem: teams building video AI compare model answers about long footage, and the answers differ in small
  details: a count, a colour, a caption. Checking means a person finding the moment in hours of video.
- Solution: Portia, a judge built from Meta's models.
  - Three Muse Glimmer agents investigate the footage with real tools.
  - Muse Spark 1.3 re-checks every verdict on their evidence.
  - Every verdict comes back with the frames it cites and a measured trust tier.
  - Batch audits and a REST API plug it into an evaluation pipeline.
- Meta's models, three ways:
  - Muse Glimmer: open weights, deployed on a Modal Endpoint and on Fireworks (both tested), no per-token API cost.
  - Muse Spark 1.3: the Meta Model API, about $0.004 per case.
  - Muse Spark Open: open frontier weights hosted on Baseten.
- Evidence (development set):
  - 72.9% for one agent, 74.0% for the vote, 75.2% for Portia fully local, 78.8% with Spark 1.3 on splits, 80.5% with
    Spark Open on splits (1,100 runs).
  - 82.0% with Spark 1.3 checking every verdict (880 runs). All three agents agree on the wrong answer in 15% of
    cases; Spark 1.3 fixed 59 of these and broke 29, and came out ahead on each of the four investigator sets
    measured.
- Trust: auto-accept 26% of cases at 93.4% right; spot-check 64% (76-82% right); 10% needs review.
- Answer honestly if asked:
  - "Is this held out?" The local jury is: on the untouched shards 5-6 (316 contests, pre-registered, audit 021)
    Portia fully local was right 81.0% [76.6, 85.1] against 75.3% for the majority vote, and "safe to accept" was 88.6%
    right (88.7% in development). The held-out splits went better than development's, partly by chance (86 splits).
    Muse Spark 1.3 then ran once on the same contests (audit 022): 81.3% ruling on splits and 81.6% checking every
    verdict, about the same as Muse Glimmer alone there. The video's Proof chapter shows the development table.
  - "Does Portia beat Spark alone?" Not measured at scale. Spark 1.3 as the whole agent got 8 of 10 in a smoke
    test, at about $0.011 per case, three times Portia's check-all cost.
  - "Does the agent beat a no-tools Glimmer?" On the held-out scorecard (316 contests, 3 seeds each), one tool
    agent scored 75.3%. That tied a no-tools Glimmer given shared-text retrieval (76.3%) and beat question-only
    retrieval (70.6%). Portia's value is the jury, the evidence it cites, the escalation and the trust tiers, not the
    single agent.
- Impact: video-AI evaluation teams (a pairwise judge plus a batch API), media and compliance checks, anyone who
  must trust an AI's account of a recording.
- What's next:
  - checking one answer on its own (Portia writes the counterfactual);
  - outlining the cited object with SAM;
  - shareable evidence clips.

## Bonus prizes Portia fits

- Best Build on Meta Open Weight Models ($10K): Muse Glimmer on a Modal Endpoint and a Fireworks deployment, and Muse
  Spark Open.
- Best Agentic Use-Case ($5K): autonomous multi-agent investigation, adjudication, escalation and self-assessed
  trust.
