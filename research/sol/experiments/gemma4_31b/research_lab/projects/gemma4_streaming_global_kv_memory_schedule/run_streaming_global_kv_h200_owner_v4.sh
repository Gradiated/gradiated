#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?}
bench=${STREAMING_GLOBAL_KV_BENCH:?}
expected=${STREAMING_GLOBAL_KV_EXPECTED_CLAIMED_AT:?}
release_by=${STREAMING_GLOBAL_KV_RELEASE_BY_UTC:?}
image=${STREAMING_GLOBAL_KV_IMAGE:?}
endpoint=${STREAMING_GLOBAL_KV_ENDPOINT_COMMAND:?}
pool=(env PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab_dir")
repair=/root/workspace/research/factory/tools/repair-handshake
runner="$project_dir/streaming_global_kv_h200_runner_r2.py"
runner_hash=$(sha256sum "$runner" | awk '{print $1}')
patch="$project_dir/STREAMING_GLOBAL_KV_R2_PATCH.json"
patch_hash=$(sha256sum "$patch" | awk '{print $1}')

"${pool[@]}" show --bench "$bench" >"$artifact_root/r2-bench.json"
readarray -t connection < <(python3 - "$artifact_root/r2-bench.json" "$expected" <<'PY'
import json,sys
row=json.load(open(sys.argv[1])); claim=row['claim']
assert claim['claimed_at'] == sys.argv[2]
assert claim['project'] == 'gemma4_streaming_global_kv_memory_schedule'
resource=row['resource']
for name in ('ssh_user','public_ipv4','ssh_identity_path','known_hosts_namespace'):
 print(resource[name])
PY
)
user=${connection[0]}; host=${connection[1]}; key=${connection[2]}; known=${connection[3]}
remote=/home/glmrunner/streaming-global-kv
remote_runner="streaming_global_kv_h200_runner_r2.${runner_hash}.py"
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")

stopping=0
heartbeat() {
  while [[ $stopping == 0 ]]; do
    sleep 45
    "${pool[@]}" heartbeat --project gemma4_streaming_global_kv_memory_schedule >"$artifact_root/heartbeat-r2.json" 2>&1 || true
  done
}
heartbeat &
heartbeat_pid=$!
cleanup() {
  stopping=1
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
}
trap cleanup EXIT

"${ssh[@]}" "install -d '$remote/input' '$remote/out/triton-cache' '$remote/out/xdg-cache'"
if ! "${ssh[@]}" "test -f '$remote/input/$remote_runner' && test \$(sha256sum '$remote/input/$remote_runner' | awk '{print \$1}') = '$runner_hash'"; then
  "${scp[@]}" "$runner" "$user@$host:$remote/input/$remote_runner.part"
  "${ssh[@]}" "test \$(sha256sum '$remote/input/$remote_runner.part' | awk '{print \$1}') = '$runner_hash' && chmod 0444 '$remote/input/$remote_runner.part' && mv '$remote/input/$remote_runner.part' '$remote/input/$remote_runner'"
fi
"${ssh[@]}" "test \$(sha256sum '$remote/input/multiresolution_global_kv.py' | awk '{print \$1}') = '47c1dd902dd287cab2403cb06790095a3e041df434e48ffe22832dfdad4d4880' && test \$(sha256sum '$remote/input/streaming_global_kv_schedule.py' | awk '{print \$1}') = '636cc6e683d04f8950ce288f567ed5411a8d3cbb667b92329827c9bc6d35a23a'"
python3 - "$artifact_root/R2_REMOTE_RUNNER.json" "$runner_hash" "$patch_hash" "$remote_runner" <<'PY'
import json,os,sys
path=sys.argv[1]; temporary=path+'.part'
json.dump({'runner_sha256':sys.argv[2],'patch_sha256':sys.argv[3],'remote_runner':sys.argv[4]},open(temporary,'w'),sort_keys=True,indent=2)
json.load(open(temporary)); os.replace(temporary,path)
PY

run_cuda() {
  local generation=$1
  local remote_output="CUDA_DISCRIMINATOR_R2_${generation}.json"
  local local_output="$artifact_root/$remote_output"
  set +e
  "${ssh[@]}" "sudo -n docker run --rm --gpus all --user \$(id -u):\$(id -g) -e TRITON_CACHE_DIR=/out/triton-cache -e XDG_CACHE_HOME=/out/xdg-cache -v '$remote/input:/work:ro' -v '$remote/out:/out' '$image' python3 /work/$remote_runner --output /out/$remote_output" >"$artifact_root/cuda-r2-${generation}.stdout" 2>"$artifact_root/cuda-r2-${generation}.stderr"
  local code=$?
  set -e
  if [[ $code -ne 0 ]]; then return "$code"; fi
  "${scp[@]}" "$user@$host:$remote/out/$remote_output" "$local_output"
  python3 - "$local_output" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['gates_pass'] and x['endpoint_eligible']
assert x['correctness_c26_q1']['compact_entries'] == 26
assert [row['compact_entries'] for row in x['boundaries']] == [64,64]
PY
}

attempt=0
while true; do
  generation="attempt${attempt}"
  if run_cuda "$generation"; then break; fi
  repair_id="streaming-global-kv-r2-cuda-discriminator-${attempt}"
  "$repair" ready --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --failure-kind recoverable_cuda_integration --diagnostic "cuda_r2_${generation}_failed" --retry-scope cuda_discriminator >"$artifact_root/repair-ready-r2-${attempt}.json"
  "$repair" wait --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --poll-seconds 15 >"$artifact_root/repair-wait-r2-${attempt}.json" || exit 1
  python3 - "$artifact_root/.repair-handshakes/$repair_id/REPAIR_REQUEST.json" "$patch_hash" "$artifact_root/repair-request-r2-${attempt}.json" <<'PY'
import hashlib,json,os,pathlib,sys
request=pathlib.Path(sys.argv[1]); expected=sys.argv[2]; output=pathlib.Path(sys.argv[3])
x=json.loads(request.read_text()); patch=pathlib.Path(x['patch_artifact'])
if hashlib.sha256(patch.read_bytes()).hexdigest() != expected: raise RuntimeError('repair_patch_hash_mismatch')
temporary=output.with_suffix(output.suffix+'.part'); temporary.write_text(json.dumps(x,sort_keys=True,indent=2)); json.loads(temporary.read_text()); os.replace(temporary,output)
PY
  attempt=$((attempt + 1))
done

set +e
"${ssh[@]}" "cd '$remote' && STREAMING_GLOBAL_KV_OUTPUT_ROOT='$remote/out/endpoint-r2' $endpoint" >"$artifact_root/endpoint-r2.stdout" 2>"$artifact_root/endpoint-r2.stderr"
endpoint_code=$?
set -e
if [[ $endpoint_code -ne 0 ]]; then
  "$repair" ready --root "$artifact_root" --repair-id streaming-global-kv-r2-endpoint-0 --deadline "$release_by" --failure-kind recoverable_endpoint_integration --diagnostic "endpoint_r2_exit_${endpoint_code}" --retry-scope endpoint_only >"$artifact_root/repair-ready-r2-endpoint.json"
  "$repair" wait --root "$artifact_root" --repair-id streaming-global-kv-r2-endpoint-0 --deadline "$release_by" --poll-seconds 15 >"$artifact_root/repair-wait-r2-endpoint.json" || exit 1
  exit 1
fi
"${pool[@]}" show --bench "$bench" >"$artifact_root/pre-release-r2.json"
python3 - "$artifact_root/pre-release-r2.json" "$expected" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['claim']['claimed_at'] == sys.argv[2]
PY
"${pool[@]}" release --project gemma4_streaming_global_kv_memory_schedule --condition ready
