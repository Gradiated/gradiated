#!/usr/bin/env bash
set -Eeuo pipefail

mode=${1:?mode required}
requested_mode=$mode
root=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination
input="$root/input"
artifacts="$root/artifacts"
container_artifacts=/work/artifacts
if [[ "$mode" == sync_pair ]]; then
  sudo docker rm -f streamk-component residual-profile residual-control residual-candidate gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  mode=pair
elif [[ "$mode" == iteration2_pair ]]; then
  artifacts="$root/iteration2-artifacts"
  container_artifacts=/work/iteration2-artifacts
  sudo docker rm -f residual-profile residual-control residual-candidate gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  mode=pair
elif [[ "$mode" == scheduler_pair_v2 ]]; then
  artifacts="$root/scheduler-rebind-artifacts"
  container_artifacts=/work/scheduler-rebind-artifacts
  sudo docker rm -f residual-profile residual-control residual-candidate residual-sync-trace gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  mode=pair
elif [[ "$mode" == scheduler_trace_v2 ]]; then
  artifacts="$root/scheduler-rebind-artifacts"
  container_artifacts=/work/scheduler-rebind-artifacts
  mode=scheduler_trace
elif [[ "$mode" == scheduler_candidate_repair ]]; then
  artifacts="$root/scheduler-repair-artifacts"
  container_artifacts=/work/scheduler-repair-artifacts
  sudo docker rm -f residual-profile residual-control residual-candidate residual-sync-trace gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  mode=scheduler_candidate
elif [[ "$mode" == scheduler_trace_repair ]]; then
  artifacts="$root/scheduler-repair-artifacts"
  container_artifacts=/work/scheduler-repair-artifacts
  mode=scheduler_trace
elif [[ "$mode" == attention_pair ]]; then
  artifacts="$root/attention-artifacts-v2"
  container_artifacts=/work/attention-artifacts-v2
  if [[ -f "$input/RESET_INVALID_ATTENTION_CONTROL.json" && -f "$artifacts/control/TERMINAL.json" && ! -f "$artifacts/candidate/TERMINAL.json" ]]; then
    rm -rf "$artifacts/invalid-control-stale-server"
    mv "$artifacts/control" "$artifacts/invalid-control-stale-server"
    rm -rf "$artifacts/control-audit"
    python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text())
x['control_cuda_started']=False; x['control_science_started']=False
p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
PY
    mv "$input/RESET_INVALID_ATTENTION_CONTROL.json" "$artifacts/RESET_INVALID_ATTENTION_CONTROL.consumed.json"
  fi
  mode=pair
elif [[ "$mode" == fp8_linear_pair ]]; then
  artifacts="$root/fp8-linear-artifacts"
  container_artifacts=/work/fp8-linear-artifacts
  sudo docker rm -f residual-profile residual-control residual-candidate gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  if [[ -f "$input/RESET_INVALID_FP8_CANDIDATE.json" && -f "$artifacts/control/TERMINAL.json" && ! -f "$artifacts/candidate/TERMINAL.json" ]]; then
    mkdir -p "$artifacts/invalid-candidate-pre-invocation-compile"
    for path in candidate-audit candidate.container-id candidate.models.json candidate.models.stderr candidate.runner.stdout candidate.runner.stderr candidate.server-start.log candidate.smoke.json residual-candidate.final.log residual-candidate.inspect.json; do
      [[ -e "$artifacts/$path" ]] && mv "$artifacts/$path" "$artifacts/invalid-candidate-pre-invocation-compile/"
    done
    python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text())
x['candidate_cuda_started']=False; x['candidate_science_started']=False
p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
PY
    mv "$input/RESET_INVALID_FP8_CANDIDATE.json" "$artifacts/RESET_INVALID_FP8_CANDIDATE.consumed.json"
  fi
  mode=pair
elif [[ "$mode" == global_attention_pair ]]; then
  artifacts="$root/global-attention-artifacts"
  container_artifacts=/work/global-attention-artifacts
  sudo docker rm -f residual-profile residual-control residual-candidate gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  mode=pair
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
v=json.loads(p.read_text()) if p.exists() else {'profile_cuda_started':False,'profile_science_started':False,'control_cuda_started':False,'control_science_started':False,'candidate_cuda_started':False,'candidate_science_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

compact() {
  set +e
  for container in residual-profile residual-control residual-candidate; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    --exclude='*.nsys-rep' --exclude='*.sqlite' -czf "$root/compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/compact.tar.gz" >"$root/compact.tar.gz.sha256"
}
trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"

if [[ "$requested_mode" == sync_pair ]]; then
  state validation_cuda_started
  sudo docker run --rm --gpus all -v "$root:/work" \
    -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e RESIDUAL_ARM=candidate \
    -e RESIDUAL_CANDIDATE_AUDIT=/work/artifacts/mutation-audit.jsonl \
    "$image" python3 /work/input/metadata_equivalence_test.py \
    --output /work/artifacts/METADATA_EQUIVALENCE_TEST.json \
    >"$artifacts/metadata-test.stdout" 2>"$artifacts/metadata-test.stderr" \
    || fail metadata_equivalence_test_failed
  python3 - "$artifacts/METADATA_EQUIVALENCE_TEST.json" <<'PY' \
    || fail metadata_equivalence_terminal_invalid
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True
assert {row['name'] for row in x.get('cases',[])} == {
    'empty', 'odd_lengths', 'cache_hit_reorder', 'page_boundary',
    'filter_merge', 'maximum_exact_workload',
    'cuda_graph_replay_dynamic_lengths'
}
PY
fi

if [[ "$requested_mode" == iteration2_pair ]]; then
  if ! python3 - "$artifacts/COMPONENT_TERMINAL.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('candidate_cuda_started') is True
PY
  then
    state component_cuda_started
    state component_science_started
    sudo docker run --rm --gpus all -v "$root:/work" \
      -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
      -e RESIDUAL_ARM=control \
      "$image" python3 /work/input/producer_fused_component.py \
      --output /work/iteration2-artifacts/COMPONENT_TERMINAL.json \
      >"$artifacts/component.stdout" 2>"$artifacts/component.stderr" \
      || fail producer_fused_component_failed
  fi
  python3 - "$artifacts/COMPONENT_TERMINAL.json" <<'PY' \
    || fail producer_fused_component_terminal_invalid
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True
assert x.get('geometry',{}).get('batch_size') == 32
assert x.get('geometry',{}).get('valid_indices') == 32768
assert x.get('complete_output_consumed') is True
assert {row['name'] for row in x.get('cases',[])} == {
    'odd_filter_merge', 'exact_c32', 'cuda_graph_dynamic_lengths'
}
PY
fi

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

start_server() {
  local arm=$1 container=$2 profiled=$3
  local runtime_arm=${4:-$arm}
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  local command=(python3 /work/input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}")
  local profile_env=()
  local scheduler_env=()
  if [[ "$requested_mode" == scheduler_pair_v2 || "$requested_mode" == scheduler_trace_v2 || "$requested_mode" == scheduler_candidate_repair || "$requested_mode" == scheduler_trace_repair ]]; then
    scheduler_env=(-e SCHEDULER_REBIND_STACKED=1)
  fi
  if [[ "$profiled" == yes ]]; then
    sudo docker run --rm "$image" sh -lc 'command -v nsys' >"$artifacts/nsys-path.txt" 2>"$artifacts/nsys-path.stderr" || fail nsys_not_in_pinned_image
    command=(nsys profile --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none --capture-range=cudaProfilerApi --capture-range-end=stop-shutdown --force-overwrite=true -o /work/artifacts/control-profile "${command[@]}")
    profile_env=(-e PROFILE_SIGNAL_AUDIT=/work/artifacts/control-profile-signals.jsonl)
  fi
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e QKV_EPILOGUE_AUDIT="$container_artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="$container_artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="$container_artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="$container_artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    -e RESIDUAL_ARM="$runtime_arm" -e RESIDUAL_CANDIDATE_AUDIT="$container_artifacts/$arm-audit/residual.jsonl" \
    "${profile_env[@]}" "${scheduler_env[@]}" "$image" "${command[@]}" >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then ready=1; break; fi
    sleep 5
  done
  sudo docker logs "$container" >"$artifacts/$arm.server-start.log" 2>&1 || true
  [[ "$ready" -eq 1 ]] || fail "$arm.server_not_ready"
  if [[ "$requested_mode" == scheduler_candidate_repair || "$requested_mode" == scheduler_trace_repair ]]; then
    python3 - "$audit/residual.jsonl" <<'PY' || fail "$arm.scheduler_installation_proof_missing"
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
assert any(
    row.get('candidate_path') == 'Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot'
    and row.get('phase') == 'installation_complete'
    and row.get('implementation_sha256') == '3b5aa497985a400c16189db8359a458d981adff66d8465c26a92ed54394414e6'
    and row.get('predecessor') == 'pinned_async_penalty_tokens'
    for row in rows
)
PY
  fi
  python3 - "$artifacts/$arm.smoke.json" <<'PY' || fail "$arm.smoke_failed"
import json,sys,urllib.request
rows=[]
for want,prompt in [('READY','Reply with exactly: READY'),('4','What is 2+2? Reply with only the number.'),('json','Return only a JSON object with key "status" and string value "ok".')]:
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    text=raw['choices'][0]['message']['content'].strip()
    ok=text==want if want!='json' else json.loads(text.strip('`json\n'))=={'status':'ok'}
    rows.append({'want':want,'text':text,'pass':ok})
out={'rows':rows,'pass':all(row['pass'] for row in rows)}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n'); assert out['pass']
PY
}

run_exact() {
  local arm=$1 container=$2 label=$3
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/input/fp8_qkv_paired_runner.py \
    --output "$container_artifacts/$arm" --arm "$label" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  python3 - "$artifacts/$arm/TERMINAL.json" <<'PY' || fail "$arm.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32 and len(x.get('rows',[])) == 32
assert x.get('cache',{}).get('cached_prompt_tokens_delta') == 17120
assert x.get('cache',{}).get('uncached_prompt_tokens_delta') == 117728
PY
}

validate_baseline_proofs() {
  local arm=$1
  python3 - "$artifacts/$arm-audit" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
modules=[json.loads(x) for x in (p/'modules.jsonl').read_text().splitlines() if x]
consumers=[json.loads(x) for x in (p/'consumers.jsonl').read_text().splitlines() if x]
qkv=[json.loads(x) for x in (p/'qkv.jsonl').read_text().splitlines() if x]
assert len(modules)==240 and consumers
assert qkv and all(x.get('candidate_symbol')=='_qkv_norm_rope_inplace_kernel' and x.get('dtype')=='torch.bfloat16' for x in qkv)
PY
}

validate_attention_proof() {
  local arm=$1
  python3 - "$artifacts/$arm-audit/residual.jsonl" <<'PY'
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
assert any(
    row.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit'
    and row.get('phase')=='runtime_invocation'
    and row.get('qk_head_dim')==256
    and row.get('v_head_dim')==256
    and row.get('sliding_window_size')==1024
    and row.get('removed_operations')==['k.clone','v.clone']
    for row in rows
)
PY
}

validate_retained_sync_proof() {
  local arm=$1
  python3 - "$artifacts/$arm-audit/residual.jsonl" <<'PY'
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
assert any(
    row.get('candidate_path')=='ScheduleBatch.prepare_for_decode.pinned_async_penalty_tokens'
    and row.get('phase')=='runtime_invocation'
    and row.get('batch_size')==32
    and row.get('dtype')=='torch.int64'
    and row.get('pin_memory') is True
    and row.get('non_blocking') is True
    for row in rows
)
assert any(
    row.get('candidate_path')=='BatchedMinNewTokensPenalizer.host_required_dense_add'
    and row.get('phase')=='runtime_invocation'
    and row.get('host_counter') is True
    and row.get('no_device_scalar_read') is True
    for row in rows
)
PY
}

validate_metadata_proof() {
  local arm=$1
  python3 - "$artifacts/$arm-audit/residual.jsonl" <<'PY'
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
assert any(
    row.get('candidate_path')=='update_sliding_window_buffer.device_count_masked_swa_gather'
    and row.get('phase')=='runtime_invocation'
    and row.get('batch_size')==32
    and row.get('graph_safe') is True
    and row.get('no_device_scalar_read') is True
    and row.get('valid_count_source')=='window_kv_indptr[batch_size] read inside Triton kernel'
    for row in rows
)
PY
}

validate_producer_fused_proof() {
  local arm=$1
  python3 - "$artifacts/$arm-audit/residual.jsonl" <<'PY'
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
assert any(
    row.get('candidate_path')=='create_flashinfer_kv_indices_triton.producer_fused_swa_mapping'
    and row.get('phase')=='runtime_invocation'
    and row.get('batch_size')==32
    and row.get('block_size')==512
    and row.get('graph_safe') is True
    and row.get('device_count_proportional') is True
    and row.get('no_capacity_wide_second_pass') is True
    and row.get('no_device_scalar_read') is True
    for row in rows
)
PY
}

validate_scheduler_proof() {
  local arm=$1
  python3 - "$artifacts/$arm-audit/residual.jsonl" <<'PY'
import json,pathlib,sys
rows=[json.loads(x) for x in pathlib.Path(sys.argv[1]).read_text().splitlines() if x]
expected={
    "sglang.srt.managers.schedule_batch":"b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459",
    "sglang.srt.managers.scheduler":"3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4",
    "sglang.srt.sampling.sampling_batch_info":"e7903417a4cab05294975d069555987e2720557dd9fd0b8d79a6f934f3fbb0db",
    "sglang.srt.sampling.penaltylib.orchestrator":"88d9a4c04866a8b2dad0efe6f010f28f7e7dfa0e65708920f7845d760e833192",
}
assert any(
    row.get("candidate_path")=="Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot"
    and row.get("phase")=="runtime_invocation"
    and row.get("ordering_edge")=="forward_stream.wait_stream(schedule_stream)"
    and row.get("lifetime")=="record_batch_in_overlap_two_iteration_ring"
    and row.get("source_sha256")==expected
    for row in rows
)
PY
}

if [[ "$mode" == sync_trace || "$mode" == scheduler_trace ]]; then
  sudo docker rm -f residual-profile residual-control residual-candidate residual-sync-trace >/dev/null 2>&1 || true
  rm -rf "$artifacts/trace" "$artifacts/trace-audit"
  rm -f "$artifacts/control-profile.nsys-rep" "$artifacts/control-profile.sqlite"
  start_server trace residual-sync-trace yes candidate
  sudo docker exec residual-sync-trace sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR1 "$pid"' || fail profiler_start_signal_failed
  sleep 1
  run_exact trace residual-sync-trace fp8_qkv_sync_trace_candidate
  sudo docker exec residual-sync-trace sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR2 "$pid"' || fail profiler_stop_signal_failed
  for _ in $(seq 1 120); do
    sudo docker inspect -f '{{.State.Running}}' residual-sync-trace 2>/dev/null | grep -q false && break
    sleep 1
  done
  sudo docker stop -t 30 residual-sync-trace >/dev/null 2>&1 || true
  test -s "$artifacts/control-profile.nsys-rep" || fail profiler_report_missing
  sudo docker run --rm -v "$root:/work" "$image" nsys export --type sqlite --force-overwrite=true \
    --output /work/artifacts/control-profile.sqlite /work/artifacts/control-profile.nsys-rep \
    >"$artifacts/nsys-export.stdout" 2>"$artifacts/nsys-export.stderr" || fail profiler_export_failed
  validate_baseline_proofs trace
  validate_attention_proof trace
  validate_retained_sync_proof trace
  if [[ "$requested_mode" == scheduler_trace_v2 || "$requested_mode" == scheduler_trace_repair ]]; then
    validate_producer_fused_proof trace
    validate_scheduler_proof trace
  else
    validate_metadata_proof trace
  fi
  atomic_terminal trace_complete exact_candidate_counter_trace_persisted
elif [[ "$mode" == profile ]]; then
  rm -rf "$artifacts/profile" "$artifacts/profile-audit"
  start_server profile residual-profile yes
  sudo docker exec residual-profile sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR1 "$pid"' || fail profiler_start_signal_failed
  sleep 1
  run_exact profile residual-profile fp8_qkv_profile_control
  sudo docker exec residual-profile sh -lc 'pid=$(pgrep -f "^/usr/bin/python3 /work/input/proven_v0513_endpoint_entrypoint.py" | head -n 1); test -n "$pid"; kill -USR2 "$pid"' || fail profiler_stop_signal_failed
  for _ in $(seq 1 120); do
    sudo docker inspect -f '{{.State.Running}}' residual-profile 2>/dev/null | grep -q false && break
    sleep 1
  done
  sudo docker stop -t 30 residual-profile >/dev/null 2>&1 || true
  test -s "$artifacts/control-profile.nsys-rep" || fail profiler_report_missing
  sudo docker run --rm -v "$root:/work" "$image" nsys export --type sqlite --force-overwrite=true \
    --output /work/artifacts/control-profile.sqlite /work/artifacts/control-profile.nsys-rep \
    >"$artifacts/nsys-export.stdout" 2>"$artifacts/nsys-export.stderr" || fail profiler_export_failed
  sudo docker run --rm -v "$root:/work" "$image" nsys stats --force-export=false --format csv \
    --report cuda_gpu_kern_sum,cuda_api_sum /work/artifacts/control-profile.nsys-rep \
    >"$artifacts/nsys-stats.csv" 2>"$artifacts/nsys-stats.stderr" || fail profiler_stats_failed
  validate_baseline_proofs profile
  atomic_terminal profile_complete exact_profile_control_persisted
elif [[ "$mode" == scheduler_candidate ]]; then
  test -s "$input/residual_intervention.py" || fail residual_intervention_missing
  test -s "$input/attention_intervention.py" || fail attention_intervention_missing
  test -s "$input/scheduler_intervention.py" || fail scheduler_intervention_missing
  test -s "$input/retained_control_terminal.json" || fail retained_control_terminal_missing
  python3 - "$input/retained_control_terminal.json" <<'PY' || fail retained_control_terminal_invalid
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
assert float(x['service_seconds_per_request']) == 0.6745249759062517
assert x['cache']['cached_prompt_tokens_delta'] == 17120 and x['cache']['uncached_prompt_tokens_delta'] == 117728
PY
  rm -rf "$artifacts/candidate" "$artifacts/candidate-audit"
  start_server candidate residual-candidate no
  run_exact candidate residual-candidate fp8_qkv_residual_candidate
  validate_baseline_proofs candidate
  validate_attention_proof candidate
  validate_retained_sync_proof candidate
  validate_producer_fused_proof candidate
  validate_scheduler_proof candidate
  python3 - "$input/retained_control_terminal.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" "$artifacts/candidate-audit/residual.jsonl" <<'PY'
import json,os,pathlib,sys
c=json.load(open(sys.argv[1])); q=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3]); proof=[json.loads(x) for x in pathlib.Path(sys.argv[4]).read_text().splitlines() if x]
control=float(c['service_seconds_per_request']); candidate=float(q['service_seconds_per_request']); gain=1-candidate/control
scheduler=any(x.get('candidate_path')=='Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot' and x.get('phase')=='runtime_invocation' and x.get('ordering_edge')=='forward_stream.wait_stream(schedule_stream)' and x.get('lifetime')=='record_batch_in_overlap_two_iteration_ring' for x in proof)
installation=any(x.get('candidate_path')=='Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot' and x.get('phase')=='installation_complete' and x.get('implementation_sha256')=='3b5aa497985a400c16189db8359a458d981adff66d8465c26a92ed54394414e6' and x.get('predecessor')=='pinned_async_penalty_tokens' for x in proof)
smoke=json.load(open(out.parent/'candidate.smoke.json'))
valid=bool(smoke.get('pass')) and scheduler and installation
classification='promote_ceiling' if valid and candidate<=0.6381105230769232 else ('retain_simple_positive' if valid and gain>0 else 'close_scheduler_overlap' if valid else 'invalid')
v={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'control':c,'candidate':q,'control_service_seconds_per_request':control,'candidate_service_seconds_per_request':candidate,'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105230769232,'ceiling_pass':valid and candidate<=0.6381105230769232,'retain_pass':valid and gain>0,'semantic_proof':smoke,'accounting_proof':{'control':c['cache'],'candidate':q['cache']},'candidate_path_proof':proof,'installation_proof':installation,'control_replayed':False}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
  atomic_terminal pair_complete repaired_candidate_scientific_terminal_persisted
elif [[ "$mode" == pair ]]; then
  test -s "$input/residual_intervention.py" || fail residual_intervention_missing
  test -s "$input/attention_intervention.py" || fail attention_intervention_missing
  if [[ "$requested_mode" == scheduler_pair_v2 ]]; then
    test -s "$input/scheduler_intervention.py" || fail scheduler_intervention_missing
  fi
  if [[ "$requested_mode" == sync_pair || "$requested_mode" == iteration2_pair || "$requested_mode" == scheduler_pair_v2 ]]; then
    sudo docker rm -f residual-profile residual-control residual-candidate gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  fi
  if ! python3 - "$artifacts/control/TERMINAL.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
PY
  then
    python3 - "$artifacts/INVOCATION_STATE.json" <<'PY' || fail consumed_control_missing_terminal
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text()) if p.exists() else {}
assert not x.get('control_science_started')
PY
    rm -rf "$artifacts/control" "$artifacts/control-audit"
    start_server control residual-control no
    run_exact control residual-control fp8_qkv_contemporaneous_control
    validate_baseline_proofs control
    validate_attention_proof control
    validate_retained_sync_proof control
    if [[ "$requested_mode" == scheduler_pair_v2 ]]; then
      validate_producer_fused_proof control
    fi
  fi
  sudo docker rm -f residual-control >/dev/null 2>&1 || true
  if ! python3 - "$artifacts/candidate/TERMINAL.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
PY
  then
    python3 - "$artifacts/INVOCATION_STATE.json" <<'PY' || fail consumed_candidate_missing_terminal
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text()) if p.exists() else {}
assert not x.get('candidate_science_started')
PY
    sudo rm -rf "$artifacts/candidate" "$artifacts/candidate-audit"
    start_server candidate residual-candidate no
    run_exact candidate residual-candidate fp8_qkv_residual_candidate
    validate_baseline_proofs candidate
    validate_attention_proof candidate
    validate_retained_sync_proof candidate
    if [[ "$requested_mode" == iteration2_pair ]]; then
      validate_producer_fused_proof candidate
    elif [[ "$requested_mode" == scheduler_pair_v2 ]]; then
      validate_producer_fused_proof candidate
      validate_scheduler_proof candidate
    else
      validate_metadata_proof candidate
    fi
  fi
  test -s "$artifacts/candidate-audit/residual.jsonl" || fail candidate_path_proof_missing
  python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" "$artifacts/control-audit/residual.jsonl" "$artifacts/candidate-audit/residual.jsonl" "$requested_mode" <<'PY'
import json,os,pathlib,sys
c=json.load(open(sys.argv[1])); q=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3]); control_proof=[json.loads(x) for x in pathlib.Path(sys.argv[4]).read_text().splitlines() if x]; proof=[json.loads(x) for x in pathlib.Path(sys.argv[5]).read_text().splitlines() if x]
control=float(c['service_seconds_per_request']); candidate=float(q['service_seconds_per_request']); gain=1-candidate/control
smoke=[json.load(open(out.parent/f'{arm}.smoke.json')) for arm in ('control','candidate')]
sync_mode=sys.argv[6] in {'sync_pair','iteration2_pair','scheduler_pair_v2'}
producer_fused=sys.argv[6]=='iteration2_pair'
scheduler_mode=sys.argv[6]=='scheduler_pair_v2'
path_ok=bool(proof)
if sync_mode:
    attention=lambda rows:any(x.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' and x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==256 and x.get('v_head_dim')==256 and x.get('sliding_window_size')==1024 for x in rows)
    pinned=lambda rows:any(x.get('candidate_path')=='ScheduleBatch.prepare_for_decode.pinned_async_penalty_tokens' and x.get('phase')=='runtime_invocation' and x.get('batch_size')==32 and x.get('dtype')=='torch.int64' and x.get('pin_memory') is True and x.get('non_blocking') is True for x in rows)
    dense=lambda rows:any(x.get('candidate_path')=='BatchedMinNewTokensPenalizer.host_required_dense_add' and x.get('phase')=='runtime_invocation' and x.get('host_counter') is True and x.get('no_device_scalar_read') is True for x in rows)
    if producer_fused or scheduler_mode:
        metadata=any(x.get('candidate_path')=='create_flashinfer_kv_indices_triton.producer_fused_swa_mapping' and x.get('phase')=='runtime_invocation' and x.get('batch_size')==32 and x.get('graph_safe') is True and x.get('device_count_proportional') is True and x.get('no_capacity_wide_second_pass') is True and x.get('no_device_scalar_read') is True for x in proof)
    else:
        metadata=any(x.get('candidate_path')=='update_sliding_window_buffer.device_count_masked_swa_gather' and x.get('phase')=='runtime_invocation' and x.get('batch_size')==32 and x.get('graph_safe') is True and x.get('no_device_scalar_read') is True for x in proof)
    control_metadata=any(x.get('candidate_path')=='create_flashinfer_kv_indices_triton.producer_fused_swa_mapping' and x.get('phase')=='runtime_invocation' for x in control_proof)
    scheduler=any(x.get('candidate_path')=='Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot' and x.get('phase')=='runtime_invocation' and x.get('ordering_edge')=='forward_stream.wait_stream(schedule_stream)' and x.get('lifetime')=='record_batch_in_overlap_two_iteration_ring' for x in proof)
    path_ok=attention(control_proof) and attention(proof) and pinned(control_proof) and pinned(proof) and dense(control_proof) and dense(proof) and metadata and (not scheduler_mode or (control_metadata and scheduler))
valid=all(x.get('pass') for x in smoke) and path_ok
classification='promote_ceiling' if valid and candidate<=0.6381105230769232 else ('retain_simple_positive' if valid and gain>0 else 'close_scheduler_overlap' if valid and scheduler_mode else 'close_producer_fused_translation' if valid and producer_fused else 'close_metadata_attempt' if valid and sync_mode else 'invalid')
component_name='COMPONENT_TERMINAL.json' if producer_fused else 'METADATA_EQUIVALENCE_TEST.json'
v={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'control':c,'candidate':q,'control_service_seconds_per_request':control,'candidate_service_seconds_per_request':candidate,'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105230769232,'ceiling_pass':valid and candidate<=0.6381105230769232,'retain_pass':valid and gain>0,'semantic_proof':smoke,'accounting_proof':{'control':c['cache'],'candidate':q['cache']},'fp8_proof':True,'qkv_proof':True,'attention_proof':{'control':control_proof,'candidate':proof},'candidate_path_proof':proof}
if not scheduler_mode:
    v['metadata_equivalence']=json.load(open(out.parent/component_name))
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
  atomic_terminal pair_complete paired_scientific_terminal_persisted
else
  fail unknown_mode
fi
