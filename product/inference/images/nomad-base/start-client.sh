#!/usr/bin/env bash
set -euo pipefail
# Runpod has no delegated cgroups. These capabilities permit user switching,
# allocation ownership, and process cleanup without running the agent as root.
exec setpriv --reuid=nomad --regid=nomad --init-groups \
  --inh-caps=+setuid,+setgid,+chown,+kill \
  --ambient-caps=+setuid,+setgid,+chown,+kill \
  nomad agent -config=/etc/nomad/client.hcl
