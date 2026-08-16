#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_h200_dflash_endpoint
lab=/root/workspace/research/lab/experiments/gemma4_31b/research_lab
out="$1"
deadline=2026-07-25T20:35:00Z
remote=/home/glmrunner/gemma4-dflash/depth4-endpoint-project
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
mkdir -p "$out/packet" "$out/retrieved"
exec > >(tee -a "$out/OWNER_CONTROLLER.log") 2>&1
export PYTHONPATH=/root/workspace/research/factory/src
pool=(python3 -m grad_research.gpu_pool --lab "$lab")
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20 glmrunner@89.169.109.132)
scp=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20)
heartbeat() { while sleep 30; do "${pool[@]}" heartbeat --project gemma4_h200_dflash_endpoint >> "$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!
finish() { rc=$?; kill "$hb" 2>/dev/null || true; "${ssh[@]}" 'sudo docker rm -f gemma4-dflash >/dev/null 2>&1 || true' || true; "${pool[@]}" release --project gemma4_h200_dflash_endpoint --condition ready --contents "Depth-4 DFlash endpoint pair terminal/retrieval: $out" || true; exit "$rc"; }
trap finish EXIT
cp "$project"/{dflash_endpoint_runner.py,remote_depth4_endpoint_pair.sh} "$out/packet/"
sha256sum "$out/packet"/* > "$out/packet/BOUND.sha256"
"${ssh[@]}" "rm -rf '$remote' && mkdir -p '$remote'"
"${scp[@]}" "$out/packet/dflash_endpoint_runner.py" "$out/packet/remote_depth4_endpoint_pair.sh" "glmrunner@89.169.109.132:$remote/"
"${ssh[@]}" "chmod 700 '$remote/remote_depth4_endpoint_pair.sh'; bash '$remote/remote_depth4_endpoint_pair.sh'"
"${scp[@]}" -r "glmrunner@89.169.109.132:/home/glmrunner/gemma4-dflash/work/dflash-depth4-endpoint/." "$out/retrieved/"
python3 "$project/summarize_depth4_endpoint_pair.py" --results "$out/retrieved/results" --server-log "$out/retrieved/dflash.server.log" --output "$out/DFLASH_DEPTH4_ENDPOINT_TERMINAL.json"
cp "$out/DFLASH_DEPTH4_ENDPOINT_TERMINAL.json" "$project/DFLASH_DEPTH4_ENDPOINT_TERMINAL.json"
