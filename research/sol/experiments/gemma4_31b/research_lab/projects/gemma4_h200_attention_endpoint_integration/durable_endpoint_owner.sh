#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_attention_endpoint_integration
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
remote=/home/glmrunner/gemma-attention-endpoint
checkpoint=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint
trace=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma_exact_cache_trace_contract/TRACE_PACKET.json
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
out="$project/artifacts/h200-attention-endpoint-20260718t1638z"
deadline_epoch=1784400180
mkdir -p "$out"
exec > >(tee -a "$out/owner.stdout.log") 2> >(tee -a "$out/owner.stderr.log" >&2)

ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)

event() {
  python3 - "$out/EVENTS.jsonl" "$1" "${2:-}" <<'PY'
import datetime,json,pathlib,sys
with pathlib.Path(sys.argv[1]).open('a') as f:
    f.write(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),'phase':sys.argv[2],'detail':sys.argv[3]},sort_keys=True)+'\n')
PY
}

fail() {
  python3 - "$out/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); value={'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}; t=p.with_suffix('.part'); t.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); t.replace(p)
PY
  exit 1
}
trap 'fail integration_owner_failure "$BASH_COMMAND"' ERR

event setup_start
"${ssh_cmd[@]}" "set -e; if ! command -v docker >/dev/null; then sudo apt-get update && sudo apt-get install -y docker.io curl ca-certificates; fi; sudo systemctl enable --now docker; if ! command -v nvidia-ctk >/dev/null; then curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null; sudo apt-get update; sudo apt-get install -y nvidia-container-toolkit; sudo nvidia-ctk runtime configure --runtime=docker; sudo systemctl restart docker; fi; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; sudo install -d -o glmrunner -g glmrunner $remote $remote/workspace $remote/checkpoint"

tar -C "$project" -cf - c32_endpoint_runner.py numerical_oracle.py reconcile_terminal.py IDENTITIES.json | "${ssh_cmd[@]}" "tar -C $remote/workspace -xf -"
"${scp_cmd[@]}" "$trace" "glmrunner@$ip:$remote/workspace/TRACE_PACKET.json"

event checkpoint_stage_start
(tar -C "$checkpoint" -cf - . | "${ssh_cmd[@]}" "tar -C $remote/checkpoint -xf -"; "${ssh_cmd[@]}" "cd $remote/checkpoint && test \$(find . -maxdepth 1 -type f | wc -l) -eq 8 && test \$(du -sb . | awk '{print \$1}') -eq 62578655208"; event checkpoint_stage_complete) &
checkpoint_pid=$!
event image_pull_start
("${ssh_cmd[@]}" "sudo docker pull $image" >"$out/image_pull.stdout.log" 2>"$out/image_pull.stderr.log"; event image_pull_complete) &
image_pid=$!
wait "$checkpoint_pid"
wait "$image_pid"

event source_extract_start
"${ssh_cmd[@]}" "set -e; sudo docker rm -f sglang-source-copy >/dev/null 2>&1 || true; sudo docker create --name sglang-source-copy $image true >/dev/null; rm -rf $remote/source; mkdir -p $remote/source; source_path=\$(sudo docker run --rm $image python3 -c 'import pathlib,sglang; print(pathlib.Path(sglang.__file__).resolve().parent)'); echo \$source_path >$remote/sglang_source_path.txt; sudo docker cp sglang-source-copy:\$source_path $remote/source/sglang; sudo chown -R glmrunner:glmrunner $remote/source; sudo docker rm sglang-source-copy >/dev/null; cd $remote/source && tar -czf $remote/sglang-source.tar.gz sglang"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/sglang-source.tar.gz" "$out/sglang-source.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/sglang_source_path.txt" "$out/sglang_source_path.txt"
event source_extract_complete

launch_server() {
  arm=$1
  mount_arg=()
  if [[ "$arm" == candidate ]]; then
    source_path=$(<"$out/sglang_source_path.txt")
    mount_arg=(-v "$remote/source/sglang:$source_path")
  fi
  "${ssh_cmd[@]}" "sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true"
  "${ssh_cmd[@]}" "sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host -v $remote:/work ${mount_arg[*]} $image python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup"
  for attempt in $(seq 1 120); do
    if "${ssh_cmd[@]}" 'curl -fsS http://127.0.0.1:30000/v1/models' >"$out/${arm}-models.json" 2>"$out/${arm}-models.stderr.log"; then return 0; fi
    sleep 5
  done
  "${ssh_cmd[@]}" 'sudo docker logs gemma-attention-endpoint' >"$out/${arm}-server.log" 2>&1 || true
  fail "${arm}_support_terminal" server_not_ready
}

event stock_server_start
launch_server stock
event stock_c32_start
"${ssh_cmd[@]}" "rm -rf $remote/stock-c32; sudo docker exec gemma-attention-endpoint python3 /work/workspace/c32_endpoint_runner.py --trace /work/workspace/TRACE_PACKET.json --output /work/stock-c32 --arm stock"
"${ssh_cmd[@]}" "cd $remote && tar -czf stock-c32.tar.gz stock-c32; sudo docker logs gemma-attention-endpoint >stock-server.log 2>&1"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/stock-c32.tar.gz" "$out/stock-c32.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/stock-c32/TERMINAL.json" "$out/STOCK_TERMINAL.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/stock-server.log" "$out/stock-server.log"
event stock_c32_complete
touch "$out/READY_FOR_CANDIDATE"

while [[ ! -f "$project/candidate.patch" ]]; do
  if (( $(date +%s) >= deadline_epoch - 900 )); then fail source_terminal candidate_patch_deadline; fi
  sleep 5
done
event candidate_patch_start
"${scp_cmd[@]}" "$project/candidate.patch" "glmrunner@$ip:$remote/candidate.patch"
"${ssh_cmd[@]}" "cd $remote/source && patch -p1 < $remote/candidate.patch && sha256sum $remote/candidate.patch >$remote/candidate-patch.sha256"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/candidate-patch.sha256" "$out/candidate-patch.sha256"
event candidate_server_start
launch_server candidate
  "${ssh_cmd[@]}" "sudo docker exec gemma-attention-endpoint python3 /work/workspace/numerical_oracle.py --output /work/numerical-oracle.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/numerical-oracle.json" "$out/NUMERICAL_ORACLE.json"
event candidate_c32_start
"${ssh_cmd[@]}" "rm -rf $remote/candidate-c32; sudo docker exec gemma-attention-endpoint python3 /work/workspace/c32_endpoint_runner.py --trace /work/workspace/TRACE_PACKET.json --output /work/candidate-c32 --arm candidate"
"${ssh_cmd[@]}" "cd $remote && tar -czf candidate-c32.tar.gz candidate-c32; sudo docker logs gemma-attention-endpoint >candidate-server.log 2>&1"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/candidate-c32.tar.gz" "$out/candidate-c32.tar.gz"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/candidate-c32/TERMINAL.json" "$out/CANDIDATE_TERMINAL.json"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/candidate-server.log" "$out/candidate-server.log"
event candidate_c32_complete

python3 "$project/reconcile_terminal.py" --artifact-root "$out"
event terminal_complete
