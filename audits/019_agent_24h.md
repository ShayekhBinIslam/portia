# 019: Improve the agent (24 h, GPUs 0 and 3)

Status: **E1-E3 done, none adopted; two trust improvements adopted.** GPUs back on the queue. Written by the Portia coding agent (Claude). The user: "keep improving the
agent next 24 hours; keep gpu 0 and 3 busy". Rules: Muse models only, GPUs 0 and 3 only, development shards 3-4 only
(no held-out), no paid API runs (Spark 1.3 has $0.33 left of its $4 cap).

## Where the headroom is (measured before this plan, `analysis/local_rules.py`)

- On 7 investigator triples (seeds 0-2 ... 32-34), Portia's local Glimmer adjudicator gains **+1.8 points over the
  vote** (6 triples up, 1 down); two adjudication samples that must agree, else the vote, gain +2.1 (5 up, 1 down).
- Muse Spark 1.3 checking every verdict gains +7.9 (plan 014). On case 038 it won by looking wider than the
  investigators: a contact sheet over two minutes, then a zoom on the moment none of them had opened.
- Dead ends, not repeated: Glimmer re-checking unanimous verdicts (t012: fixed 8, broke 9; all-forced subset fixed 5,
  broke 6); weighting a vote by "answered on its own" or "looked at frames" (a 1.5 weight can never flip a 2-1 split);
  earlier plans: more turns, xhigh, vote of 5, look-first, inspect, native aspect.

## Experiments, pre-registered

**E1: the adjudicator looks wider.** The Glimmer evidence-only adjudicator gets one added instruction: the
investigators' images can miss the evidence by seconds (a page turn, a cut, the moment before), so for each
difference it first takes a `contact_sheet` from about a minute before to a minute after the moment the images show,
then zooms where the detail appears. Everything else equal: same splits, same seed salt (0), same 4 turns.
Run on every triple with a standard adjudication (14 triples, about 9 minutes each).
- Metric: accuracy on all 220 contests per triple, against the standard adjudication of the same triple (paired).
- Explore half = the 7 triples above (1st, 3rd, ... in seed order); confirm half = the others.
- **Adopt** for Portia's local mode only if the explore half gains on average more than +0.5 points over the
  standard adjudicator with at least 5 of 7 triples up, **and** the confirm half gains on average more than 0 with
  more triples up than down. Otherwise keep the standard adjudicator and report the result.

**E2: the investigators look around before answering.** When two turns are left, the turn note asks each investigator
to check a minute either side of its key moment with a contact sheet before it answers. Paired by seed with the
queue's baseline runs of the same seeds (41-46, two triples): the same seed salt, the only change is the note.
- Metric: per-agent accuracy and the triple's vote, against the baseline of the same seeds.
- **Adopt** only if per-agent accuracy rises on both triples and the pooled gain over the 6 seed pairs is above +1
  point; then the jury (with the adjudicator chosen in E1) is scored on the two triples.

**E3 (if E1 is adopted): two samples of the wider adjudicator** that must agree, else the vote, on the triples that
have a second sample, scored like E1.

## Running

Experiments are priority items in the GPU queue (`scripts/gpu_queue.py`, runs/queue/extra.jsonl), so the GPUs never
idle and the queue's seed runs continue after them; every result goes into runs/plan019_*.md and this file.

## Results

- **E1: do not adopt** (pre-registered rule: explore fails, confirm passes). Over all 14 triples the
  wider-looking adjudicator is -0.13 points against the standard one (7 triples up, 7 down; on splits it fixed 104 and
  broke 108; explore -0.45 with 3 up, 4 down; confirm +0.19 with 4 up, 3 down). Why: the standard adjudicator already
  takes a contact sheet in 52-57% of splits (median span 2-3 minutes); the note raised that to 72-77% and changed
  nothing measurable. Glimmer's limit is reading fine detail, not finding the moment. Full table: runs/plan019_e1.md.
- Side results (no GPU): two adjudication samples that must agree, against one, on the same 12 triples: +0.34 (5 up,
  4 down: noise); weighting a lone self-answered agent at 2.5: +0.06 (5 up, 6 down); the observe-first adjudicator of
  plan 012 against the standard on 4 paired triples: -2.3, +0.5, +1.8, +0.5. No failures to fix: 4,620 agent-contests
  of seeds 20-49 have no errors and no missing verdicts.
- Cost lever for Spark 1.3 (plan 014 data, 880 runs): checking splits plus unanimous verdicts where at least two agents
  ran out of turns scores 81.7% at 0.72 calls per case ($0.0027), against 82.0% at 1.00 for checking every verdict
  (selected on the same data, so mildly optimistic).
- **Trust tiers on 14 triples (adopted):** the local (Glimmer) mode's paths are now measured on
  3,080 contest-triples (5 triples of plans 005-006 plus the queue's 9 later ones) instead of 1,100, and they held:
  agreed and settled 89.1 -> 88.8% (26.9% of cases), agreed at the turn limit 73.9 -> 73.4%, split ruled by the Glimmer
  adjudicator 62.7 -> 64.0%. Every path keeps its tier. The Spark modes are unchanged. Live app and gallery updated;
  the 5-triple file is kept as runs/trust_tiers_5triples.json.
- **What the answers dispute (adopted as a trust rule):** classifying each case by the kind of
  detail its answers disagree on (engine.dispute_kind: quoted or on-screen text, counts, colours, positions, objects;
  a first regex was too loose, counting possessive apostrophes as quotes, and was fixed before anything was used):
  - local jury, 14 triples: objects 82.5%, colours 75.7%, counts 72.2%, text 67.9%, positions 61.5%;
  - when the investigators agree on their own ("safe to accept", 88.8% overall): objects 94.8% (43 contests), colours
    90.7% (43), counts 87.7% (24), **positions 66.7% (6), text 55.8% (9)**;
  - Muse Spark 1.3 checking every verdict (4 triples) gains most where Glimmer reads worst: text +17.5, positions
    +19.2, colours +7.1, objects +5.4, counts -0.5.
  Portia now never marks a text or position dispute "safe to accept" (spot-check instead, with the reason), in the UI
  (trustFor), the batch audits (engine.trust_for) and the Proof page. Few contests behind the two cells: a conservative
  rule, which only ever lowers a claim. Routing only text, position and colour disputes to Spark 1.3 would keep most
  of its gain at about half the calls: a post-hoc design, not run.
- **E2 futility rule, added after the first of 12 seed pairs** (seed 41, shard 3: look-around 74.5%
  against 79.8% for the same seed without the note; fixed 2, broke 7): after four seed pairs, if the pooled change is
  -1 point or worse, E2 stops (its +1 adoption bar is then out of reach) and the GPUs return to the queue.
- **Proof page:** a "What the answers disagree about" table (analysis/dispute_kinds.py ->
  runs/dispute_kinds.json -> engine.proof()["kinds"]) under the trust tiers, with the new rule stated above it.
- **E2 futility check: continue.** After the four pre-set seed pairs (seeds 41-42, both shards,
  440 agent-contests) the pooled change is -0.45 points (seed 41: 72.7 against 75.0; seed 42: 75.0 against 73.6),
  above the -1.0 futility line, so E2 runs to its end. Consistently fewer agents answer on their own with the note
  (84 -> 68, 71 -> 61, 37 -> 31 per seed): the extra contact sheet seems to take the turn they would answer in.

**E3, pre-registered (before any E3 run): a procedure for the kind of dispute.** The Glimmer
evidence-only adjudicator gets one added paragraph only on splits whose answers dispute a count or words on screen
(the same classifier as engine.dispute_kind, applied to the adjudicator's list of differences): for counts, a `burst`
at the decisive moment and a count in each frame before ruling; for words on screen, a `zoom` on the text and the text
copied letter by letter before comparing. Every other split keeps the standard prompt (so it replays from the cache).
Same 14 triples, seed salt 0, paired against the standard adjudication.
- Metric: accuracy on the count and text splits of each triple (the only contests where the prompt changes).
- **Adopt** only if the mean gain over the standard on those splits is above +3 points with at least 9 of 14 triples
  up; otherwise keep the standard adjudicator.
- **E2: do not adopt; the note hurts.** Over all six seed pairs (seeds 41-46, both shards, 1,320
  agent-contests) the look-around investigators score 71.0% against 73.5% for the same seeds without the note
  (-2.50 points; seeds 41 -2.3, 42 +1.4, 43 -2.8, 44 -5.9, 45 +0.5, 46 -5.9); the triples' votes fall -2.7 and -0.9.
  Every seed has fewer agents answering on their own with the note (69-84 -> 58-68): the extra contact sheet takes
  the turn they would answer in, and the forced answers that replace those are worse. Full table: runs/plan019_e2.md.
- **E3: do not adopt.** On the count and text splits of all 14 triples the procedure scores +0.13
  points against the standard adjudicator (5 triples up, 6 down; fixed 33, broke 33); every other split kept the
  standard verdict in every triple (the control). Full table: runs/plan019_e3.md.

## Conclusion

Three pre-registered prompt changes, each tested paired on 14 triples or 6 seed pairs, all null or worse: looking
wider (adjudicator, -0.13), looking around before answering (investigators, -2.50), a procedure for counts and text
(adjudicator, +0.13). Decision rules over existing runs add noise only. Glimmer's ceiling here is reading fine visual
detail; prompting does not move it. What did improve Portia tonight is its self-knowledge: trust tiers re-measured on
3,080 runs (and they held), the dispute-kind rule (never "safe to accept" on words on screen or positions), and the
Proof page's table of where it is strong and weak. The remaining accuracy lever is Muse Spark 1.3, whose gain is
concentrated where Glimmer reads worst; a routed design (text, position and colour disputes, or splits plus forced
agreements) needs a fresh-triple confirmation with Spark 1.3 calls (about $1), which waits for the user's budget.
- **Refresh:** trust tiers on 17 triples (3,740 runs: settled 88.7%, turn limit 73.8%, split
  63.7%) and the kind table on 18 (it picks up every finished triple; text agreed-on-own 58.3% over 11 contests,
  positions 69.4%); the capped-trust wording now reads these figures live (app.js weakRange) instead of fixed numbers.
  14-triple file kept as runs/trust_tiers_14triples.json.
