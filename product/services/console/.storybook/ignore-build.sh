#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
baseline="${VERCEL_GIT_PREVIOUS_SHA:-}"
# New branches and shallow clones without the last deployment must build.
if [[ -z "$baseline" ]] || ! git cat-file -e "${baseline}^{commit}" 2>/dev/null; then
  exit 1
fi

git diff --quiet "$baseline" HEAD -- \
  product/services/console \
  product/packages/contracts \
  product/packages/analytics \
  product/package.json \
  product/pnpm-lock.yaml \
  product/pnpm-workspace.yaml \
  product/tsconfig.base.json \
  product/turbo.json \
  product/.npmrc \
  product/.nvmrc \
  mise.toml \
  ':!product/services/console/screenshots' \
  ':!**/*.md'
