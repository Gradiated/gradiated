#!/usr/bin/env bash
# v3 data pilot: prepare mixes/v3.json (v2 plus the broad public sources, with abstention and state re-serialisation
# augmentation), then train two short runs from the pplx base with identical settings, one on v3 and one on v1 as the
# control, and score both on the Decision Index dev sample and Google's panel. Brier weight 1 and LR 2.7e-6 follow
# the recipe in the mammoth-1 technical report (ideas only; nothing of theirs is used).
# Usage on the VM: run-v3-pilot.sh [STEPS=240]   (idempotent; data, runs and results in S3)
set -euo pipefail
source "$HOME/gdecide/env.sh"
STEPS=${1:-240}
cd "$ROOT"
V=src/gradiated-decide/vm
PY=$ROOT/venv/bin/python
mkdir -p logs data/broad
if [ ! -f data/v3/done ]; then
  if aws s3 ls "$S3_PREFIX/data/v3/done" >/dev/null 2>&1; then
    aws s3 sync --only-show-errors "$S3_PREFIX/data/v3" data/v3
  else
    aws s3 sync --only-show-errors "$S3_PREFIX/data/broad" data/broad
    (cd src/gradiated-decide && $PY -m gdecide.prepare --checkpoint "$ROOT/ckpt/base" --mix mixes/v3.json --out "$ROOT/data/v3" --workers 48)
    touch data/v3/done
    aws s3 sync --only-show-errors data/v3 "$S3_PREFIX/data/v3"
  fi
fi
for DATA in v3 v1; do
  RUN=pilot-$DATA-s$STEPS
  grep -q '"event": "finished"' "runs/$RUN/train.log.jsonl" 2>/dev/null || \
    VENV=venv-cc bash $V/run-train.sh "$RUN" "$DATA" --epochs 1 --max-steps "$STEPS" --lr 2.7e-6 --readout-lr 1e-5 \
      --brier 1.0 --warmup 8 --state-minutes 30 --dev-every 120 --seed 20261112 > "logs/train-$RUN.log" 2>&1
  [ -f "runs/$RUN/export-$STEPS/done" ] || aws s3 sync --only-show-errors "$S3_PREFIX/runs/$RUN/export-$STEPS" "runs/$RUN/export-$STEPS"
  [ -f "runs/evals/$RUN-sample/done" ] || COMPARE=runs/evals/base-sample bash $V/run-eval.sh "$RUN" "$ROOT/runs/$RUN/export-$STEPS" sample
  [ -f "runs/external/$RUN/done" ] || bash $V/run-external.sh "$RUN" "$ROOT/runs/$RUN/export-$STEPS"
done
touch logs/v3-pilot-finished
