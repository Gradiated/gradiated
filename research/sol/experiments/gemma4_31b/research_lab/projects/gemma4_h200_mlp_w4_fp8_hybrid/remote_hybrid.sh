#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-h200-mlp-w4-hybrid
input="$root/input"
w4="$root/w4"
hybrid="$root/hybrid-checkpoint"
artifacts="$root/artifacts"
current=/home/glmrunner/gemma4-h200-dense-fp8-streamk/checkpoint
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
  for container in gemma-w4hybrid-control gemma-w4hybrid-candidate; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/hybrid-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/hybrid-compact.tar.gz" >"$root/hybrid-compact.tar.gz.sha256"
}

trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"
state worker_initialized
test -s "$current/model.safetensors.index.json" || fail current_checkpoint_missing
test -s "$input/GPU_INPUT_MANIFEST.json" || fail input_manifest_missing
test -s "$input/layer0_mlp_awq.safetensors" || fail component_snapshot_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_missing

rm -rf "$artifacts/component"
state component_cuda_started
sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work" -v "$current:/current:ro" \
  -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e TORCH_EXTENSIONS_DIR=/work/torch-extensions "$image" \
  python3 /work/input/hybrid_component.py \
  --output /work/artifacts/component --current-checkpoint /current \
  --w4-component /work/input/layer0_mlp_awq.safetensors \
  >"$artifacts/component.stdout" 2>"$artifacts/component.stderr" || {
    test -s "$artifacts/component/TERMINAL.json" || fail component_failed_without_terminal
  }
state component_science_started

python3 - "$artifacts/component/TERMINAL.json" <<'PY' || {
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True
PY
  atomic_terminal component_negative component_correctness_failed
  exit 20
}

python3 - "$artifacts/component/TERMINAL.json" <<'PY' || {
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('promotion_pass') is True
PY
  atomic_terminal component_reject call_weighted_bound_below_three_percent
  exit 21
}

if sudo docker run --rm --gpus all "$image" bash -lc 'command -v ncu' >"$artifacts/ncu.path" 2>"$artifacts/ncu.detect.stderr"; then
  for arm in control candidate; do
    rm -rf "$artifacts/counter-$arm"
    sudo docker run --rm --gpus all --ipc=host \
      -v "$root:/work" -v "$current:/current:ro" \
      -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
      -e TORCH_EXTENSIONS_DIR=/work/torch-extensions "$image" \
      ncu --profile-from-start off --target-processes all --csv \
      --section LaunchStats --section Occupancy --section SpeedOfLight \
      --section ComputeWorkloadAnalysis --section MemoryWorkloadAnalysis_Tables \
      --log-file "/work/artifacts/ncu-$arm.csv" \
      python3 /work/input/hybrid_component.py \
      --output "/work/artifacts/counter-$arm" --current-checkpoint /current \
      --w4-component /work/input/layer0_mlp_awq.safetensors --counter-probe "$arm" \
      >"$artifacts/ncu-$arm.stdout" 2>"$artifacts/ncu-$arm.stderr" || fail "ncu_$arm.failed"
  done
else
  python3 - "$artifacts/component/TERMINAL.json" "$artifacts/CAUSAL_COUNTERS.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
m32=next(r for r in x['rows'] if r['m']==32)
out={'schema_version':1,'classification':'ncu_unavailable','measured':{'control_layer_ms':m32['control_timing']['cuda_event']['p50_ms'],'candidate_layer_ms':m32['candidate_timing']['cuda_event']['p50_ms']},'analytical':{'fp8_gate_up_weight_bytes':5376*43008,'fp8_down_weight_bytes':21504*5376,'w4_gate_up_payload_bytes':5376*43008/2,'w4_down_payload_bytes':21504*5376/2,'prediction':'more than 35% compulsory MLP weight-byte reduction after scales and zero-points'},'counter_boundary':'Nsight Compute is absent from the pinned runtime image; endpoint promotion still requires the measured timing and path gates.'}
open(sys.argv[2],'w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY
fi

test -s "$w4/model.safetensors.index.json" || fail full_w4_snapshot_missing
rm -rf "$hybrid"
python3 "$input/build_hybrid_checkpoint.py" --current "$current" --w4 "$w4" --output "$hybrid" \
  >"$artifacts/build-hybrid.stdout" 2>"$artifacts/build-hybrid.stderr" || fail hybrid_checkpoint_build_failed

base_args=(
  --served-model-name google/gemma-4-31B-it --dtype bfloat16
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking
  --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1
  --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8
)

start_server() {
  local arm=$1 container=$2 checkpoint=$3 quant=$4
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" -v "$current:/current:ro" \
    -e PYTHONPATH=/work/input:/work/input/stack:/sgl-workspace/sglang/python \
    -e TORCH_EXTENSIONS_DIR=/work/torch-extensions \
    -e STACK_BASELINE_SITECUSTOMIZE=/work/input/stack/residual_sitecustomize.py \
    -e RESIDUAL_ARM=control \
    -e RESIDUAL_CANDIDATE_AUDIT="/work/artifacts/$arm-audit/attention.jsonl" \
    -e HYBRID_ARM="$arm" \
    -e HYBRID_QUANT_AUDIT="/work/artifacts/$arm-audit/hybrid.jsonl" \
    -e QKV_EPILOGUE_AUDIT="/work/artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/input/stack/proven_v0513_endpoint_entrypoint.py \
    --model-path "$checkpoint" --tokenizer-path /current --quantization "$quant" "${base_args[@]}" \
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
}

coherence() {
  local arm=$1
  python3 - "$artifacts/$arm.coherence.json" <<'PY'
import json,sys,urllib.request
rows=[]
checks=(('Reply with exactly: READY',lambda x:'READY' in x.upper()),('What is 2+2? Reply with only the number.',lambda x:'4' in x),('Return only JSON with key "status" and value "ok".',lambda x:'status' in x.lower() and 'ok' in x.lower()))
for prompt,check in checks:
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    text=raw['choices'][0]['message']['content'].strip()
    rows.append({'prompt':prompt,'text':text,'pass':bool(text) and check(text)})
out={'rows':rows,'pass':all(r['pass'] for r in rows)}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\n')
assert out['pass']
PY
}

run_arm() {
  local arm=$1 container=$2
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/input/stack/fp8_qkv_paired_runner.py \
    --output "/work/artifacts/$arm" --arm "$arm" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  python3 - "$artifacts/$arm/TERMINAL.json" <<'PY' || fail "$arm.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests')==32 and len(x.get('rows',[]))==32
assert x.get('cache',{}).get('cached_prompt_tokens_delta')==17120
assert x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
PY
}

start_server control gemma-w4hybrid-control /current fp8
run_arm control gemma-w4hybrid-control
sudo docker rm -f gemma-w4hybrid-control >/dev/null 2>&1 || true

start_server candidate gemma-w4hybrid-candidate /work/hybrid-checkpoint awq_marlin
coherence candidate || {
  atomic_terminal coherence_reject hybrid_failed_three_prompt_gate
  exit 22
}
run_arm candidate gemma-w4hybrid-candidate

python3 - "$artifacts/candidate-audit/hybrid.jsonl" <<'PY' || fail candidate_path_invalid
import json,sys
rows=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]
awq=[x for x in rows if x.get('representation')=='awq_marlin_w4a16']
fp8=[x for x in rows if x.get('representation')=='dynamic_fp8']
assert len(awq)==120 and len({x['prefix'] for x in awq})==120
assert all('.mlp.' in x['prefix'] for x in awq)
assert fp8 and all('.mlp.' not in (x.get('prefix') or '') for x in fp8)
PY

python3 - "$artifacts/component/TERMINAL.json" "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
component=json.load(open(sys.argv[1])); control=json.load(open(sys.argv[2])); candidate=json.load(open(sys.argv[3]))
c=float(control['service_seconds_per_request']); h=float(candidate['service_seconds_per_request']); gain=1-h/c
valid=all(x.get('pass') and x.get('complete_requests')==32 and len(x.get('rows',[]))==32 for x in (control,candidate))
value={'schema_version':1,'status':'terminal','classification':'frontier_pass' if valid and h<=0.6381105231 else ('stable_positive' if valid and gain>0 else 'endpoint_negative'),'pass':valid,'component':component,'control_service_seconds_per_request':c,'hybrid_service_seconds_per_request':h,'reduction_fraction':gain,'economic_ceiling_seconds_per_request':0.6381105231,'economic_ceiling_pass':valid and h<=0.6381105231,'rows_and_cache_valid':valid,'coherence':json.load(open(pathlib.Path(sys.argv[3]).parent.parent/'candidate.coherence.json'))}
out=pathlib.Path(sys.argv[4]); tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
atomic_terminal completed component_counters_coherence_and_endpoint_pair_persisted
