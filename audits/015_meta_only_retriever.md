# 015: A Meta-only retriever: Muse Glimmer (LLM2Vec-style) and Meta's own encoders, in place of Qwen embeddings

Status: **closed: the Qwen index stays (the user: "keep qwen then")**. Written by the Portia coding agent (Claude). The
user: "since it is meta hack, could we use muse glimmer as LLM2Vec2 version as some form of retriever, search web to
use it as embedding model in best way as meta doesn't have embedding model, give me the plan first".

## Why

- **Qwen is the last non-Meta model in Portia.** Every `search` / `search_video` call and the 64-segment overview pack
  rank 96,777 thirty-second segments by Qwen3-VL-Embedding-8B vectors.
  - The index (`play/3_inference/.cache/retrieval/...`) embeds each segment from 16 frames at about 960x720.
  - Queries are encoded on the box CPU by the same 8B model, which is slow and shared.
- **The hackathon rule is "hack is only muse"** (user).
  - A Meta-only stack ("Glimmer investigates, Meta encoders retrieve, Muse Spark adjudicates") answers Use of Meta AI
    tooling (25%) directly.
  - It also strengthens the Best Build on Meta Open Weight Models entry.
  - It is new work, so it can be shown in the demo.
- **Retrieval matters, but is not the main limit.**
  - The current index finds about half of the evidence clips in its top 64 (`analysis/retrieval_queries.py`).
  - E1 (plan 009) showed that Glimmer is limited by judgement more than by finding moments.
  - The goal is therefore **parity or better with Meta-only parts**, not a large accuracy gain.

## What the web says

- **LLM2Vec** (McGill, 2024) makes a decoder LLM into a text encoder in three trained steps:
  - bidirectional attention;
  - masked next-token prediction;
  - unsupervised contrastive training (SimCSE).
- **VLM2Vec-V2** (TIGER-Lab, TMLR) is the video version: a VLM fine-tuned with instruction-guided contrastive
  training on MMEB-V2, covering text, images, videos and documents. It is trained (Qwen2-VL 2B), not training-free.
- **Training-free embeddings from a frozen decoder:**
  - PromptEOL: "This sentence: '...' means in one word:", last token;
  - Echo: repeat the input and pool the second copy;
  - Token Prepending;
  - KV-Embedding (ACL): re-route the last token's KV as a prefix; up to +10% over the others on MTEB, with
    retrieval gaining most;
  - ReverseEOL.
  - For images, E5-V-style prompts ("summarize the above image in one word:") give usable multimodal vectors without
    training.
  - The MoE-specific trick (routing weights as embeddings) does not apply: Glimmer is dense, with 52 layers and width
    6656.
- **vLLM:** `--runner pooling --convert embed` turns a generative checkpoint into a last-token-pooled embedding
  server. Documented for single-tower text models; Glimmer's multimodal class may not be supported.
- **Meta does have embedding models:**
  - **Perception Encoder, PE-Core** (FAIR, Apache 2.0): CLIP-style image and video encoders, each with a text tower.
    - PE-Core-G14-448: 1.88B vision and 0.47B text; MSR-VTT text-to-video 51.2, COCO text-to-image 58.1.
    - PE-Core-L14-336: 0.32B vision and 0.31B text; MSR-VTT 50.3, so nearly as good at a sixth of the size.
  - **Glimmer's own vision tower is a Perception Encoder:** "~1.8B param ViT-G/14, 50 layers, width 1536". The card
    lists it among the Apache 2.0 artifacts.
  - **DRAMA** (FAIR, ACL 2025): dense text retrievers from pruned Llama 3, `facebook/drama-base` (0.1B) and
    `facebook/drama-1b`.

## Three arms, each measured offline before any agent run

| Arm | Visual channel (frames) | Spoken channel (transcripts) | Query encoder at search time | Muse? |
|---|---|---|---|---|
| **G: Glimmer as the embedder** (the user's LLM2Vec idea, training-free) | Glimmer on 4 frames, E5-V-style "one word" prompt, last-token vector | Glimmer on the transcript, PromptEOL / Echo prompt | Glimmer pooling server: one GPU and a second 56 GB copy of the weights | Yes, Glimmer weights only |
| **P: Perception Encoder** (Glimmer's vision family) | PE-Core frame vectors, mean or max over 8 frames | DRAMA on transcripts, fused with rank fusion | PE text tower + DRAMA on the box CPU, tens of ms | Meta FAIR, and Glimmer's vision tower if the weights match |
| **P+G: Perception Encoder, steered by Glimmer** | as P | as P | as P, plus Glimmer (the running chat server) rewrites each question into 2-4 short scene descriptions, because CLIP text towers read about 70 tokens | Meta + Muse |

Arm P+G is the strongest candidate for Portia:
- Glimmer does the language work: it reads the question and writes visual queries.
- The Perception Encoder does fast, cheap matching.
- No second Glimmer copy is needed at search time.

Arm G is the direct test of "Glimmer as an embedding model". If it wins clearly, it ships as an index-time encoder, or
with a dedicated GPU.

## Phases

0. **Harness** (CPU, about 1 hour, no GPU).
   - Reuse `analysis/retrieval_queries.py` on **development shards 3-4 only**: the 220 dev contests, their
     ground-truth evidence clips, and the search scope of the contest's whole domain.
   - **Metrics:** an evidence segment in the top 8; the share of evidence clips in the top 64 (the overview pack);
     mean reciprocal rank.
   - **Queries:** the question plus the shared answer text, exactly what the agents' overview uses.
   - **Baseline:** the current Qwen index, from the cached query vectors.
1. **Is Glimmer's vision tower PE-Core-G?** (CPU, minutes.)
   - Download `facebook/PE-Core-G14-448` and compare tensor hashes with Glimmer's vision weights.
   - If they match, the story becomes "Glimmer's own perception encoder, with its released text tower".
2. **Arm P index** (one GPU, about 1-1.5 hours, or less with L14).
   - PE-Core-L14-336 first, on all 96,777 segments: 8 frames each at 336 px, with per-frame vectors kept.
   - Then PE-Core-G14 if L14 is competitive.
   - DRAMA-1b on the transcripts (GPU minutes, or about an hour on CPU).
   - Score P alone, then P+G with Glimmer's query rewrites (about 220 short generations on the running chat server).
3. **Arm G** (one GPU, about 3 hours, the chat server on that GPU paused).
   - A subset first: each dev contest's evidence clips plus 2,000 random segments per domain, about 15k segments.
   - Compare it with P and with Qwen on the same candidates.
   - Text-only (transcript) variants first, which are cheap; the 4-frame multimodal variant if text shows promise.
   - Through vLLM's pooling runner if it accepts Glimmer, else HF transformers with hidden states.
   - The full corpus only if G is competitive on the subset.
4. **Agents** (one GPU, about 3.5 hours).
   - The best Meta-only retriever replaces Qwen in `search`, `search_video` and the overview pack.
   - Tuned 8-turn investigators, seeds 0-2 on shards 3 and 4, compared pairwise with the logged Qwen-index seeds 0-2.
   - **Adopt it if** accuracy is within -1 point of Qwen's; that is enough, since the gain is Meta-only.
5. **Portia.**
   - The live app and `product/ingest.py` (uploaded videos) use the new index and query encoder. CPU-only query
     encoding also frees the box CPU that the 8B Qwen encoder now holds.
   - The How it works page and the demo say "Meta end to end".

## Rules

- **Data:** development shards 3-4 only. No training, so there is no leakage from training. The question and answers
  used in queries are what the agents already see.
- **GPU time:** GPUs 0 and 3 run the speed-mode lanes into tonight.
  - Phases 2-4 need about 8 GPU hours in all, on one GPU at a time.
  - They start after the lanes or, with the user's OK, by pausing one lane.
- **No paid API:** query rewrites use the local Glimmer server.
- **Code:** the new retriever is an opt-in flag (`--retriever pe|glimmer|qwen`). The default stays Qwen until phase 4
  decides. The golden-request test must still show 0 differences with the flag off.

## Risks

- **Short text towers:** CLIP text towers (P) read short captions, and our questions are long two-hop texts. That is
  why P+G has Glimmer write short scene queries.
- **Weak training-free embeddings:** they usually trail trained embedders on retrieval. Arm G may lose clearly to
  Qwen3-VL-Embedding-8B, which was trained for exactly this. That is a valid result, reported as such.
- **vLLM may not support Glimmer:** its pooling conversion may reject the multimodal Glimmer class. The fallback is HF
  transformers, which is slower; subset only.
- **Meta, not Muse:** PE-Core and DRAMA are Meta FAIR models, not "Muse". Whether they satisfy "hack is only muse" is
  the user's call (decision 1). Phase 1 may show that P is literally Glimmer's own encoder.

## Decisions for the user

1. **Does "Meta models" count for the hackathon,** PE-Core and DRAMA from Meta FAIR, or must every model be a Muse
   model? If Muse only, arm G alone remains, plus Glimmer's own vision tower if phase 1 finds a matching text tower.
2. **GPU time:** start phases 2-4 after tonight's lanes, or pause one lane now?

## Sources

- LLM2Vec: https://arxiv.org/abs/2404.05961 and https://mcgill-nlp.github.io/llm2vec/
- VLM2Vec-V2: https://arxiv.org/abs/2507.04590 and https://github.com/TIGER-AI-Lab/VLM2Vec
- Token Prepending: https://arxiv.org/abs/2412.11556
- KV-Embedding: https://aclanthology.org/2026.acl-long.540/
- ReverseEOL: https://arxiv.org/abs/2606.05858
- MoE routing-weight embeddings: https://arxiv.org/abs/2410.10814
- vLLM pooling models: https://docs.vllm.ai/en/latest/models/pooling_models/embed/
- Perception Encoder: https://arxiv.org/abs/2504.13181 and https://github.com/facebookresearch/perception_models/blob/main/apps/pe/README.md
- DRAMA: https://arxiv.org/abs/2502.18460 and https://huggingface.co/facebook/drama-1b
- Muse Glimmer card: https://huggingface.co/meta-models/Muse-Glimmer-30B

## Revision log

- **the user approved arm P:** "awesome, let's try pe-core then, it should work", then "i think,
  pe core should be enough for vision and text both?".
  - **PE-Core is the only model:** its text tower encodes the queries, and its vision tower encodes keyframes.
  - **Transcripts** are tested two ways:
    - the PE text tower on 20-word windows, with the best window per segment (the user's idea);
    - BM25, which is not a model.
  - **DRAMA is dropped:** its license is CC-BY-NC-4.0, non-commercial.
  - **The text tower is short:** PE-Core-L14 reads 32 tokens and G14 reads 72, so long queries are also cut into
    windows.
  - **Harness:** `analysis/pe_retrieval.py` (prep, index, score). The environment is `.venv-pe` (torch 2.14 cu130,
    open_clip 3.3, PyAV, bm25s).
  - **Candidates:** 25,645 segments: the 1,679 evidence segments of the 220 dev contests, plus a random 25% of each
    domain's other segments. Qwen ranks the same set.
  - **Where it runs:** the PE-Core-L14 index runs on GPU 3's spare memory (cap 2.5 GB), beside the lane's vLLM server
    (tmux `p2pe`). A first try with 256-frame batches hit out-of-memory and was restarted with 64.

- **arm P result: PE-Core-L14 is far below Qwen3-VL-Embedding-8B on this task.**
  - **Setup:** 220 dev contests and the same 25,571 candidates (`runs/pe_retrieval/report.md`). The index took 26 min
    on GPU 0's spare memory.

  | Retriever | hit@8 | any@64 | clip recall@64 | MRR |
  |---|---|---|---|---|
  | Qwen (current index: 16 frames + transcript) | **78.2%** | **92.7%** | **69.0%** | **0.563** |
  | PE frames, query cut into 20-word windows | 45.5% | 72.3% | 41.6% | 0.264 |
  | PE frames, Glimmer's 4 scene queries | 44.5% | 70.9% | 37.6% | 0.256 |
  | PE frames, raw query (first 32 tokens) | 24.5% | 56.4% | 23.2% | 0.170 |
  | PE text tower on transcripts (the user's idea) | 27.7% | 56.8% | 25.8% | 0.181 |
  | BM25 on transcripts (no model) | 58.2% | 76.4% | 43.8% | 0.360 |
  | RRF(PE frames windows, BM25): best Meta-only | 57.7% | 85.0% | 52.8% | 0.366 |
  | RRF(Qwen, BM25) | 72.3% | 91.8% | 64.7% | 0.500 |

  - **Reading:**
    - CLIP-style frame matching cannot locate the moments of long two-hop questions as well as Qwen's joint
      frames+transcript vectors.
    - Transcripts carry much of the signal: BM25 alone beats every PE variant.
    - PE's text tower is weak on transcripts, as expected from its 32-token caption training.
- **DRAMA-1B on transcripts was blocked** by the permission system. Its loader runs code from the
  model repo (`trust_remote_code`). Not pursued; the user decides. (It is also CC-BY-NC-4.0.)
- **closed by the user:** "keep qwen then".
  - The Qwen3-VL-Embedding-8B index stays.
  - Portia's README, How it works page and demo script now say plainly that it is the one non-Meta model, built
    before the hackathon. They also state that the Meta-only index was measured and found less accurate (57.7% against
    78.2% in the top 8).
  - **Kept for later:** the PE-Core index and the evaluation harness (`runs/pe_retrieval/`,
    `analysis/pe_retrieval.py`, `.venv-pe`).

