#!/usr/bin/env bash
set -Eeuo pipefail
p=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_runtime_codesign; lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab; bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j; image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
: "${OWNER_ARTIFACT_ROOT:?}" "${OWNER_REMOTE_ROOT:?}" "${OWNER_DEADLINE_UTC:?}"; out=$OWNER_ARTIFACT_ROOT; remote=$OWNER_REMOTE_ROOT; mkdir -p "$out/remote-artifacts"
phase(){ echo "$(date -u +%FT%TZ) $1" >>"$out/OWNER_PROGRESS.log"; }; hb(){ while sleep 15; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_runtime_codesign --bench "$bench" >>"$out/heartbeat.log" 2>&1||true; done; }; hb & h=$!; trap 'kill $h 2>/dev/null||true' EXIT
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench"); eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']); assert r['claim']['project']=='gemma4_b200_fp8_runtime_codesign'
for a,b in [('host','public_ipv4'),('user','ssh_user'),('key','identity_file'),('known','known_hosts_namespace')]: print(a+'='+shlex.quote(r['resource'][b]))
PY
)"; ssh=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host"); scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
phase stage; "${ssh[@]}" "mkdir -p '$remote'"; "${scp[@]}" "$p/candidate/run_b200_fp8_runtime_falsifier.py" "$p/PRECLAIM_B200_FP8_RUNTIME_FALSIFIER_REPAIR_TERMINAL.json" "$user@$host:$remote/" >"$out/stage.stdout" 2>"$out/stage.stderr"
phase gpu_generation; set +e; "${ssh[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$remote:/work' '$image' /work/run_b200_fp8_runtime_falsifier.py --output /work/B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json" >"$out/worker.stdout" 2>"$out/worker.stderr"; rc=$?; set -e; echo "$rc" >"$out/worker.exit"
phase retrieve; "${scp[@]}" "$user@$host:$remote/B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json" "$out/remote-artifacts/" >"$out/retrieve.stdout" 2>"$out/retrieve.stderr" || true; test -s "$out/remote-artifacts/B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json" || { phase retrieve_failed; exit 75; }
cp "$out/remote-artifacts/B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json" "$p/B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json"; cls=$(jq -r .classification "$p/B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json"); phase "terminal:$cls"
if [[ "$cls" != "interpretable_exact_component_generation" ]]; then
  printf '%s\n' "classification=$cls" >"$out/REPAIR_DIAGNOSTIC.txt"
  /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "runtime-falsifier-layout-$(date -u +%Y%m%dT%H%M%SZ)" --deadline "$OWNER_DEADLINE_UTC" --failure-kind "$cls" --diagnostic "$out/REPAIR_DIAGNOSTIC.txt" --retry-scope fp8_linear_layout >"$out/repair-ready.json"
  phase repair_ready
  while [[ "$(date -u +%s)" -lt "$(date -u -d "$OWNER_DEADLINE_UTC" +%s)" ]]; do
    if find "$out/.repair-handshakes" -name REPAIR_REQUEST.json -type f -print -quit 2>/dev/null | grep -q .; then phase repair_request_received; exit 75; fi
    sleep 5
  done
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_runtime_codesign --bench "$bench" --condition maintenance --contents "$out/RELEASE_CONTENTS.json" >>"$out/release.log" 2>&1 || true
  exit 75
fi
printf '{"state":"b200_fp8_runtime_falsifier_complete","science_consumed":true,"component_terminal":"B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json","server_state":"GPU unoccupied; image and caches retained"}\n' >"$out/RELEASE_CONTENTS.json"; PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_runtime_codesign --bench "$bench" --condition ready --contents "$out/RELEASE_CONTENTS.json" >"$out/release.log" 2>&1
