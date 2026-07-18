#!/usr/bin/env bash
set -Eeuo pipefail
root=/workspace/frontier-$STAGE; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$root" "$public"; mkdir -p "$root" "$public"
finish() { rc=$?; set +e; [ -n "$telemetry" ] && kill -TERM "$telemetry" 2>/dev/null; [ -n "$telemetry" ] && wait "$telemetry" 2>/dev/null; python3 - "$root" "$STAGE" "$rc" <<'PY'
import hashlib,json,sys
from pathlib import Path
root,stage,rc=Path(sys.argv[1]),sys.argv[2],int(sys.argv[3]); result={}
try: result=json.loads((root/'result.json').read_text())
except Exception as error: result={'pass':False,'error':{'type':type(error).__name__,'message':str(error)}}
files=[]
for path in sorted(root.rglob('*')):
 if path.is_file() and path.name not in ('manifest.json','stage-terminal.json'): files.append({'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(files,indent=2,sort_keys=True)+'\n')
terminal={'schema_version':1,'stage':stage,'result':result,'all_actual_consumers_pass':result.get('all_actual_consumers_pass', result.get('pass')),'pass':bool(rc==0 and result.get('pass') is True)}
(root/'stage-terminal.json').write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$ARTIFACT_BASENAME.tar.gz" "frontier-$STAGE"; sha256sum "$public/$ARTIFACT_BASENAME.tar.gz" > "$public/$ARTIFACT_BASENAME.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits; sleep .15; done) > "$root/telemetry.csv" 2> "$root/telemetry.stderr" & telemetry=$!
python3 "$MICROBENCH_PATH" --output "$root/result.json" > "$root/program.stdout" 2> "$root/program.stderr"
