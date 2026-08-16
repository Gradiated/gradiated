#!/usr/bin/env bash
set -Eeuo pipefail

project="$(cd "$(dirname "$0")" && pwd)"
lab="$(cd "$project/../.." && pwd)"
stamp="$(date -u +%Y%m%dt%H%M%SZ)"
out="$project/artifacts/candidate-only-owner-$stamp"
stage="$out/packet"
remote="/home/glmrunner/gemma4-dflash/candidate-only/$stamp"
host="glmrunner@89.169.109.132"
key="/root/.config/nebius/glm-campaign/ssh_ed25519"
known="/root/.config/nebius/glm-campaign/known_hosts"
archive="$project/artifacts/request-state-capture-rebinding-20260725t2309z/REQUEST_STATE_CAPTURE_PACKET.tar"
exact="$project/artifacts/request-ownership-observer-repair-20260725T234315Z/packet/3407231bdcc05a950d2f50cee02936a8f1f785ff32336b40b1760eb205539174"
ar="$project/artifacts/request-state-capture-owner-20260725T232227Z/retrieved-final/results/ar-c32/TERMINAL.json"
mkdir -p "$out"

ssh_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20 "$host")
scp_cmd=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20)

hb() { while sleep 30; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_h200_dflash_endpoint >> "$out/heartbeat.log" 2>&1 || true; done; }
hb & hb_pid=$!
cleanup() { kill "$hb_pid" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$stage"
tar -xf "$archive" -C "$stage"
cp "$exact/sitecustomize.py" "$stage/request_state_capture_sitecustomize.py"
cp "$exact/request_state_observer.py" "$stage/request_state_observer.py"
if test -f "$project/candidate_sitecustomize_repair.py"; then
  cp "$project/candidate_sitecustomize_repair.py" "$stage/request_state_capture_sitecustomize.py"
fi
(cd "$stage" && sha256sum $(find . -type f -not -name PACKET.sha256 -printf '%P\n' | sort) > PACKET.sha256)
sha256sum "$exact/MANIFEST.json" > "$out/consumed-packet-manifest.sha256"
sha256sum "$archive" > "$out/execution-archive.sha256"
printf '{"arm":"dflash-depth4-c32","ar_replayed":false,"packet_identity_sha256":"3407231bdcc05a950d2f50cee02936a8f1f785ff32336b40b1760eb205539174"}\n' > "$out/PRE_SCIENCE_BINDING.json"

"${ssh_cmd[@]}" "mkdir -p '$remote'"
"${scp_cmd[@]}" -r "$stage/." "$host:$remote/"
"${ssh_cmd[@]}" "bash '$remote/remote_request_state_capture.sh' '$remote' '$remote' dflash" > "$out/remote.stdout" 2> "$out/remote.stderr" || worker_rc=$?
worker_rc=${worker_rc:-0}

mkdir -p "$out/retrieved"
"${scp_cmd[@]}" -r "$host:$remote/." "$out/retrieved/" > "$out/retrieve.stdout" 2> "$out/retrieve.stderr" || retrieve_rc=$?
retrieve_rc=${retrieve_rc:-0}
printf '{"worker_exit_code":%d,"retrieve_exit_code":%d,"candidate_science_marker":%s}\n' "$worker_rc" "$retrieve_rc" "$(test -f "$out/retrieved/dflash-depth4-c32.SCIENCE_STARTED.json" && echo true || echo false)" > "$out/REMOTE_RETRIEVAL_TERMINAL.json"

if test -s "$out/retrieved/results/dflash-depth4-c32/TERMINAL.json" && test -s "$out/retrieved/states/dflash-depth4-c32.jsonl" && test ! -e "$out/retrieved/states/dflash-depth4-c32.observer-error"; then
  python3 "$project/summarize_candidate_request_state_capture.py" \
    --ar-terminal "$ar" \
    --candidate-terminal "$out/retrieved/results/dflash-depth4-c32/TERMINAL.json" \
    --candidate-states "$out/retrieved/states/dflash-depth4-c32.jsonl" \
    --result "$out/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_RESULT.json" \
    --terminal "$out/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_TERMINAL.json" > "$out/summarize.stdout" 2> "$out/summarize.stderr" || summarize_rc=$?
  summarize_rc=${summarize_rc:-0}
else
  summarize_rc=79
fi

python3 - "$out/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_TERMINAL.json" "$out/REMOTE_RETRIEVAL_TERMINAL.json" "$worker_rc" "$retrieve_rc" "$summarize_rc" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
value=json.loads(p.read_text()) if p.is_file() else {}
value.update({"worker_exit_code":int(sys.argv[3]),"retrieve_exit_code":int(sys.argv[4]),"summarize_exit_code":int(sys.argv[5]),"ar_producer_replayed":False,"candidate_only_packet_identity_sha256":"3407231bdcc05a950d2f50cee02936a8f1f785ff32336b40b1760eb205539174"})
p.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
PY

if test "$summarize_rc" -eq 0 || test "$summarize_rc" -eq 74; then
  cp "$out/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_RESULT.json" "$project/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_RESULT.json" 2>/dev/null || true
  cp "$out/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_TERMINAL.json" "$project/DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_TERMINAL.json" 2>/dev/null || true
  release_condition=ready
  release_contents="candidate-only dflash-depth4-c32 capture terminalized; artifacts=$out"
else
  release_condition=maintenance
  release_contents="candidate-only dflash-depth4-c32 incomplete or unretrieved; preserve artifacts=$out for repair"
fi
release_json=$(python3 -c 'import json,sys; print(json.dumps({"summary":sys.argv[1]}))' "$release_contents")
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_h200_dflash_endpoint --condition "$release_condition" --contents "$release_json"
exit "$summarize_rc"
