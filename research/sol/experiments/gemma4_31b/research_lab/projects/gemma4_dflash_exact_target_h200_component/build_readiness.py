#!/usr/bin/env python3
"""Validate, pack, and atomically publish the final DFlash component readiness."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
from typing import Any

PROJECT = pathlib.Path(__file__).resolve().parent
WORKSPACE = pathlib.Path("/root/workspace")
MANIFEST_TOOL = WORKSPACE / "research/factory/tools/manifest-pack"
MANIFEST = PROJECT / "PACKET_MANIFEST.json"
ARCHIVE = PROJECT / "DFLASH_H200_COMPONENT_PACKET.tar"
READY = PROJECT / "DFLASH_H200_COMPONENT_READY.json"
VALIDATION = PROJECT / "VALIDATION.json"
STATUS = PROJECT / "STATUS.json"
LOG = PROJECT / "RESEARCH_LOG.md"

PACKET_MEMBERS = [
    "PROJECT.md",
    "DIRECTOR_DFLASH_H200_COMPONENT_SOURCE_GATE_20260729T2215Z.json",
    "DIRECTOR_DFLASH_H200_WATCHDOG_R5_20260729T2223Z.json",
    "EXPERIMENT_CONTRACT.json",
    "OPPORTUNITY_REGISTER.json",
    "EXECUTION_BINDING_TEMPLATE.json",
    "component_observer.py",
    "sitecustomize.py",
    "run_bound_c32.py",
    "summarize_component.py",
    "dflash_component_worker.py",
    "dflash_component_owner.py",
    "test_component_packet.py",
    "build_readiness.py",
    "VALIDATION.json",
    "inputs/CHECKPOINT_MANIFEST.json",
    "inputs/exact_c32_runner.py",
    "inputs/server_args.f63458b5.py",
    "inputs/sglang-f63458b5.tar",
    "inputs/EXACT_TARGET_PARALLEL_DRAFT_COMPATIBILITY.json",
    "inputs/DFLASH_REQUEST25_OFFLINE_BOUNDARY_RESULT.json",
    "inputs/REQUEST_POOL_OWNERSHIP_FIXTURE_RESULT.json",
    "inputs/REQUEST_POOL_OWNER_REPAIR.patch",
]


def now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(canonical(value))
        temporary = pathlib.Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row(relative: str) -> dict[str, Any]:
    path = PROJECT / relative
    return {
        "path": relative,
        "absolute_path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def validate() -> dict[str, Any]:
    commands = [
        [
            "python3",
            "-m",
            "py_compile",
            *[
                str(path)
                for path in sorted(PROJECT.glob("*.py"))
            ],
        ],
        [
            "python3",
            "-m",
            "unittest",
            "-v",
            str(PROJECT / "test_component_packet.py"),
        ],
        [
            "python3",
            str(
                WORKSPACE
                / ".agents/skills/experiment-run/scripts/opportunity_register.py"
            ),
            str(PROJECT / "OPPORTUNITY_REGISTER.json"),
        ],
    ]
    results = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=WORKSPACE,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        results.append(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode:
            raise RuntimeError(f"validation failed: {command}")
    identities = {
        "source_archive_sha256": sha256(PROJECT / "inputs/sglang-f63458b5.tar"),
        "runner_sha256": sha256(PROJECT / "inputs/exact_c32_runner.py"),
        "checkpoint_manifest_sha256": sha256(
            PROJECT / "inputs/CHECKPOINT_MANIFEST.json"
        ),
        "source_terminal_sha256": sha256(
            PROJECT / "inputs/EXACT_TARGET_PARALLEL_DRAFT_COMPATIBILITY.json"
        ),
        "request25_boundary_sha256": sha256(
            PROJECT / "inputs/DFLASH_REQUEST25_OFFLINE_BOUNDARY_RESULT.json"
        ),
        "ownership_fixture_sha256": sha256(
            PROJECT / "inputs/REQUEST_POOL_OWNERSHIP_FIXTURE_RESULT.json"
        ),
        "ownership_patch_sha256": sha256(
            PROJECT / "inputs/REQUEST_POOL_OWNER_REPAIR.patch"
        ),
    }
    expected = {
        "source_archive_sha256": "3b7c1c8a43a179c10020be8621465be9b7d07ff9353164054c77fd7791f3b8c1",
        "runner_sha256": "8672802c73137910c28e3c73be7b7f1c6152acc5899279cd8d36e3fd82783c03",
        "checkpoint_manifest_sha256": "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6",
        "source_terminal_sha256": "738567dce0eee75ef4578b2e968919c533c7add11947cf585c0e2237374a046a",
        "request25_boundary_sha256": "dfca865f1e4c66b1698c92921d65dec3999c351aa83be64d9987a264d61bf711",
        "ownership_fixture_sha256": "2b94b14f0d0df94df03830ee91aa884fba53fa3b3888d420648c4510479809bc",
        "ownership_patch_sha256": "a8bb7d77c99ee80e9dd9cb1ab5cb89797bab07e90dc2f1e22c9c6d44ee2aebbd",
    }
    if identities != expected:
        raise RuntimeError(f"identity mismatch: {identities}")
    value = {
        "schema_version": 1,
        "validated_at_utc": now(),
        "pass": True,
        "commands": results,
        "identities": identities,
        "gpu_used": False,
        "provider_accessed": False,
        "endpoint_traffic_sent": False,
    }
    atomic(VALIDATION, value)
    return value


def build() -> None:
    if READY.exists():
        raise RuntimeError("readiness already exists; revoke it before rebuilding")
    validation = validate()
    files = [row(relative) for relative in PACKET_MEMBERS]
    manifest_value = {
        "schema_version": 1,
        "project": "gemma4_dflash_exact_target_h200_component",
        "files": [
            {
                "path": item["path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in files
        ],
    }
    atomic(MANIFEST, manifest_value)
    packed = subprocess.run(
        [
            str(MANIFEST_TOOL),
            "--root",
            str(PROJECT),
            "--manifest",
            str(MANIFEST),
            "--archive",
            str(ARCHIVE),
        ],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if packed.returncode:
        raise RuntimeError(packed.stderr)
    pack_result = json.loads(packed.stdout)
    archive_sha256 = pack_result["archive_sha256"]
    manifest_row = row("PACKET_MANIFEST.json")
    archive_row = row("DFLASH_H200_COMPONENT_PACKET.tar")
    ready_value = {
        "schema_version": 1,
        "artifact_type": "dflash_h200_component_ready",
        "created_at_utc": now(),
        "project": "gemma4_dflash_exact_target_h200_component",
        "decision": "ready_for_later_director_claim_binding",
        "claim_allowed": False,
        "claim_gate": (
            "A later director must bind this exact readiness digest, remaining "
            "reservation, current compatible bench, claim generation, immutable "
            "resident target path, and a fresh owner deadline before claiming."
        ),
        "reservation": {
            "authorized_cumulative_usd": 6.0,
            "actual_spend_usd_before_claim": 0.0,
            "reserved_at_utc": "2026-07-29T22:19:47.529405Z",
            "hourly_rate_usd": 2.45,
        },
        "identities": {
            "target": {
                "repo": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "manifest_sha256": "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6",
                "weight_index_sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
                "tokenizer_json_sha256": "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f",
                "bytes": 62578655208,
            },
            "draft": {
                "repo": "z-lab/gemma-4-31B-it-DFlash",
                "revision": "eabd648301ce28583cc14757912e5e0f84e152e1",
                "config_sha256": "325f2a18894994b19f916e551b6f13a6904e961ae59a818d2b1dec18458e97f8",
                "weight_sha256": "b3f28580103d6e8a0a1d9389646957b9309df5982558afd754b9810357f425b7",
                "weight_bytes": 3071941240,
            },
            "runtime_commit": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
            "source_archive_sha256": "3b7c1c8a43a179c10020be8621465be9b7d07ff9353164054c77fd7791f3b8c1",
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
            "runner_sha256": "8672802c73137910c28e3c73be7b7f1c6152acc5899279cd8d36e3fd82783c03",
            "workload": {
                "concurrency": 32,
                "prompt_tokens_per_request": 4214,
                "output_tokens_per_request": 358,
                "temperature": 0,
                "seed": 20260718,
                "block_size_including_current": 16,
            },
        },
        "historical_request_25": {
            "terminal_sha256": "dfca865f1e4c66b1698c92921d65dec3999c351aa83be64d9987a264d61bf711",
            "replayed": False,
            "used_as_evidence": False,
            "single_consumption_preserved": True,
            "reusable_mapping_only": True,
        },
        "ownership_mapping": {
            "logical": "ForwardBatch.rids[row]",
            "physical": "ForwardBatch.req_pool_indices[row]",
            "pool": "target_worker.model_runner.req_to_token_pool.req_to_token",
            "fixture_sha256": "2b94b14f0d0df94df03830ee91aa884fba53fa3b3888d420648c4510479809bc",
            "patch_sha256": "a8bb7d77c99ee80e9dd9cb1ab5cb89797bab07e90dc2f1e22c9c6d44ee2aebbd",
        },
        "measurement": {
            "arms": ["ar", "dflash", "ngram"],
            "order": ["ar", "dflash", "ngram"],
            "fresh_generation_each": True,
            "single_consumption_markers": True,
            "greedy_output_token_equality": True,
            "next_round_kv_bonus_audits": ["zero", "partial", "full"],
            "cuda_event_interval_union_phases": [
                "draft",
                "target_verify",
                "acceptance",
                "kv_commit",
            ],
            "economics": "c32 accepted target tokens per component second and committed-rate USD per million target tokens",
            "endpoint_claim": False,
        },
        "owner": {
            "path": "dflash_component_owner.py",
            "sha256": sha256(PROJECT / "dflash_component_owner.py"),
            "controller": "/root/workspace/research/factory/tools/detached-owner",
            "unit_manager": "pid",
            "heartbeat": True,
            "release": "generation-fenced with expected claimed_at",
            "repair": "generation-scoped hash-bound same-claim repair",
        },
        "worker": {
            "path": "dflash_component_worker.py",
            "sha256": sha256(PROJECT / "dflash_component_worker.py"),
            "pre_science": "Exact target/source/draft/image/runner/block identities and health before fresh submission.",
            "producer_consumption": "Each arm has an exclusive SCIENCE_STARTED marker; completed arms are never replayed by later-scope repair.",
        },
        "commands": {
            "claim": (
                "PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool "
                "--lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab "
                "claim --project gemma4_dflash_exact_target_h200_component --bench DIRECTOR_BOUND_BENCH"
            ),
            "owner": (
                "research/factory/tools/detached-owner start --unit-manager pid "
                "--state ABS_OWNER_STATE --log ABS_OWNER_LOG --cwd "
                "/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/"
                "gemma4_dflash_exact_target_h200_component -- python3 "
                "/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/"
                "gemma4_dflash_exact_target_h200_component/dflash_component_owner.py "
                "--execution-binding ABS_DIRECTOR_EXECUTION_BINDING "
                "--artifact-root ABS_ARTIFACT_ROOT"
            ),
            "active_session_contract": (
                "Record detached-owner absolute state path as unit plus emitted pid, "
                "start_ticks, unit_manager=pid, deadline, artifact_root, and generation."
            ),
        },
        "packet": {
            "manifest": "PACKET_MANIFEST.json",
            "manifest_sha256": manifest_row["sha256"],
            "archive": "DFLASH_H200_COMPONENT_PACKET.tar",
            "archive_sha256": archive_sha256,
            "archive_bytes": archive_row["bytes"],
            "file_count": len(files) + 1,
        },
        "immutable_files": [
            *files,
            manifest_row,
            archive_row,
        ],
        "validation": validation,
        "limitations": [
            "No GPU, provider, SSH, Docker, CUDA, or endpoint operation occurred while publishing readiness.",
            "Readiness is not a load, acceptance, timing, semantic, endpoint, or quality result.",
            "A later director must recheck lifecycle runway and reservation before claim."
        ],
    }
    ready_digest = hashlib.sha256(canonical(ready_value)).hexdigest()
    log = (
        "# Research log\n\n"
        f"## {ready_value['created_at_utc']} — exact H200 component packet ready\n\n"
        "Question: can exact DFlash beat matched AR and NGRAM controls while preserving "
        "greedy target and KV semantics?\n\n"
        "Action: materialized the exact f63458b5 source archive and immutable runner, "
        "adopted the fixture-validated RID/physical-slot mapping, and built a durable "
        "owner/worker packet with single-consumption markers, same-claim repair, "
        "zero/partial/full next-round audits, and CUDA interval-union accounting.\n\n"
        "Evidence: offline validation passed; no GPU/provider/endpoint action occurred. "
        "The historical request-25 sample remains consumed, uninterpretable, excluded, "
        "and unreplayed.\n\n"
        f"Artifact: DFLASH_H200_COMPONENT_READY.json SHA-256 `{ready_digest}`; "
        f"packet archive SHA-256 `{archive_sha256}`.\n\n"
        "Next: a later director may bind a compatible current bench and atomically claim "
        "only after rechecking the exact $6 reservation and lifecycle runway.\n"
    )
    LOG.write_text(log)
    status = json.loads(STATUS.read_text())
    status.update(
        {
            "status": "active",
            "decision": "ready_for_later_director_claim_binding",
            "claim_allowed": False,
            "actual_spend_usd": 0.0,
            "active_session": None,
            "readiness_artifact": "DFLASH_H200_COMPONENT_READY.json",
            "readiness_sha256": ready_digest,
            "packet_archive": "DFLASH_H200_COMPONENT_PACKET.tar",
            "packet_archive_sha256": archive_sha256,
            "summary": (
                "Hash-complete exact target/draft/runtime/runner owner-worker packet "
                "is durable and offline-validated. Historical request 25 remains "
                "excluded and unreplayed; no H200 claim or provider/endpoint action "
                "occurred. A later director must bind current lifecycle and claim generation."
            ),
            "next_action": (
                "Director: verify DFLASH_H200_COMPONENT_READY.json and the exact $6 "
                "remaining reservation against a current compatible H200 lifecycle. "
                "If admitted, publish an execution binding from the template, atomically "
                "claim, launch the controller-host owner through detached-owner "
                "--unit-manager pid, and record its PID/start_ticks/unit in active_session."
            ),
        }
    )
    atomic(STATUS, status)
    atomic(READY, ready_value)
    print(
        json.dumps(
            {
                "ready": str(READY),
                "ready_sha256": ready_digest,
                "packet_archive": str(ARCHIVE),
                "packet_archive_sha256": archive_sha256,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    build()
