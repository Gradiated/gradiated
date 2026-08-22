#!/usr/bin/env bash
set -Eeuo pipefail
p=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_runtime_codesign; lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab; bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j; image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79; o=$OWNER_ARTIFACT_ROOT; mkdir -p "$o/r"
hb(){ while sleep 15; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_runtime_codesign --bench "$bench" >>"$o/heartbeat.log" 2>&1 || true; done; }; hb & h=$!; trap 'kill $h 2>/dev/null || true' EXIT
s=(ssh -n -i /root/.config/nebius/glm-campaign/ssh_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts glmrunner@46.243.147.55); c=(scp -p -i /root/.config/nebius/glm-campaign/ssh_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts)
"${s[@]}" "mkdir -p '$OWNER_REMOTE_ROOT'"
"${c[@]}" "$p/candidate/run_b200_fp8_block_pair.py" "$p/PRECLAIM_B200_FP8_BLOCK_PAIR_TERMINAL.json" "glmrunner@46.243.147.55:$OWNER_REMOTE_ROOT/"
set +e; "${s[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$OWNER_REMOTE_ROOT:/work' '$image' /work/run_b200_fp8_block_pair.py --output /work/TERMINAL.json" >"$o/stdout.log" 2>"$o/stderr.log"; rc=$?; set -e
"${c[@]}" "glmrunner@46.243.147.55:$OWNER_REMOTE_ROOT/TERMINAL.json" "$o/r/" || true
if [[ -f "$o/r/TERMINAL.json" ]]; then cp "$o/r/TERMINAL.json" "$p/B200_FP8_BLOCK_PAIR_TERMINAL.json"; fi
if [[ $rc -ne 0 || ! -f "$o/r/TERMINAL.json" ]] || ! jq -e '.classification=="interpretable_block_scaled_linear_pair" and (.rows|length)==18' "$o/r/TERMINAL.json" >/dev/null; then
  printf '{"classification":"recoverable_block_consumer_defect","repair_deadline_utc":"2026-07-28T22:18:00Z"}\n' > "$o/REPAIR_READY.json"
  while [[ "$(date -u +%s)" -lt "$(date -u -d 2026-07-28T22:18:00Z +%s)" ]]; do sleep 10; done
  exit 0
fi
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_runtime_codesign --bench "$bench" --condition ready
