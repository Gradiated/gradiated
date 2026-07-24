#!/usr/bin/env bash
set -euo pipefail

project=${1:?project path required}
output=${2:?output path required}
shift 2
manifest="$project/EXACT_CONSUMER_GPU_INPUT_MANIFEST.json"

mkdir -p "$output"
source_root="$output/build-source"
cp -a "$project/inputs/exact_consumer/qserve_sm89" "$source_root"
chmod -R u+w "$source_root"
set +e
(
  cd "$source_root"
  TORCH_CUDA_ARCH_LIST=8.9 python3 setup.py build_ext --inplace
) >"$output/compile.log" 2>&1
compile_exit=$?
set -e
python3 "$project/inputs/exact_consumer/compile_report.py" \
  --log "$output/compile.log" \
  --output "$output/COMPILE_TERMINAL.json" \
  --exit-code "$compile_exit"
if (( compile_exit != 0 )); then
  exit "$compile_exit"
fi

PYTHONPATH="$source_root${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$project/inputs/exact_consumer/exact_component.py" \
  --project "$project" \
  --manifest "$manifest" \
  --output "$output/component" \
  "$@"
