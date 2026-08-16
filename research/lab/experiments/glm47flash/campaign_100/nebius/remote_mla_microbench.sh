#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/campaign-100-mla-microbench
PUBLIC=/workspace/public-mla-microbench
TELEMETRY=
MICROBENCH_PATH="${MICROBENCH_PATH:-/input/vllm_mla_microbench.py}"

rm -rf "$OUT" "$PUBLIC"
mkdir -p "$OUT" "$PUBLIC"

phase() {
  printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"
}

package_artifact() {
  python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
root = Path("/workspace/campaign-100-mla-microbench")
rows = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "manifest.json":
        rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(root / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C /workspace -czf "$PUBLIC/mla-microbench.tar.gz.tmp" campaign-100-mla-microbench
  mv "$PUBLIC/mla-microbench.tar.gz.tmp" "$PUBLIC/mla-microbench.tar.gz"
  sha256sum "$PUBLIC/mla-microbench.tar.gz" > "$PUBLIC/mla-microbench.tar.gz.sha256"
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
import hashlib
import json
import os
from pathlib import Path
import torch
import triton
import vllm
source = Path("/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_decode_attention.py")
benchmark = Path(os.environ.get("MICROBENCH_PATH", "/input/vllm_mla_microbench.py"))
print(json.dumps({
    "vllm": vllm.__version__,
    "torch": torch.__version__,
    "triton": triton.__version__,
    "cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(),
    "capability": torch.cuda.get_device_capability(),
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "benchmark_sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest(),
}, indent=2, sort_keys=True))
PY
phase bootstrap complete

(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY=$!

phase exact_shape_sweep begin
printf '%q ' python3 "$MICROBENCH_PATH" --output "$OUT/microbench-result.json" --seed 1234 > "$OUT/microbench-command.txt"
set +e
python3 "$MICROBENCH_PATH" --output "$OUT/microbench-result.json" --seed 1234 \
  > "$OUT/microbench.stdout.log" 2> "$OUT/microbench.stderr.log"
MICROBENCH_RC=$?
set -e
phase exact_shape_sweep complete

if [ -s "$OUT/microbench-result.json" ]; then
python3 - <<'PY'
import json
import os
from pathlib import Path
source = Path("/workspace/campaign-100-mla-microbench/microbench-result.json")
result = json.loads(source.read_text())
result.update({
    "experiment_spec_sha256": os.environ["EXPERIMENT_SPEC_SHA256"],
    "runtime_image": os.environ["RUNTIME_IMAGE_IDENTITY"],
    "benchmark_sha256": __import__("hashlib").sha256(Path(os.environ["MICROBENCH_PATH"]).read_bytes()).hexdigest(),
})
Path("/workspace/campaign-100-mla-microbench/allocation-result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n"
)
PY
fi

exit "$MICROBENCH_RC"
