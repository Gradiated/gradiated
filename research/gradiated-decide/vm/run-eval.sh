#!/usr/bin/env bash
# Evaluate a checkpoint (optionally a LoRA adapter) on the Decision Index panel or the dev sample, then score it.
# Usage: run-eval.sh NAME CHECKPOINT_DIR [sample|panel] [extra evaluate args...]
# Env: EVAL_VENV (default venv; venv-mm for --backend mammoth, from vm/setup-mammoth.sh), COMPARE.
set -euo pipefail
source "$HOME/gdecide/env.sh"
NAME=$1; CKPT=$2; WHICH=${3:-sample}; shift 3 || true
cd "$ROOT"
OUT=runs/evals/$NAME-$WHICH
mkdir -p "$OUT"
# On a replacement VM, resume from the shards s3-sync.sh uploaded (evaluate.py skips ids already answered).
[ -f "$OUT/done" ] || ls "$OUT"/results-*.jsonl >/dev/null 2>&1 || \
  aws s3 sync --only-show-errors "$S3_PREFIX/$OUT" "$OUT" --exclude "*" --include "results-*.jsonl" || true
# The comparison run usually comes from another VM: fetch its merged results (score.py reads results.jsonl).
if [ -n "${COMPARE:-}" ] && [ ! -f "$COMPARE/results.jsonl" ]; then
  aws s3 cp --only-show-errors "$S3_PREFIX/$COMPARE/results.jsonl" "$COMPARE/results.jsonl"
fi
pgrep -f vm/s3-sync.sh >/dev/null || (setsid nohup bash src/gradiated-decide/vm/s3-sync.sh > logs/s3-sync.log 2>&1 < /dev/null &)
cd src/gradiated-decide
../../${EVAL_VENV:-venv}/bin/torchrun --standalone --nproc-per-node 8 -m gdecide.evaluate --suite "$ROOT/suite/suite-0.3" \
  --checkpoint "$CKPT" --out "$ROOT/$OUT" --sample "$ROOT/suite/$WHICH-ids.json" "$@" > "$ROOT/$OUT/eval.log" 2>&1
../../venv/bin/python -m gdecide.score --suite "$ROOT/suite/suite-0.3" --run "$ROOT/$OUT" --sample "$ROOT/suite/$WHICH-ids.json" \
  ${COMPARE:+--compare "$ROOT/$COMPARE"} > "$ROOT/$OUT/score.log" 2>&1
touch "$ROOT/$OUT/done"
aws s3 sync --only-show-errors "$ROOT/$OUT" "$S3_PREFIX/$OUT" --exclude "results-*.jsonl"
aws s3 cp --only-show-errors "$ROOT/$OUT/results.jsonl" "$S3_PREFIX/$OUT/results.jsonl"
grep -m1 '"index"' "$ROOT/$OUT/gdecide-score.json"
