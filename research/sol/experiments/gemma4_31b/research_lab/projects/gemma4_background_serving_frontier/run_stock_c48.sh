#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=stock-c48-20260718t1743z
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
"${ssh_cmd[@]}" "set -e; test \$(find $remote/checkpoint -maxdepth 1 -type f | wc -l) -eq 8; sudo docker image inspect $image >/dev/null; mkdir -p $remote/workspace; sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true"
"${scp_cmd[@]}" "$project/exact_mix_runner.py" "glmrunner@$ip:$remote/workspace/"
"${ssh_cmd[@]}" "sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 48 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --cuda-graph-max-bs 48"
for attempt in $(seq 1 120); do
 if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/models.json" 2>"$out/models.stderr.log"; then break; fi
 sleep 4
done
test -s "$out/models.json" || fail unsupported_server c48_not_ready
"${ssh_cmd[@]}" "rm -rf $remote/$run_id; sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py --output /work/$run_id --arm stock_c48 --concurrency 48"
"${ssh_cmd[@]}" "cd $remote && tar -czf $run_id.tar.gz $run_id; sudo docker logs gemma-attention-endpoint >$run_id-server.log 2>&1"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/c48.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-server.log" "$out/server.log"
python3 - "$out" <<'PY'
import json,pathlib,tarfile,sys
root=pathlib.Path(sys.argv[1])
with tarfile.open(root/'c48.tar.gz') as t: row=json.load(t.extractfile(next(x for x in t.getmembers() if x.name.endswith('/TERMINAL.json'))))
valid=all(x['error'] is None and x['prompt_tokens']==4214 and x['completion_tokens']==358 and x['text_nonempty'] and x['text_finite'] for x in row['rows'])
row['pass']=valid
ceiling=.921393893372
classification='promote' if valid and row['service_seconds_per_request']<=ceiling else 'negative'
(root/'TERMINAL.json').write_text(json.dumps({'schema_version':1,'status':'terminal','classification':classification,'pass':classification=='promote','frozen_c32_sha256':'6508e309d09a1ab04daa50c33243062843836bb5259ce107f387603008f65d0f','frozen_c32_service_seconds_per_request':.969888308813,'promotion_ceiling_seconds_per_request':ceiling,'c48':row},indent=2,sort_keys=True)+'\n')
PY
