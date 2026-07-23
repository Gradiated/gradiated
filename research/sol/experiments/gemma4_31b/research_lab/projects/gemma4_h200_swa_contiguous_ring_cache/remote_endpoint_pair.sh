#!/usr/bin/env bash
set -Eeuo pipefail

root=${RING_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/endpoint-artifacts"
checkpoint=/home/glmrunner/gemma4-async-result-pipeline/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n')
os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x=json.loads(p.read_text()) if p.exists() else {'control_cuda_started':False,'control_science_started':False,'candidate_cuda_started':False,'candidate_science_started':False}
x[sys.argv[2]]=True; x['updated_unix_s']=time.time()
q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() { atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"; exit 1; }
finalize() {
  set +e
  for arm in control candidate; do
    sudo docker logs "gemma-ring-$arm" >"$artifacts/$arm.server-final.log" 2>&1 || true
    sudo docker inspect "gemma-ring-$arm" >"$artifacts/$arm.container-inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/endpoint-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/endpoint-compact.tar.gz" >"$root/endpoint-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"
  rm -f \
  "$artifacts/ENDPOINT_RESULT.json" \
  "$artifacts/SEMANTIC_DISCRIMINATOR.json" \
  "$artifacts/TRANSITION_PROOF.json"
python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({
 'control_cuda_started':False,
 'control_science_started':False,
 'control_replayed':False,
 'candidate_cuda_started':False,
 'candidate_science_started':False,
 'updated_unix_s':time.time(),
},indent=2,sort_keys=True)+'\n')
os.replace(q,p)
PY
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_not_resident

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
if [[ "${RING_CACHE_DISABLE_RADIX:-0}" == 1 ]]; then
  base_args+=(--disable-radix-cache)
fi
printf '%q ' "${base_args[@]}" >"$artifacts/server-args.txt"

start_server() {
  local arm=$1
  local ring_arm=$2
  local trace_transitions=${3:-0}
  local container="gemma-ring-$arm"
  local audit="$artifacts/$arm-audit"
  local server_args=("${base_args[@]}")
  if [[ "$trace_transitions" == 1 ]]; then
    server_args+=(--disable-cuda-graph)
  fi
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/ring" \
    -e PYTHONPATH=/work/ring/input:/sgl-workspace/sglang/python \
    -e STACKED_FRONTIER_ARM=candidate -e RING_CACHE_ARM="$ring_arm" \
    -e RING_CACHE_TRACE_TRANSITIONS="$trace_transitions" \
    -e RING_CACHE_AUDIT="/work/ring/endpoint-artifacts/$arm-audit/ring.jsonl" \
    -e RESIDUAL_CANDIDATE_AUDIT="/work/ring/endpoint-artifacts/$arm-audit/residual.jsonl" \
    -e QKV_EPILOGUE_AUDIT="/work/ring/endpoint-artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/ring/endpoint-artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/ring/endpoint-artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/ring/endpoint-artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/ring/input/proven_v0513_endpoint_entrypoint.py "${server_args[@]}" \
    >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 150); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then ready=1; break; fi
    if [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" != true ]]; then
      break
    fi
    sleep 4
  done
  sudo docker logs "$container" >"$artifacts/$arm.server-start.log" 2>&1 || true
  if [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" != true ]]; then
    fail "$arm.container_not_running"
  fi
  [[ "$ready" -eq 1 ]] || fail "$arm.server_not_ready"
  if [[ "$ring_arm" == candidate ]]; then
    python3 - "$audit/ring.jsonl" <<'PY' || fail "$arm.candidate_path_absent"
import json,sys
events=[json.loads(row) for row in open(sys.argv[1]) if row.strip()]
assert any(row.get('event')=='ring_region_reserved' for row in events)
PY
  fi
  python3 - "$artifacts/$arm.smoke.json" "$trace_transitions" <<'PY' || fail "$arm.smoke_failed"
import json,os,sys,urllib.request
rows=[]
cases=[
 ('json_first','json','Return only a JSON object with key "status" and string value "ok".'),
 ('ready','READY','Reply with exactly: READY'),
 ('arithmetic','4','What is 2+2? Reply with only the number.'),
 ('json_after_prefix_population','json','Return only a JSON object with key "status" and string value "ok".'),
]
for label,want,prompt in cases:
 body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
 raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
 text=raw['choices'][0]['message']['content'].strip()
 if want!='json':
  ok=text==want
 else:
  try:
   ok=json.loads(text.strip('`json\n'))=={'status':'ok'}
  except (TypeError,ValueError):
   ok=False
 rows.append({'label':label,'want':want,'text':text,'pass':ok})
by_label={row['label']:row for row in rows}
first=by_label['json_first']['pass']
after=by_label['json_after_prefix_population']['pass']
if first and not after:
 localization='prefix_restore_or_request_reuse'
elif not first:
 localization='first_extend_to_decode_transition'
elif first and after:
 localization='cuda_graph_padding_or_concurrency'
else:
 localization='undetermined'
out={
 'rows':rows,
 'pass':all(x['pass'] for x in rows),
 'localization':localization,
 'radix_cache_disabled':os.environ.get('RING_CACHE_DISABLE_RADIX')=='1',
}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n')
if sys.argv[2]!='1':
 assert out['pass']
PY
}

run_arm() {
  local arm=$1
  state "${arm}_science_started"
  sudo docker exec "gemma-ring-$arm" python3 /work/ring/input/fp8_qkv_paired_runner.py \
    --output "/work/ring/endpoint-artifacts/$arm" --arm "ring_$arm" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  python3 - "$artifacts/$arm/TERMINAL.json" <<'PY' || fail "$arm.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('pass') is True and x.get('complete_requests')==32 and len(x.get('rows',[]))==32
assert x.get('cache',{}).get('cached_prompt_tokens_delta')==17120
assert x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
PY
}

sudo docker rm -f gemma-ring-control gemma-ring-candidate >/dev/null 2>&1 || true
mkdir -p "$artifacts/control"
control_terminal_tmp="$artifacts/control/TERMINAL.json.part.$$"
sudo install -m 0644 "$input/persisted-control-terminal.json" "$control_terminal_tmp"
sudo mv -f "$control_terminal_tmp" "$artifacts/control/TERMINAL.json"
python3 - "$artifacts/control/TERMINAL.json" <<'PY' || fail persisted_control_invalid
import json,sys
x=json.load(open(sys.argv[1]))
ok=x.get('pass') is True and x.get('complete_requests')==32 and len(x.get('rows',[]))==32
ok=ok and x.get('cache',{}).get('cached_prompt_tokens_delta')==17120
ok=ok and x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
raise SystemExit(0 if ok else 1)
PY

padded_proof_tmp="$artifacts/PADDED_NOOP_PROOF.json.part.$$"
sudo install -m 0644 "$input/persisted-padded-noop-proof.json" "$padded_proof_tmp"
sudo mv -f "$padded_proof_tmp" "$artifacts/PADDED_NOOP_PROOF.json"
python3 - "$artifacts/PADDED_NOOP_PROOF.json" <<'PY' || fail persisted_padded_noop_invalid
import json,sys
value=json.load(open(sys.argv[1]))
assert value.get('pass') is True
assert value.get('producer_negative_row_noop') is True
assert value.get('consumer_negative_row_zero') is True
PY

sudo docker stop gemma4-async-result-pipeline >/dev/null 2>&1 || true
rm -rf "$artifacts/candidate-audit"
start_server candidate candidate 1
cp "$artifacts/candidate.smoke.json" "$artifacts/SEMANTIC_DISCRIMINATOR.json"
if python3 - "$artifacts/SEMANTIC_DISCRIMINATOR.json" "$artifacts/candidate-audit/ring.jsonl" "$artifacts/PADDED_NOOP_PROOF.json" "$artifacts/TRANSITION_PROOF.json" "$artifacts/ENDPOINT_RESULT.json" <<'PY'
import json,os,pathlib,sys
smoke=json.load(open(sys.argv[1]))
audit_path=pathlib.Path(sys.argv[2])
padded=json.load(open(sys.argv[3]))
events=[json.loads(row) for row in audit_path.read_text().splitlines() if row] if audit_path.exists() else []
extends=[row for row in events if row.get('event')=='ring_transition_extend']
decodes=[row for row in events if row.get('event')=='ring_transition_decode']
comparisons=[]
for row in extends:
 comparisons.extend(row.get(name) for name in ('current_k','current_v','prefix_k','prefix_v') if row.get(name) is not None)
for row in decodes[:2]:
 comparisons.extend(row.get(name) for name in ('current_k','current_v','ring_vs_stock_output') if row.get(name) is not None)
comparison_pass=bool(comparisons) and all(
 value.get('all_finite') and value.get('relative_l2',float('inf')) <= 1e-5
 for value in comparisons
)
slots=[slot for row in extends+decodes for slot in row.get('request_pool_indices',[])]
rows=[ring_row for row in extends+decodes for ring_row in row.get('ring_rows',[])]
ownership_pass=all((slot==0) == (ring_row==-1) for slot,ring_row in zip(slots,rows))
ownership_pass=ownership_pass and len({ring_row for ring_row in rows if ring_row>=0})==len({slot for slot in slots if slot>0})
value={
 'schema_version':1,
 'status':'terminal',
 'classification':'transition_and_semantic_pass',
 'pass':smoke.get('pass') is True and padded.get('pass') is True and bool(extends) and len(decodes)>=2 and comparison_pass and ownership_pass,
 'semantic_discriminator':smoke,
 'padded_noop_proof':padded,
 'extend_transition_count':len(extends),
 'decode_transition_count':len(decodes),
 'first_two_decode_transitions':decodes[:2],
 'comparison_pass':comparison_pass,
 'ownership_pass':ownership_pass,
 'request_slots_observed':sorted(set(slots)),
 'ring_rows_observed':sorted(set(rows)),
 'padded_slot_maps_to_negative_row':all(r==-1 for s,r in zip(slots,rows) if s==0),
 'component_and_control_replayed':False,
}
if not value['pass']:
 value['classification']='semantic_discriminator_'+smoke.get('localization','invalid')
target=pathlib.Path(sys.argv[4]); temporary=target.with_suffix('.part')
temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(temporary,target)
if not value['pass']:
 out=pathlib.Path(sys.argv[5]); temporary=out.with_suffix('.part')
 value.update({'candidate_latency_measured':False})
 temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(temporary,out)
 raise SystemExit(2)
PY
then
  transition_status=0
else
  transition_status=$?
fi
if [[ "$transition_status" -ne 0 ]]; then
  atomic "$artifacts/WORKER_TERMINAL.json" endpoint_complete semantic_discriminator_reject
  exit 0
fi

sudo docker rm -f gemma-ring-candidate >/dev/null 2>&1 || true
rm -rf "$artifacts/candidate-audit"
rm -rf "$artifacts/candidate"
start_server candidate candidate 0
run_arm candidate

python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/ENDPOINT_RESULT.json" "$artifacts/candidate.smoke.json" "$artifacts/candidate-audit/ring.jsonl" "$artifacts/TRANSITION_PROOF.json" <<'PY' || fail endpoint_evaluation_failed
import json,math,os,pathlib,sys
control=json.load(open(sys.argv[1])); candidate=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3])
smoke=json.load(open(sys.argv[4]))
audit_path=pathlib.Path(sys.argv[5])
transition=json.load(open(sys.argv[6]))
events=[json.loads(x) for x in audit_path.read_text().splitlines() if x] if audit_path.exists() else []
captures=[x for x in events if x.get('event')=='ring_decode_captured']
reservations=[x for x in events if x.get('event')=='ring_region_reserved']
local_ids=sorted({x.get('layer_id') for x in captures})
path_ok=(local_ids==[x for x in range(60) if x%6!=5] and bool(reservations) and all(x.get('window')==1024 and x.get('kv_heads')==16 and x.get('head_dim')==256 for x in captures))
accounting=all(x.get('cache',{}).get('cached_prompt_tokens_delta')==17120 and x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728 for x in (control,candidate))
responses=smoke.get('pass') is True and transition.get('pass') is True
c=float(control['service_seconds_per_request']); q=float(candidate['service_seconds_per_request']); gain=1-q/c
valid=path_ok and accounting and responses and all(x.get('pass') for x in (control,candidate)) and math.isfinite(c) and math.isfinite(q)
classification='retain_ring' if valid and q<c else ('ceiling_pass' if valid and q<=0.6381105231 else ('endpoint_negative' if valid else 'invalid'))
value={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'control_service_seconds_per_request':c,'candidate_service_seconds_per_request':q,'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105231,'ceiling_pass':valid and q<=0.6381105231,'control':control,'candidate':candidate,'semantic_smoke':smoke,'transition_proof':transition,'accounting_pass':accounting,'candidate_path_proof':{'local_layer_ids':local_ids,'ring_events':events,'global_paged_e5m2_unchanged_by_construction':True,'pass':path_ok}}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
assert valid
PY
atomic "$artifacts/WORKER_TERMINAL.json" endpoint_complete paired_endpoint_terminal_persisted
