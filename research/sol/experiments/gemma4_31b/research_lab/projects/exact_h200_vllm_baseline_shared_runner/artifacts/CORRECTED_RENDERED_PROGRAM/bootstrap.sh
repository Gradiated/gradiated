#!/usr/bin/env bash
set -Eeuo pipefail
deadline=${1:?deadline epoch required}
w=/home/glmrunner/gemma
mkdir -p "$w/input" "$w/artifacts" "$w/runtime"
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io curl ca-certificates gnupg
fi
sudo systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq nvidia-container-toolkit
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker pull 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
sudo docker image inspect 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79' > "$w/runtime/image-inspect.json"
nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,clocks.sm,clocks.mem --format=csv,noheader,nounits > "$w/runtime/gpu-telemetry.csv"
nohup bash -c 'while test $(date +%s) -lt '"$deadline"'; do nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,clocks.sm,clocks.mem --format=csv,noheader,nounits; sleep 1; done' >> "$w/runtime/gpu-telemetry.csv" 2> "$w/runtime/gpu-telemetry.stderr" < /dev/null &
echo $! > "$w/runtime/gpu-telemetry.pid"
sudo docker rm -f gemma-vllm >/dev/null 2>&1 || true
sudo docker run -d --rm --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'   vllm serve "$w/model" --served-model-name 'google/gemma-4-31B-it' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-prefix-caching --enable-metrics --host 0.0.0.0 --port 30000 > "$w/runtime/container-id"
ready=0
while test $(date +%s) -lt "$deadline"; do
  if curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models.json"; then ready=1; break; fi
  sleep 5
done
test "$ready" = 1
sudo docker inspect gemma-vllm > "$w/runtime/container-inspect-after-load.json"
curl -fsS http://127.0.0.1:30000/metrics > "$w/runtime/metrics-after-load.prom"
