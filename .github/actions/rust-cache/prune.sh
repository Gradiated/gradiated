#!/usr/bin/env bash
set -euo pipefail

# Keep Cargo fingerprints, compiled dependencies, and build-script output. Remove
# only disposable incremental state and downloaded registry source checkouts;
# Cargo can extract those again from the retained .crate archives.
while IFS= read -r workspace; do
  [[ -n "$workspace" && -d "$workspace/target" ]] || continue
  find "$workspace/target" -type d -name incremental -prune -exec rm -rf -- {} +
done <<< "$WORKSPACES"
rm -rf -- "$HOME/.cargo/registry/src"
