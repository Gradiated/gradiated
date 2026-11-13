#!/usr/bin/env bash
# Full fine-tune with spot safety: restore the run from S3 when the local copy is missing, keep s3-sync.sh running,
# then train (resuming from the newest complete state). Usage: run-train.sh RUN_NAME DATA_NAME [train_full args...]
# Env: CKPT (starting checkpoint, default $ROOT/ckpt/base; $ROOT/ckpt/knowline with --family gemma), VENV.
set -euo pipefail
source "$HOME/gdecide/env.sh"
RUN=$1; DATA=$2; shift 2
cd "$ROOT"
mkdir -p "runs/$RUN" logs
[ -f "data/$DATA/done" ] || { aws s3 sync --only-show-errors "$S3_PREFIX/data/$DATA" "data/$DATA"; touch "data/$DATA/done"; }
# States live in RAM (STATE_ROOT, uploaded by s3-sync.sh); after a preemption the newest one comes back from S3.
STATE_DIR=${STATE_ROOT:-/dev/shm/gdecide}/runs/$RUN
mkdir -p "$STATE_DIR"
if ! ls -d runs/$RUN/state-*/done "$STATE_DIR"/state-*/done >/dev/null 2>&1; then
  latest=$(aws s3 ls "$S3_PREFIX/runs/$RUN/" | awk '{print $2}' | grep '^state-' | tr -d / | sort -t- -k2 -n | tail -1 || true)
  [ -n "$latest" ] && aws s3 sync --only-show-errors "$S3_PREFIX/runs/$RUN/$latest" "$STATE_DIR/$latest" && touch "$STATE_DIR/$latest/.uploaded"
fi
pgrep -f vm/s3-sync.sh >/dev/null || (setsid nohup bash src/gradiated-decide/vm/s3-sync.sh > logs/s3-sync.log 2>&1 < /dev/null &)
cd src/gradiated-decide
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True NCCL_NVLS_ENABLE=0
../../${VENV:-venv}/bin/python -m torch.distributed.run --standalone --nproc-per-node 8 -m gdecide.train_full --checkpoint "${CKPT:-$ROOT/ckpt/base}" \
  --data "$ROOT/data/$DATA" --out "$ROOT/runs/$RUN" --state-dir "$STATE_DIR" "$@"
