#!/usr/bin/env python3
"""Bounded owner for a future director-readmitted target-only component.

The direct start command is ``python3 target_only_proxy_allocator_component_owner.py``.
It intentionally contains no current host, deadline, or artifact root: a new
director binding supplies all of them.  Recoverable and unclassified
pre-science outcomes retain the warm claim and emit the standard repair
handshake.  Runtime removal and pool release exist only in explicitly selected
terminal cleanup or the absolute-deadline backstop.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from target_only_proxy_allocator_component_runner import (
    START_COMMAND as COMPONENT_COMMAND,
    verify_bench_identity,
)


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
START_COMMAND = "python3 target_only_proxy_allocator_component_owner.py"
REPAIR_READY = "REPAIR_READY.json"
REPAIR_REQUEST = "REPAIR_REQUEST.json"


def atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    partial.replace(path)


def load_binding() -> tuple[dict[str, Any], Path]:
    configured = os.environ.get("HYBRID_TARGET_ONLY_READMISSION_BINDING")
    candidates = [Path(configured)] if configured else sorted(ROOT.glob("DIRECTOR_TARGET_ONLY_PROXY_ALLOCATOR_READMISSION*.json"))
    if len(candidates) != 1 or not candidates[0].is_file():
        raise RuntimeError("one new director target-only readmission binding is required")
    binding_path = candidates[0]
    binding = json.loads(binding_path.read_text())
    required = ("artifact_root", "deadline_utc", "bench", "source_sha256", "owner_entrypoint", "component_runner")
    missing = [key for key in required if not binding.get(key)]
    if missing:
        raise RuntimeError(f"readmission binding missing {', '.join(missing)}")
    source_hash = hashlib.sha256((ROOT / "forward_batch_dual_cache_driver.py").read_bytes()).hexdigest()
    if binding["source_sha256"] != source_hash:
        raise RuntimeError("readmission binding source hash does not match installed target-only driver")
    owner = binding["owner_entrypoint"]
    runner = binding["component_runner"]
    for entrypoint, expected_path, expected_command in ((owner, Path(__file__).name, START_COMMAND), (runner, "target_only_proxy_allocator_component_runner.py", COMPONENT_COMMAND)):
        if not isinstance(entrypoint, dict) or entrypoint.get("path") != str(expected_path):
            raise RuntimeError("readmission binding entrypoint path is not the admitted component seam")
        if entrypoint.get("command") != expected_command:
            raise RuntimeError("readmission binding entrypoint command is not the admitted future command")
        installed = ROOT / str(expected_path)
        if entrypoint.get("sha256") != hashlib.sha256(installed.read_bytes()).hexdigest():
            raise RuntimeError("readmission binding entrypoint hash does not match installed bytes")
    artifact_root = Path(binding["artifact_root"])
    if not artifact_root.is_absolute():
        raise RuntimeError("readmission artifact_root must be absolute")
    if deadline_reached(binding["deadline_utc"]):
        raise RuntimeError("readmission deadline is already expired")
    # This reads only the local shared inventory.  It runs before pool_claim.
    verify_bench_identity(binding)
    return binding, binding_path


def deadline_reached(deadline_utc: str) -> bool:
    return datetime.now(timezone.utc) >= datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))


class OwnerActions:
    """Small side-effect boundary; tests use this class's call ledger only."""

    def __init__(self, artifact_root: Path, binding: dict[str, Any], binding_path: Path):
        self.artifact_root, self.binding, self.binding_path = artifact_root, binding, binding_path
        self.runtime_removal_calls = 0
        self.gpu_pool_release_calls = 0
        self.events: list[str] = []

    def persist_repair_ready(self, outcome: dict[str, Any]) -> None:
        self.events.append("repair_ready_persisted")
        atomic(ROOT / REPAIR_READY, {
            "schema_version": 1,
            "phase": "retained_repair",
            "binding": str(self.binding_path),
            "artifact_root": str(self.artifact_root),
            "deadline_utc": self.binding["deadline_utc"],
            "outcome": outcome,
            "science_started": False,
            "scientific_component_consumed": False,
        })

    def persist_disposition(self, disposition: str, outcome: dict[str, Any]) -> None:
        self.events.append("disposition_persisted")
        atomic(self.artifact_root / "OWNER_DISPOSITION.json", {
            "schema_version": 1,
            "disposition": disposition,
            "binding": str(self.binding_path),
            "outcome": outcome,
        })

    def remove_runtime(self) -> None:
        self.events.append("runtime_removed")
        self.runtime_removal_calls += 1
        command = self.binding.get("runtime_cleanup_command")
        if command:
            subprocess.run(command, cwd=ROOT, shell=True, text=True, check=False)

    def release_bench(self) -> None:
        self.events.append("bench_released")
        self.gpu_pool_release_calls += 1
        subprocess.run(
            [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "release", "--project", PROJECT, "--bench", str(self.binding["bench"])],
            text=True, capture_output=True, check=False,
        )


def select_disposition(outcome: dict[str, Any], *, absolute_deadline: bool = False) -> str:
    """Choose a lifecycle branch from evidence, never from a generic failure."""
    if absolute_deadline:
        return "absolute_deadline_cleanup"
    if outcome.get("scientific_component_consumed") or outcome.get("interpretable_component_result"):
        return "decision_bearing_terminal_cleanup"
    if outcome.get("guest_unsafe") or outcome.get("guest_unreachable"):
        return "safety_terminal_cleanup"
    # Ordinary, pre-science, and unknown states all retain the warm boundary.
    return "retained_repair"


def apply_disposition(actions: OwnerActions, outcome: dict[str, Any], *, absolute_deadline: bool = False) -> str:
    disposition = select_disposition(outcome, absolute_deadline=absolute_deadline)
    if disposition == "retained_repair":
        actions.persist_repair_ready(outcome)
        return disposition
    # Persist the decision before either destructive lifecycle operation.
    actions.persist_disposition(disposition, outcome)
    actions.remove_runtime()
    actions.release_bench()
    return disposition


def pool_claim(binding: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "claim", "--project", PROJECT, "--bench", str(binding["bench"])],
        text=True, capture_output=True, check=False,
    )


def heartbeat(binding: dict[str, Any], stop: threading.Event) -> None:
    while not stop.wait(45):
        subprocess.run(
            [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "heartbeat", "--project", PROJECT, "--bench", str(binding["bench"])],
            text=True, capture_output=True, check=False,
        )


def run_component(binding: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    command = binding["component_runner"]["command"]
    completed = subprocess.run(command, cwd=ROOT, shell=True, text=True, capture_output=True, check=False)
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "component.stdout.log").write_text(completed.stdout)
    (artifact_root / "component.stderr.log").write_text(completed.stderr)
    result_path = artifact_root / "COMPONENT_RESULT.json"
    if result_path.is_file():
        return json.loads(result_path.read_text())
    return {"kind": "unclassified_component_exit", "returncode": completed.returncode, "scientific_component_consumed": False}


def main() -> int:
    try:
        binding, binding_path = load_binding()
    except RuntimeError as exc:
        print(f"target-only owner preflight: {exc}", file=sys.stderr)
        return 2
    artifact_root = Path(binding["artifact_root"])
    claim = pool_claim(binding)
    if claim.returncode:
        atomic(artifact_root / "TARGET_ONLY_PROXY_ALLOCATOR_COMPONENT_TERMINAL.json", {
            "schema_version": 1, "classification": "infrastructure_terminal", "failure_kind": "atomic_claim_failed",
            "binding": str(binding_path), "scientific_component_consumed": False,
        })
        return 2

    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(binding, stop), daemon=True)
    thread.start()
    actions = OwnerActions(artifact_root, binding, binding_path)
    outcome = run_component(binding, artifact_root)
    disposition = apply_disposition(actions, outcome)
    while disposition == "retained_repair" and not deadline_reached(binding["deadline_utc"]):
        request = ROOT / REPAIR_REQUEST
        if request.is_file():
            request.unlink()
            outcome = run_component(binding, artifact_root)
            disposition = apply_disposition(actions, outcome)
            continue
        time.sleep(2)
    if disposition == "retained_repair":
        disposition = apply_disposition(actions, outcome, absolute_deadline=True)
    stop.set()
    thread.join(timeout=2)
    return 0 if disposition == "decision_bearing_terminal_cleanup" else 2


if __name__ == "__main__":
    raise SystemExit(main())
