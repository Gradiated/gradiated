#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma-kernel-frontier
input="$root/mtp-input"
assistant="$root/mtp-assistant"
artifacts="$root/artifacts/fp8-mtp-v0513"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"

atomic_json() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
v={'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v=json.loads(p.read_text()) if p.exists() else {'control_cuda_started':False,'control_science_started':False,'mtp_cuda_started':False,'mtp_science_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_json "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"
  exit 1
}

finalize() {
  set +e
  for container in gemma-fp8-control-v0513 gemma-fp8-mtp-v0513; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/fp8-mtp-v0513-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/fp8-mtp-v0513-compact.tar.gz" >"$root/fp8-mtp-v0513-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_json "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json"

sudo docker image inspect "$image" >/dev/null 2>&1 || sudo docker pull "$image" >"$artifacts/image-pull.log" 2>&1 || fail image_pull_failed
sudo docker image inspect "$image" >"$artifacts/image-inspect.json"

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
  local arm=$1 container=$2; shift 2
  local audit="$artifacts/$arm-audit"
  mkdir -p "$audit"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state "${arm}_cuda_started"
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host -v "$root:/work" \
    -e FP8_MODULE_AUDIT="/work/artifacts/fp8-mtp-v0513/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/artifacts/fp8-mtp-v0513/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/artifacts/fp8-mtp-v0513/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/mtp-input/endpoint_entrypoint_v0513.py "${base_args[@]}" "$@" \
    >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then ready=1; break; fi
    sleep 5
  done
  sudo docker logs "$container" >"$artifacts/$arm.server-start.log" 2>&1 || true
  [[ "$ready" -eq 1 ]] || fail "$arm.server_not_ready"
}

run_arm() {
  local arm=$1 container=$2 output="$artifacts/$1"
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/mtp-input/paired_endpoint_runner.py --output "/work/artifacts/fp8-mtp-v0513/$arm" --arm "${3}" \
    >"$artifacts/$arm.runner.stdout" 2>"$artifacts/$arm.runner.stderr" || fail "$arm.runner_failed"
  python3 - "$output/TERMINAL.json" <<'PY' || fail "$arm.terminal_invalid"
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
PY
}

if ! python3 - "$artifacts/control/TERMINAL.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
PY
then
  sudo docker rm -f gemma-fp8-mtp-v0513 >/dev/null 2>&1 || true
  start_server control gemma-fp8-control-v0513
  run_arm control gemma-fp8-control-v0513 fp8_control
fi

sudo docker rm -f gemma-fp8-control-v0513 >/dev/null 2>&1 || true
if ! python3 - "$artifacts/mtp/TERMINAL.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
PY
then
  start_server mtp gemma-fp8-mtp-v0513 \
    --speculative-algorithm NEXTN --speculative-draft-model-path /work/mtp-assistant \
    --speculative-num-steps 1 --speculative-eagle-topk 1 --speculative-num-draft-tokens 2
  run_arm mtp gemma-fp8-mtp-v0513 fp8_mtp_c32
fi

python3 - "$artifacts/control/TERMINAL.json" "$artifacts/mtp/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
c=json.load(open(sys.argv[1])); m=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3]); tmp=out.with_suffix('.part')
control=float(c['service_seconds_per_request']); candidate=float(m['service_seconds_per_request']); reduction=1-candidate/control
diag_equal=[a['output_token_ids_sha256']==b['output_token_ids_sha256'] for a,b in zip(c['diagnostics'],m['diagnostics'])]
row_equal=[a['output_token_ids_sha256']==b['output_token_ids_sha256'] for a,b in zip(c['rows'],m['rows'])]
target_modules=[json.loads(x) for x in pathlib.Path(out.parent/'mtp-audit/modules.jsonl').read_text().splitlines() if x]
consumers=[json.loads(x) for x in pathlib.Path(out.parent/'mtp-audit/consumers.jsonl').read_text().splitlines() if x]
target_fp8=any('language_model' in str(x.get('prefix')) or str(x.get('prefix','')).startswith('model.layers') for x in target_modules)
target_consumer=any('language_model' in str(x.get('prefix')) or str(x.get('prefix','')).startswith('model.layers') for x in consumers)
telemetry=m['speculation']; valid=all(diag_equal) and all(row_equal) and target_fp8 and target_consumer and telemetry.get('pass') is True
classification='frontier_pass' if valid and candidate<=0.7145910375209391 else ('stable_positive' if valid and reduction>0 else 'mtp_negative')
v={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and reduction>0,'control':c,'mtp':m,'control_service_seconds_per_request':control,'mtp_service_seconds_per_request':candidate,'reduction_fraction':reduction,'frontier_ceiling_seconds_per_request':0.7145910375209391,'frontier_pass':valid and candidate<=0.7145910375209391,'promotion_pass':valid and reduction>=0.04537074092551777,'diagnostic_output_ids_equal':all(diag_equal),'exact_output_ids_equal':all(row_equal),'target_fp8_module_proven':target_fp8,'target_fp8_consumer_proven':target_consumer,'speculation':telemetry}
tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
atomic_json "$artifacts/WORKER_TERMINAL.json" completed paired_scientific_terminal_persisted
