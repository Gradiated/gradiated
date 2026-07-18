#!/usr/bin/env bash
set -Eeuo pipefail
out=/workspace/h100-w4-decode-residual
public=/workspace/public-mla-microbench
base=${ARTIFACT_BASENAME:?}
rm -rf "$out" "$public"
mkdir -p "$out" "$public"
telemetry_pid=
finish() {
  rc=$?
  set +e
  test -z "$telemetry_pid" || kill "$telemetry_pid" 2>/dev/null
  wait "$telemetry_pid" 2>/dev/null
  nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1
  python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); rows=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'manifest.json':
        rows.append({'path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
(root/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" "$(basename "$out")"
  sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"
  exit "$rc"
}
trap finish EXIT
nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv -lms 200 > "$out/nvml.csv" 2> "$out/nvml.stderr.log" &
telemetry_pid=$!
set +e
python3 "$MICROBENCH_PATH" --output "$out/result.json" > "$out/benchmark.stdout.log" 2> "$out/benchmark.stderr.log"
rc=$?
set -e
python3 - "$out/result.json" "$out/stage-terminal.json" "$rc" <<'PY'
import json,sys
result=json.load(open(sys.argv[1])); rc=int(sys.argv[3])
terminal={'schema_version':1,'stage':'c128_decode_residual','pass':rc==0 and result.get('pass') is True,
          'all_actual_consumers_pass':result.get('all_actual_consumers_pass') is True,
          'decision':result.get('decision'),'result':result,
          'typed_failure':None if result.get('pass') else result.get('error')}
json.dump(terminal,open(sys.argv[2],'w'),indent=2,sort_keys=True); open(sys.argv[2],'a').write('\n')
PY
exit "$rc"
