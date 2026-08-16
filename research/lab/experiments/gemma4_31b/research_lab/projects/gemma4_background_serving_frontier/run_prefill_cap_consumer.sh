#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
run_id=prefill-cap32768-consumer-c32-20260718t2101z
runner=inputs/exact_mix_runner-143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7.py
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
sha256sum "$project/$runner" > "$out/local-runner-sha256.txt"
grep -Fx '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7  /root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/inputs/exact_mix_runner-143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7.py' "$out/local-runner-sha256.txt"
"${ssh_cmd[@]}" "set -e; sudo docker inspect -f '{{.State.Running}}' gemma-prefill-cap32768-c32 | grep -Fx true; curl -fsS http://127.0.0.1:30000/v1/models >$remote/$run_id-models.json; sudo docker logs gemma-prefill-cap32768-c32 >$remote/$run_id-server-start.log 2>&1; sha256sum $remote/workspace/exact_mix_runner_bound.py >$remote/$run_id-remote-runner-sha256.txt; grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' $remote/$run_id-remote-runner-sha256.txt; pool=\$(grep -o 'max_total_num_tokens=[0-9]*' $remote/$run_id-server-start.log | head -1 | cut -d= -f2); test -n \"\$pool\"; test \"\$pool\" -ge 146304; printf '%s\\n' \"\$pool\" >$remote/$run_id-token-pool.txt; curl -fsS http://127.0.0.1:30000/metrics >$remote/$run_id-metrics-preflight.prom; curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:30000/flush_cache -D $remote/$run_id-flush.headers -o $remote/$run_id-flush.body; grep -E '^HTTP/.* 200' $remote/$run_id-flush.headers; grep -F 'max_prefill_tokens=32768' $remote/$run_id-server-start.log; grep -F 'stream_interval=1' $remote/$run_id-server-start.log; grep -F 'enable_mixed_chunk=False' $remote/$run_id-server-start.log; grep -F \"prefill_attention_backend='triton'\" $remote/$run_id-server-start.log; grep -F \"decode_attention_backend='triton'\" $remote/$run_id-server-start.log; grep -F 'num_continuous_decode_steps=1' $remote/$run_id-server-start.log"
"${ssh_cmd[@]}" "rm -rf $remote/$run_id; sudo docker exec gemma-prefill-cap32768-c32 python3 /work/workspace/exact_mix_runner_bound.py --output /work/$run_id --arm prefill_cap32768"
"${ssh_cmd[@]}" "cd $remote && sudo docker logs gemma-prefill-cap32768-c32 >$run_id-server.log 2>&1 && tar -czf $run_id.tar.gz $run_id $run_id-models.json $run_id-server-start.log $run_id-server.log $run_id-remote-runner-sha256.txt $run_id-token-pool.txt $run_id-metrics-preflight.prom $run_id-flush.headers $run_id-flush.body"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz"
tar -xzf "$out/artifacts.tar.gz" -C "$out"
python3 - "$out" "$run_id" <<'PY'
import json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]); rid=sys.argv[2]; run=root/rid
c=json.loads((run/'TERMINAL.json').read_text()); ident=(root/f'{rid}-server-start.log').read_text(); log=(root/f'{rid}-server.log').read_text(); cache=c['cache']; pool=int((root/f'{rid}-token-pool.txt').read_text().strip())
identity=all(x in ident for x in ('max_prefill_tokens=32768','stream_interval=1','enable_mixed_chunk=False',"prefill_attention_backend='triton'","decode_attention_backend='triton'",'num_continuous_decode_steps=1','page_size=1',"dtype='bfloat16'","kv_cache_dtype='fp8_e5m2'",'triton_attention_num_kv_splits=8'))
retractions='Retract requests' in log; valid=bool(c.get('pass') and c.get('complete_requests')==32 and cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728 and identity and pool>=146304 and not retractions)
base=.9194573941250042; service=c.get('service_seconds_per_request'); classification='negative' if valid and service>=base else 'retain_incremental' if valid and service>.873484524419 else 'promote' if valid else 'negative_resource' if retractions or pool<146304 else 'unsupported'
root.joinpath('TERMINAL.json').write_text(json.dumps({'schema_version':1,'status':'terminal','classification':classification,'pass':classification in ('promote','retain_incremental'),'runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','comparator_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','comparator_service_seconds_per_request':base,'promotion_ceiling_seconds_per_request':.873484524419,'candidate':c,'token_pool':pool,'retractions':retractions,'identity_ok':identity,'cache_accounting':cache,'service_seconds_per_request_reduction':None if not valid else 1-service/base},indent=2,sort_keys=True)+'\n')
PY
