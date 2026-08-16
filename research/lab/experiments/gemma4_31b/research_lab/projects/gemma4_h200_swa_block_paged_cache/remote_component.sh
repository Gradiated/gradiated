#!/usr/bin/env bash
set -uo pipefail

remote_root=${BLOCK_PAGED_REMOTE_ROOT:-/home/glmrunner/gemma4-swa-block-paged-cache}
input_root="${remote_root}/input"
artifact_root="${remote_root}/artifacts/component"
image="docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"

mkdir -p "${artifact_root}"
candidate_started=false
scientific_started=false

sudo docker run --rm --gpus all --ipc=host \
  -v "${input_root}:/block-input:ro" \
  -v "${artifact_root}:/block-artifacts" \
  "${image}" \
  bash -lc "cd /block-input && PYTHONPATH=/block-input:/sgl-workspace/sglang/python python3 block_paged_component.py --artifact-root /block-artifacts --batch-size 32 --context 1024 --warmups 5 --iterations 31 --seed 20260723" \
  >"${artifact_root}/worker.stdout" \
  2>"${artifact_root}/worker.stderr"
worker_code=$?

if [[ -f "${artifact_root}/INVOCATION_STATE.json" ]]; then
  candidate_started=$(python3 -c 'import json,sys; print(str(bool(json.load(open(sys.argv[1])).get("candidate_cuda_invocation_started"))).lower())' "${artifact_root}/INVOCATION_STATE.json")
  scientific_started=$(python3 -c 'import json,sys; print(str(bool(json.load(open(sys.argv[1])).get("candidate_scientific_invocation_started"))).lower())' "${artifact_root}/INVOCATION_STATE.json")
fi

classification=integration_failure
if [[ -f "${artifact_root}/COMPONENT_TERMINAL.json" ]]; then
  classification=component_complete
elif [[ "${candidate_started}" == "true" ]]; then
  classification=candidate_failure_after_cuda_start
fi

python3 - "${artifact_root}/REMOTE_TERMINAL.json" "${classification}" "${worker_code}" "${candidate_started}" "${scientific_started}" <<'PY'
import datetime as dt
import json
import os
import sys

path, classification, worker_code, candidate_started, scientific_started = sys.argv[1:]
value = {
    "schema_version": 1,
    "classification": classification,
    "worker_exit_code": int(worker_code),
    "candidate_cuda_invocation_started": candidate_started == "true",
    "candidate_scientific_invocation_started": scientific_started == "true",
    "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary = path + ".part"
with open(temporary, "w") as handle:
    json.dump(value, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(temporary, path)
PY

tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
  -czf "${remote_root}/component-compact.tar.gz.part" \
  -C "${artifact_root}" .
mv "${remote_root}/component-compact.tar.gz.part" "${remote_root}/component-compact.tar.gz"
sha256sum "${remote_root}/component-compact.tar.gz" >"${remote_root}/component-compact.tar.gz.sha256"
exit "${worker_code}"
