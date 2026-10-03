#!/usr/bin/env bash
set -euo pipefail
umask 022

url=${1:?Pass the bundle URL}
digest=${2:?Pass the SHA-256 digest}
destination=${3:?Pass the runtime directory}
[[ "$digest" =~ ^[0-9a-f]{64}$ ]] || {
  echo 'Invalid bundle digest' >&2
  exit 1
}

# Accept only immutable release objects, not arbitrary downloader arguments.
[[ "$url" =~ ^s3::https://([a-z0-9.-]+)\.s3\.us-east-1\.amazonaws\.com/bundles/sha256/$digest\.tar\.gz$ ]] || {
  echo 'Invalid bundle URL' >&2
  exit 1
}

source_url=${url#s3::}
if [[ -e "$destination" ]]; then
  [[ -f "$destination/.bundle-sha256" && $(cat "$destination/.bundle-sha256") == "$digest" ]] || {
    echo 'Runtime directory holds a different bundle' >&2
    exit 1
  }

  exit 0
fi

work=$(mktemp -d "${destination}.download.XXXXXX")
started=$SECONDS
phase=download
cleanup() {
  local status=$?
  if ((status != 0)); then
    printf 'Bundle %s failed after %ss (exit %s)\n' "$phase" "$((SECONDS - started))" "$status" >&2
  fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
(
  set -a
  # Enrollment owns this file. Only the downloader user can read it.
  # shellcheck source=/dev/null
  source /etc/gradiated/artifact.env
  set +a
  printf 'Bundle download started\n'
  timeout --kill-after=10s 20m python3 "$(dirname "$0")/download-runtime" \
    "$source_url" "$work/runtime.tar.gz"
)
phase=checksum
printf 'Bundle download completed in %ss\n' "$((SECONDS - started))"
printf '%s  %s\n' "$digest" "$work/runtime.tar.gz" | sha256sum --check --status
printf 'Bundle checksum verified at %ss\n' "$((SECONDS - started))"
phase=extraction
mkdir "$work/runtime"
# Extract only after verifying the trusted release. bsdtar rejects unsafe paths.
timeout --kill-after=10s 10m bsdtar --no-same-owner --no-same-permissions \
  -xf "$work/runtime.tar.gz" -C "$work/runtime"
printf '%s\n' "$digest" >"$work/runtime/.bundle-sha256"
mv -T "$work/runtime" "$destination"
printf 'Bundle ready in %ss\n' "$((SECONDS - started))"
