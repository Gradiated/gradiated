#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-h100-fp8-qkv
input="$root/input"
checkpoint="$root/checkpoint"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-h100-fp8-qkv-c32
mkdir -p "$artifacts"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'candidate_science_started':False}
v[sys.argv[2]]=True; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/container-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/compact.tar.gz" >"$root/compact.tar.gz.sha256"
}
fail() { atomic "$artifacts/WORKER_TERMINAL.json" "$1" "$2"; exit 1; }
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/WORKER_TERMINAL.json" "$artifacts/INVOCATION_STATE.json" "$artifacts/qkv.jsonl" "$artifacts/modules.jsonl" "$artifacts/consumers.jsonl"

test -f "$checkpoint/model.safetensors.index.json" || fail integration_failure checkpoint_not_staged
sudo docker image inspect "$image" >/dev/null 2>&1 || sudo docker pull "$image" >"$artifacts/image-pull.log" 2>&1 || fail integration_failure image_pull_failed
state candidate_cuda_started
cp "$input/stack_sitecustomize.py" "$input/sitecustomize.py"
sudo docker rm -f "$container" >/dev/null 2>&1 || true
sudo docker run -d --name "$container" --gpus all --ipc=host --network host -v "$root:/work" \
  -e PYTHONPATH="/work/input:/sgl-workspace/sglang/python" \
  -e QKV_STACK_ARM=candidate -e QKV_EPILOGUE_AUDIT=/work/artifacts/qkv.jsonl \
  -e FP8_STACK_MODULE_AUDIT=/work/artifacts/modules.jsonl -e FP8_STACK_CONSUMER_AUDIT=/work/artifacts/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/artifacts/runtime.json -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" python3 /work/input/proven_v0513_endpoint_entrypoint.py \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 >"$artifacts/container-id.txt"
for _ in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/models.json" 2>"$artifacts/models.stderr" && break; sleep 5; done
test -s "$artifacts/models.json" || fail integration_failure server_not_ready
curl -fsS http://127.0.0.1:30000/metrics >"$artifacts/metrics-idle.prom"
python3 - "$artifacts/metrics-idle.prom" <<'PY' || fail integration_failure queue_not_idle
import re,sys
assert not any(float(x)>0 for x in re.findall(r'sglang:(?:num_running_reqs|num_queue_reqs)\\s+([0-9.]+)',open(sys.argv[1]).read()))
PY
state candidate_science_started
sudo docker exec "$container" python3 /work/input/fp8_qkv_paired_runner.py --output /work/artifacts/exact-c32 --arm fp8_qkv_candidate >"$artifacts/runner.stdout" 2>"$artifacts/runner.stderr" || fail endpoint_negative runner_failed
python3 - "$artifacts/exact-c32/TERMINAL.json" "$artifacts/modules.jsonl" "$artifacts/consumers.jsonl" "$artifacts/qkv.jsonl" <<'PY' || fail path_unproven consumer_audit_failed
import json,sys
t=json.load(open(sys.argv[1])); modules=[json.loads(x) for x in open(sys.argv[2]) if x.strip()]; consumers=[json.loads(x) for x in open(sys.argv[3]) if x.strip()]; qkv=[json.loads(x) for x in open(sys.argv[4]) if x.strip()]
assert t['pass'] and t['complete_requests']==32 and len(t['rows'])==32
assert t['cache']['cached_prompt_tokens_delta']==17120 and t['cache']['uncached_prompt_tokens_delta']==117728
assert len(modules)==240 and consumers and qkv
assert all(x.get('candidate_symbol')=='_qkv_norm_rope_inplace_kernel' and x.get('dtype')=='torch.bfloat16' for x in qkv)
PY
atomic "$artifacts/WORKER_TERMINAL.json" completed scientific_endpoint_completed
