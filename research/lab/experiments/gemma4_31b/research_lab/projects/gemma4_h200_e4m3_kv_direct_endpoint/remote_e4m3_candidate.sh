#!/usr/bin/env bash
set -Eeuo pipefail

root=${E4M3_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/endpoint-artifacts"
checkpoint=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-e4m3-kv-direct-candidate
mkdir -p "$artifacts/candidate-audit"

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
x=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'candidate_science_started':False}
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
rm -f "$artifacts/WORKER_TERMINAL.json"

test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_not_resident
printf '%q ' \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e4m3 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 >"$artifacts/candidate.server-args.txt"

sudo docker rm -f "$container" >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/e4m3" \
  -e PYTHONPATH=/work/e4m3/input:/sgl-workspace/sglang/python \
  -e QKV_STACK_ARM=candidate -e QKV_EPILOGUE_AUDIT=/work/e4m3/endpoint-artifacts/candidate-audit/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/e4m3/endpoint-artifacts/candidate-audit/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/e4m3/endpoint-artifacts/candidate-audit/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/e4m3/endpoint-artifacts/candidate-audit/runtime.json \
  -e FP8_STACK_MODULE_AUDIT=/work/e4m3/endpoint-artifacts/candidate-audit/stack-modules.jsonl \
  -e FP8_STACK_CONSUMER_AUDIT=/work/e4m3/endpoint-artifacts/candidate-audit/stack-consumers.jsonl \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" python3 /work/e4m3/input/proven_v0513_endpoint_entrypoint.py \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e4m3 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 >"$artifacts/candidate.container-id"

ready=0
for _ in $(seq 1 150); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/candidate.models.json" 2>"$artifacts/candidate.models.stderr"; then ready=1; break; fi
  sleep 4
done
sudo docker logs "$container" >"$artifacts/candidate.server-start.log" 2>&1 || true
[[ "$ready" -eq 1 ]] || fail candidate_server_not_ready

python3 - "$artifacts/E4M3_VS_E5M2_DISCRIMINATOR.json" <<'PY' || fail candidate_coherence_discriminator_failed
import json,sys,urllib.request
rows=[]
for expected,prompt in [('READY','Reply with exactly: READY'),('4','What is 2+2? Reply with only the number.'),('json','Return only a JSON object with key "status" and string value "ok".')]:
    body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
    raw=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=180))
    text=raw['choices'][0]['message']['content'].strip()
    ok=text==expected if expected!='json' else json.loads(text.strip('`json\n'))=={'status':'ok'}
    rows.append({'e5m2_reference_expected':expected,'e4m3_text':text,'pass':ok})
value={'schema_version':1,'kind':'nonzero_e4m3_vs_persisted_e5m2_coherence_discriminator','pass':all(r['pass'] for r in rows),'rows':rows}
open(sys.argv[1],'w').write(json.dumps(value,indent=2,sort_keys=True)+'\n'); assert value['pass']
PY

state candidate_science_started
sudo docker exec "$container" python3 /work/e4m3/input/fp8_qkv_paired_runner.py --output /work/e4m3/endpoint-artifacts/candidate --arm e4m3_kv_direct --concurrency 32 >"$artifacts/candidate.runner.stdout" 2>"$artifacts/candidate.runner.stderr" || fail candidate_runner_failed
python3 - "$artifacts/candidate/TERMINAL.json" "$artifacts/ENDPOINT_RESULT.json" "$artifacts/candidate.server-args.txt" "$artifacts/candidate-audit" <<'PY' || fail candidate_terminal_invalid
import json,math,os,pathlib,sys
x=json.load(open(sys.argv[1])); out=pathlib.Path(sys.argv[2]); args=pathlib.Path(sys.argv[3]).read_text(); audit=pathlib.Path(sys.argv[4])
def rows(name):
 p=audit/name
 return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []
modules=rows('modules.jsonl'); consumers=rows('consumers.jsonl'); qkv=rows('qkv.jsonl')
path_ok=('fp8_e4m3' in args and args.count('attention-backend triton')==2 and 'flash' not in args.lower() and bool(consumers) and bool(qkv))
accounting=x.get('cache',{}).get('cached_prompt_tokens_delta')==17120 and x.get('cache',{}).get('uncached_prompt_tokens_delta')==117728
responses=all(r.get('text_nonempty') and r.get('text_finite') and r.get('error') is None for r in x.get('rows',[]))
valid=x.get('pass') is True and x.get('complete_requests')==32 and len(x.get('rows',[]))==32 and accounting and responses and path_ok
s=float(x['service_seconds_per_request']); classification='retain_direct' if valid and s<0.6743258590313417 else ('hybrid_comparator' if valid else 'close')
value={'schema_version':1,'status':'terminal','classification':classification,'pass':valid,'candidate_service_seconds_per_request':s,'persisted_e5m2_control_seconds_per_request':0.6743258590313417,'economic_ceiling_seconds_per_request':0.6381105231,'relative_to_control_fraction':1-s/0.6743258590313417,'candidate':x,'candidate_path_proof':{'server_args':args,'fp8_modules':len(modules),'fp8_consumer_events':consumers,'qkv_events':qkv,'triton_only':path_ok},'accounting_pass':accounting,'response_pass':responses}
tmp=out.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,out)
assert valid
PY
atomic "$artifacts/WORKER_TERMINAL.json" completed candidate_scientific_terminal_persisted
