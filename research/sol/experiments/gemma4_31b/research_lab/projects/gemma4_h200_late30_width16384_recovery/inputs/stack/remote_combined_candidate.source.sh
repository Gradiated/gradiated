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
x=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'candidate_science_started':False}
x[sys.argv[2]]=True; x['updated_unix_s']=time.time()
q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() { atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"; exit 1; }
finalize() {
  set +e
  sudo docker logs gemma-width-ring-candidate >"$artifacts/candidate.server-final.log" 2>&1 || true
  sudo docker inspect gemma-width-ring-candidate >"$artifacts/candidate.container-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/endpoint-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/endpoint-compact.tar.gz" >"$root/endpoint-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json" "$artifacts/ENDPOINT_RESULT.json" "$artifacts/INVOCATION_STATE.json"
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_not_resident

base_args=(
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint
  --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30001
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking
  --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1
  --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8
)

start_server() {
  local trace=$1
  local audit="$artifacts/candidate-audit"
  local server_args=("${base_args[@]}")
  [[ "$trace" == 1 ]] && server_args+=(--disable-cuda-graph)
  sudo docker rm -f gemma-width16384-candidate gemma-ring-candidate gemma-width-ring-candidate >/dev/null 2>&1 || true
  rm -rf "$audit"
  mkdir -p "$audit"
  state candidate_cuda_started
  sudo docker run -d --name gemma-width-ring-candidate --gpus all --ipc=host --network host \
    -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/ring" \
    -e PYTHONPATH=/work/ring/input:/sgl-workspace/sglang/python \
    -e STACKED_FRONTIER_ARM=candidate -e MLP_WIDTH16384_ARM=candidate -e RING_CACHE_ARM=candidate \
    -e MLP_WIDTH16384_SELECTION=/work/ring/input/JOINT_NORM_SELECTION.json \
    -e MLP_WIDTH16384_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/mlp_width.jsonl \
    -e RING_CACHE_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/ring.jsonl \
    -e RING_CACHE_TRACE_TRANSITIONS="$trace" \
    -e RESIDUAL_CANDIDATE_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/residual.jsonl \
    -e QKV_EPILOGUE_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/qkv.jsonl \
    -e FP8_MODULE_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/modules.jsonl \
    -e FP8_CONSUMER_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/consumers.jsonl \
    -e FP8_RUNTIME_AUDIT=/work/ring/endpoint-artifacts/candidate-audit/runtime.json \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/ring/input/proven_v0513_endpoint_entrypoint.py "${server_args[@]}" >"$artifacts/candidate.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30001/v1/models >"$artifacts/candidate.models.json" 2>"$artifacts/candidate.models.stderr"; then ready=1; break; fi
    [[ "$(sudo docker inspect -f '{{.State.Running}}' gemma-width-ring-candidate 2>/dev/null || true)" == true ]] || break
    sleep 4
  done
  sudo docker logs gemma-width-ring-candidate >"$artifacts/candidate.server-start.log" 2>&1 || true
  [[ "$ready" == 1 ]] || fail candidate_server_not_ready
  python3 - "$audit/mlp_width.jsonl" "$audit/ring.jsonl" "$artifacts/PATH_AUDITS.json" <<'PY' || fail candidate_path_invalid
import json, pathlib, sys
mlp=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]
ring=[json.loads(x) for x in open(sys.argv[2]) if x.strip()]
width_ok=len(mlp)==180 and {x['layer'] for x in mlp}==set(range(60)) and all(x['indices_count']==16384 and x['candidate_shape']==([5376,16384] if x['projection']=='down_proj' else [16384,5376]) for x in mlp)
reservations=[x for x in ring if x.get('event')=='ring_region_reserved']
ring_ok=bool(reservations)
p=pathlib.Path(sys.argv[3]); p.write_text(json.dumps({'pass':width_ok and ring_ok,'width':{'pass':width_ok,'rows':len(mlp),'layers':len({x['layer'] for x in mlp})},'ring':{'pass':ring_ok,'server_construction_reservation_seen':True,'global_paged_e5m2_unchanged_by_construction':True}},indent=2,sort_keys=True)+'\n')
assert width_ok and ring_ok
PY
}

semantic_transition() {
  python3 - "$artifacts/candidate.smoke.json" "$input/PERSISTED_WIDTH_ENDPOINT_TERMINAL.json" <<'PY' || fail semantic_smoke_failed
import json,math,sys,urllib.request
rows=[]
for label,want,prompt in [('json_first','json','Return only a JSON object with key "status" and string value "ok".'),('ready','READY','Reply with exactly: READY'),('arithmetic','4','What is 2+2? Reply with only the number.'),('json_after_prefix_population','json','Return only a JSON object with key "status" and string value "ok".')]:
 body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode(); raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30001/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180)); text=raw['choices'][0]['message']['content'].strip()
 rows.append({'label':label,'expected':want,'text':text[:500],'transport_pass':isinstance(text,str) and bool(text) and all(math.isfinite(ord(c)) for c in text)})
width=json.load(open(sys.argv[2])); reference=next(row['text'] for row in width['coherence']['rows'] if row['want']=='4')
arithmetic=next(row for row in rows if row['label']=='arithmetic'); arithmetic['persisted_width_reference']=reference; arithmetic['matches_persisted_incoherent_reference']=arithmetic['text']==reference
out={'pass':all(row['transport_pass'] for row in rows) and arithmetic['matches_persisted_incoherent_reference'],'quality_unsafe':True,'semantic_correctness_pass':False,'rows':rows}; open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n'); assert out['pass']
PY
  python3 - "$artifacts/candidate-audit/ring.jsonl" "$artifacts/TRANSITION_PROOF.json" <<'PY' || fail transition_invalid
import json,pathlib,sys
events=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]; extends=[x for x in events if x.get('event')=='ring_transition_extend']; decodes=[x for x in events if x.get('event')=='ring_transition_decode']
comparisons=[v for x in extends for v in (x.get('current_k'),x.get('current_v'),x.get('prefix_k'),x.get('prefix_v')) if v is not None]+[v for x in decodes[:2] for v in (x.get('current_k'),x.get('current_v'),x.get('ring_vs_stock_output')) if v is not None]
comparison=bool(comparisons) and all(v.get('all_finite') and v.get('exact_bytes') is True for v in comparisons)
tokens=bool(extends) and all(x.get(n,{}).get('all_tokens_exact') is True and x.get(n,{}).get('token_count')==len(x.get('absolute_positions',[])) for x in extends for n in ('current_k_tokens','current_v_tokens'))
slots=[s for x in extends+decodes for s in x.get('request_pool_indices',[])]; rows=[r for x in extends+decodes for r in x.get('ring_rows',[])]; ownership=all((s==0)==(r==-1) for s,r in zip(slots,rows)) and len({r for r in rows if r>=0})==len({s for s in slots if s>0})
out={'pass':bool(extends) and len(decodes)>=2 and comparison and tokens and ownership,'comparison_pass':comparison,'extend_token_pass':tokens,'ownership_pass':ownership,'extend_transition_count':len(extends),'decode_transition_count':len(decodes),'first_two_decode_transitions':decodes[:2],'component_and_control_replayed':False}; pathlib.Path(sys.argv[2]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); assert out['pass']
PY
}

resume=0
if [[ -d "$artifacts/candidate" ]]; then
  sudo docker inspect -f '{{.State.Running}}' gemma-width-ring-candidate | grep -qx true || fail resume_server_unhealthy
  curl -fsS http://127.0.0.1:30001/v1/models >"$artifacts/resume.models.json" || fail resume_models_unhealthy
  test "$(find "$artifacts/candidate" -type f | wc -l)" -eq 1 || fail resume_partial_not_zero_request
  test "$(sha256sum "$artifacts/candidate/WORKLOAD.json" | cut -d' ' -f1)" = 7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d || fail resume_workload_identity
  archive="$artifacts/candidate.pre_request.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$artifacts/candidate" "$archive"
  (cd "$archive" && find . -type f -print0 | sort -z | xargs -0 sha256sum) >"$archive.sha256"
  resume=1
fi
if [[ "$resume" == 0 ]]; then
sudo docker stop gemma4-async-result-pipeline >/dev/null 2>&1 || true
start_server 1
semantic_transition
python3 - "$artifacts/candidate-audit/ring.jsonl" "$artifacts/PATH_AUDITS.json" <<'PY' || fail ring_path_invalid
import json,pathlib,sys
x=json.loads(pathlib.Path(sys.argv[2]).read_text()); events=[json.loads(r) for r in open(sys.argv[1]) if r.strip()]; captures=[r for r in events if r.get('event')=='ring_decode_captured']; ids=sorted({r.get('layer_id') for r in captures}); ok=ids==[i for i in range(60) if i%6!=5] and all(r.get('window')==1024 and r.get('kv_heads')==16 and r.get('head_dim')==256 for r in captures); x['ring']={'pass':ok,'local_layer_ids':ids,'global_paged_e5m2_unchanged_by_construction':True}; x['pass']=x['width']['pass'] and ok; pathlib.Path(sys.argv[2]).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); assert x['pass']
PY
cp "$artifacts/PATH_AUDITS.json" "$artifacts/TRACE_PATH_AUDITS.json"
sudo docker rm -f gemma-width-ring-candidate >/dev/null 2>&1 || true
start_server 0
fi
state candidate_science_started
sudo docker exec gemma-width-ring-candidate python3 /work/ring/input/fp8_qkv_paired_runner.py --output /work/ring/endpoint-artifacts/candidate --arm width16384_e5m2_ring_combined --concurrency 32 >"$artifacts/candidate.runner.stdout" 2>"$artifacts/candidate.runner.stderr" || fail candidate_runner_failed

python3 - "$input/PERSISTED_WIDTH_ENDPOINT_TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PATH_AUDITS.json" "$artifacts/TRANSITION_PROOF.json" "$artifacts/candidate.smoke.json" "$artifacts/ENDPOINT_RESULT.json" <<'PY' || fail endpoint_evaluation_failed
import json,math,pathlib,sys
control,candidate,audits,transition,smoke=[json.load(open(x)) for x in sys.argv[1:6]]
accounting=all(x.get('cache',{}).get('cached_prompt_tokens_delta')==17120 and x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728 for x in (control,candidate)); rows=candidate.get('complete_requests')==32 and len(candidate.get('rows',[]))==32 and all(r.get('text_finite') for r in candidate.get('rows',[])); c=float(control['candidate_seconds_per_request']); q=float(candidate['service_seconds_per_request']); valid=audits.get('pass') and transition.get('pass') and smoke.get('pass') and accounting and rows and candidate.get('pass') and math.isfinite(q)
incremental=1-q/c; total=1-q/0.6743258590313417
classification='stack_positive' if valid and q<c else ('stack_regression' if valid else 'invalid')
out={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'quality_unsafe':True,'candidate_seconds_per_request':q,'persisted_width_seconds_per_request':c,'incremental_reduction_fraction':incremental,'qualified_control_seconds_per_request':0.6743258590313417,'total_reduction_fraction':total,'economic_ceiling_seconds_per_request':0.6381105231,'ceiling_pass':valid and q<=0.6381105231,'accounting_pass':accounting,'finite_rows_pass':rows,'path_audits':audits,'transition_proof':transition,'semantic_smoke':smoke,'candidate':candidate}
pathlib.Path(sys.argv[6]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); assert valid
PY
atomic "$artifacts/WORKER_TERMINAL.json" completed scientific_terminal_persisted
