#!/usr/bin/env bash
# Run in a disposable base image; only synthetic credentials are used.
set -euo pipefail
export GRADIATED_RUNTIME_ACCESS_TOKEN=synthetic_runtime_token_0000000000000000
export GRADIATED_DEPLOYMENT_STATUS_TOKEN=synthetic_status_token_00000000000000000
export GRADIATED_ADAPTER_CONTROL_TOKEN=synthetic_adapter_token_0000000000000000
bash /opt/gradiated/bin/configure-serving
for file in runtime-access.token deployment-status.token runtime-proxy.conf runtime-proxy-auth.conf; do
  runuser -u desmond -- test -r "/etc/gradiated/$file"
  if runuser -u runtime -- test -r "/etc/gradiated/$file"; then
    echo "runtime can read $file" >&2
    exit 1
  fi
done
runuser -u runtime -- test -r /etc/gradiated/adapter-control.token
if runuser -u desmond -- test -r /etc/gradiated/adapter-control.token; then
  echo 'desmond can read adapter control token' >&2
  exit 1
fi
[[ $(stat -c %a /etc/gradiated/adapter-control.token) == 600 ]]
status=0
GRADIATED_ADAPTER_CONTROL_TOKEN='invalid"token' bash /opt/gradiated/bin/configure-serving 2>/dev/null || status=$?
[[ $status == 64 ]]
status=0
GRADIATED_RUNTIME_ACCESS_TOKEN='invalid"token' bash /opt/gradiated/bin/configure-serving 2>/dev/null || status=$?
[[ $status == 64 ]]
runuser -u desmond -- bash -c 'ulimit -S -n 1024; exec nginx -c /etc/gradiated/runtime-proxy.conf -g "daemon off;"' &
proxy=$!
trap 'kill -TERM "$proxy" 2>/dev/null || true; wait "$proxy" 2>/dev/null || true; rm -f /etc/gradiated/adapter-control.token' EXIT

request() {
  TOKEN="$1" REQUEST_PATH="${2:-/health}" timeout 5 bash -c '
    set -e
    exec 3<>/dev/tcp/127.0.0.1/8888
    printf "GET %s HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer %s\r\nConnection: close\r\n\r\n" "$REQUEST_PATH" "$TOKEN" >&3
    IFS= read -r line <&3
    printf "%s" "$line"
  '
}
for attempt in {1..20}; do
  if response=$(request '' 2>/dev/null); then break; fi
  sleep 0.1
done
[[ $response == *' 401 '* ]]
[[ $(request wrong-token) == *' 401 '* ]]
# No model runs in this test: an authenticated request must reach the absent upstream.
[[ $(request "$GRADIATED_RUNTIME_ACCESS_TOKEN") == *' 502 '* ]]
for operation in load unload; do
  [[ $(request "$GRADIATED_RUNTIME_ACCESS_TOKEN" "/v1/${operation}_lora_adapter") == *' 404 '* ]]
done
master=$(cat /tmp/gradiated-runtime-proxy.pid)
workers=$(cat "/proc/$master/task/$master/children")
[[ -n "$workers" ]]
for worker in $workers; do
  limit=$(awk '$1 == "Max" && $2 == "open" && $3 == "files" { print $4 }' "/proc/$worker/limits")
  [[ "$limit" == unlimited || "$limit" -ge 8192 ]]
done
echo 'Serving proxy authentication, credential isolation and file limits passed'
