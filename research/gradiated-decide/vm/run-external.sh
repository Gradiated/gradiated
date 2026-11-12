#!/usr/bin/env bash
# Google's Gemini Decision 1 launch panel (gdecide.external) for one model, resumable, results to S3.
# Usage on the VM: run-external.sh NAME CHECKPOINT_DIR [extra `gdecide.external run` args, e.g. --backend knowline]
# CHECKPOINT_DIR may be "merge:RUN/export-STEP:ALPHA" to rebuild a blend with the base from the S3 export.
set -euo pipefail
source "$HOME/gdecide/env.sh"
NAME=$1; CKPT=$2; shift 2
cd "$ROOT"
OUT=runs/external/$NAME
mkdir -p "$OUT" external
pgrep -f vm/s3-sync.sh >/dev/null || (setsid nohup bash src/gradiated-decide/vm/s3-sync.sh > logs/s3-sync.log 2>&1 < /dev/null &)
[ -s external/items.jsonl ] || aws s3 cp --only-show-errors "$S3_PREFIX/external/items.jsonl" external/items.jsonl
if [[ $CKPT == merge:* ]]; then
  IFS=: read -r _ export alpha <<<"$CKPT"
  merged=$ROOT/runs/merges/$(dirname "$export")-s${export##*-}-a$alpha
  if [ ! -f "$merged/done" ]; then
    [ -f "runs/$export/done" ] || aws s3 sync --only-show-errors "$S3_PREFIX/runs/$export" "runs/$export"
    (cd src/gradiated-decide && ../../venv/bin/python -m gdecide.merge --base "$ROOT/ckpt/base" --models "$ROOT/runs/$export" \
      --weights "$alpha" --out "$merged")
  fi
  CKPT=$merged
fi
# Resume from the predictions s3-sync.sh uploaded, on a replacement VM.
[ -f "$OUT/done" ] || ls "$OUT"/predictions-*.jsonl >/dev/null 2>&1 || \
  aws s3 sync --only-show-errors "$S3_PREFIX/$OUT" "$OUT" --exclude "*" --include "predictions-*.jsonl" || true
cd src/gradiated-decide
[ -f "$ROOT/$OUT/done" ] || ../../venv/bin/torchrun --standalone --nproc-per-node 8 -m gdecide.external run \
  --items "$ROOT/external/items.jsonl" --checkpoint "$CKPT" --out "$ROOT/$OUT" "$@" > "$ROOT/$OUT/run.log" 2>&1
../../venv/bin/python -m gdecide.external score --items "$ROOT/external/items.jsonl" --run "$ROOT/$OUT" > "$ROOT/$OUT/score.log"
touch "$ROOT/$OUT/done"
aws s3 sync --only-show-errors "$ROOT/$OUT" "$S3_PREFIX/$OUT"
