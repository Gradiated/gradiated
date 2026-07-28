#!/usr/bin/env python3
"""Construct the director-authorized invalid terminal without CUDA activity."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOCALIZATION = ROOT / "artifacts/h100-streaming-component/PACKED_M384_STREAMING_LAUNCH_LOCALIZATION_TERMINAL.json"
EXPECTED_LOCALIZATION_SHA256 = "cbebfdcc5e7c95342bd5619031dce5bf0cac025568c5593bc6aa1813e4369033"
AUTHORIZATION = ROOT / "DIRECTOR_HOPPER_PACKED_STREAMING_ARM_ISOLATED_RETRY_20260726T2210Z.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    if sha256(LOCALIZATION) != EXPECTED_LOCALIZATION_SHA256:
        raise RuntimeError("localization_digest_mismatch")
    localization = json.loads(LOCALIZATION.read_text())
    if localization.get("scientific_result") is not False:
        raise RuntimeError("localization_not_invalid_attempt")
    if sha256(AUTHORIZATION) != "63a976e6e06e80c9a19a82e76ff5f0264e3889caa72762ac151d1d84597d2a4e":
        raise RuntimeError("authorization_digest_mismatch")
    output = args.artifact_root / "PACKED_M384_STREAMING_COMPONENT_RESULT.json"
    atomic_json(output, {
        "schema_version": 1,
        "type": "packed_m384_streaming_component_result",
        "result": "invalid_attempt_shared_synchronization_ambiguity",
        "classification": "invalid_attempt_shared_synchronization_ambiguity",
        "scientific_result": False,
        "performance_interpretation_permitted": False,
        "correctness_interpretation_permitted": False,
        "cuda_invocation_performed_by_constructor": False,
        "component_replay_performed": False,
        "v2_replay_performed": False,
        "endpoint_action_performed": False,
        "source_localization": str(LOCALIZATION.relative_to(ROOT)),
        "source_localization_sha256": EXPECTED_LOCALIZATION_SHA256,
        "reason": "stock A, stock B, and candidate shared the only asynchronous completion boundary; preserved evidence cannot assign the CUDA fault to an arm",
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
