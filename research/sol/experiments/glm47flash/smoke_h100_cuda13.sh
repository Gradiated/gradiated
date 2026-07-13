#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/glm-smoke
PUBLIC=/workspace/public
MODEL=/workspace/model
SERVER_PID=
TELEMETRY_PID=
HTTP_PID=
mkdir -p "$OUT" "$PUBLIC"

phase() {
  python3 - "$1" "$2" <<'PY' >> "$OUT/phases.jsonl"
import datetime,json,sys
print(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'phase':sys.argv[1],'state':sys.argv[2],'missing_counters':[]},separators=(',',':')))
PY
}

package() {
  python3 - <<'PY'
import hashlib,json,pathlib
p=pathlib.Path('/workspace/glm-smoke')
rows=[]
for f in sorted(p.rglob('*')):
 if f.is_file(): rows.append({'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
(p/'manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
events=[json.loads(line) for line in (p/'phases.jsonl').read_text().splitlines()]
aliases={'allocation': 'allocation', 'startup': 'startup', 'warmup': 'warmup', 'benchmark': 'benchmark', 'teardown': 'teardown'}
phases=[]
for name in aliases:
 starts=[e['timestamp'] for e in events if e['phase']==name and e['state']=='begin']
 finishes=[e['timestamp'] for e in events if e['phase']==name and e['state']=='complete']
 phases.append({'name':name,'started_at':starts[0] if starts else None,'finished_at':finishes[-1] if finishes else None,'missing_counters':[]})
identity={'run_id':'glm47flash-native-smoke-20260713','model':'zai-org/GLM-4.7-Flash','model_revision':'75fce70','workload_id':'deterministic_completion_smoke_v1','workload_hash':hashlib.sha256((p/'request.json').read_bytes()).hexdigest() if (p/'request.json').exists() else None,'slo_id':'smoke_completion_determinism_v1'}
(p/'contract.json').write_text(json.dumps({'schema_version':1,'identity':identity,'provenance':{'result_kind':'measured','published_inputs_used':False},'phases':phases,'server':{'healthy':(p/'server.stdout.log').exists() and (p/'determinism.json').exists()},'teardown':{'complete':any(e['phase']=='teardown' and e['state']=='complete' for e in events)},'workload':{'slo_identity':'smoke_completion_determinism_v1'},'benchmark_result':'determinism.json','cost':{'hourly_rate_usd':None}},indent=2)+'\n')
(p/'manifest.json').write_text(json.dumps([{'name':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(p.rglob('*')) if f.is_file() and f.name != 'manifest.json'],indent=2)+'\n')
PY
  tar -C /workspace -czf "$PUBLIC/glm-smoke.tar.gz.tmp" glm-smoke
  mv "$PUBLIC/glm-smoke.tar.gz.tmp" "$PUBLIC/glm-smoke.tar.gz"
  sha256sum "$PUBLIC/glm-smoke.tar.gz" > "$PUBLIC/glm-smoke.tar.gz.sha256"
}

finish() {
  rc=$?
  set +e
  phase teardown begin
  [ -n "$SERVER_PID" ] && kill -TERM "$SERVER_PID" 2>/dev/null
  [ -n "$TELEMETRY_PID" ] && kill -TERM "$TELEMETRY_PID" 2>/dev/null
  [ -n "$SERVER_PID" ] && wait "$SERVER_PID" 2>/dev/null
  [ -n "$TELEMETRY_PID" ] && wait "$TELEMETRY_PID" 2>/dev/null
  phase teardown complete
  phase allocation complete
  package
  if [ "$rc" -eq 0 ]; then printf 'READY\n' > "$PUBLIC/STATUS"; else printf 'FAILED\n' > "$PUBLIC/STATUS"; fi
  printf '%s\n' "$rc" > "$PUBLIC/EXIT_CODE"
  wait "$HTTP_PID"
}
trap finish EXIT

printf 'BOOTSTRAP\n' > "$PUBLIC/STATUS"
python3 -m http.server 8000 --bind 0.0.0.0 --directory "$PUBLIC" > "$OUT/artifact-server.stdout.log" 2> "$OUT/artifact-server.stderr.log" &
HTTP_PID=$!
phase allocation begin
phase startup begin
date -u +%FT%TZ > "$OUT/started_at.txt"
uname -a > "$OUT/uname.txt"
printf '%s\n' "$(uname -m)" > "$OUT/architecture.txt"
[ "$(uname -m)" = x86_64 ]
nvidia-smi -q > "$OUT/nvidia-smi-q.txt" 2>&1 || true
nvidia-smi --query-gpu=timestamp,uuid,name,driver_version,pci.bus_id,memory.total,power.limit --format=csv,noheader > "$OUT/gpu-identity.csv" 2>&1 || true
phase startup complete

phase telemetry begin
(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.sm,clocks.mem --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY_PID=$!
if command -v dcgmi >/dev/null; then
  timeout 10 dcgmi discovery -l > "$OUT/dcgm-discovery.txt" 2>&1 || true
  timeout 10 dcgmi dmon -c 1 > "$OUT/dcgm-one-shot.txt" 2>&1 || true
else
  printf 'dcgmi unavailable in image\n' > "$OUT/dcgm-unavailable.txt"
fi
phase telemetry active

phase startup begin
timeout 120 python3 - <<'PY' > "$OUT/native-import.stdout.log" 2> "$OUT/native-import.stderr.log"
import cutlass,hashlib,inspect,json,pathlib
from sglang.srt.models.glm4_moe_lite import Glm4MoeLiteForCausalLM
import sglang,torch,transformers
model_file=pathlib.Path(inspect.getfile(Glm4MoeLiteForCausalLM))
cutlass_file=getattr(cutlass,'__file__',None)
print(json.dumps({'cutlass_module':cutlass_file,'native_class':Glm4MoeLiteForCausalLM.__name__,'native_module':Glm4MoeLiteForCausalLM.__module__,'native_module_file':str(model_file),'native_module_sha256':hashlib.sha256(model_file.read_bytes()).hexdigest(),'sglang':sglang.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'transformers':transformers.__version__},indent=2))
PY
phase startup complete

phase startup begin
python3 - <<'PY' > "$OUT/model-download.stdout.log" 2> "$OUT/model-download.stderr.log"
from huggingface_hub import HfApi,snapshot_download
api=HfApi(); info=api.model_info('zai-org/GLM-4.7-Flash',revision='75fce70')
print('resolved_revision='+info.sha)
print(snapshot_download('zai-org/GLM-4.7-Flash',revision=info.sha,local_dir='/workspace/model'))
PY
phase startup complete
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"
du -sb "$MODEL" > "$OUT/model-size.txt"
python3 -m pip freeze > "$OUT/pip-freeze.txt"

phase warmup begin
SERVER_CMD=(python3 -m sglang.launch_server --model-path "$MODEL" --served-model-name glm-4.7-flash --model-impl sglang --host 127.0.0.1 --port 30000 --tp-size 1 --context-length 4096 --max-running-requests 1 --max-total-tokens 4096 --max-prefill-tokens 4096 --mem-fraction-static 0.80 --chunked-prefill-size 4096 --disable-cuda-graph --disable-radix-cache --tool-call-parser glm47 --reasoning-parser glm45 --enable-metrics --enable-request-time-stats-logging --random-seed 1234)
printf '%q ' "${SERVER_CMD[@]}" > "$OUT/server-command.txt"
printf '\n' >> "$OUT/server-command.txt"
"${SERVER_CMD[@]}" > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" &
SERVER_PID=$!
ready=0
for _ in $(seq 1 180); do
  kill -0 "$SERVER_PID" 2>/dev/null || { wait "$SERVER_PID"; exit $?; }
  if curl -fsS http://127.0.0.1:30000/health >/dev/null; then ready=1; break; fi
  sleep 2
done
[ "$ready" -eq 1 ]
phase warmup complete

phase benchmark begin
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-before.txt"
REQ='{"model":"glm-4.7-flash","messages":[{"role":"user","content":"Return exactly one JSON object with keys alpha and beta, where alpha is 17 and beta is the string smoke."}],"temperature":0,"max_tokens":32,"seed":20260713}'
printf '%s\n' "$REQ" > "$OUT/request.json"
for i in 1 2; do
  curl -fsS -H 'Content-Type: application/json' -d "$REQ" http://127.0.0.1:30000/v1/chat/completions > "$OUT/response-$i.json"
done
python3 - <<'PY' > "$OUT/determinism.json"
import hashlib,json,pathlib
p=pathlib.Path('/workspace/glm-smoke')
r=[json.loads((p/f'response-{i}.json').read_text()) for i in (1,2)]
messages=[x['choices'][0]['message'] for x in r]
normalized=[{k:m.get(k) for k in ('content','reasoning_content','tool_calls')} for m in messages]
finishes=[x['choices'][0].get('finish_reason') for x in r]
counts=[(x.get('usage') or {}).get('completion_tokens') for x in r]
if normalized[0] != normalized[1] or finishes[0] != finishes[1] or counts[0] != counts[1]: raise SystemExit('greedy completion mismatch')
serialized=json.dumps(normalized[0],sort_keys=True,separators=(',',':'))
print(json.dumps({'exact_normalized_message_identity':True,'normalized_message_sha256':hashlib.sha256(serialized.encode()).hexdigest(),'finish_reasons':finishes,'completion_token_counts':counts,'response_usage':[x.get('usage') for x in r]},indent=2))
PY
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-after.txt"
cp "$OUT/metrics-after.txt" "$OUT/server.metrics.txt"
phase benchmark complete
