#!/usr/bin/env bash
# Run inside the built base image: no GPU, network, or production credentials needed.
set -euo pipefail
id desmond >/dev/null
id runtime >/dev/null
ldd /opt/gradiated/bin/desmondd | (! grep 'not found')
if /bin/bash /opt/gradiated/bin/start-desmond 2>/dev/null; then
  echo 'missing reporting configuration was accepted' >&2
  exit 1
fi
install -d -o downloader -g downloader -m 755 /var/lib/nomad-alloc/reporting-gc-test
runuser -u downloader -- touch /var/lib/nomad-alloc/reporting-gc-test/runtime-file
# Check the same capabilities as the actual client launcher, without starting an agent.
setpriv --reuid=nomad --regid=nomad --init-groups \
  --inh-caps=+setuid,+setgid,+chown,+kill,+dac_override \
  --ambient-caps=+setuid,+setgid,+chown,+kill,+dac_override \
  rm -rf /var/lib/nomad-alloc/reporting-gc-test
[[ ! -e /var/lib/nomad-alloc/reporting-gc-test ]]
install -m 600 -o desmond -g desmond /dev/null /tmp/reporting-test.token
if runuser -u runtime -- test -r /tmp/reporting-test.token; then
  echo 'runtime can read reporter credentials' >&2
  exit 1
fi
rm /tmp/reporting-test.token
echo 'base reporting prerequisites, credential isolation and allocation cleanup passed'
