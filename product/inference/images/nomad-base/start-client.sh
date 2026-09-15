#!/usr/bin/env bash
set -euo pipefail
# Runpod has no delegated cgroups. These capabilities permit user switching,
# allocation ownership, process cleanup, and garbage collection of runtime-owned
# directories without running the agent as root. Model tasks explicitly drop all capabilities.
exec setpriv --reuid=nomad --regid=nomad --init-groups \
  --inh-caps=+setuid,+setgid,+chown,+kill,+dac_override \
  --ambient-caps=+setuid,+setgid,+chown,+kill,+dac_override \
  nomad agent -config=/etc/nomad/client.hcl
