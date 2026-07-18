#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_global_head_dim256_sliced_endpoint
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
remote=/home/glmrunner/gemma-attention-endpoint
run_id=global-head256-sliced-c32-resume-20260718t2225z
out="$project/artifacts/$run_id"
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
export PYTHONPATH=/root/workspace/research/factory/src
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
heartbeat_pid=
released=0
started_epoch=$(date +%s)

write_terminal() {
  python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
}
release_claim() {
  (( released == 0 )) || return; released=1
  python3 - "$out/BENCH_CONTENTS.json" "$out/TERMINAL.json" <<'PY'
import json,pathlib,sys
t=json.loads(pathlib.Path(sys.argv[2]).read_text()) if pathlib.Path(sys.argv[2]).exists() else {}
pathlib.Path(sys.argv[1]).write_text(json.dumps({'project':'gemma4_global_head_dim256_sliced_endpoint','model':'google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4','image':'Pinned SGLang v0.5.12 image and Triton cache remain resident.','checkpoint':'Exact eight-file BF16 checkpoint remains unchanged and read-only at /home/glmrunner/gemma-attention-endpoint/checkpoint.','runtime':'One global-head256 sliced Triton c32 endpoint terminal: '+str(t.get('classification','owner_failure')),'artifacts':'Retrieved under projects/gemma4_global_head_dim256_sliced_endpoint/artifacts/global-head256-sliced-c32-resume-20260718t2225z/.','server_state':'Healthy global-head256 candidate container retained for reuse; no teardown performed.'},indent=2,sort_keys=True)+'\n')
PY
  python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_global_head_dim256_sliced_endpoint --condition ready --contents "$out/BENCH_CONTENTS.json" > "$out/bench-release.json" 2> "$out/bench-release.stderr" || true
}
cleanup() { [[ -z "$heartbeat_pid" ]] || { kill "$heartbeat_pid" >/dev/null 2>&1 || true; wait "$heartbeat_pid" >/dev/null 2>&1 || true; }; release_claim; }
trap cleanup EXIT
trap 'write_terminal owner_failure "$BASH_COMMAND"' ERR

sha256sum "$project/PATCH_MANIFEST.json" "$project/patch/gemma4_causal.py" "$project/patch/gemma4_mm.py" "$project/patch/model_config.py" "$project/inputs/exact_mix_runner.py" "$project/coherence_runner.py" "$project/remote_resume.sh" > "$out/local-input-sha256.txt"
grep -F '45d70e6d3943e349999d7d2a0a8e7e831a9440a7ca367120b58c428750d8da5d' "$out/local-input-sha256.txt"
grep -F '94a5bca79a254ca2642dd300b45af549bfd23718340a56aa83a059df2f95bd45' "$out/local-input-sha256.txt"
grep -F 'ba6a44488466db5667c47c8266d33e79eaebb2b4143e6192b0aeb9ce62837132' "$out/local-input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "mkdir -p $remote/workspace/global-head256-sliced" > "$out/ssh-preflight.log" 2>&1
"${scp_cmd[@]}" "$project/inputs/exact_mix_runner.py" "$project/coherence_runner.py" "$project/remote_resume.sh" "glmrunner@$ip:$remote/workspace/global-head256-sliced/" > "$out/scp-inputs.log" 2>&1
(
  while true; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_global_head_dim256_sliced_endpoint >> "$out/bench-heartbeats.jsonl" 2>> "$out/bench-heartbeats.stderr" || true; sleep 300; done
) & heartbeat_pid=$!
set +e
timeout --signal=TERM 3600 "${ssh_cmd[@]}" "bash $remote/workspace/global-head256-sliced/remote_resume.sh" > "$out/remote-owner.stdout" 2> "$out/remote-owner.stderr"
remote_exit=$?
set -e
printf '%s\n' "$remote_exit" > "$out/remote-owner.exit"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz" > "$out/scp-artifacts.log" 2>&1 || true
if [[ -s "$out/artifacts.tar.gz" ]]; then tar -xzf "$out/artifacts.tar.gz" -C "$out"; fi
python3 - "$out" "$remote_exit" "$started_epoch" <<'PY'
import json,pathlib,statistics,sys,time
root=pathlib.Path(sys.argv[1]); remote_exit=int(sys.argv[2]); started=int(sys.argv[3]); run=root/'global-head256-sliced-c32-resume-20260718t2225z'
owner=json.loads((run/'OWNER_TERMINAL.json').read_text()) if (run/'OWNER_TERMINAL.json').exists() else None
candidate=json.loads((run/'exact-mix/TERMINAL.json').read_text()) if (run/'exact-mix/TERMINAL.json').exists() else None
coherence=json.loads((run/'coherence.json').read_text()) if (run/'coherence.json').exists() else None
manifest=json.loads((run/'transformed-tensors.json').read_text()) if (run/'transformed-tensors.json').exists() else None
info=json.loads((run/'server-info-final.json').read_text()) if (run/'server-info-final.json').exists() else {}
identity=(run/'server.log').read_text(errors='replace') if (run/'server.log').exists() else ''
cache=(candidate or {}).get('cache',{})
rows=(candidate or {}).get('rows',[])
runtime_tokens=("prefill_attention_backend='triton'","decode_attention_backend='triton'",'triton_attention_num_kv_splits=8','page_size=1','num_continuous_decode_steps=1','stream_interval=1','enable_mixed_chunk=False','max_prefill_tokens=16384')
manifest_valid=bool(manifest and manifest.get('resolved_full_head_dim')==256 and manifest.get('resolved_local_head_dim')==256 and manifest.get('transformed_tensor_count')==50 and manifest.get('attention_k_eq_v') and manifest.get('global_layer_ids')==[5,11,17,23,29,35,41,47,53,59] and manifest.get('no_other_tensor_transform'))
valid=bool(remote_exit==0 and candidate and candidate.get('pass') and candidate.get('complete_requests')==32 and len(rows)==32 and all(x.get('prompt_tokens')==4214 and x.get('completion_tokens')==358 and x.get('text_nonempty') and x.get('text_finite') for x in rows) and cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728 and manifest_valid and all(x in identity for x in runtime_tokens))
service=float(candidate['service_seconds_per_request']) if valid else None
base=.9194573941250042; ceiling=.8734845244187539
classification=(owner or {}).get('classification','owner_failure') if not valid else ('promote' if service<=ceiling else 'negative')
elapsed=max(0,time.time()-started); spend=elapsed*2.46/3600
terminal={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and classification=='promote','performance_valid':valid,'coherence_pass':None if coherence is None else coherence.get('pass'),'quality_claim':False,'remote_exit':remote_exit,'candidate':candidate,'transformed_manifest':manifest,'owner_terminal':owner,'runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','comparator_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','comparator_service_seconds_per_request':base,'promotion_ceiling_seconds_per_request':ceiling,'service_seconds_per_request_reduction':None if service is None else 1-service/base,'cache_accounting':cache,'provider_exposure_seconds':elapsed,'provider_spend_usd_conservative':spend,'identities':{'runtime_tokens':list(runtime_tokens),'runtime_verified':all(x in identity for x in runtime_tokens),'server_full_head_dim':info.get('head_dim'),'server_local_head_dim':info.get('swa_head_dim')}}
(root/'TERMINAL.json').write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n')
PY
exit "$remote_exit"
