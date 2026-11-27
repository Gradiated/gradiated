#!/usr/bin/env bash
# A KnowLine fine-tune's blend (its export at STEP, weight ALPHA, with KnowLine) on Google's Gemini Decision 1 panel,
# through the release SGLang servers. The blend is rebuilt from the S3 export on a new VM.
# Usage on the VM: run-knowline-external.sh RUN STEP [ALPHA=0.5]   (e.g. gd-kl1 1155 0.5; writes logs/RUN-external-finished)
set -euo pipefail
source "$HOME/gdecide/env.sh"
RUN=$1; STEP=$2; ALPHA=${3:-0.5}
cd "$ROOT"
NAME=$RUN-s$STEP-a$ALPHA; MERGED=$ROOT/runs/merges/$NAME
bash src/gradiated-decide/vm/get-knowline.sh
if [ ! -f "$MERGED/done" ]; then
  [ -f "runs/$RUN/export-$STEP/done" ] || aws s3 sync --only-show-errors "$S3_PREFIX/runs/$RUN/export-$STEP" "runs/$RUN/export-$STEP"
  (cd src/gradiated-decide && ../../venv/bin/python -m gdecide.merge --base "$ROOT/ckpt/knowline" --models "$ROOT/runs/$RUN/export-$STEP" \
    --weights "$ALPHA" --out "$MERGED")
fi
bash src/gradiated-decide/vm/serve-knowline.sh "$MERGED"
bash src/gradiated-decide/vm/run-external.sh "$NAME" "$MERGED" --backend knowline-http
STOP=1 bash src/gradiated-decide/vm/serve-knowline.sh "$MERGED"
touch "logs/$RUN-external-finished"
