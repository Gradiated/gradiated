#!/usr/bin/env bash
set -Eeuo pipefail

mode=${1:?mode required}
root=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination
input="$root/input"
artifacts="$root/residual-h2d-artifacts"
container_artifacts=/work/residual-h2d-artifacts
if [[ "$mode" == pair || "$mode" == candidate_trace ]]; then
  artifacts="$root/residual-h2d-pair-artifacts"
  container_artifacts=/work/residual-h2d-pair-artifacts
fi
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v={'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v=json.loads(p.read_text()) if p.exists() else {'trace_cuda_started':False,'trace_science_started':False,'candidate_cuda_started':False,'candidate_science_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

compact() {
  set +e
  for container in residual-h2d-trace residual-h2d-control residual-h2d-candidate residual-h2d-prediction; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    --exclude='*.nsys-rep' --exclude='*.sqlite' -czf "$artifacts/compact.tar.gz" -C "$artifacts" .
  sha256sum "$artifacts/compact.tar.gz" >"$artifacts/compact.tar.gz.sha256"
}

trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"

base_args=(
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint
  --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking
  --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1
  --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8
)

validate_terminal() {
  python3 - "$1" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('pass') is True and x.get('complete_requests') == 32 and len(x.get('rows',[])) == 32
assert x.get('cache',{}).get('cached_prompt_tokens_delta') == 17120
assert x.get('cache',{}).get('uncached_prompt_tokens_delta') == 117728
PY
}

validate_frontier() {
  python3 - "$1" <<'PY'
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
assert any(x.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' and x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==256 and x.get('v_head_dim')==256 and x.get('sliding_window_size')==1024 for x in rows)
assert any(x.get('candidate_path')=='ScheduleBatch.prepare_for_decode.pinned_async_penalty_tokens' and x.get('phase')=='runtime_invocation' and x.get('batch_size')==32 and x.get('dtype')=='torch.int64' and x.get('pin_memory') is True and x.get('non_blocking') is True for x in rows)
assert any(x.get('candidate_path')=='BatchedMinNewTokensPenalizer.host_required_dense_add' and x.get('phase')=='runtime_invocation' and x.get('host_counter') is True and x.get('no_device_scalar_read') is True for x in rows)
assert any(x.get('candidate_path')=='create_flashinfer_kv_indices_triton.producer_fused_swa_mapping' and x.get('phase')=='runtime_invocation' and x.get('batch_size')==32 and x.get('block_size')==512 and x.get('graph_safe') is True and x.get('device_count_proportional') is True and x.get('no_capacity_wide_second_pass') is True and x.get('no_device_scalar_read') is True for x in rows)
PY
}

test -s "$input/sitecustomize.py" || fail sitecustomize_missing
test -s "$input/residual_intervention.py" || fail producer_fused_intervention_missing
test -s "$input/attention_intervention.py" || fail attention_intervention_missing
test -s "$input/pinned_async_penalty_tokens.py" || fail pinned_intervention_missing
test -s "$input/host_min_new_tokens_gate.py" || fail dense_intervention_missing

start_server() {
  local arm=$1 container=$2 profiled=$3
  local runtime_arm=${4:-$arm}
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  local command=(python3 /work/input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}")
  local profile_env=()
  if [[ "$profiled" == yes ]]; then
    command=(
      nsys profile --trace=cuda,nvtx --sample=process-tree
      --cudabacktrace=memory:0,sync:10000000 --python-backtrace=cuda
      --capture-range=cudaProfilerApi --capture-range-end=stop-shutdown
      --force-overwrite=true -o /work/residual-h2d-pair-artifacts/prediction
      "${command[@]}"
    )
    profile_env=(-e PROFILE_SIGNAL_AUDIT=/work/residual-h2d-pair-artifacts/prediction-profile-signals.jsonl)
  fi
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e QKV_EPILOGUE_AUDIT="$container_artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="$container_artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="$container_artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="$container_artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    -e RESIDUAL_ARM="$runtime_arm" \
    -e RESIDUAL_CANDIDATE_AUDIT="$container_artifacts/$arm-audit/residual.jsonl" \
    "${profile_env[@]}" "$image" "${command[@]}" >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then
      ready=1
      break
    fi
    if sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q false; then
      break
    fi
    sleep 5
  done
  sudo docker logs "$container" >"$artifacts/$arm.server-start.log" 2>&1 || true
  [[ "$ready" -eq 1 ]] || fail "$arm.server_not_ready"
  python3 - "$artifacts/$arm.smoke.json" <<'PY' || fail "$arm.smoke_failed"
import json,sys,urllib.request
rows=[]
for want,prompt in [('READY','Reply with exactly: READY'),('4','What is 2+2? Reply with only the number.'),('json','Return only a JSON object with key "status" and string value "ok".')]:
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    value=raw['choices'][0]['message']['content'].strip()
    ok=value==want if want!='json' else json.loads(value.strip('`json\n'))=={'status':'ok'}
    rows.append({'want':want,'text':value,'pass':ok})
out={'rows':rows,'pass':all(row['pass'] for row in rows)}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n')
assert out['pass']
PY
}

run_exact() {
  local arm=$1 container=$2 label=$3
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/input/fp8_qkv_paired_runner.py \
    --output "$container_artifacts/$arm" --arm "$label" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  validate_terminal "$artifacts/$arm/TERMINAL.json" || fail "$arm.terminal_invalid"
}

validate_candidate_path() {
  python3 - "$1" <<'PY'
import json,pathlib,sys
rows=[json.loads(line) for line in pathlib.Path(sys.argv[1]).read_text().splitlines() if line]
installed=any(
    row.get('candidate_path')=='write_cache_indices.pinned_async_prefix_pointer_h2d'
    and row.get('phase')=='installation_complete'
    and row.get('source_sha256')=='987c02d71dd773d32263d6d34d94d508b74c707e0ca3d918723e981088bb14a9'
    and row.get('layout_change') is False
    and row.get('dtype_change') is False
    and row.get('synchronization_added') is False
    for row in rows
)
runtime=[
    row for row in rows
    if row.get('candidate_path')=='write_cache_indices.pinned_async_prefix_pointer_h2d'
    and row.get('phase')=='runtime_invocation'
]
assert installed and runtime
assert {row.get('bytes') for row in runtime}.issubset({8,16})
assert {row.get('batch_size') for row in runtime}.issubset({1,2})
assert all(
    row.get('dtype')=='torch.uint64'
    and row.get('pin_memory') is True
    and row.get('non_blocking') is True
    and row.get('consumer')=='write_req_to_token_pool_triton'
    for row in runtime
)
PY
}

if [[ "$mode" == pair ]]; then
  test -s "$input/pinned_prefix_pointer_h2d.py" || fail candidate_intervention_missing
  if ! validate_terminal "$artifacts/control/TERMINAL.json" 2>/dev/null; then
    python3 - "$artifacts/INVOCATION_STATE.json" <<'PY' || fail consumed_control_missing_terminal
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text()) if p.exists() else {}
assert not x.get('control_science_started')
PY
    rm -rf "$artifacts/control" "$artifacts/control-audit"
    start_server control residual-h2d-control no
    run_exact control residual-h2d-control residual_h2d_contemporaneous_control
    validate_frontier "$artifacts/control-audit/residual.jsonl" || fail control_frontier_proof_missing
  fi
  sudo docker rm -f residual-h2d-control >/dev/null 2>&1 || true
  if ! validate_terminal "$artifacts/candidate/TERMINAL.json" 2>/dev/null; then
    python3 - "$artifacts/INVOCATION_STATE.json" <<'PY' || fail consumed_candidate_missing_terminal
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text()) if p.exists() else {}
assert not x.get('candidate_science_started')
PY
    rm -rf "$artifacts/candidate" "$artifacts/candidate-audit"
    start_server candidate residual-h2d-candidate no
    run_exact candidate residual-h2d-candidate residual_h2d_pinned_prefix_pointer_candidate
    validate_frontier "$artifacts/candidate-audit/residual.jsonl" || fail candidate_frontier_proof_missing
    validate_candidate_path "$artifacts/candidate-audit/residual.jsonl" || fail candidate_path_proof_missing
  fi
  sudo docker rm -f residual-h2d-candidate >/dev/null 2>&1 || true
  python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIR_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
control=json.load(open(sys.argv[1])); candidate=json.load(open(sys.argv[2])); output=pathlib.Path(sys.argv[3])
c=float(control['service_seconds_per_request']); q=float(candidate['service_seconds_per_request']); reduction=1-q/c
classification='promote_ceiling' if q<=0.6381105231 else ('retain_simple_gain' if q<c else 'close_pinned_prefix_pointer_h2d')
value={
  'schema_version':1,'status':'producer_persisted','classification':classification,'pass':True,
  'control':control,'candidate':candidate,'control_service_seconds_per_request':c,
  'candidate_service_seconds_per_request':q,'reduction_fraction':reduction,
  'economic_ceiling_seconds_per_request':0.6381105231,'ceiling_pass':q<=0.6381105231,
  'candidate_path':'write_cache_indices.pinned_async_prefix_pointer_h2d',
  'candidate_source_sha256':'987c02d71dd773d32263d6d34d94d508b74c707e0ca3d918723e981088bb14a9',
}
part=output.with_suffix('.part'); part.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(part,output)
PY
  atomic_terminal pair_complete profiler_off_c32_control_candidate_persisted
  exit 0
elif [[ "$mode" == candidate_trace ]]; then
  test -s "$artifacts/PAIR_TERMINAL.json" || fail persisted_pair_missing
  test -s "$input/pinned_prefix_pointer_h2d.py" || fail candidate_intervention_missing
  rm -rf "$artifacts/prediction" "$artifacts/prediction-audit"
  rm -f "$artifacts/prediction.nsys-rep" "$artifacts/prediction.sqlite"
  start_server prediction residual-h2d-prediction yes candidate
  sudo docker exec residual-h2d-prediction sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR1 "$pid"' || fail prediction.profiler_start_failed
  sleep 1
  run_exact prediction residual-h2d-prediction residual_h2d_candidate_prediction_trace
  sudo docker exec residual-h2d-prediction sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR2 "$pid"' || fail prediction.profiler_stop_failed
  for _ in $(seq 1 180); do
    sudo docker inspect -f '{{.State.Running}}' residual-h2d-prediction 2>/dev/null | grep -q false && break
    sleep 1
  done
  sudo docker stop -t 30 residual-h2d-prediction >/dev/null 2>&1 || true
  test -s "$artifacts/prediction.nsys-rep" || fail prediction.profiler_report_missing
  sudo docker run --rm -v "$root:/work" "$image" nsys export --type sqlite --force-overwrite=true \
    --output /work/residual-h2d-pair-artifacts/prediction.sqlite \
    /work/residual-h2d-pair-artifacts/prediction.nsys-rep \
    >"$artifacts/prediction.nsys-export.stdout" 2>"$artifacts/prediction.nsys-export.stderr" || fail prediction.profiler_export_failed
  validate_frontier "$artifacts/prediction-audit/residual.jsonl" || fail prediction.frontier_proof_missing
  validate_candidate_path "$artifacts/prediction-audit/residual.jsonl" || fail prediction.candidate_path_proof_missing
  atomic_terminal trace_complete candidate_prediction_trace_persisted
  exit 0
elif [[ "$mode" != trace ]]; then
  fail unsupported_mode
fi

sudo docker rm -f residual-h2d-trace residual-h2d-control residual-h2d-candidate residual-profile residual-control residual-candidate residual-sync-trace >/dev/null 2>&1 || true
rm -rf "$artifacts/trace" "$artifacts/trace-audit"
rm -f "$artifacts/current-frontier.nsys-rep" "$artifacts/current-frontier.sqlite"
sudo docker run --rm "$image" nsys profile --help >"$artifacts/nsys-profile-help.txt" 2>"$artifacts/nsys-profile-help.stderr" || fail nsys_help_failed
grep -q -- '--python-backtrace=' "$artifacts/nsys-profile-help.txt" || fail nsys_python_backtrace_unsupported
grep -q -- '--cudabacktrace=' "$artifacts/nsys-profile-help.txt" || fail nsys_cuda_backtrace_unsupported

state trace_cuda_started
command=(
  nsys profile --trace=cuda,nvtx --sample=process-tree
  --cudabacktrace=memory:0,sync:10000000 --python-backtrace=cuda
  --capture-range=cudaProfilerApi --capture-range-end=stop-shutdown
  --force-overwrite=true -o /work/residual-h2d-artifacts/current-frontier
  python3 /work/input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}"
)
sudo docker run -d --name residual-h2d-trace --gpus all --ipc=host --network host \
  -v "$root:/work" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e QKV_EPILOGUE_AUDIT="$container_artifacts/trace-audit/qkv.jsonl" \
  -e FP8_MODULE_AUDIT="$container_artifacts/trace-audit/modules.jsonl" \
  -e FP8_CONSUMER_AUDIT="$container_artifacts/trace-audit/consumers.jsonl" \
  -e FP8_RUNTIME_AUDIT="$container_artifacts/trace-audit/runtime.json" \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  -e RESIDUAL_ARM=control -e RESIDUAL_CANDIDATE_AUDIT="$container_artifacts/trace-audit/residual.jsonl" \
  -e PROFILE_SIGNAL_AUDIT="$container_artifacts/profile-signals.jsonl" \
  "$image" "${command[@]}" >"$artifacts/trace.container-id"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/trace.models.json" 2>"$artifacts/trace.models.stderr"; then
    ready=1
    break
  fi
  if sudo docker inspect -f '{{.State.Running}}' residual-h2d-trace 2>/dev/null | grep -q false; then
    break
  fi
  sleep 5
done
sudo docker logs residual-h2d-trace >"$artifacts/trace.server-start.log" 2>&1 || true
[[ "$ready" -eq 1 ]] || fail trace.server_not_ready

python3 - "$artifacts/trace.smoke.json" <<'PY' || fail trace.smoke_failed
import json,sys,urllib.request
rows=[]
for want,prompt in [('READY','Reply with exactly: READY'),('4','What is 2+2? Reply with only the number.'),('json','Return only a JSON object with key "status" and string value "ok".')]:
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    text=raw['choices'][0]['message']['content'].strip()
    ok=text==want if want!='json' else json.loads(text.strip('`json\n'))=={'status':'ok'}
    rows.append({'want':want,'text':text,'pass':ok})
out={'rows':rows,'pass':all(row['pass'] for row in rows)}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n')
assert out['pass']
PY

sudo docker exec residual-h2d-trace sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR1 "$pid"' || fail profiler_start_signal_failed
sleep 1
state trace_science_started
sudo docker exec residual-h2d-trace python3 /work/input/fp8_qkv_paired_runner.py \
  --output "$container_artifacts/trace" --arm fp8_qkv_producer_fused_current_frontier_trace --concurrency 32 \
  >"$artifacts/trace.runner.stdout" 2>"$artifacts/trace.runner.stderr" || fail trace.runner_failed
validate_terminal "$artifacts/trace/TERMINAL.json" || fail trace.terminal_invalid
sudo docker exec residual-h2d-trace sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR2 "$pid"' || fail profiler_stop_signal_failed
for _ in $(seq 1 180); do
  sudo docker inspect -f '{{.State.Running}}' residual-h2d-trace 2>/dev/null | grep -q false && break
  sleep 1
done
sudo docker stop -t 30 residual-h2d-trace >/dev/null 2>&1 || true
test -s "$artifacts/current-frontier.nsys-rep" || fail profiler_report_missing
sudo docker run --rm -v "$root:/work" "$image" nsys export --type sqlite --force-overwrite=true \
  --output /work/residual-h2d-artifacts/current-frontier.sqlite \
  /work/residual-h2d-artifacts/current-frontier.nsys-rep \
  >"$artifacts/nsys-export.stdout" 2>"$artifacts/nsys-export.stderr" || fail profiler_export_failed
validate_frontier "$artifacts/trace-audit/residual.jsonl" || fail current_frontier_path_proof_missing
atomic_terminal trace_complete current_frontier_sync_trace_persisted
