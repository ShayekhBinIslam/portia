#!/usr/bin/env bash
# gpu_run.sh <gpu> "<job description>" <python> <script> [args...]
# Runs a GPU job on one GPU. On the author's box (physics/training's runid.py and titled.py present) every process,
# vLLM workers included, is titled shayekh-<id> and only GPUs 0 and 3 are allowed; anywhere else it simply runs the
# command on the given GPU (PORTIA_TITLE_TOOLS can point at the titling tools elsewhere).
set -euo pipefail
GPU=$1; JOB=$2; PY=$3; shift 3
T=${PORTIA_TITLE_TOOLS:-/data2/shayekh/scratch/physics/training}
export CUDA_VISIBLE_DEVICES=$GPU HF_HUB_DISABLE_XET=1
if [ -f "$T/scripts/titled.py" ]; then
  case "$GPU" in 0|3) ;; *) echo "GPU $GPU is not ours (0 and 3 only)"; exit 1 ;; esac
  RID=$($T/.venv/bin/python -c "import sys; sys.path.insert(0, '$T/scripts'); from runid import new_run_id; print(new_run_id('portia: $JOB (box GPU $GPU)', '$PWD'))")
  echo "[gpu_run] shayekh-$RID on GPU $GPU: $JOB"
  export QP_PROCTITLE=shayekh-$RID VLLM_PROCESS_NAME_PREFIX=shayekh-$RID
  export PYTHONPATH=$T/sitecustomize${PYTHONPATH:+:$PYTHONPATH}
  exec "$PY" $T/scripts/titled.py "$RID" "$@"
fi
echo "[gpu_run] GPU $GPU: $JOB"
exec "$PY" "$@"
