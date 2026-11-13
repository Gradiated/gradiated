#!/usr/bin/env bash
# gd-kl1's best blend (its final export at weight ALPHA with KnowLine) on Google's Gemini Decision 1 panel, through the
# release SGLang servers. The blend is rebuilt from the S3 export on a new VM. Usage on the VM: run-kl1-external.sh [ALPHA=0.5]
set -euo pipefail
source "$HOME/gdecide/env.sh"
ALPHA=${1:-0.5}
cd "$ROOT"
NAME=gd-kl1-s1155-a$ALPHA; MERGED=$ROOT/runs/merges/$NAME
KL_REVISION=8e56aa1b236a6dd1064dcfd22ba1e5e360e4c140  # as run-ensemble-eval.sh
if [ ! -f ckpt/knowline/done ]; then
  HF_HUB_DISABLE_XET=1 venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('PelaAI/KnowLine-31B-Gen1.5', revision='$KL_REVISION', local_dir='ckpt/knowline', max_workers=16)"
  (cd ckpt/knowline && sha256sum --quiet --ignore-missing -c SHA256SUMS) || { echo "KnowLine SHA256SUMS mismatch" >&2; exit 1; }
  echo "$KL_REVISION" > ckpt/knowline/done
fi
if [ ! -f "$MERGED/done" ]; then
  [ -f runs/gd-kl1/export-1155/done ] || aws s3 sync --only-show-errors "$S3_PREFIX/runs/gd-kl1/export-1155" runs/gd-kl1/export-1155
  (cd src/gradiated-decide && ../../venv/bin/python -m gdecide.merge --base "$ROOT/ckpt/knowline" --models "$ROOT/runs/gd-kl1/export-1155" \
    --weights "$ALPHA" --out "$MERGED")
fi
bash src/gradiated-decide/vm/serve-knowline.sh "$MERGED"
bash src/gradiated-decide/vm/run-external.sh "$NAME" "$MERGED" --backend knowline-http
STOP=1 bash src/gradiated-decide/vm/serve-knowline.sh "$MERGED"
touch logs/kl1-external-finished
