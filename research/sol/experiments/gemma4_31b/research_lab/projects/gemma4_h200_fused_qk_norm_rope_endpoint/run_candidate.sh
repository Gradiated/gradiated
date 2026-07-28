#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_fused_qk_norm_rope_endpoint
runner=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py
comparator=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/artifacts/exact-mix-c32-20260718t1729z/TERMINAL.json
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=fused-qk-norm-rope-c32-20260718t1806z
out="$project/artifacts/$run_id"
deadline_epoch=1784399340
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
path=pathlib.Path(sys.argv[1]); temporary=path.with_suffix('.part')
temporary.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n')
temporary.replace(path)
PY
}
fail() { terminal "$1" "$2"; exit 1; }
trap 'terminal owner_failure "$BASH_COMMAND"' ERR
(( $(date +%s) < deadline_epoch )) || fail deadline_expired before_launch
[[ "$(sha256sum "$runner" | awk '{print $1}')" == 143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7 ]] || fail identity_failure runner_sha256
[[ "$(sha256sum "$comparator" | awk '{print $1}')" == 6508e309d09a1ab04daa50c33243062843836bb5259ce107f387603008f65d0f ]] || fail identity_failure comparator_sha256
event resident_preflight
"${ssh_cmd[@]}" "set -e; test \$(find $remote/checkpoint -maxdepth 1 -type f | wc -l) -eq 8; sudo docker image inspect $image >/dev/null; mkdir -p $remote/workspace"
"${scp_cmd[@]}" "$runner" "glmrunner@$ip:$remote/workspace/exact_mix_runner.py"
event stock_c48_stop_and_candidate_start
"${ssh_cmd[@]}" "sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true; sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope"
for attempt in $(seq 1 90); do
  if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/models.json" 2>"$out/models.stderr.log"; then break; fi
  sleep 4
done
test -s "$out/models.json" || { "${ssh_cmd[@]}" 'sudo docker logs gemma-attention-endpoint' >"$out/server.log" 2>&1 || true; fail unsupported_server fused_candidate_not_ready; }
"${ssh_cmd[@]}" "sudo docker inspect gemma-attention-endpoint >$remote/$run_id-container-inspect.json; sudo docker logs gemma-attention-endpoint >$remote/$run_id-server.log 2>&1"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-container-inspect.json" "$out/container-inspect.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server.log" "$out/server-start.log"
grep -F -- '--enable-fused-qk-norm-rope' "$out/container-inspect.json" >/dev/null || fail unsupported_path fused_flag_absent_from_container_args
event candidate_exact_mix_start
"${ssh_cmd[@]}" "rm -rf $remote/$run_id; sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py --output /work/$run_id --arm fused_qk_norm_rope"
"${ssh_cmd[@]}" "cd $remote && tar -czf $run_id.tar.gz $run_id; sudo docker logs gemma-attention-endpoint >$run_id-server.log 2>&1; sudo docker inspect gemma-attention-endpoint >$run_id-container-inspect-final.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/candidate.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server.log" "$out/server.log"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-container-inspect-final.json" "$out/container-inspect-final.json"
python3 - "$out" "$comparator" <<'PY'
import json,pathlib,tarfile,sys
root=pathlib.Path(sys.argv[1]); comparator=json.loads(pathlib.Path(sys.argv[2]).read_text())['candidate']
with tarfile.open(root/'candidate.tar.gz') as archive:
    candidate=json.load(archive.extractfile(next(item for item in archive.getmembers() if item.name.endswith('/TERMINAL.json'))))
path_verified='--enable-fused-qk-norm-rope' in (root/'container-inspect-final.json').read_text()
valid=bool(candidate['pass'] and candidate['complete_requests']==32 and path_verified and candidate['cache']['cached_prompt_tokens_delta']==17120 and candidate['cache']['uncached_prompt_tokens_delta']==117728)
service=float(candidate['service_seconds_per_request']); baseline=float(comparator['service_seconds_per_request']); ceiling=.8840766932250105
if not valid: classification='negative'
elif service<=ceiling: classification='promote'
elif service<baseline: classification='retain_incremental'
else: classification='negative'
terminal={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and classification in ('promote','retain_incremental'),'candidate':candidate,'comparator_sha256':'6508e309d09a1ab04daa50c33243062843836bb5259ce107f387603008f65d0f','runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','comparator_service_seconds_per_request':baseline,'promotion_ceiling_seconds_per_request':ceiling,'service_seconds_per_request_reduction':1-service/baseline,'path_verified':path_verified,'cache_accounting_verified':candidate['cache']['cached_prompt_tokens_delta']==17120 and candidate['cache']['uncached_prompt_tokens_delta']==117728}
(root/'TERMINAL.json').write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n')
PY
event terminal_complete
