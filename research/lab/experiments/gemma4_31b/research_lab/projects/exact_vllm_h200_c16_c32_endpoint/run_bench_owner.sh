#!/usr/bin/env bash
set -uo pipefail

project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/exact_vllm_h200_c16_c32_endpoint
lab=/root/workspace/research/lab/experiments/gemma4_31b/research_lab
remote=/home/glmrunner/gemma-attention-endpoint
run_id=vllm-c32-warm-bench-20260718t1912z
out="$project/artifacts/$run_id"
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
export PYTHONPATH=/root/workspace/research/factory/src
mkdir -p "$out"
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)

heartbeat_pid=
released=0
release_claim() {
  if (( released == 1 )); then return; fi
  released=1
  condition=ready
  python3 - "$out/TERMINAL.json" "$out/BENCH_CONTENTS.json" <<'PY'
import json,pathlib,sys
path=pathlib.Path(sys.argv[1]); terminal=json.loads(path.read_text()) if path.exists() else {}
value={"project":"exact_vllm_h200_c16_c32_endpoint","model":"google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4","image":"Pinned vLLM Gemma4 image pulled if absent.","checkpoint":"Exact eight-file BF16 checkpoint remains at /home/glmrunner/gemma-attention-endpoint/checkpoint.","runtime":"vLLM c32 terminal "+str(terminal.get("classification","owner_failure")),"artifacts":"Retrieved under projects/exact_vllm_h200_c16_c32_endpoint/artifacts/vllm-c32-warm-bench-20260718t1912z/.","server_state":terminal.get("server_state","inspect terminal")}
pathlib.Path(sys.argv[2]).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
PY
  python3 -m grad_research.gpu_pool --lab "$lab" release --project exact_vllm_h200_c16_c32_endpoint --condition "$condition" --contents "$out/BENCH_CONTENTS.json" >"$out/bench-release.json" 2>"$out/bench-release.stderr" || true
}
cleanup() {
  if [[ -n "$heartbeat_pid" ]]; then kill "$heartbeat_pid" >/dev/null 2>&1 || true; wait "$heartbeat_pid" >/dev/null 2>&1 || true; fi
  release_claim
}
trap cleanup EXIT

sha256sum "$project/remote_vllm_c32.sh" "$project/vllm_c32_consumer.py" /root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py >"$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "mkdir -p $remote/workspace" >"$out/ssh-preflight.log" 2>&1 || exit 51
"${scp_cmd[@]}" "$project/remote_vllm_c32.sh" "$project/vllm_c32_consumer.py" /root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py "glmrunner@$ip:$remote/workspace/" >"$out/scp-inputs.log" 2>&1 || exit 52

(
  while true; do
    python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project exact_vllm_h200_c16_c32_endpoint >>"$out/bench-heartbeats.jsonl" 2>>"$out/bench-heartbeats.stderr" || true
    sleep 300
  done
) &
heartbeat_pid=$!

set +e
timeout --signal=TERM 5100 "${ssh_cmd[@]}" "bash $remote/workspace/remote_vllm_c32.sh" >"$out/remote-owner.stdout" 2>"$out/remote-owner.stderr"
remote_exit=$?
set -e
printf '%s\n' "$remote_exit" >"$out/remote-owner.exit"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id/artifacts.tar.gz" "$out/artifacts.tar.gz" >"$out/scp-artifacts.log" 2>&1 || true
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id/artifacts.tar.gz.sha256" "$out/artifacts.tar.gz.sha256" >>"$out/scp-artifacts.log" 2>&1 || true
if [[ -s "$out/artifacts.tar.gz" ]]; then
  tar -xzf "$out/artifacts.tar.gz" -C "$out"
  cp "$out/artifacts/TERMINAL.json" "$out/TERMINAL.json" 2>/dev/null || true
fi
release_claim
exit "$remote_exit"
