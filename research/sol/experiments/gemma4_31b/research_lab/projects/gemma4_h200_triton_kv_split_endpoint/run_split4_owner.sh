#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_triton_kv_split_endpoint
runner_project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=triton-kv-split4-c32-20260718t2018z
out="$project/artifacts/$run_id"
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)

fail() {
  python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n');q.replace(p)
PY
  exit 1
}
trap 'fail owner_failure "$BASH_COMMAND"' ERR

sha256sum "$runner_project/exact_mix_runner.py" > "$out/local-input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "set -e; test \$(find $remote/checkpoint -maxdepth 1 -type f | wc -l) -eq 8; sudo docker image inspect $image >/dev/null; mkdir -p $remote/workspace; sudo docker rm -f gemma-mixed-chunk-c32 >/dev/null"
"${scp_cmd[@]}" "$runner_project/exact_mix_runner.py" "glmrunner@$ip:$remote/workspace/"
"${ssh_cmd[@]}" "sudo docker run -d --name gemma-triton-kv-split4-c32 --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 4"
for attempt in $(seq 1 120); do
  if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/models.json" 2>"$out/models.stderr.log"; then break; fi
  sleep 4
done
test -s "$out/models.json" || fail startup_failure server_not_ready
"${ssh_cmd[@]}" "sudo docker logs gemma-triton-kv-split4-c32 >$remote/$run_id-server-start.log 2>&1; curl -fsS http://127.0.0.1:30000/metrics >$remote/$run_id-metrics-preflight.prom; curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:30000/flush_cache -D $remote/$run_id-flush.headers -o $remote/$run_id-flush.body; grep -E '^HTTP/.* 200' $remote/$run_id-flush.headers; grep -F 'triton_attention_num_kv_splits=4' $remote/$run_id-server-start.log; grep -F \"prefill_attention_backend='triton'\" $remote/$run_id-server-start.log; grep -F \"decode_attention_backend='triton'\" $remote/$run_id-server-start.log; grep -F 'enable_mixed_chunk=False' $remote/$run_id-server-start.log; grep -F 'num_continuous_decode_steps=1' $remote/$run_id-server-start.log; grep -F 'page_size=1' $remote/$run_id-server-start.log"
"${ssh_cmd[@]}" "rm -rf $remote/$run_id; sudo docker exec gemma-triton-kv-split4-c32 python3 /work/workspace/exact_mix_runner.py --output /work/$run_id --arm triton_kv_split4"
"${ssh_cmd[@]}" "cd $remote && sudo docker logs gemma-triton-kv-split4-c32 >$run_id-server.log 2>&1 && tar -czf $run_id.tar.gz $run_id $run_id-server-start.log $run_id-server.log $run_id-metrics-preflight.prom $run_id-flush.headers $run_id-flush.body"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz"
tar -xzf "$out/artifacts.tar.gz" -C "$out"
python3 - "$out" "$run_id" <<'PY'
import json,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]); run=root/sys.argv[2]
c=json.loads((run/'TERMINAL.json').read_text()); ident=(root/(sys.argv[2]+'-server-start.log')).read_text(); pre=(root/(sys.argv[2]+'-metrics-preflight.prom')).read_text(); headers=(root/(sys.argv[2]+'-flush.headers')).read_text()
cache=c['cache']; rows=c['rows']; gpu=list((run/'gpu.csv').read_text().splitlines()[1:])
samples=[]
for line in gpu:
    parts=line.split(',')
    if len(parts)==4:
        try: samples.append(tuple(float(x.strip()) for x in parts[1:]))
        except ValueError: pass
valid=bool(c.get('pass') and c.get('complete_requests')==32 and len(rows)==32 and all(x['prompt_tokens']==4214 and x['completion_tokens']==358 and x['text_nonempty'] and x['text_finite'] for x in rows) and cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728)
identity=all(x in ident for x in ('triton_attention_num_kv_splits=4',"prefill_attention_backend='triton'","decode_attention_backend='triton'",'enable_mixed_chunk=False','num_continuous_decode_steps=1','page_size=1'))
base=.9194573941250042; service=c['service_seconds_per_request'] if valid and identity else None
classification='owner_failure' if service is None else 'promote' if service<=.873484524419 else 'retain_incremental' if service<base else 'negative'
terminal={'schema_version':1,'status':'terminal','classification':classification,'pass':classification in ('promote','retain_incremental'),'candidate':{'arm':c['arm'],'service_seconds_per_request':service,'batch_seconds':c['batch_seconds'],'complete_requests':c['complete_requests'],'valid_rows':len(rows),'prompt_tokens_per_request':4214,'output_tokens_per_request':358,'cache':{'cached_prompt_tokens':cache['cached_prompt_tokens_delta'],'fresh_prompt_tokens':cache['uncached_prompt_tokens_delta'],'cached_fraction':cache['cached_fraction']},'phases_seconds':{'ttft_mean':c['phases']['ttft']['mean'],'decode_mean':c['phases']['decode']['mean'],'end_to_end_mean':c['phases']['end_to_end']['mean']},'gpu':{'utilization_mean_pct':statistics.mean(x[0] for x in samples) if samples else None,'memory_peak_mib':max(x[1] for x in samples) if samples else None,'power_mean_w':statistics.mean(x[2] for x in samples) if samples else None,'power_peak_w':max(x[2] for x in samples) if samples else None}},'comparator':{'terminal_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','service_seconds_per_request':base,'promotion_ceiling_seconds_per_request':.873484524419},'service_reduction_fraction':None if service is None else 1-service/base,'validity':{'runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','all_rows_nonempty_finite':valid,'exact_4214_358_rows':valid,'exact_cache_accounting':valid,'preflight_zero_running_and_queue':all(x not in pre for x in ('num_running_reqs 1','num_queue_reqs 1')),'cache_flush_http_status':200 if ' 200' in headers.splitlines()[0] else None,'resolved_triton_attention_num_kv_splits':identity,'frozen_runtime_identity':'TP1 bfloat16 weights; fp8_e5m2 KV; dynamic chunking 2048; fused QK/RoPE; Triton prefill/decode; page size 1; continuous decode steps 1; mixed chunk false; CUDA graphs through bs32'},'raw_runner_terminal':str(run.relative_to(root)/'TERMINAL.json'),'raw_artifacts':'artifacts.tar.gz'}
(root/'TERMINAL.json').write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n')
PY
