#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?project remote root}"
MODE="${2:?control|candidate}"
case "$MODE" in
  control) MODEL="$ROOT/bf16-source" ;;
  candidate) MODEL="$ROOT/nvfp4-checkpoint" ;;
  *) exit 64 ;;
esac
OUT="$ROOT/result-$MODE"
mkdir -p "$OUT"
if [ "$MODE" = candidate ]; then test -f "$MODEL/CONVERSION_MANIFEST.json"; fi
docker run --rm --gpus all --network host -v "$ROOT:$ROOT:ro" docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79 \
  vllm serve "$MODEL" --quantization compressed-tensors --dtype bfloat16 \
  --enable-prefix-caching --max-num-seqs 32 --max-model-len 4608 \
  --max-num-batched-tokens 134848 --served-model-name google/gemma-4-31B-it \
  --disable-log-requests >"$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
python3 "$ROOT/wait_server.py" --pid "$SERVER" --url http://127.0.0.1:30000/v1/models --output "$OUT/server-readiness.json"
python3 "$ROOT/endpoint_driver.py" --host 127.0.0.1 --port 30000 --output "$OUT"
