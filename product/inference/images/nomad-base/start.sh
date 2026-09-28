#!/usr/bin/env bash
set -euo pipefail
# A provider reset wipes the container filesystem, so the bootstrap arrives in the
# environment on every boot and is cleared before anything else starts.
bootstrap=(
  GRADIATED_INSTANCE_ID GRADIATED_NODE_NAME GRADIATED_NOMAD_NODE_ID
  GRADIATED_NOMAD_NODE_SECRET GRADIATED_NOMAD_CA GRADIATED_NOMAD_CERT
  GRADIATED_NOMAD_KEY GRADIATED_ARTIFACT_ENV
)
uuid='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

private_file() {
  install -m 600 -o "$1" -g "$1" /dev/null "$2"
  cat >"$2"
}

write_bootstrap() {
  local name
  for name in "${bootstrap[@]}"; do
    [[ -n "${!name:-}" ]] || {
      echo "Host bootstrap is missing $name" >&2
      exit 1
    }
  done
  for name in GRADIATED_INSTANCE_ID GRADIATED_NOMAD_NODE_ID GRADIATED_NOMAD_NODE_SECRET; do
    [[ "${!name}" =~ $uuid ]] || {
      echo "$name must be a UUID" >&2
      exit 1
    }
  done
  [[ "$GRADIATED_NODE_NAME" =~ ^[a-z0-9-]{1,63}$ ]] || {
    echo 'GRADIATED_NODE_NAME must be a lowercase DNS label' >&2
    exit 1
  }

  base64 -d <<<"$GRADIATED_NOMAD_CA" | private_file nomad /etc/nomad/tls/ca.pem
  base64 -d <<<"$GRADIATED_NOMAD_CERT" | private_file nomad /etc/nomad/tls/client.pem
  base64 -d <<<"$GRADIATED_NOMAD_KEY" | private_file nomad /etc/nomad/tls/client-key.pem
  base64 -d <<<"$GRADIATED_ARTIFACT_ENV" | private_file downloader /etc/gradiated/artifact.env

  # Nomad adopts this identity; it rejects a trailing newline.
  install -d -m 700 -o nomad -g nomad /var/lib/nomad/client
  printf '%s' "$GRADIATED_NOMAD_NODE_ID" | private_file nomad /var/lib/nomad/client/client-id
  printf '%s' "$GRADIATED_NOMAD_NODE_SECRET" | private_file nomad /var/lib/nomad/client/secret-id

  cat >/etc/nomad/node.hcl <<EOF
name = "$GRADIATED_NODE_NAME"
client {
  meta {
    gradiated_instance_id = "$GRADIATED_INSTANCE_ID"
    serving_ingress = "host-proxy"
    runtime_base_id = "$(cat /etc/gradiated/base-id)"
  }
}
EOF
}

install -d /run/sshd
# Mounted provider storage may reject chown. Create the cache as its user.
runuser -u runtime -- mkdir -p /workspace/gradiated/model-cache

if [[ -n "${GRADIATED_NOMAD_NODE_ID:-}" ]]; then
  write_bootstrap
fi
unset "${bootstrap[@]}"

if [[ -n "${GRADIATED_RUNTIME_ACCESS_TOKEN:-}${GRADIATED_DEPLOYMENT_STATUS_TOKEN:-}" ]]; then
  bash /opt/gradiated/bin/configure-serving
fi
unset GRADIATED_RUNTIME_ACCESS_TOKEN GRADIATED_DEPLOYMENT_STATUS_TOKEN

if [[ -n "${PUBLIC_KEY:-}" ]]; then
  install -d -m 700 /root/.ssh
  printf '%s\n' "$PUBLIC_KEY" >/root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  ssh-keygen -A
  /usr/sbin/sshd
fi

if [[ -f /etc/nomad/node.hcl ]]; then
  exec bash /opt/gradiated/bin/start-client
fi
echo 'No host bootstrap; run instance:register for this machine' >&2
exec sleep infinity
