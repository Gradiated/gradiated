#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEPENDENCY = ROOT.parent / "gemma4_h200_e4m3_kv_direct_endpoint"
DEPENDENCY_TERMINAL = (
    DEPENDENCY / "artifacts/e4m3-kv-direct-20260723/FINAL_TERMINAL.json"
)
DEPENDENCY_STATUS = DEPENDENCY / "STATUS.json"
INPUT_ROOT = ROOT / "inputs/dependency"
ARTIFACT_ROOT = ROOT / "artifacts/dependency-boundary-20260723"

EXPECTED_TERMINAL_SHA256 = (
    "800d1afeeb33bdbd7a0bd3a3e8a25d51e6a187eddfc8ef0d49cd668d837dee44"
)
EXPECTED_STATUS_SHA256 = (
    "8250961489187c0ded8728d02c61bd7ed7cb9a104de4283202230e80168f8ab4"
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1 << 20), b""):
            value.update(part)
    return value.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def main() -> int:
    observed_terminal_sha = digest(DEPENDENCY_TERMINAL)
    observed_status_sha = digest(DEPENDENCY_STATUS)
    if observed_terminal_sha != EXPECTED_TERMINAL_SHA256:
        raise RuntimeError(
            f"dependency_terminal_changed:{observed_terminal_sha}"
        )
    if observed_status_sha != EXPECTED_STATUS_SHA256:
        raise RuntimeError(f"dependency_status_changed:{observed_status_sha}")

    dependency_terminal = json.loads(DEPENDENCY_TERMINAL.read_text())
    dependency_status = json.loads(DEPENDENCY_STATUS.read_text())
    path_proof = dependency_terminal["candidate_path_proof"]
    qkv_event_count = len(path_proof["qkv_events"])
    if dependency_terminal["status"] != "terminal":
        raise RuntimeError("dependency_not_terminal")
    if dependency_status["status"] != "complete":
        raise RuntimeError("dependency_not_complete")
    if dependency_terminal["classification"] != "close":
        raise RuntimeError("dependency_not_closed")
    if dependency_terminal["pass"] is not False:
        raise RuntimeError("dependency_unexpectedly_passed")
    if qkv_event_count != 0:
        raise RuntimeError(f"dependency_qkv_audit_changed:{qkv_event_count}")

    local_terminal = INPUT_ROOT / "FINAL_TERMINAL.json"
    local_status = INPUT_ROOT / "STATUS.json"
    atomic_copy(DEPENDENCY_TERMINAL, local_terminal)
    atomic_copy(DEPENDENCY_STATUS, local_status)
    if digest(local_terminal) != EXPECTED_TERMINAL_SHA256:
        raise RuntimeError("local_dependency_terminal_copy_mismatch")
    if digest(local_status) != EXPECTED_STATUS_SHA256:
        raise RuntimeError("local_dependency_status_copy_mismatch")

    candidate_seconds = float(
        dependency_terminal["candidate_service_seconds_per_request"]
    )
    e5m2_control_seconds = float(
        dependency_terminal["persisted_e5m2_control_seconds_per_request"]
    )
    local_wall_fraction = 0.1531203203096733
    perfect_local_removal_seconds = (
        candidate_seconds - e5m2_control_seconds * local_wall_fraction
    )
    manifest = {
        "schema_version": 1,
        "dependency_project": DEPENDENCY.name,
        "source_terminal": str(DEPENDENCY_TERMINAL),
        "source_status": str(DEPENDENCY_STATUS),
        "files": [
            {
                "path": str(local_terminal.relative_to(ROOT)),
                "bytes": local_terminal.stat().st_size,
                "sha256": digest(local_terminal),
            },
            {
                "path": str(local_status.relative_to(ROOT)),
                "bytes": local_status.stat().st_size,
                "sha256": digest(local_status),
            },
        ],
    }
    atomic_json(INPUT_ROOT / "MANIFEST.json", manifest)

    source_binding = ROOT / "SOURCE_BINDING.json"
    source_binding_terminal = (
        ROOT / "artifacts/offline-binding-20260723/OFFLINE_BINDING_TERMINAL.json"
    )
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "dependency_comparator_invalid_no_claim",
        "pass": False,
        "scientific_candidate_admitted": False,
        "scientific_invocation_started": False,
        "candidate_cuda_invocation_started": False,
        "bench_claimed": False,
        "provider_spend_usd": 0.0,
        "project_cumulative_spend_usd": 0.0,
        "dependency": {
            "project": DEPENDENCY.name,
            "classification": dependency_terminal["classification"],
            "pass": dependency_terminal["pass"],
            "candidate_service_seconds_per_request": candidate_seconds,
            "persisted_e5m2_control_seconds_per_request": e5m2_control_seconds,
            "relative_to_control_fraction": dependency_terminal[
                "relative_to_control_fraction"
            ],
            "accounting_pass": dependency_terminal["accounting_pass"],
            "response_pass": dependency_terminal["response_pass"],
            "qkv_event_count": qkv_event_count,
            "fp8_consumer_event_count": len(path_proof["fp8_consumer_events"]),
            "terminal_sha256": observed_terminal_sha,
            "status_sha256": observed_status_sha,
            "comparator_admissible": False,
        },
        "analytical_bound": {
            "e4m3_candidate_seconds_per_request": candidate_seconds,
            "e5m2_control_local_wall_fraction": local_wall_fraction,
            "perfect_local_removal_seconds_per_request": (
                perfect_local_removal_seconds
            ),
            "economic_ceiling_seconds_per_request": 0.6381105231,
            "performance_bound_survives": (
                perfect_local_removal_seconds < 0.6381105231
            ),
            "evidence_label": "analytical_cross-representation_upper_bound_only",
        },
        "decision": (
            "Do not claim the H200 or invoke the component/c32 hybrid. The "
            "required exact E4M3-Triton comparator was scientifically consumed "
            "with zero retained QKV audit events and is explicitly closed as "
            "inadmissible by its owner. Replaying that endpoint or substituting "
            "another backend is outside this project's contract."
        ),
        "offline_binding": {
            "source_binding": str(source_binding.relative_to(ROOT)),
            "source_binding_sha256": digest(source_binding),
            "terminal": str(source_binding_terminal.relative_to(ROOT)),
            "terminal_sha256": digest(source_binding_terminal),
        },
        "dependency_manifest": str(
            (INPUT_ROOT / "MANIFEST.json").relative_to(ROOT)
        ),
    }
    atomic_json(ARTIFACT_ROOT / "FINAL_TERMINAL.json", terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
