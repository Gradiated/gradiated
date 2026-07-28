#!/usr/bin/env bash
set -Eeuo pipefail

run_root=/home/glmrunner/gemma4-qkv-epilogue
artifact_root="$run_root/artifacts/component"
input_root="$run_root/input"
run_id="${QKV_COMPONENT_RUN_ID:?QKV_COMPONENT_RUN_ID is required}"
image='docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a'
expected_program_sha256=0f9c58b04ec0201e8b0a0dee1e3faab63643e3ded6c01ec7507456ccfb35b86d

[[ "$run_id" =~ ^run-[A-Za-z0-9._-]+$ ]]
mkdir -p "$artifact_root"
test ! -e "$artifact_root/$run_id"
actual_program_sha256=$(sha256sum "$input_root/qkv_epilogue_discriminator.py" | cut -d' ' -f1)
test "$actual_program_sha256" = "$expected_program_sha256"
nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,memory.used,power.draw,clocks.sm,clocks.mem,temperature.gpu --format=csv -l 1 > "$artifact_root/gpu.csv" 2> "$artifact_root/gpu.stderr" &
telemetry_pid=$!
cleanup() {
  kill "$telemetry_pid" 2>/dev/null || true
  wait "$telemetry_pid" 2>/dev/null || true
}
trap cleanup EXIT

sudo docker image inspect "$image" --format '{{json .RepoDigests}}' > "$artifact_root/image-repodigests.json"
sudo docker run --rm --gpus all --ipc=host --shm-size=32g \
  -v "$input_root:/input:ro" \
  -v "$artifact_root:/output" \
  -e "RUNTIME_IMAGE_IDENTITY=$image" \
  --entrypoint bash "$image" -lc \
  "rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; python3 /input/qkv_epilogue_discriminator.py --output-dir /output/$run_id" \
  > "$artifact_root/benchmark.stdout" 2> "$artifact_root/benchmark.stderr"

test -f "$artifact_root/$run_id/TERMINAL.json"
sha256sum "$input_root"/* > "$artifact_root/input-sha256.txt"
tar -C "$artifact_root" -czf "$run_root/component.tar.gz" .
sha256sum "$run_root/component.tar.gz" > "$run_root/component.tar.gz.sha256"
