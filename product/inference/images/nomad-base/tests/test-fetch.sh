#!/usr/bin/env bash
# Run in the disposable test container; no cloud credentials or network needed.
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work" /etc/gradiated/artifact.env' EXIT
mkdir -p "$work/bin" "$work/bundle" /etc/gradiated
printf 'AWS_ACCESS_KEY_ID=test-only\n' >/etc/gradiated/artifact.env
printf 'verified runtime\n' >"$work/bundle/payload"
tar -czf "$work/bundle.tar.gz" -C "$work/bundle" .
export TEST_BUNDLE="$work/bundle.tar.gz"
export PATH="$work/bin:$PATH"
cat >"$work/bin/s5cmd" <<'FIXTURE'
#!/usr/bin/env bash
set -euo pipefail
[[ "$AWS_ACCESS_KEY_ID" == test-only ]]
cp "$TEST_BUNDLE" "${@: -1}"
FIXTURE
chmod +x "$work/bin/s5cmd"
digest=$(sha256sum "$TEST_BUNDLE" | cut -d' ' -f1)
url="s3::https://test-bucket.s3.us-east-1.amazonaws.com/bundles/sha256/$digest.tar.gz"
fetch() { bash /opt/gradiated/bin/fetch-runtime "$@"; }

fetch "$url" "$digest" "$work/runtime"
cmp "$work/bundle/payload" "$work/runtime/payload"
# A completed pre-start task can be retried without another download.
rm "$work/bin/s5cmd"
fetch "$url" "$digest" "$work/runtime"

cat >"$work/bin/s5cmd" <<'FIXTURE'
#!/usr/bin/env bash
printf 'corrupt archive' > "${@: -1}"
FIXTURE
chmod +x "$work/bin/s5cmd"
if fetch "$url" "$digest" "$work/corrupt"; then
  echo 'A corrupt download was accepted' >&2
  exit 1
fi
[[ ! -e "$work/corrupt" ]]
[[ -z $(find "$work" -maxdepth 1 -name '*.download.*' -print) ]]
# A valid checksum does not permit archive entries to escape the directory.
tar -czf "$work/unsafe.tar.gz" --transform='s,payload,../escaped,' -C "$work/bundle" payload
export TEST_BUNDLE="$work/unsafe.tar.gz"
digest=$(sha256sum "$TEST_BUNDLE" | cut -d' ' -f1)
url="s3::https://test-bucket.s3.us-east-1.amazonaws.com/bundles/sha256/$digest.tar.gz"
cat >"$work/bin/s5cmd" <<'FIXTURE'
#!/usr/bin/env bash
cp "$TEST_BUNDLE" "${@: -1}"
FIXTURE
if fetch "$url" "$digest" "$work/unsafe"; then
  echo 'An unsafe archive was accepted' >&2
  exit 1
fi
[[ ! -e "$work/unsafe" && ! -e "$work/escaped" ]]
[[ -z $(find "$work" -maxdepth 1 -name '*.download.*' -print) ]]
if fetch 'https://example.invalid/bundle' "$digest" "$work/invalid"; then
  echo 'An unsupported source was accepted' >&2
  exit 1
fi
printf 'Runtime download checks passed.\n'
