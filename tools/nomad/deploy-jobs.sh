#!/usr/bin/env bash
set -euo pipefail
# Deploys every job that has a committed <job>.vars.hcl. A job without one, such as a
# qualification-only job, is never submitted. Git is the desired state: an unchanged
# job produces no new allocations.
#
# Reads the Nomad CLI environment: NOMAD_ADDR, NOMAD_TOKEN, NOMAD_CACERT,
# NOMAD_CLIENT_CERT, NOMAD_CLIENT_KEY and NOMAD_TLS_SERVER_NAME.
repo=$(git rev-parse --show-toplevel)
jobs=product/inference/nomad/jobs
image=hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9
tls=$(dirname "$NOMAD_CACERT")

nomad() {
  docker run --rm --network host \
    -e NOMAD_ADDR -e NOMAD_TOKEN -e NOMAD_TLS_SERVER_NAME \
    -e NOMAD_CACERT="/tls/$(basename "$NOMAD_CACERT")" \
    -e NOMAD_CLIENT_CERT="/tls/$(basename "$NOMAD_CLIENT_CERT")" \
    -e NOMAD_CLIENT_KEY="/tls/$(basename "$NOMAD_CLIENT_KEY")" \
    -v "$tls:/tls:ro" -v "$repo/$jobs:/jobs:ro" \
    "$image" "$@"
}

shopt -s nullglob
deployable=("$repo/$jobs"/*.vars.hcl)
if ((${#deployable[@]} == 0)); then
  echo 'No job has a vars file; nothing to deploy'
  exit 0
fi

for vars in "${deployable[@]}"; do
  name=$(basename "$vars" .vars.hcl)
  [[ -f "$repo/$jobs/$name.nomad.hcl" ]] || {
    echo "$name.vars.hcl has no $name.nomad.hcl" >&2
    exit 1
  }
  echo "::group::$name"
  # Plan exits 1 when allocations would change, which is the normal case for a rollout.
  status=0
  nomad job plan -var-file="/jobs/$name.vars.hcl" "/jobs/$name.nomad.hcl" || status=$?
  ((status <= 1)) || exit "$status"
  nomad job run -var-file="/jobs/$name.vars.hcl" "/jobs/$name.nomad.hcl"
  echo '::endgroup::'
done
