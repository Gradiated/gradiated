#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_trtllm_decode_backend_endpoint
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
remote=/home/glmrunner/gemma-attention-endpoint
run_id=trtllm-decode-c32-20260718t1937z
out="$project/artifacts/$run_id"
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
export PYTHONPATH=/root/workspace/research/factory/src
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
heartbeat_pid=
released=0

write_terminal() { python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); t=p.with_suffix('.part')
t.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); t.replace(p)
PY
}
release_claim() {
  (( released == 0 )) || return; released=1
  python3 - "$out/BENCH_CONTENTS.json" "$out/TERMINAL.json" <<'PY'
import json,pathlib,sys
t=json.loads(pathlib.Path(sys.argv[2]).read_text()) if pathlib.Path(sys.argv[2]).exists() else {}
pathlib.Path(sys.argv[1]).write_text(json.dumps({'project':'gemma4_h200_trtllm_decode_backend_endpoint','model':'google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4','image':'Pinned SGLang v0.5.12 image remains resident.','checkpoint':'Exact eight-file BF16 checkpoint remains at /home/glmrunner/gemma-attention-endpoint/checkpoint.','runtime':'SGLang TRTLLM-MHA decode terminal '+str(t.get('classification','owner_failure')),'artifacts':'Retrieved under projects/gemma4_h200_trtllm_decode_backend_endpoint/artifacts/trtllm-decode-c32-20260718t1937z/.','server_state':'retain healthy candidate container for reuse'},indent=2,sort_keys=True)+'\n')
PY
  python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_h200_trtllm_decode_backend_endpoint --condition ready --contents "$out/BENCH_CONTENTS.json" > "$out/bench-release.json" 2> "$out/bench-release.stderr" || true
}
cleanup() { [[ -z "$heartbeat_pid" ]] || { kill "$heartbeat_pid" >/dev/null 2>&1 || true; wait "$heartbeat_pid" >/dev/null 2>&1 || true; }; release_claim; }
trap cleanup EXIT
trap 'write_terminal owner_failure "$BASH_COMMAND"' ERR

sha256sum "$project/remote_trtllm_c32.sh" /root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py > "$out/local-input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "mkdir -p $remote/workspace" > "$out/ssh-preflight.log" 2>&1
"${scp_cmd[@]}" "$project/remote_trtllm_c32.sh" /root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py "glmrunner@$ip:$remote/workspace/" > "$out/scp-inputs.log" 2>&1
(
  while true; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_h200_trtllm_decode_backend_endpoint >> "$out/bench-heartbeats.jsonl" 2>> "$out/bench-heartbeats.stderr" || true; sleep 300; done
) & heartbeat_pid=$!
set +e
timeout --signal=TERM 3900 "${ssh_cmd[@]}" "bash $remote/workspace/remote_trtllm_c32.sh" > "$out/remote-owner.stdout" 2> "$out/remote-owner.stderr"
remote_exit=$?
set -e
printf '%s\n' "$remote_exit" > "$out/remote-owner.exit"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz" > "$out/scp-artifacts.log" 2>&1 || true
if [[ -s "$out/artifacts.tar.gz" ]]; then tar -xzf "$out/artifacts.tar.gz" -C "$out"; fi
python3 - "$out" "$remote_exit" <<'PY'
import json,pathlib,tarfile,sys
root=pathlib.Path(sys.argv[1]); remote_exit=int(sys.argv[2]); remote=root/'trtllm-decode-c32-20260718t1937z'; owner=json.loads((remote/'OWNER_TERMINAL.json').read_text()) if (remote/'OWNER_TERMINAL.json').exists() else None
candidate=json.loads((remote/'exact-mix/TERMINAL.json').read_text()) if (remote/'exact-mix/TERMINAL.json').exists() else None
identity=(remote/'server-start.log').read_text() if (remote/'server-start.log').exists() else ''
valid=bool(candidate and candidate.get('pass') and candidate.get('complete_requests')==32 and candidate.get('cache',{}).get('prompt_tokens_delta')==134848 and candidate.get('cache',{}).get('cached_prompt_tokens_delta') is not None and "prefill_attention_backend='triton'" in identity and "decode_attention_backend='trtllm_mha'" in identity and 'page_size=64' in identity and "kv_cache_dtype='fp8_e5m2'" in identity)
service=float(candidate['service_seconds_per_request']) if valid else None
base=0.9194573941250042; ceiling=0.8734845244187539
classification=(owner or {}).get('classification','owner_failure') if not valid else ('promote' if service<=ceiling else 'retain_incremental' if service<base else 'negative')
value={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and classification in ('promote','retain_incremental'),'remote_exit':remote_exit,'candidate':candidate,'owner_terminal':owner,'runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','comparator_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','comparator_service_seconds_per_request':base,'promotion_ceiling_seconds_per_request':ceiling,'service_seconds_per_request_reduction':None if service is None else 1-service/base,'cache_accounting':None if candidate is None else candidate.get('cache')}
(root/'TERMINAL.json').write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
PY
exit "$remote_exit"
