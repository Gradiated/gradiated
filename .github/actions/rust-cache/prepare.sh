#!/usr/bin/env bash
set -euo pipefail
mapfile -t workspaces < <(printf '%s\n' "$WORKSPACES" | sed '/^$/d')
# Tree IDs cover all tracked build inputs, including build-script assets,
# without changing for unrelated commits or generated target files.
sources=$(for workspace in "${workspaces[@]}"; do git rev-parse "HEAD:$workspace" || exit 1; done | sha256sum | cut -d' ' -f1)
toolchain=$(rustc -vV | sha256sum | cut -d' ' -f1)
prefix="${RUNNER_OS}-${RUNNER_ARCH}-rust-v3-${SCOPE}-${toolchain}-${CONFIG_HASH}"
{
  echo "key=${prefix}-${sources}"
  echo "prefix=${prefix}-"
  echo 'paths<<RUST_CACHE_PATHS'
  echo ~/.cargo/registry
  echo ~/.cargo/git
  printf '%s/target\n' "${workspaces[@]}"
  echo RUST_CACHE_PATHS
} >> "$GITHUB_OUTPUT"
# Incremental state is large and tied to a particular checkout. Retain
# compiled dependencies while avoiding this per-build cache growth.
if [[ "$MODE" == restore ]]; then
  echo 'CARGO_INCREMENTAL=0' >> "$GITHUB_ENV"
fi
