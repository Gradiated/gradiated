#!/usr/bin/env bash
set -Eeuo pipefail

root=${STATIC_C32_REMOTE_ROOT:?}
artifacts="$root/artifacts"

# Earlier closed arms used this shared retained work directory. Their compact
# archives are already durable locally; remove only stage-local names before
# the unstarted stream-ordered component creates fresh evidence.
sudo rm -rf "$artifacts/component-supergraph.runner"
sudo rm -f "$artifacts/component-supergraph."{audit.jsonl,summary.json,runner.stdout,runner.stderr,server.log,server-failure.log,container-id,container-inspect.json,models.json,models.stderr,ring.jsonl,residual.jsonl,qkv.jsonl,modules.jsonl,consumers.jsonl,runtime.json}
sudo rm -f "$artifacts"/{INVOCATION_STATE.json,WORKER_TERMINAL.json,COMPONENT_RESULT.json,CANDIDATE_ENDPOINT_RESULT.json,gpu-final.csv,server-last.log,server-last.inspect.json}

exec bash "$root/input/remote_static_c32_supergraph.sh"
