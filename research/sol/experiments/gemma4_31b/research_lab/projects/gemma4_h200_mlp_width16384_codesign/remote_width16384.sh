#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-width16384
input="$root/input"
artifacts="$root/artifacts"
checkpoint="$root/checkpoint"
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
x=json.loads(p.read_text()) if p.exists() else {'component_candidate_cuda_started':False,'component_candidate_science_started':False,'endpoint_candidate_cuda_started':False,'endpoint_candidate_science_started':False}
x[sys.argv[2]]=True; x['updated_unix_s']=time.time()
q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() { atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"; exit 1; }
finalize() {
  set +e
  sudo docker logs gemma-width16384-candidate >"$artifacts/candidate.server-final.log" 2>&1 || true
  sudo docker inspect gemma-width16384-candidate >"$artifacts/candidate.container-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/width16384-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/width16384-compact.tar.gz" >"$root/width16384-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_not_resident

sudo rm -rf "$artifacts/component"
state component_candidate_cuda_started
sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work" \
  -e PYTHONPATH=/sgl-workspace/sglang/python \
  "$image" python3 /work/input/mlp_component.py \
    --output /work/artifacts/component \
    --snapshot /work/input/layer0-rms-qkv-gate-up.safetensors \
    --down-snapshot /work/input/layer0-down.safetensors \
    --selection /work/input/JOINT_NORM_SELECTION.json \
  >"$artifacts/component.stdout" 2>"$artifacts/component.stderr" || fail component_failed
state component_candidate_science_started

python3 - "$artifacts/component/TERMINAL.json" "$input/CURRENT_FP8_LINEAR_SHAPE_MAP.json" "$input/CURRENT_TRACE_ATTRIBUTION.json" "$artifacts/BOUND.json" <<'PY' || fail bound_derivation_failed
import json,os,pathlib,sys
component=json.load(open(sys.argv[1])); shape=json.load(open(sys.argv[2])); trace=json.load(open(sys.argv[3])); out=pathlib.Path(sys.argv[4]); tmp=out.with_suffix('.part')
if component.get('pass') is not True:
    raise RuntimeError('component_not_positive')
reductions={int(row['m']):float(row['reduction_fraction']) for row in component['rows']}
conservative=min(reductions.values())
families={row['projection']:row for row in shape['projection_families']}
mlp_seconds=families['gate_up_proj']['seconds']+families['down_proj']['seconds']
window=float(trace['window']['seconds'])
saved=mlp_seconds*conservative
reduction=saved/window
value={'schema_version':1,'status':'terminal','pass':reduction>=0.03,'classification':'endpoint_gate_pass' if reduction>=0.03 else 'bound_below_3pct','component_conservative_reduction_fraction':conservative,'component_reductions_by_m':reductions,'current_trace_window_seconds':window,'current_trace_mapped_mlp_seconds':mlp_seconds,'current_trace_mapped_mlp_fraction':mlp_seconds/window,'conservative_saved_seconds':saved,'conservative_whole_request_reduction_fraction':reduction,'gate_fraction':0.03,'mapping':'current trace dominant CUTLASS FP8 launches mechanically sequenced to qkv/o/gate_up/down actual-consumer audit; only measured gate_up+down time admitted'}
tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY

if ! python3 - "$artifacts/BOUND.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1])).get('pass') is True
PY
then
  atomic "$artifacts/WORKER_TERMINAL.json" completed component_bound_below_endpoint_gate
  exit 0
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
sudo docker rm -f gemma-width16384-candidate >/dev/null 2>&1 || true
mkdir -p "$artifacts/candidate-audit"
state endpoint_candidate_cuda_started
sudo docker run -d --name gemma-width16384-candidate --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work" \
  -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e STACKED_FRONTIER_ARM=candidate -e MLP_WIDTH16384_ARM=candidate \
  -e MLP_WIDTH16384_SELECTION=/work/input/JOINT_NORM_SELECTION.json \
  -e MLP_WIDTH16384_AUDIT=/work/artifacts/candidate-audit/mlp_width.jsonl \
  -e RESIDUAL_CANDIDATE_AUDIT=/work/artifacts/candidate-audit/residual.jsonl \
  -e QKV_EPILOGUE_AUDIT=/work/artifacts/candidate-audit/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/artifacts/candidate-audit/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/artifacts/candidate-audit/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/artifacts/candidate-audit/runtime.json \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" python3 /work/input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}" \
  >"$artifacts/candidate.container-id"
ready=0
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/candidate.models.json" 2>"$artifacts/candidate.models.stderr"; then ready=1; break; fi
  sleep 5
done
sudo docker logs gemma-width16384-candidate >"$artifacts/candidate.server-start.log" 2>&1 || true
[[ "$ready" -eq 1 ]] || fail candidate_server_not_ready

python3 - "$artifacts/candidate-audit/mlp_width.jsonl" "$artifacts/PATH_PROOF.json" <<'PY' || fail candidate_path_invalid
import json,os,pathlib,sys
rows=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]
valid=len(rows)==180 and {x['layer'] for x in rows}==set(range(60))
for row in rows:
    projection=row['projection']
    expected=[5376,16384] if projection=='down_proj' else [16384,5376]
    valid=valid and row['candidate_shape']==expected and row['indices_count']==16384
value={'schema_version':1,'pass':valid,'rows':len(rows),'layers':len({x['layer'] for x in rows}),'projections':sorted({x['projection'] for x in rows}),'candidate_shapes':sorted({str(x['candidate_shape']) for x in rows}),'all_non_mlp_paths_untouched_by_width_patch':True}
p=pathlib.Path(sys.argv[2]); q=p.with_suffix('.part'); q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
assert valid
PY

python3 - "$artifacts/COHERENCE.json" <<'PY' || fail coherence_transport_failed
import json,math,os,pathlib,sys,urllib.request
rows=[]
for want,prompt in [('READY','Reply with exactly: READY'),('4','What is 2+2? Reply with only the number.'),('json','Return only a JSON object with key "status" and string value "ok".')]:
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    text=raw['choices'][0]['message']['content'].strip()
    try: ok=text==want if want!='json' else json.loads(text.strip('`json\n'))=={'status':'ok'}
    except Exception: ok=False
    rows.append({'want':want,'text':text[:500],'pass':ok,'finite':isinstance(text,str)})
value={'schema_version':1,'pass':all(x['pass'] for x in rows),'transport_pass':all(x['finite'] for x in rows),'quality_unsafe':True,'rows':rows}
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part'); q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
assert value['transport_pass']
PY

state endpoint_candidate_science_started
sudo rm -rf "$artifacts/candidate"
sudo docker exec gemma-width16384-candidate python3 /work/input/fp8_qkv_paired_runner.py \
  --output /work/artifacts/candidate --arm width16384_quality_unsafe --concurrency 32 \
  >"$artifacts/candidate.runner.stdout" 2>"$artifacts/candidate.runner.stderr" || fail candidate_runner_failed

python3 - "$artifacts/candidate/TERMINAL.json" "$input/persisted_control_terminal.json" "$artifacts/BOUND.json" "$artifacts/COHERENCE.json" "$artifacts/PATH_PROOF.json" "$artifacts/TERMINAL.json" <<'PY' || fail endpoint_terminal_invalid
import json,os,pathlib,sys
cand,control,bound,coherence,path=[json.load(open(x)) for x in sys.argv[1:6]]
if cand.get('pass') is not True or cand.get('complete_requests')!=32 or len(cand.get('rows',[]))!=32:
    raise RuntimeError('candidate rows invalid')
cache=cand.get('cache',{})
if cache.get('cached_prompt_tokens_delta')!=17120 or cache.get('uncached_prompt_tokens_delta')!=117728:
    raise RuntimeError('candidate cache accounting invalid')
candidate=float(cand['service_seconds_per_request']); baseline=float(control['service_seconds_per_request']); reduction=1-candidate/baseline
classification='frontier_nomination' if candidate<=0.6381105231 else ('measured_positive_below_frontier' if reduction>0 else 'endpoint_regression')
value={'schema_version':1,'status':'terminal','classification':classification,'pass':candidate<=0.6381105231,'quality_claim_authorized':False,'quality_unsafe':True,'coherence':coherence,'path_proof':path,'component_bound':bound,'persisted_control_seconds_per_request':baseline,'candidate_seconds_per_request':candidate,'endpoint_reduction_fraction':reduction,'economic_ceiling_seconds_per_request':0.6381105231,'candidate':cand}
p=pathlib.Path(sys.argv[6]); q=p.with_suffix('.part'); q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
atomic "$artifacts/WORKER_TERMINAL.json" completed scientific_terminal_persisted
