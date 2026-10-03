#!/usr/bin/env bash
# Run in the disposable test container; no cloud credentials or network needed.
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work" /etc/gradiated/artifact.env' EXIT
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

printf 'Runtime download checks passed.\n'
