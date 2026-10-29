#!/usr/bin/env bash
set -euo pipefail

if [[ ! "${SOURCE_SHA:-}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid release source SHA." >&2
  exit 1
fi
if ! git diff --cached --quiet; then
  echo "Release checkout already has staged changes." >&2
  exit 1
fi

release_paths=(
  infra/environments/prod/us-east-1/kubernetes/gpu-inference/controller.yaml
  infra/environments/prod/us-east-1/kubernetes/gpu-inference/gpu-fleet.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/kustomization.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/recovery/cronjobs.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/rollout-analysis.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/api.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/clickhouse-migrate.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/proxy.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/collector.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/worker.yaml
  infra/environments/prod/us-east-1/kubernetes/workloads/temporal-worker.yaml
  infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml
)
if git diff --quiet -- "${release_paths[@]}"; then
  echo "Release state already matches ${SOURCE_SHA}."
else
  git config user.name 'github-actions[bot]'
  git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
  git add -- "${release_paths[@]}"
  git commit -m "deploy(prod): release ${SOURCE_SHA:0:12} [skip ci]"

  for attempt in 1 2 3; do
    git fetch origin main
    node tools/deployment/release-order.mjs "$SOURCE_SHA" --reject-stale
    git rebase origin/main
    if git push origin HEAD:refs/heads/main; then
      break
    fi
    if [[ "$attempt" == 3 ]]; then
      echo "Could not publish the release commit after three attempts." >&2
      exit 1
    fi
  done
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "release_commit=$(git rev-parse HEAD)" >>"$GITHUB_OUTPUT"
fi
