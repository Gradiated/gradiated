#!/usr/bin/env bash
set -Eeuo pipefail
root=${UPSTREAM_REBASE_ROOT:?}
test "$(sudo docker inspect -f '{{.State.Running}}' gemma4-ngram-upstream-v0515)" = true
UPSTREAM_REBASE_ROOT="$root" UPSTREAM_REBASE_OUT="$root/out-endpoint" sudo -E python3 "$root/remote_v0515_endpoint.py"
