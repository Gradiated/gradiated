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

source_url="s3://${BASH_REMATCH[1]}/bundles/sha256/$digest.tar.gz"
if [[ -e "$destination" ]]; then
  [[ -f "$destination/.bundle-sha256" && $(cat "$destination/.bundle-sha256") == "$digest" ]] || {
    echo 'Runtime directory holds a different bundle' >&2
    exit 1
  }

  exit 0
fi

work=$(mktemp -d "${destination}.download.XXXXXX")
started=$SECONDS
trap 'rm -rf "$work"' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
(
  set -a
  # Enrollment owns this file. Only the downloader user can read it.
  # shellcheck source=/dev/null
  source /etc/gradiated/artifact.env
  set +a
  export AWS_EC2_METADATA_DISABLED=true AWS_REGION=us-east-1
  timeout --kill-after=10s 20m s5cmd --numworkers 1 cp --concurrency 8 --part-size 64 \
    "$source_url" "$work/runtime.tar.gz"
)
printf 'Bundle download completed in %ss\n' "$((SECONDS - started))"
printf '%s  %s\n' "$digest" "$work/runtime.tar.gz" | sha256sum --check --status
printf 'Bundle checksum verified at %ss\n' "$((SECONDS - started))"
mkdir "$work/runtime"
# Extract only after verifying the trusted release. bsdtar rejects unsafe paths.
timeout --kill-after=10s 10m bsdtar --no-same-owner --no-same-permissions \
  -xf "$work/runtime.tar.gz" -C "$work/runtime"
printf '%s\n' "$digest" >"$work/runtime/.bundle-sha256"
mv -T "$work/runtime" "$destination"
printf 'Bundle ready in %ss\n' "$((SECONDS - started))"
