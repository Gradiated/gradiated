#!/usr/bin/env bash
# One unattended run on a fresh or replacement VM: bootstrap, train (resuming from S3), then the merge sweep and the
# full-panel eval of the best blend. Usage: campaign.sh RUN DATA "ALPHAS" [train_full args...]
set -uo pipefail
source "$HOME/gdecide/env.sh"
RUN=$1; DATA=$2; ALPHAS=$3; shift 3
cd "$ROOT"
bash src/gradiated-decide/vm/bootstrap.sh > logs/bootstrap.log 2>&1 || { echo "bootstrap failed"; exit 1; }
[ -f "runs/$RUN/after-train-done" ] && exit 0
grep -q '"event": "finished"' "runs/$RUN/train.log.jsonl" 2>/dev/null || \
  VENV=venv-cc bash src/gradiated-decide/vm/run-train.sh "$RUN" "$DATA" "$@" > "logs/train-$RUN.log" 2>&1
bash src/gradiated-decide/vm/after-train.sh "$RUN" "$ALPHAS" > "logs/after-train-$RUN.log" 2>&1
