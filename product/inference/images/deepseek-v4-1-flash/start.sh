#!/usr/bin/env bash
set -euo pipefail
export HF_HOME="${HF_HOME:-/var/cache/huggingface}"
export VLLM_ENGINE_READY_TIMEOUT_S=3600
export OMP_NUM_THREADS=1
export PYTHONUNBUFFERED=1
export HF_XET_HIGH_PERFORMANCE=1
MODEL=deepseek-ai/DeepSeek-V4.1-Flash
REVISION=dba1be0a40aa45a94ad051997016db3960a90277
args=("${VLLM_BIN:-vllm}" serve "$MODEL" --revision "$REVISION" --tokenizer-revision "$REVISION"
  --served-model-name "$MODEL" --host "${RUNTIME_HOST:-127.0.0.1}" --port "${RUNTIME_PORT:-8000}"
  --tensor-parallel-size 4 --language-model-only
  --engram-config '{"cpu_offload":false}'
  --tokenizer-mode deepseek_v41 --tool-call-parser deepseek_v41
  --enable-auto-tool-choice --reasoning-parser deepseek_v41
  --max-model-len 1048576 --max-num-seqs 32 --max-num-batched-tokens 8192
  --gpu-memory-utilization 0.90 --scheduling-policy priority
  --enable-prompt-tokens-details --disable-uvicorn-access-log)
if [[ "${SPECULATIVE_DECODING:-1}" == 1 ]]; then
  args+=(--speculative-config '{"method":"dspark","num_speculative_tokens":5,"draft_sample_method":"probabilistic","rejection_sample_method":"block","enable_adaptive_verification":true}')
fi
exec "${args[@]}"
