#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/workspace/campaign-100-mla-microbench
PUBLIC=/workspace/public-mla-microbench
BENCH=/input/upstream_onehead_fp8_packet.py
rm -rf "$OUT" "$PUBLIC"; mkdir -p "$OUT" "$PUBLIC"
phase() { printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"; }
package_artifact() {
  python3 - <<'PY'
import hashlib,json
from pathlib import Path
root=Path('/workspace/campaign-100-mla-microbench'); rows=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name != 'manifest.json': rows.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$PUBLIC/mla-microbench.tar.gz.tmp" campaign-100-mla-microbench
  mv "$PUBLIC/mla-microbench.tar.gz.tmp" "$PUBLIC/mla-microbench.tar.gz"
  sha256sum "$PUBLIC/mla-microbench.tar.gz" > "$PUBLIC/mla-microbench.tar.gz.sha256"
}
finish() { rc=$?; set +e; phase teardown begin; nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1; phase teardown complete; package_artifact; exit "$rc"; }
trap finish EXIT
phase bootstrap begin
python3 - <<'PY' > "$OUT/native-import.json"
import hashlib,json
from pathlib import Path
import torch,triton,vllm
root=Path('/usr/local/lib/python3.12/dist-packages')
paths=[root/'vllm/v1/attention/backends/mla/triton_mla.py',root/'vllm/v1/attention/ops/triton_reshape_and_cache_flash.py',root/'vllm/v1/attention/ops/triton_decode_attention.py',root/'vllm/v1/worker/gpu_model_runner.py']
print(json.dumps({'vllm':vllm.__version__,'torch':torch.__version__,'triton':triton.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2,sort_keys=True))
PY
phase bootstrap complete
phase exact_onehead_matrix begin
set +e
python3 "$BENCH" --output "$OUT/allocation-result.json" --seed 1234 > "$OUT/benchmark.stdout.log" 2> "$OUT/benchmark.stderr.log"
rc=$?
set -e
phase exact_onehead_matrix complete
exit "$rc"
