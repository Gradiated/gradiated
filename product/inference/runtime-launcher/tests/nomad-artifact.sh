#!/usr/bin/env bash
# Run in the disposable test container. No production connection or GPU use.
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test-support.sh
source "$test_dir/test-support.sh"

[[ "${GRADIATED_TEST_CONTAINER:-}" == 1 ]] ||
  fail "Run this integration test through tests/Dockerfile"

launcher=${1:?Pass the launcher executable}
work=$(mktemp -d)
server_pid=
agent_pid=
export NOMAD_ADDR=http://127.0.0.1:4646

cleanup() {
  local status=$?
  if ((status != 0)) && [[ -f "$work/agent.log" ]]; then
    tail -50 "$work/agent.log" >&2
  fi
  for pid in "$agent_pid" "$server_pid"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  rm -f /usr/local/share/ca-certificates/nomad-fixture.crt
  update-ca-certificates >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

prepare_bundle() {
  mkdir "$work/bundle"
  cp "$test_dir/fixtures/entrypoint.sh" "$work/bundle/entrypoint"
  chmod 755 "$work/bundle/entrypoint"
  printf 'test-base-v1\n' >"$work/bundle/base-id"
  tar -czf "$work/bundle.tar.gz" -C "$work/bundle" .
}

start_https_server() {
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -subj /CN=localhost -addext subjectAltName=DNS:localhost \
    -keyout "$work/key.pem" -out "$work/cert.pem" >/dev/null 2>&1
  cp "$work/cert.pem" /usr/local/share/ca-certificates/nomad-fixture.crt
  update-ca-certificates >/dev/null 2>&1
  (
    cd "$work"
    exec openssl s_server -quiet -accept 19443 -cert cert.pem -key key.pem -WWW
  ) >"$work/tls.log" 2>&1 &
  server_pid=$!
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
  nomad job run -output -var="name=$name" -var="checksum=$checksum" \
    -var="launcher=$launcher" "$test_dir/fixtures/artifact.nomad.hcl" |
    jq '.Job.ID = .Job.Name' >"$work/job.json"
  nomad job run -detach -json "$work/job.json" >/dev/null
  wait_until "an allocation for $name" 10 allocation_exists "$name"
}

task_is_terminal() {
  nomad alloc status -json "$allocation_id" >"$work/allocation.json"
  jq -e '.TaskStates.runtime.State == "dead"' "$work/allocation.json" >/dev/null
}

test_valid_bundle() {
  local checksum
  checksum=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1)
  submit_job artifact-valid "$checksum"
  wait_until "successful bundle execution" 15 task_is_terminal
  jq -e '.TaskStates.runtime.Failed == false' "$work/allocation.json" >/dev/null ||
    fail "The valid runtime failed"
  assert_equal "runtime fixture passed" \
    "$(nomad alloc logs "$allocation_id" runtime)" "Nomad task output"
}

test_invalid_checksum() {
  submit_job artifact-invalid "$(printf '%064d' 0)"
  wait_until "checksum rejection" 15 task_is_terminal
  jq -e '
    .TaskStates.runtime |
    .Failed == true and
    any(.Events[]; .Type == "Failed Artifact Download") and
    all(.Events[]; .Type != "Started")
  ' "$work/allocation.json" >/dev/null ||
    fail "The bad checksum did not prevent task startup"
}

prepare_bundle
start_https_server
start_nomad
test_valid_bundle
test_invalid_checksum
