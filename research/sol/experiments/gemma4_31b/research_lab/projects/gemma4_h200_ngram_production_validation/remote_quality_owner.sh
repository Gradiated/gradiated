#!/usr/bin/env bash
set -euo pipefail
root=/home/glmrunner/gemma4-h200-ngram-sequential-validation
name=gemma-ngram-quality-discriminator
mkdir -p "$root/artifacts"
sudo docker rm -f "$name" >/dev/null 2>&1 || true
sudo docker run -d --name "$name" --gpus all --ipc=host --network host \
  -v "$root:/work" -v "$root/input:/work/input:ro" -v /home/glmrunner/gemma4-async-result-pipeline/checkpoint:/work/checkpoint:ro \
  -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e FP8_MODULE_AUDIT=/work/artifacts/quality.modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/artifacts/quality.consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/artifacts/quality.runtime.json \
  -e FP8_STACK_MODULE_AUDIT=/work/artifacts/quality.stack-modules.jsonl \
  -e FP8_STACK_CONSUMER_AUDIT=/work/artifacts/quality.stack-consumers.jsonl \
  docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 \
  python3 /work/input/endpoint_entrypoint.py \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 --tool-call-parser gemma4 --speculative-algorithm NGRAM >"$root/artifacts/quality-container-id"
for _ in $(seq 1 240); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$root/artifacts/quality-models.json"; then break; fi
  sleep 2
done
test -s "$root/artifacts/quality-models.json"
python3 "$root/discriminator.py"
sudo docker cp "$name":/sgl-workspace/sglang/python/sglang/srt/speculative/ngram_worker.py "$root/artifacts/ngram_worker.py"
sudo docker logs "$name" >"$root/artifacts/quality-server-final.log" 2>&1 || true
sudo docker rm -f "$name"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader >"$root/artifacts/quality-after-compute.csv" || true
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >"$root/artifacts/quality-after-gpu.csv"
