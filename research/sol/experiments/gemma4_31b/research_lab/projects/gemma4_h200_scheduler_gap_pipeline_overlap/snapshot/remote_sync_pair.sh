#!/usr/bin/env bash
set -Eeuo pipefail

mode=${1:?mode required}
requested_mode=$mode
root=/home/glmrunner/gemma4-h200-decode-sync-graph-elimination
input="$root/input"
artifacts="$root/artifacts"
container_artifacts=/work/artifacts
if [[ "$mode" == sync_pair ]]; then
  sudo docker rm -f residual-profile residual-control residual-candidate gemma-fp8-control-v0513 gemma-fp8-mtp-v0513 sglang-endpoint >/dev/null 2>&1 || true
  mode=pair
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
    "${profile_env[@]}" "$image" "${command[@]}" >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then ready=1; break; fi
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

validate_sync_proof() {
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
PY
}

if [[ "$mode" == sync_trace ]]; then
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
  validate_sync_proof trace
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
elif [[ "$mode" == pair ]]; then
  test -s "$input/residual_intervention.py" || fail residual_intervention_missing
  test -s "$input/attention_intervention.py" || fail attention_intervention_missing
  if [[ "$requested_mode" == sync_pair || "$requested_mode" == attention_pair || "$requested_mode" == fp8_linear_pair || "$requested_mode" == global_attention_pair ]]; then
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
    validate_sync_proof candidate
  fi
  test -s "$artifacts/candidate-audit/residual.jsonl" || fail candidate_path_proof_missing
  python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" "$artifacts/control-audit/residual.jsonl" "$artifacts/candidate-audit/residual.jsonl" "$requested_mode" <<'PY'
import json,os,pathlib,sys
c=json.load(open(sys.argv[1])); q=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3]); control_proof=[json.loads(x) for x in pathlib.Path(sys.argv[4]).read_text().splitlines() if x]; proof=[json.loads(x) for x in pathlib.Path(sys.argv[5]).read_text().splitlines() if x]
control=float(c['service_seconds_per_request']); candidate=float(q['service_seconds_per_request']); gain=1-candidate/control
smoke=[json.load(open(out.parent/f'{arm}.smoke.json')) for arm in ('control','candidate')]
attention_mode=sys.argv[6]=='attention_pair'
fp8_linear_mode=sys.argv[6]=='fp8_linear_pair'
global_attention_mode=sys.argv[6]=='global_attention_pair'
sync_mode=sys.argv[6]=='sync_pair'
path_ok=bool(proof)
if sync_mode:
    attention=lambda rows:any(x.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' and x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==256 and x.get('v_head_dim')==256 and x.get('sliding_window_size')==1024 for x in rows)
    sync_path=any(x.get('candidate_path')=='ScheduleBatch.prepare_for_decode.pinned_async_penalty_tokens' and x.get('phase')=='runtime_invocation' and x.get('batch_size')==32 and x.get('dtype')=='torch.int64' and x.get('pin_memory') is True and x.get('non_blocking') is True for x in proof)
    path_ok=attention(control_proof) and attention(proof) and sync_path
if attention_mode:
    path_ok=any(x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==256 and x.get('v_head_dim')==256 and x.get('sliding_window_size')==1024 and x.get('removed_operations')==['k.clone','v.clone'] for x in proof)
if fp8_linear_mode:
    attention=lambda rows:any(x.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' and x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==256 and x.get('v_head_dim')==256 and x.get('sliding_window_size')==1024 for x in rows)
    fp8_path=any(x.get('candidate_path')=='fp8_gate_up_exact_shape_64x256x128' and x.get('phase')=='runtime_invocation' and x.get('m',0)>128 and x.get('n')==43008 and x.get('k')==5376 and x.get('tile')==[64,256,128] for x in proof)
    path_ok=attention(control_proof) and attention(proof) and fp8_path
if global_attention_mode:
    attention=lambda rows:any(x.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' and x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==256 and x.get('v_head_dim')==256 and x.get('sliding_window_size')==1024 for x in rows)
    global_path=any(x.get('candidate_path')=='extend_attention_fwd.global_head512_block_m16' and x.get('phase')=='runtime_invocation' and x.get('qk_head_dim')==512 and x.get('v_head_dim')==512 and x.get('q_heads')==32 and x.get('kv_heads')==4 and x.get('sliding_window_size',0)<=-1 and x.get('control_tile')==[32,64] and x.get('candidate_tile')==[16,64] for x in proof)
    path_ok=attention(control_proof) and attention(proof) and global_path
valid=all(x.get('pass') for x in smoke) and path_ok
classification='promote_ceiling' if valid and candidate<=0.6381105230769232 else ('promote_gain' if valid and gain>=.05 else 'retain_simple_positive' if valid and (sync_mode or attention_mode or fp8_linear_mode or global_attention_mode) and gain>0 else 'close_sync_attempt' if valid and sync_mode else 'close_attention_attempt' if valid and attention_mode else 'close_fp8_linear_attempt' if valid and fp8_linear_mode else 'close_global_attention_attempt' if valid and global_attention_mode else 'close_boundary' if valid else 'invalid')
v={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'control':c,'candidate':q,'control_service_seconds_per_request':control,'candidate_service_seconds_per_request':candidate,'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105230769232,'ceiling_pass':valid and candidate<=0.6381105230769232,'retain_pass':valid and gain>=.05,'semantic_proof':smoke,'accounting_proof':{'control':c['cache'],'candidate':q['cache']},'fp8_proof':True,'qkv_proof':True,'attention_proof':{'control':control_proof,'candidate':proof},'candidate_path_proof':proof}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
  atomic_terminal pair_complete paired_scientific_terminal_persisted
else
  fail unknown_mode
fi
