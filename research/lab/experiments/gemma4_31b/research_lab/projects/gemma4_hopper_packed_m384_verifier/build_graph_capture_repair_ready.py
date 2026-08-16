#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
ENDPOINT = PROJECT / "inputs" / "endpoint"
DIRECTOR = (
    PROJECT
    / "DIRECTOR_H100_PACKED_M384_GRAPH_CAPTURE_REPAIR_20260726T1828Z.json"
)
ARCHIVE = PROJECT / "artifacts/endpoint/endpoint-repair2-artifacts.tar.gz"
ORACLE = ENDPOINT / "CONTROL_TOKEN_ORACLE.json"
MANIFEST = ENDPOINT / "ENDPOINT_INPUT_MANIFEST.json"
REPAIR_MANIFEST = ENDPOINT / "GRAPH_REPAIR_INPUT_MANIFEST.json"
OWNER = PROJECT / "run_graph_repair_owner.py"
EXPECTED_DIRECTOR = (
    "803290e8b934e4c56635f5afca0e3e7677edd5b08b33275a893f1f07c6c1c923"
)
EXPECTED_ARCHIVE = (
    "8391ac82b788fc311797fe0b61f5369f70897a7d1424ca2cdfb94db50101afd5"
)
PACKET_NAMES = [
    "CONTROL_TOKEN_ORACLE.json",
    "candidate_resume.py",
    "decode_equivalent_lm_head.py",
    "endpoint_entrypoint.py",
    "endpoint_pair.py",
    "exact_runner.py",
    "packed_m384_endpoint.py",
    "sitecustomize.py",
    "token_oracle.py",
    "token_trace_hook.py",
    "triton_backend.v0.5.13.py",
]
REPAIR_NAMES = {
    "CONTROL_TOKEN_ORACLE.json",
    "candidate_resume.py",
    "packed_m384_endpoint.py",
    "sitecustomize.py",
    "token_oracle.py",
}


def sha256(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def row(path: pathlib.Path, remote: str) -> dict:
    return {
        "bytes": path.stat().st_size,
        "path": remote,
        "sha256": sha256(path),
        "source": str(path.relative_to(PROJECT)),
    }


def function_ast(path: pathlib.Path, name: str) -> str:
    module = ast.parse(path.read_text())
    node = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return hashlib.sha256(
        ast.dump(node, include_attributes=False).encode()
    ).hexdigest()


def main() -> None:
    if sha256(DIRECTOR) != EXPECTED_DIRECTOR:
        raise RuntimeError("director_binding_mismatch")
    if sha256(ARCHIVE) != EXPECTED_ARCHIVE:
        raise RuntimeError("control_archive_binding_mismatch")
    oracle = json.loads(ORACLE.read_text())
    if (
        oracle.get("type") != "packed_m384_persisted_control_token_oracle"
        or oracle.get("source", {}).get("archive_sha256") != EXPECTED_ARCHIVE
        or len(oracle.get("rows", [])) != 32
        or any(len(row["emitted_token_ids"]) != 358 for row in oracle["rows"])
    ):
        raise RuntimeError("control_oracle_invalid")

    kernel_names = [
        "_score_partition_kernel",
        "_merge_state_kernel",
        "_value_consumer_kernel",
    ]
    measured = PROJECT / "packed_m384_attention_v2.py"
    integrated = ENDPOINT / "packed_m384_endpoint.py"
    kernel_hashes = {
        name: {
            "measured_v2_ast_sha256": function_ast(measured, name),
            "repaired_endpoint_ast_sha256": function_ast(integrated, name),
        }
        for name in kernel_names
    }
    if any(
        value["measured_v2_ast_sha256"]
        != value["repaired_endpoint_ast_sha256"]
        for value in kernel_hashes.values()
    ):
        raise RuntimeError("measured_v2_kernel_ast_changed")
    integrated_source = integrated.read_text()
    if (
        ".is_contiguous()" in integrated_source
        or "tensor.stride(-1) == 1" not in integrated_source
        or "q_extend.stride(0)" not in integrated_source
        or "o_extend.stride(0)" not in integrated_source
        or "BLOCK_M = 16" not in integrated_source
        or "PARTITION_N = 512" not in integrated_source
    ):
        raise RuntimeError("layout_repair_contract_invalid")
    backend_source = (ENDPOINT / "triton_backend.v0.5.13.py").read_text()
    if (
        "q.view(-1, layer.tp_q_head_num, layer.qk_head_dim)" not in backend_source
        or "k.contiguous()" not in backend_source
        or "v.contiguous()" not in backend_source
        or "o.view(-1, layer.tp_q_head_num, layer.v_head_dim)"
        not in backend_source
    ):
        raise RuntimeError("pinned_graph_layout_source_fact_missing")

    previous_manifest = json.loads(MANIFEST.read_text())
    checkpoint_rows = previous_manifest["checkpoint_files"]
    packet_rows = [
        row(ENDPOINT / name, f"input/{name}") for name in PACKET_NAMES
    ]
    full_manifest = {
        "schema_version": 1,
        "project": "gemma4_hopper_packed_m384_verifier",
        "packet_files": packet_rows,
        "checkpoint_files": checkpoint_rows,
        "checkpoint_total_bytes": previous_manifest["checkpoint_total_bytes"],
        "materialization": previous_manifest["materialization"],
    }
    atomic(MANIFEST, full_manifest)
    manifest_sha = sha256(MANIFEST)
    repair_rows = [
        value
        for value in packet_rows
        if pathlib.PurePosixPath(value["path"]).name in REPAIR_NAMES
    ]
    repair_rows.append(row(MANIFEST, "input/ENDPOINT_INPUT_MANIFEST.json"))
    repair_manifest = {
        "schema_version": 1,
        "project": "gemma4_hopper_packed_m384_verifier",
        "kind": "candidate_only_graph_capture_repair_delta",
        "full_manifest_sha256": manifest_sha,
        "files": repair_rows,
        "retained_files": [
            value["path"]
            for value in full_manifest["packet_files"]
            + full_manifest["checkpoint_files"]
            if value["path"] not in {item["path"] for item in repair_rows}
        ],
    }
    atomic(REPAIR_MANIFEST, repair_manifest)

    owner_sha = sha256(OWNER)
    start_command = [
        "/root/workspace/research/factory/tools/detached-owner",
        "start",
        "--unit-manager",
        "pid",
        "--state",
        "GRAPH_REPAIR_OWNER_STATE.json",
        "--log",
        "GRAPH_REPAIR_OWNER_CONTROLLER.log",
        "--cwd",
        str(PROJECT),
        "--",
        "python3",
        "run_graph_repair_owner.py",
    ]
    ready = {
        "schema_version": 1,
        "type": "packed_m384_graph_capture_repair_ready",
        "project": "gemma4_hopper_packed_m384_verifier",
        "decision": "candidate_only_retained_h100_resume_bound",
        "gpu_claim_allowed": False,
        "director_must_consume_before_claim": True,
        "director_binding": {
            "path": DIRECTOR.name,
            "sha256": EXPECTED_DIRECTOR,
        },
        "causal_repair": {
            "failure": "packed_m384_exact_shape_required",
            "rejected_assumption": "full_tensor_contiguity",
            "required_layout": (
                "rank-3 Q/K/V/O with unit feature stride; token and head "
                "strides are passed explicitly to the measured kernels"
            ),
            "pinned_producer": (
                "TritonAttnBackend.forward_extend passes Q/O shaped views and "
                "explicitly contiguous K/V tensors"
            ),
            "source_path": "inputs/endpoint/packed_m384_endpoint.py",
            "source_sha256": sha256(integrated),
            "route_path": "inputs/endpoint/sitecustomize.py",
            "route_sha256": sha256(ENDPOINT / "sitecustomize.py"),
            "measured_v2_kernel_ast_identity": kernel_hashes,
            "scientific_geometry_unchanged": {
                "batch": 32,
                "query_tokens": 384,
                "query_heads": 32,
                "local": {
                    "kv_heads": 16,
                    "head_dim": 256,
                    "window": 1024,
                },
                "global": {
                    "kv_heads": 4,
                    "head_dim": 512,
                    "prefix_capacity": 4608,
                },
                "block_m": 16,
                "partition_n": 512,
                "direct_fp8_paged_kv": True,
            },
        },
        "persisted_control_oracle": {
            "path": str(ORACLE.relative_to(PROJECT)),
            "sha256": sha256(ORACLE),
            "source_archive": str(ARCHIVE.relative_to(PROJECT)),
            "source_archive_sha256": EXPECTED_ARCHIVE,
            "request_identities": 32,
            "emitted_token_ids_per_request": 358,
            "join": "raw SSE response id -> token-event rid -> ordered scheduler deltas",
            "control_request_replayed": False,
            "control_service_seconds_per_request": oracle[
                "control_terminal"
            ]["service_seconds_per_request"],
        },
        "candidate_only_command": {
            "remote": [
                "python3",
                "/home/glmrunner/gemma4_hopper_packed_m384_endpoint/input/candidate_resume.py",
                "--root",
                "/home/glmrunner/gemma4_hopper_packed_m384_endpoint",
                "--manifest",
                "/home/glmrunner/gemma4_hopper_packed_m384_endpoint/input/ENDPOINT_INPUT_MANIFEST.json",
                "--oracle",
                "/home/glmrunner/gemma4_hopper_packed_m384_endpoint/input/CONTROL_TOKEN_ORACLE.json",
                "--absolute-deadline-epoch",
                "1785095700",
            ],
            "candidate_resume_sha256": sha256(
                ENDPOINT / "candidate_resume.py"
            ),
            "control_request_replay_allowed": False,
            "candidate_request_submissions_remaining": 1,
            "profiler": "off",
            "expected_terminal": "artifacts/ENDPOINT_TERMINAL.json",
        },
        "inputs": {
            "full_manifest": {
                "path": str(MANIFEST.relative_to(PROJECT)),
                "sha256": manifest_sha,
            },
            "repair_delta_manifest": {
                "path": str(REPAIR_MANIFEST.relative_to(PROJECT)),
                "sha256": sha256(REPAIR_MANIFEST),
            },
            "checkpoint_bytes": full_manifest["checkpoint_total_bytes"],
            "retained_checkpoint_path": (
                "/home/glmrunner/gemma4_hopper_packed_m384_endpoint/checkpoint"
            ),
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
        },
        "retained_repair_owner": {
            "path": OWNER.name,
            "sha256": owner_sha,
            "exact_start_command": start_command,
            "state_path": "GRAPH_REPAIR_OWNER_STATE.json",
            "log_path": "GRAPH_REPAIR_OWNER_CONTROLLER.log",
            "unit_manager": "pid",
            "heartbeat_interval_seconds": 30,
            "repair_generation_policy": (
                "fresh generation per recoverable pre-submission exit; "
                "unknown or post-submission state never replays"
            ),
            "candidate_release_deadline_utc": "2026-07-26T19:55:00Z",
        },
        "required_director_readmission": {
            "destination": "GRAPH_CAPTURE_REPAIR_READMISSION.json",
            "required_fields": {
                "project": "gemma4_hopper_packed_m384_verifier",
                "evidence.graph_capture_repair_ready_sha256": (
                    "sha256 of this artifact"
                ),
                "bench.id": "h100-paged-fp8-e00mkpyvykfak0bg1m",
                "bench.candidate_release_deadline_utc": (
                    "2026-07-26T19:55:00Z"
                ),
                "candidate_only_resume": True,
            },
            "claim_before_readmission": False,
        },
        "offline_validation": {
            "commands": [
                "python3 reconstruct_control_oracle.py --archive artifacts/endpoint/endpoint-repair2-artifacts.tar.gz --output inputs/endpoint/CONTROL_TOKEN_ORACLE.json",
                "python3 -m unittest -v test_endpoint_integration.py test_graph_capture_repair.py",
                "python3 -m py_compile run_graph_repair_owner.py inputs/endpoint/candidate_resume.py inputs/endpoint/token_oracle.py",
            ],
            "tests_passed": 7,
            "candidate_cuda_execution_due_after_readmission": True,
        },
    }
    atomic(PROJECT / "GRAPH_CAPTURE_REPAIR_READY.json", ready)
    print(
        json.dumps(
            {
                "ready": str(PROJECT / "GRAPH_CAPTURE_REPAIR_READY.json"),
                "ready_sha256": sha256(
                    PROJECT / "GRAPH_CAPTURE_REPAIR_READY.json"
                ),
                "manifest_sha256": manifest_sha,
                "repair_manifest_sha256": sha256(REPAIR_MANIFEST),
                "owner_sha256": owner_sha,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
