#!/usr/bin/env bash
set -euo pipefail
owner=${1:?owner}
grep -Fq 'show --bench "$bench"' "$owner"
! grep -Fq 'claim --project gemma4_streaming_global_kv_memory_schedule' "$owner"
grep -Fq '"${ssh[@]}" -n "$2" </dev/null' "$owner"
grep -Fq "while read -r name sha;do stage" "$owner"
grep -Fq 'while ! checkpoint_integrity;do retain staging_failure' "$owner"
grep -Fq 'heartbeat --project gemma4_streaming_global_kv_memory_schedule' "$owner"
grep -Fq -- '--expected-claimed-at "$claimed_at" --condition ready' "$owner"
python3 - "$owner" <<'PY'
import pathlib,sys
s=pathlib.Path(sys.argv[1]).read_text()
assert s.index('while read -r name sha;do stage') < s.index('while ! checkpoint_integrity')
assert s.index('same-claim.json') < s.index("remote=/home/glmrunner")
PY
printf '%s\n' '{"fixture":"v10_same_claim","zero_ssh":true,"same_claim_validation":true,"manifest_staging_before_integrity":true,"expected_generation_heartbeat_release":true}'
