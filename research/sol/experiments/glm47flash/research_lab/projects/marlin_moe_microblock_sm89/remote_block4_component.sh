#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/workspace/campaign-100-mla-microbench
PUBLIC=/workspace/public-mla-microbench
rm -rf "$OUT" "$PUBLIC"
mkdir -p "$OUT" "$PUBLIC"
phase() { printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"; }
package() {
  python3 - <<'PY'
import hashlib,json
from pathlib import Path
r=Path('/workspace/campaign-100-mla-microbench')
rows=[{'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(r.rglob('*')) if p.is_file() and p.name!='manifest.json']
(r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$PUBLIC/block4-component.tar.gz.tmp" campaign-100-mla-microbench
  mv "$PUBLIC/block4-component.tar.gz.tmp" "$PUBLIC/block4-component.tar.gz"
  sha256sum "$PUBLIC/block4-component.tar.gz" > "$PUBLIC/block4-component.tar.gz.sha256"
}
trap 'rc=$?; nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1 || true; package; exit "$rc"' EXIT
phase bootstrap begin
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt"
python3 -m pip freeze > "$OUT/pip-freeze.txt"
phase component begin
python3 /input/block4_component.py --output "$OUT/microbench-result.json" --seed 1234 > "$OUT/microbench.stdout.log" 2> "$OUT/microbench.stderr.log"
cp "$OUT/microbench-result.json" "$OUT/allocation-result.json"
phase component complete
