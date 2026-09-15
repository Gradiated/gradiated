#!/usr/bin/env bash
set -euo pipefail
launcher=${1:?Pass the launcher executable}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p /etc/gradiated "$work/source" "$work/cache"
echo test-base-v1 > /etc/gradiated/base-id
echo test-base-v1 > "$work/source/base-id"
cat > "$work/source/entrypoint" <<'ENTRY'
#!/bin/sh
printf '%s\n' "$1"
test -f "$GRADIATED_RUNTIME_ROOT/base-id"
ENTRY
chmod +x "$work/source/entrypoint"
pack() { tar -czf "$work/bundle.tar.gz" -C "$work/source" .; hash=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1); }
run() { "$launcher" --archive "$work/bundle.tar.gz" --sha256 "$hash" --cache "$work/cache" -- 'literal $(false)'; }
pack
[[ "$(run)" == 'literal $(false)' ]]
rm "$work/bundle.tar.gz"
[[ "$(run)" == 'literal $(false)' ]] # Cache hit needs no source archive.
echo PASS: launch-and-cache
pack
bad_hash=$(printf '%064d' 0)
if "$launcher" --archive "$work/bundle.tar.gz" --sha256 "$bad_hash" --cache "$work/cache"; then exit 1; fi
[[ ! -e "$work/cache/$bad_hash" ]]
echo PASS: checksum-rejection
# Failed base checks must not publish a cache entry.
echo wrong-base > "$work/source/base-id"
pack
if run; then exit 1; fi
[[ ! -e "$work/cache/$hash" ]]
echo PASS: base-rejection
# Reject traversal even when the archive checksum matches.
echo test-base-v1 > "$work/source/base-id"
tar -czf "$work/bundle.tar.gz" --transform='s|^entrypoint$|../escaped|' -C "$work/source" entrypoint
hash=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1)
if run; then exit 1; fi
[[ ! -e "$work/cache/$hash" ]]
[[ -z "$(find "$work/cache" -name escaped -o -name '*.partial.*')" ]]
echo PASS: traversal-rejection-and-cleanup
# An archive cannot write through a symlink it supplied.
mkdir "$work/attack"
ln -s "$work" "$work/attack/link"
echo escaped > "$work/payload"
tar -cf "$work/attack.tar" -C "$work/attack" link
tar -rf "$work/attack.tar" --transform='s|^payload$|link/escaped|' -C "$work" payload
gzip -c "$work/attack.tar" > "$work/bundle.tar.gz"
hash=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1)
if run; then exit 1; fi
[[ ! -e "$work/escaped" ]]
echo PASS: symlink-write-rejection
# Exercise HTTPS download and certificate validation with a local TLS server.
echo test-base-v1 > "$work/source/base-id"
pack
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj /CN=localhost -addext subjectAltName=DNS:localhost \
  -keyout "$work/key.pem" -out "$work/cert.pem" >/dev/null 2>&1
(cd "$work" && exec openssl s_server -quiet -accept 19443 -cert cert.pem -key key.pem -WWW) > "$work/tls.log" 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true; rm -rf "$work"' EXIT
sleep 1
if "$launcher" --bundle https://localhost:19443/bundle.tar.gz --sha256 "$hash" --cache "$work/https-cache"; then exit 1; fi
cp "$work/cert.pem" /usr/local/share/ca-certificates/runtime-launch-test.crt
update-ca-certificates >/dev/null 2>&1
[[ "$("$launcher" --bundle https://localhost:19443/bundle.tar.gz --sha256 "$hash" --cache "$work/https-cache" -- https-ok)" == https-ok ]]
echo PASS: HTTPS-download-and-certificate-validation
# The supervisor must clean ordinary and detached descendants on stop or exit.
g++ -std=c++20 tests/process-tree.cpp -o "$work/source/entrypoint"
pack
sleep 600 &
unrelated=$!
trap 'kill "$server" "$unrelated" 2>/dev/null || true; wait "$server" "$unrelated" 2>/dev/null || true; rm -rf "$work"' EXIT
for mode in stop exit crash stubborn; do
  mkdir "$work/$mode"
  "$launcher" --archive "$work/bundle.tar.gz" --sha256 "$hash" --cache "$work/cache" -- "$work/$mode" "$mode" &
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
