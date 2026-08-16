#!/usr/bin/env bash
set -Eeuo pipefail

root=${LOCAL_ATTENTION_REMOTE_ROOT:?}
artifacts="$root/artifacts"

terminal() {
  python3 - "$artifacts/REMOTE_TERMINAL.json" "$1" "$2" <<'PY'
import datetime, json, os, pathlib, sys
path = pathlib.Path(sys.argv[1]); temporary = path.with_suffix(".part")
state_path = path.parent / "component/INVOCATION_STATE.json"
state = json.loads(state_path.read_text()) if state_path.is_file() else {}
value = {
    "schema_version": 2, "status": "terminal", "classification": sys.argv[2],
    "message": sys.argv[3],
    "candidate_cuda_invocation_started": state.get("candidate_cuda_invocation_started", False),
    "scientific_invocation_started": state.get("scientific_invocation_started", False),
    "scientific_terminal_recorded": state.get("scientific_terminal_recorded", False),
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n"); os.replace(temporary, path)
PY
}

compact() {
  set +e
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/component-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/component-compact.tar.gz" >"$root/component-compact.tar.gz.sha256"
}
trap compact EXIT
trap 'terminal component_consumer_failure "$BASH_COMMAND"' ERR

test -f "$artifacts/component/COMPONENT_TERMINAL.json"
test -f "$artifacts/component/INVOCATION_STATE.json"
test -f "$artifacts/ncu-export.csv"
test -f "$artifacts/local-two-stage.ncu-rep"
set +e
python3 "$root/input/analyze_iteration2.py" \
  --component-terminal "$artifacts/component/COMPONENT_TERMINAL.json" \
  --ncu-csv "$artifacts/ncu-export.csv" \
  --ncu-report "$artifacts/local-two-stage.ncu-rep" \
  --output "$artifacts/COMPONENT_RESULT.json" \
  >"$artifacts/analyze.stdout" 2>"$artifacts/analyze.stderr"
rc=$?
set -e
if [[ -f "$artifacts/COMPONENT_RESULT.json" ]]; then
  python3 - "$artifacts/COMPONENT_RESULT.json" <<'PY'
import json, os, pathlib, sys
path=pathlib.Path(sys.argv[1]); value=json.loads(path.read_text())
identity=value.get('component_terminal',{}).get('identity',{})
module_hash=identity.get('candidate_module_sha256')
if module_hash and 'candidate_source_sha256' not in identity:
    identity['candidate_source_sha256']=module_hash
tmp=path.with_suffix('.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,path)
PY
fi
if [[ "$rc" -eq 0 || "$rc" -eq 2 ]]; then
  terminal component_complete "preserved producer; analyzer_rc=$rc"
else
  terminal component_consumer_failure "preserved producer; analyzer_rc=$rc"
fi
exit "$rc"
