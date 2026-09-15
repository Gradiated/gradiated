#!/usr/bin/env bash
set -euo pipefail

: "${GLM_MODEL_PATH:?Mount the verified model snapshot and set GLM_MODEL_PATH}"
export HF_HOME="${HF_HOME:-/var/cache/huggingface}"

arguments=(
  "${VLLM_BIN:-vllm}" serve "${GLM_MODEL_PATH}"
  --host "${RUNTIME_HOST:-127.0.0.1}"
  --port "${RUNTIME_PORT:-8000}"
  --served-model-name zai-org/GLM-5.3-Flash
  --tensor-parallel-size 2
  --max-model-len 1048576
  --max-num-seqs 16
  --scheduling-policy priority
  --block-size 128
  --gpu-memory-utilization 0.90
  --kv-cache-dtype fp8
  --safetensors-load-strategy prefetch
  --safetensors-prefetch-num-threads 8
  --tool-call-parser glm47
  --reasoning-parser glm45
  --enable-auto-tool-choice
  --enable-prompt-tokens-details
)

if [[ -n "${VLLM_MOE_BACKEND:-}" ]]; then
  arguments+=(--moe-backend "${VLLM_MOE_BACKEND}")
fi

exec "${arguments[@]}"
