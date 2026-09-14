#!/usr/bin/env bash
set -euo pipefail
: "${TUNNEL_HOST:?}"
: "${TUNNEL_USER:?}"
: "${TUNNEL_KEY_FILE:?}"
: "${TUNNEL_KNOWN_HOSTS_FILE:?}"
# An external supervisor restarts this process with bounded backoff.
# Each mapping must match its Nomad server's explicit RPC advertisement.
exec ssh -F /dev/null -NT \
  -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
  -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o ConnectTimeout=10 \
  -o "UserKnownHostsFile=${TUNNEL_KNOWN_HOSTS_FILE}" \
  -i "$TUNNEL_KEY_FILE" -p "${TUNNEL_PORT:-443}" \
  -L 127.77.0.1:4647:nomad-0.nomad-headless.nomad.svc.cluster.local:4647 \
  -L 127.77.0.2:4647:nomad-1.nomad-headless.nomad.svc.cluster.local:4647 \
  -L 127.77.0.3:4647:nomad-2.nomad-headless.nomad.svc.cluster.local:4647 \
  "${TUNNEL_USER}@${TUNNEL_HOST}"
