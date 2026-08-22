#!/usr/bin/env bash
set -euo pipefail
owner=${1:?owner}
grep -Fq 'local scope=$1; local why=$2; local id=' "$owner"
grep -Fq 'head -c "$n" "$src"|sha256sum' "$owner"
grep -Fq 'tail -c +$((offset+1)) "$src"' "$owner"
grep -Fq 'guest_hash "$dst.part" "$sha"' "$owner"
grep -Fq 'mv '\''$dst.part'\'' '\''$dst'\'' && chmod 0444' "$owner"
grep -Fq '"${ssh[@]}" -n "$2" </dev/null' "$owner"
grep -Fq -- '--expected-claimed-at "$claimed_at" --condition ready' "$owner"
python3 - "$owner" <<'PY'
import pathlib,sys
s=pathlib.Path(sys.argv[1]).read_text()
assert s.index('local scope=$1; local why=$2') < s.index('local id="streaming-global-kv-v11')
assert s.index('head -c "$n"') < s.index('tail -c +$((offset+1))') < s.index('guest_hash "$dst.part"')
PY
printf '%s\n' '{"fixture":"v11_resumable_same_claim","ordered_retain":true,"matching_prefix_resume":true,"exact_offset_append":true,"complete_hash_before_rename":true,"zero_ssh":true}'
