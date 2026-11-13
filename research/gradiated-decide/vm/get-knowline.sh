#!/usr/bin/env bash
# Download KnowLine-31B-Gen1.5 at the pinned revision into $ROOT/ckpt/knowline and check its SHA256SUMS (idempotent).
set -euo pipefail
source "$HOME/gdecide/env.sh"
cd "$ROOT"
# The repo history was squashed on 2026-11-12, dropping 8e56aa1b; 56ca884 has byte-identical weights, tokenizer, config,
# temperatures and layout (SHA256SUMS differ only in README, INFERENCE.md and comments in knowline_server.py).
KL_REVISION=56ca884a8e3195c9c0786a4ec22e651669d04ba9  # as run-ensemble-eval.sh
if [ ! -f ckpt/knowline/done ]; then
  HF_HUB_DISABLE_XET=1 venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('PelaAI/KnowLine-31B-Gen1.5', revision='$KL_REVISION', local_dir='ckpt/knowline', max_workers=16)"
  (cd ckpt/knowline && sha256sum --quiet --ignore-missing -c SHA256SUMS) || { echo "KnowLine SHA256SUMS mismatch" >&2; exit 1; }
  echo "$KL_REVISION" > ckpt/knowline/done
fi
