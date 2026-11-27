#!/usr/bin/env bash
# mammoth-1 on everything the ensemble is compared on: Google's Gemini Decision 1 panel (incl. JevBench public), the
# gate's held-out gold rows, and the Decision Index full panel. Idempotent; each step resumes from S3 on a new VM.
# Usage on the VM: run-mammoth.sh [MODEL=mammoth-1]
set -euo pipefail
source "$HOME/gdecide/env.sh"
MODEL=${1:-mammoth-1}
cd "$ROOT"
V=src/gradiated-decide/vm
bash $V/bootstrap.sh > logs/bootstrap.log 2>&1
bash $V/setup-mammoth.sh "$MODEL" > logs/setup-mammoth.log 2>&1
export EVAL_VENV=venv-mm
bash $V/run-external.sh "$MODEL" "$ROOT/ckpt/$MODEL" --backend mammoth
ITEMS=external/gate-items.jsonl bash $V/run-external.sh "gate-$MODEL" "$ROOT/ckpt/$MODEL" --backend mammoth
[ -f "runs/evals/$MODEL-panel/done" ] || COMPARE=runs/evals/base-panel bash $V/run-eval.sh "$MODEL" "$ROOT/ckpt/$MODEL" panel --backend mammoth
