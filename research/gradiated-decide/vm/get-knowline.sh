#!/usr/bin/env bash
# Download KnowLine-31B-Gen1.5 at the pinned revision into $ROOT/ckpt/knowline and check its SHA256SUMS (idempotent).
set -euo pipefail
source "$HOME/gdecide/env.sh"
cd "$ROOT"
KL_REVISION=8e56aa1b236a6dd1064dcfd22ba1e5e360e4c140  # as run-ensemble-eval.sh
if [ ! -f ckpt/knowline/done ]; then
  HF_HUB_DISABLE_XET=1 venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('PelaAI/KnowLine-31B-Gen1.5', revision='$KL_REVISION', local_dir='ckpt/knowline', max_workers=16)"
  (cd ckpt/knowline && sha256sum --quiet --ignore-missing -c SHA256SUMS) || { echo "KnowLine SHA256SUMS mismatch" >&2; exit 1; }
  echo "$KL_REVISION" > ckpt/knowline/done
fi
