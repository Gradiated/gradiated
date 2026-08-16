#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence
remote=/home/glmrunner/gemma-generation-equivalence
ip=195.242.13.223
key=/root/.config/nebius/glm-campaign/ssh_ed25519
out="$project/artifacts/h200-generation-equivalence-20260718t1318z"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
exec > >(tee -a "$out/consumer.stdout.log") 2> >(tee -a "$out/consumer.stderr.log" >&2)
"${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models >/dev/null; sudo docker exec gemma-generation-equivalence sh -c "test -e /root/workspace || ln -s /work/workspace /root/workspace"'
"${ssh_cmd[@]}" 'sudo docker exec -e PYTHONPATH=/root/workspace/research/lab/experiments/glm47flash/campaign_100/quality gemma-generation-equivalence python3 /root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_sglang_transformers_generation_equivalence/generation_equivalence_runner.py generate --checkpoint /work/checkpoint --sglang-base http://127.0.0.1:30000 --output-dir /work/run' >"$out/runner.stdout.log" 2>"$out/runner.stderr.log"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/TERMINAL.json" "$out/TERMINAL.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/transformers_raw.json" "$out/transformers_raw.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/run/sglang_raw.json" "$out/sglang_raw.json"
