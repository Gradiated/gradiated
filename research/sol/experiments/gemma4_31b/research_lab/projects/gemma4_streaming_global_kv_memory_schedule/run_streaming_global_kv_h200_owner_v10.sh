#!/usr/bin/env bash
# Derived only from v9.  V10 is a same-claim staging repair: it never claims.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
binding=${STREAMING_GLOBAL_KV_EXECUTION_BINDING:?}
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?}
expected_claimed_at=${STREAMING_GLOBAL_KV_EXPECTED_CLAIMED_AT:?}
pool=(env PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab_dir")
repair=/root/workspace/research/factory/tools/repair-handshake
mkdir -p "$artifact_root"
python3 - "$binding" "$project_dir" "$artifact_root/EXECUTION_BINDING.json" <<'PY'
import hashlib,json,os,pathlib,sys
binding,root,out=map(pathlib.Path,sys.argv[1:]); x=json.loads(binding.read_text())
for k in ('bench_id','expected_claimed_at_utc','source_execution_binding','source_owner','repair_evidence','deadlines','immutable_science','replacement'):
 if k not in x: raise RuntimeError('v10_binding_missing_'+k)
if x['expected_claimed_at_utc'] != os.environ['STREAMING_GLOBAL_KV_EXPECTED_CLAIMED_AT']: raise RuntimeError('claim_generation')
if x['source_owner']['sha256'] != hashlib.sha256((root/x['source_owner']['path']).read_bytes()).hexdigest(): raise RuntimeError('v9_owner_hash')
src=root/x['source_execution_binding']['path']
if hashlib.sha256(src.read_bytes()).hexdigest()!=x['source_execution_binding']['sha256']: raise RuntimeError('v9_binding_hash')
y=json.loads(src.read_text()); y['release_by_utc']=x['deadlines']['release_by_utc']; y['staging_complete_by_utc']=x['deadlines']['checkpoint_integrity_by_utc']; y['server_ready_by_utc']=x['deadlines']['candidate_server_ready_by_utc']
t=out.with_suffix('.part'); t.write_text(json.dumps(y,sort_keys=True,indent=2)+'\n'); json.loads(t.read_text()); os.replace(t,out)
PY
readarray -t c < <(python3 - "$artifact_root/EXECUTION_BINDING.json" "$binding" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); v=json.load(open(sys.argv[2]))
for q in (x['bench_id'],x['release_by_utc'],x['staging_complete_by_utc'],x['server_ready_by_utc'],x['runtime_image'],x['checkpoint']['local_root'],x['checkpoint']['manifest'],x['exact_runner']['path'],x['candidate_server_command'],v['repair_evidence']['repair_id']): print(q)
PY
)
bench=${c[0]}; release_by=${c[1]}; staging_by=${c[2]}; server_by=${c[3]}; image=${c[4]}; checkpoint_source=${c[5]}; checkpoint_manifest=${c[6]}; runner_source=${c[7]}; server_command=${c[8]}; predecessor_repair=${c[9]}
epoch(){ date -u -d "$1" +%s; }
release_epoch=$(epoch "$release_by"); stage_epoch=$(epoch "$staging_by"); server_epoch=$(epoch "$server_by")
left(){ local end=$1 n=$((end-$(date -u +%s))); ((n>0)) || return 1; printf '%s\n' "$n"; }
bounded(){ local end=$1 cap=$2; shift 2; local n; n=$(left "$end") || return 124; ((cap<n))&&n=$cap; timeout --preserve-status --kill-after=5 "$n" "$@"; }
# Same-claim adoption occurs before any guest mutation; no pool claim is legal here.
bounded "$release_epoch" 30 "${pool[@]}" show --bench "$bench" >"$artifact_root/same-claim.json"
readarray -t ssh_cfg < <(python3 - "$artifact_root/same-claim.json" "$expected_claimed_at" "$bench" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); e=sys.argv[2]; b=sys.argv[3]; c=x.get('claim') or {}
assert x['id']==b and x['status']=='claimed'
assert c.get('project')=='gemma4_streaming_global_kv_memory_schedule' and c.get('claimed_at')==e and not c.get('stale')
r=x['resource']
for k in ('ssh_user','public_ipv4','ssh_identity_path','known_hosts_namespace'): print(r[k])
PY
)
claimed_at=$expected_claimed_at
python3 - "$artifact_root/CLAIM_GENERATION.json" "$bench" "$claimed_at" "$predecessor_repair" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); t=p.with_suffix('.part'); t.write_text(json.dumps({'bench_id':sys.argv[2],'claimed_at':sys.argv[3],'source':'same_claim_replacement','predecessor_repair_id':sys.argv[4]},sort_keys=True,indent=2)+'\n'); os.replace(t,p)
PY
user=${ssh_cfg[0]};host=${ssh_cfg[1]};key=${ssh_cfg[2]};known=${ssh_cfg[3]}
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
stopping=0
heartbeat(){ while [[ $stopping == 0 ]];do sleep 45;if bounded "$release_epoch" 20 "${pool[@]}" heartbeat --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" >"$artifact_root/heartbeat.json" 2>&1;then python3 - "$artifact_root/heartbeat.json" "$claimed_at" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['claim']['claimed_at']==sys.argv[2]
PY
fi;done;}
heartbeat & hb=$!
trap 'stopping=1;kill "$hb" 2>/dev/null||true;wait "$hb" 2>/dev/null||true' EXIT
remote=/home/glmrunner/streaming-global-kv-v9
# Both -n and stdin redirection protect manifest-loop input from remote probes.
remote_run(){ bounded "$release_epoch" "$1" "${ssh[@]}" -n "$2" </dev/null; }
repair_no=0
retain(){ local scope=$1 why=$2 id="streaming-global-kv-v10-${scope}-${repair_no}"; repair_no=$((repair_no+1)); "$repair" ready --root "$artifact_root" --repair-id "$id" --deadline "$release_by" --failure-kind recoverable_post_claim --diagnostic "$why" --retry-scope "$scope" >"$artifact_root/$id.ready.json"; bounded "$release_epoch" 600 "$repair" wait --root "$artifact_root" --repair-id "$id" --deadline "$release_by" --poll-seconds 15 >"$artifact_root/$id.wait.json"; }
preclaim="$artifact_root/preclaim-inputs"
python3 - "$checkpoint_source" "$checkpoint_manifest" "$runner_source" "$preclaim" <<'PY'
import hashlib,json,os,pathlib,shutil,sys
source,manifest,runner,dest=map(pathlib.Path,sys.argv[1:]); spec=json.loads(manifest.read_text()); (dest/'checkpoint').mkdir(parents=True,exist_ok=True)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def admit(src,dst,want):
 if dst.exists() and digest(dst)==want:return
 t=dst.with_suffix(dst.suffix+'.part'); t.unlink(missing_ok=True)
 try:os.link(src,t)
 except OSError:shutil.copy2(src,t)
 if digest(t)!=want:raise RuntimeError('local_hash:'+src.name)
 os.chmod(t,0o444);os.replace(t,dst)
for f in spec['files']:admit(source/f['name'],dest/'checkpoint'/f['name'],f['sha256'])
admit(runner,dest/'exact_runner.py','143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7');admit(manifest,dest/'CHECKPOINT_MANIFEST.json','6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6')
PY
guest_hash(){ local path=$1 want=$2; remote_run 60 "python3 - '$path' '$want' <<'PY'
import hashlib,sys
h=hashlib.sha256()
with open(sys.argv[1],'rb') as f:
 for b in iter(lambda:f.read(1048576),b''):h.update(b)
raise SystemExit(0 if h.hexdigest()==sys.argv[2] else 1)
PY"; }
stage(){ local src=$1 dst=$2 sha=$3; while ! guest_hash "$dst" "$sha";do if ! bounded "$release_epoch" 600 "${scp[@]}" "$src" "$user@$host:$dst.part" </dev/null;then retain staging_failure scp_failed;continue;fi;if ! remote_run 60 "mv '$dst.part' '$dst' && chmod 0444 '$dst'";then retain staging_failure finalize_failed;fi;done; }
while ! remote_run 30 "install -d '$remote/input' '$remote/checkpoint' '$remote/out'";do retain staging_failure remote_directory_failed;done
while read -r name sha;do stage "$preclaim/checkpoint/$name" "$remote/checkpoint/$name" "$sha";done < <(python3 - "$preclaim/CHECKPOINT_MANIFEST.json" <<'PY'
import json,sys
for f in json.load(open(sys.argv[1]))['files']:print(f['name'],f['sha256'])
PY
)
stage "$preclaim/exact_runner.py" "$remote/input/exact_runner.py" 143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7
stage "$preclaim/CHECKPOINT_MANIFEST.json" "$remote/input/CHECKPOINT_MANIFEST.json" 6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6
for f in streaming_global_kv_endpoint_r3.py streaming_global_kv_sglang_hook.py streaming_global_kv_schedule.py;do sha=$(sha256sum "$project_dir/$f"|awk '{print $1}');stage "$project_dir/$f" "$remote/input/$(basename "$f")" "$sha";done
activated=inputs/activated_multiresolution_global_kv.py; activated_sha=$(sha256sum "$project_dir/$activated"|awk '{print $1}'); stage "$project_dir/$activated" "$remote/input/multiresolution_global_kv.py" "$activated_sha"
checkpoint_integrity(){ remote_run 600 "python3 - '$remote/input/CHECKPOINT_MANIFEST.json' '$remote/checkpoint' '$remote/out/CHECKPOINT_INTEGRITY.json' <<'PY'
import hashlib,json,os,pathlib,sys
manifest,root,out=map(pathlib.Path,sys.argv[1:]);spec=json.loads(manifest.read_text());rows=[]
for row in spec['files']:
 p=root/row['name'];h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 got=h.hexdigest()
 if got!=row['sha256']:raise RuntimeError('checkpoint_hash:'+row['name'])
 rows.append({'name':row['name'],'sha256':got,'bytes':p.stat().st_size})
payload={'schema_version':1,'manifest_sha256':'6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6','files':rows};t=out.with_suffix('.part');t.write_text(json.dumps(payload,sort_keys=True,indent=2)+'\\n');os.replace(t,out)
PY"; }
while ! checkpoint_integrity;do retain staging_failure checkpoint_integrity_failed;done
(( $(date -u +%s) < stage_epoch )) || { retain staging_failure staging_deadline; exit 1; }
while ! remote_run 900 "sudo -n docker pull '$image'";do retain staging_failure image_pull_failed;done
container=gemma4-streaming-global-kv-v10
start_server(){ remote_run 180 "sudo -n docker rm -f '$container' >/dev/null 2>&1||true;rm -f '$remote/out/activation.json';sudo -n docker run -d --name '$container' --gpus all --ipc=host --network host -v '$remote/checkpoint:/work/checkpoint:ro' -v '$remote/input:/work/input:ro' -v '$remote/out:/work/out' -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python -e GLOBAL_KV_HOOK=1 -e GLOBAL_KV_TELEMETRY=/work/out/candidate-telemetry.jsonl -e GLOBAL_KV_DIAGNOSTIC=/work/out/hook-diagnostic.json -e GLOBAL_KV_ACTIVATION_CAPTURE=/work/out/activation.json '$image' python3 -c \"import streaming_global_kv_sglang_hook;import runpy;runpy.run_module('sglang.launch_server',run_name='__main__')\" $server_command"; }
while ! start_server;do retain server_launch server_launch_failed;done
ready(){ remote_run 20 "curl -fsS --max-time 10 http://127.0.0.1:30000/health >/dev/null&&test -s '$remote/out/activation.json'"; };live(){ remote_run 20 "sudo -n docker inspect --format '{{.State.Running}}' '$container'|grep -qx true"; }
while ! ready;do if ! live;then retain server_launch server_exited;while ! start_server;do retain server_launch server_launch_failed;done;elif (( $(date -u +%s) >= server_epoch ));then retain server_launch server_readiness_deadline;else sleep 5;fi;done
run_endpoint(){ remote_run 1800 "STREAMING_GLOBAL_KV_OUTPUT_ROOT='$remote/out/endpoint-$1' STREAMING_GLOBAL_KV_EXACT_RUNNER='$remote/input/exact_runner.py' STREAMING_GLOBAL_KV_CANDIDATE_SERVER=1 GLOBAL_KV_TELEMETRY='$remote/out/candidate-telemetry.jsonl' GLOBAL_KV_ACTIVATION_CAPTURE='$remote/out/activation.json' python3 '$remote/input/streaming_global_kv_endpoint_r3.py'"; }
attempt=0;while ! run_endpoint "$attempt" >"$artifact_root/endpoint-$attempt.stdout" 2>"$artifact_root/endpoint-$attempt.stderr";do retain endpoint_only endpoint_failed;attempt=$((attempt+1));done
bounded "$release_epoch" 300 "${scp[@]}" -r "$user@$host:$remote/out/endpoint-$attempt" "$artifact_root/endpoint-final";remote_run 120 "sudo -n docker logs '$container' >'$remote/out/server.stdout' 2>'$remote/out/server.stderr';sudo -n docker rm -f '$container' >/dev/null";bounded "$release_epoch" 30 "${pool[@]}" release --project gemma4_streaming_global_kv_memory_schedule --bench "$bench" --expected-claimed-at "$claimed_at" --condition ready >"$artifact_root/release.json"
