#!/usr/bin/env bash
set -euo pipefail
umask 077
bundle=${1:?Pass the runtime bundle directory}
marker=${NOMAD_ALLOC_DIR:?}/runtime-starting
rm -f "$marker"
devices=${NVIDIA_VISIBLE_DEVICES:?Nomad must assign GPU UUIDs}
[[ $devices =~ ^GPU-[[:xdigit:]-]+(,GPU-[[:xdigit:]-]+)*$ ]] || {
  echo 'Expected explicit Nomad GPU UUIDs' >&2
  exit 1
}
lock_dir=${HOME:?}/.cache/gradiated/gpu-locks
mkdir -p "$lock_dir"
IFS=, read -ra assigned <<<"$devices"
mapfile -t ordered < <(printf '%s\n' "${assigned[@]}" | LC_ALL=C sort -u)
deadline=$((SECONDS + 1200))
for gpu in "${ordered[@]}"; do
  exec {lock}>"$lock_dir/$gpu"
  remaining=$((deadline - SECONDS))
  ((remaining > 0)) && flock --exclusive --timeout "$remaining" "$lock" || {
    echo 'Timed out waiting for the previous GPU owner' >&2
    exit 1
  }
done

while true; do
  active=$(timeout --kill-after=1s 10s nvidia-smi --id="$devices" --query-compute-apps=pid --format=csv,noheader)
  [[ -z $active ]] && break
  ((SECONDS < deadline)) || {
    echo 'Timed out waiting for existing GPU processes to finish' >&2
    exit 1
  }
  sleep 1
done

# The launcher guardian inherits these locks until all runtime descendants exit.
touch "$marker"
exec "$bundle/runtime-launch" "$bundle"
