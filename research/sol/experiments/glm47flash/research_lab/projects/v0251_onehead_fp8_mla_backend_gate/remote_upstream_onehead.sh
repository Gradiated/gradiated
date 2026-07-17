#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/upstream-onehead
PUBLIC=/workspace/public-upstream-onehead
TELEMETRY=
BENCH=/input/upstream_onehead_fp8_mla.py
rm -rf "$OUT" "$PUBLIC"
mkdir -p "$OUT" "$PUBLIC"
phase() { printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"; }
package_artifact() {
  python3 - <<'PY'
import hashlib, json
from pathlib import Path
root=Path('/workspace/upstream-onehead')
rows=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name != 'manifest.json':
        rows.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$PUBLIC/upstream-onehead.tar.gz.tmp" upstream-onehead
  mv "$PUBLIC/upstream-onehead.tar.gz.tmp" "$PUBLIC/upstream-onehead.tar.gz"
  sha256sum "$PUBLIC/upstream-onehead.tar.gz" > "$PUBLIC/upstream-onehead.tar.gz.sha256"
}
finish() {
  rc=$?
  set +e
  phase teardown begin
  [ -n "$TELEMETRY" ] && kill -TERM "$TELEMETRY" 2>/dev/null
  [ -n "$TELEMETRY" ] && wait "$TELEMETRY" 2>/dev/null
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  phase teardown complete
  package_artifact
  exit "$rc"
}
trap finish EXIT

phase bootstrap begin
uname -a > "$OUT/uname.txt"
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
python3 -m pip freeze > "$OUT/pip-freeze.txt"
python3 - <<'PY' > "$OUT/native-import.json"
import hashlib, json
from pathlib import Path
import torch, triton, vllm
paths=[Path('/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/backends/mla/triton_mla.py'),Path('/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_reshape_and_cache_flash.py'),Path('/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_decode_attention.py')]
print(json.dumps({'vllm':vllm.__version__,'torch':torch.__version__,'triton':triton.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability(),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2,sort_keys=True))
PY
phase bootstrap complete
(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" & TELEMETRY=$!
phase upstream_onehead_matrix begin
set +e
python3 "$BENCH" --output "$OUT/result.json" --seed 1234 > "$OUT/benchmark.stdout.log" 2> "$OUT/benchmark.stderr.log"
rc=$?
set -e
phase upstream_onehead_matrix complete
if [ -s "$OUT/result.json" ]; then cp "$OUT/result.json" "$OUT/allocation-result.json"; fi
exit "$rc"
