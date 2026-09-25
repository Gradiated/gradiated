#!/usr/bin/env bash
# Shared environment for Cloud Agent product setup and services.
# Values mirror product/mprocs.yaml. All credentials here are local-only,
# non-secret development values and must never be used in production.

export PATH="$HOME/.local/bin:$PATH"

if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate bash)" 2>/dev/null || true
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT
export PRODUCT_DIR="${REPO_ROOT}/product"

export DATABASE_URL="postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated"
export VALKEY_URL="redis://127.0.0.1:6379"

export CLICKHOUSE_DATABASE="gradiated"
export CLICKHOUSE_HOST="127.0.0.1"
export CLICKHOUSE_PORT="8123"
export CLICKHOUSE_SECURE="false"
export CLICKHOUSE_USERNAME="gradiated"
export CLICKHOUSE_PASSWORD="gradiated"

# Admin/application/metabase roles used by the ClickHouse bootstrap migration.
export CLICKHOUSE_ADMIN_USERNAME="gradiated"
export CLICKHOUSE_ADMIN_PASSWORD="gradiated"
export CLICKHOUSE_APPLICATION_USERNAME="gradiated"
export CLICKHOUSE_APPLICATION_PASSWORD="gradiated"
export CLICKHOUSE_METABASE_USERNAME="metabase"
export CLICKHOUSE_METABASE_PASSWORD="metabase"

# API / auth (local test mode: magic links are captured, not emailed).
export AUTH_TEST_MODE="true"
export BETTER_AUTH_URL="http://localhost:3000"
export BETTER_AUTH_SECRET="local-only-not-secret-change-in-production-0001"
export TRUSTED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
export NODE_ENV="development"

# PostHog Development project public client token (from mprocs.yaml).
export VITE_POSTHOG_KEY="phc_umjFzXmQDsCr89BAGzpegeqe64WgrLuvEH9tvKB3qA2H"

mise_run() {
  if command -v mise >/dev/null 2>&1; then
    mise exec -- "$@"
  else
    "$@"
  fi
}
