#!/usr/bin/env bash
set -Eeuo pipefail

root=${LOCAL_ATTENTION_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"
rm -f "$artifacts/COMPONENT_RESULT.json" "$artifacts/local-control-candidate.ncu-rep" "$artifacts/ncu-export.csv"

terminal() {
  python3 - "$artifacts/REMOTE_TERMINAL.json" "$1" "$2" <<'PY'
import datetime, json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
invocation = path.parent / "component/INVOCATION_STATE.json"
state = json.loads(invocation.read_text()) if invocation.is_file() else {}
value = {
    "schema_version": 1,
    "status": "terminal",
    "classification": sys.argv[2],
    "message": sys.argv[3],
    "candidate_cuda_invocation_started": state.get("candidate_cuda_invocation_started", False),
    "scientific_invocation_started": state.get("scientific_invocation_started", False),
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary = path.with_suffix(".part")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY
}

compact() {
  set +e
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/component-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/component-compact.tar.gz" >"$root/component-compact.tar.gz.sha256"
}
trap compact EXIT
trap 'test -f "$artifacts/REMOTE_TERMINAL.json" || terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/REMOTE_TERMINAL.json"

sudo docker image inspect "$image" >/dev/null 2>&1 || \
  sudo docker pull "$image" >"$artifacts/image-pull.stdout" 2>"$artifacts/image-pull.stderr"
sudo docker image inspect "$image" >"$artifacts/image-inspect.json"

ncu_path=$(sudo docker run --rm "$image" sh -lc 'command -v ncu || find /opt/nvidia -type f -name ncu 2>/dev/null | head -n1' | tail -n1)
test -n "$ncu_path"

metrics=sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,dram__throughput.avg.pct_of_peak_sustained_elapsed,lts__throughput.avg.pct_of_peak_sustained_elapsed,sm__warps_active.avg.pct_of_peak_sustained_active,launch__occupancy_limit_registers,launch__occupancy_limit_shared_mem,launch__registers_per_thread,launch__registers_per_thread_allocated,launch__shared_mem_per_block_dynamic,launch__shared_mem_per_block,launch__stack_size,launch__sm_count,launch__waves_per_multiprocessor,l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum,l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum,gpu__time_duration.sum,profiler__replayer_passes

set +e
sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN \
  -v "$root:/work" -w /work/input \
  -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e LOCAL_ATTENTION_RESIDENCY_AUDIT=/work/artifacts/candidate-path.jsonl \
  -e TRITON_DUMP_PTXAS_LOG=1 \
  "$image" "$ncu_path" --target-processes all --profile-from-start off \
  --kernel-name-base function --kernel-name 'regex:^_fwd_kernel$' --launch-count 2 \
  --metrics "$metrics" --export /work/artifacts/local-control-candidate \
  python3 /work/input/component_benchmark.py \
    --source /work/input/inputs/source/extend_attention.v0.5.13.py \
    --artifact-root /work/artifacts/component --profile-candidate \
  >"$artifacts/component.stdout" 2>"$artifacts/component.stderr"
benchmark_rc=$?
set -e

test -f "$artifacts/component/INVOCATION_STATE.json"
test -f "$artifacts/component/COMPONENT_TERMINAL.json"
test -f "$artifacts/local-control-candidate.ncu-rep"
sudo docker run --rm -v "$root:/work" "$image" "$ncu_path" \
  --import /work/artifacts/local-control-candidate.ncu-rep --csv --page raw \
  >"$artifacts/ncu-export.csv" 2>"$artifacts/ncu-export.stderr"

set +e
python3 "$input/analyze_component.py" \
  --component-terminal "$artifacts/component/COMPONENT_TERMINAL.json" \
  --ncu-csv "$artifacts/ncu-export.csv" \
  --ncu-report "$artifacts/local-control-candidate.ncu-rep" \
  --output "$artifacts/COMPONENT_RESULT.json" \
  >"$artifacts/analyze.stdout" 2>"$artifacts/analyze.stderr"
analyze_rc=$?
set -e

if [[ "$analyze_rc" -eq 0 || "$analyze_rc" -eq 2 ]]; then
  terminal component_complete "benchmark_rc=$benchmark_rc analyzer_rc=$analyze_rc"
else
  terminal component_consumer_failure "benchmark_rc=$benchmark_rc analyzer_rc=$analyze_rc"
fi

exit "$analyze_rc"
