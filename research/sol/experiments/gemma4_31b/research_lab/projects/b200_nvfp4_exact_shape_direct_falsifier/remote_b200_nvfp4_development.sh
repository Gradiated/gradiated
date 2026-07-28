#!/usr/bin/env bash
set -Eeuo pipefail
work=${WORK_DIR:-/var/tmp/gemma-b200-nvfp4}
mkdir -p "$work/artifacts"
export VLLM_NVFP4_GEMM_BACKEND=cutlass
python3 /input/b200_nvfp4_evaluator.py \
  --mechanism /input/MECHANISM.json \
  --upstream-benchmark /vllm-workspace/benchmarks/kernels/benchmark_nvfp4_gemm.py \
  --output "$work/artifacts/SENTINEL.json" \
  --mode sentinel
metrics='dram__bytes_read.sum,lts__t_bytes.sum,sm__warps_active.avg.pct_of_peak_sustained_active,sm__pipe_tensor_op_hmma_cycles_active.avg.pct_of_peak_sustained_active'
python3 /input/b200_nvfp4_evaluator.py \
  --mechanism /input/MECHANISM.json \
  --upstream-benchmark /vllm-workspace/benchmarks/kernels/benchmark_nvfp4_gemm.py \
  --output "$work/artifacts/SWEEP.json" \
  --mode sweep
if command -v ncu >/dev/null 2>&1; then
  ncu --csv --page raw --force-overwrite \
    --section LaunchStats --section Occupancy --metrics "$metrics" \
    --target-processes all --launch-count 1 --kernel-name 'regex:.*cutlass.*fp4.*' \
    python3 /input/b200_nvfp4_evaluator.py \
      --mechanism /input/MECHANISM.json \
      --upstream-benchmark /vllm-workspace/benchmarks/kernels/benchmark_nvfp4_gemm.py \
      --output "$work/artifacts/SENTINEL_PROFILE_ROW.json" \
      --mode profile --shape sliding_qkv --m 8 \
    > "$work/artifacts/SENTINEL_LAUNCH_RESOURCES.csv" 2>&1
  for m in 8 3679; do
  ncu --csv --page raw --force-overwrite \
    --section LaunchStats --section Occupancy --metrics "$metrics" \
    --target-processes all --launch-count 1 --kernel-name 'regex:.*cutlass.*fp4.*' \
    python3 /input/b200_nvfp4_evaluator.py \
      --mechanism /input/MECHANISM.json \
      --upstream-benchmark /vllm-workspace/benchmarks/kernels/benchmark_nvfp4_gemm.py \
      --output "$work/artifacts/MERGED_GATE_UP_M${m}_PROFILE_ROW.json" \
      --mode profile --shape merged_gate_up --m "$m" \
    > "$work/artifacts/MERGED_GATE_UP_M${m}_COUNTERS.csv" 2>&1
  done
else
  printf '%s\n' 'ncu unavailable in pinned image; decisive exact-consumer sweep completed without optional profiler counters' \
    > "$work/artifacts/PROFILER_UNAVAILABLE.txt"
fi
nvidia-smi -q > "$work/artifacts/nvidia-smi-q.txt"
sha256sum /input/* > "$work/artifacts/input-sha256.txt"
