#!/usr/bin/env bash
set -Eeuo pipefail
out=/workspace/h100-bf16-sweep;public=/workspace/public-mla-microbench;telemetry=
rm -rf "$out" "$public";mkdir -p "$out" "$public"
finish(){ rc=$?;set +e;[ -n "$telemetry" ]&&kill -TERM "$telemetry" 2>/dev/null;[ -n "$telemetry" ]&&wait "$telemetry" 2>/dev/null;nvidia-smi -q >"$out/nvidia-smi-final.txt" 2>&1;python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);a=[{'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in sorted(r.rglob('*'))if p.is_file()and p.name!='manifest.json'];(r/'manifest.json').write_text(json.dumps(a,indent=2,sort_keys=True)+'\\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$ARTIFACT_BASENAME.tar.gz" h100-bf16-sweep;sha256sum "$public/$ARTIFACT_BASENAME.tar.gz">"$public/$ARTIFACT_BASENAME.tar.gz.sha256";exit "$rc";};trap finish EXIT
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ];do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits;sleep .2;done)>"$out/telemetry.csv" 2>"$out/telemetry.stderr" & telemetry=$!
set +e;python3 "$MICROBENCH_PATH" --stage sweep --output "$out/sweep.json" --seed 20260717 >"$out/sweep.stdout" 2>"$out/sweep.stderr";rc=$?;set -e
head=false;head_rc=99
if [ "$rc" -eq 0 ] && [ "$((CAMPAIGN_DEADLINE_EPOCH-$(date +%s)))" -ge 420 ];then
 head=$(python3 - "$out/sweep.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));score=sum(sum(x['cuda_event_ms']['raw'])for x in r.get('rows',[]))/1000;print('true'if r.get('sweep',{}).get('pass')and r['sweep'].get('surviving_concurrencies')and score>=0 else'false')
PY
 )
 [ "$head" = true ]&&{ set +e;python3 /input/vllm_parallel_lm_head_bench.py --stage head --output "$out/head.json" --seed 20260717 >"$out/head.stdout" 2>"$out/head.stderr";head_rc=$?;set -e; }
fi
kill -TERM "$telemetry" 2>/dev/null||true;wait "$telemetry" 2>/dev/null||true;telemetry=
python3 - "$out/sweep.json" "$out/stage-terminal.json" "$rc" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));t={'schema_version':1,'stage':'conditional','type':'h100_bf16_24_row_sweep','result':r,'head_disposition':{'trigger_name':'H100_BF16_LINEAR_SURVIVES_AND_SETUP_DOMINATES_AND_HEAD_READY','trigger':False,'run':False},'pass':sys.argv[3]=='0' and r.get('sweep',{}).get('pass') is True and len(r.get('rows',[]))==24};json.dump(t,open(sys.argv[2],'w'),indent=2,sort_keys=True);open(sys.argv[2],'a').write('\\n');raise SystemExit(0 if t['pass'] else 1)
PY
