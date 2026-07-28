#!/usr/bin/env bash
# Bounded outer owner for a content-bound repair.  It deliberately does not
# reconstruct the missing workload or touch resident guest inputs.
set -euo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h100_v0515_ngram_verify_launch_pipeline
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
pool_root=/root/workspace
deadline=2026-07-25T17:20:00Z
diagnostic='resident_workload_integrity_boundary: strict read-only guest search found neither /home/glmrunner/gemma4-h100-packed-endpoint/fresh_workload.jsonl nor FRESH_WORKLOAD.json, so required index/hash/novelty verification is impossible; binding prohibits reconstruction or mutation; no endpoint request, stock arm, or candidate arm was submitted'

heartbeat() {
  while :; do
    PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
      --lab "$lab" heartbeat \
      --project gemma4_h100_v0515_ngram_verify_launch_pipeline || true
    sleep 45
  done
}

heartbeat &
heartbeat_pid=$!
cleanup() {
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$pool_root"
/root/workspace/research/factory/tools/repair-handshake ready \
  --root "$project" \
  --deadline "$deadline" \
  --failure-kind resident_workload_binding_precondition_invalid \
  --diagnostic "$diagnostic" \
  --retry-scope 'director-rebind-required: provide a new content-addressed workload admission or explicitly authorize construction; retain current claim and resident checkpoint/packet/runtime unchanged'

# This is a repair handshake, not an endpoint-preparation sleep.  The loop
# keeps the current pool claim alive until a director-supplied rebind can be
# handled or the absolute repair deadline forces director disposition.
while :; do
  set +e
  /root/workspace/research/factory/tools/repair-handshake wait \
    --root "$project" --poll-seconds 60
  wait_status=$?
  set -e
  if [ "$wait_status" -eq 0 ]; then
    printf '%s repair_request_observed; retained claim remains heartbeating pending director rebind\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    sleep 60
    continue
  fi
  printf '%s repair_deadline_or_handshake_boundary status=%s; retaining claim for director disposition\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$wait_status"
  sleep 60
done
