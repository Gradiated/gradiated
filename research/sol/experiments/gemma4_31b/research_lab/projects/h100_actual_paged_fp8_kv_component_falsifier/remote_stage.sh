#!/usr/bin/env bash
set -Eeuo pipefail
out=/workspace/h100-paged-kv-${STAGE:?}; public=/workspace/public-mla-microbench; base=${ARTIFACT_BASENAME:?}
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish() { rc=$?; set +e; nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1; python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); rows=[]
for p in sorted(r.rglob('*')):
 if p.is_file() and p.name!='manifest.json': rows.append({'path':str(p.relative_to(r)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
(r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" "$(basename "$out")"
sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
set +e
python3 "$MICROBENCH_PATH" --stage "$STAGE" --output "$out/result.json" --seed 20260717 > "$out/benchmark.stdout.log" 2> "$out/benchmark.stderr.log"; rc=$?
set -e
python3 - "$out/result.json" "$out/stage-terminal.json" "$STAGE" "$rc" <<'PY'
import json,sys
r,t,stage,rc=sys.argv[1:]; value=json.load(open(r)); sentinel=value.get('sentinel',{})
terminal={'schema_version':1,'stage':stage,'pass':bool(rc=='0' and value.get('pass') is True),'all_actual_consumers_pass':value.get('all_actual_consumers_pass',False),'economic_both_envelopes_falsified':value.get('economic_both_envelopes_falsified',False),'sentinel':sentinel,'result':value,'typed_failure':None if value.get('pass') else {'class':'actual_image_producer_or_context_construction_failure','sentinel':sentinel}}
json.dump(terminal,open(t,'w'),indent=2,sort_keys=True); open(t,'a').write('\n')
PY
exit "$rc"
