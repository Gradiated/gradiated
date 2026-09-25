#!/usr/bin/env bash
# Per-boot Cloud Agent entrypoint (environment `start`). Brings up the
# datastores and migrations, then launches the product services in the
# background so a booted agent has the full stack running. Idempotent: it
# will not start a second copy of a service that is already running.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/cloud-env.sh"

bash "${SCRIPT_DIR}/cloud-start.sh"

LOG_DIR="/tmp/cloud-services"
mkdir -p "${LOG_DIR}"

launch() {
  local name="$1"
  if pgrep -f "cloud-service.sh ${name}\b" >/dev/null 2>&1; then
    echo "Service ${name} already running."
    return 0
  fi

  setsid bash "${SCRIPT_DIR}/cloud-service.sh" "${name}" \
    >"${LOG_DIR}/${name}.log" 2>&1 </dev/null &
  echo "Launched ${name} (logs: ${LOG_DIR}/${name}.log)."
}

launch api
launch worker
launch gateway
launch console
launch seed

echo "Product stack starting. Console: http://localhost:3000  API: http://localhost:3001  Gateway: http://localhost:3002"
