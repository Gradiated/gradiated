#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_local_attention_fusion
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
plan=$project/B200_LOCAL_PAGED_GQA_SPLIT_REDUCER_PLAN.json
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79

: "${OWNER_DEADLINE_UTC:?future director binding must set OWNER_DEADLINE_UTC}"
: "${OWNER_ARTIFACT_ROOT:?future director binding must set OWNER_ARTIFACT_ROOT}"
: "${OWNER_REMOTE_ROOT:?future director binding must set OWNER_REMOTE_ROOT}"
: "${OWNER_EXECUTION_BINDING:?future director binding must set OWNER_EXECUTION_BINDING}"
out=$OWNER_ARTIFACT_ROOT
remote=$OWNER_REMOTE_ROOT

mkdir -p "$out"
phase() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
atomic_json() {
  python3 - "$1" "$2" <<'PY'
import json, os, pathlib, sys, tempfile
p = pathlib.Path(sys.argv[1])
v = json.loads(sys.argv[2])
p.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile("w", dir=p.parent, delete=False) as f:
    json.dump(v, f, indent=2, sort_keys=True)
    f.write("\n")
    name = f.name
json.loads(pathlib.Path(name).read_text())
os.replace(name, p)
PY
}
heartbeat() {
  while sleep 20; do
    PYTHONPATH=/root/workspace/research/factory/src \
      python3 -m grad_research.gpu_pool --lab "$lab" heartbeat \
      --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" \
      >>"$out/heartbeat.log" 2>&1 || true
  done
}
heartbeat & hb=$!
trap 'kill "$hb" 2>/dev/null || true' EXIT

release_terminal() {
  local condition=$1
  phase "release:$condition"
  PYTHONPATH=/root/workspace/research/factory/src \
    python3 -m grad_research.gpu_pool --lab "$lab" release \
    --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" \
    --condition "$condition" --contents "$out/RELEASE_CONTENTS.json" \
    >>"$out/release.log" 2>&1
}

phase binding
python3 - "$plan" "$0" "$project" "$OWNER_EXECUTION_BINDING" "$OWNER_DEADLINE_UTC" <<'PY'
import hashlib, json, pathlib, sys
plan_path, owner_path, project, binding_path = map(pathlib.Path, sys.argv[1:5])
deadline = sys.argv[5]
p = json.loads(plan_path.read_text())
b = json.loads(binding_path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert p["execution_authorized"] is False
assert b["execution_authorized"] is True
assert b["project"] == "gemma4_b200_fp8_local_attention_fusion"
assert b["bench"] == "b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j"
assert b["plan_sha256"] == sha(plan_path)
assert b["deadline_utc"] == deadline
assert p["hashes"]["owner_sha256"] == sha(owner_path.resolve())
for field, rel in {
    "candidate_sha256": "candidate/local_paged_gqa_split_reducer_fused.py",
    "runner_sha256": "candidate/check_split_reducer_correctness_b200.py",
    "kernel_sha256": "candidate/split_reducer_src/batch_decode_kernel.cu",
    "config_sha256": "candidate/split_reducer_src/batch_decode_config.inc",
    "pinned_source_manifest_sha256": "inputs/pinned/flashinfer-0.6.6/split-reducer-source/MANIFEST.sha256",
}.items():
    assert p["hashes"][field] == sha(project / rel)
PY

row=$(PYTHONPATH=/root/workspace/research/factory/src \
  python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench")
eval "$(ROW="$row" python3 - <<'PY'
import json, os, shlex
r = json.loads(os.environ["ROW"])
assert r["claim"]["project"] == "gemma4_b200_fp8_local_attention_fusion"
for k, v in {
    "host": r["resource"]["public_ipv4"],
    "user": r["resource"]["ssh_user"],
    "key": r["resource"]["identity_file"],
    "known": r["resource"]["known_hosts_namespace"],
}.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"
test -f "$key" && test -f "$known"
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
ssh_stream=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")

phase stage
"${ssh_cmd[@]}" "mkdir -p '$remote/input' '$remote/output-0'" \
  >"$out/stage.stdout" 2>"$out/stage.stderr"
tar -C "$project" -cf - \
  candidate/local_paged_gqa_split_reducer_fused.py \
  candidate/check_split_reducer_correctness_b200.py \
  candidate/split_reducer_src \
  inputs/pinned/flashinfer-0.6.6/split-reducer-source \
  inputs/pinned/flashinfer-0.6.6/trtllm-gen-artifact \
  B200_LOCAL_PAGED_GQA_SPLIT_REDUCER_PLAN.json |
  "${ssh_stream[@]}" "tar -C '$remote/input' -xf -" \
    >>"$out/stage.stdout" 2>>"$out/stage.stderr"

attempt=0
repair_generation=0
execute_worker=1
while true; do
  attempt_out=$out/attempt-$attempt
  remote_out=$remote/output-$attempt
  mkdir -p "$attempt_out/remote-artifacts"
  "${ssh_cmd[@]}" "mkdir -p '$remote_out'"
  if (( execute_worker )); then
    phase "attempt:$attempt:scientific_pair"
    set +e
    "${ssh_cmd[@]}" \
      "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$remote/input:/work:ro' -v '$remote_out:/out' '$image' /work/candidate/check_split_reducer_correctness_b200.py --project-root /work --artifact-root /out" \
      >"$attempt_out/worker.stdout" 2>"$attempt_out/worker.stderr"
    worker_rc=$?
    set -e
    printf '%s\n' "$worker_rc" >"$attempt_out/worker.exit"
  else
    phase "attempt:$attempt:retrieval_only"
    worker_rc=$(<"$attempt_out/worker.exit")
  fi

  set +e
  "${ssh_cmd[@]}" "cat '$remote_out/CORRECTNESS_TERMINAL.json'" \
    >"$attempt_out/remote-artifacts/CORRECTNESS_TERMINAL.json" \
    2>"$attempt_out/retrieve.stderr"
  retrieve_rc=$?
  "${ssh_cmd[@]}" \
    "test -e '$remote_out/candidate_science_started' && echo candidate_science_started=true || echo candidate_science_started=false" \
    >"$attempt_out/candidate_science_started.txt" 2>>"$attempt_out/retrieve.stderr"
  set -e

  classification=$(python3 - "$attempt_out" "$worker_rc" "$retrieve_rc" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); worker_rc = int(sys.argv[2]); retrieve_rc = int(sys.argv[3])
if retrieve_rc:
    print("unknown_retrieval")
else:
    try: t = json.loads((root / "remote-artifacts/CORRECTNESS_TERMINAL.json").read_text())
    except Exception: print("unknown_terminal")
    else:
        print(t.get("terminal") if t.get("interpretable_result") else "invalid_attempt")
PY
)
  if [[ "$classification" == correct || "$classification" == incorrect ]]; then
    cp "$attempt_out/remote-artifacts/CORRECTNESS_TERMINAL.json" "$out/CORRECTNESS_TERMINAL.json"
    atomic_json "$out/OWNER_TERMINAL.json" \
      "{\"schema_version\":1,\"terminal\":\"$classification\",\"interpretable_result\":true,\"scientific_sample_consumed\":true,\"attempt\":$attempt,\"worker_exit_code\":$worker_rc}"
    atomic_json "$out/RELEASE_CONTENTS.json" \
      "{\"schema_version\":1,\"state\":\"split_reducer_$classification\",\"stage\":\"correctness_component\",\"science_consumed\":true,\"server_state\":\"GPU unoccupied; image/source/build/checkpoint caches retained\",\"component_terminal\":\"CORRECTNESS_TERMINAL.json\"}"
    release_terminal ready
    exit 0
  fi

  # Unknown or invalid attempts retain the continuous claim and expose an
  # executable repair path.  A request must supply a bound tar patch under
  # this project; the owner stages it and re-enters only this invalidated pair.
  retry_scope=scientific_pair
  [[ "$classification" == unknown_retrieval ]] && retry_scope=retrieval
  repair_id="split-reducer-repair-$repair_generation"
  diagnostic=$attempt_out/REPAIR_DIAGNOSTIC-$repair_generation.txt
  {
    printf 'classification=%s\nworker_rc=%s\nretrieve_rc=%s\n' \
      "$classification" "$worker_rc" "$retrieve_rc"
    tail -80 "$attempt_out/worker.stderr" "$attempt_out/retrieve.stderr" 2>/dev/null || true
  } >"$diagnostic"
  /root/workspace/research/factory/tools/repair-handshake ready \
    --root "$out" --repair-id "$repair_id" --deadline "$OWNER_DEADLINE_UTC" \
    --failure-kind "$classification" --diagnostic "$diagnostic" \
    --retry-scope "$retry_scope" >"$attempt_out/repair-ready-$repair_generation.json"
  phase "attempt:$attempt:repair_ready"
  set +e
  /root/workspace/research/factory/tools/repair-handshake wait \
    --root "$out" --repair-id "$repair_id" --deadline "$OWNER_DEADLINE_UTC" \
    --poll-seconds 2 >"$attempt_out/repair-wait-$repair_generation.json"
  wait_rc=$?
  set -e
  if (( wait_rc != 0 )); then
    atomic_json "$out/RELEASE_CONTENTS.json" \
      '{"schema_version":1,"state":"split_reducer_repair_deadline","stage":"correctness_component","science_consumed":false,"server_state":"GPU unoccupied; source/image/build/checkpoint caches retained"}'
    release_terminal maintenance
    exit 75
  fi
  request_scope=$(python3 - "$attempt_out/repair-wait-$repair_generation.json" <<'PY'
import json, pathlib, sys
s = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert s["state"] == "requested"
print(s["request"]["retry_scope"])
PY
)
  if [[ "$request_scope" == retrieval ]]; then
    execute_worker=0
    repair_generation=$((repair_generation + 1))
    continue
  fi
  patch=$(python3 - "$attempt_out/repair-wait-$repair_generation.json" "$project" <<'PY'
import json, pathlib, sys
s = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert s["state"] == "requested"
p = pathlib.Path(s["request"]["patch_artifact"]).resolve()
root = pathlib.Path(sys.argv[2]).resolve()
assert p.is_file() and p.is_relative_to(root)
print(p)
PY
)
  sha256sum "$patch" >"$attempt_out/repair-patch.sha256"
  tar -tf "$patch" >"$attempt_out/repair-patch-members.txt"
  if grep -Eq '(^/|(^|/)\\.\\.(/|$))' "$attempt_out/repair-patch-members.txt"; then
    printf 'unsafe repair archive\n' >&2
    exit 76
  fi
  tar -cf - -C "$(dirname "$patch")" "$(basename "$patch")" |
    "${ssh_stream[@]}" "tar -C '$remote' -xf - && tar -C '$remote/input' -xf '$remote/$(basename "$patch")'"
  attempt=$((attempt + 1))
  repair_generation=$((repair_generation + 1))
  execute_worker=1
done
