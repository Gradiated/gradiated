#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"; base="${ARTIFACT_BASENAME:?}"; out=/workspace/gemma-h200-bf16-linears; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
phase() { printf '{"timestamp":"%s","stage":"%s","phase":"%s"}\n' "$(date -u +%FT%TZ)" "$stage" "$1" >> "$out/phases.jsonl"; }
finish() { rc=$?; set +e; phase teardown; [ -n "$telemetry" ] && kill -TERM "$telemetry" 2>/dev/null; [ -n "$telemetry" ] && wait "$telemetry" 2>/dev/null; nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1; python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); files=[]
for path in sorted(root.rglob('*')):
 if path.is_file() and path.name != 'manifest.json': files.append({'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(files,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" gemma-h200-bf16-linears; sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
phase bootstrap; nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
python3 - <<'PY' > "$out/runtime.json"
import hashlib,json,os,torch,vllm
from pathlib import Path
bench=Path('/input')/Path(os.environ['MICROBENCH_PATH']).name
print(json.dumps({'vllm':vllm.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'gpu_count':torch.cuda.device_count(),'capability':torch.cuda.get_device_capability(),'benchmark_sha256':hashlib.sha256(bench.read_bytes()).hexdigest()},sort_keys=True))
PY
( while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits; sleep 1; done ) > "$out/telemetry.csv" 2> "$out/telemetry.stderr.log" & telemetry=$!
phase sweep; date +%s.%N > "$out/sweep-start-epoch.txt"; set +e; python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 1234 > "$out/microbench.stdout.log" 2> "$out/microbench.stderr.log"; rc=$?; set -e; date +%s.%N > "$out/sweep-end-epoch.txt"
kill -TERM "$telemetry" 2>/dev/null || true; wait "$telemetry" 2>/dev/null || true; telemetry=
python3 - "$out/telemetry.csv" "$out/sweep-start-epoch.txt" "$out/sweep-end-epoch.txt" "$out/telemetry-validation.json" <<'PY'
import csv,datetime as dt,json,sys
telemetry,start_path,end_path,output=sys.argv[1:]
rows=list(csv.reader(open(telemetry)))
parsed=[]
for row in rows:
 if len(row) < 10: continue
 try: stamp=dt.datetime.strptime(row[0].strip(),'%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=dt.timezone.utc).timestamp()
 except ValueError: continue
 parsed.append((stamp,row))
start=float(open(start_path).read()); end=float(open(end_path).read())
checks={'nonempty':len(rows)>0,'all_rows_parseable':len(parsed)==len(rows),'h200_identity':bool(parsed) and all('H200' in row[2] for _,row in parsed),'covers_sweep_start':bool(parsed) and parsed[0][0] <= start+2.5,'covers_sweep_end':bool(parsed) and parsed[-1][0] >= end-2.5,'multiple_samples':len(parsed)>=2}
value={'schema_version':1,'rows':len(rows),'parsed_rows':len(parsed),'sweep_start_epoch':start,'sweep_end_epoch':end,'first_sample_epoch':None if not parsed else parsed[0][0],'last_sample_epoch':None if not parsed else parsed[-1][0],'checks':checks,'pass':all(checks.values())}
json.dump(value,open(output,'w'),indent=2,sort_keys=True); open(output,'a').write('\n')
PY
python3 - "$out/result.json" "$out/stage-terminal.json" "$out/telemetry-validation.json" "$stage" "$rc" <<'PY'
import json,sys
result_path,terminal_path,telemetry_path,stage,rc=sys.argv[1:]
try: result=json.load(open(result_path))
except Exception as error: result={'error':{'type':type(error).__name__,'message':str(error)}}
try: telemetry=json.load(open(telemetry_path))
except Exception as error: telemetry={'pass':False,'error':{'type':type(error).__name__,'message':str(error)}}
terminal={'stage':stage,'pass':rc=='0' and result.get('pass') is True and telemetry.get('pass') is True,'all_actual_consumers_pass':result.get('all_actual_consumers_pass',False) and telemetry.get('pass') is True,'economic_both_envelopes_falsified':result.get('economic_both_envelopes_falsified',False),'h200_head_trigger_basis':result.get('h200_head_trigger_basis',{}),'telemetry_validation':telemetry,'useful_gpu_seconds':result.get('useful_gpu_seconds',0.0),'result':result}
json.dump(terminal,open(terminal_path,'w'),indent=2,sort_keys=True); open(terminal_path,'a').write('\n')
PY
exit "$rc"
