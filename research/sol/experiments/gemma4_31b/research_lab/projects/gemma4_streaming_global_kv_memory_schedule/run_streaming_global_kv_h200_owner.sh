#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
factory_src=/root/workspace/research/factory/src
pool=(env "PYTHONPATH=$factory_src" python3 -m grad_research.gpu_pool --lab "$lab_dir")
repair=/root/workspace/research/factory/tools/repair-handshake
snapshot=/root/workspace/research/factory/tools/artifact-snapshot
project=gemma4_streaming_global_kv_memory_schedule
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?}
bench=${STREAMING_GLOBAL_KV_BENCH:?}
release_by=${STREAMING_GLOBAL_KV_RELEASE_BY_UTC:?}
image=${STREAMING_GLOBAL_KV_IMAGE:?}
endpoint_command=${STREAMING_GLOBAL_KV_ENDPOINT_COMMAND:?}
expected_claimed_at=${STREAMING_GLOBAL_KV_EXPECTED_CLAIMED_AT:?}
remote_root=${STREAMING_GLOBAL_KV_REMOTE_ROOT:-/home/glmrunner/streaming-global-kv}
mkdir -p "$artifact_root"

atomic_json() { python3 - "$1" "$2" <<'PY'
import json, os, pathlib, sys
path=pathlib.Path(sys.argv[1]); value=json.loads(sys.argv[2]); tmp=path.with_suffix(path.suffix+'.part')
tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); json.loads(tmp.read_text()); os.replace(tmp,path)
PY
}
progress() { atomic_json "$artifact_root/OWNER_PROGRESS.json" "{\"at_utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"phase\":\"$1\"}"; }
remaining() { python3 - "$release_by" <<'PY'
import datetime,sys
end=datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')); now=datetime.datetime.now(datetime.timezone.utc)
print(max(0,int((end-now).total_seconds())))
PY
}
repair_wait() {
  local kind=$1 diag=$2 scope=$3 repair_id="streaming-global-kv-${scope}-$(date -u +%Y%m%dt%H%M%Sz)"
  "$repair" ready --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --failure-kind "$kind" --diagnostic "$diag" --retry-scope "$scope" >"$artifact_root/repair-ready-${repair_id}.json"
  progress repair_ready
  "$repair" wait --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --poll-seconds 15 >"$artifact_root/repair-wait-${repair_id}.json" || return 1
}
terminal_release() {
  local classification=$1 condition=$2
  atomic_json "$artifact_root/TERMINAL.json" "{\"schema_version\":1,\"classification\":\"$classification\",\"released_at_utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"science_consumed\":true}"
  "${pool[@]}" show --bench "$bench" >"$artifact_root/pre-release-bench.json"
  observed_claimed_at=$(python3 - "$artifact_root/pre-release-bench.json" <<'PY'
import json,sys
print((json.load(open(sys.argv[1])).get('claim') or {}).get('claimed_at',''))
PY
)
  [[ $observed_claimed_at == "$expected_claimed_at" ]] || { progress generation_fence_mismatch; return 1; }
  "${pool[@]}" release --project "$project" --condition "$condition" --contents "$(printf '{\"schema_version\":1,\"project\":\"%s\",\"state\":\"terminal\",\"artifacts\":\"%s\"}' "$project" "$artifact_root")"
}

progress pre_claim
"${pool[@]}" claim --project "$project" --bench "$bench" >"$artifact_root/claim.json"
claimed=1
stop=0
heartbeat() { while [[ $stop == 0 ]]; do sleep 45; "${pool[@]}" heartbeat --project "$project" >"$artifact_root/heartbeat.json" 2>&1 || true; done; }
heartbeat & heartbeat_pid=$!
trap 'stop=1; wait "$heartbeat_pid" 2>/dev/null || true' EXIT
"${pool[@]}" show --bench "$bench" >"$artifact_root/bench.json"
readarray -t connection < <(python3 - "$artifact_root/bench.json" <<'PY'
import json,sys
b=json.load(open(sys.argv[1])); r=b['resource']; print(r['ssh_user']); print(r['public_ipv4']); print(r['ssh_identity_path']); print(r['known_hosts_namespace'])
PY
)
user=${connection[0]}; host=${connection[1]}; key=${connection[2]}; known=${connection[3]}
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
progress cold_bootstrap
"${ssh_cmd[@]}" "install -d '$remote_root/input' '$remote_root/out'"
for source in "$project_dir/streaming_global_kv_h200_runner.py" "$project_dir/streaming_global_kv_schedule.py" "$project_dir/inputs/activated_multiresolution_global_kv.py"; do
  name=$(basename "$source"); [[ $name == activated_multiresolution_global_kv.py ]] && name=multiresolution_global_kv.py
  sha=$(sha256sum "$source" | awk '{print $1}'); target="$remote_root/input/$name"
  if ! "${ssh_cmd[@]}" "test -f '$target' && test \$(sha256sum '$target' | awk '{print \$1}') = '$sha'"; then
    part="$target.$sha.part"; "${scp_cmd[@]}" "$source" "$user@$host:$part"
    "${ssh_cmd[@]}" "test \$(sha256sum '$part' | awk '{print \$1}') = '$sha' && chmod 0444 '$part' && mv '$part' '$target'"
  fi
done
progress cuda_discriminator
set +e
"${ssh_cmd[@]}" "sudo -n docker pull '$image' >/dev/null && sudo -n docker run --rm --gpus all --user \$(id -u):\$(id -g) -v '$remote_root/input:/work:ro' -v '$remote_root/out:/out' '$image' python3 /work/streaming_global_kv_h200_runner.py --output /out/CUDA_DISCRIMINATOR.json" >"$artifact_root/cuda.stdout" 2>"$artifact_root/cuda.stderr"
cuda_exit=$?
set -e
if [[ $cuda_exit != 0 ]]; then repair_wait recoverable_cuda_integration "cuda_discriminator_exit_$cuda_exit" cuda_discriminator || true; exit 1; fi
"${scp_cmd[@]}" "$user@$host:$remote_root/out/CUDA_DISCRIMINATOR.json" "$artifact_root/CUDA_DISCRIMINATOR.json"
python3 - "$artifact_root/CUDA_DISCRIMINATOR.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['gates_pass'] and x['endpoint_eligible']
PY
progress conditional_candidate_endpoint
set +e
"${ssh_cmd[@]}" "cd '$remote_root' && STREAMING_GLOBAL_KV_OUTPUT_ROOT='$remote_root/out/endpoint' $endpoint_command" >"$artifact_root/endpoint.stdout" 2>"$artifact_root/endpoint.stderr"
endpoint_exit=$?
set -e
if [[ $endpoint_exit != 0 ]]; then repair_wait recoverable_endpoint_integration "endpoint_exit_$endpoint_exit" endpoint_only || true; exit 1; fi
"${ssh_cmd[@]}" "test -s '$remote_root/out/endpoint/LAYER35_PASSAGE.json'" || { repair_wait recoverable_endpoint_observer "layer35_passage_missing" endpoint_only || true; exit 1; }
"${ssh_cmd[@]}" "cd '$remote_root' && tar -czf endpoint.tar.gz out && sha256sum endpoint.tar.gz" >"$artifact_root/retrieval.sha256"
"${scp_cmd[@]}" "$user@$host:$remote_root/endpoint.tar.gz" "$artifact_root/endpoint.tar.gz.part"
expected=$(awk '{print $1}' "$artifact_root/retrieval.sha256"); actual=$(sha256sum "$artifact_root/endpoint.tar.gz.part" | awk '{print $1}')
[[ $expected == "$actual" ]] || { repair_wait recoverable_retrieval_defect archive_hash retrieval_only || true; exit 1; }
mv "$artifact_root/endpoint.tar.gz.part" "$artifact_root/endpoint.tar.gz"
"$snapshot" --archive "$artifact_root/endpoint.tar.gz" --root "$artifact_root/snapshots" >"$artifact_root/artifact-snapshot.json"
terminal_release streamed_c32_memory_feasible_endpoint_measured ready
