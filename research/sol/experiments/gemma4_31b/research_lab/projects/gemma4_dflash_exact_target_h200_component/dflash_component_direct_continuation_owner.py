#!/usr/bin/env python3
"""Fresh-claim DFlash continuation owner with no repair-wait transition.

This owner retrieves and classifies the retained run before it reads a direct
continuation authority.  It never enters the generic repair waiter: a future
director must bind one exact fresh claim and the known unconsumed adoption.
"""

from __future__ import annotations

import argparse
import pathlib
import shlex
from typing import Any

import dflash_component_owner as base
import dflash_component_replacement_owner as retrieval


PROJECT = pathlib.Path(__file__).resolve().parent
PROJECT_NAME = base.PROJECT_NAME
ARMS = ("ar", "dflash", "ngram")
EXPECTED_MANIFEST = "499c50ed75257df865652559b5508fae56cc297aef3855287f8f9d6879174405"
EXPECTED_ADOPTION = "283375f25b465eab43ab4d5b812ee05d7d2d242db9226c7d752e9632f8ae1b96"
EXPECTED_REQUEST = "5f792d35b2124addc42e537b9cace8aaf253434ffa59355ed3020b6fbdf06405"
PACKET_SHA256 = "bcccec58b0f5ced606f8c7e3584f8500fa99546a97db2af67afbad4347451c04"
IMMUTABLE_SCIENCE = {
    "target_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
    "draft_revision": "eabd648301ce28583cc14757912e5e0f84e152e1",
    "runtime_revision": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
    "block_size": 16,
    "control_order": ["AR", "DFLASH", "NGRAM"],
    "historical_request_25_replay_allowed": False,
}


def require(value: dict[str, Any], fields: dict[str, object], kind: str) -> None:
    for key, expected in fields.items():
        if value.get(key) != expected:
            raise base.Boundary(kind, f"{key}_mismatch", False)


def classify_exact_unconsumed(snapshot: pathlib.Path) -> dict[str, Any]:
    adoption = retrieval.classify_snapshot(snapshot)
    require(
        adoption,
        {
            "classification": "classified_persisted_attempt",
            "continuation_allowed": True,
            "retry_scope": "all",
            "science_started": {arm: False for arm in ARMS},
            "science_consumed": {arm: False for arm in ARMS},
        },
        "direct_adoption_boundary",
    )
    if adoption["snapshot_manifest"].get("manifest_sha256") != EXPECTED_MANIFEST:
        raise base.Boundary("direct_adoption_boundary", "snapshot_manifest", False)
    attempt = adoption.get("attempt", {})
    if attempt.get("consumption_evidence") != "exclusive_pre_request_markers_absent":
        raise base.Boundary("direct_adoption_boundary", "marker_predicate", False)
    if attempt.get("scientific_terminal") is not False:
        raise base.Boundary("direct_adoption_boundary", "attempt_terminal", False)
    return adoption


def validate_direct_authority(
    authority: dict[str, Any], adoption: dict[str, Any], binding: dict[str, Any]
) -> pathlib.Path:
    require(
        authority,
        {
            "schema_version": 1,
            "decision": "direct_classified_unconsumed_continuation",
            "project": PROJECT_NAME,
            "direct_continuation_authorized": True,
            "prior_corrected_adoption_sha256": EXPECTED_ADOPTION,
            "snapshot_manifest_sha256": EXPECTED_MANIFEST,
            "unconsumed_request_sha256": EXPECTED_REQUEST,
            "retry_scope": "all",
            "packet_archive_sha256": PACKET_SHA256,
            "historical_request_25_replay_allowed": False,
            "claim_generation": binding["claimed_at"],
        },
        "direct_authority_boundary",
    )
    if adoption["snapshot_manifest"]["manifest_sha256"] != authority["snapshot_manifest_sha256"]:
        raise base.Boundary("direct_authority_boundary", "fresh_manifest", False)
    if authority.get("fresh_adoption_classification") != adoption["classification"]:
        raise base.Boundary("direct_authority_boundary", "fresh_adoption", False)
    if authority.get("immutable_science") != IMMUTABLE_SCIENCE:
        raise base.Boundary("direct_authority_boundary", "immutable_science", False)
    if not isinstance(authority.get("remote_run"), str) or not authority["remote_run"]:
        raise base.Boundary("direct_authority_boundary", "remote_run", False)
    packet = pathlib.Path(authority["packet_archive"])
    if base.sha256(packet) != PACKET_SHA256:
        raise base.Boundary("direct_authority_boundary", "packet_digest", False)
    return packet


def persist_adoption(
    artifact_root: pathlib.Path, adoption: dict[str, Any], receipt: dict[str, Any], binding: dict[str, Any], generation: int
) -> pathlib.Path:
    persisted = dict(adoption)
    persisted.update(
        {
            "created_at_utc": base.iso(),
            "claim_generation": binding["claimed_at"],
            "archive_sha256": receipt["archive_sha256"],
            "retrieval_receipt_sha256": base.sha256(artifact_root / "RETRIEVAL_RECEIPT_0.json"),
            "prior_corrected_adoption_sha256": EXPECTED_ADOPTION,
            "direct_continuation_path": True,
        }
    )
    path = artifact_root / f"DIRECT_CONTINUATION_ADOPTION_{generation}.json"
    base.atomic(path, persisted)
    return path


def terminal_or_maintenance(
    binding: dict[str, Any], artifact_root: pathlib.Path, snapshot: pathlib.Path, reason: str
) -> int:
    if (snapshot / "REMOTE_TERMINAL.json").is_file():
        component = base.validate_scientific_terminal(snapshot)
        base.atomic(PROJECT / "DFLASH_H200_COMPONENT_TERMINAL.json", component)
        _, spend = base.claim_exposure(binding)
        base.update_status(status="completed", decision=component["classification"], summary="Direct owner retrieved and validated the exact component terminal.", actual_spend_usd=spend, terminal_artifact="DFLASH_H200_COMPONENT_TERMINAL.json")
        base.release(binding, artifact_root, condition="ready", summary="Direct owner validated scientific terminal.", state="available_quiescent_after_dflash_component")
        return 0
    _, spend = base.claim_exposure(binding)
    base.atomic(artifact_root / "DIRECT_CONTINUATION_INCOMPLETE.json", {"schema_version": 1, "reason": reason, "science_terminal": False})
    base.update_status(status="blocked", decision="direct_continuation_incomplete_handoff", summary=reason, actual_spend_usd=spend, terminal_artifact=None)
    base.release(binding, artifact_root, condition="maintenance", summary=reason, state="maintenance_after_direct_continuation_incomplete")
    return 77


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--direct-authority", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    binding = base.load(args.execution_binding.resolve())
    authority = base.load(args.direct_authority.resolve())
    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    ready = base.validate_ready(binding)
    bench = base.validate_claim(binding)
    deadline = base.parse_time(binding["owner_deadline_utc"])
    if base.utc_now() >= deadline:
        raise base.Boundary("typed_deadline_boundary", "owner_deadline_passed", False)
    remote_run = str(authority["remote_run"])
    remote = base.Remote(bench, artifact_root, deadline)
    with base.Heartbeat(artifact_root, binding["claimed_at"]):
        snapshot, receipt = retrieval.package_and_retrieve_outside_tree(
            remote, remote_run, artifact_root, 0
        )
        adoption = classify_exact_unconsumed(snapshot)
        persist_adoption(artifact_root, adoption, receipt, binding, 0)
        packet = validate_direct_authority(authority, adoption, binding)
        if ready["packet"]["archive_sha256"] != PACKET_SHA256:
            raise base.Boundary("direct_authority_boundary", "ready_packet", False)
        packet_root, _ = base.stage_packet(remote, packet, PACKET_SHA256)
        worker = remote.run(
            f"python3 {shlex.quote(packet_root + '/dflash_component_worker.py')} "
            f"--packet-root {shlex.quote(packet_root)} "
            f"--remote-root {shlex.quote(remote_run)} "
            f"--target-source {shlex.quote(binding['remote_target_path'])} "
            f"--deadline-epoch {deadline.timestamp()} "
            f"--generation {shlex.quote(binding['generation'])} --retry-scope all",
            "direct-continuation-worker-0",
            cap=max(60, int((deadline - base.utc_now()).total_seconds() - 120)),
            check=False,
        )
        base.atomic(artifact_root / "DIRECT_CONTINUATION_WORKER_0.json", {"returncode": worker.returncode})
        generation = 1
        while base.utc_now() < deadline:
            snapshot, receipt = retrieval.package_and_retrieve_outside_tree(remote, remote_run, artifact_root, generation)
            adoption = retrieval.classify_snapshot(snapshot)
            adoption_path = persist_adoption(artifact_root, adoption, receipt, binding, generation)
            if adoption["classification"] == "scientific_terminal":
                return terminal_or_maintenance(binding, artifact_root, snapshot, "scientific_terminal")
            if not adoption.get("continuation_allowed"):
                return terminal_or_maintenance(binding, artifact_root, snapshot, "post_worker_unclassified_state")
            request = base.repair_wait(artifact_root, adoption_path, str(adoption["retry_scope"]), deadline, f"{binding['generation']}-direct-{generation}")
            if request is None:
                break
            if "_repair_terminal" in request:
                base.atomic(artifact_root / f"DIRECT_REPAIR_TERMINAL_{generation}.json", request["_repair_terminal"])
                generation += 1
                continue
            patch = retrieval.validated_continuation_patch(request, adoption_path, binding, str(adoption["retry_scope"]))
            packet_root, _ = base.stage_packet(remote, pathlib.Path(patch["packet_archive"]), patch["packet_archive_sha256"])
            worker = remote.run(
                f"python3 {shlex.quote(packet_root + '/dflash_component_worker.py')} --packet-root {shlex.quote(packet_root)} --remote-root {shlex.quote(remote_run)} --target-source {shlex.quote(binding['remote_target_path'])} --deadline-epoch {deadline.timestamp()} --generation {shlex.quote(binding['generation'])} --retry-scope {shlex.quote(str(adoption['retry_scope']))}",
                f"direct-continuation-worker-{generation}", cap=max(60, int((deadline - base.utc_now()).total_seconds() - 120)), check=False,
            )
            base.atomic(artifact_root / f"DIRECT_CONTINUATION_WORKER_{generation}.json", {"returncode": worker.returncode})
            generation += 1
        snapshot = artifact_root / "missing-post-worker-snapshot"
        return terminal_or_maintenance(binding, artifact_root, snapshot, "direct_continuation_deadline_or_request_absent")


if __name__ == "__main__":
    raise SystemExit(main())
