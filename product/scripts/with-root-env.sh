#!/usr/bin/env bash
# Each NAME the caller has set keeps the caller's value over .env and .env.local.
set -eo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
kept=()

while [[ $# -gt 0 && "$1" != "--" ]]; do
  if [[ -n "${!1+x}" ]]; then
    kept+=("$1=${!1}")
  fi
  shift
done

if [[ $# -lt 2 ]]; then
  printf 'Usage: %s [NAME...] -- COMMAND [ARG...]\n' "$0" >&2
  exit 64
fi

shift

set -a
for file in "${root}/.env" "${root}/.env.local"; do
  if [[ -f "${file}" ]]; then
    # shellcheck source=/dev/null
    source "${file}"
  fi
done
set +a

for assignment in ${kept[@]+"${kept[@]}"}; do
  export "${assignment?}"
done

exec "$@"
