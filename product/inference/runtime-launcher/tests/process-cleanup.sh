#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test-support.sh
source "$test_dir/test-support.sh"

mode=${1:?Pass the process mode}
launcher=${2:?Pass the launcher executable}
fixture=${3:?Pass the process fixture executable}
work=$(mktemp -d)
supervisor_pid=
unrelated_pid=

cleanup() {
  # On assertion failure, still give the supervisor time to reap its children.
  if [[ -n "$supervisor_pid" ]]; then
    kill -TERM "$supervisor_pid" 2>/dev/null || true
    wait "$supervisor_pid" 2>/dev/null || true
  fi
  if [[ -n "$unrelated_pid" ]]; then
    kill "$unrelated_pid" 2>/dev/null || true
    wait "$unrelated_pid" 2>/dev/null || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

cp "$fixture" "$work/entrypoint"
printf 'test-base-v1\n' >"$work/base-id"
sleep 600 &
unrelated_pid=$!
"$launcher" "$work" -- "$work" "$mode" &
supervisor_pid=$!

wait_until "the process fixture" 5 test -s "$work/ready"
case "$mode" in
  stop | stubborn)
    kill -TERM "$supervisor_pid"
    expected_status=143
    ;;
  exit) expected_status=37 ;;
  crash) expected_status=137 ;;
  *) fail "Unknown process mode: $mode" ;;
esac

actual_status=0
wait "$supervisor_pid" || actual_status=$?
supervisor_pid=
assert_equal "$expected_status" "$actual_status" "Supervisor exit status"

for process in leader ordinary detached; do
  pid=$(cat "$work/$process")
  if kill -0 "$pid" 2>/dev/null; then
    fail "$process process $pid survived the $mode test"
  fi
done
kill -0 "$unrelated_pid" || fail "The supervisor stopped an unrelated process"
