#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
out=/workspace/h100-head-m16-m32-conditional; public=/workspace/public-mla-microbench; telemetry=
sentinel=/workspace/h100-head-sentinel/stage-terminal.json
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish(){ rc=$?; set +e; [ -n "$telemetry" ]&&kill -TERM "$telemetry" 2>/dev/null; [ -n "$telemetry" ]&&wait "$telemetry" 2>/dev/null; nvidia-smi -q >"$out/nvidia-smi-final.txt" 2>&1; PYTHONPATH=/input python3 - "$out" <<'PY'
import json,sys
from pathlib import Path
from h100_stage2_contract import manifest
r=Path(sys.argv[1]); (r/'manifest.json').write_text(json.dumps(manifest(r),indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$ARTIFACT_BASENAME.tar.gz" h100-head-m16-m32-conditional; sha256sum "$public/$ARTIFACT_BASENAME.tar.gz">"$public/$ARTIFACT_BASENAME.tar.gz.sha256"; exit "$rc"; }; trap finish EXIT
[ -f "$sentinel" ] || { printf '%s\n' '{"pass":false,"stage":"primary","type":"missing_remote_sentinel"}' >"$out/stage-terminal.json"; exit 71; }
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ];do date -u +%s.%N|tr -d '\n';printf ',';nvidia-smi --query-gpu=uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits;sleep .15;done)>"$out/telemetry.csv" 2>"$out/telemetry.stderr" & telemetry=$!
head_start=$(date -u +%s.%N); set +e; PYTHONPATH=/input python3 /input/h100_parallel_lm_head_bench.py --stage remainder --output "$out/head-result.json" --seed 20260717 >"$out/head.stdout.log" 2>"$out/head.stderr.log"; head_rc=$?; set -e; head_end=$(date -u +%s.%N)
python3 - "$out/head-result.json" "$out/telemetry.csv" "$out/head-terminal.json" "$head_rc" "$head_start" "$head_end" <<'PY'
import csv,json,os,sys
from pathlib import Path
r=json.load(open(sys.argv[1]));rows=list(csv.reader(open(sys.argv[2])));stamps=[float(x[0]) for x in rows if len(x)>=10];gaps=[b-a for a,b in zip(stamps,stamps[1:])];scoped=[x for x in stamps if float(sys.argv[5])<=x<=float(sys.argv[6])];tele={'rows':len(rows),'scoped_rows':len(scoped),'max_observed_gap_seconds':max(gaps)if gaps else None,'cadence_lte_200ms':bool(gaps)and max(gaps)<=.2,'gpu_names':sorted({x[2].strip()for x in rows if len(x)>=10})};valid=r.get('pass')is True and [x.get('m')for x in r.get('rows',[])]==[16,32]and all(x.get('pass')is True for x in r.get('rows',[]));t={'schema_version':1,'stage':'conditional','type':'persisted_h100_actual_parallel_lm_head_m16_m32','result':r,'telemetry':tele,'pass':sys.argv[4]=='0'and valid and tele['gpu_names']==['NVIDIA H100 80GB HBM3']and tele['scoped_rows']>=1 and tele['cadence_lte_200ms']};p=Path(sys.argv[3]);q=p.with_suffix('.json.tmp');q.write_text(json.dumps(t,indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
trigger=$(PYTHONPATH=/input python3 - "$sentinel" "$out/head-terminal.json" /input/HISTORICAL_SETUP.json "$CAMPAIGN_DEADLINE_EPOCH" <<'PY'
import json,sys,time
from h100_stage2_contract import linear_trigger
load=lambda p:json.load(open(p));print('true' if linear_trigger(load(sys.argv[1]),load(sys.argv[2]),load(sys.argv[3]),float(sys.argv[4]),time.time()) else 'false')
PY
)
linear_rc=0
if [ "$trigger" = true ]; then
  set +e; PYTHONPATH=/input python3 /input/h100_bf16_linear_bench.py --stage sweep --output "$out/linear-result.json" --seed 20260717 >"$out/linear.stdout.log" 2>"$out/linear.stderr.log"; linear_rc=$?; set -e
fi
kill -TERM "$telemetry" 2>/dev/null||true; wait "$telemetry" 2>/dev/null||true; telemetry=
python3 - "$out/telemetry.csv" "$out/telemetry-summary.json" <<'PY'
import csv,json,sys
rows=list(csv.reader(open(sys.argv[1])));stamps=[float(x[0])for x in rows if len(x)>=10];gaps=[b-a for a,b in zip(stamps,stamps[1:])];v={'rows':len(rows),'scoped_rows':len(rows),'max_observed_gap_seconds':max(gaps)if gaps else None,'cadence_lte_200ms':bool(gaps)and max(gaps)<=.2,'gpu_names':sorted({x[2].strip()for x in rows if len(x)>=10})};json.dump(v,open(sys.argv[2],'w'),indent=2,sort_keys=True);open(sys.argv[2],'a').write('\n')
PY
linear_args=(); [ -f "$out/linear-result.json" ] && linear_args=(--linear-result "$out/linear-result.json")
set +e; PYTHONPATH=/input python3 /input/h100_stage2_contract.py --sentinel "$sentinel" --remainder "$out/head-terminal.json" --history /input/HISTORICAL_SETUP.json "${linear_args[@]}" --telemetry "$out/telemetry-summary.json" --deadline-epoch "$CAMPAIGN_DEADLINE_EPOCH" --now-epoch "$(date +%s)" --output "$out/stage-terminal.json"; final_rc=$?; set -e
if [ "$linear_rc" -ne 0 ] || [ "$final_rc" -ne 0 ]; then exit 1; fi
