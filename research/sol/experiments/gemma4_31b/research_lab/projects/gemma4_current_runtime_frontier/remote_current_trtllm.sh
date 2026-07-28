#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-current-trtllm
checkpoint=/home/glmrunner/gemma4-current-sglang/checkpoint
input="$root/input"
out="$root/artifacts/current-trtllm-c32-r2"
image='nvcr.io/nvidia/tensorrt-llm/release:1.2.0@sha256:7202108ab373557e0562f78ef3c0f65bdc70e18cc0b040c8d6805a5cde897a0d'
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
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part');v=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'candidate_science_started':False};v[sys.argv[2]]=True;q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}

finish() {
  rc=$?
  sudo docker logs gemma-current-trtllm >"$out/server.log" 2>&1 || true
  sudo docker inspect gemma-current-trtllm >"$out/server.inspect.json" 2>&1 || true
  test -f "$out/WORKER_TERMINAL.json" || atomic "$out/WORKER_TERMINAL.json" integration_failure "remote exit $rc"
  exit "$rc"
}
trap finish EXIT

(cd "$input" && sha256sum -c INPUTS.sha256)
sudo docker pull "$image" >"$out/image-pull.log" 2>&1 || true
sudo docker image inspect "$image" >"$out/image-inspect.json"
sudo docker run --rm --gpus all "$image" trtllm-serve --help >"$out/trtllm-serve-help.txt" 2>&1
sha256sum "$out/trtllm-serve-help.txt" >"$out/trtllm-serve-help.sha256"
sudo docker rm -f gemma-current-trtllm >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name gemma-current-trtllm --gpus all --ipc=host --network host -v "$root:/work" -v "$checkpoint:/work/checkpoint:ro" "$image" \
  trtllm-serve /work/checkpoint --host 0.0.0.0 --port 30000 --backend pytorch --dtype bfloat16 \
  --kv_cache_dtype fp8 --max_batch_size 32 --max_num_tokens 5000 --max_seq_len 5000 >"$out/container-id"
for _ in $(seq 1 180); do
  curl -fsS http://127.0.0.1:30000/v1/models >"$out/models.json" 2>"$out/models.stderr" && break
  sleep 5
done
test -s "$out/models.json" || { atomic "$out/WORKER_TERMINAL.json" startup_timeout 'standalone TensorRT-LLM did not become ready'; exit 70; }
sudo docker logs gemma-current-trtllm >"$out/server-startup.log" 2>&1
curl -fsS http://127.0.0.1:30000/metrics >"$out/preflight-metrics.prom" || true
python3 - "$out/TRTLLM_CONSUMER.json" "$out/image-inspect.json" "$out/models.json" "$out/trtllm-serve-help.sha256" <<'PY'
import hashlib,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part')
q.write_text(json.dumps({'runtime':'standalone TensorRT-LLM','server_command':'trtllm-serve','image_inspect_sha256':hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest(),'models_sha256':hashlib.sha256(pathlib.Path(sys.argv[3]).read_bytes()).hexdigest(),'help_sha256':pathlib.Path(sys.argv[4]).read_text().strip()},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
state candidate_science_started
sudo docker exec gemma-current-trtllm python3 /work/input/current-sglang/exact_c32_runner.py --output /work/artifacts/current-trtllm-c32-r2/exact-c32 --arm standalone_current_tensorrt_llm_fp8_c32
python3 - "$out/exact-c32/TERMINAL.json" "$out/WORKER_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
x=json.load(open(sys.argv[1]));p=pathlib.Path(sys.argv[2]);q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':'measured_endpoint' if x['pass'] else 'endpoint_gate_failure','terminal':x},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
