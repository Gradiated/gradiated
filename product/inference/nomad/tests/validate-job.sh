#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
# Validate committed configurations for every deployable job as well. Deploy supplies
# a bundle job's release, so placeholders stand in for it here.
bundles=$(node "$root/../../../tools/models/release.mjs" list)
shopt -s nullglob
for vars in "$root/jobs"/*.vars.hcl; do
  name=$(basename "$vars" .vars.hcl)
  release=()
  if jq -e --arg name "$name" 'index($name)' <<<"$bundles" >/dev/null; then
    release=(
      -var=bundle_url=https://example.invalid/bundle.tar.gz
      -var=bundle_sha256=0000000000000000000000000000000000000000000000000000000000000000
      -var=base_id=test-base-v1
    )
  fi
  docker run --rm --network none --entrypoint nomad -v "$root/jobs:/jobs:ro" \
    hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 \
    job validate ${release[@]+"${release[@]}"} -var-file="/jobs/$name.vars.hcl" "/jobs/$name.nomad.hcl"
  job=$(docker run --rm --network none --entrypoint nomad -v "$root/jobs:/jobs:ro" \
    hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 \
    job run -output ${release[@]+"${release[@]}"} -var-file="/jobs/$name.vars.hcl" "/jobs/$name.nomad.hcl")
  jq -e '
    .Job.Meta as $meta |
    if $meta.gradiated_model_id then
      ($meta.gradiated_release | fromjson) as $release |
      ($release.model_path == $meta.gradiated_model_id) or
        (($release.runtime_model_name // "") | length > 0)
    else true end
  ' <<<"$job" >/dev/null || {
    echo "$name must declare runtime_model_name when its artifact and public model IDs differ" >&2
    exit 1
  }
done

node "$root/../../../tools/nomad/model-replica-rules.mjs" --check
