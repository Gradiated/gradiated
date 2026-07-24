#!/usr/bin/env bash
set -euo pipefail

packet_root="${1:?packet root required}"
artifact_root="${2:?artifact root required}"
export PYTHONPATH="${packet_root}/inputs/exact_gemma_kv4:${PYTHONPATH:-}"
export CUDA_DEVICE_MAX_CONNECTIONS=1
export TORCHINDUCTOR_CACHE_DIR="${artifact_root}/torch-cache"
export TRITON_CACHE_DIR="${artifact_root}/triton-cache"
mkdir -p "${artifact_root}"
python3 "${packet_root}/inputs/exact_gemma_kv4/kv4_component.py" \
  --artifact-root "${artifact_root}" \
  --iterations 50
