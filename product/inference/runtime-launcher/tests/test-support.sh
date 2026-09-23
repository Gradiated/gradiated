#!/usr/bin/env bash
readonly test_base_id=test-base-v1
trap 'exit 143' TERM
trap 'exit 130' INT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

require_test_container() {
  [[ "${GRADIATED_TEST_CONTAINER:-}" == 1 ]] ||
    fail "Run this test through tests/Dockerfile"
}

make_bundle() {
  local directory=$1 entrypoint_source=$2
  mkdir -p "$directory"
  install -m 755 "$entrypoint_source" "$directory/entrypoint"
  printf '%s\n' "$test_base_id" >"$directory/base-id"
}

assert_equal() {
  local expected=$1 actual=$2 description=$3
  [[ "$actual" == "$expected" ]] ||
    fail "$description: expected '$expected', got '$actual'"
}

assert_exits_with() {
  local expected_status=$1 expected=$2 status=0 stderr
  shift 2
  stderr=$("$@" 2>&1 >/dev/null) || status=$?

  if ((status != expected_status)) || [[ "$stderr" != *"$expected"* ]]; then
    fail "$* exited $status; expected status $expected_status and stderr containing '$expected', got stderr '$stderr'"
  fi
}

assert_fails_with() {
  assert_exits_with 1 "$@"
}

wait_until() {
  local description=$1 timeout_seconds=$2
  shift 2
  local deadline=$((SECONDS + timeout_seconds))
  until "$@"; do
    ((SECONDS < deadline)) || fail "Timed out waiting for $description"
    sleep 0.1
  done
}

stop_process() {
  local pid=$1 signal=${2:-TERM}
  kill -"$signal" "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
