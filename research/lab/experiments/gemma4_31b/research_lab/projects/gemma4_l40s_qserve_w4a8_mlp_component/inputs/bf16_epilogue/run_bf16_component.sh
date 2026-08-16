#!/usr/bin/env bash
set -euo pipefail

project=${1:?project path required}
output=${2:?output path required}
manifest="$project/BF16_GPU_INPUT_MANIFEST.json"
source_root="$project/inputs/bf16_epilogue/qserve_sm89"

mkdir -p "$output"
python3 "$project/inputs/bf16_epilogue/verify_packet.py" \
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
python3 "$project/inputs/bf16_epilogue/compile_report.py" \
  --log "$output/compile.log" \
  --output "$output/COMPILE_TERMINAL.json" \
  --exit-code "$compile_exit"
if (( compile_exit != 0 )); then
  exit "$compile_exit"
fi

PYTHONPATH="$source_root${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$project/inputs/bf16_epilogue/qserve_bf16_component.py" \
  --project "$project" \
  --manifest "$manifest" \
  --output "$output/component"
