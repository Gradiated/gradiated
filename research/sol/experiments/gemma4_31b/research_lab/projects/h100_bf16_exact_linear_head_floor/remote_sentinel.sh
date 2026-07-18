#!/usr/bin/env bash
set -Eeuo pipefail
out=/workspace/h100-bf16-sentinel; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish(){ rc=$?;set +e;[ -n "$telemetry" ]&&kill -TERM "$telemetry" 2>/dev/null;[ -n "$telemetry" ]&&wait "$telemetry" 2>/dev/null;nvidia-smi -q >"$out/nvidia-smi-final.txt" 2>&1;python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);a=[{'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in sorted(r.rglob('*'))if p.is_file()and p.name!='manifest.json'];(r/'manifest.json').write_text(json.dumps(a,indent=2,sort_keys=True)+'\\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$ARTIFACT_BASENAME.tar.gz" h100-bf16-sentinel;sha256sum "$public/$ARTIFACT_BASENAME.tar.gz">"$public/$ARTIFACT_BASENAME.tar.gz.sha256";exit "$rc";};trap finish EXIT
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ];do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits;sleep .2;done)>"$out/telemetry.csv" 2>"$out/telemetry.stderr" & telemetry=$!
set +e;python3 "$MICROBENCH_PATH" --stage sentinel --output "$out/result.json" --seed 20260717 >"$out/stdout.log" 2>"$out/stderr.log";rc=$?;set -e
kill -TERM "$telemetry" 2>/dev/null||true;wait "$telemetry" 2>/dev/null||true;telemetry=
python3 - "$out/result.json" "$out/telemetry.csv" "$out/stage-terminal.json" "$rc" <<'PY'
import csv,json,sys
r=json.load(open(sys.argv[1]));rows=list(csv.reader(open(sys.argv[2])));names=sorted({x[2].strip()for x in rows if len(x)>=9});t={'schema_version':1,'stage':'primary','type':'retrieved_h100_bf16_sliding_qkv_m8_sentinel','result':r,'telemetry':{'rows':len(rows),'gpu_names':names},'pass':sys.argv[4]=='0' and r.get('sentinel',{}).get('pass') is True and names==['NVIDIA H100 80GB HBM3'] and len(rows)>=2};json.dump(t,open(sys.argv[3],'w'),indent=2,sort_keys=True);open(sys.argv[3],'a').write('\\n');raise SystemExit(0 if t['pass'] else 1)
PY
