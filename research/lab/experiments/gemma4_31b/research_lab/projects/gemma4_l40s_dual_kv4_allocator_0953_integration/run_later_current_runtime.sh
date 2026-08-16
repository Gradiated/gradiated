#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 ABS_CHECKPOINT ABS_OUTPUT_ROOT" >&2
  exit 2
fi

checkpoint=$1
output_root=$2
integration_root=$(cd "$(dirname "$0")" && pwd)

[[ "$checkpoint" = /* && -d "$checkpoint" ]] || {
  echo "checkpoint must be an existing absolute project-local snapshot" >&2
  exit 2
}
[[ "$output_root" = /* && ! -e "$output_root" ]] || {
  echo "output root must be an absent absolute path" >&2
  exit 2
}
[[ "${NVIDIA_VISIBLE_DEVICES:-}" != "void" ]] || {
  echo "NVIDIA device is not visible" >&2
  exit 2
}

mkdir -p "$output_root"
export PYTHONPATH="$integration_root${PYTHONPATH:+:$PYTHONPATH}"

python3 -m sglang.launch_server \
  --model-path "$checkpoint" \
  --tokenizer-path "$checkpoint" \
  --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 \
  --quantization fp8 \
  --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 \
  --host 127.0.0.1 \
  --context-length 5000 \
  --max-running-requests 32 \
  --mem-fraction-static 0.953 \
  --enable-metrics \
  --skip-server-warmup \
  --enable-dynamic-chunking \
  --chunked-prefill-size 2048 \
  --enable-fused-qk-norm-rope \
  --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton \
  --decode-attention-backend triton \
  --page-size 1 \
  --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 \
  --tool-call-parser gemma4 \
  --port 30000 \
  >"$output_root/server.stdout.log" \
  2>"$output_root/server.stderr.log" &
server_pid=$!

cleanup() {
  if kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid"
    wait "$server_pid" || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 360); do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    wait "$server_pid"
  fi
  if curl --fail --silent --max-time 2 http://127.0.0.1:30000/v1/models \
    >"$output_root/readiness.json"; then
    break
  fi
  sleep 1
done

curl --fail --silent --max-time 2 http://127.0.0.1:30000/v1/models \
  >"$output_root/models.json"
printf '%s\n' "science_started" >"$output_root/science_started"
python3 "$integration_root/packet/exact_c32_consumer.py" \
  --endpoint http://127.0.0.1:30000 \
  --output "$output_root/c32" \
  --workload "$integration_root/packet/WORKLOAD.json" \
  --arm dual-kv4-allocator-0953
