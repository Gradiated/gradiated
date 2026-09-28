#!/usr/bin/env bash
set -euo pipefail
# Git is the desired state: every job with a committed <job>.vars.hcl runs and every
# other job is stopped, so a job without one, such as a qualification-only job, never
# runs. A job named after a runtime bundle gets that bundle's release for this commit;
# until it is published the job is left as it is, and the deploy that follows
# publication rolls it out.
#
# Reads the Nomad CLI environment (NOMAD_ADDR, NOMAD_TOKEN, NOMAD_CACERT,
# NOMAD_CLIENT_CERT, NOMAD_CLIENT_KEY, NOMAD_TLS_SERVER_NAME) and AWS_ACCOUNT_ID.
repo=$(git rev-parse --show-toplevel)
source_sha=$(git rev-parse HEAD)
jobs=product/inference/nomad/jobs
image=hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9
tls=$(dirname "$NOMAD_CACERT")
bucket="gradiated-prod-model-artifacts-${AWS_ACCOUNT_ID:?}"
bundles=$(node "$repo/tools/models/release.mjs" list)
waiting=$(mktemp)
trap 'rm -f "$waiting"' EXIT
: >"$waiting"

nomad() {
  docker run --rm --network host \
    -e NOMAD_ADDR -e NOMAD_TOKEN -e NOMAD_TLS_SERVER_NAME \
    -e NOMAD_CACERT="/tls/$(basename "$NOMAD_CACERT")" \
    -e NOMAD_CLIENT_CERT="/tls/$(basename "$NOMAD_CLIENT_CERT")" \
    -e NOMAD_CLIENT_KEY="/tls/$(basename "$NOMAD_CLIENT_KEY")" \
    -v "$tls:/tls:ro" -v "$repo/$jobs:/jobs:ro" \
    "$image" "$@"
}

render() {
  local name=$1 release
  local args=(-var-file="/jobs/$name.vars.hcl")
  if jq -e --arg name "$name" 'index($name)' <<<"$bundles" >/dev/null; then
    release=$(node "$repo/tools/models/release.mjs" resolve "$name" "$source_sha" "$bucket" "$AWS_ACCOUNT_ID")
    if [[ -z "$release" ]]; then
      echo "::notice::$name has no published bundle for $source_sha yet; publication deploys it"
      return
    fi
    args+=(
      -var "bundle_url=$(jq -er .url <<<"$release")"
      -var "bundle_sha256=$(jq -er .sha256 <<<"$release")"
      -var "base_id=$(jq -er .baseId <<<"$release")"
    )
  fi
  nomad job run -output "${args[@]}" "/jobs/$name.nomad.hcl" | jq -c .Job >>"$waiting"
}

shopt -s nullglob
deployable=("$repo/$jobs"/*.vars.hcl)
if ((${#deployable[@]} == 0)); then
  echo 'No job has a vars file; refusing to stop every job' >&2
  exit 1
fi

for vars in "${deployable[@]}"; do
  name=$(basename "$vars" .vars.hcl)
  [[ -f "$repo/$jobs/$name.nomad.hcl" ]] || {
    echo "$name.vars.hcl has no $name.nomad.hcl" >&2
    exit 1
  }
  echo "::group::$name"
  render "$name"
  echo '::endgroup::'
done

running=$(nomad operator api /v1/jobs | jq -r '.[] | select(.Stop | not) | .ID')
for name in $running; do
  if [[ ! -f "$repo/$jobs/$name.vars.hcl" ]]; then
    echo "Stopping $name, which Git no longer defines"
    nomad job stop -detach "$name"
  fi
done

rendered=$(jq -s . "$waiting")
printf '%s\n' "$rendered" >"$waiting"
node "$repo/tools/nomad/submit-jobs.mjs" "$waiting"
