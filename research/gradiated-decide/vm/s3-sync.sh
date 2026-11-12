#!/usr/bin/env bash
# Mirror run directories to S3 every few minutes (spot VMs can disappear at any time).
# Directories marked complete with a `done` file are uploaded whole; unfinished ones upload only their results and logs
# (never partial states). Usage: S3_PREFIX=s3://<bucket>/gradiated-decide nohup bash s3-sync.sh &
set -uo pipefail
ROOT=${ROOT:-/data/gdecide}
INTERVAL=${INTERVAL:-300}
while true; do
  for run in "$ROOT"/runs/*/; do
    name=$(basename "$run")
    for d in "$run"*/; do
      sub=$(basename "$d")
      if [ ! -f "$d/done" ]; then
        # In-progress work (eval shards, logs) so a replacement VM can resume it; states and exports only once complete.
        case "$sub" in state-*|export-*) ;; *) aws s3 sync --only-show-errors "$d" "$S3_PREFIX/runs/$name/$sub/" \
          --exclude "*" --include "*.jsonl" --include "*.log" --include "*.json" || true;; esac
        continue
      fi
      [ -f "$d/.uploaded" ] && [ "$d/.uploaded" -nt "$d/done" ] && continue
      if aws s3 sync --only-show-errors "$d" "$S3_PREFIX/runs/$name/$sub/" --exclude ".uploaded"; then
        touch "$d/.uploaded"
        case "$sub" in state-*) for old in $(aws s3 ls "$S3_PREFIX/runs/$name/" | awk '{print $2}' | grep '^state-' | tr -d /); do
          [ "$old" != "$sub" ] && aws s3 rm --recursive --only-show-errors "$S3_PREFIX/runs/$name/$old/"; done;; esac
      fi
    done
    aws s3 sync --only-show-errors "$run" "$S3_PREFIX/runs/$name/" --exclude "*/*" || true
    for f in "$run"eval-*/; do [ -d "$f" ] && aws s3 sync --only-show-errors "$f" "$S3_PREFIX/runs/$name/$(basename "$f")/" --exclude "*.pt" || true; done
  done
  aws s3 sync --only-show-errors "$ROOT/logs" "$S3_PREFIX/logs" || true
  sleep "$INTERVAL"
done
