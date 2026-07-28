#!/usr/bin/env bash
set -euo pipefail
root=/home/glmrunner/gemma4-h200-ngram-speculative-endpoint
input="$root/input"
artifacts="$root/artifacts"
shared_checkpoint=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"
terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':time.time()},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
trap 'terminal integration_failure "$BASH_COMMAND"' ERR
sudo docker rm -f gemma-ngram >/dev/null 2>&1 || true
sudo docker run -d --name gemma-ngram --gpus all --ipc=host --network host \
  -v "$root:/work" -v "$shared_checkpoint:/work/checkpoint:ro" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e FP8_MODULE_AUDIT=/work/artifacts/fp8-modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/artifacts/fp8-consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/artifacts/fp8-runtime.json \
  -e FP8_STACK_MODULE_AUDIT=/work/artifacts/fp8-stack-modules.jsonl \
  -e FP8_STACK_CONSUMER_AUDIT=/work/artifacts/fp8-stack-consumers.jsonl \
  "$image" python3 /work/input/endpoint_entrypoint.py \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint \
  --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 \
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 \
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 \
  --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 --prefill-attention-backend triton \
  --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 --speculative-algorithm NGRAM \
  >"$artifacts/container-id"
for _ in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/models.json" 2>"$artifacts/models.stderr" && break; sleep 2; done
test -s "$artifacts/models.json"
sudo docker logs gemma-ngram >"$artifacts/server-start.log" 2>&1 || true
sudo docker exec gemma-ngram ps -ef >"$artifacts/processes.txt"
sudo docker exec gemma-ngram python3 /work/input/exact_runner.py --output /work/artifacts/diagnostic --arm native_ngram_diagnostic --concurrency 32 >"$artifacts/runner.stdout" 2>"$artifacts/runner.stderr"
curl -fsS http://127.0.0.1:30000/metrics >"$artifacts/metrics-final.prom" || true
sudo docker logs gemma-ngram >"$artifacts/server-final.log" 2>&1 || true
python3 - "$artifacts" <<'PY'
import json,pathlib,os,sys
p=pathlib.Path(sys.argv[1]); t=json.loads((p/'diagnostic/TERMINAL.json').read_text())
metrics=(p/'metrics-final.prom').read_text(errors='replace') if (p/'metrics-final.prom').exists() else ''
rows=[x for x in metrics.splitlines() if 'spec' in x.lower() or 'forward' in x.lower()]
v={'schema_version':1,'pass':bool(t.get('pass')),'complete_requests':t.get('complete_requests'),'service_seconds_per_request':t.get('service_seconds_per_request'),'cache':t.get('cache'),'speculative_metric_lines':rows,'assistant_model_absent':True,'contract':'NGRAM default arguments only'}
q=p/'DIAGNOSTIC.json.part'; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p/'DIAGNOSTIC.json')
PY
terminal diagnostic_complete native_ngram_exact_request_diagnostic_persisted
