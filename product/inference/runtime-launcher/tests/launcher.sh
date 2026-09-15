#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test-support.sh
source "$test_dir/test-support.sh"

case_name=${1:?Pass the test case}
launcher=${2:?Pass the launcher executable}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

cp "$test_dir/fixtures/entrypoint.sh" "$work/entrypoint"
chmod 755 "$work/entrypoint"
printf 'test-base-v1\n' >"$work/base-id"

run_launcher() {
  # Confirm that the launcher passes shell syntax without evaluating it.
  # shellcheck disable=SC2016
  "$launcher" "$work" -- 'literal $(false)'
}

case "$case_name" in
  arguments)
    assert_equal "runtime fixture passed" "$(run_launcher)" "Entrypoint output"
    ;;
  wrong-base)
    printf 'wrong-base\n' >"$work/base-id"
    assert_status 1 run_launcher
    ;;
  missing-base)
    rm "$work/base-id"
    assert_status 1 run_launcher
    ;;
  non-executable)
    chmod 644 "$work/entrypoint"
    assert_status 1 run_launcher
    ;;
  symlink-entrypoint)
    mv "$work/entrypoint" "$work/real-entrypoint"
    ln -s real-entrypoint "$work/entrypoint"
    assert_status 1 run_launcher
    ;;
  missing-directory)
    assert_status 1 "$launcher" "$work/missing"
    ;;
  invalid-arguments)
    assert_status 1 "$launcher"
    assert_status 1 "$launcher" "$work" unexpected-argument
    ;;
  *)
    fail "Unknown launcher test: $case_name"
    ;;
esac
