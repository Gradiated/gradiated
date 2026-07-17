#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/glm47-lm-head-w4
PUBLIC=/workspace/public-mla-microbench
TELEMETRY=
rm -rf "$OUT" "$PUBLIC"
mkdir -p "$OUT" "$PUBLIC"

phase() { printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"; }
package_artifact() {
  python3 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('/workspace/glm47-lm-head-w4')
rows = [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'manifest.json']
(root / 'manifest.json').write_text(json.dumps(rows, indent=2, sort_keys=True) + '\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$PUBLIC/vllm-head-microbench.tar.gz.tmp" glm47-lm-head-w4
  mv "$PUBLIC/vllm-head-microbench.tar.gz.tmp" "$PUBLIC/vllm-head-microbench.tar.gz"
  sha256sum "$PUBLIC/vllm-head-microbench.tar.gz" > "$PUBLIC/vllm-head-microbench.tar.gz.sha256"
}
finish() {
  rc=$?; set +e; phase teardown begin
  [ -n "$TELEMETRY" ] && kill -TERM "$TELEMETRY" 2>/dev/null
  [ -n "$TELEMETRY" ] && wait "$TELEMETRY" 2>/dev/null
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  phase teardown complete; package_artifact; exit "$rc"
}
trap finish EXIT

phase bootstrap begin
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
sha256sum /input/lm_head_qweight.pt /input/lm_head_scales.pt /input/payload-manifest.json > "$OUT/input-sha256.txt"
python3 - <<'PY' > "$OUT/runtime.json"
import json, torch, vllm
print(json.dumps({'torch': torch.__version__, 'vllm': vllm.__version__, 'cuda': torch.version.cuda, 'device': torch.cuda.get_device_name()}, sort_keys=True))
PY
phase bootstrap complete
(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" & TELEMETRY=$!
phase exact_shape_sweep begin
set +e
python3 /input/vllm_head_marlin_microbench.py --output "$OUT/microbench-result.json" --seed 1234 > "$OUT/microbench.stdout.log" 2> "$OUT/microbench.stderr.log"
RC=$?
set -e
phase exact_shape_sweep complete
if [ -s "$OUT/microbench-result.json" ]; then
  python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
p=Path('/workspace/glm47-lm-head-w4/microbench-result.json'); row=json.loads(p.read_text())
row.update({'experiment_spec_sha256': os.environ['EXPERIMENT_SPEC_SHA256'], 'runtime_image': os.environ['RUNTIME_IMAGE_IDENTITY'], 'benchmark_sha256': hashlib.sha256(Path('/input/vllm_head_marlin_microbench.py').read_bytes()).hexdigest()})
Path('/workspace/glm47-lm-head-w4/allocation-result.json').write_text(json.dumps(row, indent=2, sort_keys=True)+'\n')
PY
fi
exit "$RC"
