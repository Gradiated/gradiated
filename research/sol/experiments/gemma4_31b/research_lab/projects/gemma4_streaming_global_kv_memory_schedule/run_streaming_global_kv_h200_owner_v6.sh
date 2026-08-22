#!/usr/bin/env bash
# Future-only candidate owner; the later binding supplies every mutable bench value.
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
binding=${STREAMING_GLOBAL_KV_EXECUTION_BINDING:?future_execution_binding_required}
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?artifact_root_required}
pool=(env PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab_dir")
repair=/root/workspace/research/factory/tools/repair-handshake
mkdir -p "$artifact_root"

python3 - "$binding" "$artifact_root/EXECUTION_BINDING.json" <<'PY'
import json,os,pathlib,sys
source,target=map(pathlib.Path,sys.argv[1:])
x=json.loads(source.read_text())
required=('project','bench_id','claim_generation','release_by_utc','runtime_image','checkpoint','exact_runner','candidate_server_command','reservation')
if any(k not in x for k in required): raise RuntimeError('future_binding_missing_required_field')
if x['project']!='gemma4_streaming_global_kv_memory_schedule': raise RuntimeError('future_binding_project_mismatch')
if not x['runtime_image'].startswith('docker.io/lmsysorg/sglang@sha256:'): raise RuntimeError('future_binding_image_not_pinned')
if x['checkpoint'].get('manifest_sha256')!='6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6': raise RuntimeError('future_binding_checkpoint_identity_mismatch')
if x['exact_runner'].get('sha256')!='143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7': raise RuntimeError('future_binding_runner_identity_mismatch')
if x['reservation'].get('authorized_usd',0)<8: raise RuntimeError('future_binding_reservation_missing')
t=target.with_suffix('.part'); t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\\n'); json.loads(t.read_text()); os.replace(t,target)
PY

readarray -t cfg < <(python3 - "$artifact_root/EXECUTION_BINDING.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
for item in (x['bench_id'],x['claim_generation'],x['release_by_utc'],x['runtime_image'],x['checkpoint']['local_root'],x['checkpoint']['manifest'],x['exact_runner']['path'],x['candidate_server_command']): print(item)
PY
)
bench=${cfg[0]}; generation=${cfg[1]}; release_by=${cfg[2]}; image=${cfg[3]}; checkpoint_source=${cfg[4]}; checkpoint_manifest=${cfg[5]}; runner_source=${cfg[6]}; server_command=${cfg[7]}

# Build the immutable project-local view before the claim; post-claim staging never
# resolves the shared source path again.
preclaim="$artifact_root/preclaim-inputs"
python3 - "$checkpoint_source" "$checkpoint_manifest" "$runner_source" "$preclaim" <<'PY'
import hashlib,json,os,pathlib,shutil,sys
source,manifest,runner,destination=map(pathlib.Path,sys.argv[1:])
spec=json.loads(manifest.read_text()); (destination/'checkpoint').mkdir(parents=True,exist_ok=True)
def materialize(src,dst,digest):
    if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest()==digest: return
    t=dst.with_suffix(dst.suffix+'.part'); t.unlink(missing_ok=True)
    try: os.link(src,t)
    except OSError: shutil.copy2(src,t)
    if hashlib.sha256(t.read_bytes()).hexdigest()!=digest: raise RuntimeError('preclaim_hash_mismatch:'+src.name)
    os.chmod(t,0o444); os.replace(t,dst)
for item in spec['files']: materialize(source/item['name'],destination/'checkpoint'/item['name'],item['sha256'])
materialize(runner,destination/'exact_runner.py','143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7')
materialize(manifest,destination/'CHECKPOINT_MANIFEST.json','6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6')
PY

"${pool[@]}" claim --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" >"$artifact_root/claim.json"
"${pool[@]}" show --bench "$bench" >"$artifact_root/bench.json"
readarray -t ssh_cfg < <(python3 - "$artifact_root/bench.json" "$generation" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); c=x['claim']; r=x['resource']
if c['project']!='gemma4_streaming_global_kv_memory_schedule' or c['claimed_at']!=sys.argv[2]: raise RuntimeError('fresh_claim_generation_mismatch')
for k in ('ssh_user','public_ipv4','ssh_identity_path','known_hosts_namespace'): print(r[k])
PY
)
user=${ssh_cfg[0]}; host=${ssh_cfg[1]}; key=${ssh_cfg[2]}; known=${ssh_cfg[3]}
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
remote=/home/glmrunner/streaming-global-kv-v6
stopping=0
heartbeat(){ while [[ $stopping == 0 ]]; do sleep 45; "${pool[@]}" heartbeat --project gemma4_streaming_global_kv_memory_schedule >"$artifact_root/heartbeat.json" 2>&1 || true; done; }
heartbeat & heartbeat_pid=$!
trap 'stopping=1; kill "$heartbeat_pid" 2>/dev/null || true; wait "$heartbeat_pid" 2>/dev/null || true' EXIT

"${ssh[@]}" "install -d '$remote/input' '$remote/checkpoint' '$remote/out'"
stage(){ local source=$1 destination=$2 digest=$3; if ! "${ssh[@]}" "test -f '$destination' && test \$(sha256sum '$destination' | awk '{print \$1}') = '$digest'"; then "${scp[@]}" "$source" "$user@$host:$destination.part"; "${ssh[@]}" "test \$(sha256sum '$destination.part' | awk '{print \$1}') = '$digest' && chmod 0444 '$destination.part' && mv '$destination.part' '$destination'"; fi; }
while read -r name digest; do stage "$preclaim/checkpoint/$name" "$remote/checkpoint/$name" "$digest"; done < <(python3 - "$preclaim/CHECKPOINT_MANIFEST.json" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))['files']: print(item['name'],item['sha256'])
PY
)
stage "$preclaim/exact_runner.py" "$remote/input/exact_runner.py" 143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7
for file in streaming_global_kv_endpoint_r3.py streaming_global_kv_sglang_hook.py streaming_global_kv_schedule.py inputs/activated_multiresolution_global_kv.py; do digest=$(sha256sum "$project_dir/$file" | awk '{print $1}'); stage "$project_dir/$file" "$remote/input/$(basename "$file")" "$digest"; done
"${ssh[@]}" "sudo -n docker pull '$image'"
container=gemma4-streaming-global-kv-v6
python3 - "$artifact_root/LAUNCH_CAPTURE.json" "$image" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); t=p.with_suffix('.part'); t.write_text(json.dumps({'runtime_image':sys.argv[2],'candidate_path':'u8_streamed'},indent=2,sort_keys=True)+'\\n'); os.replace(t,p)
PY
start_server(){ "${ssh[@]}" "sudo -n docker rm -f '$container' >/dev/null 2>&1 || true; rm -f '$remote/out/activation.json'; sudo -n docker run -d --name '$container' --gpus all --ipc=host --network host -v '$remote/checkpoint:/work/checkpoint:ro' -v '$remote/input:/work/input:ro' -v '$remote/out:/work/out' -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python -e GLOBAL_KV_HOOK=1 -e GLOBAL_KV_TELEMETRY=/work/out/candidate-telemetry.jsonl -e GLOBAL_KV_DIAGNOSTIC=/work/out/hook-diagnostic.json -e GLOBAL_KV_ACTIVATION_CAPTURE=/work/out/activation.json '$image' python3 -c \"import streaming_global_kv_sglang_hook; import runpy; runpy.run_module('sglang.launch_server',run_name='__main__')\" $server_command"; }
start_server || true
deadline=$(date -u -d "$release_by" +%s)
while ! "${ssh[@]}" "curl -fsS --max-time 10 http://127.0.0.1:30000/health >/dev/null && test -s '$remote/out/activation.json'"; do
  [[ $(date -u +%s) -lt $deadline ]] || { "$repair" ready --root "$artifact_root" --repair-id fresh-server-deadline --deadline "$release_by" --failure-kind deadline_bounded_candidate_startup --diagnostic health_or_activation_capture_missing --retry-scope server_launch; exit 1; }
  "$repair" ready --root "$artifact_root" --repair-id fresh-server --deadline "$release_by" --failure-kind candidate_server_startup --diagnostic health_or_activation_capture_missing --retry-scope server_launch >"$artifact_root/server-repair-ready.json"
  "$repair" wait --root "$artifact_root" --repair-id fresh-server --deadline "$release_by" --poll-seconds 15 >"$artifact_root/server-repair-wait.json"
  python3 - "$artifact_root/.repair-handshakes/fresh-server/REPAIR_REQUEST.json" <<'PY'
import json,sys
if json.load(open(sys.argv[1])).get('retry_scope')!='server_launch': raise RuntimeError('repair_scope_not_server_launch')
PY
  start_server || true
done
run_endpoint(){ "${ssh[@]}" "STREAMING_GLOBAL_KV_OUTPUT_ROOT='$remote/out/endpoint-$1' STREAMING_GLOBAL_KV_EXACT_RUNNER='$remote/input/exact_runner.py' STREAMING_GLOBAL_KV_CANDIDATE_SERVER=1 GLOBAL_KV_TELEMETRY='$remote/out/candidate-telemetry.jsonl' GLOBAL_KV_ACTIVATION_CAPTURE='$remote/out/activation.json' python3 '$remote/input/streaming_global_kv_endpoint_r3.py'"; }
attempt=0
while ! run_endpoint "$attempt" >"$artifact_root/endpoint-$attempt.stdout" 2>"$artifact_root/endpoint-$attempt.stderr"; do "${ssh[@]}" "if test -d '$remote/out/endpoint-$attempt'; then mv '$remote/out/endpoint-$attempt' '$remote/out/endpoint-$attempt.invalid-'\$(date -u +%s); fi"; repair_id="fresh-endpoint-$attempt"; "$repair" ready --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --failure-kind recoverable_endpoint_integration --diagnostic endpoint_exit_nonzero --retry-scope endpoint_only >"$artifact_root/repair-ready-$attempt.json"; "$repair" wait --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --poll-seconds 15 >"$artifact_root/repair-wait-$attempt.json"; python3 - "$artifact_root/.repair-handshakes/$repair_id/REPAIR_REQUEST.json" <<'PY'
import json,sys
if json.load(open(sys.argv[1])).get('retry_scope')!='endpoint_only': raise RuntimeError('repair_scope_not_endpoint_only')
PY
attempt=$((attempt+1)); done
"${scp[@]}" -r "$user@$host:$remote/out/endpoint-$attempt" "$artifact_root/endpoint-final"
"${ssh[@]}" "sudo -n docker logs '$container' >'$remote/out/server.stdout' 2>'$remote/out/server.stderr'; sudo -n docker rm -f '$container' >/dev/null"
"${pool[@]}" show --bench "$bench" >"$artifact_root/pre-release.json"
python3 - "$artifact_root/pre-release.json" "$generation" <<'PY'
import json,sys
if json.load(open(sys.argv[1]))['claim']['claimed_at']!=sys.argv[2]: raise RuntimeError('release_generation_mismatch')
PY
"${pool[@]}" release --project gemma4_streaming_global_kv_memory_schedule --condition ready
