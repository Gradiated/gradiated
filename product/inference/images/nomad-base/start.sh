#!/usr/bin/env bash
set -euo pipefail
# Enrollment supplies client configuration and private, agent-owned TLS files.
install -d /run/sshd
# Mounted provider storage may reject chown. Create the cache as its user.
runuser -u runtime -- mkdir -p /workspace/gradiated/model-cache
if [[ -n "${PUBLIC_KEY:-}" ]]; then
  install -d -m 700 /root/.ssh
  printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
fi
ssh-keygen -A
/usr/sbin/sshd
if [[ -f /etc/nomad/client.hcl ]]; then
  exec bash /opt/gradiated/bin/start-client
fi
# Allow SSH enrollment before the first client configuration is installed.
exec sleep infinity
