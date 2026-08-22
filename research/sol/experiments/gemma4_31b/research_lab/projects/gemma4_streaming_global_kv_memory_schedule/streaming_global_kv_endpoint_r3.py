#!/usr/bin/env python3
"""Consume exactly one fresh candidate c32 endpoint after activation proof."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def require_activation(path: pathlib.Path) -> dict:
    proof = json.loads(path.read_text())
    if proof.get("candidate_path") != "u8_streamed" or proof.get("target") != "sglang.srt.layers.radix_attention.RadixAttention.forward":
        raise RuntimeError("candidate_activation_proof_invalid")
    return proof


def main() -> int:
    root = pathlib.Path(os.environ["STREAMING_GLOBAL_KV_OUTPUT_ROOT"])
    runner = pathlib.Path(os.environ["STREAMING_GLOBAL_KV_EXACT_RUNNER"])
    telemetry = pathlib.Path(os.environ["GLOBAL_KV_TELEMETRY"])
    activation = pathlib.Path(os.environ["GLOBAL_KV_ACTIVATION_CAPTURE"])
    authorization = pathlib.Path(
        os.environ.get(
            "STREAMING_GLOBAL_KV_REPAIR_AUTHORIZATION",
            "/work/out/REPAIR_AUTHORIZATION.json",
        )
    )
    if not authorization.is_file():
        raise RuntimeError("endpoint_repair_authorization_missing")
    if os.environ.get("STREAMING_GLOBAL_KV_CANDIDATE_SERVER") != "1":
        raise RuntimeError("candidate_server_activation_proof_missing")
    if root.exists():
        raise RuntimeError("endpoint_output_root_must_be_fresh")
    proof = require_activation(activation)
    root.mkdir(parents=True)
    invocation = [sys.executable, str(runner), "--output", str(root / "exact-c32"), "--arm", "streamed-candidate", "--concurrency", "32"]
    result = subprocess.run(invocation, text=True, capture_output=True, check=False)
    (root / "endpoint.stdout").write_text(result.stdout)
    (root / "endpoint.stderr").write_text(result.stderr)
    terminal_path = root / "exact-c32" / "TERMINAL.json"
    if not terminal_path.is_file():
        raise RuntimeError(f"endpoint_terminal_missing:{result.returncode}")
    terminal = json.loads(terminal_path.read_text())
    if result.returncode or not terminal.get("pass") or terminal.get("complete_requests") != 32:
        raise RuntimeError(f"endpoint_invalid:{result.returncode}:{terminal.get('complete_requests')}")
    rows = [json.loads(line) for line in telemetry.read_text().splitlines() if line.strip()]
    layer35 = [row for row in rows if row.get("layer_id") == 35 and row.get("candidate_path") == "u8_streamed" and not row.get("fallback", True)]
    if not layer35:
        raise RuntimeError("layer35_candidate_path_proof_missing")
    atomic(root / "LAYER35_PASSAGE.json", {"schema_version": 1, "layer_id": 35, "candidate_path": "u8_streamed", "rows": layer35})
    atomic(root / "TERMINAL.json", {"schema_version": 1, "classification": "candidate_endpoint_complete", "complete_requests": 32, "activation": proof, "endpoint_terminal": terminal, "endpoint_terminal_sha256": hashlib.sha256(terminal_path.read_bytes()).hexdigest(), "telemetry_rows": len(rows), "layer35_rows": len(layer35)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
