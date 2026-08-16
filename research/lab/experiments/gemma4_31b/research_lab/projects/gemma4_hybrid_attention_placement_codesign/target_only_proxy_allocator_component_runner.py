#!/usr/bin/env python3
"""Lifecycle-pure remote TARGET_VERIFY component runner.

The future component command is ``python3 target_only_proxy_allocator_component_runner.py``.
This program deliberately has no claim, heartbeat, cleanup, release, or repair
loop.  The outer owner exclusively owns those lifecycle operations.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
START_COMMAND = "python3 target_only_proxy_allocator_component_runner.py"
SOURCE_FILES = (
    "sitecustomize.py",
    "forward_batch_dual_cache_driver.py",
    "full_model_memory_adapter.py",
    "phase_selective_full_model_remote.py",
    "forward_batch_activation_component.py",
)


def atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    partial.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persist_source_manifest(artifact_root: Path) -> dict[str, str]:
    """Record all bytes staged into the one resident-server consumer."""
    sources = [ROOT / name for name in SOURCE_FILES]
    if any(not path.is_file() for path in sources):
        missing = ", ".join(path.name for path in sources if not path.is_file())
        raise RuntimeError(f"local source missing: {missing}")
    manifest = {path.name: sha256(path) for path in sources}
    atomic(artifact_root / "source_manifest.json", manifest)
    return manifest


def submit_retained_claim_repair(binding: dict[str, Any], binding_path: Path, artifact_root: Path) -> None:
    """Atomically hand the repaired live join to the already-running owner."""
    ready_path = ROOT / "REPAIR_READY.json"
    if not ready_path.is_file():
        raise RuntimeError("retained-claim REPAIR_READY.json is missing")
    ready = json.loads(ready_path.read_text())
    outcome = ready.get("outcome", {})
    if outcome.get("failure_kind") != "server_launch_failed" or outcome.get("scientific_component_consumed"):
        raise RuntimeError("retained-claim repair is not the admitted pre-science server-launch boundary")
    manifest_path = artifact_root / "source_manifest.json"
    request = {
        "schema_version": 1,
        "state": "repair_requested",
        "repair_id": "target-only-live-producer-retrieval-join-20260726t0648z",
        "binding": str(binding_path),
        "runner_sha256": sha256(Path(__file__)),
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256(manifest_path),
        "retry_scope": "live_full_model_producer_consumer_and_retrieval_join_only",
        "scientific_contract_changed": False,
        "scientific_component_consumed": False,
        "candidate_cuda_invocation_started": False,
    }
    atomic(ROOT / "REPAIR_REQUEST.json", request)


def load_binding() -> tuple[dict[str, Any], Path]:
    configured = os.environ.get("HYBRID_TARGET_ONLY_READMISSION_BINDING")
    candidates = [Path(configured)] if configured else sorted(ROOT.glob("DIRECTOR_TARGET_ONLY_PROXY_ALLOCATOR_READMISSION*.json"))
    if len(candidates) != 1 or not candidates[0].is_file():
        raise RuntimeError("one new director target-only readmission binding is required")
    binding_path = candidates[0]
    binding = json.loads(binding_path.read_text())
    required = ("artifact_root", "bench", "bench_connection_identity", "remote_workspace", "runtime_name", "ssh_identity_path")
    missing = [key for key in required if not binding.get(key)]
    if missing:
        raise RuntimeError(f"readmission binding missing {', '.join(missing)}")
    return binding, binding_path


def bench_record(binding: dict[str, Any]) -> dict[str, Any]:
    inventory = json.loads((LAB / "runtime" / "gpus.json").read_text())
    benches = inventory.get("benches", [])
    if isinstance(benches, dict):
        benches = list(benches.values())
    matches = [item for item in benches if item.get("id") == binding["bench"]]
    if len(matches) != 1:
        raise RuntimeError("bound bench is not uniquely present in current inventory")
    return matches[0]


def connection_identity(record: dict[str, Any]) -> dict[str, Any]:
    resource = record.get("resource", {})
    return {
        "bench_id": record.get("id"),
        "instance_id": resource.get("instance_id"),
        "public_ipv4": resource.get("public_ipv4"),
        "ssh_user": resource.get("ssh_user"),
        "known_hosts_namespace": resource.get("known_hosts_namespace"),
        "ssh_ed25519_fingerprint": resource.get("ssh_ed25519_fingerprint"),
    }


def verify_bench_identity(binding: dict[str, Any]) -> dict[str, Any]:
    record = bench_record(binding)
    if binding["bench_connection_identity"] != connection_identity(record):
        raise RuntimeError("bound bench connection identity differs from current inventory")
    return record


@dataclass
class Completed:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Transport(Protocol):
    def remote(self, command: str) -> Completed: ...
    def copy_to(self, files: list[Path], destination: str) -> Completed: ...
    def copy_from(self, source: str, destination: Path) -> Completed: ...


class SshTransport:
    def __init__(self, record: dict[str, Any], identity_path: str):
        resource = record["resource"]
        self.host = f"{resource['ssh_user']}@{resource['public_ipv4']}"
        self.common = ["-i", identity_path, "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20"]

    def remote(self, command: str) -> Completed:
        value = subprocess.run(["ssh", *self.common, self.host, command], text=True, capture_output=True, check=False)
        return Completed(value.returncode, value.stdout, value.stderr)

    def copy_to(self, files: list[Path], destination: str) -> Completed:
        value = subprocess.run(["scp", *self.common, *map(str, files), f"{self.host}:{destination}"], text=True, capture_output=True, check=False)
        return Completed(value.returncode, value.stdout, value.stderr)

    def copy_from(self, source: str, destination: Path) -> Completed:
        destination.mkdir(parents=True, exist_ok=True)
        value = subprocess.run(["scp", *self.common, "-r", f"{self.host}:{source}", str(destination)], text=True, capture_output=True, check=False)
        return Completed(value.returncode, value.stdout, value.stderr)


def evidence_result(artifact_root: Path, stage: str, completed: Completed, *, unsafe: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1, "classification": "infrastructure_terminal", "failure_kind": f"{stage}_failed",
        "stage": stage, "returncode": completed.returncode, "guest_unsafe": unsafe,
        "scientific_component_consumed": False, "candidate_cuda_invocation_started": False,
        "interpretable_component_result": False,
    }


def result_from_retrieval(artifact_root: Path, consumer_returncode: int) -> dict[str, Any]:
    # ``scp -r remote/artifact local/retrieved`` copies the source directory,
    # so the live records are under ``retrieved/artifact``.  The earlier fake
    # transport omitted that directory and made the consumer inspect a layout
    # that never occurs on the claimed bench.
    retrieved = artifact_root / "retrieved" / "artifact"
    terminal = retrieved / "forward-batch-activation-c32" / "TERMINAL.json"
    invocation = retrieved / "forward-batch-activation-c32" / "INVOCATION.json"
    producer = retrieved / "forward_batch_dual_cache.json"
    adapter = retrieved / "adapter_attach.json"
    if not all(path.is_file() for path in (terminal, invocation, producer, adapter)):
        return {"schema_version": 1, "classification": "infrastructure_terminal", "failure_kind": "component_evidence_missing",
                "consumer_returncode": consumer_returncode, "scientific_component_consumed": False,
                "candidate_cuda_invocation_started": False, "interpretable_component_result": False}
    try:
        target = json.loads(terminal.read_text())
        invocation_value = json.loads(invocation.read_text())
        producer_value = json.loads(producer.read_text())
        adapter_value = json.loads(adapter.read_text())
    except json.JSONDecodeError:
        return {"schema_version": 1, "classification": "infrastructure_terminal", "failure_kind": "component_evidence_corrupt",
                "scientific_component_consumed": False, "candidate_cuda_invocation_started": False,
                "interpretable_component_result": False}
    # The activation script deliberately labels itself non-decision-bearing.
    # Its persisted submission/result facts become decision evidence only when
    # joined to the actual resident ModelRunner ForwardBatch record, rather
    # than to fixture-only ``target_logit_consumer`` fields.
    consumed = bool(invocation_value.get("science_started") and invocation_value.get("submitted_requests") == 32)
    cuda_started = bool(target.get("candidate_cuda_invocation_started") and target.get("complete", 0) > 0)
    complete = bool(
        consumer_returncode == 0
        and target.get("kind") == "activation_only_not_component_decision"
        and target.get("complete") == 32
        and target.get("accepted_request_observed") is True
        and producer_value.get("mode") == "TARGET_VERIFY"
        and producer_value.get("logical_rows") == 384
        and producer_value.get("padded_rows_cache_inert") is True
        and producer_value.get("cache_policy") == "production_dual_allocator_shadow_write_accept_move_reject_free"
        and producer_value.get("first_target_consumer") == "NGRAMWorker.forward_batch_generation"
        and adapter_value.get("attached") is True
        and adapter_value.get("one_resident_target_model") is True
    )
    return {"schema_version": 1, "classification": target.get("classification", "component_execution_record"),
            "failure_kind": target.get("failure_kind"), "consumer_returncode": consumer_returncode,
            "scientific_component_consumed": consumed, "candidate_cuda_invocation_started": cuda_started,
            "interpretable_component_result": complete, "target_terminal": target, "invocation": invocation_value,
            "live_forward_batch_producer": producer_value, "live_adapter_attach": adapter_value,
            "retrieval_layout": "retrieved/artifact"}


def run_component(binding: dict[str, Any], artifact_root: Path, transport: Transport, record: dict[str, Any]) -> dict[str, Any]:
    """Run only remote component stages; serialize typed evidence for the owner."""
    workspace = str(binding["remote_workspace"])
    runtime = str(binding["runtime_name"])
    sources = [ROOT / name for name in SOURCE_FILES]
    try:
        manifest = persist_source_manifest(artifact_root)
    except RuntimeError:
        missing = [path.name for path in sources if not path.is_file()]
        return {"schema_version": 1, "classification": "infrastructure_terminal", "failure_kind": "local_source_missing",
                "missing": missing, "scientific_component_consumed": False, "candidate_cuda_invocation_started": False,
                "interpretable_component_result": False}
    program = binding.get("component_program")
    if not isinstance(program, dict) or not all(program.get(key) for key in ("server_launch_command", "readiness_command", "target_verify_command")):
        return {"schema_version": 1, "classification": "infrastructure_terminal", "failure_kind": "live_component_program_missing",
                "scientific_component_consumed": False, "candidate_cuda_invocation_started": False,
                "interpretable_component_result": False}
    stages = (
        ("remote_prepare", lambda: transport.remote(f"set -eu; mkdir -p {shlex.quote(workspace)}/source {shlex.quote(workspace)}/artifact")),
        ("source_copy", lambda: transport.copy_to(sources, f"{workspace}/source/")),
        ("server_launch", lambda: transport.remote(str(program["server_launch_command"]))),
        ("readiness", lambda: transport.remote(str(program["readiness_command"]))),
        ("target_verify_consumer", lambda: transport.remote(str(program["target_verify_command"]))),
        ("artifact_retrieval", lambda: transport.copy_from(f"{workspace}/artifact", artifact_root / "retrieved")),
    )
    consumer_rc = 0
    for stage, invoke in stages:
        completed = invoke()
        (artifact_root / f"{stage}.stdout.log").write_text(completed.stdout)
        (artifact_root / f"{stage}.stderr.log").write_text(completed.stderr)
        if stage == "target_verify_consumer":
            consumer_rc = completed.returncode
        if completed.returncode:
            return evidence_result(artifact_root, stage, completed)
    return result_from_retrieval(artifact_root, consumer_rc)


def main() -> int:
    try:
        binding, binding_path = load_binding()
        record = verify_bench_identity(binding)
    except RuntimeError as exc:
        print(f"target-only component runner preflight: {exc}", file=os.sys.stderr)
        return 2
    artifact_root = Path(binding["artifact_root"])
    if "--manifest-only" in sys.argv[1:]:
        persist_source_manifest(artifact_root)
        return 0
    if "--repair-request" in sys.argv[1:]:
        persist_source_manifest(artifact_root)
        submit_retained_claim_repair(binding, binding_path, artifact_root)
        return 0
    result = run_component(binding, artifact_root, SshTransport(record, str(binding["ssh_identity_path"])), record)
    atomic(artifact_root / "COMPONENT_RESULT.json", result)
    return 0 if result.get("interpretable_component_result") else 2


if __name__ == "__main__":
    raise SystemExit(main())
