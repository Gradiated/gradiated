#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
owner="$project_dir/run_streaming_global_kv_h200_owner_v12.sh"
tmp=$(mktemp -d "$project_dir/artifacts/v12-part-state-fixture.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

remote_run(){ local cap=$1 command=$2; [[ $cap == 60 ]]; bash -c "$command"; }
eval "$(sed -n '/^part_state(){/,/^record_offset(){/p' "$owner" | sed '$d')"

absent="$tmp/absent.part"
[[ $(part_state "$absent") == '0 absent' ]]
present="$tmp/present.part"
printf 'verified-prefix-bytes' >"$present"
read -r bytes sha < <(part_state "$present")
[[ $bytes == $(wc -c <"$present") ]]
[[ $sha == $(sha256sum "$present" | awk '{print $1}') ]]
printf '%s\n' '{"fixture":"v12_part_state","absent":"0 absent","present":"size_sha256","status":"pass"}'
