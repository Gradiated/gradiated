#!/usr/bin/env bash
# Future-only cold-start candidate owner; no current invocation is authorized.
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
if [[ ${STREAMING_GLOBAL_KV_V7_FIXTURE:-} == lifecycle ]]; then
  python3 - "$0" <<'PY'
import json,pathlib,sys
source=pathlib.Path(sys.argv[1]).read_text()
required=(
 "claim_generation_must_come_from_atomic_claim",
 "atomic-claim.json",
 "CLAIM_GENERATION.json",
 "heartbeat_generation_changed",
 "--expected-claimed-at",
 "timeout --preserve-status",
 "server_live(){",
 "server_ready(){",
 "candidate_server_exited",
 "next_repair_id(){ local scope=$1; repair_id=",
)
missing=[item for item in required if item not in source]
if missing: raise SystemExit("fixture_missing:"+",".join(missing))
print(json.dumps({"fixture":"lifecycle","pure":True,"atomic_claim_generation":True,"heartbeat_generation":True,"release_generation":True,"loading_supervision":True,"bounded_children":True,"fresh_repair_ids":True},sort_keys=True))
PY
  exit 0
fi
binding=${STREAMING_GLOBAL_KV_EXECUTION_BINDING:?future_execution_binding_required}
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?artifact_root_required}
pool=(env PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab_dir")
repair=/root/workspace/research/factory/tools/repair-handshake
mkdir -p "$artifact_root"

python3 - "$binding" "$artifact_root/EXECUTION_BINDING.json" <<'PY'
import json,os,pathlib,sys
source,target=map(pathlib.Path,sys.argv[1:])
x=json.loads(source.read_text())
required=("project","bench_id","claim_generation_mode","release_by_utc","runtime_image","checkpoint","exact_runner","candidate_server_command","reservation")
if any(k not in x for k in required): raise RuntimeError("future_binding_missing_required_field")
if x["project"]!="gemma4_streaming_global_kv_memory_schedule": raise RuntimeError("future_binding_project_mismatch")
if x["claim_generation_mode"]!="from_atomic_claim" or "claim_generation" in x: raise RuntimeError("claim_generation_must_come_from_atomic_claim")
if x["checkpoint"].get("manifest_sha256")!="6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6": raise RuntimeError("checkpoint_manifest_mismatch")
if x["exact_runner"].get("sha256")!="143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7": raise RuntimeError("runner_mismatch")
if x["reservation"].get("authorized_usd",0)<8: raise RuntimeError("reservation_missing")
t=target.with_suffix(".part"); t.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n"); json.loads(t.read_text()); os.replace(t,target)
PY

readarray -t cfg < <(python3 - "$artifact_root/EXECUTION_BINDING.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
for value in (x["bench_id"],x["release_by_utc"],x["runtime_image"],x["checkpoint"]["local_root"],x["checkpoint"]["manifest"],x["exact_runner"]["path"],x["candidate_server_command"]): print(value)
PY
)
bench=${cfg[0]}; release_by=${cfg[1]}; image=${cfg[2]}; checkpoint_source=${cfg[3]}; checkpoint_manifest=${cfg[4]}; runner_source=${cfg[5]}; server_command=${cfg[6]}
deadline_epoch=$(date -u -d "$release_by" +%s)
remaining(){ local seconds=$((deadline_epoch-$(date -u +%s))); (( seconds > 0 )) || return 1; printf '%s\n' "$seconds"; }
bounded(){ local budget=$1; shift; local seconds; seconds=$(remaining) || return 124; (( budget < seconds )) && seconds=$budget; timeout --preserve-status --kill-after=5 "$seconds" "$@"; }
atomic_json(){ python3 - "$1" "$2" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); t=p.with_suffix(p.suffix+".part"); t.write_text(json.dumps(json.loads(sys.argv[2]),indent=2,sort_keys=True)+"\n"); json.loads(t.read_text()); os.replace(t,p)
PY
}

# Finish and verify the project-local immutable view before the atomic claim.
preclaim="$artifact_root/preclaim-inputs"
python3 - "$checkpoint_source" "$checkpoint_manifest" "$runner_source" "$preclaim" <<'PY'
import hashlib,json,os,pathlib,shutil,sys
source,manifest,runner,destination=map(pathlib.Path,sys.argv[1:]); spec=json.loads(manifest.read_text()); (destination/"checkpoint").mkdir(parents=True,exist_ok=True)
def materialize(src,dst,digest):
    if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest()==digest: return
    t=dst.with_suffix(dst.suffix+".part"); t.unlink(missing_ok=True)
    try: os.link(src,t)
    except OSError: shutil.copy2(src,t)
    if hashlib.sha256(t.read_bytes()).hexdigest()!=digest: raise RuntimeError("preclaim_hash_mismatch:"+src.name)
    os.chmod(t,0o444); os.replace(t,dst)
for item in spec["files"]: materialize(source/item["name"],destination/"checkpoint"/item["name"],item["sha256"])
materialize(runner,destination/"exact_runner.py","143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7")
materialize(manifest,destination/"CHECKPOINT_MANIFEST.json","6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6")
PY

bounded 90 "${pool[@]}" claim --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" >"$artifact_root/atomic-claim.json"
claimed_at=$(python3 - "$artifact_root/atomic-claim.json" "$bench" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
if x.get("id")!=sys.argv[2] or x.get("claim",{}).get("project")!="gemma4_streaming_global_kv_memory_schedule": raise RuntimeError("atomic_claim_response_mismatch")
print(x["claim"]["claimed_at"])
PY
)
atomic_json "$artifact_root/CLAIM_GENERATION.json" "{\"bench_id\":\"$bench\",\"claimed_at\":\"$claimed_at\",\"source\":\"atomic_claim_response\"}"
readarray -t ssh_cfg < <(python3 - "$artifact_root/atomic-claim.json" <<'PY'
import json,sys
for key in ("ssh_user","public_ipv4","ssh_identity_path","known_hosts_namespace"): print(json.load(open(sys.argv[1]))["resource"][key])
PY
)
user=${ssh_cfg[0]}; host=${ssh_cfg[1]}; key=${ssh_cfg[2]}; known=${ssh_cfg[3]}
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
remote=/home/glmrunner/streaming-global-kv-v7
stopping=0
heartbeat(){ while [[ $stopping == 0 ]]; do sleep 45; if bounded 25 "${pool[@]}" heartbeat --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" >"$artifact_root/heartbeat.json" 2>&1; then python3 - "$artifact_root/heartbeat.json" "$claimed_at" <<'PY'
import json,sys
if json.load(open(sys.argv[1]))["claim"]["claimed_at"]!=sys.argv[2]: raise RuntimeError("heartbeat_generation_changed")
PY
fi; done; }
heartbeat & heartbeat_pid=$!
trap 'stopping=1; kill "$heartbeat_pid" 2>/dev/null || true; wait "$heartbeat_pid" 2>/dev/null || true' EXIT
remote_run(){ bounded "$1" "${ssh[@]}" "$2"; }
stage(){ local source=$1 destination=$2 digest=$3; if ! remote_run 30 "test -f '$destination' && test $(sha256sum '$destination' | awk '{print $1}') = '$digest'"; then bounded 600 "${scp[@]}" "$source" "$user@$host:$destination.part"; remote_run 45 "test $(sha256sum '$destination.part' | awk '{print $1}') = '$digest' && chmod 0444 '$destination.part' && mv '$destination.part' '$destination'"; fi; }

remote_run 30 "install -d '$remote/input' '$remote/checkpoint' '$remote/out'"
while read -r name digest; do stage "$preclaim/checkpoint/$name" "$remote/checkpoint/$name" "$digest"; done < <(python3 - "$preclaim/CHECKPOINT_MANIFEST.json" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))["files"]: print(item["name"],item["sha256"])
PY
)
stage "$preclaim/exact_runner.py" "$remote/input/exact_runner.py" 143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7
for file in streaming_global_kv_endpoint_r3.py streaming_global_kv_sglang_hook.py streaming_global_kv_schedule.py inputs/activated_multiresolution_global_kv.py; do digest=$(sha256sum "$project_dir/$file"|awk '{print $1}'); stage "$project_dir/$file" "$remote/input/$(basename "$file")" "$digest"; done
remote_run 900 "sudo -n docker pull '$image'"
container=gemma4-streaming-global-kv-v7
repair_counter=0
next_repair_id(){ local scope=$1; repair_id="streaming-global-kv-v7-${scope}-${repair_counter}"; repair_counter=$((repair_counter+1)); }
repair_in_place(){ local scope=$1 kind=$2 diagnostic=$3; next_repair_id "$scope"; atomic_json "$artifact_root/REPAIR_${repair_counter}.json" "{\"repair_id\":\"$repair_id\",\"scope\":\"$scope\",\"predecessor_repair_id\":\"${previous_repair_id:-}\"}"; previous_repair_id=$repair_id; bounded 30 "$repair" ready --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --failure-kind "$kind" --diagnostic "$diagnostic" --retry-scope "$scope" >"$artifact_root/$repair_id.ready.json"; bounded 900 "$repair" wait --root "$artifact_root" --repair-id "$repair_id" --deadline "$release_by" --poll-seconds 15 >"$artifact_root/$repair_id.wait.json"; python3 - "$artifact_root/.repair-handshakes/$repair_id/REPAIR_REQUEST.json" "$scope" <<'PY'
import json,sys
if json.load(open(sys.argv[1])).get("retry_scope")!=sys.argv[2]: raise RuntimeError("repair_scope_mismatch")
PY
}
start_server(){ remote_run 180 "sudo -n docker rm -f '$container' >/dev/null 2>&1 || true; rm -f '$remote/out/activation.json'; sudo -n docker run -d --name '$container' --gpus all --ipc=host --network host -v '$remote/checkpoint:/work/checkpoint:ro' -v '$remote/input:/work/input:ro' -v '$remote/out:/work/out' -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python -e GLOBAL_KV_HOOK=1 -e GLOBAL_KV_TELEMETRY=/work/out/candidate-telemetry.jsonl -e GLOBAL_KV_DIAGNOSTIC=/work/out/hook-diagnostic.json -e GLOBAL_KV_ACTIVATION_CAPTURE=/work/out/activation.json '$image' python3 -c \"import streaming_global_kv_sglang_hook; import runpy; runpy.run_module('sglang.launch_server',run_name='__main__')\" $server_command"; }
server_live(){ remote_run 20 "sudo -n docker inspect --format '{{.State.Running}}' '$container'" | grep -qx true; }
server_ready(){ remote_run 20 "curl -fsS --max-time 10 http://127.0.0.1:30000/health >/dev/null && test -s '$remote/out/activation.json'"; }
start_server || repair_in_place server_launch candidate_server_launch_failed
while ! server_ready; do
  if ! server_live; then remote_run 60 "sudo -n docker logs '$container' >'$remote/out/server.failed.stdout' 2>'$remote/out/server.failed.stderr' || true" || true; repair_in_place server_launch candidate_server_exited; start_server; continue; fi
  remaining >/dev/null || { repair_in_place server_launch deadline_bounded_candidate_startup; exit 1; }
  sleep 5
done
run_endpoint(){ remote_run 1800 "STREAMING_GLOBAL_KV_OUTPUT_ROOT='$remote/out/endpoint-$1' STREAMING_GLOBAL_KV_EXACT_RUNNER='$remote/input/exact_runner.py' STREAMING_GLOBAL_KV_CANDIDATE_SERVER=1 GLOBAL_KV_TELEMETRY='$remote/out/candidate-telemetry.jsonl' GLOBAL_KV_ACTIVATION_CAPTURE='$remote/out/activation.json' python3 '$remote/input/streaming_global_kv_endpoint_r3.py'"; }
attempt=0
while ! run_endpoint "$attempt" >"$artifact_root/endpoint-$attempt.stdout" 2>"$artifact_root/endpoint-$attempt.stderr"; do remote_run 30 "if test -d '$remote/out/endpoint-$attempt'; then mv '$remote/out/endpoint-$attempt' '$remote/out/endpoint-$attempt.invalid-'$(date -u +%s); fi" || true; repair_in_place endpoint_only recoverable_endpoint_integration endpoint_exit_nonzero; attempt=$((attempt+1)); done
bounded 300 "${scp[@]}" -r "$user@$host:$remote/out/endpoint-$attempt" "$artifact_root/endpoint-final"
remote_run 120 "sudo -n docker logs '$container' >'$remote/out/server.stdout' 2>'$remote/out/server.stderr'; sudo -n docker rm -f '$container' >/dev/null"
bounded 30 "${pool[@]}" release --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" --expected-claimed-at "$claimed_at" --condition ready >"$artifact_root/release.json"
