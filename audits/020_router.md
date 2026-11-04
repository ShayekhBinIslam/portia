# 020: Portia's router: every Meta model where it measured best (draft)

Status: **draft; waits for the user's OK on spending** (Baseten about $8, Meta Model API about $1, Modal and Fireworks
credits). Written by the Portia coding agent (Claude), after the user: "we have meta api, fireworks, baseten
(spark open only) and modal credits, how can we show them to use in best way, like could build a router with
fireworks?"

## The design: one case, four providers, each doing what it measured best at

| Step | Model | Provider | Why (development set) |
|---|---|---|---|
| Investigate (3 agents, the bulk of tokens) | Muse Glimmer 30B | our GPUs (vLLM + DFlash); **Modal** endpoint as overflow | $0 a case locally; Modal absorbs bursts when several judges start runs at once |
| Split verdicts | Muse Spark Open | **Baseten** | best measured split adjudicator: 83.0% on splits (Spark 1.3 76.7%, Glimmer 63.7%) |
| Risky agreements (two or more agents out of turns, or the answers dispute text, positions or colours) | Muse Spark 1.3 | **Meta Model API** | gains most exactly there (text +17.5, positions +19.2, colours +7.1) at $0.0037 a check |
| Safe agreements (settled, objects or counts) | none | none | accepted as they are: 94.5% (objects) and 86.7% (counts) right |
| Fireworks | Muse Glimmer | **Fireworks** | serverless overflow if it serves Glimmer; the free LoRA fine-tuning (text only) fits the text-only steps: the check-one-answer variant writer and the router's triage |

## Measured so far (post hoc, 4 triples, 880 runs where both Spark adjudications exist)

Local only 75.3% ($0); Spark Open on splits 80.3% ($0.018 a case); Spark 1.3 checking every verdict 82.0% ($0.0037);
Spark 1.3 on splits and risky agreements 82.0% ($0.0031); **the router 83.8% ($0.020)**. The "risky" definition was
chosen on the same runs, so 83.8% is optimistic until confirmed.

## Confirmation, to pre-register before any call

Fresh investigator triples never used for these choices: seeds 41-43 and 44-46 (both shards, 440 contest-triples).
Spark Open on their splits (about 116 calls, about $7.8 Baseten), Spark 1.3 on their risky agreements (about 220 calls,
about $0.8 Meta). Report the router's accuracy and cost against local only and against Spark 1.3 checking every
verdict, with the per-triple gains; adopt it as Portia's "best" mode only if it beats Spark 1.3 checking every
verdict on both triples.

## In the product and the video

Each verdict names its route ("split -> Muse Spark Open on Baseten", "agreed on words on screen -> Muse Spark 1.3 on the
Meta Model API"), and each investigator its backend ("Glimmer, our GPU 3" or "Glimmer, Modal"). The Proof page shows the
accuracy-cost frontier above. The video's "Built on Meta's models" card shows the four providers and their roles.
