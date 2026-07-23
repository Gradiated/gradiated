#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma-kernel-frontier
input="$root/qkv-stack-input"
artifacts="$root/artifacts/fp8-qkv-stack-v0513"
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
v=json.loads(p.read_text()) if p.exists() else {'control_cuda_started':False,'control_science_started':False,'candidate_cuda_started':False,'candidate_science_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

fail() {
  atomic_json "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"
  exit 1
}

finalize() {
  set +e
  for container in gemma-fp8-qkv-control-v0513 gemma-fp8-qkv-candidate-v0513; do
    sudo docker logs "$container" >"$artifacts/$container.final.log" 2>&1 || true
    sudo docker inspect "$container" >"$artifacts/$container.inspect.json" 2>&1 || true
  done
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/fp8-qkv-stack-v0513-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/fp8-qkv-stack-v0513-compact.tar.gz" >"$root/fp8-qkv-stack-v0513-compact.tar.gz.sha256"
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
  cp "$input/stack_sitecustomize.py" "$input/sitecustomize.py"
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host -v "$root:/work" \
    -e PYTHONPATH="/work/qkv-stack-input:/sgl-workspace/sglang/python" \
    -e QKV_STACK_ARM="$arm" -e QKV_EPILOGUE_AUDIT="/work/artifacts/fp8-qkv-stack-v0513/$arm-audit/qkv.jsonl" \
    -e FP8_MODULE_AUDIT="/work/artifacts/fp8-qkv-stack-v0513/$arm-audit/modules.jsonl" \
    -e FP8_CONSUMER_AUDIT="/work/artifacts/fp8-qkv-stack-v0513/$arm-audit/consumers.jsonl" \
    -e FP8_RUNTIME_AUDIT="/work/artifacts/fp8-qkv-stack-v0513/$arm-audit/runtime.json" \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/qkv-stack-input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}" "$@" \
    >"$artifacts/$arm.container-id"
  local ready=0
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/$arm.models.json" 2>"$artifacts/$arm.models.stderr"; then ready=1; break; fi
    sleep 5
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
    ok=text==want if want!='json' else json.loads(text.strip('`json\\n'))=={'status':'ok'}
    rows.append({'want':want,'text':text,'pass':ok})
out={'rows':rows,'pass':all(row['pass'] for row in rows)}
open(sys.argv[1],'w').write(json.dumps(out,indent=2)+'\\n')
assert out['pass']
PY
}

run_arm() {
  local arm=$1 container=$2 output="$artifacts/$1"
  state "${arm}_science_started"
  sudo docker exec "$container" python3 /work/qkv-stack-input/fp8_qkv_paired_runner.py --output "/work/artifacts/fp8-qkv-stack-v0513/$arm" --arm "${3}" \
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
  sudo docker rm -f gemma-fp8-qkv-candidate-v0513 >/dev/null 2>&1 || true
  start_server control gemma-fp8-qkv-control-v0513
  run_arm control gemma-fp8-qkv-control-v0513 fp8_control
fi

sudo docker rm -f gemma-fp8-qkv-control-v0513 >/dev/null 2>&1 || true
if ! python3 - "$artifacts/candidate/TERMINAL.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x.get('complete_requests') == 32
PY
then
  start_server candidate gemma-fp8-qkv-candidate-v0513
  run_arm candidate gemma-fp8-qkv-candidate-v0513 fp8_qkv_candidate
fi

python3 - "$artifacts/control/TERMINAL.json" "$artifacts/candidate/TERMINAL.json" "$artifacts/PAIRED_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
c=json.load(open(sys.argv[1])); q=json.load(open(sys.argv[2])); out=pathlib.Path(sys.argv[3]); tmp=out.with_suffix('.part')
control=float(c['service_seconds_per_request']); candidate=float(q['service_seconds_per_request']); reduction=1-candidate/control
smoke=[json.load(open(out.parent/f'{arm}.smoke.json')) for arm in ('control','candidate')]
modules=[json.loads(x) for x in (out.parent/'candidate-audit/modules.jsonl').read_text().splitlines() if x]
consumers=[json.loads(x) for x in (out.parent/'candidate-audit/consumers.jsonl').read_text().splitlines() if x]
qkv=[json.loads(x) for x in (out.parent/'candidate-audit/qkv.jsonl').read_text().splitlines() if x]
target_fp8=len(modules)==240 and bool(consumers)
target_qkv=bool(qkv) and all(x.get('candidate_symbol')=='_qkv_norm_rope_inplace_kernel' and x.get('dtype')=='torch.bfloat16' for x in qkv)
rows_valid=all(x.get('complete_requests')==32 and len(x.get('rows',[]))==32 and all(r.get('text_nonempty') and r.get('text_finite') for r in x['rows']) and x.get('cache',{}).get('cached_prompt_tokens_delta')==17120 and x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728 for x in (c,q))
valid=all(x.get('pass') for x in smoke) and rows_valid and target_fp8 and target_qkv
classification='frontier_stack_pass' if valid and candidate<=0.7145910375209391 else ('stable_positive' if valid and reduction>0 else 'stack_negative')
v={'schema_version':1,'status':'terminal','classification':classification,'pass':valid and reduction>0,'control':c,'candidate':q,'control_service_seconds_per_request':control,'candidate_service_seconds_per_request':candidate,'reduction_fraction':reduction,'frontier_ceiling_seconds_per_request':0.7145910375209391,'frontier_stack_pass':valid and candidate<=0.7145910375209391,'smoke':smoke,'target_fp8_module_proven':target_fp8,'target_fp8_consumer_proven':bool(consumers),'target_qkv_epilogue_proven':target_qkv,'qkv_audit':qkv,'rows_valid':rows_valid}
tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
PY
atomic_json "$artifacts/WORKER_TERMINAL.json" completed paired_scientific_terminal_persisted
