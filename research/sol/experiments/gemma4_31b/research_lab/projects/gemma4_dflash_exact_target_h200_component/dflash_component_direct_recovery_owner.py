#!/usr/bin/env python3
"""One-shot, same-claim recovery owner for the lost r2 direct owner."""

from __future__ import annotations

import argparse
import pathlib
import shlex

import dflash_component_owner as base
import dflash_component_replacement_owner as retrieval


PROJECT = pathlib.Path(__file__).resolve().parent
PROJECT_NAME = base.PROJECT_NAME
DIRECTOR = PROJECT / "DIRECTOR_DFLASH_R2_LOST_OWNER_RECOVERY_20260730T0002Z.json"


def require(value: dict, fields: dict, kind: str) -> None:
    for key, expected in fields.items():
        if value.get(key) != expected:
            raise base.Boundary(kind, f"{key}_mismatch", False)


def recovery_contract() -> dict:
    value = base.load(DIRECTOR)
    require(value, {"schema_version": 1, "project": PROJECT_NAME,
                    "decision": "prepare_exact_same_claim_lost_owner_recovery"},
            "recovery_binding_boundary")
    return value


def verify_local(contract: dict) -> tuple[pathlib.Path, dict]:
    boundary = contract["recovery_boundary"]
    paths = {key: PROJECT / boundary[key] for key in ("adoption", "repair_ready", "consumed_request", "patch")}
    digests = {"adoption": "adoption_sha256", "repair_ready": "repair_ready_sha256",
               "consumed_request": "consumed_request_sha256", "patch": "patch_sha256"}
    for key, path in paths.items():
        if base.sha256(path) != boundary[digests[key]]:
            raise base.Boundary("recovery_binding_boundary", f"{key}_digest", False)
    adoption = base.load(paths["adoption"])
    require(adoption, {"classification": "classified_persisted_attempt", "continuation_allowed": True,
                       "retry_scope": boundary["retry_scope"], "science_started": contract["immutable_science"]["science_started"],
                       "science_consumed": contract["immutable_science"]["science_consumed"]}, "recovery_adoption_boundary")
    if adoption["snapshot_manifest"]["manifest_sha256"] != boundary["snapshot_manifest_sha256"]:
        raise base.Boundary("recovery_adoption_boundary", "snapshot_manifest", False)
    request, patch = base.load(paths["consumed_request"]), base.load(paths["patch"])
    require(request, {"state": "repair_requested", "retry_scope": boundary["retry_scope"]}, "recovery_request_boundary")
    require(patch, {"continuation_authorized": True, "retry_scope": boundary["retry_scope"],
                    "adoption_sha256": boundary["adoption_sha256"], "packet_archive_sha256": boundary["packet_archive_sha256"]},
            "recovery_patch_boundary")
    archive = pathlib.Path(patch["packet_archive"])
    if base.sha256(archive) != boundary["packet_archive_sha256"]:
        raise base.Boundary("recovery_patch_boundary", "packet_archive", False)
    return archive, boundary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    contract = recovery_contract()
    archive, boundary = verify_local(contract)
    binding = base.load(args.recovery_execution_binding.resolve())
    require(binding, {"schema_version": 1, "project": PROJECT_NAME,
                      "decision": "run_r2_lost_owner_recovery", "claimed_at": contract["claim"]["claimed_at"],
                      "bench_id": contract["claim"]["bench_id"], "gpu_uuid": contract["claim"]["gpu_uuid"],
                      "recovery_binding_sha256": base.sha256(DIRECTOR), "worker_generation": 2,
                      "packet_archive_sha256": boundary["packet_archive_sha256"]}, "recovery_execution_boundary")
    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    bench = base.validate_claim(binding)
    deadline = base.parse_time(binding["owner_deadline_utc"])
    if base.utc_now() >= deadline:
        raise base.Boundary("typed_deadline_boundary", "owner_deadline_passed", False)
    remote = base.Remote(bench, artifact_root, deadline)
    remote_run = boundary["remote_run"]
    with base.Heartbeat(artifact_root, binding["claimed_at"]):
        snapshot, receipt = retrieval.package_and_retrieve_outside_tree(remote, remote_run, artifact_root, 2)
        adoption = retrieval.classify_snapshot(snapshot)
        if adoption["snapshot_manifest"]["manifest_sha256"] != boundary["snapshot_manifest_sha256"]:
            raise base.Boundary("recovery_remote_snapshot_boundary", "manifest", False)
        base.atomic(artifact_root / "RECOVERY_ADOPTION_2_PRE.json", {**adoption, "receipt": receipt})
        packet_root, _ = base.stage_packet(remote, archive, boundary["packet_archive_sha256"])
        worker = remote.run(
            f"python3 {shlex.quote(packet_root + '/dflash_component_worker.py')} --packet-root {shlex.quote(packet_root)} "
            f"--remote-root {shlex.quote(remote_run)} --target-source {shlex.quote(binding['remote_target_path'])} "
            f"--deadline-epoch {deadline.timestamp()} --generation {shlex.quote(str(binding['generation']) + '-recovery2')} --retry-scope all",
            "recovery-worker-2", cap=max(60, int((deadline - base.utc_now()).total_seconds() - 120)), check=False)
        base.atomic(artifact_root / "RECOVERY_WORKER_2.json", {"returncode": worker.returncode, "worker_generation": 2})
        snapshot, receipt = retrieval.package_and_retrieve_outside_tree(remote, remote_run, artifact_root, 3)
        adoption = retrieval.classify_snapshot(snapshot)
        base.atomic(artifact_root / "RECOVERY_ADOPTION_2_POST.json", {**adoption, "receipt": receipt, "worker_returncode": worker.returncode})
        if adoption["classification"] == "scientific_terminal":
            component = base.validate_scientific_terminal(snapshot)
            base.atomic(PROJECT / "DFLASH_H200_COMPONENT_TERMINAL.json", component)
            _, spend = base.claim_exposure(binding)
            base.update_status(status="completed", decision=component["classification"], summary="Recovery owner retrieved validated component terminal.", actual_spend_usd=spend, terminal_artifact="DFLASH_H200_COMPONENT_TERMINAL.json")
            base.release(binding, artifact_root, condition="ready", summary="Recovery terminal validated.", state="available_quiescent_after_dflash_component")
            return 0
        diagnostic = artifact_root / "RECOVERY_ADOPTION_2_POST.json"
        base.repair_wait(artifact_root, diagnostic, str(adoption.get("retry_scope", "classify")), deadline, f"{binding['generation']}-recovery-3")
    return 77


if __name__ == "__main__":
    raise SystemExit(main())
