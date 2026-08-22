#!/usr/bin/env python3
"""R7 retained H200 owner: dispatch the sole unconsumed NGRAM arm."""
from __future__ import annotations

import argparse
import pathlib

import dflash_component_direct_recovery_owner_r2 as dispatcher
import dflash_component_owner as base
import dflash_component_replacement_owner as retrieval


PROJECT = pathlib.Path(__file__).resolve().parent
DIRECTOR = PROJECT / "DIRECTOR_DFLASH_R7_NGRAM_FLASHINFER_WARM_EXECUTION_20260730T0325Z.json"
PACKET = PROJECT / "artifacts/dflash-h200-r6-ngram-flashinfer-repair/dflash-component-ngram-flashinfer-repair-packet.tar"


def require(value: dict, fields: dict, kind: str) -> None:
    for key, expected in fields.items():
        if value.get(key) != expected:
            raise base.Boundary(kind, f"{key}_mismatch", False)


def dispatch_repair(root, binding, diagnostic, deadline):
    attempt = 0
    while base.utc_now() < deadline:
        repair_id = f"{binding['repair_namespace']}-worker-7-repair-{attempt}"
        request = base.repair_wait(root, diagnostic, "classify", deadline, repair_id)
        if request is None:
            return "deadline", None
        if "_repair_terminal" in request:
            return "repair_terminal", None
        try:
            return "valid", retrieval.validated_continuation_patch(
                request, diagnostic, binding, "classify"
            )
        except base.Boundary as error:
            diagnostic = root / f"R7_REQUEST_REJECTION_{attempt}.json"
            base.atomic(diagnostic, {
                "classification": "rejected_repair_request", "kind": error.kind,
                "message": error.message, "retry_scope": "classify", "worker_generation": 7,
            })
            attempt += 1
    return "deadline", None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    binding = base.load(args.execution_binding.resolve())
    director = base.load(DIRECTOR)
    require(binding, {
        "schema_version": 1, "project": base.PROJECT_NAME,
        "bench_id": director["bench"]["id"], "gpu_uuid": director["bench"]["gpu_uuid"],
        "director_sha256": base.sha256(DIRECTOR), "owner_source": pathlib.Path(__file__).name,
        "owner_source_sha256": base.sha256(pathlib.Path(__file__)), "initial_worker_generation": 7,
        "retry_scope": "classify", "packet_archive_sha256": director["immutable_inputs"]["packet_archive_sha256"],
        "remote_run": director["immutable_inputs"]["remote_run"],
        "remote_target_path": director["immutable_inputs"]["remote_target_path"],
        "target_manifest_sha256": director["immutable_inputs"]["target_manifest_sha256"],
        "repair_namespace": director["owner_contract"]["repair_namespace"],
    }, "r7_execution_boundary")
    if base.sha256(PACKET) != binding["packet_archive_sha256"]:
        raise base.Boundary("r7_packet_boundary", "digest", False)
    root = args.artifact_root.resolve(); root.mkdir(parents=True, exist_ok=True)
    deadline = base.parse_time(binding["owner_deadline_utc"])
    bench = base.validate_claim(binding)
    if base.utc_now() >= deadline:
        raise base.Boundary("typed_deadline_boundary", "owner_deadline_passed", False)
    remote = base.Remote(bench, root, deadline)
    with base.Heartbeat(root, binding["claimed_at"]):
        base.atomic(root / "PHASE.json", {
            "phase": "ngram_only_worker_7_dispatching", "claimed_at": binding["claimed_at"],
            "packet_archive_sha256": binding["packet_archive_sha256"], "retry_scope": "classify",
        })
        snapshot, adoption, diagnostic = dispatcher.worker(
            remote, binding, {"remote_run": binding["remote_run"]}, PACKET, root, 7, "classify", deadline
        )
        if adoption["classification"] == "scientific_terminal":
            # R7 is admitted against the director's cumulative $18 cap, not R1's retired cap.
            base.AUTHORIZED_USD = 18.0
            return retrieval.finalize_terminal(binding, root, snapshot)
        disposition, _ = dispatch_repair(root, binding, diagnostic, deadline)
        base.atomic(root / "R7_RETAINED_BOUNDARY.json", {
            "classification": f"r7_{disposition}", "retry_scope": "classify",
            "worker_generation": 7, "claimed_at": binding["claimed_at"],
        })
        return 77


if __name__ == "__main__":
    raise SystemExit(main())
