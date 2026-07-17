#!/usr/bin/env python3
"""Durably validate the admitted hardlink transfer view before provider creation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
from session_staging import checkpoint_files, validate_local_files_cached  # noqa: E402


VIEW = HERE.parent / "exact_h200_vllm_baseline_shared_runner/artifacts/corrected-transfer-view"
CHECKPOINT_TERMINAL = (
    HERE.parent
    / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json"
)
ASSERTION = HERE / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
OUTPUT = HERE / "artifacts/TRANSFER_VIEW_TERMINAL.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(value: dict[str, object]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)


def main() -> int:
    started = time.monotonic()
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("durable user systemd owner required")
    try:
        assertion = json.loads(ASSERTION.read_text())
        terminal = json.loads(CHECKPOINT_TERMINAL.read_text())
        rows = terminal.get("files")
        if assertion.get("pass") is not True or terminal.get("pass") is not True or not isinstance(rows, list):
            raise RuntimeError("bound checkpoint assertion is not passing")
        files = checkpoint_files(VIEW)
        cached = validate_local_files_cached(VIEW, rows)
        source = Path(str(terminal["checkpoint_root"]))
        hardlinks = all(
            (VIEW / row["path"]).stat().st_dev == (source / row["path"]).stat().st_dev
            and (VIEW / row["path"]).stat().st_ino == (source / row["path"]).stat().st_ino
            for row in rows
        )
        result = {
            "schema_version": 1,
            "classification": "transfer_view_integrity_terminal",
            "pass": hardlinks,
            "assertion_sha256": sha(ASSERTION),
            "checkpoint_terminal_sha256": sha(CHECKPOINT_TERMINAL),
            "transfer_view": str(VIEW),
            "manifest_sha256": sha(VIEW / "model-files.sha256"),
            "files_total": len(files),
            "total_bytes": sum(row.bytes for row in files),
            "hardlink_identity_pass": hardlinks,
            "cached_integrity_marker_reused": cached,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write(result)
        return 0 if result["pass"] else 2
    except Exception as error:
        write(
            {
                "schema_version": 1,
                "classification": "typed_transfer_view_precreate_failure",
                "pass": False,
                "error_type": type(error).__name__,
                "message": str(error),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
