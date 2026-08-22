#!/usr/bin/env python3
"""Dispatcher-capable same-claim recovery owner; initial work is worker 3 only."""
from __future__ import annotations

import argparse
import pathlib
import shlex

import dflash_component_owner as base
import dflash_component_replacement_owner as retrieval

PROJECT = pathlib.Path(__file__).resolve().parent
DIRECTOR = PROJECT / "DIRECTOR_DFLASH_R2_CONSUMED_REPAIR3_OWNERLESS_RECOVERY_20260730T0015Z.json"
ARMS = ("ar", "dflash", "ngram")

def require(value, fields, kind):
    for key, expected in fields.items():
        if value.get(key) != expected:
            raise base.Boundary(kind, f"{key}_mismatch", False)

def contract():
    value = base.load(DIRECTOR)
    require(value, {"schema_version": 1, "project": base.PROJECT_NAME,
                    "decision": "prepare_ownerless_same_claim_consumed_repair3_recovery"},
            "recovery_r2_binding_boundary")
    return value

def verify_local(value):
    b = value["consumed_repair"]
    paths = {k: PROJECT / b[k] for k in ("adoption", "consumed_request", "patch")}
    for key, digest in (("adoption", "adoption_sha256"), ("consumed_request", "consumed_request_sha256"), ("patch", "patch_sha256")):
        if base.sha256(paths[key]) != b[digest]:
            raise base.Boundary("recovery_r2_binding_boundary", f"{key}_digest", False)
    adoption, request, patch = (base.load(paths[k]) for k in ("adoption", "consumed_request", "patch"))
    require(adoption, {"classification": "classified_persisted_attempt", "continuation_allowed": True,
                       "retry_scope": b["retry_scope"]}, "recovery_r2_adoption_boundary")
    if adoption["snapshot_manifest"]["manifest_sha256"] != b["snapshot_manifest_sha256"] or any(adoption[x][a] for x in ("science_started", "science_consumed") for a in ARMS):
        raise base.Boundary("recovery_r2_adoption_boundary", "science_or_manifest", False)
    require(request, {"schema_version": 1, "state": "repair_requested", "repair_id": b["repair_id"], "retry_scope": b["retry_scope"]}, "recovery_r2_request_boundary")
    require(patch, {"schema_version": 1, "continuation_authorized": True, "claim_generation": value["claim"]["claimed_at"],
                    "adoption_sha256": b["adoption_sha256"], "retry_scope": b["retry_scope"],
                    "packet_archive_sha256": b["packet_archive_sha256"]}, "recovery_r2_patch_boundary")
    archive = pathlib.Path(patch["packet_archive"])
    if base.sha256(archive) != b["packet_archive_sha256"]:
        raise base.Boundary("recovery_r2_patch_boundary", "packet_digest", False)
    return b, archive

def worker(remote, binding, boundary, archive, root, number, scope, deadline):
    packet, _ = base.stage_packet(remote, archive, base.sha256(archive))
    result = remote.run(
        f"python3 {shlex.quote(packet + '/dflash_component_worker.py')} --packet-root {shlex.quote(packet)} "
        f"--remote-root {shlex.quote(boundary['remote_run'])} --target-source {shlex.quote(binding['remote_target_path'])} "
        f"--deadline-epoch {deadline.timestamp()} --generation {shlex.quote(str(binding['generation']) + '-recovery' + str(number))} --retry-scope {shlex.quote(scope)}",
        f"recovery-r2-worker-{number}", cap=max(60, int((deadline-base.utc_now()).total_seconds()-120)), check=False)
    base.atomic(root / f"RECOVERY_R2_WORKER_{number}.json", {"worker_generation": number, "retry_scope": scope, "returncode": result.returncode})
    snapshot, receipt = retrieval.package_and_retrieve_outside_tree(remote, boundary["remote_run"], root, number + 100)
    adoption = retrieval.classify_snapshot(snapshot)
    adoption.update({"worker_generation": number, "worker_returncode": result.returncode, "receipt": receipt})
    path = root / f"RECOVERY_R2_ADOPTION_{number}.json"
    base.atomic(path, adoption)
    return snapshot, adoption, path

def dispatch_repair(root, binding, diagnostic, retry_scope, deadline, worker_generation):
    """Wait until one newly validated request authorizes the next worker.

    A rejected request is itself a recoverable diagnostic, not authority to
    execute or advance.  Each loop iteration therefore owns a fresh repair ID.
    """
    current_diagnostic, current_scope, attempt = diagnostic, retry_scope, 0
    while base.utc_now() < deadline:
        repair_id = f"{binding['generation']}-recovery-r2-{worker_generation}-dispatch-{attempt}"
        request = base.repair_wait(root, current_diagnostic, current_scope, deadline, repair_id)
        if request is None:
            return "deadline", None, None
        if "_repair_terminal" in request:
            path = root / f"RECOVERY_R2_REPAIR_TERMINAL_{worker_generation}_{attempt}.json"
            base.atomic(path, request["_repair_terminal"])
            return "repair_terminal", None, path
        try:
            patch = retrieval.validated_continuation_patch(request, current_diagnostic, binding, current_scope)
            return "valid", patch, current_diagnostic
        except base.Boundary as error:
            current_diagnostic = root / f"RECOVERY_R2_REQUEST_REJECTION_{worker_generation}_{attempt}.json"
            base.atomic(current_diagnostic, {
                "classification": "rejected_repair_request",
                "kind": error.kind,
                "message": error.message,
                "worker_generation": worker_generation,
                "request_consumed_path": request.get("_consumed_path"),
                "retry_scope": "classify",
            })
            current_scope, attempt = "classify", attempt + 1
    return "deadline", None, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    value = contract(); boundary, archive = verify_local(value)
    binding = base.load(args.recovery_execution_binding.resolve())
    require(binding, {"schema_version": 1, "project": base.PROJECT_NAME, "bench_id": value["claim"]["bench_id"],
                      "claimed_at": value["claim"]["claimed_at"], "gpu_uuid": value["claim"]["gpu_uuid"],
                      "recovery_binding_sha256": base.sha256(DIRECTOR), "worker_generation": 3,
                      "packet_archive_sha256": base.sha256(archive)}, "recovery_r2_execution_boundary")
    root = args.artifact_root.resolve(); root.mkdir(parents=True, exist_ok=True)
    adopted = root / "RECOVERY_R2_CONSUMED_REPAIR3_ADOPTED.json"
    marker = {"repair_id": boundary["repair_id"], "consumed_request_sha256": boundary["consumed_request_sha256"],
              "patch_sha256": boundary["patch_sha256"], "packet_archive_sha256": base.sha256(archive), "worker_generation": 3}
    if adopted.exists() and base.load(adopted) != marker:
        raise base.Boundary("recovery_r2_adoption_boundary", "adoption_marker_mismatch", False)
    base.atomic(adopted, marker)
    bench = base.validate_claim(binding); deadline = base.parse_time(binding["owner_deadline_utc"])
    if base.utc_now() >= deadline: raise base.Boundary("typed_deadline_boundary", "owner_deadline_passed", False)
    remote = base.Remote(bench, root, deadline)
    with base.Heartbeat(root, binding["claimed_at"]):
        snap, receipt = retrieval.package_and_retrieve_outside_tree(remote, boundary["remote_run"], root, 99)
        initial = retrieval.classify_snapshot(snap)
        if initial["snapshot_manifest"]["manifest_sha256"] != boundary["snapshot_manifest_sha256"] or not initial.get("continuation_allowed"):
            raise base.Boundary("recovery_r2_remote_snapshot_boundary", "initial_adoption", False)
        number, scope = 3, boundary["retry_scope"]
        while base.utc_now() < deadline:
            snap, adoption, diagnostic = worker(remote, binding, boundary, archive, root, number, scope, deadline)
            if adoption["classification"] == "scientific_terminal":
                return retrieval.finalize_terminal(binding, root, snap)
            disposition, patch, terminal_path = dispatch_repair(
                root, binding, diagnostic, str(adoption.get("retry_scope", "classify")), deadline, number)
            if disposition == "valid":
                archive = pathlib.Path(patch["packet_archive"])
                scope = str(patch["retry_scope"])
                number += 1
                continue
            state = "maintenance_recovery_r2_repair_terminal" if disposition == "repair_terminal" else "maintenance_recovery_r2_deadline"
            summary = "Recovery r2 adopted a repair terminal without replaying a worker." if disposition == "repair_terminal" else "Recovery r2 reached deadline without a scientific terminal."
            base.release(binding, root, condition="maintenance", summary=summary, state=state)
            return 77
        base.release(binding, root, condition="maintenance", summary="Recovery r2 reached deadline without a scientific terminal.", state="maintenance_recovery_r2_deadline")
        return 77

if __name__ == "__main__":
    raise SystemExit(main())
