#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_dynamic_fp8_endpoint
source_root=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/b200_nvfp4_gemma4_endpoint/inputs/bf16-source
target_root="$project/inputs/bf16-source"
out="$project/artifacts/snapshot-materialization-20260728t1451z"
mkdir -p "$target_root" "$out"
for name in config.json tokenizer.json tokenizer_config.json chat_template.jinja processor_config.json model.safetensors.index.json model-files.sha256 model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do
  cp --preserve=mode,timestamps "$source_root/$name" "$target_root/$name"
done
(cd "$target_root" && sha256sum -c model-files.sha256) >"$out/model-verification.log"
python3 - "$target_root" "$out/SNAPSHOT_TERMINAL.json" <<'PY'
import datetime, hashlib, json, os, pathlib, sys
root, out = map(pathlib.Path, sys.argv[1:])
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir()) if p.is_file()}
value = {"schema_version": 1, "classification": "project_local_checkpoint_snapshot", "completed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"), "root": str(root), "files": files, "model_manifest_sha256": hashlib.sha256((root / "model-files.sha256").read_bytes()).hexdigest()}
tmp = out.with_suffix(".part")
tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(tmp, out)
PY
