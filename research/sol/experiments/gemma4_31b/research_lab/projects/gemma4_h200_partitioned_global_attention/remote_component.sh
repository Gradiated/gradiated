#!/usr/bin/env bash
set -Eeuo pipefail

root=${PARTITIONED_ATTENTION_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"
rm -f "$artifacts/COMPONENT_RESULT.json" "$artifacts/candidate-global.ncu-rep" "$artifacts/ncu-export.csv"

ncu_path=$(sudo docker run --rm "$image" sh -lc 'command -v ncu || find /opt/nvidia -type f -name ncu 2>/dev/null | head -n1' | tail -n1)
test -n "$ncu_path"

metrics=sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,dram__throughput.avg.pct_of_peak_sustained_elapsed,lts__throughput.avg.pct_of_peak_sustained_elapsed,sm__warps_active.avg.pct_of_peak_sustained_active,launch__occupancy_limit_registers,launch__occupancy_limit_shared_mem,launch__registers_per_thread,launch__registers_per_thread_allocated,launch__shared_mem_per_block_dynamic,launch__shared_mem_per_block,launch__sm_count,launch__waves_per_multiprocessor,sm__maximum_warps_avg_per_active_cycle,sm__maximum_warps_per_active_cycle_pct,gpu__time_duration.sum,profiler__replayer_passes

set +e
sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN \
  -v "$root:/work" -w /work/input \
  -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  "$image" "$ncu_path" --target-processes all --profile-from-start off \
  --kernel-name-base function --kernel-name 'regex:^_fwd_kernel$' --launch-count 1 \
  --metrics "$metrics" --export /work/artifacts/candidate-global \
  python3 /work/input/component_benchmark.py \
    --source /work/input/inputs/extend_attention.v0.5.13.py \
    --artifact-root /work/artifacts/component --profile-candidate \
  >"$artifacts/component.stdout" 2>"$artifacts/component.stderr"
benchmark_rc=$?
set -e

test -f "$artifacts/component/INVOCATION_STATE.json"
test -f "$artifacts/component/COMPONENT_TERMINAL.json"
test -f "$artifacts/candidate-global.ncu-rep"
sudo docker run --rm -v "$root:/work" "$image" "$ncu_path" \
  --import /work/artifacts/candidate-global.ncu-rep --csv --page raw \
  >"$artifacts/ncu-export.csv" 2>"$artifacts/ncu-export.stderr"

set +e
python3 "$input/analyze_component.py" \
  --component-terminal "$artifacts/component/COMPONENT_TERMINAL.json" \
  --ncu-csv "$artifacts/ncu-export.csv" \
  --ncu-report "$artifacts/candidate-global.ncu-rep" \
  --output "$artifacts/COMPONENT_RESULT.json" \
  >"$artifacts/analyze.stdout" 2>"$artifacts/analyze.stderr"
analyze_rc=$?
set -e

python3 - "$artifacts/REMOTE_TERMINAL.json" "$benchmark_rc" "$analyze_rc" <<'PY'
import datetime, json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
value = {
    "schema_version": 1,
    "status": "terminal",
    "classification": "component_complete" if int(sys.argv[3]) in (0, 2) else "component_consumer_failure",
    "benchmark_returncode": int(sys.argv[2]),
    "analyzer_returncode": int(sys.argv[3]),
    "candidate_cuda_invocation_started": json.loads((path.parent / "component/INVOCATION_STATE.json").read_text()).get("candidate_cuda_invocation_started", False),
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary = path.with_suffix(".part")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY

exit "$analyze_rc"
