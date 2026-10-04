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
# Release URLs stay stable; enrolled hosts use the bucket's accelerated endpoint.
source_url=${source_url/.s3.us-east-1.amazonaws.com\//.s3-accelerate.amazonaws.com\/}
if [[ -e "$destination" ]]; then
  [[ -f "$destination/.bundle-sha256" && $(cat "$destination/.bundle-sha256") == "$digest" ]] || {
    echo 'Runtime directory holds a different bundle' >&2
    exit 1
  }

  exit 0
fi

# Older enrolled hosts remain compatible until this private directory is installed.
cache=/var/cache/gradiated/runtime-bundles
cached=
if [[ -d "$cache" ]]; then
  [[ ! -L "$cache" && $(stat -c %u "$cache") == "$EUID" && $(stat -c %a "$cache") == 700 ]] || {
    echo 'Runtime cache must be a private directory owned by the downloader' >&2
    exit 1
  }
  exec {cache_lock}>"$cache/.lock"
  # Allow queued cold downloads on an eight-GPU host (up to four TP2 allocations).
  # Extraction runs outside the lock; serving tasks keep their separate deadlines.
  flock --exclusive --timeout 5400 "$cache_lock"
  cached="$cache/$digest.tar.gz"
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
archive="$work/runtime.tar.gz"
verified=false
if [[ -n "$cached" && -f "$cached" ]]; then
  phase=checksum
  if printf '%s  %s\n' "$digest" "$cached" | sha256sum --check --status; then
    archive=$cached
    verified=true
    printf 'Bundle cache hit\n'
  else
    rm -f -- "$cached"
    printf 'Discarded corrupt bundle cache entry\n' >&2
  fi
fi
if [[ "$verified" == false ]]; then
  phase=download
  (
    set -a
    # Enrollment owns this file. Only the downloader user can read it.
    # shellcheck source=/dev/null
    source /etc/gradiated/artifact.env
    set +a
    printf 'Bundle download started\n'
    timeout --kill-after=10s 20m python3 "$(dirname "$0")/download-runtime" \
      "$source_url" "$archive"
  )
  printf 'Bundle download completed in %ss\n' "$((SECONDS - started))"
fi
phase=checksum
if [[ "$verified" == false ]]; then
  printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status
fi
printf 'Bundle checksum verified at %ss\n' "$((SECONDS - started))"
if [[ -n "$cached" ]]; then
  if [[ "$archive" != "$cached" ]]; then
    mv -T "$archive" "$cached"
    archive=$cached
  fi
  touch "$cached"
  # One lock covers readers and eviction. Retain at most four verified archives.
  mapfile -t stale < <(cd "$cache" && find . -maxdepth 1 -type f -name '*.tar.gz' -printf '%T@ %f\n' | sort -rn | tail -n +5 | cut -d' ' -f2-)
  for name in "${stale[@]}"; do rm -f -- "$cache/$name"; done
  # Keep the verified inode open so eviction cannot interrupt extraction.
  exec {archive_fd}<"$cached"
  archive="/proc/self/fd/$archive_fd"
  flock --unlock "$cache_lock"
fi
phase=extraction
mkdir "$work/runtime"
# Extract only after verifying the trusted release. bsdtar rejects unsafe paths.
timeout --kill-after=10s 10m bsdtar --no-same-owner --no-same-permissions \
  -xf "$archive" -C "$work/runtime"
printf '%s\n' "$digest" >"$work/runtime/.bundle-sha256"
mv -T "$work/runtime" "$destination"
printf 'Bundle ready in %ss\n' "$((SECONDS - started))"
