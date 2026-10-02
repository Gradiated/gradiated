#!/usr/bin/env bash
set -euo pipefail
# Provider configuration survives resets; tokens are scoped to their consuming user.
: "${GRADIATED_RUNTIME_ACCESS_TOKEN:?runtime access token is required}"
: "${GRADIATED_DEPLOYMENT_STATUS_TOKEN:?reporting token is required}"
for token in "$GRADIATED_RUNTIME_ACCESS_TOKEN" "$GRADIATED_DEPLOYMENT_STATUS_TOKEN"; do
  [[ "$token" =~ ^[A-Za-z0-9_-]{32,256}$ ]] || {
    echo 'Serving tokens must be 32-256 base64url characters' >&2
    exit 64
  }
done
if [[ -n "${GRADIATED_ADAPTER_CONTROL_TOKEN:-}" && ! "$GRADIATED_ADAPTER_CONTROL_TOKEN" =~ ^[A-Za-z0-9_-]{32,256}$ ]]; then
  echo 'Adapter token must be 32-256 base64url characters' >&2
  exit 64
fi
umask 077
printf '%s\n' "$GRADIATED_RUNTIME_ACCESS_TOKEN" >/etc/gradiated/runtime-access.token
printf '%s\n' "$GRADIATED_DEPLOYMENT_STATUS_TOKEN" >/etc/gradiated/deployment-status.token
template=$(cat /etc/gradiated/runtime-proxy.conf.template)
printf '%s\n' "${template//__RUNTIME_TOKEN__/$GRADIATED_RUNTIME_ACCESS_TOKEN}" \
  >/etc/gradiated/runtime-proxy.conf
# The host-proxy job renders its routes from Nomad and includes this map entry.
printf '"Bearer %s" 1;\n' "$GRADIATED_RUNTIME_ACCESS_TOKEN" >/etc/gradiated/runtime-proxy-auth.conf
chown desmond:desmond /etc/gradiated/{runtime-access.token,deployment-status.token,runtime-proxy.conf,runtime-proxy-auth.conf}
chmod 600 /etc/gradiated/{runtime-access.token,deployment-status.token,runtime-proxy.conf,runtime-proxy-auth.conf}
if [[ -n "${GRADIATED_ADAPTER_CONTROL_TOKEN:-}" ]]; then
  printf '%s\n' "$GRADIATED_ADAPTER_CONTROL_TOKEN" >/etc/gradiated/adapter-control.token
  chown runtime:runtime /etc/gradiated/adapter-control.token
  chmod 600 /etc/gradiated/adapter-control.token
fi
