#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/sglang-v0513-mtp-accepted-depth
input="$root/input"
assistant="$root/assistant"
checkpoint=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x={'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],
   'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x=json.loads(p.read_text()) if p.exists() else {
  'diagnostic_cuda_started':False,'diagnostic_science_started':False,
  'control_cuda_started':False,'control_science_started':False,
  'mtp_cuda_started':False,'mtp_science_started':False}
x[sys.argv[2]]=True; q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

compact() {
  set +e
  for container in mtp-depth-diagnostic mtp-depth-control mtp-depth-candidate; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/compact.tar.gz" >"$root/compact.tar.gz.sha256"
}
trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR

sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>"$artifacts/image-inspect.stderr" \
  || fail pinned_image_missing

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
  local phase=$1 container=$2 accepted_audit=$3 timing=$4
  shift 4
  local audit="$artifacts/$phase-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${phase}_cuda_started"
  local accepted_env=()
  if [[ -n "$accepted_audit" ]]; then
    accepted_env=(-e ACCEPTED_DEPTH_AUDIT="$accepted_audit" -e ACCEPTED_DEPTH_TIMING="$timing")
  fi
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" -v "$checkpoint:/work/checkpoint:ro" \
    -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e STACKED_FRONTIER_ARM=candidate \
    -e RESIDUAL_ARM=candidate \
    -e RESIDUAL_CANDIDATE_AUDIT="/work/artifacts/$phase-audit/residual.jsonl" \
    -e QKV_EPILOGUE_AUDIT="/work/artifacts/$phase-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/artifacts/$phase-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/artifacts/$phase-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/artifacts/$phase-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    -e SGLANG_EAGER_INPUT_NO_COPY=true \
    "${accepted_env[@]}" "$image" python3 /work/input/accepted_depth_entrypoint.py \
    "${base_args[@]}" "$@" >"$artifacts/$phase.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$phase.models.json" 2>"$artifacts/$phase.models.stderr"; then
      ready=1
      break
    fi
    sleep 5
  done
  sudo docker logs "$container" >"$artifacts/$phase.server-start.log" 2>&1 || true
  [[ "$ready" -eq 1 ]] || fail "$phase.server_not_ready"
}

smoke() {
  local phase=$1
  python3 - "$artifacts/$phase.smoke.json" <<'PY' || fail "$phase.smoke_failed"
import json,sys,urllib.request
rows=[]
for label,prompt in [
    ('instruction','Reply with exactly: READY'),
    ('arithmetic','What is 2+2? Reply with only the number.'),
    ('structured','Return only a JSON object with key "status" and string value "ok".')]:
    body={'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],
          'temperature':0,'seed':20260718,'max_tokens':32}
    request=urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',
                                   json.dumps(body).encode(),{'Content-Type':'application/json'})
    raw=urllib.request.urlopen(request,timeout=180).read()
    text=json.loads(raw)['choices'][0]['message']['content'].strip()
    ok=text=='READY' if label=='instruction' else text=='4' if label=='arithmetic' else json.loads(text.strip('`json\n'))=={'status':'ok'}
    rows.append({'label':label,'text':text,'pass':ok})
x={'rows':rows,'pass':all(row['pass'] for row in rows)}
open(sys.argv[1],'w').write(json.dumps(x,indent=2,sort_keys=True)+'\n')
assert x['pass']
PY
}

validate_stack() {
  local phase=$1 require_c32=$2
  python3 - "$artifacts/$phase-audit" "$require_c32" <<'PY' || fail "$phase.stacked_path_missing"
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); require_c32=sys.argv[2]=='yes'
modules=[json.loads(x) for x in (p/'modules.jsonl').read_text().splitlines() if x]
consumers=[json.loads(x) for x in (p/'consumers.jsonl').read_text().splitlines() if x]
qkv=[json.loads(x) for x in (p/'qkv.jsonl').read_text().splitlines() if x]
residual=[json.loads(x) for x in (p/'residual.jsonl').read_text().splitlines() if x]
target=lambda row:any(key in str(row.get('prefix','')) for key in ('language_model','model.layers'))
assert sum(target(row) for row in modules) >= 240
assert any(target(row) for row in consumers)
target_qkv=[row for row in qkv if row.get('dispatch')=='fused_qkv_target']
assistant_qkv=[row for row in qkv if row.get('dispatch')=='stock_qkv_kv_shared_assistant']
kernel_qkv=[row for row in qkv if 'candidate_symbol' in row]
assert target_qkv and kernel_qkv
assert all(row.get('is_kv_shared_layer') is False for row in target_qkv)
if p.name != 'control-audit':
    assert assistant_qkv
    assert all(row.get('is_kv_shared_layer') is True for row in assistant_qkv)
assert all(row.get('candidate_symbol')=='_qkv_norm_rope_inplace_kernel' for row in kernel_qkv)
assert any(row.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' for row in residual)
assert any(row.get('candidate_path')=='ScheduleBatch.prepare_for_decode.pinned_async_penalty_tokens' for row in residual)
assert any(row.get('candidate_path')=='BatchedMinNewTokensPenalizer.host_required_dense_add' for row in residual)
metadata=[row for row in residual if row.get('candidate_path')=='create_flashinfer_kv_indices_triton.producer_fused_swa_mapping']
assert metadata
if require_c32:
    assert any(row.get('batch_size')==32 and row.get('graph_safe') is True and row.get('no_device_scalar_read') is True for row in metadata)
PY
}

run_exact() {
  local phase=$1 container=$2 arm=$3
  state "${phase}_science_started"
  sudo docker exec "$container" python3 /work/input/fp8_qkv_paired_runner.py \
    --output "/work/artifacts/$phase" --arm "$arm" --concurrency 32 \
    >"$artifacts/$phase.runner.stdout" 2>"$artifacts/$phase.runner.stderr" \
    || fail "$phase.runner_failed"
  python3 - "$artifacts/$phase/TERMINAL.json" <<'PY' || fail "$phase.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('pass') is True and x.get('complete_requests')==32
assert x['cache']['uncached_prompt_tokens_delta']==117728
assert x['cache']['cached_prompt_tokens_delta']==17120
PY
}

sudo docker rm -f mtp-depth-control mtp-depth-candidate >/dev/null 2>&1 || true
if [[ "${PAIR_ONLY:-0}" != 1 ]]; then
start_server diagnostic mtp-depth-diagnostic /work/artifacts/diagnostic-audit/accepted-depth.jsonl 1 \
  --speculative-algorithm NEXTN --speculative-draft-model-path /work/assistant \
  --speculative-num-steps 1 --speculative-eagle-topk 1 --speculative-num-draft-tokens 2
smoke diagnostic
sudo truncate -s 0 "$artifacts/diagnostic-audit/accepted-depth.jsonl"
state diagnostic_science_started
sudo docker exec mtp-depth-diagnostic python3 /work/input/accepted_depth_diagnostic.py \
  --audit /work/artifacts/diagnostic-audit/accepted-depth.jsonl \
  --output /work/artifacts/ACCEPTED_DEPTH_TERMINAL.json \
  >"$artifacts/diagnostic.runner.stdout" 2>"$artifacts/diagnostic.runner.stderr" \
  || fail accepted_depth_diagnostic_failed
validate_stack diagnostic no

admitted=$(python3 - "$artifacts/ACCEPTED_DEPTH_TERMINAL.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('pass') is True
print('yes' if x.get('endpoint_pair_admitted') is True else 'no')
PY
)
if [[ "$admitted" != yes ]]; then
  python3 - "$artifacts/ACCEPTED_DEPTH_TERMINAL.json" "$artifacts/FINAL_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
x=json.load(open(sys.argv[1]))
x.update({'status':'terminal','endpoint_pair_run':False,'classification':'close_below_three_percent_bound'})
p=pathlib.Path(sys.argv[2]); q=p.with_suffix('.part'); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
  atomic_terminal scientific_terminal accepted_depth_below_bound
  exit 0
fi
fi

if [[ "${CANDIDATE_ONLY:-0}" != 1 ]]; then
  sudo docker rm -f mtp-depth-diagnostic >/dev/null 2>&1 || true
  start_server control mtp-depth-control "" 0
  smoke control
  run_exact control mtp-depth-control stacked_control_c32
  validate_stack control yes
  sudo docker rm -f mtp-depth-control >/dev/null 2>&1 || true
fi

start_server mtp mtp-depth-candidate /work/artifacts/mtp-audit/accepted-depth.jsonl 0 \
  --speculative-algorithm NEXTN --speculative-draft-model-path /work/assistant \
  --speculative-num-steps 1 --speculative-eagle-topk 1 --speculative-num-draft-tokens 2
smoke mtp
sudo truncate -s 0 "$artifacts/mtp-audit/accepted-depth.jsonl"
run_exact mtp mtp-depth-candidate stacked_mtp_c32
validate_stack mtp yes

if [[ "${CANDIDATE_ONLY:-0}" == 1 ]]; then
  python3 - "$artifacts/mtp/TERMINAL.json" "$artifacts/FINAL_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
mtp=json.load(open(sys.argv[1])); out=pathlib.Path(sys.argv[2])
x={'schema_version':1,'status':'terminal','classification':'mtp_candidate_terminal_persisted','pass':mtp.get('pass') is True,'endpoint_pair_run':False,'candidate_only':True,'mtp':mtp}
q=out.with_suffix('.part');q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');os.replace(q,out)
assert x['pass']
PY
  atomic_terminal scientific_terminal mtp_candidate_terminal_persisted
  exit 0
fi

python3 - "$artifacts/control/TERMINAL.json" "$artifacts/mtp/TERMINAL.json" \
  "$artifacts/control.smoke.json" "$artifacts/mtp.smoke.json" \
  "$artifacts/mtp-audit/accepted-depth.jsonl" "$artifacts/ACCEPTED_DEPTH_TERMINAL.json" \
  "$artifacts/FINAL_TERMINAL.json" <<'PY' || fail paired_terminal_invalid
import json,os,pathlib,sys
c=json.load(open(sys.argv[1])); m=json.load(open(sys.argv[2]))
cs=json.load(open(sys.argv[3])); ms=json.load(open(sys.argv[4]))
events=[json.loads(x) for x in pathlib.Path(sys.argv[5]).read_text().splitlines() if x]
diagnostic=json.load(open(sys.argv[6])); out=pathlib.Path(sys.argv[7])
verify=[x for x in events if x.get('event')=='target_verify']
assistant=[x for x in events if x.get('event')=='assistant_forward']
verify_calls=sum(int(x['batch_size']) for x in verify)
accepted_drafts=sum(int(x['accepted_drafts_total']) for x in verify)
accepted_tokens=verify_calls+accepted_drafts
smoke_equal=[x['text'] for x in cs['rows']]==[x['text'] for x in ms['rows']]
control=float(c['service_seconds_per_request']); candidate=float(m['service_seconds_per_request'])
gain=1-candidate/control
valid=(
    c.get('pass') is True and m.get('pass') is True and smoke_equal and assistant and verify
    and accepted_tokens==32*358
    and c['cache']['uncached_prompt_tokens_delta']==m['cache']['uncached_prompt_tokens_delta']==117728
    and c['cache']['cached_prompt_tokens_delta']==m['cache']['cached_prompt_tokens_delta']==17120
)
classification=(
    'promote_ceiling' if valid and candidate<=0.6381105231 else
    'retain_simple_positive' if valid and gain>0 else
    'close_mtp_endpoint' if valid else 'invalid_endpoint_pair'
)
x={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,
   'endpoint_pair_run':True,'control':c,'mtp':m,
   'control_service_seconds_per_request':control,'mtp_service_seconds_per_request':candidate,
   'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105231,
   'ceiling_pass':valid and candidate<=0.6381105231,'retain_pass':valid and gain>0,
   'deterministic_smoke_equal':smoke_equal,'control_smoke':cs,'mtp_smoke':ms,
   'mtp_telemetry':{'assistant_forward_events':len(assistant),'target_verify_events':len(verify),
                    'verify_calls':verify_calls,'accepted_drafts':accepted_drafts,
                    'accepted_tokens':accepted_tokens,
                    'mean_accepted_depth':accepted_tokens/verify_calls if verify_calls else 0},
   'accepted_depth_diagnostic':diagnostic,
   'accounting':{'control':c['cache'],'mtp':m['cache']},
   'stacked_path_proof':True}
q=out.with_suffix('.part'); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,out)
assert valid
PY
atomic_terminal scientific_terminal paired_endpoint_terminal_persisted
