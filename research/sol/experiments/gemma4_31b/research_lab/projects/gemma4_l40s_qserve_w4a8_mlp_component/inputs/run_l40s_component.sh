#!/usr/bin/env bash
set -euo pipefail

project=${1:?project path required}
output=${2:?output path required}
manifest="$project/GPU_INPUT_MANIFEST.json"
source_root="$project/inputs/qserve_sm89"

mkdir -p "$output"
python3 "$project/inputs/verify_packet.py" \
  --project "$project" \
  --manifest "$manifest" \
  >"$output/manifest-check.json"

set +e
(
  cd "$source_root"
  TORCH_CUDA_ARCH_LIST=8.9 python3 setup.py build_ext --inplace
) >"$output/compile.log" 2>&1
compile_exit=$?
set -e
python3 "$project/inputs/compile_report.py" \
  --log "$output/compile.log" \
  --output "$output/COMPILE_TERMINAL.json" \
  --exit-code "$compile_exit"

PYTHONPATH="$source_root${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$project/inputs/qserve_mlp_component.py" \
  --project "$project" \
  --manifest "$manifest" \
  --output "$output/component"
