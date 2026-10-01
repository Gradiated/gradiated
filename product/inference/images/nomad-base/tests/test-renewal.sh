#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../../.." && pwd)
temporary=$(mktemp -d)
container="gradiated-cert-test-$$"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$temporary"
}
trap cleanup EXIT
docker create --name "$container" hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 >/dev/null
docker cp "$container:/bin/nomad" "$temporary/nomad"
NOMAD_BINARY="$temporary/nomad" timeout 60 python3 -m unittest discover \
  -s "$root/inference/images/nomad-base/tests" -p 'test_renew_certificate.py'
