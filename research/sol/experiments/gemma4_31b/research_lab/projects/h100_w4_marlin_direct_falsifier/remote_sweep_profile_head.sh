#!/usr/bin/env bash
set -Eeuo pipefail
out=/workspace/h100-w4-conditional;public=/workspace/public-mla-microbench;telemetry=;rm -rf "$out" "$public";mkdir -p "$out" "$public"
finish(){ rc=$?;set +e;[ -n "$telemetry" ]&&kill -TERM "$telemetry" 2>/dev/null;[ -n "$telemetry" ]&&wait "$telemetry" 2>/dev/null;python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);rows=[]
for path in sorted(root.rglob('*')):
 if path.is_file() and path.name!='manifest.json': rows.append({'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$ARTIFACT_BASENAME.tar.gz" h100-w4-conditional;sha256sum "$public/$ARTIFACT_BASENAME.tar.gz">"$public/$ARTIFACT_BASENAME.tar.gz.sha256";exit "$rc";};trap finish EXIT
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ];do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits;sleep .15;done)>"$out/telemetry.csv" 2>"$out/telemetry.stderr" & telemetry=$!
start=$(date +%s.%N);set +e;python3 "$MICROBENCH_PATH" --stage sweep --output "$out/sweep.json" --seed 20260717 >"$out/sweep.stdout" 2>"$out/sweep.stderr";sweep_rc=$?;set -e;sweep_end=$(date +%s.%N)
profile_pass=false
if [ "$sweep_rc" -eq 0 ];then
 profile_pass=true
 profile_backend=timed_stage
 if command -v ncu >/dev/null 2>&1;then profile_backend=ncu;fi
 for m in 8 3679;do set +e
  if [ "$profile_backend" = ncu ];then ncu --target-processes all --nvtx --nvtx-include marlin_candidate --metrics dram__bytes_read.sum,lts__t_bytes.sum,sm__warps_active.avg.pct_of_peak_sustained_active,sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active --csv --log-file "$out/profile-m$m.csv" python3 "$MICROBENCH_PATH" --stage profile --case merged_gate_up --m "$m" --output "$out/profile-m$m.json" >"$out/profile-m$m.stdout" 2>"$out/profile-m$m.stderr"
  else python3 "$MICROBENCH_PATH" --stage profile --case merged_gate_up --m "$m" --output "$out/profile-m$m.json" >"$out/profile-m$m.stdout" 2>"$out/profile-m$m.stderr";fi
  prc=$?;set -e;[ "$prc" -eq 0 ]||profile_pass=false
 done
fi
session_started=${SESSION_STARTED_EPOCH:-$start}
# The Machete continuation authorizes only the sentinel, sweep, and profiles.
trigger=false;head_run=false;head_rc=99
kill -TERM "$telemetry" 2>/dev/null||true;wait "$telemetry" 2>/dev/null||true;telemetry=
python3 - "$out/sweep.json" "$out/stage-terminal.json" "$sweep_rc" "$profile_pass" "$profile_backend" "$trigger" "$head_run" "$head_rc" "$session_started" "$start" "$sweep_end" <<'PY'
import json,sys,time
r=json.load(open(sys.argv[1]));head=None
try:head=json.load(open('/workspace/h100-w4-conditional/head.json'))
except:pass
t={'schema_version':1,'stage':'conditional','type':'h100_w4_sweep_profiles_machete','result':r,'profiles':{'attempted':r.get('pass') is True,'required_rows':['merged_gate_up_m8','merged_gate_up_m3679'],'backend':sys.argv[5],'pass':sys.argv[4]=='true','hardware_counters_available':sys.argv[5]=='ncu'},'head_disposition':{'authorized':False,'reason':'director_machete_continuation_excludes_head','trigger':sys.argv[6]=='true','run':sys.argv[7]=='true','returncode':int(sys.argv[8]),'result':head},'timing':{'session_started_epoch':float(sys.argv[9]),'sweep_started_epoch':float(sys.argv[10]),'sweep_ended_epoch':float(sys.argv[11]),'setup_seconds':float(sys.argv[10])-float(sys.argv[9])},'pass':bool(sys.argv[3]=='0' and r.get('pass') is True and len(r.get('rows',[]))==24 and sys.argv[4]=='true')};json.dump(t,open(sys.argv[2],'w'),indent=2,sort_keys=True);open(sys.argv[2],'a').write('\n');raise SystemExit(0 if t['pass'] else 1)
PY
