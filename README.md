# Portia

Portia judges AI answers about long videos against the footage. Given a question and two answers, three Muse Glimmer
agents search about a hundred hours of video turn by turn, reading transcripts and zooming into frames, Muse Spark 1.3
checks their evidence, and Portia returns the better-supported answer with the moments it rests on and how far to
trust it. Built for the Meta Global AI Developer Hackathon, Indie Developer track.

| link | what is there |
|---|---|
| [portia.shayekh.tech](https://portia.shayekh.tech) | the live app: every recorded investigation opens and replays; new runs need the access code given in the submission |
| [demo video](https://youtu.be/mPPWk1gVlJ8) | three minutes: the problem, a live run and the evidence |
| [`product/site/`](product/site/) | the same app as a static gallery of the recorded investigations, with no GPU and no keys |
| [`meta_hackathon/NEW_WORK.md`](meta_hackathon/NEW_WORK.md) | every part of this repository, in the order it was built |

Before the hackathon there was only our video database (the videos, questions and answer keys of an earlier
long-video benchmark) and its search index. Everything in this repository was written during the hackathon, in the
order [`meta_hackathon/NEW_WORK.md`](meta_hackathon/NEW_WORK.md) lists.
[`audits/`](audits/) keeps every plan, pre-registration and result in order, including the ideas that did not help.

## How a case runs

1. Three Muse Glimmer 30B agents, each with its own seed, investigate for up to 8 turns. They search all the videos
   or one, grep and read transcripts, look at contact sheets and frames, and zoom in. Each one ends with an answer
   and the moments it cites.
2. The three agree in about three cases in four, and are then right 79.6% of the time. When they split, the majority
   is right 57.8% of the time.
3. An adjudicator rules on the disputed details. It sees the agents' looks (frames and transcript lines) and does not
   see their votes. By default it is Muse Glimmer; Muse Spark 1.3 can instead re-check every verdict, agreed ones
   included.
4. The verdict comes with the moments it rests on, an evidence clip and a trust tier (safe to accept, spot-check or
   needs review) measured from how the verdict was reached.

## Meta's models in Portia

| model | where it runs | what it does |
|---|---|---|
| Muse Glimmer 30B (open weights) | a Modal Endpoint or a Fireworks deployment (both tested); self-hosted, vLLM with its DFlash drafter (3.2 to 4.0 tokens accepted per step) | the three investigators, the default adjudicator, the variant writer for "check one answer" and the one-line versions of the library questions |
| Muse Spark 1.3 | Meta Model API | re-checks every verdict on the investigators' evidence (82.0% in development, 81.6% on held-out data) |
| Muse Spark Open (open weights) | Baseten (`meta-models/muse-spark-open-1026`) | an adjudicator option for split verdicts |
| Muse Voice Transcribe | Meta Model API | the transcript of an uploaded video (the Tears of Steel example) |

One model is not Meta's. The search index was built before the hackathon with Qwen3-VL-Embedding-8B, and the same
model encodes the agents' search queries and the transcripts of uploaded videos. Every model that reads, reasons or
decides is a Meta model. A Meta-only index (Perception Encoder on keyframes plus BM25 on transcripts) found the
evidence in the top 8 for 57.7% of development cases, against 78.2% for the Qwen index
([audit 015](audits/015_meta_only_retriever.md)).

## Results

Development shards 3-4: 220 cases, five independent sets of three investigators, 1,100 runs.

| setup | right | API cost per case |
|---|---|---|
| one Muse Glimmer agent | 72.9% | $0 |
| three agents, majority vote | 74.0% | $0 |
| Portia on Muse Glimmer alone (the Glimmer adjudicator on splits) | 75.2% | $0 |
| Portia with Muse Spark Open on splits | 80.5% | $0.017 |
| Portia with Muse Spark 1.3 checking every verdict (880 runs) | 82.0% | $0.004 |

Held-out shards 5-6: 316 contests that no choice used, pre-registered in [audit 021](audits/021_final_push.md) and
computed by [`analysis/heldout_021.py`](analysis/heldout_021.py), with 95% bootstrap intervals over contests.

| setup | all 316 | the 179 whose question never appears in development |
|---|---|---|
| three agents, majority vote | 75.3% [70.6, 80.1] | 76.0% [69.3, 82.1] |
| Portia on Muse Glimmer alone | 81.0% [76.6, 85.1] | 81.0% [75.4, 86.6] |
| Portia with Muse Spark 1.3 on splits | 81.3% [76.9, 85.8] | 82.1% [76.5, 87.7] |
| Portia with Muse Spark 1.3 checking every verdict | 81.6% [77.2, 85.8] | 79.3% [73.2, 84.9] |

On held-out data "safe to accept" covers 27.8% of cases at 88.6% right (88.7% in development). Portia's held-out score
is above its development 75.2% because the Glimmer adjudicator ruled 76.7% of the 86 held-out splits right, against
63.7% in development; with 86 splits, part of that gap is chance. The two Spark 1.3 rows come from one run of the
development settings on the same contests, pre-registered in [audit 022](audits/022_spark13_heldout.md) and computed
by [`analysis/heldout_022.py`](analysis/heldout_022.py). On held-out data, Spark 1.3 checking every verdict was about
as accurate as Muse Glimmer alone: of the 230 verdicts all three agents agreed on, 40 were wrong, and Spark 1.3 fixed
16 of them and broke 15 right ones (in development it fixed 59 and broke 29 over 880 runs).

Every number comes from a script in [`analysis/`](analysis/). The app's Proof page shows them with their sources,
including when to trust a verdict ("safe to accept" covers 26% of cases at 93.4% right with Spark 1.3).

## Run it

### The gallery, with no GPU and no keys

```bash
python scripts/static_server.py 5260 product/site        # then open http://127.0.0.1:5260
```

The gallery is the app in static mode: the 220 development cases and every recorded investigation, replayed turn by
turn with the reasoning, tool calls, vote, adjudication, verdict and trust tier. It has no frames of the benchmark's
videos, since that footage is not ours to redistribute; the live app shows them. The one exception is an uploaded
film, Blender's Tears of Steel (CC BY 3.0), whose run keeps its frames and clip.

### Muse Glimmer on Modal or Fireworks

Portia reaches Muse Glimmer through the OpenAI chat API, so a hosted deployment needs three settings:
`PORTIA_GLIMMER_SERVERS`, `PORTIA_GLIMMER_MODEL` and `PORTIA_GLIMMER_KEY`. Both hosts below were tested
with the same two investigations, and both got them right (78 s and 100 s each).

A Modal Endpoint scales to zero when idle and bills compute while it runs:

```bash
modal endpoint create --name portia-glimmer --model meta-models/Muse-Glimmer-30B
modal workspace proxy-tokens create --name portia    # prints a token id (wk-...) and a secret (ws-...)
modal endpoint info portia-glimmer                   # the endpoint's URL
export PORTIA_GLIMMER_SERVERS='[["<endpoint URL>/v1", "Modal"]]'
export PORTIA_GLIMMER_MODEL=portia-glimmer
export PORTIA_GLIMMER_KEY=<token id>.<token secret>
modal endpoint stop portia-glimmer -y                # when done; a stopped endpoint cannot be restarted
```

On Fireworks, Glimmer runs on an on-demand deployment (one H200, $8.00 per GPU-hour while a replica runs; it scales to
zero after 5 idle minutes):

```bash
export FIREWORKS_API_KEY=... FIREWORKS_ACCOUNT=<account id>
python scripts/deploy_fireworks.py create            # prints the three settings for Portia
python scripts/deploy_fireworks.py delete <deployment id>
```

### Self-hosted

Needs a GPU with about 96 GB for Muse Glimmer 30B in bf16, Python 3.11, and the video database with its index.

1. `pip install -r requirements.txt`
2. Muse Glimmer: `python -m venv .venv-muse && .venv-muse/bin/pip install -r requirements-muse.txt`, download
   `meta-models/Muse-Glimmer-30B` and `meta-models/Muse-Glimmer-30B-assistant` from Hugging Face, then
   `GPU=0 PORT=18660 bash scripts/serve_muse.sh` (and `GPU=1 PORT=18661 ...` for a second server).
3. The search encoder: copy `src/models/qwen3_vl_embedding.py` from github.com/QwenLM/Qwen3-VL-Embedding (commit
   8ce3aab) into `pod/vendor/qwen3vl_repo/src/models/` and install `qwen_vl_utils` (`pod/` is not in the repository),
   then `python scripts/local_encoder.py` (port 18531).
4. The data: point `PORTIA_DATASET`, `PORTIA_SHARDS`, `PORTIA_VIDEOS` and `PORTIA_INDEX` at the benchmark, its shard
   files, its videos and the index,
   in the environment or in `paths.local.json` ([`judge/paths.py`](judge/paths.py)).
5. Keys, optional: `cp .env.example .env` and add the Meta Model API key (Muse Spark 1.3) and the Baseten key (Muse
   Spark Open). Portia on Muse Glimmer alone needs neither.
6. `python product/server.py`, then open http://127.0.0.1:5250.

Pages, the REST API and the limits: [`product/README.md`](product/README.md).

## Layout

```
configs/     the settings, one YAML file per topic: models and prices, budgets, the agent, the app, the Proof runs, the GPU queue
judge/       the investigator agent, its video tools, the evidence-only adjudicator and the model clients
product/     the server, the pipeline engine, the web app, the static gallery and the demo video's build scripts
             (product/video/ needs manim and a TTS engine of its own; see product/DEMO_SCRIPT.md)
prompts/     every prompt template
analysis/    the scripts behind every number on the Proof page
scripts/     serving Muse Glimmer (locally or on Fireworks), the search encoder and the GPU queue the experiments ran on
audits/      every plan, pre-registration and result, in order
```

## Data and rights

The benchmark's videos are public YouTube videos used for evaluation, and this repository holds no video, frame or
transcript file from them. The gallery's records include the 220 development cases (each question, its two answers
and the answer key) and, inside the recorded runs, the short transcript lines and video titles the agents cited.
Videos can be uploaded to the live app as files; adding YouTube links is off on the public site.

The uploaded example is *Tears of Steel*, (CC) Blender Foundation, mango.blender.org, under CC BY 3.0, downloaded from
download.blender.org. Its transcript was made by Muse Voice Transcribe (12 minutes, about $0.04), and the run keeps
its frames and evidence clip with this credit.

## License

The code is under the Apache License 2.0 ([LICENSE](LICENSE)). The Muse models, the benchmark data and the videos are
not covered by it and keep their own terms.
