#!/usr/bin/env bash
set -uo pipefail
child=''
stop() {
  [[ -z "$child" ]] || kill -TERM "$child" 2>/dev/null || true
  exit 0
}
trap stop TERM INT
while true; do
  python3 /opt/gradiated/bin/renew-certificate &
  child=$!
  status=0
  wait "$child" || status=$?
  child=''
  [[ "$status" != 75 ]] || exit 0
  printf '{"event":"host_certificate_renewer_exited","exit_code":%d}\n' "$status"
  sleep 60
done
