#!/usr/bin/env bash
set -uo pipefail
exec 9>/var/lib/gradiated-tailscale/control.lock
flock --exclusive --nonblock 9 || exit 0
child=''
trap '[[ -z "$child" ]] || kill -TERM "$child" 2>/dev/null; exit 0' TERM INT
while true; do
  python3 /opt/gradiated/bin/forward-control 9>&- &
  child=$!
  wait "$child" || true
  child=''
  sleep 2
done
