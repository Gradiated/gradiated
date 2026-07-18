#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_global_head_dim256_attention_distillation
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
out=$project/artifacts/head256-distill-20260718t2311z-r1
remote=/home/glmrunner/gemma-attention-endpoint
run_id=head256-distill-20260718t2311z-r1
ip=195.242.30.125
key=/root/.config/nebius/glm-campaign/ssh_ed25519
export PYTHONPATH=/root/workspace/research/factory/src
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts "glmrunner@$ip")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
heartbeat_pid=
released=0
mkdir -p "$out"

release_claim() {
  (( released == 0 )) || return
  released=1
  python3 - "$out/BENCH_CONTENTS.json" "$out/$run_id/OWNER_TERMINAL.json" <<'PY'
import json,pathlib,sys
t=json.loads(pathlib.Path(sys.argv[2]).read_text()) if pathlib.Path(sys.argv[2]).exists() else {}
contents={'project':'gemma4_global_head_dim256_attention_distillation','model':'google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4','image':'Pinned SGLang v0.5.12 image and Triton cache remain resident.','checkpoint':'Exact eight-file BF16 checkpoint remains unchanged and read-only at /home/glmrunner/gemma-attention-endpoint/checkpoint.','runtime':'One frozen head-256 attention distillation candidate terminal: '+str(t.get('classification','owner_failure')),'artifacts':'Retrieved under projects/gemma4_global_head_dim256_attention_distillation/artifacts/head256-distill-20260718t2311z-r1/.','server_state':'Distilled candidate server retained if startup reached coherence; otherwise image, checkpoint, and caches retained.','export':'Content-addressed overlay retained remotely under /home/glmrunner/gemma-attention-endpoint/head256-distill-20260718t2311z-r1/distillation/overlay.safetensors when training completed.'}
pathlib.Path(sys.argv[1]).write_text(json.dumps(contents,indent=2,sort_keys=True)+'\n')
PY
  python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_global_head_dim256_attention_distillation --condition ready --contents "$out/BENCH_CONTENTS.json" > "$out/bench-release.json" 2> "$out/bench-release.stderr" || true
}

cleanup() {
  [[ -z "$heartbeat_pid" ]] || { kill "$heartbeat_pid" >/dev/null 2>&1 || true; wait "$heartbeat_pid" >/dev/null 2>&1 || true; }
  release_claim
}
trap cleanup EXIT

(while sleep 120; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_global_head_dim256_attention_distillation >> "$out/bench-heartbeats.jsonl" 2>> "$out/bench-heartbeats.stderr" || exit; done) &
heartbeat_pid=$!
"${scp_cmd[@]}" "$project/remote_run.sh" "glmrunner@$ip:$remote/workspace/head256-distill-bound-20260718t2311z-r1/remote_run.sh" > "$out/scp-remote-run.log" 2>&1
set +e
timeout --signal=TERM 4500 "${ssh_cmd[@]}" "bash $remote/workspace/head256-distill-bound-20260718t2311z-r1/remote_run.sh" > "$out/remote-owner.stdout" 2> "$out/remote-owner.stderr"
remote_exit=$?
set -e
printf '%s\n' "$remote_exit" > "$out/remote-owner.exit"
"${scp_cmd[@]}" "glmrunner@$ip:$remote/$run_id.tar.gz" "$out/artifacts.tar.gz" > "$out/scp-artifacts.log" 2>&1 || true
if [[ -s "$out/artifacts.tar.gz" ]]; then tar -xzf "$out/artifacts.tar.gz" -C "$out"; fi
exit "$remote_exit"
