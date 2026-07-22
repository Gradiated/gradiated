#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-h200-dense-fp8-streamk
program="$root/program"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v={'schema_version':1,'classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v=json.loads(p.read_text()) if p.exists() else {'compile_started':False,'candidate_cuda_started':False,'candidate_science_started':False,'endpoint_pair_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

compact() {
  set +e
  for container in streamk-component streamk-control streamk-candidate; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/streamk-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/streamk-compact.tar.gz" >"$root/streamk-compact.tar.gz.sha256"
}

trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"
sudo docker rm -f streamk-component streamk-control streamk-candidate >/dev/null 2>&1 || true

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

state compile_started
rm -rf "$root/build"
mkdir -p "$root/build"
sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work" "$image" \
  python3 /work/program/build_candidate.py --project-root /work/program \
    --build-root /work/build --output /work/artifacts/BUILD.json \
    >"$artifacts/build.stdout" 2>"$artifacts/build.stderr" || fail candidate_compile_failed
module=$(find "$root/build" -maxdepth 1 -type f -name 'gemma4_fp8_down_streamk*.so' -print -quit)
test -n "$module" || fail candidate_module_missing
module_in_container="/work/build/$(basename "$module")"

start_server() {
  local arm=$1 container=$2 mode=$3
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  local candidate_env=()
  if [[ "$mode" != control ]]; then
    candidate_env=(
      -e DOWN_STREAMK_ARM="$arm"
      -e DOWN_STREAMK_MODE="$mode"
      -e DOWN_STREAMK_MODULE="$module_in_container"
      -e DOWN_STREAMK_AUDIT="/work/artifacts/$arm-audit/down_streamk.jsonl"
    )
  fi
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" \
    -e PYTHONPATH=/work/program:/work/program/inputs/runtime:/sgl-workspace/sglang/python \
    -e QKV_EPILOGUE_AUDIT="/work/artifacts/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/artifacts/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/artifacts/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/artifacts/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "${candidate_env[@]}" "$image" \
    python3 /work/program/inputs/runtime/proven_v0513_endpoint_entrypoint.py "${base_args[@]}" \
    >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then
      ready=1
      break
    fi
    sleep 5
  done
  sudo docker logs "$container" >"$artifacts/$arm.server-start.log" 2>&1 || true
  [[ "$ready" -eq 1 ]] || fail "$arm.server_not_ready"
}

run_exact() {
  local arm=$1 container=$2
  mkdir -p "$artifacts/$arm"
  sudo docker exec "$container" python3 /work/program/inputs/runtime/fp8_qkv_paired_runner.py \
    --output "/work/artifacts/$arm" --arm "$arm" --concurrency 32 \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
}

run_discovery() {
  python3 - "$artifacts/DISCOVERY.json" <<'PY'
import json,sys,urllib.request
prompt=' '.join(['stream-k discovery']*96)
body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':1}).encode()
request=urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'})
response=json.load(urllib.request.urlopen(request,timeout=180))
value={'pass':bool(response.get('choices')),'usage':response.get('usage'),'response_id':response.get('id')}
open(sys.argv[1],'w').write(json.dumps(value,indent=2,sort_keys=True)+'\n')
assert value['pass']
PY
}

state candidate_cuda_started
state candidate_science_started
start_server component streamk-component component
run_discovery
run_exact component streamk-component
sudo docker stop -t 30 streamk-component >/dev/null 2>&1 || true
cat "$artifacts/build.stdout" "$artifacts/build.stderr" >"$artifacts/build.combined.log"
set +e
sync_args=()
if [[ -f "$program/inputs/sync/TERMINAL.json" && -f "$program/inputs/sync/BINDING.json" ]]; then
  sync_args=(--sync-terminal "$program/inputs/sync/TERMINAL.json" --sync-binding "$program/inputs/sync/BINDING.json")
fi
python3 "$program/consume_component.py" \
  --audit "$artifacts/component-audit/down_streamk.jsonl" \
  --runner-terminal "$artifacts/component/TERMINAL.json" \
  --build-log "$artifacts/build.combined.log" \
  --output "$artifacts/COMPONENT_TERMINAL.json" \
  "${sync_args[@]}"
component_rc=$?
set -e
if [[ "$component_rc" -ne 0 ]]; then
  atomic_terminal component_correctness_failure exact_real_consumer_component_failed
  exit 0
fi
promote=$(python3 -c 'import json,sys; print("yes" if json.load(open(sys.argv[1]))["promote_endpoint"] else "no")' "$artifacts/COMPONENT_TERMINAL.json")
if [[ "$promote" != yes ]]; then
  atomic_terminal component_no_endpoint_promotion measured_bound_below_five_percent
  exit 0
fi

state endpoint_pair_started
start_server control streamk-control control
run_exact control streamk-control
sudo docker stop -t 30 streamk-control >/dev/null 2>&1 || true
start_server candidate streamk-candidate endpoint
run_exact candidate streamk-candidate
sudo docker stop -t 30 streamk-candidate >/dev/null 2>&1 || true
python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
control=json.load(open(sys.argv[1])); candidate=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3])
c=float(control['service_seconds_per_request']); q=float(candidate['service_seconds_per_request'])
value={'schema_version':1,'control_seconds_per_request':c,'candidate_seconds_per_request':q,'gain_fraction':1-q/c,'pass':control.get('pass') is True and candidate.get('pass') is True and q<c}
temporary=out.with_suffix('.part')
temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
os.replace(temporary,out)
PY
atomic_terminal endpoint_pair_complete conditional_c32_pair_persisted
