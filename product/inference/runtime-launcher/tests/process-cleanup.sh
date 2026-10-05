#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test-support.sh
source "$test_dir/test-support.sh"
require_test_container

mode=${1:?Pass the process mode}
supervisor=${2:?Pass the launcher, or the supervise adapter for the stubborn mode}
fixture=${3:?Pass the process fixture executable}
fixture_mode=${mode#*-}
[[ "$mode" != launcher-killed* && "$mode" != launcher-group-killed ]] || fixture_mode=stubborn
work=$(mktemp -d)
supervisor_pid=
unrelated_pid=
sent_signal=
expected_status=

case "$fixture_mode" in
  stop | stubborn) sent_signal=15 expected_status=143 ;;
  interrupt) sent_signal=2 expected_status=130 ;;
  hangup) sent_signal=1 expected_status=129 ;;
  exit) expected_status=37 ;;
  crash) expected_status=137 ;;
  *) fail "Unknown process mode: $mode" ;;
esac

cleanup() {
  # On assertion failure, still give the supervisor time to reap its children.
  if [[ -n "$supervisor_pid" ]]; then
    stop_process "$supervisor_pid"
  fi
  if [[ -n "$unrelated_pid" ]]; then
    stop_process "$unrelated_pid"
  fi
  rm -rf "$work"
}
trap cleanup EXIT

[[ "$mode" != launcher-killed* && "$mode" != launcher-group-killed ]] || { sent_signal=9 expected_status=137; }

stubborn_grace_seconds=2

now_ms() {
  local now=${EPOCHREALTIME/./}
  printf '%s\n' $((now / 1000))
}

# Ignored and blocked signals survive exec, so these modes start the launcher
# with the signal state that a careless parent could leave behind.
start_supervisor() {
  local launch=("$supervisor" "$work" -- "$work" "$fixture_mode")
  make_bundle "$work" "$fixture"

  case "$mode" in
    launcher-group-killed)
      setsid "${launch[@]}" &
      ;;
    ignored-*)
      (
        trap '' CHLD TERM INT HUP
        exec "${launch[@]}"
      ) &
      ;;
    blocked-*)
      perl -MPOSIX -e \
        'sigprocmask(SIG_BLOCK, POSIX::SigSet->new(SIGTERM, SIGINT, SIGHUP)) or die; exec @ARGV or die' \
        "${launch[@]}" &
      ;;
    stubborn)
      "$supervisor" --grace-seconds "$stubborn_grace_seconds" "$fixture" "$work" "$mode" &
      ;;
    *)
      "${launch[@]}" &
      ;;
  esac
}

sleep 600 &
unrelated_pid=$!
start_supervisor
supervisor_pid=$!

wait_until "the process fixture" 5 test -s "$work/ready"
started=$(now_ms)
if [[ "$mode" == launcher-killed-during-stop ]]; then
  kill -TERM "$supervisor_pid"
  sleep 1
fi
if [[ -n "$sent_signal" ]]; then
  if [[ "$mode" == launcher-group-killed ]]; then
    kill -"$sent_signal" -- "-$supervisor_pid"
  else
    kill -"$sent_signal" "$supervisor_pid"
  fi
fi

if [[ "$mode" == stubborn ]]; then
  sleep 1
  kill -0 "$(cat "$work/detached")" || fail "SIGKILL arrived before the grace period ended"
fi

actual_status=0
wait "$supervisor_pid" || actual_status=$?
supervisor_pid=
elapsed_ms=$(($(now_ms) - started))
assert_equal "$expected_status" "$actual_status" "Supervisor exit status"

process_exited() {
  ! kill -0 "$1" 2>/dev/null
}

if [[ "$mode" == launcher-killed* || "$mode" == launcher-group-killed ]]; then
  for process in leader ordinary detached; do
    pid=$(cat "$work/$process")
    wait_until "$process cleanup after launcher SIGKILL" 5 process_exited "$pid"
  done
fi

for process in leader ordinary detached; do
  pid=$(cat "$work/$process")
  if kill -0 "$pid" 2>/dev/null; then
    fail "$process process $pid survived the $mode test"
  fi
done
kill -0 "$unrelated_pid" || fail "The supervisor stopped an unrelated process"

case "$fixture_mode" in
  stop | interrupt | hangup) signaled=(leader ordinary detached) forwarded=$sent_signal ;;
  exit | crash) signaled=(ordinary detached) forwarded=15 ;;
  stubborn) signaled=(leader ordinary) forwarded=$sent_signal ;;
esac
[[ "$mode" != launcher-killed* && "$mode" != launcher-group-killed ]] || signaled=()
for process in "${signaled[@]}"; do
  assert_equal "$forwarded" "$(cat "$work/$process.signal")" "Signal received by the $process process"
done

if [[ "$mode" == stubborn ]]; then
  ((elapsed_ms >= stubborn_grace_seconds * 1000 && elapsed_ms < 8000)) ||
    fail "Escalation took $elapsed_ms ms with a $stubborn_grace_seconds s grace"
elif ((elapsed_ms >= 5000)); then
  fail "Cleanup took $elapsed_ms ms without a stubborn process"
fi
