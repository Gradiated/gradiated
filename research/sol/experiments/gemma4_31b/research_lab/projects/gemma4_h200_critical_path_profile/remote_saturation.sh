#!/usr/bin/env bash
set -Eeuo pipefail
root=/home/glmrunner/gemma-critical-path-saturation
shared=/home/glmrunner/gemma-kernel-frontier
input="$root/input"
output="$root/artifacts/$1"
concurrency="$2"
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
container=gemma-critical-path-saturation
mkdir -p "$output"
test "$(find "$shared/checkpoint" -maxdepth 1 -type f | wc -l)" -eq 8
sudo docker image inspect "$image" >"$output/image-inspect.json"
sudo docker rm -f "$container" >/dev/null 2>&1 || true
sudo docker run -d --name "$container" --gpus all --ipc=host --network host -v "$shared:/work" -v "$root:/run" "$image" python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests "$concurrency" --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --cuda-graph-max-bs "$concurrency"
for _ in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models >"$output/models.json" 2>"$output/models.stderr" && break; sleep 2; done
test -s "$output/models.json"
sudo docker exec "$container" python3 /run/input/endpoint_saturation_runner.py --output "/run/artifacts/$1/exact-c$concurrency" --arm "$1" --concurrency "$concurrency" >"$output/runner.stdout" 2>"$output/runner.stderr"
sudo docker logs "$container" >"$output/server.log" 2>&1 || true
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/$1.tar.gz" -C "$output" .
sha256sum "$root/$1.tar.gz" >"$root/$1.tar.gz.sha256"
