#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/workspace/gemma-exact-shape; PUBLIC=/workspace/public-mla-microbench; TELEMETRY=
rm -rf "$OUT" "$PUBLIC"; mkdir -p "$OUT" "$PUBLIC"
finish() { rc=$?; set +e; [ -n "$TELEMETRY" ] && kill "$TELEMETRY"; [ -n "$TELEMETRY" ] && wait "$TELEMETRY"; nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1; python3 - <<'PY'
import hashlib,json
from pathlib import Path
r=Path('/workspace/gemma-exact-shape'); rows=[]
for p in sorted(r.rglob('*')):
 if p.is_file(): rows.append({'path':str(p.relative_to(r)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
(r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$PUBLIC/gemma-l40s-fp8-exact-shape.tar.gz" gemma-exact-shape; sha256sum "$PUBLIC/gemma-l40s-fp8-exact-shape.tar.gz" > "$PUBLIC/gemma-l40s-fp8-exact-shape.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt"; python3 - <<'PY' > "$OUT/runtime.json"
import json,torch
print(json.dumps({'gpu':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability(),'torch':torch.__version__,'cuda':torch.version.cuda},sort_keys=True))
PY
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total,power.draw,clocks.current.sm --format=csv,noheader,nounits; sleep 1; done) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" & TELEMETRY=$!
set +e; python3 "$MICROBENCH_PATH" --output "$OUT/microbench-result.json" --seed 1729 > "$OUT/microbench.stdout.log" 2> "$OUT/microbench.stderr.log"; rc=$?; set -e
python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
root=Path('/workspace/gemma-exact-shape'); result=root/'microbench-result.json'; primary=root/'primary-rows.json'
if result.is_file(): x=json.loads(result.read_text())
elif primary.is_file(): x={'primary_persisted_before_kv':json.loads(primary.read_text()),'primary_fp8_pass':json.loads(primary.read_text()).get('primary_fp8_pass'), 'retained_kv_arm':{'triggered':True,'pass':False,'classification':'kv_failure_after_atomic_primary_persistence'}, 'sweep_pass':False}
else: x={'primary_fp8_pass':False,'retained_kv_arm':{'triggered':False,'pass':False,'classification':'primary_not_persisted'},'sweep_pass':False}
x.update({'experiment_spec_sha256':os.environ['EXPERIMENT_SPEC_SHA256'],'runtime_image':os.environ['RUNTIME_IMAGE_IDENTITY'],'benchmark_sha256':hashlib.sha256(Path(os.environ['MICROBENCH_PATH']).read_bytes()).hexdigest()}); (root/'allocation-result.json').write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
PY
exit "$rc"
