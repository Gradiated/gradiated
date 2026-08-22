#!/usr/bin/env python3
"""Retrieval-first replacement owner for the retained exact DFlash H200 claim.

This controller is deliberately inert until a later director supplies an exact
handoff binding and the predecessor PID is absent.  Its first remote operation
packages and retrieves the already-persisted run.  No packet staging, worker,
CUDA, or arm continuation is possible before that snapshot has been classified
and a hash-bound repair request explicitly authorizes the resulting scope.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any

import dflash_component_owner as base


PROJECT = pathlib.Path(__file__).resolve().parent
PROJECT_NAME = base.PROJECT_NAME
ARMS = ("ar", "dflash", "ngram")


def proc_start_ticks(pid: int) -> int | None:
    path = pathlib.Path(f"/proc/{pid}/stat")
    if not path.exists():
        return None
    fields = path.read_text().split()
    if len(fields) < 22:
        raise base.Boundary("predecessor_identity_boundary", "short_proc_stat", False)
    return int(fields[21])


def validate_handoff(
    path: pathlib.Path,
    binding: dict[str, Any],
    replacement_ready: pathlib.Path,
    predecessor_pid: int,
    predecessor_start_ticks: int,
) -> dict[str, Any]:
    handoff = base.load(path)
    required = {
        "schema_version": 1,
        "decision": "launch_retrieval_first_replacement_owner",
        "project": PROJECT_NAME,
        "predecessor_pid": predecessor_pid,
        "predecessor_start_ticks": predecessor_start_ticks,
        "claim_generation": binding["claimed_at"],
        "execution_binding_sha256": base.sha256(
            PROJECT / "DIRECTOR_DFLASH_H200_COMPONENT_EXECUTION_20260729T2247Z.json"
        ),
        "replacement_ready_sha256": base.sha256(replacement_ready),
        "replacement_owner_sha256": base.sha256(pathlib.Path(__file__).resolve()),
    }
    for key, expected in required.items():
        if handoff.get(key) != expected:
            raise base.Boundary(
                "replacement_handoff_boundary", f"{key}_mismatch", False
            )
    if proc_start_ticks(predecessor_pid) is not None:
        raise base.Boundary(
            "concurrent_owner_boundary",
            f"predecessor_pid_{predecessor_pid}_still_live",
            False,
        )
    return handoff


def verified_claim(binding: dict[str, Any]) -> dict[str, Any]:
    bench = base.validate_claim(binding)
    claim = bench["claim"]
    if bench.get("status") != "claimed":
        raise base.Boundary("claim_generation_boundary", "status_not_claimed", False)
    if claim.get("project") != PROJECT_NAME:
        raise base.Boundary("claim_generation_boundary", "wrong_project", False)
    if claim.get("claimed_at") != binding["claimed_at"]:
        raise base.Boundary(
            "claim_generation_boundary", "claimed_at_mismatch", False
        )
    return bench


def snapshot_manifest(root: pathlib.Path) -> dict[str, Any]:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": base.sha256(path),
            }
        )
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "files": rows,
        "file_count": len(rows),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def package_and_retrieve_outside_tree(
    remote: base.Remote,
    remote_run: str,
    artifact_root: pathlib.Path,
    generation: int,
    *,
    archive_dir: str = "/home/glmrunner/dflash-component/retrieval",
) -> tuple[pathlib.Path, dict[str, Any]]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha256(remote_run.encode()).hexdigest()[:16]
    prefix = f"{slug}-compact-{generation}"
    command = (
        "set -eu; "
        f"test -d {shlex.quote(remote_run)}; "
        f"mkdir -p {shlex.quote(archive_dir)}; "
        f"tmp=$(mktemp {shlex.quote(archive_dir + '/' + prefix + '.XXXXXX.tar.gz.part')}); "
        "trap 'rm -f \"$tmp\"' EXIT; "
        f"tar --exclude=immutable -C {shlex.quote(remote_run)} -czf \"$tmp\" .; "
        "digest=$(sha256sum \"$tmp\" | cut -d' ' -f1); "
        f"final={shlex.quote(archive_dir + '/' + prefix)}.$digest.tar.gz; "
        "if test -e \"$final\"; then "
        "test \"$(sha256sum \"$final\" | cut -d' ' -f1)\" = \"$digest\"; "
        "rm -f \"$tmp\"; "
        "else chmod 0444 \"$tmp\"; mv \"$tmp\" \"$final\"; fi; "
        "trap - EXIT; "
        "printf '%s\\t%s\\n' \"$digest\" \"$final\""
    )
    packaged = remote.run(
        command, f"replacement-package-{generation}", cap=180, check=True
    )
    fields = packaged.stdout.strip().split("\t")
    if len(fields) != 2 or len(fields[0]) != 64:
        raise base.Boundary(
            "remote_retrieval_boundary", "malformed_package_receipt"
        )
    expected, remote_archive = fields
    if not all(character in "0123456789abcdef" for character in expected):
        raise base.Boundary(
            "remote_retrieval_boundary", "malformed_package_digest"
        )
    local_part = artifact_root / f".compact-{expected}.tar.gz.part"
    local_archive = artifact_root / f"compact-{expected}.tar.gz"
    if not local_archive.exists():
        remote.get(
            remote_archive,
            local_part,
            f"replacement-retrieve-{generation}",
        )
        if base.sha256(local_part) != expected:
            raise base.Boundary(
                "remote_retrieval_boundary", "compact_archive_digest"
            )
        os.replace(local_part, local_archive)
    elif base.sha256(local_archive) != expected:
        raise base.Boundary(
            "remote_retrieval_boundary", "existing_compact_archive_digest"
        )
    destination = artifact_root / f"snapshot-{expected}"
    if not destination.exists():
        temporary = pathlib.Path(
            tempfile.mkdtemp(prefix=f".snapshot-{expected}.", dir=artifact_root)
        )
        try:
            with tarfile.open(local_archive, "r:gz") as bundle:
                bundle.extractall(temporary, filter="data")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    receipt = {
        "schema_version": 1,
        "generation": generation,
        "remote_run": remote_run,
        "remote_archive": remote_archive,
        "remote_archive_outside_run_tree": not remote_archive.startswith(
            remote_run.rstrip("/") + "/"
        ),
        "archive_sha256": expected,
        "local_archive": str(local_archive),
        "snapshot": str(destination),
        "snapshot_manifest": snapshot_manifest(destination),
    }
    if not receipt["remote_archive_outside_run_tree"]:
        raise base.Boundary(
            "remote_retrieval_boundary", "archive_inside_source_tree", False
        )
    base.atomic(
        artifact_root / f"RETRIEVAL_RECEIPT_{generation}.json", receipt
    )
    return destination, receipt


def classify_snapshot(snapshot: pathlib.Path) -> dict[str, Any]:
    manifest = snapshot_manifest(snapshot)
    terminal = snapshot / "REMOTE_TERMINAL.json"
    attempt_path = snapshot / "REMOTE_ATTEMPT.json"
    if terminal.is_file():
        component = base.validate_scientific_terminal(snapshot)
        return {
            "schema_version": 1,
            "classification": "scientific_terminal",
            "continuation_allowed": False,
            "retry_scope": None,
            "component_classification": component["classification"],
            "snapshot_manifest": manifest,
        }
    if not attempt_path.is_file():
        return {
            "schema_version": 1,
            "classification": (
                "empty_remote_run"
                if manifest["file_count"] == 0
                else "unclassified_persisted_state"
            ),
            "continuation_allowed": manifest["file_count"] == 0,
            "retry_scope": "all" if manifest["file_count"] == 0 else "classify",
            "snapshot_manifest": manifest,
        }
    attempt = base.load(attempt_path)
    started = attempt.get("science_started")
    consumed = attempt.get("science_consumed")
    if not isinstance(started, dict) or not all(
        isinstance(started.get(arm), bool) for arm in ARMS
    ):
        return {
            "schema_version": 1,
            "classification": "unclassified_science_markers",
            "continuation_allowed": False,
            "retry_scope": "classify",
            "attempt": attempt,
            "snapshot_manifest": manifest,
        }
    if (
        consumed is None
        and attempt.get("classification") == "server_startup_defect"
        and attempt.get("scientific_terminal") is False
        and not any(started.values())
    ):
        consumed = {arm: False for arm in ARMS}
        attempt = dict(attempt)
        attempt["science_consumed"] = consumed
        attempt["consumption_evidence"] = "exclusive_pre_request_markers_absent"
    if isinstance(consumed, dict) and all(
        isinstance(consumed.get(arm), bool) for arm in ARMS
    ):
        if any(consumed.values()):
            scope = "summarize"
        elif not any(started.values()):
            scope = str(attempt.get("retry_scope", "all"))
        else:
            scope = "classify"
        return {
            "schema_version": 1,
            "classification": "classified_persisted_attempt",
            "continuation_allowed": scope != "classify",
            "retry_scope": scope,
            "science_started": started,
            "science_consumed": consumed,
            "attempt": attempt,
            "snapshot_manifest": manifest,
        }
    return {
        "schema_version": 1,
        "classification": "unclassified_consumption",
        "continuation_allowed": False,
        "retry_scope": "classify",
        "science_started": started,
        "attempt": attempt,
        "snapshot_manifest": manifest,
    }


def finalize_terminal(
    binding: dict[str, Any],
    artifact_root: pathlib.Path,
    snapshot: pathlib.Path,
) -> int:
    component = base.validate_scientific_terminal(snapshot)
    final_name = "DFLASH_H200_COMPONENT_TERMINAL.json"
    base.atomic(PROJECT / final_name, component)
    _, spend = base.claim_exposure(binding)
    if spend > base.AUTHORIZED_USD:
        raise base.Boundary("spend_boundary", f"{spend}>{base.AUTHORIZED_USD}", False)
    summary = (
        f"{component['classification']}; retrieved/adopted exact "
        "AR/DFLASH/NGRAM c32 component and semantic ledgers."
    )
    base.update_status(
        status="completed",
        decision=component["classification"],
        summary=summary,
        actual_spend_usd=spend,
        terminal_artifact=final_name,
    )
    base.release(
        binding,
        artifact_root,
        condition="ready",
        summary=summary,
        state="available_quiescent_after_dflash_component",
    )
    return 0


def validated_continuation_patch(
    request: dict[str, Any],
    adoption_path: pathlib.Path,
    binding: dict[str, Any],
    retry_scope: str,
) -> dict[str, Any]:
    patch = base.load(pathlib.Path(request["patch_artifact"]))
    required = {
        "schema_version": 1,
        "continuation_authorized": True,
        "claim_generation": binding["claimed_at"],
        "adoption_sha256": base.sha256(adoption_path),
        "retry_scope": retry_scope,
    }
    for key, expected in required.items():
        if patch.get(key) != expected:
            raise base.Boundary(
                "continuation_authority_boundary", f"{key}_mismatch", False
            )
    archive = pathlib.Path(patch["packet_archive"])
    if base.sha256(archive) != patch["packet_archive_sha256"]:
        raise base.Boundary("repair_packet_boundary", "packet_digest", False)
    return patch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--replacement-ready", type=pathlib.Path, required=True)
    parser.add_argument("--handoff-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--predecessor-pid", type=int, required=True)
    parser.add_argument("--predecessor-start-ticks", type=int, required=True)
    args = parser.parse_args()

    binding = base.load(args.execution_binding.resolve())
    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    validate_handoff(
        args.handoff_binding.resolve(),
        binding,
        args.replacement_ready.resolve(),
        args.predecessor_pid,
        args.predecessor_start_ticks,
    )
    ready = base.validate_ready(binding)
    bench = verified_claim(binding)
    deadline = base.parse_time(binding["owner_deadline_utc"])
    if base.utc_now() >= deadline:
        raise base.Boundary("typed_deadline_boundary", "owner_deadline_passed", False)

    packet_digest = ready["packet"]["archive_sha256"]
    remote_run = (
        "/home/glmrunner/dflash-component/runs/"
        f"{binding['claimed_at'].replace(':', '').replace('.', '')}-"
        f"{packet_digest[:12]}"
    )
    remote = base.Remote(bench, artifact_root, deadline)
    generation = 0
    with base.Heartbeat(artifact_root, binding["claimed_at"]):
        while base.utc_now() < deadline:
            snapshot, receipt = package_and_retrieve_outside_tree(
                remote, remote_run, artifact_root, generation
            )
            adoption = classify_snapshot(snapshot)
            adoption.update(
                {
                    "created_at_utc": base.iso(),
                    "claim_generation": binding["claimed_at"],
                    "generation": generation,
                    "retrieval_receipt_sha256": base.sha256(
                        artifact_root / f"RETRIEVAL_RECEIPT_{generation}.json"
                    ),
                    "archive_sha256": receipt["archive_sha256"],
                }
            )
            adoption_path = artifact_root / f"RETRIEVAL_ADOPTION_{generation}.json"
            base.atomic(adoption_path, adoption)
            if adoption["classification"] == "scientific_terminal":
                return finalize_terminal(binding, artifact_root, snapshot)

            retry_scope = str(adoption["retry_scope"])
            request = base.repair_wait(
                artifact_root,
                adoption_path,
                retry_scope,
                deadline,
                f"{binding['generation']}-replacement-adoption-{generation}",
            )
            if request is None:
                break
            if "_repair_terminal" in request:
                base.atomic(
                    artifact_root / f"REPAIR_TERMINAL_ADOPTION_{generation}.json",
                    request["_repair_terminal"],
                )
                generation += 1
                continue
            patch = validated_continuation_patch(
                request, adoption_path, binding, retry_scope
            )
            if not adoption["continuation_allowed"]:
                raise base.Boundary(
                    "consumption_classification_boundary",
                    "continuation_forbidden_until_classified",
                    False,
                )
            packet_root, _ = base.stage_packet(
                remote,
                pathlib.Path(patch["packet_archive"]),
                patch["packet_archive_sha256"],
            )
            worker = remote.run(
                f"python3 {shlex.quote(packet_root + '/dflash_component_worker.py')} "
                f"--packet-root {shlex.quote(packet_root)} "
                f"--remote-root {shlex.quote(remote_run)} "
                f"--target-source {shlex.quote(binding['remote_target_path'])} "
                f"--deadline-epoch {deadline.timestamp()} "
                f"--generation {shlex.quote(binding['generation'])} "
                f"--retry-scope {shlex.quote(retry_scope)}",
                f"replacement-worker-{generation}",
                cap=max(60, int((deadline - base.utc_now()).total_seconds() - 120)),
                check=False,
            )
            base.atomic(
                artifact_root / f"REPLACEMENT_WORKER_{generation}.json",
                {
                    "returncode": worker.returncode,
                    "retry_scope": retry_scope,
                    "patch_artifact": request["patch_artifact"],
                    "patch_artifact_sha256": base.sha256(
                        pathlib.Path(request["patch_artifact"])
                    ),
                },
            )
            generation += 1

        _, spend = base.claim_exposure(binding)
        base.update_status(
            status="blocked",
            decision="replacement_owner_deadline_handoff",
            summary=(
                "Retrieval-first owner reached its deadline without an adoptable "
                f"scientific terminal; artifacts={artifact_root}"
            ),
            actual_spend_usd=spend,
            terminal_artifact=None,
        )
        base.release(
            binding,
            artifact_root,
            condition="maintenance",
            summary="Retrieval-first replacement reached the absolute deadline.",
            state="maintenance_at_replacement_owner_deadline",
        )
        return 77


if __name__ == "__main__":
    raise SystemExit(main())
