#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"; base="${ARTIFACT_BASENAME:?}"; out=/workspace/gemma-w4-fp8; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
phase() { printf '{"timestamp":"%s","stage":"%s","phase":"%s"}\n' "$(date -u +%FT%TZ)" "$stage" "$1" >> "$out/phases.jsonl"; }
finish() { rc=$?; set +e; phase teardown; [ -n "$telemetry" ] && kill -TERM "$telemetry" 2>/dev/null; [ -n "$telemetry" ] && wait "$telemetry" 2>/dev/null; nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1; python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); rows=[]
for p in sorted(r.rglob('*')):
 if p.is_file() and p.name!='manifest.json': rows.append({'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" gemma-w4-fp8; sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
phase bootstrap; nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
python3 - <<'PY' > "$out/runtime.json"
import hashlib,json,torch,vllm
from pathlib import Path
p=Path('/input')/Path(__import__('os').environ['MICROBENCH_PATH']).name
print(json.dumps({'vllm':vllm.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability(),'benchmark_sha256':hashlib.sha256(p.read_bytes()).hexdigest()},sort_keys=True))
PY
( while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits; sleep 1; done ) > "$out/telemetry.csv" 2> "$out/telemetry.stderr.log" & telemetry=$!
phase sweep; set +e; python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 1234 > "$out/microbench.stdout.log" 2> "$out/microbench.stderr.log"; rc=$?; set -e
python3 - "$out/result.json" "$out/stage-terminal.json" "$stage" "$rc" <<'PY'
import json,sys
r,t,stage,rc=sys.argv[1:]
try: value=json.load(open(r))
except Exception as e: value={'error':{'type':type(e).__name__,'message':str(e)}}
terminal={'stage':stage,'pass':rc=='0' and value.get('pass') is True,'all_actual_consumers_pass':value.get('all_actual_consumers_pass',False),'economic_both_envelopes_falsified':value.get('economic_both_envelopes_falsified',False),'useful_gpu_seconds':value.get('useful_gpu_seconds',0.0),'result':value}
json.dump(terminal,open(t,'w'),indent=2,sort_keys=True); open(t,'a').write('\n')
PY
exit "$rc"
