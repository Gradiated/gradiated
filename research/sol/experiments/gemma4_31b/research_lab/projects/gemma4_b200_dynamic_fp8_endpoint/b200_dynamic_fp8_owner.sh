#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_dynamic_fp8_endpoint
LAB=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
BENCH=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
OUT=$PROJECT/artifacts/b200-dynamic-fp8-20260728t1515z
DEADLINE=2026-07-28T16:35:00Z
IMAGE=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
mkdir -p "$OUT"

phase() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$OUT/OWNER_PROGRESS.log"; }
heartbeat() { PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" heartbeat --project gemma4_b200_dynamic_fp8_endpoint --bench "$BENCH" >>"$OUT/heartbeat.log" 2>&1; }
while true; do heartbeat; sleep 45; done &
HEARTBEAT=$!
trap 'kill "$HEARTBEAT" 2>/dev/null || true' EXIT

repair() {
  phase "repair:$1"
  printf '%s\n' "$2" >"$OUT/REPAIR_DIAGNOSTIC.txt"
  /root/workspace/research/factory/tools/repair-handshake ready --root "$OUT" --repair-id "b200-dynamic-fp8-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$1" --diagnostic "$OUT/REPAIR_DIAGNOSTIC.txt" --retry-scope endpoint_consumer --deadline "$DEADLINE" >>"$OUT/repair.log" 2>&1 || true
  while [ "$(date -u +%s)" -lt "$(date -u -d "$DEADLINE" +%s)" ]; do
    request=$(find "$OUT/.repair-handshakes" -name REPAIR_REQUEST.json -type f -print -quit 2>/dev/null || true)
    if [ -n "$request" ]; then phase repair_request_received; exit 75; fi
    sleep 30
  done
  exit 75
}

row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" show --bench "$BENCH") || exit 70
eval "$(ROW="$row" python3 - <<'PY'
import json, os, shlex
r=json.loads(os.environ['ROW'])['resource']
for key, value in {'HOST':r['public_ipv4'],'USER':r['ssh_user'],'KEY':r['identity_file'],'KNOWN':r['known_hosts_namespace']}.items(): print(f'{key}={shlex.quote(value)}')
PY
)"
[ -f "$KEY" ] || repair identity "missing inventory identity file"
REMOTE=/home/$USER/b200-dynamic-fp8-20260728t1515z
RETAINED=/home/$USER/b200-nvfp4-gemma4-endpoint-v2-20260728t1323z/bf16-source
ssh_cmd=(ssh -n -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST")

phase pre_science_remote_setup
"${ssh_cmd[@]}" "test -f '$RETAINED/model.safetensors.index.json' && mkdir -p '$REMOTE'" >"$OUT/remote-setup.stdout" 2>"$OUT/remote-setup.stderr" || repair retained_checkpoint "$(tail -80 "$OUT/remote-setup.stderr")"
scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PROJECT/dynamic_fp8_endpoint_driver.py" "$PROJECT/run_endpoint_pair.sh" "$USER@$HOST:$REMOTE/" >>"$OUT/remote-setup.stdout" 2>>"$OUT/remote-setup.stderr" || repair packet_copy "$(tail -80 "$OUT/remote-setup.stderr")"
"${ssh_cmd[@]}" "chmod 0755 '$REMOTE/run_endpoint_pair.sh'; ln -sfn dynamic_fp8_endpoint_driver.py '$REMOTE/endpoint_driver.py'; ln -sfn '$RETAINED' '$REMOTE/checkpoint'" >>"$OUT/remote-setup.stdout" 2>>"$OUT/remote-setup.stderr" || repair packet_finalize "$(tail -80 "$OUT/remote-setup.stderr")"

phase endpoint_execution
"${ssh_cmd[@]}" "cd '$REMOTE' && sudo -n bash run_endpoint_pair.sh '$REMOTE' '$IMAGE'" >"$OUT/worker.stdout" 2>"$OUT/worker.stderr" || repair endpoint_worker "$(tail -120 "$OUT/worker.stderr")"
phase terminal_retrieval
mkdir -p "$OUT/remote-artifacts"
scp -r -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST:$REMOTE/artifacts/." "$OUT/remote-artifacts/" >>"$OUT/retrieve.stdout" 2>>"$OUT/retrieve.stderr" || repair terminal_retrieval "$(tail -120 "$OUT/retrieve.stderr")"
python3 - "$OUT/remote-artifacts/PAIR_TERMINAL.json" <<'PY' || repair terminal_validation invalid_pair_terminal
import json, sys
x=json.load(open(sys.argv[1])); assert x['classification'] in {'dynamic_fp8_endpoint_pair','endpoint_pair_invalid'}
PY
phase scientific_terminal
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" release --project gemma4_b200_dynamic_fp8_endpoint --bench "$BENCH" --condition ready >>"$OUT/release.log" 2>&1
