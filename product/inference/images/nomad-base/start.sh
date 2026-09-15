#!/usr/bin/env bash
set -euo pipefail
# Enrollment supplies the root-owned client configuration and TLS files.
install -d /run/sshd
install -d -o runtime -g runtime /workspace/gradiated/model-cache
if [[ -n "${PUBLIC_KEY:-}" ]]; then
  install -d -m 700 /root/.ssh
  printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
fi
ssh-keygen -A
/usr/sbin/sshd
if [[ -f /etc/nomad/client.hcl ]]; then
  exec nomad agent -config=/etc/nomad/client.hcl
fi
# Allow SSH enrollment before the first client configuration is installed.
exec sleep infinity
