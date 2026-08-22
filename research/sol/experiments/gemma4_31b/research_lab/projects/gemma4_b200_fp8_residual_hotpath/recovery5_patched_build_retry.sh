#!/usr/bin/env bash
set -Eeuo pipefail

# Narrow same-claim repair for the recorded CMake CUDA_nvrtc_LIBRARY defect.
# It consumes only the already-built derived image and already-patched fresh
# source tree; it does not clone, rebuild the image, or submit a science arm.
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_residual_hotpath
artifact_root=$project/artifacts/b200-m32-dispatch-recovery5-20260728t1623z
host=46.243.147.55
user=glmrunner
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
remote=/home/glmrunner/b200-m32-dispatch-20260728t1623z
source_remote=$remote/vllm-recovery5
derived=b200-m32-recovery5:20260728t1623z
log=$artifact_root/patched-build-repair5.log

ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
{
  date -u +%FT%TZ
  "${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint bash -e SETUPTOOLS_SCM_PRETEND_VERSION=0.19.1.dev6+g6d4a8e6d2 -e SETUPTOOLS_SCM_PRETEND_VERSION_FOR_VLLM=0.19.1.dev6+g6d4a8e6d2 -e CUDA_HOME=/usr/local/cuda -e CUDA_PATH=/usr/local/cuda -e LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/targets/x86_64-linux/lib -v /usr/local/cuda:/usr/local/cuda:ro -v '$source_remote:/work/vllm' '$derived' -lc 'git config --global --add safe.directory /work/vllm && cd /work/vllm && CMAKE_ARGS=\"-DCUDA_nvrtc_LIBRARY=/usr/local/cuda/lib64/libnvrtc.so\" pip install -e . --no-build-isolation --no-deps'"
  date -u +%FT%TZ
} >"$log" 2>&1

python3 - "$artifact_root/REPAIR_BOUNDARY.json" "$log" <<'PY'
import hashlib, json, pathlib, sys
out, log = map(pathlib.Path, sys.argv[1:])
value = {
    'schema_version': 1,
    'classification': 'patched_build_repair_succeeded',
    'science_consumed': False,
    'candidate_science_started': False,
    'stage': 'patched_build',
    'repair_scope': 'patched_build',
    'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
}
tmp = out.with_suffix('.json.part')
tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
tmp.replace(out)
PY
