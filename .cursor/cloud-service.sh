#!/usr/bin/env bash
# Launches one product service in a Cloud Agent terminal. Mirrors the native
# host processes from product/mprocs.yaml. Usage: cloud-service.sh <name>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/cloud-env.sh"

service="${1:?usage: cloud-service.sh <api|worker|gateway|console|seed>}"

cd "${PRODUCT_DIR}"

wait_for_url() {
  local url="$1"
  for _ in $(seq 1 120); do
    if curl -fsS -m 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

case "$service" in
  api)
    export PORT="3001"
    mise_run pnpm --filter @gradiated/api dev
    ;;

  worker)
    export METRICS_PORT="9465"
    export WORKER_CONSUMER_NAME="local-worker-1"
    mise_run pnpm --filter @gradiated/worker dev
    ;;

  gateway)
    export GATEWAY_BIND_ADDRESS="127.0.0.1:3002"
    export GATEWAY_GENERATION_TIMEOUT_SECONDS="630"
    export GATEWAY_BROWSER_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
    export GATEWAY_SETTLEMENT_BACKLOG_LIMIT="100000"
    mise_run cargo run --manifest-path services/gateway/Cargo.toml --locked
    ;;

  console)
    mise_run pnpm --filter @gradiated/console dev
    ;;

  seed)
    echo "Waiting for the API to become ready before seeding..."
    if ! wait_for_url "http://127.0.0.1:3001/health/ready"; then
      echo "API did not become ready; run the seed manually from product/." >&2
      exit 1
    fi
    export SEED_API_URL="http://127.0.0.1:3001"
    # Include the small local model so the gateway advertises a catalog entry.
    # DeepSeek/GLM are seeded as catalog-only rows with no deployments, so
    # without this the gateway serves an empty /v1/models on a clean boot.
    export SEED_LOCAL_QWEN="1"
    mise_run pnpm --filter @gradiated/api seed
    echo
    echo "Seed complete. Sign in at http://localhost:3000 as dev@gradiated.com"
    echo "(local test-mode magic links are captured by the API, not emailed)."
    ;;

  *)
    echo "Unknown service: $service" >&2
    exit 1
    ;;
esac
