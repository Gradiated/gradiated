#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-qserve-endpoint
trace=$(cd "$(dirname "$0")" && pwd)
out="$root/artifacts/qserve-causal-trace"
checkpoint="$root/checkpoint"
qserve=/home/glmrunner/gemma4-qserve-bf16/runs/8828d463cf965bab69e4eb1890c38a6ab713a6f555a5e4388ec1601472efb08a
endpoint="$root/input"
image='docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
container=gemma-qserve-bf16-endpoint
mkdir -p "$out"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]);q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'classification':sys.argv[2],'message':sys.argv[3],'epoch':time.time()},indent=2,sort_keys=True)+'\n')
os.replace(q,p)
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
    atomic "$out/WORKER_TERMINAL.json" integration_failure "causal trace worker exit $rc"
  fi
  exit "$rc"
}
trap finish EXIT

python3 "$trace/verify_trace.py" \
  --root "$trace" \
  --manifest "$trace/TRACE_INPUT_MANIFEST.json" \
  >"$out/input-verification.json"
cd "$checkpoint"
sha256sum -c "$endpoint/CHECKPOINT.sha256" >"$out/checkpoint-verification.log"
cd "$endpoint"
sha256sum -c ENDPOINT.sha256 >"$out/endpoint-verification.log"
find "$root/w4_cache/d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2" \
  -maxdepth 1 -type f -name '*.pt' | wc -l >"$out/w4-cache-count.txt"
test "$(cat "$out/w4-cache-count.txt")" = 180
nvidia-smi --query-gpu=timestamp,name,uuid,memory.used,memory.total,utilization.gpu,power.draw --format=csv,noheader >"$out/gpu-before.csv"
sudo docker inspect "$container" >"$out/resident-server-before.inspect.json"
sudo docker logs "$container" >"$out/resident-server-before.log" 2>&1

python3 - "$out/TRACE_CONTROL.json" <<'PY'
import json,os,pathlib
p=pathlib.Path(__import__('sys').argv[1]);q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'run_id':'startup','depth':60,'capture_layer':-1,'capture_step':-1},sort_keys=True)+'\n')
os.replace(q,p)
PY

sudo docker rm -f "$container" >"$out/resident-server-replaced.txt"
sudo docker run -d \
  --name "$container" \
  --gpus all \
  --ipc=host \
  --network host \
  -e "PYTHONPATH=/trace:$qserve/inputs/bf16_epilogue/qserve_sm89" \
  -e "QSERVE_W4_CACHE=/work/w4_cache/d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2" \
  -e "QSERVE_EVENT_LOG=/work/artifacts/qserve-causal-trace/qserve-events.jsonl" \
  -e "QSERVE_TRACE_CONTROL=/work/artifacts/qserve-causal-trace/TRACE_CONTROL.json" \
  -e "QSERVE_TRACE_EVENTS=/work/artifacts/qserve-causal-trace/trace-events.jsonl" \
  -e "QSERVE_TRACE_CAPTURE=/work/artifacts/qserve-causal-trace/captured-hidden.pt" \
  -v "$root:/work" \
  -v "$trace:/trace:ro" \
  -v "$endpoint:/endpoint:ro" \
  -v "$qserve:$qserve:ro" \
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
  --disable-cuda-graph \
  --prefill-attention-backend triton \
  --decode-attention-backend triton \
  --page-size 1 >"$out/container-id"

for _ in $(seq 1 720); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$out/models.json" 2>"$out/models.stderr"; then
    break
  fi
  if ! sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -qx true; then
    atomic "$out/WORKER_TERMINAL.json" model_startup_failure "trace server exited before model probe"
    exit 70
  fi
  sleep 5
done
test -s "$out/models.json" || {
  atomic "$out/WORKER_TERMINAL.json" model_startup_timeout "trace server did not become ready"
  exit 70
}

printf '%s\n' "$(date -u +%FT%TZ)" >"$out/TRACE_SCIENCE_STARTED.txt"
sudo docker exec "$container" python3 /trace/trace_runner.py \
  >"$out/trace-runner.stdout" 2>"$out/trace-runner.stderr"
sudo docker exec \
  -e "PYTHONPATH=$qserve/inputs/bf16_epilogue/qserve_sm89" \
  "$container" python3 /trace/oracle_compare.py \
  >"$out/oracle.stdout" 2>"$out/oracle.stderr"
set +e
sudo docker exec "$container" python3 /trace/finalize_trace.py \
  >"$out/finalize.stdout" 2>"$out/finalize.stderr"
finalize_rc=$?
set -e
cp "$out/TERMINAL.json" "$out/WORKER_TERMINAL.json"
capture
exit "$finalize_rc"
