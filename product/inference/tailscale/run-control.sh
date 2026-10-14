#!/usr/bin/env bash
set -uo pipefail
child=''
trap '[[ -z "$child" ]] || kill -TERM "$child" 2>/dev/null; exit 0' TERM INT
while true; do
  python3 /opt/gradiated/bin/forward-control &
  child=$!
  wait "$child" || true
  child=''
  sleep 2
done
