#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=mixed-chunk-c32-20260718t2004z
out="$project/artifacts/$run_id"
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
fail() { python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part');q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n');q.replace(p)
PY
exit 1; }
trap 'fail owner_failure "$BASH_COMMAND"' ERR
sha256sum "$project/exact_mix_runner.py" > "$out/local-input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "set -e; test \$(find $remote/checkpoint -maxdepth 1 -type f | wc -l) -eq 8; sudo docker image inspect $image >/dev/null; mkdir -p $remote/workspace; sudo docker rm -f gemma-continuous-decode-steps-c32 >/dev/null 2>&1 || true; sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true"
"${scp_cmd[@]}" "$project/exact_mix_runner.py" "glmrunner@$ip:$remote/workspace/"
"${ssh_cmd[@]}" "sudo docker run -d --name gemma-mixed-chunk-c32 --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 --enable-mixed-chunk"
for attempt in $(seq 1 120); do
 if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/models.json" 2>"$out/models.stderr.log"; then break; fi
 sleep 4
done
test -s "$out/models.json" || fail unsupported_server mixed_chunk_not_ready
"${ssh_cmd[@]}" "sudo docker logs gemma-mixed-chunk-c32 >$remote/$run_id-server-start.log 2>&1; curl -fsS http://127.0.0.1:30000/metrics >$remote/$run_id-metrics-preflight.prom; curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:30000/flush_cache -D $remote/$run_id-flush.headers -o $remote/$run_id-flush.body; grep -E '^HTTP/.* 200' $remote/$run_id-flush.headers; grep -F 'enable_mixed_chunk=True' $remote/$run_id-server-start.log; grep -F \"prefill_attention_backend='triton'\" $remote/$run_id-server-start.log; grep -F \"decode_attention_backend='triton'\" $remote/$run_id-server-start.log; grep -F 'num_continuous_decode_steps=1' $remote/$run_id-server-start.log"
"${ssh_cmd[@]}" "rm -rf $remote/$run_id; sudo docker exec gemma-mixed-chunk-c32 python3 /work/workspace/exact_mix_runner.py --output /work/$run_id --arm mixed_chunk"
"${ssh_cmd[@]}" "cd $remote && sudo docker logs gemma-mixed-chunk-c32 >$run_id-server.log 2>&1 && tar -czf $run_id.tar.gz $run_id $run_id-server-start.log $run_id-server.log $run_id-metrics-preflight.prom $run_id-flush.headers $run_id-flush.body"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz"
tar -xzf "$out/artifacts.tar.gz" -C "$out"
python3 - "$out" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); run=root/'mixed-chunk-c32-20260718t2004z'; c=json.loads((run/'TERMINAL.json').read_text()); ident=(run/'mixed-chunk-c32-20260718t2004z-server-start.log').read_text(); cache=c['cache']; valid=bool(c.get('pass') and c.get('complete_requests')==32 and cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728 and all(x in ident for x in ('enable_mixed_chunk=True',"prefill_attention_backend='triton'","decode_attention_backend='triton'",'num_continuous_decode_steps=1','page_size=1')))
base=.9194573941250042; service=c['service_seconds_per_request'] if valid else None; classification='owner_failure' if not valid else 'promote' if service<=.873484524419 else 'retain_incremental' if service<base else 'negative'
(root/'TERMINAL.json').write_text(json.dumps({'schema_version':1,'status':'terminal','classification':classification,'pass':classification in ('promote','retain_incremental'),'candidate':c,'runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','comparator_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','comparator_service_seconds_per_request':base,'promotion_ceiling_seconds_per_request':.873484524419,'service_seconds_per_request_reduction':None if service is None else 1-service/base,'cache_accounting':cache},indent=2,sort_keys=True)+'\n')
PY
