#!/usr/bin/env bash
set -Eeuo pipefail

project_root=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/b200_nvfp4_exact_shape_direct_falsifier
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00jxp168hnbx08c86
host=46.243.146.177
identity=/root/.config/nebius/glm-campaign/ssh_ed25519
known_hosts=/root/.config/nebius/glm-campaign/known_hosts
remote_root=/home/glmrunner/b200-nvfp4-source-audit-g6-20260728t1030z
artifact_root="$project_root/artifacts/b200-nvfp4-source-audit-g6-20260728t1030z"
mkdir -p "$artifact_root"
ssh_cmd=(ssh -i "$identity" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts" -o ConnectTimeout=20 glmrunner@"$host")
scp_cmd=(scp -i "$identity" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts")

heartbeat() {
  while true; do
    PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project b200_nvfp4_exact_shape_direct_falsifier >/dev/null || true
    sleep 30
  done
}

repair() {
  local reason=$1
  printf '%s\n' "$reason" > "$artifact_root/outer_failure.txt"
  /root/workspace/research/factory/tools/repair-handshake ready --root "$artifact_root" --repair-id b200-nvfp4-source-audit-g6-20260728t1030z --deadline 2026-07-28T10:34:30Z --failure-kind integration --diagnostic "$artifact_root/outer_failure.txt" --retry-scope "retrieve diagnostics and retain typed evidence until the absolute watchdog" || true
  /root/workspace/research/factory/tools/repair-handshake wait --root "$artifact_root" --repair-id b200-nvfp4-source-audit-g6-20260728t1030z --deadline 2026-07-28T10:34:30Z || true
}

heartbeat &
heartbeat_pid=$!
trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT

if ! "${ssh_cmd[@]}" "mkdir -p '$remote_root/input' '$remote_root/output'"; then
  repair "remote staging root creation failed before science"
  exit 1
fi
if ! "${scp_cmd[@]}" "$project_root/b200_nvfp4_evaluator.py" "$project_root/remote_b200_nvfp4_development.sh" "$project_root/inputs/MECHANISM.json" "glmrunner@$host:$remote_root/input/"; then
  repair "immutable project-local input transfer failed before science"
  exit 1
fi
if ! "${ssh_cmd[@]}" "chmod 755 '$remote_root/input/remote_b200_nvfp4_development.sh' && sudo -n docker pull docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79" >"$artifact_root/docker-pull.log" 2>&1; then
  repair "pinned image pull failed before science"
  exit 1
fi
set +e
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --entrypoint /bin/bash -e WORK_DIR=/output -v '$remote_root/input:/input:ro' -v '$remote_root/output:/output' docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79 /input/remote_b200_nvfp4_development.sh" >"$artifact_root/worker.stdout.log" 2>"$artifact_root/worker.stderr.log"
worker_rc=$?
set -e
"${ssh_cmd[@]}" "sudo -n chown -R glmrunner:glmrunner '$remote_root/output'" || true
"${scp_cmd[@]}" -r "glmrunner@$host:$remote_root/output/." "$artifact_root/remote-output" >"$artifact_root/retrieve.stdout.log" 2>"$artifact_root/retrieve.stderr.log" || true
"${ssh_cmd[@]}" "nvidia-smi --query-gpu=name,utilization.gpu,memory.used --format=csv,noheader,nounits; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits || true" >"$artifact_root/post_worker_gpu.txt" 2>&1 || true
if [[ -f "$artifact_root/remote-output/artifacts/SWEEP.json" ]]; then
  cp "$artifact_root/remote-output/artifacts/SWEEP.json" "$artifact_root/TERMINAL.json"
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project b200_nvfp4_exact_shape_direct_falsifier --condition ready >/dev/null
  exit 0
fi
repair "worker exited $worker_rc without a retrieved exact 24-row terminal; raw logs and remote output retrieval are retained"
exit "$worker_rc"
