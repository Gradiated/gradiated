#!/usr/bin/env bash
# After a run finishes: interpolate its final export with the base at several weights, score each on the dev
# sample against the base, then run the best on the full panel. Usage: after-train.sh RUN_NAME "1.0 0.7 0.5"
set -uo pipefail
source "$HOME/gdecide/env.sh"
RUN=$1; ALPHAS=${2:-"1.0 0.7 0.5"}
cd "$ROOT"
until grep -q '"event": "finished"' "runs/$RUN/train.log.jsonl" 2>/dev/null; do sleep 60; done
FINAL=$(ls -d runs/$RUN/export-*/ | sort -t- -k3 -n | tail -1); FINAL=${FINAL%/}
STEP=${FINAL##*-}
best=""; best_index=-1
for a in $ALPHAS; do
  name=$RUN-s$STEP-a$a
  ckpt=$ROOT/$FINAL
  if [ "$a" != "1.0" ]; then
    ckpt=$ROOT/runs/merges/$name
    [ -f "$ckpt/done" ] || (cd src/gradiated-decide && ../../venv/bin/python -m gdecide.merge --base "$ROOT/ckpt/base" --models "$ROOT/$FINAL" --weights "$a" --out "$ckpt")
  fi
  COMPARE=runs/evals/base-sample bash src/gradiated-decide/vm/run-eval.sh "$name" "$ckpt" sample
  idx=$(python3 -c "import json;print(json.load(open('runs/evals/$name-sample/gdecide-score.json'))['index'])")
  echo "{\"candidate\": \"$name\", \"sample_index\": $idx}" >> "runs/$RUN/candidates.jsonl"
  if python3 -c "import sys;sys.exit(0 if $idx > $best_index else 1)"; then best=$name; best_index=$idx; best_ckpt=$ckpt; fi
done
echo "{\"best\": \"$best\", \"sample_index\": $best_index}" >> "runs/$RUN/candidates.jsonl"
COMPARE=runs/evals/base-panel bash src/gradiated-decide/vm/run-eval.sh "$best" "$best_ckpt" panel
touch "runs/$RUN/after-train-done"
aws s3 cp --only-show-errors "runs/$RUN/candidates.jsonl" "$S3_PREFIX/runs/$RUN/candidates.jsonl"
