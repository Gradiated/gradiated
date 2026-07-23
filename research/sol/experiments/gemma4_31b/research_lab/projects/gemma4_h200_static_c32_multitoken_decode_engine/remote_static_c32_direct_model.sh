#!/usr/bin/env bash
set -Eeuo pipefail

root=${STATIC_C32_REMOTE_ROOT:?}
if [[ ! -s "$root/artifacts/component-supergraph.summary.json" ]]; then
  sudo rm -rf "$root/artifacts/component-supergraph.runner"
fi
set +e
bash "$root/input/remote_static_c32_supergraph.sh"
rc=$?
set -e
blocker="$root/artifacts/DIRECT_MODEL_TOPOLOGY_BLOCKER.json"
if [[ "$rc" -ne 0 && -s "$blocker" ]]; then
  python3 - "$root/artifacts/WORKER_TERMINAL.json" "$blocker" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+".part")
b=json.load(open(sys.argv[2]))
x={
    "schema_version":2,
    "status":"terminal",
    "classification":"component_topology_reject_graph_memory_shortfall",
    "message":"exact c32 7/8/6 raw-forward parent graph exceeded retained H200 memory",
    "topology_blocker":b,
    "unix_s":time.time(),
}
q.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
os.replace(q,p)
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/static-c32-supergraph-compact.tar.gz" \
    -C "$root/artifacts" .
  sha256sum "$root/static-c32-supergraph-compact.tar.gz" \
    >"$root/static-c32-supergraph-compact.tar.gz.sha256"
  exit 0
fi
exit "$rc"
