#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test-support.sh
source "$test_dir/test-support.sh"
require_test_container

launcher=${1:?Pass the launcher executable}
process_fixture=${2:?Pass the process fixture executable}
work=$(mktemp -d)
agent_pid=
export NOMAD_ADDR=http://127.0.0.1:4646

cleanup() {
  local status=$?
  if ((status != 0)) && [[ -f "$work/agent.log" ]]; then
    tail -50 "$work/agent.log" >&2
  fi
  if [[ -n "$agent_pid" ]]; then
    stop_process "$agent_pid"
  fi
  rm -f /usr/local/bin/curl /etc/gradiated/artifact.env
  rm -rf "$work"
}
trap cleanup EXIT

prepare_bundle() {
  make_bundle "$work/bundle" "$test_dir/fixtures/entrypoint.sh"
  tar -czf "$work/bundle.tar.gz" -C "$work/bundle" .
}

prepare_downloader() {
  printf 'AWS_ACCESS_KEY_ID=test-only\nAWS_SECRET_ACCESS_KEY=test-only\n' >/etc/gradiated/artifact.env
  cat >/usr/local/bin/curl <<'FIXTURE'
#!/usr/bin/env bash
set -euo pipefail
config=$(cat)
[[ "$config" == *'user = "test-only:test-only"'* ]]
[[ "$*" != *test-only* ]]
if [[ "$*" == *--head* ]]; then
  stat -c %s "$TEST_BUNDLE"
  exit 0
fi
while (($#)); do
  if [[ "$1" == --range ]]; then range=$2; break; fi
  shift
done
start=${range%-*}; end=${range#*-}
dd if="$TEST_BUNDLE" bs=1 skip="$start" count="$((end - start + 1))" status=none
FIXTURE
  chmod 755 /usr/local/bin/curl
}

node_is_ready() {
  kill -0 "$agent_pid" || fail "The test Nomad agent exited"
  nomad node status -json 2>/dev/null | jq -e 'any(.[]; .Status == "ready")' >/dev/null
}

start_nomad() {
  # Nomad runs as a normal user to avoid cgroup setup in the test container.
  chmod 755 "$work"
  chown nobody "$work"
  install -d -o nobody -m 700 "$work/state"
  runuser -u nobody -- nomad agent -dev -bind=127.0.0.1 \
    -data-dir="$work/state" -config="$test_dir/fixtures/nomad-client.hcl" \
    >"$work/agent.log" 2>&1 &
  agent_pid=$!
  wait_until "the test Nomad node" 10 node_is_ready
}

allocation_exists() {
  allocation_id=$(nomad job allocs -json "$1" | jq -r '.[0].ID // empty')
  [[ -n "$allocation_id" ]]
}

submit_job() {
  local name=$1 checksum=$2
  # shellcheck disable=SC2016
  local runtime_args='["literal $(false)"]'
  if (($# >= 3)); then runtime_args=$3; fi
  nomad job run -output -var="name=$name" -var="checksum=$checksum" \
    -var="launcher=$launcher" -var="bundle=$work/bundle.tar.gz" "$test_dir/fixtures/artifact.nomad.hcl" |
    jq --argjson runtime_args "$runtime_args" '
      .Job.ID = .Job.Name |
      (.Job.TaskGroups[].Tasks[] | select(.Name == "runtime") | .Config.args) |=
        ([.[0], "--"] + $runtime_args)
    ' >"$work/job.json"
  nomad job run -detach -json "$work/job.json" >/dev/null
  wait_until "an allocation for $name" 10 allocation_exists "$name"
}

task_is_dead() {
  nomad alloc status -json "$allocation_id" >"$work/allocation.json"
  jq -e --arg task "$1" '.TaskStates[$task].State == "dead"' "$work/allocation.json" >/dev/null
}

test_valid_bundle() {
  local checksum
  checksum=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1)
  submit_job artifact-valid "$checksum"
  wait_until "successful bundle execution" 15 task_is_dead runtime
  jq -e '.TaskStates.runtime.Failed == false' "$work/allocation.json" >/dev/null ||
    fail "The valid runtime failed"
  assert_equal "runtime fixture passed" \
    "$(nomad alloc logs "$allocation_id" runtime)" "Nomad task output"
}

test_invalid_checksum() {
  submit_job artifact-invalid "$(printf '%064d' 0)"
  wait_until "checksum rejection" 15 task_is_dead download-runtime
  jq -e '
    .TaskStates["download-runtime"].Failed == true and
    all(.TaskStates.runtime.Events[]; .Type != "Started")
  ' "$work/allocation.json" >/dev/null ||
    fail "The bad checksum did not prevent task startup"
}

test_launcher_cleanup() {
  local pids="$work/runtime-pids" checksum runtime_args pid
  install -d -o nobody -m 700 "$pids"
  install -m 755 "$process_fixture" "$work/bundle/entrypoint"
  tar -czf "$work/bundle.tar.gz" -C "$work/bundle" .
  checksum=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1)
  runtime_args=$(jq -cn --arg pids "$pids" '[$pids, "stubborn"]')
  submit_job artifact-launcher-killed "$checksum" "$runtime_args"
  wait_until "the detached runtime fixture" 15 test -s "$pids/ready"
  nomad alloc signal -s SIGKILL -task runtime "$allocation_id" >/dev/null
  wait_until "the killed launcher" 10 task_is_dead runtime

  process_exited() {
    ! kill -0 "$1" 2>/dev/null
  }

  for process in leader ordinary detached; do
    pid=$(cat "$pids/$process")
    wait_until "$process cleanup after Nomad SIGKILL" 5 process_exited "$pid"
  done
}

prepare_bundle
prepare_downloader
start_nomad
test_valid_bundle
test_invalid_checksum
test_launcher_cleanup

NOMAD_LIVENESS_TEST=1 python3 "$test_dir/liveness.py" "$launcher" "$process_fixture" LivenessTests.test_nomad_update_and_restart
