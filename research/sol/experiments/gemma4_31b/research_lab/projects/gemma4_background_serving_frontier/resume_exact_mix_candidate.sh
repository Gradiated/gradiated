#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=exact-mix-c32-20260718t1729z
out="$project/artifacts/$run_id"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
"${scp_cmd[@]}" "$project/exact_mix_runner.py" "glmrunner@$ip:$remote/workspace/"
"${ssh_cmd[@]}" "sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true; sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048"
for attempt in $(seq 1 90); do
  if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/dynamic_chunked-models.json" 2>"$out/dynamic_chunked-models.stderr.log"; then break; fi
  sleep 4
done
test -s "$out/dynamic_chunked-models.json"
"${ssh_cmd[@]}" "rm -rf $remote/$run_id-dynamic_chunked; sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py --output /work/$run_id-dynamic_chunked --arm dynamic_chunked"
"${ssh_cmd[@]}" "cd $remote && tar -czf $run_id-stock.tar.gz $run_id-stock && tar -czf $run_id-dynamic_chunked.tar.gz $run_id-dynamic_chunked; sudo docker logs gemma-attention-endpoint >$run_id-dynamic_chunked-server.log 2>&1"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-stock.tar.gz" "$out/stock.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-dynamic_chunked.tar.gz" "$out/dynamic_chunked.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-dynamic_chunked-server.log" "$out/dynamic_chunked-server.log"
python3 - "$out" <<'PY'
import json,pathlib,tarfile,sys
root=pathlib.Path(sys.argv[1]); rows={}
for arm in ('stock','dynamic_chunked'):
    with tarfile.open(root/f'{arm}.tar.gz') as t:
        rows[arm]=json.load(t.extractfile(next(x for x in t.getmembers() if x.name.endswith('/TERMINAL.json'))))
    rows[arm]['pass']=all(x['error'] is None and x['prompt_tokens']==4214 and x['completion_tokens']==358 and x['text_nonempty'] and x['text_finite'] for x in rows[arm]['rows'])
reduction=1-rows['dynamic_chunked']['service_seconds_per_request']/rows['stock']['service_seconds_per_request']
passed=rows['stock']['pass'] and rows['dynamic_chunked']['pass'] and rows['dynamic_chunked']['complete_requests']==32 and reduction>=.05
(root/'TERMINAL.json').write_text(json.dumps({'schema_version':1,'status':'terminal','classification':'promote' if passed else 'negative','pass':passed,'stock':rows['stock'],'candidate':rows['dynamic_chunked'],'service_seconds_per_request_reduction':reduction},indent=2,sort_keys=True)+'\n')
PY
