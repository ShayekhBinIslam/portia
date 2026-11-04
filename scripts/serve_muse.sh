#!/usr/bin/env bash
# Local judge on Meta open weights: Muse Glimmer 30B (VLM, 29.6B dense + 1.8B perception encoder) behind vLLM 0.32's
# OpenAI API on a box RTX GPU, with its DFlash drafter (Muse-Glimmer-30B-assistant: 5 layers that draft 16-token blocks
# from the target's hidden states) for speculative decoding. Tool calls use Meta's ATEM format (muse_glimmer tool
# parser) and the reasoning channel is split into reasoning_content (muse_glimmer reasoning parser).
#   bash scripts/serve_muse.sh                    (GPU 3, port 18660, served as "mg30")
#   NO_SPEC=1 PORT=18661 bash scripts/serve_muse.sh   (same model without DFlash, for speed comparisons)
# the local Muse Glimmer server: Portia's default needs no API credits.
cd "$(dirname "$0")/.."
GPU=${GPU:-3}; PORT=${PORT:-18660}; NAME=${NAME:-mg30}
HUB=${HF_HUB:-${HF_HOME:-$HOME/.cache/huggingface}/hub}
# a4e59da (cached) has the same weights, config, chat template and tokenizer as main @ cec94fc
M=${MODEL:-$HUB/models--meta-models--Muse-Glimmer-30B/snapshots/a4e59da52a7bc87ae7251dd5545c0dd437c44b68}
D=${DRAFT:-$HUB/models--meta-models--Muse-Glimmer-30B-assistant/snapshots/c676cce91658f9568aaf264a416211e2782735b7}
if [ "${NO_SPEC:-0}" = 1 ]; then SPEC=(); else
  # 15 drafted tokens + 1 verified = the drafter's 16-token block (the vLLM recipe fixes it at 15)
  SPEC=(--speculative-config "{\"method\": \"dflash\", \"model\": \"$D\", \"num_speculative_tokens\": 15}"); fi
exec scripts/gpu_run.sh "$GPU" "Muse Glimmer 30B$([ ${#SPEC[@]} -gt 0 ] && echo ' + DFlash') vLLM as $NAME port $PORT" \
  "$PWD/.venv-muse/bin/python" -m vllm.entrypoints.openai.api_server --model "$M" --served-model-name "$NAME" \
  --host 127.0.0.1 --port "$PORT" --max-model-len 131072 --limit-mm-per-prompt '{"image": 130, "video": 0}' \
  --gpu-memory-utilization 0.92 --max-num-seqs 32 --max-num-batched-tokens 16384 --enable-prefix-caching \
  --generation-config auto --enable-auto-tool-choice --tool-call-parser muse_glimmer --reasoning-parser muse_glimmer \
  "${SPEC[@]}"
