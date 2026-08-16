#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-current-sglang
input="$root/input"
out="$root/artifacts/current-sglang-c32-r2"
image='docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427'
mkdir -p "$out"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}

state() {
  python3 - "$out/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part');v=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'candidate_science_started':False};v[sys.argv[2]]=True;q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}

finish() {
  rc=$?
  sudo docker logs gemma-current-sglang >"$out/server.log" 2>&1 || true
  sudo docker inspect gemma-current-sglang >"$out/server.inspect.json" 2>&1 || true
  test -f "$out/WORKER_TERMINAL.json" || atomic "$out/WORKER_TERMINAL.json" integration_failure "remote exit $rc"
  exit "$rc"
}
trap finish EXIT

(cd "$input" && sha256sum -c INPUTS.sha256)
sudo docker image inspect "$image" >/dev/null 2>&1 || sudo docker pull "$image" >"$out/image-pull.log" 2>&1
sudo docker image inspect "$image" >"$out/image-inspect.json"
sudo docker rm -f gemma-current-sglang >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name gemma-current-sglang --gpus all --ipc=host --network host -v "$root:/work" "$image" \
  python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 >"$out/container-id"
for _ in $(seq 1 180); do
  curl -fsS http://127.0.0.1:30000/v1/models >"$out/models.json" 2>"$out/models.stderr" && break
  sleep 5
done
test -s "$out/models.json" || { atomic "$out/WORKER_TERMINAL.json" startup_timeout 'SGLang did not become ready'; exit 70; }
sudo docker logs gemma-current-sglang >"$out/server-startup.log" 2>&1
curl -fsS http://127.0.0.1:30000/metrics >"$out/preflight-metrics.prom"
state candidate_science_started
python3 "$input/current-sglang/exact_c32_runner.py" --output "$out/exact-c32" --arm current_sglang_dynamic_fp8_c32
python3 - "$out/exact-c32/TERMINAL.json" "$out/WORKER_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
x=json.load(open(sys.argv[1]));p=pathlib.Path(sys.argv[2]);q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':'measured_endpoint' if x['pass'] else 'endpoint_gate_failure','terminal':x},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
