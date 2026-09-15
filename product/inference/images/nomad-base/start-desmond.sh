#!/usr/bin/env bash
set -euo pipefail
# Enrollment installs a provider-scoped token readable only by the Desmond user.
# Never put the token in job variables, allocation metadata or the runtime environment.
: "${DESMOND_DEPLOYMENT_ID:?deployment registration is required}"
: "${DESMOND_RELEASE:?runtime revision is required}"
: "${DESMOND_MODEL:?model identity is required}"
: "${DESMOND_MAXIMUM_CONCURRENCY:?capacity is required}"
: "${DESMOND_STATUS_URL:?status endpoint is required}"
: "${DESMOND_CONTROL_TOKEN_FILE:?runtime access token file is required}"
: "${DESMOND_STATUS_TOKEN_FILE:?status token file is required}"
[[ "$DESMOND_STATUS_URL" == https://* ]] || {
  echo 'Desmond status endpoint must use HTTPS' >&2
  exit 64
}
[[ -s "$DESMOND_STATUS_TOKEN_FILE" && -r "$DESMOND_STATUS_TOKEN_FILE" ]] || {
  echo 'Desmond status token is unavailable' >&2
  exit 64
}
[[ -s "$DESMOND_CONTROL_TOKEN_FILE" && -r "$DESMOND_CONTROL_TOKEN_FILE" ]] || {
  echo 'Desmond runtime access token is unavailable' >&2
  exit 64
}
exec /opt/gradiated/bin/desmondd --observe
