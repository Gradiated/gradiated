#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"; base="${ARTIFACT_BASENAME:?}"; root=/workspace/public-mla-microbench; work="$root/$stage"
rm -rf "$work"; mkdir -p "$work"
set +e
python3 "$MICROBENCH_PATH" --stage "$stage" --output "$work/result.json"
rc=$?
set -e
python3 - "$work/result.json" "$work/stage-terminal.json" "$stage" "$rc" <<'PY'
import json,sys
r,t,stage,rc=sys.argv[1:]
try: value=json.load(open(r))
except Exception as e: value={"error":{"type":type(e).__name__,"message":str(e)}}
passed=rc=="0" and value.get("pass") is True
terminal={"stage":stage,"pass":passed,"all_actual_consumers_pass":value.get("all_actual_consumers_pass",False),"economic_both_envelopes_falsified":value.get("economic_both_envelopes_falsified",False),"result":value}
json.dump(terminal,open(t,"w"),sort_keys=True)
PY
printf '%s\n' "$stage" > "$work/stage.txt"
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/$base.tar.gz" -C "$root" "$stage"
sha256sum "$root/$base.tar.gz" > "$root/$base.tar.gz.sha256"
exit "$rc"
