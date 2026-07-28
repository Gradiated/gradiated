#!/usr/bin/env bash
set -euo pipefail
proj=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_ngram_decode_equivalent_production_validation
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
artifact="${QUALITY_ARTIFACT:-$proj/artifacts/quality-20260724t1051z}"
packet="${QUALITY_PACKET:-$proj/packets/quality-20260724t1049z}"
ip=89.169.99.101
remote=/home/glmrunner/gemma4-ngram-production-quality
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
mkdir -p "$artifact"
heartbeat() { while sleep 45; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_h200_ngram_decode_equivalent_production_validation >>"$artifact/heartbeats.jsonl" 2>>"$artifact/heartbeats.stderr" || true; done; }
heartbeat & hb=$!
cleanup() { kill "$hb" >/dev/null 2>&1 || true; wait "$hb" >/dev/null 2>&1 || true; }
trap cleanup EXIT
ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$known" "glmrunner@$ip")
scp_to=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$known")
scp_from=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$known")
"${ssh_cmd[@]}" "set -e; mkdir -p $remote/packet $remote/out; ln -sfn /home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint $remote/checkpoint; rm -rf $remote/packet/*; rm -rf $remote/out/*" >"$artifact/stage.stdout" 2>"$artifact/stage.stderr"
"${scp_to[@]}" "$packet/remote_quality_capture.py" "$packet/endpoint_entrypoint.py" "$packet/gpqa_diamond_requests.jsonl" "$packet/taubench_requests.jsonl" "glmrunner@$ip:$remote/packet/"
"${scp_to[@]}" "$packet/SHA256SUMS" "glmrunner@$ip:$remote/packet/SHA256SUMS"
"${ssh_cmd[@]}" "cd $remote/packet; sha256sum -c SHA256SUMS | grep -E '(gpqa|taubench|endpoint|remote)'" >"$artifact/stage-verify.stdout" 2>"$artifact/stage-verify.stderr"
set +e
"${ssh_cmd[@]}" "timeout --signal=TERM 12600 python3 $remote/packet/remote_quality_capture.py" >"$artifact/worker.stdout" 2>"$artifact/worker.stderr"
rc=$?
set -e
"${scp_from[@]}" -r "glmrunner@$ip:$remote/out" "$artifact/retrieved" >"$artifact/retrieve.stdout" 2>"$artifact/retrieve.stderr"
if [[ -f "$artifact/retrieved/TERMINAL.json" ]]; then
  cp "$artifact/retrieved/TERMINAL.json" "$artifact/TERMINAL.json"
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_h200_ngram_decode_equivalent_production_validation --condition ready --contents "$proj/BENCH_CONTENTS.json" >"$artifact/release.json" 2>"$artifact/release.stderr" || true
  exit "$rc"
fi
printf '{"classification":"remote_consumer_or_retrieval_defect","worker_exit_code":%s,"repair_deadline_utc":"2026-07-24T14:30:00Z"}\n' "$rc" >"$proj/REPAIR_READY.json"
exit "$rc"
