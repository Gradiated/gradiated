#!/usr/bin/env bash
set -Eeuo pipefail

root=${STATIC_C32_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
checkpoint="$root/checkpoint"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-static-c32-supergraph
port=30001
mkdir -p "$artifacts" "$root/cache"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+".part")
x={"schema_version":2,"status":"terminal","classification":sys.argv[2],"message":sys.argv[3],"unix_s":time.time()}
q.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n"); os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+".part")
x=json.loads(p.read_text()) if p.exists() else {
 "candidate_component_started":False,
 "candidate_component_cuda_started":False,
 "stock_control_capture_started":False,
 "candidate_endpoint_started":False,
}
x[sys.argv[2]]=True; x["updated_unix_s"]=time.time()
q.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n"); os.replace(q,p)
PY
}

collect() {
  set +e
  if [[ -s "$artifacts/component-supergraph.audit.jsonl" ]] && \
    grep -F '"event": "supergraph_capture_started"' \
      "$artifacts/component-supergraph.audit.jsonl" >/dev/null; then
    state candidate_component_cuda_started
  fi
  sudo docker logs "$container" >"$artifacts/server-last.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/server-last.inspect.json" 2>&1 || true
  nvidia-smi --query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw \
    --format=csv,noheader >"$artifacts/gpu-final.csv" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/static-c32-supergraph-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/static-c32-supergraph-compact.tar.gz" \
    >"$root/static-c32-supergraph-compact.tar.gz.sha256"
}
trap collect EXIT
trap 'atomic_terminal integration_failure "unexpected:$BASH_COMMAND"' ERR

fail() {
  sudo docker logs "$container" >"$artifacts/server-failure.log" 2>&1 || true
  atomic_terminal integration_failure "$1"
  exit 1
}

test -r "$checkpoint/model.safetensors.index.json" || fail checkpoint_missing
test "$(sha256sum "$checkpoint/model.safetensors.index.json" | awk '{print $1}')" \
  = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2 \
  || fail checkpoint_identity
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 \
  || fail pinned_image_missing
find "$input" -maxdepth 3 -type f -print0 | sort -z | xargs -0 sha256sum \
  >"$artifacts/input-sha256.txt"
sudo docker rm -f "$container" gemma-static-c32 >/dev/null 2>&1 || true
for _ in $(seq 1 60); do
  [[ "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l)" -eq 0 ]] && break
  sleep 2
done
[[ "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l)" -eq 0 ]] \
  || fail incompatible_retained_server_owns_gpu

start_server() {
  local arm=$1
  local stage=$2
  local target=$3
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/static-c32" \
    -e PYTHONPATH=/work/static-c32/input:/work/static-c32/input/stack:/sgl-workspace/sglang/python \
    -e STACKED_FRONTIER_ARM=candidate -e RING_CACHE_ARM=candidate \
    -e STATIC_C32_ARM="$arm" -e STATIC_C32_TARGET="$target" \
    -e STATIC_C32_AUDIT="/work/static-c32/artifacts/$stage.audit.jsonl" \
    -e STATIC_C32_SUMMARY="/work/static-c32/artifacts/$stage.summary.json" \
    -e RING_CACHE_AUDIT="/work/static-c32/artifacts/$stage.ring.jsonl" \
    -e RING_CACHE_TRACE_TRANSITIONS=0 \
    -e RESIDUAL_CANDIDATE_AUDIT="/work/static-c32/artifacts/$stage.residual.jsonl" \
    -e QKV_EPILOGUE_AUDIT="/work/static-c32/artifacts/$stage.qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/static-c32/artifacts/$stage.modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/static-c32/artifacts/$stage.consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/static-c32/artifacts/$stage.runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/static-c32/input/stack/proven_v0513_endpoint_entrypoint.py \
      --model-path /work/checkpoint --tokenizer-path /work/checkpoint \
      --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 \
      --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port "$port" \
      --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 \
      --enable-metrics --skip-server-warmup --enable-dynamic-chunking \
      --chunked-prefill-size 2048 --enable-fused-qk-norm-rope \
      --cuda-graph-max-bs 32 --prefill-attention-backend triton \
      --decode-attention-backend triton --page-size 1 \
      --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 \
      --disable-overlap-schedule >"$artifacts/$stage.container-id"

  ready=0
  for _ in $(seq 1 240); do
    if curl -fsS "http://127.0.0.1:$port/v1/models" \
      >"$artifacts/$stage.models.json" 2>"$artifacts/$stage.models.stderr"; then
      ready=1
      break
    fi
    [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]] || break
    sleep 4
  done
  sudo docker logs "$container" >"$artifacts/$stage.server.log" 2>&1 || true
  [[ "$ready" == 1 ]] || fail "$stage.server_not_ready"
  sudo docker inspect "$container" >"$artifacts/$stage.container-inspect.json"
  grep -F -- "--disable-overlap-schedule" \
    "$artifacts/$stage.container-inspect.json" >/dev/null \
    || fail "$stage.overlap_identity_not_proven"
  grep -F '"event": "static_c32_supergraph_installed"' \
    "$artifacts/$stage.audit.jsonl" >/dev/null \
    || fail "$stage.supergraph_executor_not_installed"
}

run_workload() {
  local stage=$1
  local tokens=$2
  sudo docker exec "$container" python3 /work/static-c32/input/run_exact_workload.py \
    --output "/work/static-c32/artifacts/$stage.runner" \
    --arm "$stage" --output-tokens "$tokens" \
    >"$artifacts/$stage.runner.stdout" 2>"$artifacts/$stage.runner.stderr"
}

if [[ ! -s "$artifacts/component-supergraph.summary.json" ]]; then
  state candidate_component_started
  start_server candidate component-supergraph 22
  run_workload component-supergraph 64 || fail component_candidate_runner
  [[ -s "$artifacts/component-supergraph.summary.json" ]] \
    || fail component_candidate_summary_missing
fi
if grep -F '"event": "supergraph_capture_started"' \
  "$artifacts/component-supergraph.audit.jsonl" >/dev/null; then
  state candidate_component_cuda_started
fi

set +e
python3 "$input/analyze_static_c32.py" supergraph-component \
  --candidate "$artifacts/component-supergraph.summary.json" \
  --candidate-runner "$artifacts/component-supergraph.runner/TERMINAL.json" \
  --output "$artifacts/COMPONENT_RESULT.json"
component_rc=$?
set -e
if [[ "$component_rc" -eq 20 ]]; then
  atomic_terminal component_reject component_gate_failed
  exit 0
elif [[ "$component_rc" -ne 0 ]]; then
  fail component_analyzer
fi

if [[ ! -s "$artifacts/control-freeze.summary.json" ]]; then
  state stock_control_capture_started
  start_server control control-freeze 358
  run_workload control-freeze 358 || fail control_freeze_runner
  [[ -s "$artifacts/control-freeze.summary.json" ]] \
    || fail control_freeze_summary_missing
fi

python3 - "$artifacts/control-freeze.summary.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["pass"] and len(x["rows"])==32
assert all(r["token_count"]==358 for r in x["rows"])
PY

state candidate_endpoint_started
start_server candidate candidate-endpoint 358
run_workload candidate-endpoint 358 || {
  atomic_terminal endpoint_invalid candidate_endpoint_runner_failed
  exit 0
}
[[ -s "$artifacts/candidate-endpoint.summary.json" ]] || {
  atomic_terminal endpoint_invalid candidate_endpoint_summary_missing
  exit 0
}

set +e
python3 "$input/analyze_static_c32.py" endpoint \
  --component "$artifacts/COMPONENT_RESULT.json" \
  --control "$artifacts/control-freeze.summary.json" \
  --candidate "$artifacts/candidate-endpoint.summary.json" \
  --runner "$artifacts/candidate-endpoint.runner/TERMINAL.json" \
  --gpu "$artifacts/candidate-endpoint.runner/gpu.csv" \
  --output "$artifacts/CANDIDATE_ENDPOINT_RESULT.json"
endpoint_rc=$?
set -e
if [[ "$endpoint_rc" -eq 20 ]]; then
  atomic_terminal endpoint_invalid candidate_endpoint_contract_failed
  exit 0
elif [[ "$endpoint_rc" -ne 0 ]]; then
  atomic_terminal endpoint_invalid candidate_endpoint_analyzer_failed
  exit 0
fi
atomic_terminal completed scientific_terminal_persisted
