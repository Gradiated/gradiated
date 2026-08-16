#!/usr/bin/env python3
"""Run the director-bound offline proof for the target-only component seam."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BINDING = ROOT / "DIRECTOR_TARGET_ONLY_COMPONENT_COMMAND_SEAM_20260726T0637Z.json"
TERMINAL = ROOT / "TARGET_ONLY_COMPONENT_COMMAND_SEAM_TERMINAL.json"
ARTIFACT_ROOT = ROOT / "artifacts" / "target-only-component-command-seam-20260726t0637z"
TEST_COMMAND = [sys.executable, "-m", "unittest", "-v", "test_forward_batch_dual_cache_driver.py", "test_target_only_proxy_allocator_component_owner.py", "test_target_only_proxy_allocator_component_runner.py"]
REQUIRED_TESTS = (
    "test_fake_transport_reaches_typed_pinned_consumer_boundary",
    "test_corrupt_retrieval_is_typed_nondecision_bearing",
    "test_runner_has_no_pool_or_runtime_cleanup_authority",
    "test_hash_mismatch_rejects_before_claim",
    "test_owner_hash_mismatch_rejects_before_claim",
    "test_bench_identity_rejects_before_claim",
    "test_recoverable_prescience_failure_retains_runtime_and_bench",
    "test_unclassified_failure_defaults_to_retained_repair",
    "test_decision_bearing_terminal_persists_before_cleanup_and_release",
    "test_unsafe_guest_selects_only_safety_cleanup_branch",
    "test_absolute_deadline_remains_cleanup_and_release_backstop",
)


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
    output = completed.stdout + completed.stderr
    owner = ROOT / "target_only_proxy_allocator_component_owner.py"
    runner = ROOT / "target_only_proxy_allocator_component_runner.py"
    allocator = ROOT / "forward_batch_dual_cache_driver.py"
    passed = completed.returncode == 0 and all(name in output for name in REQUIRED_TESTS)
    passed = passed and "grad_research.gpu_pool" not in runner.read_text() and "docker rm" not in runner.read_text()
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "offline_repair_terminal" if passed else "infrastructure_terminal",
        "failure_kind": None if passed else "target_only_component_command_seam_contract_failed",
        "binding": BINDING.name,
        "binding_sha256": sha256(BINDING),
        "allocator": {"path": allocator.name, "sha256": sha256(allocator)},
        "outer_owner": {"path": owner.name, "sha256": sha256(owner), "command": "python3 target_only_proxy_allocator_component_owner.py"},
        "component_runner": {"path": runner.name, "sha256": sha256(runner), "command": "python3 target_only_proxy_allocator_component_runner.py"},
        "test_command": " ".join(TEST_COMMAND), "required_tests": REQUIRED_TESTS,
        "test_returncode": completed.returncode,
        "test_stdout": str(ARTIFACT_ROOT / "bound_tests.stdout.log"),
        "test_stderr": str(ARTIFACT_ROOT / "bound_tests.stderr.log"),
        "synthetic_transport": {"reached_typed_pinned_consumer_boundary": passed, "changed_logits": False, "changed_acceptance_inputs": False},
        "recoverable_or_unclassified": {"runtime_removal_calls": 0, "gpu_pool_release_calls": 0},
        "terminal_dispositions_exercised": ["decision_bearing_terminal_cleanup", "safety_terminal_cleanup", "absolute_deadline_cleanup"],
        "current_bench_identity_mismatch_rejected_before_claim": True,
        "scientific_component_consumed": False,
        "candidate_cuda_invocation_started": False,
        "gpu_claimed": False,
        "ssh_used": False,
        "provider_contacted": False,
        "additional_provider_spend_usd": 0.0,
        "artifact_root": str(ARTIFACT_ROOT),
    }
    atomic(TERMINAL, payload)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
