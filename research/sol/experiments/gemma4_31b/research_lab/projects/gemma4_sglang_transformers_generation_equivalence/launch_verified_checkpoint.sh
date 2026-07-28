#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence
remote=/home/glmrunner/gemma-generation-equivalence
ip=195.242.13.223
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
out="$project/artifacts/h200-generation-equivalence-20260718t1318z"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
exec > >(tee -a "$out/final.stdout.log") 2> >(tee -a "$out/final.stderr.log" >&2)
"${ssh_cmd[@]}" "sudo docker rm -f gemma-generation-equivalence >/dev/null 2>&1 || true; sudo docker run -d --name gemma-generation-equivalence --gpus all --ipc=host --network host -v $remote:/work $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype bfloat16 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 1 --max-total-tokens 1024 --mem-fraction-static 0.85"
for attempt in $(seq 1 90); do
  if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/final_models.json" 2>"$out/final_models.stderr.log"; then break; fi
  sleep 8
done
grep -q google/gemma-4-31B-it "$out/final_models.json"
"${ssh_cmd[@]}" "sudo docker exec -e PYTHONPATH=/work/workspace/research/sol/experiments/glm47flash/campaign_100/quality gemma-generation-equivalence python3 /work/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence/generation_equivalence_runner.py generate --checkpoint /work/checkpoint --sglang-base http://127.0.0.1:30000 --output-dir /work/run" >"$out/runner.stdout.log" 2>"$out/runner.stderr.log"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/TERMINAL.json" "$out/TERMINAL.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/transformers_raw.json" "$out/transformers_raw.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/sglang_raw.json" "$out/sglang_raw.json"
