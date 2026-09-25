#!/usr/bin/env bash
# Idempotent Cloud Agent install: pinned toolchains, product dependencies and
# the shared TypeScript packages the api/worker processes import at runtime.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/cloud-env.sh"

cd "${REPO_ROOT}"

mise trust --yes >/dev/null 2>&1 || true
mise install

cd "${PRODUCT_DIR}"
mise exec -- pnpm install --frozen-lockfile

# The api and worker dev processes import @gradiated/control from its built
# dist output, which in turn needs config, contracts and valkey compiled.
mise exec -- pnpm --filter './packages/*' build

echo "Cloud Agent install complete."
