#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
stage=${STAGE:?}; case "$stage" in sentinel|primary) ;; *) exit 64;; esac
out="/workspace/h100-head-$stage"; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish(){ rc=$?; set +e; [ -n "$telemetry" ]&&kill -TERM "$telemetry" 2>/dev/null; [ -n "$telemetry" ]&&wait "$telemetry" 2>/dev/null; nvidia-smi -q >"$out/nvidia-smi-final.txt" 2>&1; python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); rows=[{'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(r.rglob('*')) if p.is_file() and p.name!='manifest.json']; (r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$ARTIFACT_BASENAME.tar.gz" "h100-head-$stage"; sha256sum "$public/$ARTIFACT_BASENAME.tar.gz">"$public/$ARTIFACT_BASENAME.tar.gz.sha256"; exit "$rc"; }; trap finish EXIT
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do date -u +%s.%N | tr -d '\n'; printf ','; nvidia-smi --query-gpu=uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits; sleep .15; done)>"$out/telemetry.csv" 2>"$out/telemetry.stderr" & telemetry=$!
start=$(date -u +%s.%N); set +e; PYTHONPATH=/input python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 20260717 >"$out/stdout.log" 2>"$out/stderr.log"; rc=$?; set -e; end=$(date -u +%s.%N)
kill -TERM "$telemetry" 2>/dev/null||true; wait "$telemetry" 2>/dev/null||true; telemetry=
python3 - "$out/result.json" "$out/telemetry.csv" "$out/stage-terminal.json" "$rc" "$stage" "$start" "$end" <<'PY'
import csv,datetime as dt,json,sys
r=json.load(open(sys.argv[1])); rows=list(csv.reader(open(sys.argv[2]))); stamps=[float(x[0]) for x in rows if len(x)>=10]; scoped=[x for x in stamps if float(sys.argv[6])<=x<=float(sys.argv[7])]; gaps=[b-a for a,b in zip(stamps,stamps[1:])]; telemetry={'rows':len(rows),'scoped_rows':len(scoped),'max_observed_gap_seconds':max(gaps) if gaps else None,'cadence_lte_200ms':bool(gaps) and max(gaps)<=.2,'gpu_names':sorted({x[2].strip() for x in rows if len(x)>=10})}; expected=[8] if sys.argv[5]=='sentinel' else [8,16,32]; valid=r.get('pass') is True and [x.get('m') for x in r.get('rows',[])]==expected and all(x.get('pass') is True for x in r.get('rows',[])); t={'schema_version':1,'stage':'primary','type':'retrieved_h100_actual_parallel_lm_head_'+sys.argv[5],'result':r,'telemetry':telemetry,'pass':sys.argv[4]=='0' and valid and telemetry['gpu_names']==['NVIDIA H100 80GB HBM3'] and telemetry['scoped_rows']>=1 and telemetry['cadence_lte_200ms']}; json.dump(t,open(sys.argv[3],'w'),indent=2,sort_keys=True);open(sys.argv[3],'a').write('\n');raise SystemExit(0 if t['pass'] else 1)
PY
