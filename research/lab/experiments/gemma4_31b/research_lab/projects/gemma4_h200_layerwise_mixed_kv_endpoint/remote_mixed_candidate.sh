#!/usr/bin/env bash
set -Eeuo pipefail

root=${MIXED_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/endpoint-artifacts"
checkpoint=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-layerwise-mixed-kv-candidate
old_container=gemma-e4m3-kv-direct-candidate
rm -rf "$artifacts"
mkdir -p "$artifacts/mixed-kv-audit" "$artifacts/candidate-audit"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'component_started':False,'component_passed':False,'candidate_science_started':False}
x[sys.argv[2]]=True; x['updated_unix_s']=time.time(); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() { atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"; exit 1; }
finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/candidate.server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/candidate.container-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/compact.tar.gz" >"$root/compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR

test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_not_resident
printf '%q ' \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 >"$artifacts/candidate.server-args.txt"

sudo docker rm -f "$old_container" >/dev/null 2>&1 || true
sudo docker rm -f "$container" >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/mixed" \
  -e PYTHONPATH=/work/mixed/input:/sgl-workspace/sglang/python \
  -e FP8_MODULE_AUDIT=/work/mixed/endpoint-artifacts/candidate-audit/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/mixed/endpoint-artifacts/candidate-audit/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/mixed/endpoint-artifacts/candidate-audit/runtime.json \
  -e MIXED_KV_AUDIT_ROOT=/work/mixed/endpoint-artifacts/mixed-kv-audit \
  -e MIXED_KV_AUDIT_GATE=/work/mixed/endpoint-artifacts/COMPONENT_ARMED \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" python3 /work/mixed/input/mixed_endpoint_entrypoint.py \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 >"$artifacts/candidate.container-id"

ready=0
for _ in $(seq 1 150); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/candidate.models.json" 2>"$artifacts/candidate.models.stderr"; then
    ready=1
    break
  fi
  sleep 4
done
sudo docker logs "$container" >"$artifacts/candidate.server-start.log" 2>&1 || true
[[ "$ready" -eq 1 ]] || fail candidate_server_not_ready
test -f "$artifacts/mixed-kv-audit/init.json" || fail mixed_pool_init_audit_missing

state component_started
sudo docker exec "$container" python3 /work/mixed/input/component_path_check.py \
  /work/mixed/endpoint-artifacts/mixed-kv-audit \
  /work/mixed/endpoint-artifacts/COMPONENT_RESULT.json \
  /work/mixed/endpoint-artifacts/candidate.server-args.txt \
  >"$artifacts/component.stdout" 2>"$artifacts/component.stderr" || {
    python3 - "$artifacts/COMPONENT_RESULT.json" "$artifacts/ENDPOINT_RESULT.json" <<'PY'
import json,os,pathlib,sys
component=json.load(open(sys.argv[1])) if pathlib.Path(sys.argv[1]).exists() else {'pass':False,'failures':['component_result_missing']}
out=pathlib.Path(sys.argv[2])
value={'schema_version':1,'status':'terminal','classification':'close_mixed','pass':False,'component_path_check':component,'candidate_science_started':False}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
    atomic "$artifacts/WORKER_TERMINAL.json" component_reject exact_component_path_check_failed
    exit 2
  }
state component_passed

state candidate_science_started
sudo docker exec "$container" python3 /work/mixed/input/fp8_qkv_paired_runner.py \
  --output /work/mixed/endpoint-artifacts/candidate \
  --arm layerwise_mixed_e4m3_local_e5m2_global \
  --concurrency 32 >"$artifacts/candidate.runner.stdout" 2>"$artifacts/candidate.runner.stderr" || fail candidate_runner_failed

python3 - "$artifacts/candidate/TERMINAL.json" "$artifacts/candidate/WORKLOAD.json" "$artifacts/COMPONENT_RESULT.json" "$artifacts/ENDPOINT_RESULT.json" "$artifacts/candidate.server-args.txt" <<'PY' || fail candidate_terminal_invalid
import json,math,os,pathlib,sys
terminal=json.load(open(sys.argv[1]))
workload=json.load(open(sys.argv[2]))
component=json.load(open(sys.argv[3]))
out=pathlib.Path(sys.argv[4])
args=pathlib.Path(sys.argv[5]).read_text()
rows=terminal.get('rows',[])
identities=[row.get('request_sha256') for row in sorted(rows,key=lambda row: row.get('index',-1))]
expected_identities=workload.get('request_sha256',[])
usage=all(row.get('prompt_tokens')==4214 and row.get('completion_tokens')==358 for row in rows)
responses=all(row.get('text_nonempty') and row.get('text_finite') and row.get('error') is None for row in rows)
accounting=terminal.get('cache',{}).get('cached_prompt_tokens_delta')==17120 and terminal.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
path_ok=(component.get('pass') is True and '--kv-cache-dtype fp8_e5m2' in args and args.count('attention-backend triton')==2 and 'flash' not in args.lower())
valid=(terminal.get('pass') is True and terminal.get('complete_requests')==32 and len(rows)==32 and usage and responses and accounting and identities==expected_identities and path_ok)
service=float(terminal['service_seconds_per_request'])
control=0.6743258590313417
local_boundary_fraction=0.15312032
perfect_local_removal_seconds=service*(1-local_boundary_fraction)
recoverable=perfect_local_removal_seconds < control
classification='retain_mixed' if valid and (service < control or recoverable) else 'close_mixed'
value={
 'schema_version':1,
 'status':'terminal',
 'classification':classification,
 'pass':valid,
 'candidate_service_seconds_per_request':service,
 'persisted_e5m2_control_seconds_per_request':control,
 'persisted_uniform_e4m3_seconds_per_request':0.7022842785938792,
 'relative_to_control_fraction':1-service/control,
 'economic_ceiling_seconds_per_request':0.6381105231,
 'local_attention_boundary_fraction':local_boundary_fraction,
 'perfect_local_removal_seconds_per_request':perfect_local_removal_seconds,
 'recoverable_by_perfect_local_attention_removal':recoverable,
 'component_path_check':component,
 'request_identity_pass':identities==expected_identities,
 'usage_pass':usage,
 'accounting_pass':accounting,
 'response_pass':responses,
 'candidate_path_pass':path_ok,
 'candidate':terminal,
}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
assert valid
PY
atomic "$artifacts/WORKER_TERMINAL.json" completed candidate_scientific_terminal_persisted
