#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-current-vllm
input="$root/input"
out="$root/artifacts/current-vllm-e4m3-h200"
image='vllm/vllm-openai@sha256:f0b9a0dc75a9fca3b6811e3279367b2d6a448055a000bfd13859587d74cef268'
mkdir -p "$out"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

state() {
  python3 - "$out/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part'); v=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'candidate_science_started':False}; v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

finish() {
  rc=$?
  sudo docker logs gemma4-current-vllm >"$out/server.log" 2>&1 || true
  sudo docker inspect gemma4-current-vllm >"$out/server.inspect.json" 2>&1 || true
  test -f "$out/WORKER_TERMINAL.json" || atomic "$out/WORKER_TERMINAL.json" integration_failure "remote exit $rc"
  exit "$rc"
}
trap finish EXIT

(cd "$input" && sha256sum -c INPUTS.sha256)
sudo docker image inspect "$image" >/dev/null 2>&1 || sudo docker pull "$image" >"$out/image-pull.log" 2>&1
sudo docker image inspect "$image" >"$out/image-inspect.json"
sudo docker rm -f gemma4-current-vllm >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name gemma4-current-vllm --gpus all --ipc=host --network host -v "$root:/work" "$image" \
  /work/checkpoint --served-model-name google/gemma-4-31B-it --dtype bfloat16 \
  --kv-cache-dtype fp8_e4m3 --tensor-parallel-size 1 --max-model-len 5000 --max-num-seqs 32 \
  --max-num-batched-tokens 134848 --gpu-memory-utilization 0.92 --enable-prefix-caching \
  --limit-mm-per-prompt '{"image":0,"video":0,"audio":0}' --host 0.0.0.0 --port 30000 >"$out/container-id"
for _ in $(seq 1 180); do
  curl -fsS http://127.0.0.1:30000/v1/models >"$out/models.json" 2>"$out/models.stderr" && break
  sleep 5
done
test -s "$out/models.json" || { atomic "$out/WORKER_TERMINAL.json" startup_timeout 'vLLM did not become ready'; exit 70; }
curl -fsS http://127.0.0.1:30000/metrics >"$out/preflight-metrics.prom"
sudo docker logs gemma4-current-vllm >"$out/server-startup.log" 2>&1
grep -F 'Using fp8_e4m3 data type to store kv cache' "$out/server-startup.log" >"$out/kv-cache-consumer.log"
python3 - "$out/models.json" "$out/KV_CACHE_CONSUMER.json" <<'PY'
import json,os,pathlib,sys
models=json.load(open(sys.argv[1])); p=pathlib.Path(sys.argv[2]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'kv_cache_dtype':'fp8_e4m3','consumer_log':'kv-cache-consumer.log','served_models':models},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
state candidate_science_started
python3 "$input/current_vllm_exact_mix_runner.py" --output "$out/exact-c32" --arm current_vllm_fp8e4m3_c32 --concurrency 32 --provider-hourly-usd 2.46
python3 - "$out/exact-c32/TERMINAL.json" "$out/WORKER_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
x=json.load(open(sys.argv[1])); p=pathlib.Path(sys.argv[2]); q=p.with_suffix('.part')
classification='measured_endpoint' if x['pass'] else 'endpoint_gate_failure'
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':classification,'terminal':x},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
