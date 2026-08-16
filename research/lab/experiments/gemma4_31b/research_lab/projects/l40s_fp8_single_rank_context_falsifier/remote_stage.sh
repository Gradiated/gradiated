#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"
base="${ARTIFACT_BASENAME:?}"
out="/workspace/l40s-single-rank-${stage}"
public=/workspace/public-mla-microbench
telemetry=
rm -rf "$out" "$public"
mkdir -p "$out" "$public"
phase() { printf '{"timestamp":"%s","stage":"%s","phase":"%s"}\n' "$(date -u +%FT%TZ)" "$stage" "$1" >> "$out/phases.jsonl"; }
finish() {
  rc=$?
  set +e
  phase teardown
  if [ -n "$telemetry" ]; then kill -TERM "$telemetry" 2>/dev/null; wait "$telemetry" 2>/dev/null; fi
  nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1
  python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); rows=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'manifest.json':
        rows.append({'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" "$(basename "$out")"
  sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"
  exit "$rc"
}
trap finish EXIT
phase immutable-input-check
python3 - /input/STAGED_MANIFEST.json /input > "$out/input-verification.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); observed={}
for name, expected in manifest['remote_files'].items():
    path=root/name
    actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    observed[name]={'expected':expected,'actual':actual,'pass':actual==expected}
out={'schema_version':1,'observed':observed,'pass':bool(observed) and all(x['pass'] for x in observed.values())}
print(json.dumps(out,sort_keys=True))
raise SystemExit(0 if out['pass'] else 1)
PY
phase bootstrap
nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
python3 - <<'PY' > "$out/runtime.json"
import hashlib,json,os,torch,vllm
from pathlib import Path
p=Path(os.environ['MICROBENCH_PATH'])
print(json.dumps({'vllm':vllm.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability(),'runtime_image':os.environ['RUNTIME_IMAGE_IDENTITY'],'benchmark':p.name,'benchmark_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'spec_sha256':os.environ['EXPERIMENT_SPEC_SHA256']},sort_keys=True))
PY
( while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done ) > "$out/telemetry.csv" 2> "$out/telemetry.stderr.log" & telemetry=$!
phase sweep
set +e
python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 20260717 > "$out/microbench.stdout.log" 2> "$out/microbench.stderr.log"
rc=$?
set -e
kill -TERM "$telemetry" 2>/dev/null || true
wait "$telemetry" 2>/dev/null || true
telemetry=
python3 - "$out/result.json" "$out/telemetry.csv" "$out/runtime.json" "$out/stage-terminal.json" "$stage" "$rc" <<'PY'
import csv,json,math,sys
result_path,telemetry_path,runtime_path,terminal_path,stage,rc=sys.argv[1:]
try: value=json.load(open(result_path))
except Exception as error: value={'error':{'type':type(error).__name__,'message':str(error)}}
runtime=json.load(open(runtime_path))
rows=[]
try:
    with open(telemetry_path) as handle:
        for row in csv.reader(handle):
            if len(row)>=9: rows.append([x.strip() for x in row])
except Exception: rows=[]
def number(text):
    try: return float(text)
    except Exception: return math.nan
telemetry={
  'row_count':len(rows),
  'gpu_names':sorted({r[2] for r in rows}),
  'memory_total_mib':sorted({number(r[6]) for r in rows if math.isfinite(number(r[6]))}),
  'power_samples_w':[number(r[7]) for r in rows if math.isfinite(number(r[7]))],
  'gpu_util_samples_percent':[number(r[3]) for r in rows if math.isfinite(number(r[3]))],
}
telemetry['pass']=bool(telemetry['row_count']>=1 and telemetry['gpu_names']==['NVIDIA L40S'] and telemetry['memory_total_mib'] and min(telemetry['memory_total_mib'])>=45000 and telemetry['power_samples_w'] and telemetry['gpu_util_samples_percent'])
group=value.get('group_identity',{})
sentinel=value.get('sentinel') if stage=='primary' else {'pass':True}
terminal={
 'schema_version':1,'stage':stage,
 'pass':bool(rc=='0' and value.get('pass') is True and value.get('all_actual_consumers_pass') is True and group.get('pass') is True and value.get('group_teardown',{}).get('pass') is True and telemetry['pass'] and isinstance(sentinel,dict) and sentinel.get('pass') is True),
 'all_actual_consumers_pass':value.get('all_actual_consumers_pass',False),
 'economic_both_envelopes_falsified':value.get('economic_both_envelopes_falsified',False),
 'useful_gpu_seconds':value.get('useful_gpu_seconds',0.0),
 'group_identity':group,'group_teardown':value.get('group_teardown'),
 'telemetry':telemetry,'runtime':runtime,
 'sentinel':sentinel,
 'W4_RESIDUAL_TRIGGER':value.get('W4_RESIDUAL_TRIGGER'),
 'FP8_CONTEXT_ADMISSION':value.get('FP8_CONTEXT_ADMISSION'),
 'W4_DECISION':value.get('W4_DECISION'),
 'result':value,
}
with open(terminal_path,'w') as handle: json.dump(terminal,handle,indent=2,sort_keys=True); handle.write('\n')
raise SystemExit(0 if terminal['pass'] else 1)
PY
rc=$?
exit "$rc"
