#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_h200_torch_compile_endpoint
runner=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py
comparator=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=torch-compile-fused-c32-20260718t1827z
out="$project/artifacts/$run_id"
deadline_epoch=1784400240
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)

event() { python3 - "$out/EVENTS.jsonl" "$1" <<'PY'
import datetime,json,pathlib,sys
with pathlib.Path(sys.argv[1]).open('a') as handle:
    handle.write(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),'phase':sys.argv[2]},sort_keys=True)+'\n')
PY
}
terminal() { python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
path=pathlib.Path(sys.argv[1]); temp=path.with_suffix('.part')
temp.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n')
temp.replace(path)
PY
}
fail() { terminal "$1" "$2"; exit 1; }
trap 'terminal owner_failure "$BASH_COMMAND"' ERR

(( $(date +%s) < deadline_epoch )) || fail compile_timeout deadline_before_launch
[[ "$(sha256sum "$runner" | awk '{print $1}')" == 143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7 ]] || fail identity_failure runner_sha256
[[ "$(sha256sum "$comparator" | awk '{print $1}')" == 1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3 ]] || fail identity_failure comparator_sha256
event resident_preflight
"${ssh_cmd[@]}" "set -e; test \$(find $remote/checkpoint -maxdepth 1 -type f | wc -l) -eq 8; sudo docker image inspect $image >/dev/null; mkdir -p $remote/workspace"
"${scp_cmd[@]}" "$runner" "glmrunner@$ip:$remote/workspace/exact_mix_runner.py"
event fused_server_stop_compiled_candidate_start
"${ssh_cmd[@]}" "sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true; sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --enable-torch-compile --torch-compile-max-bs 32"
for attempt in $(seq 1 90); do
  if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/models.json" 2>"$out/models.stderr.log" && test -s "$out/models.json"; then break; fi
  sleep 4
done
test -s "$out/models.json" || { "${ssh_cmd[@]}" 'sudo docker logs gemma-attention-endpoint' >"$out/server.log" 2>&1 || true; fail compile_timeout compiled_candidate_not_ready; }
"${ssh_cmd[@]}" "sudo docker inspect gemma-attention-endpoint >$remote/$run_id-container-inspect.json; curl -fsS http://127.0.0.1:30000/get_server_info >$remote/$run_id-server-info.json; curl -fsS -o $remote/$run_id-flush-body.txt -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache >$remote/$run_id-flush-status.txt; curl -fsS http://127.0.0.1:30000/metrics >$remote/$run_id-idle-metrics.prom; sudo docker logs gemma-attention-endpoint >$remote/$run_id-server-start.log 2>&1"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-container-inspect.json" "$out/container-inspect.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server-info.json" "$out/server-info.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-flush-status.txt" "$out/flush-status.txt"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-flush-body.txt" "$out/flush-body.txt"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-idle-metrics.prom" "$out/idle-metrics.prom"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server-start.log" "$out/server-start.log"
python3 - "$out" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); info=json.loads((root/'server-info.json').read_text())
active=[line for line in (root/'idle-metrics.prom').read_text().splitlines() if 'sglang:http_requests_active' in line and not line.startswith('#')]
assert info['enable_torch_compile'] is True and info['torch_compile_max_bs']==32
assert info['enable_fused_qk_norm_rope'] is True and info['enable_dynamic_chunking'] is True and info['chunked_prefill_size']==2048
assert (root/'flush-status.txt').read_text().strip()=='200'
assert all(line.rstrip().endswith(' 0.0') for line in active if 'endpoint="/v1/completions"' in line)
(root/'idle-boundary.json').write_text(json.dumps({'running_requests':0,'queued_requests':0,'flush_http_status':200,'flush_response':(root/'flush-body.txt').read_text().strip(),'proof':'freshly relaunched server; active completion HTTP gauge is zero'},indent=2,sort_keys=True)+'\n')
PY
event candidate_exact_mix_start
"${ssh_cmd[@]}" "rm -rf $remote/$run_id; sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py --output /work/$run_id --arm torch_compile_fused_qk_norm_rope"
"${ssh_cmd[@]}" "cd $remote && tar -czf $run_id.tar.gz $run_id; sudo docker logs gemma-attention-endpoint >$run_id-server.log 2>&1; sudo docker inspect gemma-attention-endpoint >$run_id-container-inspect-final.json; curl -fsS http://127.0.0.1:30000/get_server_info >$run_id-server-info-final.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/candidate.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server.log" "$out/server.log"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-container-inspect-final.json" "$out/container-inspect-final.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server-info-final.json" "$out/server-info-final.json"
python3 - "$out" "$comparator" <<'PY'
import json,pathlib,tarfile,sys
root=pathlib.Path(sys.argv[1]); comparator=json.loads(pathlib.Path(sys.argv[2]).read_text())
with tarfile.open(root/'candidate.tar.gz') as archive:
    candidate=json.load(archive.extractfile(next(x for x in archive.getmembers() if x.name.endswith('/TERMINAL.json'))))
info=json.loads((root/'server-info-final.json').read_text())
args=(root/'container-inspect-final.json').read_text(); log=(root/'server.log').read_text(errors='replace')
compiled=info.get('enable_torch_compile') is True and info.get('torch_compile_max_bs')==32 and '--enable-torch-compile' in args and ('torch.compile' in log.lower() or 'torch compile' in log.lower() or 'inductor' in log.lower())
cache=candidate['cache']; valid=bool(candidate['pass'] and candidate['complete_requests']==32 and compiled and cache['cached_prompt_tokens_delta']==17120 and cache['uncached_prompt_tokens_delta']==117728)
service=float(candidate['service_seconds_per_request']); baseline=0.9194573941250042; ceiling=0.8734845244187539
classification='negative' if not valid else ('promote' if service<=ceiling else 'retain_incremental' if service<baseline else 'negative')
terminal={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and classification in ('promote','retain_incremental'),'candidate':candidate,'comparator_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','comparator_service_seconds_per_request':baseline,'promotion_ceiling_seconds_per_request':ceiling,'service_seconds_per_request_reduction':1-service/baseline,'compiled_path_consumed':compiled,'cache_accounting_verified':cache['cached_prompt_tokens_delta']==17120 and cache['uncached_prompt_tokens_delta']==117728}
(root/'TERMINAL.json').write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n')
PY
event terminal_complete
