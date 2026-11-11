#!/usr/bin/env bash
# Prepare a dev-training VM for Gradiated Decide: Python env, pinned base checkpoint, S3 restore.
# Usage on the VM: S3_PREFIX=s3://<bucket>/gradiated-decide bash bootstrap.sh
set -euo pipefail
ROOT=${ROOT:-/data/gdecide}
BASE_REVISION=cce0f3f80033e9d89d80831d5281fd72124aacce
mkdir -p "$ROOT"/{ckpt,runs,data,suite,logs}
cd "$ROOT"

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH=$HOME/.local/bin:$PATH
command -v aws >/dev/null || { apt-get update -qq && apt-get install -y -qq awscli >/dev/null || uv tool install awscli; }

if [ ! -x venv/bin/python ]; then
  uv venv -q -p 3.12 venv
  VIRTUAL_ENV=$ROOT/venv uv pip install -q torch==2.14.0 torchvision==0.29.0 transformers==5.17.0 safetensors==0.8.0 \
    pillow==12.3.0 huggingface-hub==1.31.0 accelerate peft flash-linear-attention==0.5.2 pyarrow pandas numpy scipy \
    mido python-chess tiktoken
  VIRTUAL_ENV=$ROOT/venv uv pip install -q -e "$ROOT/src/di" -e "$ROOT/src/pplx" -e "$ROOT/src/gradiated-decide"
fi
# Training env: the same packages plus causal-conv1d (Triton and the build need the Python headers).
dpkg -s python3.12-dev >/dev/null 2>&1 || sudo apt-get install -y -qq python3.12-dev >/dev/null
if [ ! -x venv-cc/bin/python ] || ! venv-cc/bin/python -c "import causal_conv1d" 2>/dev/null; then
  rm -rf venv-cc && cp -r venv venv-cc
  CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1) MAX_JOBS=32 VIRTUAL_ENV=$ROOT/venv-cc uv pip install -q --no-build-isolation causal-conv1d
fi

if [ ! -f ckpt/base/done ]; then
  HF_HUB_DISABLE_XET=1 venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('perplexity-ai/pplx-decider-v1.2', revision='$BASE_REVISION', local_dir='ckpt/base', max_workers=16)"
  touch ckpt/base/done
fi

if [ -n "${S3_PREFIX:-}" ]; then
  aws s3 sync --only-show-errors "$S3_PREFIX/suite" suite || true
  aws s3 sync --only-show-errors "$S3_PREFIX/data" data || true
  # Only the baseline evals (for paired deltas); runs restore their own state in run-train.sh.
  aws s3 sync --only-show-errors "$S3_PREFIX/runs/evals" runs/evals --exclude "*" --include "base-*" || true
fi
echo ready
