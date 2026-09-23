#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test-support.sh
source "$test_dir/test-support.sh"
require_test_container

case_name=${1:?Pass the test case}
launcher=${2:?Pass the launcher executable}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

make_bundle "$work" "$test_dir/fixtures/entrypoint.sh"

run_launcher() {
  # Confirm that the launcher passes shell syntax without evaluating it.
  # shellcheck disable=SC2016
  "$launcher" "$work" -- 'literal $(false)'
}

case "$case_name" in
  arguments)
    assert_equal "runtime fixture passed" "$(run_launcher)" "Entrypoint output"
    ;;
  canonical-root)
    cat >"$work/entrypoint" <<'ENTRYPOINT'
#!/bin/sh
printf '%s\n' "$GRADIATED_RUNTIME_ROOT"
ENTRYPOINT
    ln -s "$work" "$work/alias"

    assert_equal "$(realpath "$work")" "$("$launcher" "$work/alias")" "Runtime root"
    ;;
  wrong-base)
    printf 'wrong-base\n' >"$work/base-id"
    assert_fails_with "Bundle base ID wrong-base does not match host base ID $test_base_id" run_launcher
    ;;
  missing-base)
    rm "$work/base-id"
    assert_fails_with "Cannot read base ID" run_launcher
    ;;
  oversized-base)
    printf '%0129d\n' 0 >"$work/base-id"
    assert_fails_with "Invalid base ID in $(realpath "$work")/base-id" run_launcher
    ;;
  blank-base)
    printf '\n' >"$work/base-id"
    assert_fails_with "Invalid base ID in $(realpath "$work")/base-id" run_launcher
    ;;
  non-executable)
    chmod 644 "$work/entrypoint"
    assert_fails_with "executable regular file" run_launcher
    ;;
  symlink-entrypoint)
    mv "$work/entrypoint" "$work/real-entrypoint"
    ln -s real-entrypoint "$work/entrypoint"

    assert_fails_with "executable regular file" run_launcher
    ;;
  bad-interpreter)
    printf '#!/nonexistent/sh\n' >"$work/entrypoint"
    assert_exits_with 127 "Cannot execute $(realpath "$work")/entrypoint" run_launcher
    ;;
  missing-directory)
    assert_fails_with "$work/missing" "$launcher" "$work/missing"
    ;;
  invalid-arguments)
    assert_fails_with "Usage:" "$launcher"
    assert_fails_with "Expected --" "$launcher" "$work" unexpected-argument
    ;;
  *)
    fail "Unknown launcher test: $case_name"
    ;;
esac
