#!/usr/bin/env bash
# Shared assertions for the Linux fixture tests.
fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equal() {
  local expected=$1 actual=$2 description=$3
  [[ "$actual" == "$expected" ]] ||
    fail "$description: expected '$expected', got '$actual'"
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

assert_status() {
  local expected=$1 actual=0
  shift
  "$@" || actual=$?
  assert_equal "$expected" "$actual" "Exit status of $*"
}
