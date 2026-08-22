#!/usr/bin/env bash
set -u -o pipefail

PROJECT=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/b200_nvfp4_gemma4_endpoint
LAB=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
BENCH=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
OUT=$PROJECT/artifacts/b200-nvfp4-endpoint-v2-20260728t1323z
PACKET=$PROJECT/artifacts/native-nvfp4-endpoint-packet-v1
PRODUCER=$PROJECT/producer_v2
DEADLINE=2026-07-28T16:10:00Z
IMAGE=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
REPAIR_SCOPE=${REPAIR_SCOPE:-full}
mkdir -p "$OUT"

# The pool is the sole source of the mutable guest connection record.
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" show --bench "$BENCH") || exit 70
eval "$(ROW="$row" python3 - <<'PY'
import json, os, shlex
r=json.loads(os.environ['ROW'])['resource']
for key, value in {'HOST':r['public_ipv4'],'USER':r['ssh_user'],'KEY':r['identity_file'],'KNOWN':r['known_hosts_namespace']}.items():
    print(f'{key}={shlex.quote(value)}')
PY
)"
REMOTE=/home/$USER/b200-nvfp4-gemma4-endpoint-v2-20260728t1323z
ssh_cmd=(ssh -n -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST")

phase() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$OUT/OWNER_PROGRESS.log"; }
heartbeat() { PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" heartbeat --project b200_nvfp4_gemma4_endpoint --bench "$BENCH" >>"$OUT/heartbeat.log" 2>&1; }
while true; do heartbeat; sleep 45; done &
HEARTBEAT=$!
trap 'kill "$HEARTBEAT" 2>/dev/null || true' EXIT
repair() {
  phase "repair:$1"
  printf '%s\n' "$2" >"$OUT/REPAIR_DIAGNOSTIC.txt"
  /root/workspace/research/factory/tools/repair-handshake ready --root "$OUT" --repair-id "b200-nvfp4-v2-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$1" --diagnostic "$OUT/REPAIR_DIAGNOSTIC.txt" --retry-scope stage_or_consumer --deadline "$DEADLINE" >>"$OUT/repair.log" 2>&1 || true
  # Keep the continuous claim owner heartbeating for the hash-bound repair handoff.
  while [ "$(date -u +%s)" -lt "$(date -u -d "$DEADLINE" +%s)" ]; do
    find "$OUT/.repair-handshakes" -name REPAIR_REQUEST.json -type f -print -quit 2>/dev/null | grep -q . && { phase repair_request_received; break; }
    sleep 30
  done
  exit 75
}
run() { "$@" || repair "$1" "command failed: $*"; }

phase pre_science_remote_root
if [ "$REPAIR_SCOPE" = producer_install ] || [ "$REPAIR_SCOPE" = calibration_adapter ] || [ "$REPAIR_SCOPE" = calibration_length ]; then
  phase "${REPAIR_SCOPE}_resume"
else
run "${ssh_cmd[@]}" "mkdir -p '$REMOTE/inputs/bf16-source' '$REMOTE/packet' '$REMOTE/producer/producer-v2' '$REMOTE/artifacts'"
phase packet_and_calibration_stage
scp -r -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PACKET/." "$USER@$HOST:$REMOTE/packet/" >"$OUT/packet-copy.stdout" 2>"$OUT/packet-copy.stderr" || repair packet_copy "$(cat "$OUT/packet-copy.stderr")"
scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PROJECT/inputs/calibration.jsonl" "$USER@$HOST:$REMOTE/calibration.jsonl" >>"$OUT/packet-copy.stdout" 2>>"$OUT/packet-copy.stderr" || repair calibration_copy "$(cat "$OUT/packet-copy.stderr")"
"${ssh_cmd[@]}" "cd '$REMOTE/packet' && python3 -c 'import hashlib,json,pathlib; m=json.load(open(\"PACKET_MANIFEST.json\")); assert hashlib.sha256(pathlib.Path(\"PACKET_MANIFEST.json\").read_bytes()).hexdigest()==\"707b20f442ade965a9970d3338d8b608946cf4e3168fa7257111963b38f0b116\"; [(_ for _ in ()).throw(SystemExit(k)) for k,v in m[\"files\"].items() if k!=\"PACKET_MANIFEST.json\" and hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v]'" >>"$OUT/packet-copy.stdout" 2>>"$OUT/packet-copy.stderr" || repair packet_verify "$(cat "$OUT/packet-copy.stderr")"

phase checkpoint_reconcile
while read -r sha name; do
  local_file="$PROJECT/inputs/bf16-source/$name"; remote_file="$REMOTE/inputs/bf16-source/$name"
  observed=$("${ssh_cmd[@]}" "test -f '$remote_file' && sha256sum '$remote_file' | cut -d' ' -f1 || true" 2>>"$OUT/checkpoint.stderr" || true)
  [ "$observed" = "$sha" ] && continue
  if ! scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$local_file" "$USER@$HOST:$remote_file.partial" >>"$OUT/checkpoint-copy.stdout" 2>>"$OUT/checkpoint.stderr"; then
    repair checkpoint_copy "$(tail -40 "$OUT/checkpoint.stderr")"
  fi
  if ! "${ssh_cmd[@]}" "sha256sum '$remote_file.partial' | grep -q '^$sha ' && mv '$remote_file.partial' '$remote_file'" >>"$OUT/checkpoint-copy.stdout" 2>>"$OUT/checkpoint.stderr"; then
    repair checkpoint_verify "$(tail -40 "$OUT/checkpoint.stderr")"
  fi
done <"$PROJECT/inputs/bf16-source/model-files.sha256"
for name in config.json tokenizer.json tokenizer_config.json chat_template.jinja processor_config.json; do
  scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PROJECT/inputs/bf16-source/$name" "$USER@$HOST:$REMOTE/inputs/bf16-source/$name" >>"$OUT/checkpoint-copy.stdout" 2>>"$OUT/checkpoint.stderr" || repair checkpoint_support_copy "$(tail -40 "$OUT/checkpoint.stderr")"
done
"${ssh_cmd[@]}" "mv '$REMOTE/inputs/bf16-source' '$REMOTE/bf16-source'" 2>>"$OUT/checkpoint.stderr" || repair checkpoint_finalize "$(tail -40 "$OUT/checkpoint.stderr")"
fi

phase producer_stage
if [ "$REPAIR_SCOPE" = calibration_adapter ] || [ "$REPAIR_SCOPE" = calibration_length ]; then
  scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PRODUCER/llmcompressor_cli_adapter.py" "$USER@$HOST:$REMOTE/producer/producer-v2/llmcompressor_cli_adapter.py" >>"$OUT/producer.stdout" 2>>"$OUT/producer.stderr" || repair calibration_adapter_copy "$(tail -40 "$OUT/producer.stderr")"
  "${ssh_cmd[@]}" "sudo -n install -m 0644 '$REMOTE/producer/producer-v2/llmcompressor_cli_adapter.py' '$REMOTE/producer/producer-v2/venv/lib/python3.12/site-packages/llmcompressor/__main__.py'" >>"$OUT/producer.stdout" 2>>"$OUT/producer.stderr" || repair calibration_adapter_install "$(tail -40 "$OUT/producer.stderr")"
else
scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PRODUCER/requirements.runtime.lock" "$USER@$HOST:$REMOTE/producer/producer-v2/requirements.runtime.lock" >>"$OUT/producer.stdout" 2>>"$OUT/producer.stderr" || repair runtime_lock_copy "$(tail -40 "$OUT/producer.stderr")"
"${ssh_cmd[@]}" "set -e; p='$REMOTE/producer/producer-v2'; test -x \"\$p/venv/bin/python\" || sudo -n docker run --rm --entrypoint python3 -v '$REMOTE:$REMOTE' '$IMAGE' -m venv \"\$p/venv\"; sudo -n docker run --rm --entrypoint \"\$p/venv/bin/python\" -v '$REMOTE:$REMOTE' '$IMAGE' -m pip install --no-index --find-links \"\$p/wheels\" --requirement \"\$p/requirements.runtime.lock\"; sudo -n install -m 0644 \"\$p/llmcompressor_cli_adapter.py\" \"\$p/venv/lib/python3.12/site-packages/llmcompressor/__main__.py\"" >>"$OUT/producer.stdout" 2>>"$OUT/producer.stderr" || repair producer_install "$(tail -80 "$OUT/producer.stderr")"
fi

phase conversion
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --entrypoint '$REMOTE/producer/producer-v2/venv/bin/python' -v '$REMOTE:$REMOTE' '$IMAGE' '$REMOTE/packet/convert_native_nvfp4.py' --source '$REMOTE/bf16-source' --output '$REMOTE/nvfp4-checkpoint' --calibration '$REMOTE/calibration.jsonl'" >"$OUT/conversion.stdout" 2>"$OUT/conversion.stderr" || repair conversion "$(tail -100 "$OUT/conversion.stderr")"
phase bf16_control
"${ssh_cmd[@]}" "cd '$REMOTE' && sudo -n bash packet/run_endpoint.sh '$REMOTE' control" >"$OUT/control.stdout" 2>"$OUT/control.stderr" || repair control "$(tail -100 "$OUT/control.stderr")"
phase nvfp4_candidate
"${ssh_cmd[@]}" "cd '$REMOTE' && sudo -n bash packet/run_endpoint.sh '$REMOTE' candidate" >"$OUT/candidate.stdout" 2>"$OUT/candidate.stderr" || repair candidate "$(tail -100 "$OUT/candidate.stderr")"
phase retrieve_validate_terminals
scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST:$REMOTE/result-control/TERMINAL.json" "$OUT/CONTROL_TERMINAL.json" || repair terminal_retrieval control
scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST:$REMOTE/result-candidate/TERMINAL.json" "$OUT/CANDIDATE_TERMINAL.json" || repair terminal_retrieval candidate
python3 - "$OUT/CONTROL_TERMINAL.json" "$OUT/CANDIDATE_TERMINAL.json" <<'PY' || repair terminal_validation invalid
import json, sys
for p in sys.argv[1:]:
    x=json.load(open(p)); assert x, p
PY
phase validated_terminal_release
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" release --project b200_nvfp4_gemma4_endpoint --bench "$BENCH" --condition ready >>"$OUT/release.log" 2>&1
