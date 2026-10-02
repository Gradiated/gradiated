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
  if jq -e '.Job.Meta.gradiated_model_id' <<<"$job" >/dev/null; then
    jq -e 'all(.Job.TaskGroups[]; .Update.Canary == .Count and .Update.AutoRevert and (.Count == 0 or .Update.AutoPromote))' <<<"$job" >/dev/null || {
      echo "$name must warm a full replacement set and revert failed releases" >&2
      exit 1
    }
    jq -e '.Job.Meta.gradiated_sdk_verification == "true" and all(.Job.TaskGroups[]; .Update.HealthCheck == "manual")' <<<"$job" >/dev/null || {
      echo "$name must require production SDK verification before promotion" >&2
      exit 1
    }
    disabled=$(docker run --rm --network none --entrypoint nomad -v "$root/jobs:/jobs:ro" \
      hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 \
      job run -output "${release[@]}" -var-file="/jobs/$name.vars.hcl" -var=replicas=0 "/jobs/$name.nomad.hcl")
    jq -e 'all(.Job.TaskGroups[]; .Count == 0 and .Update.Canary == 0 and (.Update.AutoPromote | not))' <<<"$disabled" >/dev/null || {
      echo "$name must not start a canary when disabled" >&2
      exit 1
    }
  fi
  if [[ $name == glm-5-3-flash ]]; then
    jq -e '(.Job.Meta.gradiated_release | fromjson | has("lora_enabled") | not)' <<<"$job" >/dev/null
    for tp in 2 4; do
      enabled=$(docker run --rm --network none --entrypoint nomad -v "$root/jobs:/jobs:ro" \
        hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 \
        job run -output "${release[@]}" -var-file="/jobs/$name.vars.hcl" \
        -var=lora_enabled=true -var=tensor_parallel_size="$tp" \
        -var=lora_cpu_cache_bytes=1073741824 -var=lora_disk_cache_bytes=2147483648 "/jobs/$name.nomad.hcl")
      jq -e --arg tp "$tp" '
        (.Job.Meta.gradiated_release | fromjson | .lora_enabled == true) and
        all(.Job.TaskGroups[];
          (.Tasks[] | select(.Name == "vllm") |
            .Resources.Devices[0].Count == ($tp | tonumber) and
            .Env.TENSOR_PARALLEL_SIZE == $tp and .Env.LORA_ENABLED == "true") and
          (.Tasks[] | select(.Name == "desmond") |
            .Env.DESMOND_RUNTIME_PORT == "${NOMAD_PORT_runtime}"))
      ' <<<"$enabled" >/dev/null
    done
  fi
done

node "$root/../../../tools/nomad/model-replica-rules.mjs" --check
