#!/usr/bin/env bash
set -Eeuo pipefail

remote_root=${INT4_REMOTE_ROOT:?}
input_root="${remote_root}/input"
artifact_root="${remote_root}/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "${artifact_root}"
rm -f "${artifact_root}/REMOTE_TERMINAL.json"

compact() {
  set +e
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "${remote_root}/component-compact.tar.gz.part" -C "${artifact_root}" .
  mv "${remote_root}/component-compact.tar.gz.part" "${remote_root}/component-compact.tar.gz"
  sha256sum "${remote_root}/component-compact.tar.gz" >"${remote_root}/component-compact.tar.gz.sha256"
}
trap compact EXIT

ncu_path=$(sudo docker run --rm "${image}" sh -lc 'command -v ncu || find /opt/nvidia -type f -name ncu 2>/dev/null | head -n1' | tail -n1)
test -n "${ncu_path}"
metrics=dram__sectors_read.sum,lts__t_sectors_op_read.sum

set +e
sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN \
  -v "${remote_root}:/work" -w /work/input \
  -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  "${image}" "${ncu_path}" --target-processes all --profile-from-start off \
  --kernel-name-base function \
  --kernel-name 'regex:.*(_fwd_grouped_kernel_stage1|_int4_grouped_stage1).*' \
  --launch-count 2 --metrics "${metrics}" --export /work/artifacts/local-int4-component \
  python3 /work/input/int4_component.py \
    --artifact-root /work/artifacts --iterations 31 \
  >"${artifact_root}/worker.stdout" 2>"${artifact_root}/worker.stderr"
worker_code=$?
set -e

analysis_code=99
if [[ -f "${artifact_root}/local-int4-component.ncu-rep" && -f "${artifact_root}/COMPONENT_RESULT.json" ]]; then
  sudo docker run --rm -v "${remote_root}:/work" "${image}" "${ncu_path}" \
    --import /work/artifacts/local-int4-component.ncu-rep --csv --page raw \
    >"${artifact_root}/ncu-export.csv" 2>"${artifact_root}/ncu-export.stderr"
  set +e
  python3 "${input_root}/analyze_component.py" \
    --component-result "${artifact_root}/COMPONENT_RESULT.json" \
    --ncu-csv "${artifact_root}/ncu-export.csv" \
    --ncu-report "${artifact_root}/local-int4-component.ncu-rep" \
    --output "${artifact_root}/COMPONENT_RESULT.json" \
    >"${artifact_root}/analyze.stdout" 2>"${artifact_root}/analyze.stderr"
  analysis_code=$?
  set -e
fi

python3 - "${artifact_root}/REMOTE_TERMINAL.json" "${worker_code}" "${analysis_code}" <<'PY'
import datetime as dt
import json
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
worker_code, analysis_code = map(int, sys.argv[2:])
invocation_path = path.parent / "INVOCATION_STATE.json"
invocation = json.loads(invocation_path.read_text()) if invocation_path.is_file() else {}
component = path.parent / "COMPONENT_TERMINAL.json"
classification = "component_complete" if component.is_file() else "integration_failure"
value = {
    "schema_version": 1,
    "classification": classification,
    "worker_exit_code": worker_code,
    "analysis_exit_code": analysis_code,
    "candidate_cuda_invocation_started": invocation.get("candidate_cuda_invocation_started", False),
    "candidate_scientific_invocation_started": invocation.get("candidate_scientific_invocation_started", False),
    "producer_completed": invocation.get("producer_completed", False),
    "scientific_terminal_recorded": invocation.get("scientific_terminal_recorded", False),
    "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary = path.with_suffix(".part")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY

if [[ -f "${artifact_root}/COMPONENT_TERMINAL.json" ]]; then
  exit 0
fi
exit "${worker_code}"
