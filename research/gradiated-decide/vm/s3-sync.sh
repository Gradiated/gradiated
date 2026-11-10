#!/usr/bin/env bash
# Mirror run directories to S3 every few minutes (spot VMs can disappear at any time).
# Only directories marked complete with a `done` file are uploaded, plus logs and results.
# Usage: S3_PREFIX=s3://<bucket>/gradiated-decide nohup bash s3-sync.sh &
set -uo pipefail
ROOT=${ROOT:-/data/gdecide}
INTERVAL=${INTERVAL:-300}
while true; do
  for run in "$ROOT"/runs/*/; do
    name=$(basename "$run")
    for d in "$run"*/; do
      [ -f "$d/done" ] || continue
      sub=$(basename "$d")
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
