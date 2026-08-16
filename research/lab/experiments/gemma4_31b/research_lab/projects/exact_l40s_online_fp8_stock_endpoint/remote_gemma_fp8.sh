#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/gemma4-online-fp8
PUBLIC=/workspace/public-gemma4-online-fp8
MODEL=/workspace/model
SERVER=
TELEMETRY=
RELOAD_COUNT=0
PREFIX_TRIGGER=false
PREFIX_START_READY=false
PREFIX_FALSE_CLEANUP=false
PREFIX_EXECUTED=false
PREFIX_DISPOSITION=not_evaluated
PREFIX_RC=0
BASELINE_RC=1

rm -rf "$OUT" "$PUBLIC"
mkdir -p "$OUT" "$PUBLIC"

phase() {
  printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"
}

package_artifact() {
  python3 - <<'PY'
import hashlib,json
from pathlib import Path
root=Path('/workspace/gemma4-online-fp8')
rows=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'manifest.json':
        rows.append({'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
temporary=root/'manifest.json.part'
temporary.write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
temporary.replace(root/'manifest.json')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$PUBLIC/gemma4-online-fp8.tar.gz.tmp" gemma4-online-fp8
  mv "$PUBLIC/gemma4-online-fp8.tar.gz.tmp" "$PUBLIC/gemma4-online-fp8.tar.gz"
  sha256sum "$PUBLIC/gemma4-online-fp8.tar.gz" > "$PUBLIC/gemma4-online-fp8.tar.gz.sha256.tmp"
  mv "$PUBLIC/gemma4-online-fp8.tar.gz.sha256.tmp" "$PUBLIC/gemma4-online-fp8.tar.gz.sha256"
}

finish() {
  rc=$?
  set +e
  phase teardown begin
  if [ -n "$SERVER" ]; then kill -TERM "$SERVER" 2>/dev/null; fi
  if [ -n "$TELEMETRY" ]; then kill -TERM "$TELEMETRY" 2>/dev/null; fi
  if [ -n "$SERVER" ]; then wait "$SERVER" 2>/dev/null; fi
  if [ -n "$TELEMETRY" ]; then wait "$TELEMETRY" 2>/dev/null; fi
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  phase teardown complete
  package_artifact
  exit "$rc"
}
trap finish EXIT

phase allocation_bootstrap begin
python3 - <<'PY' > "$OUT/runtime.json"
import json,torch,transformers,vllm
print(json.dumps({'vllm':vllm.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability()},sort_keys=True))
PY
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY=$!
phase allocation_bootstrap complete

phase model_identity begin
test "$(sha256sum "$MODEL/model.safetensors.index.json" | awk '{print $1}')" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2
test "$(sha256sum /input/TRACE_PACKET.json | awk '{print $1}')" = ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68
(cd "$MODEL" && sha256sum -c model-files.sha256) > "$OUT/model-verification.log"
cp "$MODEL/model-files.sha256" "$OUT/model-files.sha256"
phase model_identity complete

start_server() {
  local cache_mode="$1"
  local ready_deadline="$2"
  local cache_arg=--enable-prefix-caching
  if [ "$cache_mode" = off ]; then cache_arg=--no-enable-prefix-caching; fi
  CMD=(vllm serve "$MODEL" --served-model-name google/gemma-4-31B-it --host 127.0.0.1 --port 30000 --dtype bfloat16 --quantization fp8 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --gpu-memory-utilization 0.94 --generation-config vllm --enable-metrics "$cache_arg" --seed 20260717)
  printf '%q ' "${CMD[@]}" > "$OUT/server-command-$cache_mode.txt"
  "${CMD[@]}" > "$OUT/server-$cache_mode.stdout.log" 2> "$OUT/server-$cache_mode.stderr.log" &
  SERVER=$!
  while [ "$(date +%s)" -lt "$ready_deadline" ] && [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    if ! kill -0 "$SERVER" 2>/dev/null; then
      wait "$SERVER" || true
      SERVER=
      return 1
    fi
    if curl -fsS http://127.0.0.1:30000/health >/dev/null; then return 0; fi
    sleep 2
  done
  return 1
}

phase model_load begin
start_server on "$(( $(date +%s) + 1800 ))"
nvidia-smi -q > "$OUT/nvidia-smi-loaded.txt" 2>&1
phase model_load complete

phase semantic_and_baseline begin
set +e
python3 /input/gemma_fp8_runner.py --trace /input/TRACE_PACKET.json --output "$OUT/baseline" --mode baseline > "$OUT/baseline.stdout.log" 2> "$OUT/baseline.stderr.log"
BASELINE_RC=$?
set -e
phase semantic_and_baseline complete

if [ -f "$OUT/baseline/runner-result.json" ]; then
  PREFIX_TRIGGER="$(python3 -c 'import json; print(str(bool(json.load(open("/workspace/gemma4-online-fp8/baseline/runner-result.json")).get("prefix_trigger",{}).get("trigger"))).lower())')"
fi
if [ "$PREFIX_TRIGGER" = true ] && [ -f /input/gemma_fp8_runner.py ] && [ -f /input/TRACE_PACKET.json ] && [ "$((CAMPAIGN_DEADLINE_EPOCH-$(date +%s)))" -ge 900 ]; then
  PREFIX_START_READY=true
fi

if [ "$PREFIX_TRIGGER" = true ] && [ "$PREFIX_START_READY" = true ]; then
  PREFIX_DISPOSITION=executed
  PREFIX_EXECUTED=true
  phase prefix_off_reload begin
  kill -TERM "$SERVER"
  wait "$SERVER" || true
  SERVER=
  RELOAD_COUNT=$((RELOAD_COUNT+1))
  set +e
  start_server off "$(( $(date +%s) + 600 ))"
  PREFIX_SERVER_RC=$?
  set -e
  if [ "$PREFIX_SERVER_RC" -eq 0 ]; then
    set +e
    python3 /input/gemma_fp8_runner.py --trace /input/TRACE_PACKET.json --output "$OUT/prefix-off" --mode prefix-off > "$OUT/prefix-off.stdout.log" 2> "$OUT/prefix-off.stderr.log"
    PREFIX_RC=$?
    set -e
  else
    PREFIX_RC=$PREFIX_SERVER_RC
  fi
  phase prefix_off_reload complete
elif [ "$PREFIX_TRIGGER" = true ]; then
  PREFIX_DISPOSITION=trigger_true_not_start_ready
  PREFIX_RC=0
else
  PREFIX_DISPOSITION=trigger_false_cleanup
  PREFIX_FALSE_CLEANUP=true
fi

export BASELINE_RC PREFIX_RC RELOAD_COUNT PREFIX_TRIGGER PREFIX_START_READY PREFIX_EXECUTED PREFIX_DISPOSITION PREFIX_FALSE_CLEANUP
python3 - <<'PY'
import json,os,time
from pathlib import Path

root=Path('/workspace/gemma4-online-fp8')
baseline_path=root/'baseline/runner-result.json'
baseline=json.loads(baseline_path.read_text()) if baseline_path.exists() else {'pass':False,'error':{'type':'MissingBaselineTerminal'}}
prefix_path=root/'prefix-off/runner-result.json'
prefix=json.loads(prefix_path.read_text()) if prefix_path.exists() else None
baseline_rc=int(os.environ['BASELINE_RC'])
prefix_rc=int(os.environ['PREFIX_RC'])
prefix_executed=os.environ['PREFIX_EXECUTED']=='true'
terminal_pass=baseline_rc == 0 and bool(baseline.get('pass')) and (not prefix_executed or (prefix_rc == 0 and bool(prefix and prefix.get('pass'))))
complete_requests=int(baseline.get('complete_request_count',0))+(int(prefix.get('complete_request_count',0)) if prefix else 0)
failures=int(baseline.get('failure_count',0))+(int(prefix.get('failure_count',0)) if prefix else 0)
if baseline_rc != 0: failures+=1
if prefix_executed and prefix_rc != 0: failures+=1
provider_seconds=max(0.0,time.time()-float(os.environ['CAMPAIGN_PROVIDER_STARTED_EPOCH']))
gpu_rate=float(os.environ['PROVIDER_GPU_RATE_USD_PER_HOUR'])
disk_rate=float(os.environ['PROVIDER_DISK_RATE_USD_PER_HOUR'])
value={
    'schema_version':2,
    'complete':baseline_path.exists() and (not prefix_executed or prefix_path.exists()),
    'pass':terminal_pass,
    'semantic':baseline.get('semantic'),
    'profiles':baseline.get('groups'),
    'single_10k':baseline.get('single_10k'),
    'prefix_trigger':baseline.get('prefix_trigger'),
    'prefix_executed':prefix_executed,
    'prefix_disposition':os.environ['PREFIX_DISPOSITION'],
    'prefix_start_ready':os.environ['PREFIX_START_READY']=='true',
    'prefix_false_cleanup':os.environ['PREFIX_FALSE_CLEANUP']=='true',
    'prefix_off':prefix,
    'complete_request_count':complete_requests,
    'failure_count':failures,
    'reload_count':int(os.environ['RELOAD_COUNT']),
    'economics':baseline.get('economics'),
    'useful_gpu_seconds':float(baseline.get('useful_gpu_seconds',0) or 0)+float(prefix.get('useful_gpu_seconds',0) or 0 if prefix else 0),
    'provider_seconds':provider_seconds,
    'provider':{
        'venue':'Nebius','platform':'gpu-l40s-a','preset':'1gpu-16vcpu-64gb','disk_gib':200,
        'gpu_rate_usd_per_hour':gpu_rate,'disk_rate_usd_per_hour':disk_rate,
        'compute_cost_usd_derived':provider_seconds/3600*gpu_rate,
        'disk_cost_usd_derived':provider_seconds/3600*disk_rate,
    },
    'online_quantization':'fp8','dtype':'bfloat16','model':'google/gemma-4-31B-it',
    'revision':'b9ea41a2887d8607f594846523f94c6cc75ac8a4',
    'runtime_image':os.environ['GEMMA_RUNTIME_IMAGE'],
    'experiment_spec_sha256':os.environ['EXPERIMENT_SPEC_SHA256'],
    'economics_spec_sha256':os.environ['ECONOMICS_SPEC_SHA256'],
}
temporary=root/'allocation-result.json.part'
temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
temporary.replace(root/'allocation-result.json')
PY

if [ "$BASELINE_RC" -ne 0 ]; then exit "$BASELINE_RC"; fi
if [ "$PREFIX_RC" -ne 0 ]; then exit "$PREFIX_RC"; fi
exit 0
