#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
# Placeholder values validate syntax only. This command never submits the job.
docker run --rm --network none --entrypoint nomad -v "$root/jobs:/jobs:ro" \
  hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 \
  job validate \
  -var=bundle_url=https://example.invalid/bundle.tar.gz \
  -var=bundle_sha256=0000000000000000000000000000000000000000000000000000000000000000 \
  -var=deployment_id=00000000-0000-4000-8000-000000000001 \
  -var=runtime_revision=test-release -var=status_url=https://api.example.test/v1/deployment-status \
  -var=base_id=test-base-v1 -var=cpu_mhz=1000 -var=memory_mb=1024 -var=runtime_disk_mb=1024 \
  /jobs/deepseek-v4-1-flash.nomad.hcl
