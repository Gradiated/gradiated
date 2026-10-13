#!/usr/bin/env bash
set -euo pipefail
: "${PUBLIC_KEY:?A public SSH key is required for enrollment}"
install -d -m 700 /root/.ssh
printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
unset PUBLIC_KEY GRADIATED_GPU_BOOTSTRAP
ssh-keygen -A
exec /usr/sbin/sshd -D -e
