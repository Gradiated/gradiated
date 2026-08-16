#!/usr/bin/env bash
set -Eeuo pipefail

root=${MIRRORED_RING_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/component-artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts" "$root/triton-cache"
rm -f "$artifacts/REMOTE_TERMINAL.json" "$artifacts/COMPONENT_TERMINAL.json"

compact() {
  set +e
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/component-compact.tar.gz.part" -C "$artifacts" .
  mv "$root/component-compact.tar.gz.part" "$root/component-compact.tar.gz"
  sha256sum "$root/component-compact.tar.gz" >"$root/component-compact.tar.gz.sha256"
}
trap compact EXIT

run_component() {
  local mode=$1
  local destination=$2
  sudo docker run --rm --gpus all --ipc=host \
    -v "$root:/work" -w /work/input \
    -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e TRITON_CACHE_DIR=/work/triton-cache \
    "$image" python3 /work/input/mirrored_component.py \
      --artifact-root "$destination" \
      --extension /work/input/ring_e5m2_flash_ops.so \
      --mode "$mode" --warmups 5 --iterations 31 --seed 20260723
}

set +e
run_component smoke /work/component-artifacts/smoke \
  >"$artifacts/smoke.stdout" 2>"$artifacts/smoke.stderr"
smoke_code=$?
set -e

component_code=99
if [[ "$smoke_code" -eq 0 ]]; then
  set +e
  run_component component /work/component-artifacts \
    >"$artifacts/component.stdout" 2>"$artifacts/component.stderr"
  component_code=$?
  set -e
fi

profile_code=99
if python3 - "$artifacts/COMPONENT_TERMINAL.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
raise SystemExit(0 if p.is_file() and json.loads(p.read_text()).get("component_positive") else 1)
PY
then
  ncu_path=$(sudo docker run --rm "$image" sh -lc \
    'command -v ncu || find /opt/nvidia -type f -name ncu 2>/dev/null | head -n1' | tail -n1)
  if [[ -n "$ncu_path" ]]; then
    set +e
    sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN \
      -v "$root:/work" -w /work/input \
      -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
      -e TRITON_CACHE_DIR=/work/triton-cache \
      "$image" "$ncu_path" --target-processes all --nvtx \
      --nvtx-include 'candidate/' --kernel-name-base demangled \
      --metrics \
launch__registers_per_thread,launch__shared_mem_per_block_static,launch__shared_mem_per_block_dynamic,dram__sectors_read.sum,dram__sectors_write.sum,lts__t_sectors_op_read.sum,lts__t_sectors_op_write.sum \
      --csv --page raw \
      python3 /work/input/mirrored_component.py \
        --artifact-root /work/component-artifacts/profile \
        --extension /work/input/ring_e5m2_flash_ops.so \
        --mode profile --seed 20260723 \
      >"$artifacts/ncu.csv" 2>"$artifacts/ncu.stderr"
    profile_code=$?
    set -e
  fi
fi

python3 - "$artifacts/REMOTE_TERMINAL.json" "$smoke_code" "$component_code" "$profile_code" <<'PY'
import datetime as dt
import json
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
smoke_code, component_code, profile_code = map(int, sys.argv[2:])
invocation_path = path.parent / "INVOCATION_STATE.json"
invocation = json.loads(invocation_path.read_text()) if invocation_path.is_file() else {}
component = path.parent / "COMPONENT_TERMINAL.json"
classification = "component_complete" if component.is_file() else "integration_failure"
value = {
    "schema_version": 1,
    "classification": classification,
    "smoke_exit_code": smoke_code,
    "component_exit_code": component_code,
    "profile_exit_code": profile_code,
    "candidate_cuda_invocation_started": invocation.get(
        "candidate_cuda_invocation_started", False
    ),
    "candidate_scientific_invocation_started": invocation.get(
        "candidate_scientific_invocation_started", False
    ),
    "component_terminal_recorded": component.is_file(),
    "timestamp_utc": dt.datetime.now(dt.timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
}
temporary = path.with_suffix(".part")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY

[[ -f "$artifacts/COMPONENT_TERMINAL.json" ]]
