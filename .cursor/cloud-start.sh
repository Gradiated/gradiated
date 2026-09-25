#!/usr/bin/env bash
# Per-boot Cloud Agent start: bring up the Docker daemon and the stateful
# datastores (PostgreSQL, Valkey, ClickHouse), then apply migrations. Tolerant
# of restarts; returns once the datastores are ready and migrated.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/cloud-env.sh"

start_dockerd() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "Starting dockerd (fuse-overlayfs)..."
  sudo mkdir -p /etc/docker
  if [ ! -f /etc/docker/daemon.json ]; then
    echo '{"features":{"containerd-snapshotter":false},"storage-driver":"fuse-overlayfs"}' \
      | sudo tee /etc/docker/daemon.json >/dev/null
  fi

  # A base snapshot can bake a stale, root-owned dockerd log/pid/socket from an
  # earlier boot. Remove them so the daemon starts cleanly on this boot.
  sudo rm -f /var/log/dockerd.log /var/run/docker.pid
  sudo bash -c 'nohup dockerd >/var/log/dockerd.log 2>&1 &'

  for _ in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
      break
    fi
    sudo chmod 666 /var/run/docker.sock 2>/dev/null || true
    sleep 1
  done

  sudo chmod 666 /var/run/docker.sock 2>/dev/null || true
  docker info >/dev/null 2>&1
}

wait_healthy() {
  local name="$1"
  for _ in $(seq 1 90); do
    local status
    status="$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo missing)"
    if [ "$status" = "healthy" ]; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for $name to become healthy" >&2
  return 1
}

ensure_valkey_cluster() {
  for _ in $(seq 1 60); do
    if docker exec gradiated-valkey-1 valkey-cli cluster info 2>/dev/null | grep -q 'cluster_state:ok'; then
      return 0
    fi
    # Single-node cluster: assign all slots once. "already busy" is fine.
    docker exec gradiated-valkey-1 valkey-cli cluster addslotsrange 0 16383 >/dev/null 2>&1 || true
    sleep 1
  done
  echo "Timed out waiting for Valkey cluster to reach cluster_state:ok" >&2
  return 1
}

start_dockerd

cd "${PRODUCT_DIR}"
docker compose up -d

wait_healthy gradiated-postgres-1
wait_healthy gradiated-clickhouse-1
ensure_valkey_cluster

echo "Applying PostgreSQL migrations..."
mise_run pnpm --filter @gradiated/control db:migrate

echo "Applying ClickHouse migrations..."
mise_run pnpm --filter @gradiated/control clickhouse:migrate

echo "Datastores are up and migrated. Application services start in their terminals."
