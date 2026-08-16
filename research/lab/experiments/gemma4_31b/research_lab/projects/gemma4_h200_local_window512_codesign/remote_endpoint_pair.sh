#!/usr/bin/env bash
set -Eeuo pipefail

root=${WINDOW512_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/endpoint-artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
checkpoint="/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint"
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
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v=json.loads(p.read_text()) if p.exists() else {'control_cuda_started':False,'control_science_started':False,'candidate_cuda_started':False,'candidate_science_started':False}
v[sys.argv[2]]=True; v['updated_unix_s']=time.time()
q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

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
  local arm=$1 container=$2 window_arm=$3
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$checkpoint:/work/checkpoint:ro" \
    -v "$root:/work/window" \
    -e PYTHONPATH=/work/window/input:/sgl-workspace/sglang/python \
    -e STACKED_FRONTIER_ARM=candidate -e WINDOW512_ARM="$window_arm" \
    -e WINDOW512_LAYER_AUDIT="/work/window/endpoint-artifacts/$arm-audit/layers.jsonl" \
    -e RESIDUAL_CANDIDATE_AUDIT="/work/window/endpoint-artifacts/$arm-audit/residual.jsonl" \
    -e QKV_EPILOGUE_AUDIT="/work/window/endpoint-artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/window/endpoint-artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/window/endpoint-artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/window/endpoint-artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/window/input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}" \
    >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 150); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then
      ready=1
      break
    fi
    sleep 4
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
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n')
assert out['pass']
PY
}

run_arm() {
  local arm=$1 container=$2 label=$3
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/window/input/fp8_qkv_paired_runner.py \
    --output "/work/window/endpoint-artifacts/$arm" --arm "$label" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  python3 - "$artifacts/$arm/TERMINAL.json" <<'PY' || fail "$arm.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('pass') is True and x.get('complete_requests')==32 and len(x.get('rows',[]))==32
assert x.get('cache',{}).get('cached_prompt_tokens_delta')==17120
assert x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
PY
}

sudo docker rm -f window512-control window512-candidate >/dev/null 2>&1 || true
start_server control window512-control control
run_arm control window512-control window512_control
sudo docker rm -f window512-control >/dev/null 2>&1 || true
start_server candidate window512-candidate candidate
run_arm candidate window512-candidate window512_candidate

python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/ENDPOINT_RESULT.json" "$artifacts/control.smoke.json" "$artifacts/candidate.smoke.json" "$artifacts/candidate-audit/layers.jsonl" <<'PY'
import json,os,pathlib,sys
control=json.load(open(sys.argv[1])); candidate=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3])
smoke=[json.load(open(sys.argv[4])),json.load(open(sys.argv[5]))]
layer_path=pathlib.Path(sys.argv[6])
layers=[json.loads(x) for x in layer_path.read_text().splitlines() if x] if layer_path.exists() else []
local=[x for x in layers if x.get('layer_type')=='sliding_attention']
global_rows=[x for x in layers if x.get('layer_type')=='full_attention']
local_ids=sorted({x.get('layer_id') for x in local})
global_ids=sorted({x.get('layer_id') for x in global_rows})
path_ok=(
 len(local_ids)==50 and len(global_ids)==10
 and all(x.get('sliding_window_size')==512 and x.get('q_heads')==32 and x.get('kv_heads')==16 and x.get('qk_head_dim')==256 for x in local)
 and all(x.get('sliding_window_size') is None for x in global_rows)
)
accounting=all(x.get('cache',{}).get('cached_prompt_tokens_delta')==17120 and x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728 for x in (control,candidate))
valid=path_ok and accounting and all(x.get('pass') for x in smoke)
c=float(control['service_seconds_per_request']); q=float(candidate['service_seconds_per_request']); gain=1-q/c
classification='quality_unsafe_performance_positive' if valid and gain>=0.05 else ('quality_unsafe_ceiling_pass' if valid and q<=0.6381105231 else 'endpoint_negative')
value={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'control_service_seconds_per_request':c,'candidate_service_seconds_per_request':q,'reduction_fraction':gain,'five_percent_pass':valid and gain>=0.05,'economic_ceiling_seconds_per_request':0.6381105231,'ceiling_pass':valid and q<=0.6381105231,'quality_classification':'quality_unsafe_until_separately_validated_or_trained','control':control,'candidate':candidate,'semantic_proof':smoke,'accounting_proof':{'control':control['cache'],'candidate':candidate['cache']},'candidate_path_proof':{'local_layer_ids':local_ids,'global_layer_ids':global_ids,'events':layers,'pass':path_ok}}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY

atomic_terminal endpoint_complete paired_endpoint_terminal_persisted
