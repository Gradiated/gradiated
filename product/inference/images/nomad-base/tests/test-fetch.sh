#!/usr/bin/env bash
# Run in the disposable test container; no cloud credentials or network needed.
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work" /etc/gradiated/artifact.env' EXIT
cache=/var/cache/gradiated/runtime-bundles
mkdir -p "$cache"
chown "$(id -u):$(id -g)" "$cache"
chmod 700 "$cache"
trap 'rm -rf "$work" "$cache" /etc/gradiated/artifact.env' EXIT
mkdir -p "$work/bin" "$work/bundle" /etc/gradiated
printf 'AWS_ACCESS_KEY_ID=test-only\nAWS_SECRET_ACCESS_KEY=test-only\n' >/etc/gradiated/artifact.env
printf 'verified runtime\n' >"$work/bundle/payload"
tar -czf "$work/bundle.tar.gz" -C "$work/bundle" .
export TEST_BUNDLE="$work/bundle.tar.gz"
export PATH="$work/bin:$PATH"

stub_curl() {
  {
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    cat
  } >"$work/bin/curl"
  chmod +x "$work/bin/curl"
}

bundle_url() {
  printf 's3::https://test-bucket.s3.us-east-1.amazonaws.com/bundles/sha256/%s.tar.gz' "$1"
}

fetch() { bash /opt/gradiated/bin/fetch-runtime "$@"; }

rejects() {
  local what=$1
  shift
  if fetch "$@" 2>"$work/stderr"; then
    echo "$what was accepted" >&2
    exit 1
  fi
}

left_nothing() {
  [[ ! -e "$1" ]]
  [[ -z $(find "$work" -maxdepth 1 -name '*.download.*' -print) ]]
}

stub_curl <<'FIXTURE'
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
digest=$(sha256sum "$TEST_BUNDLE" | cut -d' ' -f1)
url=$(bundle_url "$digest")
fetch "$url" "$digest" "$work/runtime"
cmp "$work/bundle/payload" "$work/runtime/payload"
[[ $(cat "$work/runtime/.bundle-sha256") == "$digest" ]]

# A completed pre-start task can be retried without another download.
rm "$work/bin/curl"
fetch "$url" "$digest" "$work/runtime"
# A different allocation reuses the verified archive, without curl or credentials.
rm /etc/gradiated/artifact.env
fetch "$url" "$digest" "$work/second-runtime"
cmp "$work/bundle/payload" "$work/second-runtime/payload"
printf 'AWS_ACCESS_KEY_ID=test-only\nAWS_SECRET_ACCESS_KEY=test-only\n' >/etc/gradiated/artifact.env
# Cache corruption cannot be extracted when the source is unavailable.
stub_curl <<'FIXTURE'
exit 1
FIXTURE
printf corrupt >"$cache/$digest.tar.gz"
rejects 'A corrupt cached archive' "$url" "$digest" "$work/corrupt-cached"
left_nothing "$work/corrupt-cached"
[[ ! -e "$cache/$digest.tar.gz" ]]
chmod 755 "$cache"
rejects 'A shared cache directory' "$url" "$digest" "$work/shared-cache"
chmod 700 "$cache"

other=$(printf '%064d' 0)
rejects 'A runtime directory with a different bundle' "$(bundle_url "$other")" "$other" "$work/runtime"
grep -qF 'Runtime directory holds a different bundle' "$work/stderr"
cmp "$work/bundle/payload" "$work/runtime/payload"
mkdir "$work/unmarked"
rejects 'A runtime directory without a bundle digest' "$url" "$digest" "$work/unmarked"
grep -qF 'Runtime directory holds a different bundle' "$work/stderr"

rejects 'An invalid digest' "$url" "${digest^^}" "$work/uppercase"
grep -qF 'Invalid bundle digest' "$work/stderr"
left_nothing "$work/uppercase"

rejects 'An unsupported source' 'https://example.invalid/bundle' "$digest" "$work/invalid"
grep -qF 'Invalid bundle URL' "$work/stderr"
left_nothing "$work/invalid"

stub_curl <<'FIXTURE'
exit 1
FIXTURE
rejects 'A failed download' "$url" "$digest" "$work/failed"
left_nothing "$work/failed"
grep -qF "Bundle download failed" "$work/stderr"

stub_curl <<'FIXTURE'
cat >/dev/null
if [[ "$*" == *--head* ]]; then
  stat -c %s "$TEST_BUNDLE"
  exit 0
fi
while (($#)); do
  if [[ "$1" == --max-filesize ]]; then count=$2; break; fi
  shift
done
head -c "$count" /dev/zero
FIXTURE
rejects 'A corrupt download' "$url" "$digest" "$work/corrupt"
left_nothing "$work/corrupt"
grep -qF "Bundle checksum failed" "$work/stderr"

# A valid checksum does not permit archive entries to escape the directory.
tar -czf "$work/unsafe.tar.gz" --transform='s,payload,../escaped,' -C "$work/bundle" payload
export TEST_BUNDLE="$work/unsafe.tar.gz"
digest=$(sha256sum "$TEST_BUNDLE" | cut -d' ' -f1)
stub_curl <<'FIXTURE'
cat >/dev/null
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
rejects 'An unsafe archive' "$(bundle_url "$digest")" "$digest" "$work/unsafe"
left_nothing "$work/unsafe"
[[ ! -e "$work/escaped" ]]

# Concurrent allocations share one download and each extract its own runtime.
export TEST_BUNDLE="$work/bundle.tar.gz" TEST_HEAD_COUNT="$work/head-count"
printf 'concurrent release\n' >"$work/bundle/payload"
tar -czf "$TEST_BUNDLE" -C "$work/bundle" .
digest=$(sha256sum "$TEST_BUNDLE" | cut -d' ' -f1)
stub_curl <<'FIXTURE'
cat >/dev/null
if [[ "$*" == *--head* ]]; then
  echo request >>"$TEST_HEAD_COUNT"
  sleep 1
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
fetch "$(bundle_url "$digest")" "$digest" "$work/concurrent-1" & first=$!
fetch "$(bundle_url "$digest")" "$digest" "$work/concurrent-2" & second=$!
wait "$first"
wait "$second"
[[ $(wc -l <"$TEST_HEAD_COUNT") == 1 ]]
cmp "$work/concurrent-1/payload" "$work/concurrent-2/payload"

# A corrupt cache entry recovers from the trusted source without operator cleanup.
printf corrupt >"$cache/$digest.tar.gz"
fetch "$(bundle_url "$digest")" "$digest" "$work/repaired-runtime"
cmp "$work/concurrent-1/payload" "$work/repaired-runtime/payload"
[[ $(wc -l <"$TEST_HEAD_COUNT") == 2 ]]

# A stalled extractor releases the lock and survives removal of its cache entry.
export TEST_EXTRACT_STARTED="$work/extract-started" TEST_EXTRACT_GATE="$work/extract-gate"
mkfifo "$TEST_EXTRACT_GATE"
cat >"$work/bin/bsdtar" <<'FIXTURE'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *stalled-runtime* ]]; then
  touch "$TEST_EXTRACT_STARTED"
  read -r -t 20 resume <"$TEST_EXTRACT_GATE"
fi
exec /usr/bin/bsdtar "$@"
FIXTURE
chmod +x "$work/bin/bsdtar"
fetch "$(bundle_url "$digest")" "$digest" "$work/stalled-runtime" & stalled=$!
for _ in {1..100}; do
  [[ ! -e "$TEST_EXTRACT_STARTED" ]] || break
  sleep 0.05
done
[[ -e "$TEST_EXTRACT_STARTED" ]]
timeout 10s bash /opt/gradiated/bin/fetch-runtime "$(bundle_url "$digest")" "$digest" "$work/unblocked-runtime"
rm "$cache/$digest.tar.gz"
printf 'resume\n' >"$TEST_EXTRACT_GATE"
wait "$stalled"
cmp "$work/stalled-runtime/payload" "$work/unblocked-runtime/payload"
rm "$work/bin/bsdtar"

# Retention bounds disk usage and preserves the most recently used bundle.
export TEST_BUNDLE="$work/bundle.tar.gz"
for i in {1..6}; do
  printf 'release %s\n' "$i" >"$work/bundle/payload"
  tar -czf "$TEST_BUNDLE" -C "$work/bundle" .
  digest=$(sha256sum "$TEST_BUNDLE" | cut -d' ' -f1)
  fetch "$(bundle_url "$digest")" "$digest" "$work/release-$i"
done
[[ $(find "$cache" -maxdepth 1 -name '*.tar.gz' | wc -l) == 4 ]]
[[ -f "$cache/$digest.tar.gz" ]]
printf 'Runtime download checks passed.\n'
