#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier
remote=/home/glmrunner/gemma-attention-endpoint
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
run_id=exact-mix-c32-20260718t1729z
out="$project/artifacts/$run_id"
deadline_epoch=1784397600
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)

event() { python3 - "$out/EVENTS.jsonl" "$1" <<'PY'
import datetime,json,pathlib,sys
with pathlib.Path(sys.argv[1]).open('a') as f: f.write(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),'phase':sys.argv[2]},sort_keys=True)+'\n')
PY
}
fail() { python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part');q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n');q.replace(p)
PY
 exit 1; }
trap 'fail owner_failure "$BASH_COMMAND"' ERR
(( $(date +%s) < deadline_epoch )) || fail deadline_expired before_launch
event resident_preflight
"${ssh_cmd[@]}" "set -e; test \$(find $remote/checkpoint -maxdepth 1 -type f | wc -l) -eq 8; sudo docker image inspect $image >/dev/null; mkdir -p $remote/workspace"
"${scp_cmd[@]}" "$project/exact_mix_runner.py" "glmrunner@$ip:$remote/workspace/"
launch() {
  local arm=$1 extra=$2
  event "${arm}_server_start"
  "${ssh_cmd[@]}" "sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true; sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup $extra"
  for attempt in $(seq 1 90); do
    if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/${arm}-models.json" 2>"$out/${arm}-models.stderr.log"; then return 0; fi
    sleep 4
  done
  "${ssh_cmd[@]}" 'sudo docker logs gemma-attention-endpoint' >"$out/${arm}-server.log" 2>&1 || true
  fail unsupported_server "$arm not ready"
}
run_arm() {
  local arm=$1
  event "${arm}_run_start"
  "${ssh_cmd[@]}" "rm -rf $remote/$run_id-$arm; sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py --output /work/$run_id-$arm --arm $arm"
  "${ssh_cmd[@]}" "cd $remote && tar -czf $run_id-$arm.tar.gz $run_id-$arm; sudo docker logs gemma-attention-endpoint >$run_id-$arm-server.log 2>&1"
  "${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-$arm.tar.gz" "$out/$arm.tar.gz"
  "${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id-$arm-server.log" "$out/$arm-server.log"
  event "${arm}_run_complete"
}
launch stock ''
run_arm stock
launch dynamic_chunked '--enable-dynamic-chunking --chunked-prefill-size 2048'
run_arm dynamic_chunked
python3 - "$out" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); rows={}
for arm in ('stock','dynamic_chunked'):
 import tarfile
 with tarfile.open(root/f'{arm}.tar.gz') as t:
  item=next(x for x in t.getmembers() if x.name.endswith('/TERMINAL.json'))
  rows[arm]=json.load(t.extractfile(item))
s=rows['stock'];c=rows['dynamic_chunked']; reduction=1-float(c['service_seconds_per_request'])/float(s['service_seconds_per_request'])
passed=bool(s['pass'] and c['pass'] and c['complete_requests']==32 and reduction>=.05)
(root/'TERMINAL.json').write_text(json.dumps({'schema_version':1,'status':'terminal','classification':'promote' if passed else 'negative','pass':passed,'stock':s,'candidate':c,'service_seconds_per_request_reduction':reduction},indent=2,sort_keys=True)+'\n')
PY
event terminal_complete
