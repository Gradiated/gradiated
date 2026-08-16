#!/usr/bin/env bash
set -uo pipefail

project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_modelopt_fp8_export_endpoint
lab=/root/workspace/research/lab/experiments/gemma4_31b/research_lab
remote=/home/glmrunner/gemma-attention-endpoint
run_id=modelopt-fp8-export-c32-20260718t1900z
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
  condition=maintenance
  if [[ -s "$out/TERMINAL.json" ]]; then condition=ready; fi
  python3 - "$out/TERMINAL.json" "$out/BENCH_CONTENTS.json" <<'PY'
import json,pathlib,sys
path=pathlib.Path(sys.argv[1]); terminal=json.loads(path.read_text()) if path.exists() else {}
success=terminal.get("classification") in ("promote_h200_export","retain_incremental","negative")
value={"project":"gemma4_modelopt_fp8_export_endpoint","model":"google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4","image":"Pinned SGLang v0.5.12 sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a remains resident.","checkpoint":"Exact eight-file 62,578,655,208-byte BF16 checkpoint remains at /home/glmrunner/gemma-attention-endpoint/checkpoint.","runtime":("Official ModelOpt FP8 export consumed by pinned SGLang; terminal "+str(terminal.get("classification"))) if success else ("ModelOpt export workflow terminal "+str(terminal.get("classification","owner_failure"))),"artifacts":"Project artifacts and export manifest retrieved under projects/gemma4_modelopt_fp8_export_endpoint/artifacts/modelopt-fp8-export-c32-20260718t1900z/.","export":terminal.get("export_path","No validated content-addressed export recorded."),"server_state":terminal.get("server_state","No healthy endpoint state proven; inspect project terminal before reuse.")}
pathlib.Path(sys.argv[2]).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
PY
  python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_modelopt_fp8_export_endpoint --condition "$condition" --contents "$out/BENCH_CONTENTS.json" >"$out/bench-release.json" 2>"$out/bench-release.stderr" || true
}
cleanup() {
  if [[ -n "$heartbeat_pid" ]]; then kill "$heartbeat_pid" >/dev/null 2>&1 || true; wait "$heartbeat_pid" >/dev/null 2>&1 || true; fi
  release_claim
}
trap cleanup EXIT

sha256sum "$project/remote_run.sh" "$project/validate_export.py" "$project/official_local_path_adapter.py" >"$out/local-input-sha256.txt"
sha256sum /root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py >>"$out/local-input-sha256.txt"
"${ssh_cmd[@]}" "mkdir -p $remote/workspace" >"$out/ssh-preflight.log" 2>&1 || exit 51
"${scp_cmd[@]}" "$project/remote_run.sh" "$project/validate_export.py" "$project/official_local_path_adapter.py" /root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_background_serving_frontier/exact_mix_runner.py "glmrunner@$ip:$remote/workspace/" >"$out/scp-inputs.log" 2>&1 || exit 52

(
  while true; do
    python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_modelopt_fp8_export_endpoint >>"$out/bench-heartbeats.jsonl" 2>>"$out/bench-heartbeats.stderr" || true
    sleep 300
  done
) &
heartbeat_pid=$!

set +e
timeout --signal=TERM 6780 "${ssh_cmd[@]}" "bash $remote/workspace/remote_run.sh" >"$out/remote-owner.stdout" 2>"$out/remote-owner.stderr"
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
