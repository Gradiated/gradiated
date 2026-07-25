#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
python_bin=${PYTHON_BIN:-python3}
gate=
sglang_root=
record=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dflash-gate)
      gate=$2
      shift 2
      ;;
    --sglang-root)
      sglang_root=$2
      shift 2
      ;;
    --record)
      record=$2
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

if [[ -z "$gate" || -z "$sglang_root" || -z "$record" || $# -eq 0 ]]; then
  echo "usage: $0 --dflash-gate FILE --sglang-root DIR --record FILE -- COMMAND..." >&2
  exit 64
fi

"$python_bin" - "$gate" "$sglang_root" "$record" "$project_dir" <<'PY'
import json
import pathlib
import sys

gate_path = pathlib.Path(sys.argv[1]).resolve()
sglang_root = pathlib.Path(sys.argv[2]).resolve()
record_path = pathlib.Path(sys.argv[3]).resolve()
project_dir = pathlib.Path(sys.argv[4]).resolve()
gate = json.loads(gate_path.read_text())
required = {
    "pass": gate.get("pass") is True,
    "classification": gate.get("classification") == "diagnostic_pass",
    "complete_requests": gate.get("complete_requests") == 4,
    "raw_token_ids": gate.get("candidate_raw_token_ids_present") is True,
    "target_exact_text": gate.get("prior_ar_decoded_text_equal") is True,
    "draft_initialized": gate.get("draft_runner_initialized") is True,
    "target_verification": int(gate.get("verify_event_count", 0)) > 0,
    "accepted_drafts": int(gate.get("accepted_draft_tokens", 0)) > 0,
}
if not all(required.values()):
    raise RuntimeError(f"active DFlash diagnostic does not admit FP8 follow-up: {required}")

sys.path.insert(0, str(project_dir / "overlay"))
from dflash_fp8_tied_head_stack import source_hashes, verify_source_hashes

observed = source_hashes(sglang_root / "python/sglang/srt")
verify_source_hashes(observed)
record = {
    "schema_version": 1,
    "status": "admitted",
    "dflash_gate": str(gate_path),
    "dflash_gate_checks": required,
    "sglang_root": str(sglang_root),
    "source_sha256": observed,
    "overlay": str(project_dir / "overlay"),
    "scope": "sequential existing-H200 follow-up only; this wrapper does not claim or create a bench",
}
temporary = record_path.with_suffix(record_path.suffix + ".part")
temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
temporary.replace(record_path)
PY

export PYTHONPATH="$project_dir/overlay:$sglang_root/python${PYTHONPATH:+:$PYTHONPATH}"
export SGLANG_DFLASH_FP8_TIED_HEAD=1
exec "$@"
