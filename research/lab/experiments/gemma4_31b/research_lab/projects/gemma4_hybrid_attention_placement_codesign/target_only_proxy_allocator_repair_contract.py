#!/usr/bin/env python3
"""Execute and preserve the director-bound offline target-only repair proof."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARTIFACT_ROOT = ROOT / "artifacts" / "target-only-proxy-allocator-repair-20260726t0623z"
TERMINAL = ROOT / "TARGET_ONLY_PROXY_ALLOCATOR_REPAIR_TERMINAL.json"
BINDING = ROOT / "DIRECTOR_TARGET_ONLY_PROXY_ALLOCATOR_OWNER_DISPOSITION_AMENDMENT_20260726T0630Z.json"
ALLOCATOR_BINDING = ROOT / "DIRECTOR_TARGET_ONLY_PROXY_ALLOCATOR_REPAIR_20260726T0623Z.json"
TEST_COMMAND = [sys.executable, "-m", "unittest", "-v", "test_forward_batch_dual_cache_driver.py", "test_target_only_proxy_allocator_component_owner.py"]
ALLOCATOR_TESTS = [
    "test_stock_extend_allocates_no_proxy_and_preserves_8192_capacity",
    "test_target_verify_uses_tree_allocator_and_keeps_native_slot_vectors",
    "test_target_accept_reject_lifecycle_is_once_and_post_accept_decode_is_stock",
    "test_prior_8192_eager_geometry_exhausts_before_repair_and_target_only_passes",
]
OWNER_DISPOSITION_TESTS = [
    "test_recoverable_prescience_failure_retains_runtime_and_bench",
    "test_unclassified_failure_defaults_to_retained_repair",
    "test_decision_bearing_terminal_persists_before_cleanup_and_release",
    "test_absolute_deadline_remains_cleanup_and_release_backstop",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    partial.replace(path)


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(TEST_COMMAND, cwd=ROOT, text=True, capture_output=True, check=False)
    (ARTIFACT_ROOT / "bound_tests.stdout.log").write_text(completed.stdout)
    (ARTIFACT_ROOT / "bound_tests.stderr.log").write_text(completed.stderr)
    owner = ROOT / "target_only_proxy_allocator_component_owner.py"
    owner_text = owner.read_text()
    required_start = "python3 target_only_proxy_allocator_component_owner.py"
    unittest_output = completed.stdout + completed.stderr
    passed = completed.returncode == 0 and all(name in unittest_output for name in ALLOCATOR_TESTS + OWNER_DISPOSITION_TESTS)
    passed = passed and required_start in owner_text and "deadline_utc" in owner_text and "artifact_root" in owner_text
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "offline_repair_terminal" if passed else "infrastructure_terminal",
        "failure_kind": None if passed else "bound_target_only_contract_failed",
        "binding": BINDING.name,
        "binding_sha256": sha256(BINDING),
        "source": "forward_batch_dual_cache_driver.py",
        "allocator_source_sha256": sha256(ROOT / "forward_batch_dual_cache_driver.py"),
        "owner_source_sha256": sha256(owner),
        "source_sha256_before_repair": json.loads(ALLOCATOR_BINDING.read_text())["repair_contract"]["source_sha256_before_repair"],
        "source_sha256_after_repair": sha256(ROOT / "forward_batch_dual_cache_driver.py"),
        "allocator_tests": ALLOCATOR_TESTS,
        "owner_disposition_tests": OWNER_DISPOSITION_TESTS,
        "test_command": " ".join(TEST_COMMAND),
        "test_returncode": completed.returncode,
        "test_stdout": str(ARTIFACT_ROOT / "bound_tests.stdout.log"),
        "test_stderr": str(ARTIFACT_ROOT / "bound_tests.stderr.log"),
        "future_launcher": {
            "entrypoint": owner.name,
            "entrypoint_sha256": sha256(owner),
            "single_start_command": required_start,
            "requires_new_readmission_binding": True,
            "expired_prior_deadline_absent": "2026-07-26T06:52:00Z" not in owner_text,
        },
        "recoverable_path_runtime_removal_calls": 0,
        "recoverable_path_gpu_pool_release_calls": 0,
        "future_entrypoint": owner.name,
        "future_start_command": required_start,
        "scientific_component_consumed": False,
        "candidate_cuda_invocation_started": False,
        "gpu_claimed": False,
        "provider_contacted": False,
        "additional_provider_spend_usd": 0.0,
        "artifact_root": str(ARTIFACT_ROOT),
    }
    atomic(TERMINAL, payload)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
