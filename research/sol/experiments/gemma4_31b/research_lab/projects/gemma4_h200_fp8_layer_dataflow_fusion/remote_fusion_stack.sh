#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-fp8-layer-fusion
input="$root/input"
checkpoint="$root/checkpoint"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts" "$root/torch-extensions"

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
v=json.loads(p.read_text()) if p.exists() else {'component_cuda_started':False,'component_science_started':False,'control_cuda_started':False,'control_science_started':False,'candidate_cuda_started':False,'candidate_science_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

compact() {
  set +e
  for container in gemma-fusion-control-v0513 gemma-fusion-candidate-v0513; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/fusion-stack-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/fusion-stack-compact.tar.gz" >"$root/fusion-stack-compact.tar.gz.sha256"
}

trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"
state worker_initialized

test -s "$input/GPU_INPUT_MANIFEST.json" || fail input_manifest_missing
test -s "$checkpoint/model.safetensors.index.json" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_missing

if [[ ! -s "$artifacts/component/TERMINAL.json" ]]; then
  rm -rf "$artifacts/component"
  state component_cuda_started
  sudo docker run --rm --gpus all --ipc=host \
    -v "$root:/work" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e TORCH_EXTENSIONS_DIR=/work/torch-extensions "$image" \
    python3 /work/input/component_benchmark.py --output /work/artifacts/component \
    >"$artifacts/component.stdout" 2>"$artifacts/component.stderr" || {
      if [[ -s "$artifacts/component/TERMINAL.json" ]]; then
        atomic_terminal component_negative exact_component_terminal_is_negative
        exit 20
      fi
      fail component_worker_failed_without_terminal
    }
  state component_science_started
fi

python3 - "$artifacts/component/TERMINAL.json" <<'PY' || {
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('candidate_invocations',0)>0
PY
  atomic_terminal component_negative exact_component_did_not_promote
  exit 20
}

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
  local arm=$1 container=$2
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" \
    -e PYTHONPATH=/work/input:/work/input/stack:/sgl-workspace/sglang/python \
    -e TORCH_EXTENSIONS_DIR=/work/torch-extensions \
    -e STACK_BASELINE_SITECUSTOMIZE=/work/input/stack/residual_sitecustomize.py \
    -e RESIDUAL_ARM=control \
    -e RESIDUAL_CANDIDATE_AUDIT="/work/artifacts/$arm-audit/attention.jsonl" \
    -e FUSION_ARM="$arm" \
    -e FUSION_AUDIT="/work/artifacts/$arm-audit/fusion.jsonl" \
    -e QKV_EPILOGUE_AUDIT="/work/artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/input/stack/proven_v0513_endpoint_entrypoint.py "${base_args[@]}" \
    >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 240); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then
      ready=1
      break
    fi
    sleep 5
  done
  sudo docker logs "$container" >"$artifacts/$arm.server-start.log" 2>&1 || true
  [[ "$ready" -eq 1 ]] || fail "$arm.server_not_ready"
  python3 - "$artifacts/$arm.smoke.json" <<'PY' || fail "$arm.smoke_failed"
import json,sys,urllib.request
rows=[]
for prompt in ('Reply with exactly: READY','What is 2+2? Reply with only the number.','Return only JSON with key "status" and value "ok".'):
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    text=raw['choices'][0]['message']['content'].strip()
    rows.append({'prompt':prompt,'text':text,'pass':bool(text)})
out={'rows':rows,'pass':all(row['pass'] for row in rows)}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n'); assert out['pass']
PY
}

run_arm() {
  local arm=$1 container=$2
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/input/stack/fp8_qkv_paired_runner.py \
    --output "/work/artifacts/$arm" --arm "fp8_qkv_${arm}" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  python3 - "$artifacts/$arm/TERMINAL.json" <<'PY' || fail "$arm.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests')==32 and len(x.get('rows',[]))==32
assert x.get('cache',{}).get('cached_prompt_tokens_delta')==17120
assert x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
PY
}

validate_stack() {
  local arm=$1
  python3 - "$artifacts/$arm-audit" "$arm" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); arm=sys.argv[2]
modules=[json.loads(x) for x in (p/'modules.jsonl').read_text().splitlines() if x]
consumers=[json.loads(x) for x in (p/'consumers.jsonl').read_text().splitlines() if x]
qkv=[json.loads(x) for x in (p/'qkv.jsonl').read_text().splitlines() if x]
attention=[json.loads(x) for x in (p/'attention.jsonl').read_text().splitlines() if x]
assert len(modules)==240 and consumers
assert qkv and all(x.get('candidate_symbol')=='_qkv_norm_rope_inplace_kernel' for x in qkv)
assert any(x.get('candidate_path')=='TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit' for x in attention)
fusion=[] if arm=='control' else [json.loads(x) for x in (p/'fusion.jsonl').read_text().splitlines() if x]
if arm=='candidate':
    assert len({x.get('prefix') for x in fusion})==60
    assert all(x.get('candidate_symbol')=='fused_gelu_tanh_mul_quant_kernel' and x.get('quantized_shape',[-1])[-1]==21504 for x in fusion)
PY
}

if [[ ! -s "$artifacts/control/TERMINAL.json" ]]; then
  sudo docker rm -f gemma-fusion-candidate-v0513 >/dev/null 2>&1 || true
  start_server control gemma-fusion-control-v0513
  run_arm control gemma-fusion-control-v0513
  validate_stack control
fi

sudo docker rm -f gemma-fusion-control-v0513 >/dev/null 2>&1 || true
if [[ ! -s "$artifacts/candidate/TERMINAL.json" ]]; then
  start_server candidate gemma-fusion-candidate-v0513
  run_arm candidate gemma-fusion-candidate-v0513
  validate_stack candidate
fi

python3 - "$artifacts/component/TERMINAL.json" "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
component=json.load(open(sys.argv[1])); control=json.load(open(sys.argv[2])); candidate=json.load(open(sys.argv[3]))
out=pathlib.Path(sys.argv[4]); tmp=out.with_suffix('.part')
c=float(control['service_seconds_per_request']); q=float(candidate['service_seconds_per_request']); gain=1-q/c
valid=all(x.get('pass') and x.get('complete_requests')==32 and len(x.get('rows',[]))==32 for x in (control,candidate)) and component.get('pass') is True
classification='frontier_pass' if valid and q<=0.6381105231 else ('stable_positive' if valid and gain>0 else 'stack_negative')
value={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and gain>0,'component':component,'control':control,'candidate':candidate,'control_service_seconds_per_request':c,'candidate_service_seconds_per_request':q,'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105231,'economic_ceiling_pass':valid and q<=0.6381105231,'rows_and_cache_valid':valid,'candidate_server_retained':'gemma-fusion-candidate-v0513'}
tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
atomic_terminal completed stacked_component_and_endpoint_terminal_persisted
