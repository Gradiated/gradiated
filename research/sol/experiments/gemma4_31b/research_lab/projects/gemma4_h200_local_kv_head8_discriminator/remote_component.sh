#!/usr/bin/env bash
set -Eeuo pipefail

run_root=/home/glmrunner/gemma-local-kv8
artifact_root="$run_root/artifacts/component"
input_root="$run_root/input"
image='docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a'

mkdir -p "$artifact_root"
nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.used,power.draw,clocks.sm,clocks.mem,temperature.gpu --format=csv -l 1 > "$artifact_root/gpu.csv" 2> "$artifact_root/gpu.stderr" &
telemetry_pid=$!
cleanup() {
  kill "$telemetry_pid" 2>/dev/null || true
  wait "$telemetry_pid" 2>/dev/null || true
}
trap cleanup EXIT

sudo docker pull "$image" > "$artifact_root/image-pull.stdout" 2> "$artifact_root/image-pull.stderr"
sudo docker image inspect "$image" --format '{{json .RepoDigests}}' > "$artifact_root/image-repodigests.json"
command -v ncu > "$artifact_root/ncu-path.txt" 2>&1 || true
command -v nsys > "$artifact_root/nsys-path.txt" 2>&1 || true
sudo docker run --rm --gpus all --ipc=host --shm-size=32g \
  -v "$input_root:/input:ro" \
  -v "$artifact_root:/output" \
  -e "RUNTIME_IMAGE_IDENTITY=$image" \
  --entrypoint bash "$image" -lc \
  'rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; python3 /input/local_kv_head_discriminator.py --output-dir /output' \
  > "$artifact_root/benchmark.stdout" 2> "$artifact_root/benchmark.stderr"

test -f "$artifact_root/TERMINAL.json"
sha256sum "$input_root"/* "$artifact_root"/pinned_decode_attention.py > "$artifact_root/artifact-sha256.txt"
tar -C "$artifact_root" -czf "$run_root/component.tar.gz" .
sha256sum "$run_root/component.tar.gz" > "$run_root/component.tar.gz.sha256"
