#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"; base="${ARTIFACT_BASENAME:?}"; out=/workspace/gemma-c32-attention; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish() { rc=$?; set +e; [ -n "$telemetry" ] && kill "$telemetry" 2>/dev/null; nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1; python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); fs=[]
for p in sorted(r.rglob('*')):
 if p.is_file() and p.name!='manifest.json': fs.append({'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(r/'manifest.json').write_text(json.dumps(fs,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" gemma-c32-attention; sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu,utilization.memory,power.draw --format=csv,noheader,nounits; sleep 1; done) > "$out/telemetry.csv" 2> "$out/telemetry.stderr.log" & telemetry=$!
set +e; python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 1234 > "$out/bench.stdout.log" 2> "$out/bench.stderr.log"; rc=$?; set -e
kill "$telemetry" 2>/dev/null || true; wait "$telemetry" 2>/dev/null || true; telemetry=
cp "$out/result.json" "$out/stage-terminal.json"; exit "$rc"
