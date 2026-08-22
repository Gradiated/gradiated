#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
image=${DESMOND_IMAGE:-gradiated/desmond-sglang:dev}

docker build \
  --file "$repo_root/product/inference/runtimes/sglang/Dockerfile" \
  --tag "$image" \
  "$repo_root/product/inference"
