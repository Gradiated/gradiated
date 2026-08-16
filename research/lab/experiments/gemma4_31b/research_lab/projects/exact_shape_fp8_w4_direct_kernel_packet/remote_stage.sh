#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"
base="${ARTIFACT_BASENAME:?}"
out="/workspace/direct-fp8-${stage}"
public=/workspace/public-mla-microbench
telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish() {
  rc=$?; set +e
  if [ -n "$telemetry" ]; then kill -TERM "$telemetry" 2>/dev/null; wait "$telemetry" 2>/dev/null; fi
  nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1
  python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); rows=[]
for p in sorted(r.rglob('*')):
    if p.is_file() and p.name != 'manifest.json': rows.append({'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" "$(basename "$out")"
  sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"
  exit "$rc"
}
trap finish EXIT
python3 - /input/STAGED_MANIFEST.json /input > "$out/input-verification.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
m=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); observed={}
for name,expected in m['remote_files'].items():
    p=root/name; actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    observed[name]={'expected':expected,'actual':actual,'pass':actual==expected}
value={'schema_version':1,'observed':observed,'pass':bool(observed) and all(x['pass'] for x in observed.values())}
print(json.dumps(value,sort_keys=True)); raise SystemExit(0 if value['pass'] else 1)
PY
nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
( while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits; sleep 1; done ) > "$out/telemetry.csv" 2> "$out/telemetry.stderr.log" & telemetry=$!
set +e
python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 20260717 > "$out/stdout.log" 2> "$out/stderr.log"
rc=$?
set -e
kill -TERM "$telemetry" 2>/dev/null || true; wait "$telemetry" 2>/dev/null || true; telemetry=
python3 - "$out/result.json" "$out/telemetry.csv" "$out/stage-terminal.json" "$stage" "$rc" <<'PY'
import csv,json,math,sys
rp,tp,op,stage,rc=sys.argv[1:]
try: result=json.load(open(rp))
except Exception as e: result={'error':{'type':type(e).__name__,'message':str(e)}}
rows=list(csv.reader(open(tp))) if __import__('pathlib').Path(tp).is_file() else []
def num(x):
    try:return float(x.strip())
    except:return math.nan
valid=[r for r in rows if len(r)>=9]
telemetry={'row_count':len(valid),'gpu_names':sorted({r[2].strip() for r in valid}),'memory_used_mib':[num(r[5]) for r in valid if math.isfinite(num(r[5]))],'memory_total_mib':[num(r[6]) for r in valid if math.isfinite(num(r[6]))],'power_w':[num(r[7]) for r in valid if math.isfinite(num(r[7]))],'gpu_util_percent':[num(r[3]) for r in valid if math.isfinite(num(r[3]))]}
telemetry['pass']=bool(telemetry['row_count']>=2 and telemetry['gpu_names']==['NVIDIA L40S'] and telemetry['memory_used_mib'] and telemetry['memory_total_mib'] and min(telemetry['memory_total_mib'])>=45000 and max(telemetry['gpu_util_percent'])>0 and max(telemetry['power_w'])>50)
terminal={'schema_version':1,'stage':stage,'pass':bool(rc=='0' and result.get('pass') is True and telemetry['pass']),'telemetry':telemetry,'result':result}
json.dump(terminal,open(op,'w'),indent=2,sort_keys=True); open(op,'a').write('\n')
raise SystemExit(0 if terminal['pass'] else 1)
PY
