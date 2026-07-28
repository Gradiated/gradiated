#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence
remote=/home/glmrunner/gemma-generation-equivalence
checkpoint=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint
ip=195.242.13.223
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
out="$project/artifacts/h200-generation-equivalence-20260718t1318z"
mkdir -p "$out"
exec > >(tee "$out/owner.stdout.log") 2> >(tee "$out/owner.stderr.log" >&2)

ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
fail() { python3 -c 'import json,sys,datetime; print(json.dumps({"classification":"generation_equivalence_execution_failure","stage":sys.argv[1],"message":sys.argv[2],"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")},sort_keys=True))' "$1" "$2" >"$out/FAILURE.json"; exit 1; }
trap 'fail shell "$BASH_COMMAND"' ERR

"${ssh_cmd[@]}" 'set -e; if ! command -v docker >/dev/null; then sudo apt-get update && sudo apt-get install -y docker.io curl ca-certificates; fi; sudo systemctl enable --now docker; if ! command -v nvidia-ctk >/dev/null; then curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#" | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null; sudo apt-get update; sudo apt-get install -y nvidia-container-toolkit; sudo nvidia-ctk runtime configure --runtime=docker; sudo systemctl restart docker; fi; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; sudo install -d -o glmrunner -g glmrunner /home/glmrunner/gemma-generation-equivalence'
tar -C /root/workspace -cf - research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence research/sol/experiments/gemma4_31b/research_lab/projects/sglang_v0512_h200_safe_code_contract_quality research/sol/experiments/gemma4_31b/research_lab/projects/sglang_v0512_h200_output_contract_adapter research/sol/experiments/glm47flash/campaign_100/quality/score_pair.py research/sol/experiments/glm47flash/campaign_100/quality/validate_quality.py | "${ssh_cmd[@]}" "mkdir -p $remote/workspace && tar -C $remote/workspace -xf -"
tar -C "$checkpoint" -cf - . | "${ssh_cmd[@]}" "mkdir -p $remote/checkpoint && tar -C $remote/checkpoint -xf -"
"${ssh_cmd[@]}" "cd $remote/checkpoint && test \$(find . -maxdepth 1 -type f | wc -l) -eq 8 && sha256sum model.safetensors.index.json; sudo docker pull $image; sudo docker rm -f gemma-generation-equivalence >/dev/null 2>&1 || true; sudo docker run -d --name gemma-generation-equivalence --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype bfloat16 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 1 --mem-fraction-static 0.85"
for attempt in $(seq 1 90); do
  if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/models.json" 2>"$out/models.stderr.log"; then break; fi
  sleep 8
done
grep -q google/gemma-4-31B-it "$out/models.json" || { "${ssh_cmd[@]}" 'sudo docker logs gemma-generation-equivalence' >"$out/server.log" 2>&1 || true; fail readiness server_not_ready; }
"${ssh_cmd[@]}" "sudo docker exec -e PYTHONPATH=/work/workspace/research/sol/experiments/glm47flash/campaign_100/quality gemma-generation-equivalence python3 /work/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence/generation_equivalence_runner.py generate --checkpoint /work/checkpoint --sglang-base http://127.0.0.1:30000 --output-dir /work/run" >"$out/runner.stdout.log" 2>"$out/runner.stderr.log"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/TERMINAL.json" "$out/TERMINAL.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/transformers_raw.json" "$out/transformers_raw.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/sglang_raw.json" "$out/sglang_raw.json"
