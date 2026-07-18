#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_global_head_dim256_backend_unlock
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
remote=/home/glmrunner/gemma-attention-endpoint
run_id=global-head256-xqa-20260718t2130z
out="$project/artifacts/$run_id"
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
container=gemma-global-head256-discriminator
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
export PYTHONPATH=/root/workspace/research/factory/src
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
heartbeat_pid=

cleanup() {
  [[ -z "$heartbeat_pid" ]] || { kill "$heartbeat_pid" >/dev/null 2>&1 || true; wait "$heartbeat_pid" >/dev/null 2>&1 || true; }
}
trap cleanup EXIT

sha256sum "$project/global_head_dim256_discriminator.py" > "$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "mkdir -p $remote/workspace $remote/$run_id; sudo docker image inspect $image >/dev/null; sudo docker inspect gemma-prefill-cap32768-c32 >/dev/null" > "$out/remote-preflight.log" 2>&1
"${scp_cmd[@]}" "$project/global_head_dim256_discriminator.py" "glmrunner@$ip:$remote/workspace/global_head_dim256_discriminator.py" > "$out/scp-input.log" 2>&1
"${ssh_cmd[@]}" "sha256sum $remote/workspace/global_head_dim256_discriminator.py" > "$out/remote-input-sha256.txt" 2>&1
cmp <(awk '{print $1}' "$out/local-input-sha256.txt") <(awk '{print $1}' "$out/remote-input-sha256.txt")
(
  while true; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_global_head_dim256_backend_unlock >> "$out/bench-heartbeats.jsonl" 2>> "$out/bench-heartbeats.stderr" || true; sleep 300; done
) & heartbeat_pid=$!

set +e
timeout --signal=TERM 2700 "${ssh_cmd[@]}" "set -Euo pipefail; sudo docker rm -f $container >/dev/null 2>&1 || true; sudo docker stop gemma-prefill-cap32768-c32 >/dev/null 2>&1 || true; nvidia-smi --query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,power.draw --format=csv,noheader,nounits -l 1 > $remote/$run_id/gpu-samples.csv & sampler=\$!; trap 'kill \$sampler >/dev/null 2>&1 || true' EXIT; sudo docker run --rm --name $container --gpus all --ipc=host --network host -v $remote:/work $image python3 /work/workspace/global_head_dim256_discriminator.py --output /work/$run_id; code=\$?; kill \$sampler >/dev/null 2>&1 || true; wait \$sampler >/dev/null 2>&1 || true; sha256sum $remote/workspace/global_head_dim256_discriminator.py > $remote/$run_id/remote-runner-sha256.txt; sudo docker image inspect $image > $remote/$run_id/image-inspect.json; tar -C $remote -czf $remote/$run_id.tar.gz $run_id; exit \$code" > "$out/remote-owner.stdout" 2> "$out/remote-owner.stderr"
remote_exit=$?
set -e
printf '%s\n' "$remote_exit" > "$out/remote-owner.exit"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz" > "$out/scp-artifacts.log" 2>&1 || true
if [[ -s "$out/artifacts.tar.gz" ]]; then tar -xzf "$out/artifacts.tar.gz" -C "$out"; fi
test -s "$out/$run_id/RESULT.json"
cp "$out/$run_id/RESULT.json" "$out/RESULT.json"
sha256sum "$out/RESULT.json" "$out/$run_id/gpu-samples.csv" "$out/$run_id/remote-runner-sha256.txt" > "$out/SHA256SUMS"
exit "$remote_exit"
