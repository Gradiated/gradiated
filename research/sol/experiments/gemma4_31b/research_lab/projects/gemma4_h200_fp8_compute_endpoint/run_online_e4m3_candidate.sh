#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-attention-endpoint
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=online-e4m3-c32-20260718t1755z

mkdir -p "$remote/$run_id"
sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true
sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host \
  -v "$remote:/work" "$image" python3 -m sglang.launch_server \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 \
  --quantization modelopt_fp8 --modelopt-quant fp8 --quantize-and-serve \
  --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it \
  --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 \
  --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048

ready=0
for attempt in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$remote/$run_id/models.json"; then
    ready=1
    break
  fi
  sleep 4
done
sudo docker logs gemma-attention-endpoint >"$remote/$run_id/server-before-run.log" 2>&1 || true
if [[ "$ready" != 1 ]]; then
  printf '%s\n' 'server did not become ready' >"$remote/$run_id/launch.failure"
  exit 75
fi

sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py \
  --output "/work/$run_id/exact_mix" --arm online_e4m3_modelopt_fp8_dynamic_chunked
sudo docker logs gemma-attention-endpoint >"$remote/$run_id/server-after-run.log" 2>&1 || true
sudo docker exec gemma-attention-endpoint python3 - <<'PY' >"$remote/$run_id/runtime-identity.json"
import json, sglang, torch
print(json.dumps({"sglang_version": getattr(sglang, "__version__", None), "torch_version": torch.__version__, "cuda": torch.version.cuda}, sort_keys=True))
PY
cd "$remote"
tar -czf "$run_id.tar.gz" "$run_id"
