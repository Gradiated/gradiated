#!/usr/bin/env bash
# Run inside the built base image: no GPU, network, or production credentials needed.
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
chmod 755 "$work"
id desmond >/dev/null
id runtime >/dev/null
ldd /opt/gradiated/bin/desmondd | (! grep 'not found')

rejects_reporting() {
  local what=$1 status=0
  shift
  "$@" bash /opt/gradiated/bin/start-desmond 2>/dev/null || status=$?
  [[ $status -eq 64 ]] || {
    echo "$what exited $status, not 64" >&2
    exit 1
  }
}

if /bin/bash /opt/gradiated/bin/start-desmond 2>/dev/null; then
  echo 'missing reporting configuration was accepted' >&2
  exit 1
fi

printf 'test-only-status\n' >"$work/status.token"
printf 'test-only-control\n' >"$work/control.token"
chown desmond:desmond "$work/status.token"
chmod 600 "$work/status.token"
if runuser -u runtime -- test -r "$work/status.token"; then
  echo 'runtime can read reporter credentials' >&2
  exit 1
fi

export DESMOND_DEPLOYMENT_ID=test DESMOND_RELEASE=test DESMOND_MODEL=test \
  DESMOND_STATUS_URL=https://status.invalid \
  DESMOND_STATUS_TOKEN_FILE="$work/status.token" \
  DESMOND_CONTROL_TOKEN_FILE="$work/control.token"
rejects_reporting 'An HTTP status endpoint' env DESMOND_STATUS_URL=http://status.invalid
rejects_reporting 'An unreadable status token' runuser -u runtime --

install -d -o downloader -g downloader -m 755 /var/lib/nomad-alloc/reporting-gc-test
runuser -u downloader -- touch /var/lib/nomad-alloc/reporting-gc-test/runtime-file
install -d -m 755 "$work/bin"
printf '#!/usr/bin/env bash\nrm -rf /var/lib/nomad-alloc/reporting-gc-test\n' >"$work/bin/nomad"
chmod 755 "$work/bin/nomad"
PATH="$work/bin:$PATH" bash /opt/gradiated/bin/start-client
[[ ! -e /var/lib/nomad-alloc/reporting-gc-test ]]

echo 'base reporting prerequisites, credential isolation and allocation cleanup passed'
