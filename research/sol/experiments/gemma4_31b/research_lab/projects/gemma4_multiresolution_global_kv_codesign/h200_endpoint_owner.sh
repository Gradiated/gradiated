#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd "$project_dir/../.." && pwd)
project_name=gemma4_multiresolution_global_kv_codesign
required_bench=h200-global-kv-computeinstance-e00f01gpfve0e49wb3
factory_src=/root/workspace/research/factory/src
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
release_by=${H200_RELEASE_BY_UTC:?H200_RELEASE_BY_UTC is required}
artifact_root=${H200_ARTIFACT_ROOT:?H200_ARTIFACT_ROOT is required}
mkdir -p "$artifact_root"

if [[ ${H200_ENTRY_SCOPE:-} == endpoint_only || ${H200_ENTRY_SCOPE:-} == endpoint_repair2 || ${H200_ENTRY_SCOPE:-} == endpoint_activation_repair3 || ${H200_ENTRY_SCOPE:-} == endpoint_activation_repair4 ]]; then
  component=${H200_ADOPT_COMPONENT_RESULT:?H200_ADOPT_COMPONENT_RESULT is required}
  [[ $(sha256sum "$component" | awk '{print $1}') == c4374f2b6e24a5d20438fd39548c00a307ac7d98d859a66fa7171f8a2211407d ]] || exit 73
  exec python3 "$project_dir/h200_endpoint_controller.py"
fi

python3 - "$lab_dir/runtime/gpus.json" "$project_name" "$artifact_root/bench.json" <<'PY'
import json, pathlib, sys
inventory=json.loads(pathlib.Path(sys.argv[1]).read_text())
raw=inventory["benches"]
benches=list(raw.values()) if isinstance(raw, dict) else raw
matches=[bench for bench in benches if bench.get("id")=="h200-global-kv-computeinstance-e00f01gpfve0e49wb3" and (bench.get("claim") or {}).get("project")==sys.argv[2] and bench.get("accelerator") in {"h200", "nvidia-h200-sxm"}]
if not matches:
    matches=[bench for bench in benches if bench.get("id")=="h200-global-kv-computeinstance-e00f01gpfve0e49wb3" and bench.get("claim") is None and bench.get("status")=="available" and bench.get("accelerator") in {"h200", "nvidia-h200-sxm"}]
if len(matches)!=1: raise SystemExit("expected_one_director_registered_h200")
pathlib.Path(sys.argv[3]).write_text(json.dumps(matches[0], indent=2, sort_keys=True)+"\n")
PY

if python3 - "$artifact_root/bench.json" <<'PY'
import json,sys
b=json.load(open(sys.argv[1])); raise SystemExit(0 if b.get("claim") is None else 1)
PY
then
  bench_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$artifact_root/bench.json")
  PYTHONPATH="$factory_src" python3 -m grad_research.gpu_pool --lab "$lab_dir" claim --project "$project_name" --bench "$bench_id" >"$artifact_root/claim.log" 2>&1 || exit $?
fi

host=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["resource"]["public_ipv4"])' "$artifact_root/bench.json")
user=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["resource"]["ssh_user"])' "$artifact_root/bench.json")
key=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["resource"]["identity_file"])' "$artifact_root/bench.json")
known=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["resource"]["known_hosts_namespace"])' "$artifact_root/bench.json")
[[ -f "$key" && -f "$known" ]] || { echo local_ssh_identity_missing >&2; exit 2; }
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
remote=/home/glmrunner/gemma4-multiresolution-global-kv

heartbeat() {
  while sleep 45; do
    PYTHONPATH="$factory_src" python3 -m grad_research.gpu_pool --lab "$lab_dir" heartbeat --project "$project_name" || true
  done
}
heartbeat & heartbeat_pid=$!
trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT

repair_ready() {
  local reason=$1
  python3 - "$artifact_root/REPAIR_READY.json" "$reason" "$release_by" <<'PY'
import json, pathlib, sys
path=pathlib.Path(sys.argv[1]); path.write_text(json.dumps({"schema_version":1,"status":"repair_ready","scope":"component_or_endpoint_owner","diagnostic":sys.argv[2],"absolute_repair_deadline_utc":sys.argv[3],"science_consumed":"unknown"},indent=2,sort_keys=True)+"\n")
PY
  while [[ $(date -u +%Y-%m-%dT%H:%M:%SZ) < "$release_by" ]]; do
    if [[ -f "$artifact_root/REPAIR_REQUEST.json" ]]; then
      request_scope=$(python3 - "$artifact_root/REPAIR_REQUEST.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d.get("retry_scope", ""))
PY
)
      [[ "$request_scope" == "component" ]] || { echo "unsupported_repair_scope:$request_scope" >&2; exit 76; }
      phase=${H200_REPAIR_PHASE:-component}
      break
    fi
    sleep 30
  done
  [[ -f "$artifact_root/REPAIR_REQUEST.json" ]] || exit 1
}

stage_file() {
  local source=$1 target=$2 hash bytes part
  hash=$(sha256sum "$source" | awk '{print $1}'); bytes=$(stat -c %s "$source")
  if "${ssh_cmd[@]}" "test -f '$target' && test \$(stat -c %s '$target') -eq '$bytes' && test \$(sha256sum '$target' | awk '{print \$1}') = '$hash'"; then return; fi
  part="$target.part.$$"
  "${scp_cmd[@]}" "$source" "$user@$host:$part"
  "${ssh_cmd[@]}" "test \$(stat -c %s '$part') -eq '$bytes' && test \$(sha256sum '$part' | awk '{print \$1}') = '$hash' && chmod 0444 '$part' && mv '$part' '$target'"
}

"${ssh_cmd[@]}" "install -d '$remote/input' '$remote/artifacts'" || repair_ready remote_root_failed
for file in h200_component_runner.py multiresolution_global_kv.py; do stage_file "$project_dir/$file" "$remote/input/$file" || repair_ready "stage_failed:$file"; done

component_remote="$remote/artifacts/component.json"
if ! "${ssh_cmd[@]}" "sudo -n docker pull '$image' >/dev/null && sudo -n docker run --rm --gpus all --user 0:0 -v '$remote/input:/work:ro' -v '$remote/artifacts:/artifacts' '$image' python3 /work/h200_component_runner.py --mode component --result /artifacts/component.json && sudo -n chown \$(id -u):\$(id -g) '$remote/artifacts/component.json'"; then
  repair_ready component_invocation_failed
fi
"${scp_cmd[@]}" "$user@$host:$component_remote" "$artifact_root/COMPONENT_RESULT.json" || repair_ready component_retrieval_failed

python3 - "$artifact_root/COMPONENT_RESULT.json" <<'PY'
import json, sys
result=json.load(open(sys.argv[1]))
if not result.get("component_contract_pass"): raise SystemExit("component_contract_reject")
PY

if [[ -z ${H200_ENDPOINT_COMMAND:-} ]]; then repair_ready endpoint_command_not_bound; fi
if ! "${ssh_cmd[@]}" "H200_COMPONENT_RESULT='$component_remote' $H200_ENDPOINT_COMMAND"; then repair_ready endpoint_failed; fi
PYTHONPATH="$factory_src" python3 -m grad_research.gpu_pool --lab "$lab_dir" release --project "$project_name" --condition ready || repair_ready release_failed
