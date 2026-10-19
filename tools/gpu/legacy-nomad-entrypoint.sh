#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != agent ]]; then
  printf '%s\n' 'Nomad is retired on this Gradiated host.' >&2
  exit 64
fi

[[ -f /etc/gradiated/kubelet.json ]]
[[ -f /etc/gradiated/tailscale.json ]]
[[ -f /opt/gradiated/kubelet/bootstrap.py ]]

bash /opt/gradiated/bin/start-tailscale
exec env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  python3 -B /opt/gradiated/kubelet/bootstrap.py
