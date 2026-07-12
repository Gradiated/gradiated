#!/bin/sh
set -eu

mask="$1"
shift
set -- --kernel-spec configs/kernels/qwen3-full-layer-v0.json

if [ $((mask & 1)) -ne 0 ]; then
  set -- "$@" --model-variant configs/variants/qwen3-8b-w4.json
fi
if [ $((mask & 2)) -ne 0 ]; then
  set -- "$@" --model-variant configs/variants/qwen3-8b-kv8.json
fi
if [ $((mask & 4)) -ne 0 ]; then
  set -- "$@" --model-variant configs/variants/qwen3-8b-kv4-heads.json
fi
if [ $((mask & 8)) -ne 0 ]; then
  set -- "$@" --model-variant configs/variants/qwen3-8b-ffn10240.json
fi

cargo run -q -p foundry-cli -- codesign-study \
  configs/qwen3-8b-agentic-h100.json \
  --constraints configs/hardware-sizing-agentic-v0.json \
  --server-tco configs/custom-server-tco-v0.json \
  --oracle roofline \
  --maximum-replicas 128 \
  "$@" \
  --output "artifacts/qwen3-8b/kernel-factorial/case-${mask}.json"
