#!/usr/bin/env python3
"""Reconstruct the request-25 observer boundary from immutable local evidence.

This program is deliberately offline.  It neither imports networking modules nor
touches the endpoint.  Its only mutation is writing the project-local evidence
bundle and the terminal boundary result.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import difflib
import hashlib
import json
import pathlib
from typing import Any, Sequence


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
PACKET_ID = "4ae9a81bfe3cfcc45a5302662be380e70c2753ef336547445b85aa7ed28f7f4b"
RUN_ID = "request25-duplicate-safe-owner-20260726T0135Z"
ARTIFACT_NAME = "request25-offline-boundary-20260726"

PACKET_ROOT = (
    PROJECT_ROOT
    / "artifacts"
    / "request25-boundary-probe-preparation-20260726"
    / "packet"
    / PACKET_ID
)
RUN_ROOT = PROJECT_ROOT / "artifacts" / RUN_ID
RETRIEVED = RUN_ROOT / "retrieved"

EXPECTED = {
    "source_binding_sha256": "cc49aa4192e737c90ddd5871c59efd4fc854c6a0ca094c557a0e78545bdb8c52",
    "dflash_worker_v2.py": "8fbddb39f4b33b4ac55b1919bc58fa846acb60892886199251d3592a5223050f",
    "forward_batch_info.py": "c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516",
    "memory_pool.py": "26ce123db5991db93f5d93fa6ca28cb360a7402a7ef0ed0e7315a3d3b37bb363",
    "response_manifest_sha256": "75a2a93e21ec6198d6b7882de4c027a071a57e56c09bc54d71b7e55e91e71ebb",
    "reported_response_sha256": "82855c7959f02213647e2efd8e68ad61b3b784b84667fb5cd72a99a1278ac741",
    "observer_sitecustomize_sha256": "f7ebe01b5d2a982da9dd74caf26466859b0c137a13a3233a50b5e4d7c9761217",
    "observer_helper_sha256": "3667691923d30ea15432a43541cd681835f7d5e028946af18b2c4c2579d0e6d2",
    "request_driver_sha256": "ac1f26ed379cf83313ce34421ec3f7993095f00875842e05d976c0b2aac4257d",
}

STALE_BLOCK = """\
    req_to_token = forward.req_to_token_pool.req_to_token
    prefix = [
        int(value)
        for value in _tolist(req_to_token[slot, :seq_len])
    ]
    worker = locals_[\"self\"]
"""
REPAIRED_BLOCK = """\
    worker = locals_[\"self\"]
    req_to_token = worker.target_worker.model_runner.req_to_token_pool.req_to_token
    prefix = [
        int(value)
        for value in _tolist(req_to_token[slot, :seq_len])
    ]
"""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(canonical_bytes(value))
    temporary.replace(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def select_request_row(
    rids: Sequence[str], req_pool_indices: Sequence[int], target_rid: str
) -> tuple[int, int]:
    """Map logical request identity to row and then to its physical pool slot."""
    if len(rids) != len(req_pool_indices):
        raise ValueError("rids and req_pool_indices must have equal length")
    rows = [row for row, rid in enumerate(rids) if str(rid) == target_rid]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one target RID, found {len(rows)}")
    row = rows[0]
    return row, int(req_pool_indices[row])


def read_request_prefix(
    req_to_token: Sequence[Sequence[int]], slot: int, seq_len: int
) -> list[int]:
    """Read the prefix from the owner pool using the physical request slot."""
    if slot < 0 or slot >= len(req_to_token):
        raise IndexError("request-pool slot is out of bounds")
    if seq_len < 0 or seq_len > len(req_to_token[slot]):
        raise ValueError("sequence length is out of bounds for request-pool row")
    return [int(value) for value in req_to_token[slot][:seq_len]]


def request_driver_retains_raw_bytes(source: str) -> bool:
    """Return whether the request driver persists the response bytearray itself."""
    tree = ast.parse(source)
    raw_writes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == "raw":
                raw_writes.append(ast.unparse(node.func))
    # len(raw) and hashlib.sha256(raw) produce metadata, not persisted raw bytes.
    return any(name not in {"len", "hashlib.sha256"} for name in raw_writes)


def build_repaired_observer(source: str) -> str:
    if source.count(STALE_BLOCK) != 1:
        raise ValueError("stale observer block did not occur exactly once")
    repaired = source.replace(STALE_BLOCK, REPAIRED_BLOCK)
    compile(repaired, "sitecustomize.repaired.py", "exec")
    return repaired


def run_fixture() -> dict[str, Any]:
    # Rows intentionally do not equal physical slots.  The target moves rows in
    # the second case while retaining its current slot.
    pool = [[slot * 100 + col for col in range(6)] for slot in range(50)]
    row, slot = select_request_row(
        ["rid-other", "rid-request-25"], [7, 42], "rid-request-25"
    )
    prefix = read_request_prefix(pool, slot, 4)
    moved_row, moved_slot = select_request_row(
        ["rid-request-25", "rid-other"], [42, 7], "rid-request-25"
    )
    moved_prefix = read_request_prefix(pool, moved_slot, 4)
    expected = [4200, 4201, 4202, 4203]
    passed = (
        row == 1
        and slot == 42
        and moved_row == 0
        and moved_slot == 42
        and prefix == expected
        and moved_prefix == expected
    )
    if not passed:
        raise AssertionError("logical-RID to physical-slot fixture failed")
    return {
        "schema_version": 1,
        "classification": "offline_fixture_pass",
        "passed": True,
        "cases": [
            {
                "rids": ["rid-other", "rid-request-25"],
                "req_pool_indices": [7, 42],
                "target_rid": "rid-request-25",
                "selected_row": row,
                "selected_slot": slot,
                "seq_len": 4,
                "prefix": prefix,
            },
            {
                "rids": ["rid-request-25", "rid-other"],
                "req_pool_indices": [42, 7],
                "target_rid": "rid-request-25",
                "selected_row": moved_row,
                "selected_slot": moved_slot,
                "seq_len": 4,
                "prefix": moved_prefix,
            },
        ],
        "invariant": (
            "rids identifies the logical row; req_pool_indices[row] selects the "
            "physical req_to_token_pool row. Logical row and pool slot are not interchangeable."
        ),
    }


def relative(path: pathlib.Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=pathlib.Path,
        default=PROJECT_ROOT / "artifacts" / ARTIFACT_NAME,
    )
    parser.add_argument(
        "--result",
        type=pathlib.Path,
        default=PROJECT_ROOT / "DFLASH_REQUEST25_OFFLINE_BOUNDARY_RESULT.json",
    )
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    result_path = args.result.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "source_binding": PACKET_ROOT / "SOURCE_BINDING.json",
        "dflash_worker_v2": PACKET_ROOT / "executed_source" / "dflash_worker_v2.py",
        "forward_batch_info": PACKET_ROOT / "executed_source" / "forward_batch_info.py",
        "memory_pool": PACKET_ROOT / "executed_source" / "memory_pool.py",
        "response_manifest": RETRIEVED / "REQUEST25_RESPONSE.json",
        "error": RETRIEVED / "request25-boundary.error.json",
        "remote_terminal": RETRIEVED / "REMOTE_TERMINAL.json",
        "probe_terminal": RUN_ROOT / "DFLASH_REQUEST25_BOUNDARY_PROBE_H200_RETRY2_TERMINAL.json",
        "science_started": RETRIEVED / "REQUEST25_SCIENCE_STARTED.json",
        "server_log": RETRIEVED / "server.log",
        "observer_sitecustomize": RETRIEVED / "observer" / "sitecustomize.py",
        "observer_helper": RETRIEVED / "observer" / "request25_boundary_probe.py",
        "request_driver": PROJECT_ROOT / "request25_single_request.py",
    }
    missing = [relative(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing immutable inputs: {missing}")

    source_binding = json.loads(paths["source_binding"].read_text())
    response_manifest = json.loads(paths["response_manifest"].read_text())
    error = json.loads(paths["error"].read_text())
    probe_terminal = json.loads(paths["probe_terminal"].read_text())
    observer_source = paths["observer_sitecustomize"].read_text()
    request_driver_source = paths["request_driver"].read_text()
    forward_batch_source = paths["forward_batch_info"].read_text()

    observed_hashes = {name: sha256_file(path) for name, path in paths.items()}
    required_hash_matches = {
        "dflash_worker_v2.py": observed_hashes["dflash_worker_v2"]
        == EXPECTED["dflash_worker_v2.py"],
        "forward_batch_info.py": observed_hashes["forward_batch_info"]
        == EXPECTED["forward_batch_info.py"],
        "memory_pool.py": observed_hashes["memory_pool"] == EXPECTED["memory_pool.py"],
        "response_manifest": observed_hashes["response_manifest"]
        == EXPECTED["response_manifest_sha256"],
        "observer_sitecustomize": observed_hashes["observer_sitecustomize"]
        == EXPECTED["observer_sitecustomize_sha256"],
        "observer_helper": observed_hashes["observer_helper"]
        == EXPECTED["observer_helper_sha256"],
        "request_driver": observed_hashes["request_driver"]
        == EXPECTED["request_driver_sha256"],
        "binding_declared_identity": source_binding["source_binding_sha256"]
        == EXPECTED["source_binding_sha256"],
    }
    if not all(required_hash_matches.values()):
        raise ValueError(f"immutable input hash mismatch: {required_hash_matches}")

    bound_files = {
        entry["packet_path"]: entry["sha256"]
        for entry in source_binding["executed_source"]
    }
    if (
        bound_files["executed_source/dflash_worker_v2.py"]
        != observed_hashes["dflash_worker_v2"]
        or bound_files["executed_source/forward_batch_info.py"]
        != observed_hashes["forward_batch_info"]
        or bound_files["executed_source/memory_pool.py"] != observed_hashes["memory_pool"]
    ):
        raise ValueError("pinned executed-source binding does not match local bytes")

    dataclass_tree = ast.parse(forward_batch_source)
    forward_batch_fields = {
        node.target.id
        for node in ast.walk(dataclass_tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    forward_batch_evidence = {
        "has_req_pool_indices": "req_pool_indices" in forward_batch_fields,
        "has_rids": "rids" in forward_batch_fields,
        "has_req_to_token_pool": "req_to_token_pool" in forward_batch_fields,
        "from_schedule_batch_assigns_req_pool_indices": (
            "req_pool_indices=batch.req_pool_indices" in forward_batch_source
        ),
        "from_schedule_batch_assigns_rids": (
            "rids=[req.rid for req in batch.reqs]" in forward_batch_source
        ),
    }
    if forward_batch_evidence != {
        "has_req_pool_indices": True,
        "has_rids": True,
        "has_req_to_token_pool": False,
        "from_schedule_batch_assigns_req_pool_indices": True,
        "from_schedule_batch_assigns_rids": True,
    }:
        raise ValueError(f"unexpected ForwardBatch evidence: {forward_batch_evidence}")

    if response_manifest["response_sha256"] != EXPECTED["reported_response_sha256"]:
        raise ValueError("reported raw response digest changed")
    if response_manifest["response_bytes"] != 228550:
        raise ValueError("reported raw response length changed")
    raw_sized_files = [
        path
        for path in RUN_ROOT.rglob("*")
        if path.is_file() and path.stat().st_size == response_manifest["response_bytes"]
    ]
    driver_retains_raw = request_driver_retains_raw_bytes(request_driver_source)
    if driver_retains_raw:
        raise ValueError("request driver unexpectedly persists raw response bytes")

    repaired_source = build_repaired_observer(observer_source)
    repaired_path = artifact_root / "sitecustomize.request_pool_owner_repaired.py"
    repaired_path.write_text(repaired_source)
    patch_path = artifact_root / "REQUEST_POOL_OWNER_REPAIR.patch"
    patch_path.write_text(
        "".join(
            difflib.unified_diff(
                observer_source.splitlines(keepends=True),
                repaired_source.splitlines(keepends=True),
                fromfile=relative(paths["observer_sitecustomize"]),
                tofile=relative(repaired_path),
            )
        )
    )
    fixture = run_fixture()
    fixture_path = artifact_root / "REQUEST_POOL_OWNERSHIP_FIXTURE_RESULT.json"
    atomic_json(fixture_path, fixture)

    server_log = paths["server_log"].read_text(errors="replace")
    aggregate_lines = [
        line
        for line in server_log.splitlines()
        if "accept len:" in line and "#running-req: 1" in line
    ]
    input_manifest_path = artifact_root / "INPUTS.sha256"
    input_manifest_path.write_text(
        "".join(
            f"{observed_hashes[name]}  {relative(path)}\n"
            for name, path in sorted(paths.items())
        )
    )

    recorded_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    result = {
        "schema_version": 1,
        "recorded_at_utc": recorded_at,
        "classification": "unrecoverable_missing_decision_evidence",
        "decision_bearing_boundary": False,
        "scientific_sample_interpretable": False,
        "request_index": 25,
        "scope": {
            "offline_only": True,
            "endpoint_contacted": False,
            "request_replayed": False,
            "gpu_used": False,
            "incremental_provider_spend_usd": 0.0,
            "cumulative_provider_spend_usd": 1.2563342402918893,
        },
        "consumed_request": {
            "submission_count": probe_terminal["request_submission_count"],
            "response_http_200_observed": '"POST /generate HTTP/1.1" 200 OK'
            in server_log,
            "observer_error": error,
            "boundary_record": probe_terminal["boundary_record"],
            "endpoint_replayed": probe_terminal["endpoint_replayed"],
        },
        "immutable_response_inspection": {
            "path": relative(paths["response_manifest"]),
            "file_bytes": paths["response_manifest"].stat().st_size,
            "file_sha256": observed_hashes["response_manifest"],
            "reported_raw_response_bytes": response_manifest["response_bytes"],
            "reported_raw_response_sha256": response_manifest["response_sha256"],
            "raw_response_bytes_persisted": False,
            "same_size_files_under_consumed_run": [
                relative(path) for path in raw_sized_files
            ],
            "driver_source": relative(paths["request_driver"]),
            "driver_sha256": observed_hashes["request_driver"],
            "driver_retains_raw_bytes": driver_retains_raw,
            "proof": (
                "The driver accumulates the HTTP stream in a process-local bytearray, "
                "then serializes only len(raw) and sha256(raw). The 423-byte JSON is a "
                "manifest, not the reported 228,550-byte stream; no file of the reported "
                "size exists under the immutable consumed-run artifact."
            ),
        },
        "pinned_runtime_source": {
            "packet_identity_sha256": PACKET_ID,
            "source_binding_path": relative(paths["source_binding"]),
            "source_binding_file_sha256": observed_hashes["source_binding"],
            "source_binding_identity_sha256": source_binding["source_binding_sha256"],
            "runtime_commit": source_binding["runtime_commit"],
            "runtime_image_lineage": source_binding["runtime_image_lineage"],
            "required_hash_matches": required_hash_matches,
            "forward_batch_evidence": forward_batch_evidence,
        },
        "ownership_mapping": {
            "logical_identity": (
                "ForwardBatch.rids[row] identifies the logical request. The observer's "
                "SLOT_TO_RID fallback preserves this identity when rids is unavailable."
            ),
            "physical_identity": (
                "ForwardBatch.req_pool_indices[row] is the current physical row in "
                "target_worker.model_runner.req_to_token_pool.req_to_token."
            ),
            "selection": (
                "Find the unique row whose RID is request 25, obtain slot = "
                "req_pool_indices[row], then read req_to_token[slot, :seq_len]."
            ),
            "stale_consumer": "forward.req_to_token_pool.req_to_token",
            "repaired_consumer": (
                "worker.target_worker.model_runner.req_to_token_pool.req_to_token"
            ),
            "fixture_result": relative(fixture_path),
            "fixture_sha256": sha256_file(fixture_path),
            "fixture_passed": fixture["passed"],
            "repaired_observer": relative(repaired_path),
            "repaired_observer_sha256": sha256_file(repaired_path),
            "repair_patch": relative(patch_path),
            "repair_patch_sha256": sha256_file(patch_path),
        },
        "unrecoverability_proof": {
            "observer_failure_order": (
                "The trace called _capture_pre at pinned dflash_worker_v2.py:528, "
                "failed while resolving ForwardBatch.req_to_token_pool before the "
                "target forward call, wrote the error, and set CAPTURED=True. Therefore "
                "the raw-logit and post-adjustment trace points never captured."
            ),
            "response_absence": (
                "Only the response byte count and SHA-256 remain. A digest cannot recover "
                "the response bytes or emitted token IDs."
            ),
            "aggregate_telemetry": aggregate_lines,
            "aggregate_telemetry_limit": (
                "The two server lines are time-window aggregates and do not identify "
                "request-25 verifier top-1, accepted prefix, bonus token, or commit length."
            ),
            "nontransfer_rule": (
                "Other c32 responses came from a different batch, request ordering, and "
                "mutable request/KV state; they cannot classify this consumed single-request sample."
            ),
            "missing_decision_fields": [
                "raw_first_position_top1",
                "post_adjustment_first_position_top1",
                "accepted_prefix_tokens",
                "accepted_prefix_length",
                "bonus_token",
                "commit_length",
                "pre_forward_request_to_token_prefix",
                "pre_forward_kv_digest",
                "raw_http_response_bytes_or_emitted_token_ids",
            ],
        },
        "decision": {
            "boundary": (
                "The stale ForwardBatch consumer is locally repairable and its ownership "
                "mapping is fixture-validated, but the already-consumed request-25 "
                "scientific boundary is unrecoverable from persisted evidence."
            ),
            "request25_disposition": (
                "Do not classify the DFlash verifier behavior from this invocation and "
                "do not replay it. Preserve it as a consumed, uninterpretable sample."
            ),
            "future_instrumentation": (
                "A future independently authorized experiment may use the repaired pool "
                "owner lookup; this offline result does not authorize endpoint contact."
            ),
        },
        "artifact_root": relative(artifact_root),
        "input_hash_manifest": relative(input_manifest_path),
        "input_hash_manifest_sha256": sha256_file(input_manifest_path),
    }
    atomic_json(result_path, result)

    outputs = [result_path, fixture_path, repaired_path, patch_path, input_manifest_path]
    output_manifest_path = artifact_root / "OUTPUTS.sha256"
    output_manifest_path.write_text(
        "".join(f"{sha256_file(path)}  {relative(path)}\n" for path in outputs)
    )
    result_sha_path = result_path.with_suffix(result_path.suffix + ".sha256")
    result_sha_path.write_text(f"{sha256_file(result_path)}  {relative(result_path)}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
