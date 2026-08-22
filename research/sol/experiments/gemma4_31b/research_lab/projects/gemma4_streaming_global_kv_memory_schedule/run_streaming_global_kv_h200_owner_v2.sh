#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?}
bench=${STREAMING_GLOBAL_KV_BENCH:?}
pool=(env PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab_dir")
mkdir -p "$artifact_root"
"${pool[@]}" claim --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" >"$artifact_root/claim.json"
claimed_at=$(python3 - "$artifact_root/claim.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); print(x['claim']['claimed_at'])
PY
)
"${pool[@]}" show --bench "$bench" >"$artifact_root/bench-v2.json"
readarray -t conn < <(python3 - "$artifact_root/bench-v2.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))['resource']
print(r['ssh_user']); print(r['public_ipv4']); print(r['ssh_identity_path']); print(r['known_hosts_namespace'])
PY
)
user=${conn[0]}; host=${conn[1]}; key=${conn[2]}; known=${conn[3]}
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
remote=/home/glmrunner/streaming-global-kv
source="$project_dir/streaming_global_kv_endpoint.py"; hash=$(sha256sum "$source" | awk '{print $1}')
"${ssh[@]}" "install -d '$remote/input' && if test -f '$remote/input/streaming_global_kv_endpoint.py' && test \$(sha256sum '$remote/input/streaming_global_kv_endpoint.py' | awk '{print \$1}') = '$hash'; then exit 0; fi"
if ! "${ssh[@]}" "test -f '$remote/input/streaming_global_kv_endpoint.py' && test \$(sha256sum '$remote/input/streaming_global_kv_endpoint.py' | awk '{print \$1}') = '$hash'"; then
  "${scp[@]}" "$source" "$user@$host:$remote/input/streaming_global_kv_endpoint.py.$hash.part"
  "${ssh[@]}" "test \$(sha256sum '$remote/input/streaming_global_kv_endpoint.py.$hash.part' | awk '{print \$1}') = '$hash' && chmod 0444 '$remote/input/streaming_global_kv_endpoint.py.$hash.part' && mv '$remote/input/streaming_global_kv_endpoint.py.$hash.part' '$remote/input/streaming_global_kv_endpoint.py'"
fi
exec env STREAMING_GLOBAL_KV_EXPECTED_CLAIMED_AT="$claimed_at" bash "$project_dir/run_streaming_global_kv_h200_owner.sh"
