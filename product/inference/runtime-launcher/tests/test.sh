#!/usr/bin/env bash
set -euo pipefail
launcher=${1:?Pass the launcher executable}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p /etc/gradiated "$work/source"
echo test-base-v1 > /etc/gradiated/base-id
echo test-base-v1 > "$work/source/base-id"
cat > "$work/source/entrypoint" <<'ENTRY'
#!/bin/sh
printf '%s\n' "$1"
test -f "$GRADIATED_RUNTIME_ROOT/base-id"
ENTRY
chmod +x "$work/source/entrypoint"
run() { "$launcher" "$work/source" -- 'literal $(false)'; }
[[ "$(run)" == 'literal $(false)' ]]
echo PASS: launch-and-literal-arguments
echo wrong-base > "$work/source/base-id"
if run; then exit 1; fi
rm "$work/source/base-id"
if run; then exit 1; fi
echo PASS: missing-and-wrong-base-rejection
echo test-base-v1 > "$work/source/base-id"
chmod -x "$work/source/entrypoint"
if run; then exit 1; fi
mv "$work/source/entrypoint" "$work/source/real-entrypoint"
chmod +x "$work/source/real-entrypoint"
ln -s real-entrypoint "$work/source/entrypoint"
if run; then exit 1; fi
rm "$work/source/entrypoint"
echo PASS: invalid-entrypoint-rejection
# The supervisor must clean ordinary and detached descendants on stop or exit.
g++ -std=c++20 tests/process-tree.cpp -o "$work/source/entrypoint"
sleep 600 &
unrelated=$!
trap 'kill "$unrelated" 2>/dev/null || true; wait "$unrelated" 2>/dev/null || true; rm -rf "$work"' EXIT
for mode in stop exit crash stubborn; do
  mkdir "$work/$mode"
  "$launcher" "$work/source" -- "$work/$mode" "$mode" &
  supervisor=$!
  for attempt in $(seq 1 100); do [[ -f "$work/$mode/detached" ]] && break; sleep 0.05; done
  [[ -s "$work/$mode/detached" ]]
  if [[ "$mode" == stop || "$mode" == stubborn ]]; then kill -TERM "$supervisor"; fi
  set +e
  wait "$supervisor"
  result=$?
  set -e
  case "$mode" in
    stop|stubborn) [[ "$result" -eq 143 ]] ;;
    exit) [[ "$result" -eq 37 ]] ;;
    crash) [[ "$result" -eq 137 ]] ;;
  esac
  for pidfile in "$work/$mode/leader" "$work/$mode/ordinary" "$work/$mode/detached"; do
    if kill -0 "$(cat "$pidfile")" 2>/dev/null; then echo "Surviving process: $mode"; exit 1; fi
  done
  kill -0 "$unrelated"
  echo "PASS: process-tree-cleanup-$mode"
done
