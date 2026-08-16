#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-qserve-endpoint
input="$root/input"
out="$root/artifacts/bf16-qserve-c32"
checkpoint="$root/checkpoint"
qserve=/home/glmrunner/gemma4-qserve-bf16/runs/8828d463cf965bab69e4eb1890c38a6ab713a6f555a5e4388ec1601472efb08a
image='docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
container=gemma-qserve-bf16-endpoint
mkdir -p "$out" "$root/w4_cache/d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]);q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'classification':sys.argv[2],'message':sys.argv[3],'epoch':time.time()},indent=2,sort_keys=True)+'\n')
os.replace(q,p)
PY
}

state() {
  python3 - "$out/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part')
v=json.loads(p.read_text()) if p.exists() else {'health_probe_started':False,'model_probe_passed':False,'coherence_request_started':False,'coherence_passed':False,'endpoint_request_started':False}
v[sys.argv[2]]=True;v['updated_epoch']=time.time()
q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}

capture() {
  sudo docker logs "$container" >"$out/server.log" 2>&1 || true
  sudo docker inspect "$container" >"$out/server.inspect.json" 2>&1 || true
  nvidia-smi --query-gpu=timestamp,name,uuid,memory.used,memory.total,utilization.gpu,power.draw --format=csv,noheader >"$out/gpu-final.csv" 2>&1 || true
}

finish() {
  rc=$?
  trap - EXIT
  capture
  if ! test -f "$out/WORKER_TERMINAL.json"; then
    atomic "$out/WORKER_TERMINAL.json" integration_failure "endpoint worker exit $rc"
  fi
  exit "$rc"
}
trap finish EXIT

python3 "$input/verify_endpoint.py" \
  --root "$input" \
  --manifest "$input/ENDPOINT_INPUT_MANIFEST.json" \
  >"$out/input-verification.json"
cd "$checkpoint"
sha256sum -c "$input/CHECKPOINT.sha256" >"$out/checkpoint-verification.log"
cd "$input"
sha256sum -c ENDPOINT.sha256 >"$out/endpoint-verification.log"
nvidia-smi --query-gpu=timestamp,name,uuid,memory.used,memory.total,utilization.gpu,power.draw --format=csv,noheader >"$out/gpu-before.csv"
sudo docker rm -f "$container" >/dev/null 2>&1 || true
sudo docker run -d \
  --name "$container" \
  --gpus all \
  --ipc=host \
  --network host \
  -e "PYTHONPATH=/endpoint:$qserve/inputs/bf16_epilogue/qserve_sm89" \
  -e "QSERVE_W4_CACHE=/work/w4_cache/d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2" \
  -e "QSERVE_EVENT_LOG=/work/artifacts/bf16-qserve-c32/qserve-events.jsonl" \
  -v "$root:/work" \
  -v "$input:/endpoint:ro" \
  -v "$qserve:$qserve" \
  --entrypoint python3 \
  "$image" \
  -m sglang.launch_server \
  --model-path /work/checkpoint \
  --tokenizer-path /work/checkpoint \
  --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 \
  --quantization fp8 \
  --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 \
  --host 0.0.0.0 \
  --port 30000 \
  --context-length 5000 \
  --max-running-requests 32 \
  --mem-fraction-static 0.80 \
  --enable-metrics \
  --skip-server-warmup \
  --enable-dynamic-chunking \
  --chunked-prefill-size 2048 \
  --enable-fused-qk-norm-rope \
  --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton \
  --decode-attention-backend triton \
  --page-size 1 >"$out/container-id"

state health_probe_started
for _ in $(seq 1 720); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$out/models.json" 2>"$out/models.stderr"; then
    state model_probe_passed
    break
  fi
  if ! sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -qx true; then
    atomic "$out/WORKER_TERMINAL.json" model_startup_failure "server exited before model probe"
    exit 70
  fi
  sleep 5
done
test -s "$out/models.json" || {
  atomic "$out/WORKER_TERMINAL.json" model_startup_timeout "server did not become ready"
  exit 70
}

cache_root="$root/w4_cache/d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
find "$cache_root" -maxdepth 1 -type f -name '*.pt' -print0 | sort -z | xargs -0 sha256sum >"$out/W4_CACHE.sha256"
cache_count=$(wc -l <"$out/W4_CACHE.sha256")
test "$cache_count" = 180 || {
  atomic "$out/WORKER_TERMINAL.json" w4_cache_incomplete "expected 180 exact-weight shards, found $cache_count"
  exit 70
}
python3 - "$out/W4_REPRESENTATION_MANIFEST.json" "$out/W4_CACHE.sha256" "$cache_root" <<'PY'
import json,os,pathlib,sys
out=pathlib.Path(sys.argv[1]); hashes=pathlib.Path(sys.argv[2]); root=pathlib.Path(sys.argv[3])
files=[]
for line in hashes.read_text().splitlines():
    digest,path=line.split(None,1);p=pathlib.Path(path)
    files.append({'name':p.name,'bytes':p.stat().st_size,'sha256':digest})
value={'schema_version':1,'model':'google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4','checkpoint_index_sha256':'d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2','group_size':128,'files':files,'bytes':sum(x['bytes'] for x in files)}
part=out.with_suffix('.part');part.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');os.replace(part,out)
PY

mkdir -p "$out/coherence"
cp "$input/coherence_runner.py" "$out/coherence/coherence_runner.py"
state coherence_request_started
python3 "$out/coherence/coherence_runner.py"
cp "$out/coherence/COHERENCE_TERMINAL.json" "$out/COHERENCE_TERMINAL.json"
python3 - "$out/COHERENCE_TERMINAL.json" <<'PY'
import json,sys
raise SystemExit(0 if json.load(open(sys.argv[1]))['pass'] else 72)
PY
state coherence_passed

state endpoint_request_started
python3 "$input/exact_c32_runner.py" \
  --output "$out/exact-c32" \
  --arm qserve_w4a8_bf16_epilogue_c32
curl -fsS http://127.0.0.1:30000/metrics >"$out/metrics-final.prom"
capture
python3 - "$out/exact-c32/TERMINAL.json" "$out/COHERENCE_TERMINAL.json" "$out/server.inspect.json" "$out/gpu-before.csv" "$out/gpu-final.csv" "$out/WORKER_TERMINAL.json" <<'PY'
import json,math,os,pathlib,sys
endpoint=json.load(open(sys.argv[1]));coherence=json.load(open(sys.argv[2]));inspect=json.load(open(sys.argv[3]))
before=pathlib.Path(sys.argv[4]).read_text();after=pathlib.Path(sys.argv[5]).read_text()
container=inspect[0] if isinstance(inspect,list) else inspect
restarts=int(container.get('RestartCount',-1))
stable=container.get('State',{}).get('Running') is True and restarts==0
passed=bool(endpoint['pass'] and coherence['pass'] and endpoint['complete_requests']==32 and endpoint['service_seconds_per_request']<=1.8853265455 and stable)
value={'schema_version':1,'classification':'endpoint_positive' if passed else 'endpoint_reject','pass':passed,'coherence':coherence,'endpoint':endpoint,'price_normalized_ceiling_seconds_per_request':1.8853265455,'container_running':container.get('State',{}).get('Running'),'restart_count':restarts,'stable_runtime':stable,'gpu_before':before,'gpu_after':after}
p=pathlib.Path(sys.argv[6]);q=p.with_suffix('.part');q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');os.replace(q,p)
raise SystemExit(0 if passed else 72)
PY
