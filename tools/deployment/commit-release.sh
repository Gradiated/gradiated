#!/usr/bin/env bash
set -euo pipefail

if [[ ! "${SOURCE_SHA:-}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid release source SHA." >&2
  exit 1
fi
source_root="$(pwd -P)"
state_root="${RELEASE_STATE_ROOT:-$source_root}"
state_git() {
  git -C "$state_root" "$@"
}

if ! state_git diff --cached --quiet; then
  echo "Release checkout already has staged changes." >&2
  exit 1
fi

prefix="infra/"
if [[ -d "${state_root}/environments/prod/us-east-1/kubernetes/workloads" ]]; then
  prefix=""
fi

release_paths=(
  "${prefix}environments/prod/us-east-1/kubernetes/gpu-inference/controller.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/gpu-inference/gpu-fleet.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/kustomization.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/recovery/cronjobs.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/rollout-analysis.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/api.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/clickhouse-migrate.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/gateway.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/proxy.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/collector.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/worker.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/temporal-worker.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/workloads/mcp.yaml"
  "${prefix}environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml"
)
if state_git diff --quiet -- "${release_paths[@]}"; then
  echo "Release state already matches ${SOURCE_SHA}."
else
  state_git config user.name 'github-actions[bot]'
  state_git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
  state_git add -- "${release_paths[@]}"
  state_git commit -m "deploy(prod): release ${SOURCE_SHA:0:12} [skip ci]"

  for attempt in 1 2 3; do
    state_git fetch origin main
    if [[ "$state_root" != "$source_root" ]]; then
      git fetch origin main
    fi
    node tools/deployment/release-order.mjs "$SOURCE_SHA" --reject-stale
    state_git rebase origin/main
    if state_git push origin HEAD:refs/heads/main; then
      break
    fi
    if [[ "$attempt" == 3 ]]; then
      echo "Could not publish the release commit after three attempts." >&2
      exit 1
    fi
  done
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "release_commit=$(state_git rev-parse HEAD)" >>"$GITHUB_OUTPUT"
fi
