#!/usr/bin/env bash
set -eu

: "${DEPLOYMENT_ID:?DEPLOYMENT_ID is required}"
: "${RUNTIME_PORT:?RUNTIME_PORT is required}"
: "${RUNTIME_REVISION:?RUNTIME_REVISION is required}"
: "${STATUS_TOKEN_FILE:?STATUS_TOKEN_FILE is required}"
: "${STATUS_URL:?STATUS_URL is required}"

MAXIMUM_CONCURRENCY="${MAXIMUM_CONCURRENCY:-4}"
KV_USAGE_LIMIT="${KV_USAGE_LIMIT:-0.90}"

status_header_file="/run/gradiated-status-${DEPLOYMENT_ID}-$$.header"
umask 077
printf 'Authorization: Bearer %s\n' "$(cat "${STATUS_TOKEN_FILE}")" > "${status_header_file}"
trap 'rm -f "${status_header_file}"' EXIT
trap 'exit 0' INT TERM

metric_value() {
  metric_name="$1"
  awk -v metric="${metric_name}" '
    $1 ~ ("^" metric "(\\{|$)") { value = $NF }
    END { print value + 0 }
  '
}

at_or_above() {
  awk -v value="$1" -v limit="$2" 'BEGIN { exit !(value >= limit) }'
}

while true; do
  healthy=false
  accepting_requests=false
  reason_code=runtime_unhealthy
  metrics=""

  if curl --fail --silent --max-time 0.5 \
      "http://127.0.0.1:${RUNTIME_PORT}/health" > /dev/null && \
    metrics="$(curl --fail --silent --max-time 0.5 \
      "http://127.0.0.1:${RUNTIME_PORT}/metrics")"; then
    healthy=true
    accepting_requests=true
    reason_code=""

    running_requests="$(printf '%s\n' "${metrics}" | metric_value 'vllm:num_requests_running')"
    waiting_requests="$(printf '%s\n' "${metrics}" | metric_value 'vllm:num_requests_waiting')"
    kv_usage="$(printf '%s\n' "${metrics}" | metric_value 'vllm:kv_cache_usage_perc')"

    if at_or_above "${waiting_requests}" 1; then
      accepting_requests=false
      reason_code=waiting_requests
    elif at_or_above "${running_requests}" "${MAXIMUM_CONCURRENCY}"; then
      accepting_requests=false
      reason_code=concurrency_full
    elif at_or_above "${kv_usage}" "${KV_USAGE_LIMIT}"; then
      accepting_requests=false
      reason_code=kv_pressure
    fi
  fi

  body="$(jq -cn \
    --arg deployment_id "${DEPLOYMENT_ID}" \
    --arg runtime_revision "${RUNTIME_REVISION}" \
    --argjson healthy "${healthy}" \
    --argjson accepting_requests "${accepting_requests}" \
    --argjson maximum_concurrency "${MAXIMUM_CONCURRENCY}" \
    --arg reason_code "${reason_code}" \
    '{
      schema_version: 1,
      deployment_id: $deployment_id,
      runtime_revision: $runtime_revision,
      healthy: $healthy,
      accepting_requests: $accepting_requests,
      maximum_concurrency: $maximum_concurrency,
      reason_code: (if $reason_code == "" then null else $reason_code end)
    }')"

  if ! curl --fail --silent --show-error --max-time 3 \
      --output /dev/null \
      --request POST \
      --header @"${status_header_file}" \
      --header 'Content-Type: application/json' \
      --data "${body}" \
      "${STATUS_URL}"; then
    printf 'deployment status upload failed for %s\n' "${DEPLOYMENT_ID}" >&2
  fi

  sleep 1
done
