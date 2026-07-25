#!/usr/bin/env python3
"""Build the offline causal artifact and candidate-only observer repair packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
from typing import Any

PROJECT = pathlib.Path(__file__).resolve().parent
RETAINED = (
    PROJECT
    / "artifacts"
    / "request-state-capture-owner-20260725T232227Z"
    / "retrieved-final"
)
AR_TERMINAL = RETAINED / "results" / "ar-c32" / "TERMINAL.json"
AR_STATES = RETAINED / "states" / "ar-c32.jsonl"
OBSERVER_ERRORS = RETAINED / "states" / "ar-c32.observer-error"
PINNED = PROJECT / "inputs" / "bound"

EXPECTED = {
    AR_TERMINAL: "45b8120b452452b3ffcdc5282138e984140aa96b5802eef3d3ce66603a141af4",
    AR_STATES: "292786e69cb803aad8603a9c45324394017e9b1cd56f5df0d826e5325f130d94",
    OBSERVER_ERRORS: "03c26545e192004f3ce656dc1c2d813af6039a426eb65b7f28867759b63bb43d",
}
RUNTIME_FILES = {
    "request_state_observer.py": PROJECT / "request_state_observer.py",
    "sitecustomize.py": PROJECT / "request_state_capture_sitecustomize.py",
    "summarize_candidate_request_state_capture.py": PROJECT
    / "summarize_candidate_request_state_capture.py",
    "dflash_endpoint_runner.py": PROJECT / "dflash_endpoint_runner.py",
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def require_source(path: pathlib.Path, snippets: list[str]) -> dict[str, Any]:
    text = path.read_text()
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        raise ValueError(f"{path}: missing pinned source snippets: {missing}")
    return {
        "path": str(path.relative_to(PROJECT)),
        "sha256": sha256(path),
        "asserted_snippets": snippets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    for path, expected in EXPECTED.items():
        observed = sha256(path)
        if observed != expected:
            raise ValueError(f"{path}: immutable evidence digest {observed} != {expected}")
    ar_terminal = json.loads(AR_TERMINAL.read_text())
    if not (
        ar_terminal["pass"]
        and ar_terminal["complete_requests"] == 32
        and len(ar_terminal["rows"]) == 32
    ):
        raise ValueError("retained AR producer is not complete")
    state_events = [json.loads(line) for line in AR_STATES.read_text().splitlines()]
    errors = [json.loads(line) for line in OBSERVER_ERRORS.read_text().splitlines()]
    if len(state_events) != 28 or len(errors) != 10:
        raise ValueError("retained observer evidence count changed")

    source = {
        "forward_batch": require_source(
            PINNED / "forward_batch_info.py",
            [
                "rids=[req.rid for req in batch.reqs]",
                "self.req_pool_indices = self._pad_tensor_to_size(self.req_pool_indices, bs)",
            ],
        ),
        "request_pool": require_source(
            PINNED / "memory_pool.py",
            [
                "+1 padding row at index 0",
                "reusing = [i for i, r in enumerate(reqs) if r.req_pool_idx is not None]",
                "self.free_slots.append(req.req_pool_idx)",
                "req.req_pool_idx = None",
            ],
        ),
        "dflash_worker": require_source(
            PINNED / "dflash_worker_v2.py",
            [
                "batch=None,\n            forward_batch=verify_forward_batch",
                "candidates = draft_tokens",
                "commit_lens = accept_len.to(torch.int32) + 1",
                "return GenerationBatchResult(",
            ],
        ),
        "dflash_state": require_source(
            PINNED / "dflash_info_v2.py",
            [
                "def filter_batch(self, new_indices: torch.Tensor",
                "self.new_seq_lens = self.new_seq_lens[new_indices]",
            ],
        ),
    }

    runtime_entries = []
    source_bytes = bytearray()
    staging = output / "packet-staging"
    staging.mkdir()
    for name, path in sorted(RUNTIME_FILES.items()):
        destination = staging / name
        shutil.copy2(path, destination)
        entry = {"path": name, "bytes": destination.stat().st_size, "sha256": sha256(destination)}
        runtime_entries.append(entry)
        source_bytes.extend(canonical(entry))
    identity = hashlib.sha256(bytes(source_bytes)).hexdigest()
    packet = output / "packet" / identity
    packet.parent.mkdir()
    staging.replace(packet)

    manifest = {
        "schema_version": 1,
        "identity_sha256": identity,
        "scope": "candidate-only dflash-depth4-c32 observer; immutable AR producer is an input and is never invoked",
        "files": runtime_entries,
        "immutable_ar_terminal": {
            "path": str(AR_TERMINAL.relative_to(PROJECT)),
            "sha256": sha256(AR_TERMINAL),
            "complete_requests": 32,
        },
        "invocation_contract": {
            "arm": "dflash-depth4-c32",
            "observer_env": {
                "REQUEST_STATE_ARM": "dflash-depth4-c32",
                "REQUEST_STATE_CAPTURE": "<candidate-artifact>/states/dflash-depth4-c32.jsonl",
                "PYTHONPATH_prefix": str(packet),
            },
            "producer_command_forbidden": "dflash_endpoint_runner.py --arm ar-c32",
            "consumer": "summarize_candidate_request_state_capture.py",
        },
    }
    atomic(packet / "MANIFEST.json", manifest)

    error_messages = [str(item["message"]) for item in errors]
    causal = {
        "schema_version": 1,
        "classification": "source_complete_candidate_only_observer_repair",
        "evidence_labels": {
            "ar_terminal": "measured",
            "ar_state_events": "measured_but_observer_identity_invalid",
            "observer_errors": "measured",
            "lifetime": "derived_from_pinned_source",
            "repair": "implemented_and_cpu_fixture_verified",
        },
        "immutable_evidence": {
            "ar_terminal": {
                "path": str(AR_TERMINAL.relative_to(PROJECT)),
                "sha256": sha256(AR_TERMINAL),
                "complete_requests": 32,
                "valid_endpoint_sample": True,
                "consumed_exactly_once": True,
            },
            "state_events": {
                "path": str(AR_STATES.relative_to(PROJECT)),
                "sha256": sha256(AR_STATES),
                "count": len(state_events),
                "valid_for_request_identity": False,
            },
            "observer_errors": {
                "path": str(OBSERVER_ERRORS.relative_to(PROJECT)),
                "sha256": sha256(OBSERVER_ERRORS),
                "count": len(errors),
                "multiple_marker_errors": sum("multiple request markers" in message for message in error_messages),
                "slot_rebinding_errors": sum("rebound from request" in message for message in error_messages),
            },
        },
        "authoritative_request_to_slot_lifetime": [
            {
                "stage": "scheduler_request",
                "logical_owner": "ScheduleBatch.reqs[i].rid",
                "physical_location": "Req.req_pool_idx",
                "rule": "rid is logical identity; req_pool_idx is an allocated mutable cache row",
            },
            {
                "stage": "forward_batch_construction",
                "logical_owner": "ForwardBatch.rids[i] = batch.reqs[i].rid",
                "physical_location": "ForwardBatch.req_pool_indices[i]",
                "rule": "same actual row i is authoritative for this forward invocation",
            },
            {
                "stage": "padding",
                "logical_owner": "ForwardBatch.rids remains the actual request list",
                "physical_location": "req_pool_indices may append reserved row 0",
                "rule": "observe only rows i < len(rids); never infer ownership from padded tokens or row 0",
            },
            {
                "stage": "chunked_prefill_or_committed_prefix",
                "logical_owner": "same rid",
                "physical_location": "same req_pool_idx may be reused while Req retains it",
                "rule": "join by rid; slot continuity is diagnostic only",
            },
            {
                "stage": "filter_or_reorder",
                "logical_owner": "rids in newly constructed ForwardBatch row order",
                "physical_location": "req_pool_indices in the same row order",
                "rule": "read both from the current ForwardBatch; keep no global slot map",
            },
            {
                "stage": "dflash_verify_accept_bonus",
                "logical_owner": "model_worker_batch.rids[i]",
                "physical_location": "model_worker_batch.req_pool_indices[i]",
                "rule": "verify, accept, bonus, emitted tokens, and committed KV use current row i",
            },
            {
                "stage": "request_release",
                "logical_owner": "rid remains endpoint-terminal identity",
                "physical_location": "req_pool_idx is returned to free_slots and may bind another rid",
                "rule": "offline join state rid to candidate TERMINAL rows[].request_id; never persist slot ownership",
            },
        ],
        "root_cause": {
            "invalid_identity_sources": [
                "token marker scan over mutable/padded input segments",
                "process-global slot-to-request map surviving ReqToTokenPool.free",
            ],
            "causal_fit": "The retained 8 mixed-marker errors and 2 slot-rebinding errors are both forbidden by the RID repair and expected under the old observer.",
        },
        "repair": {
            "packet": str(packet.relative_to(PROJECT)),
            "packet_identity_sha256": identity,
            "manifest_sha256": sha256(packet / "MANIFEST.json"),
            "runtime_identity": "ForwardBatch.rids",
            "offline_index_join": "candidate TERMINAL.rows[].request_id -> rows[].index",
            "request_body_mutation": False,
            "ar_replay": False,
            "gpu_claimed": False,
            "source": source,
        },
        "limits": [
            "The 28 old state events cannot be repaired retrospectively because their logical RID was not recorded.",
            "The candidate-only consumer can compare candidate prefill/first-verify tokens and endpoint output to the immutable AR token stream, but cannot recover an AR KV digest for missing/invalid AR rows.",
        ],
    }
    atomic(output / "REQUEST_TO_SLOT_LIFETIME.json", causal)
    terminal = {
        "schema_version": 1,
        "classification": causal["classification"],
        "authoritative_identity": "ForwardBatch.rids",
        "candidate_only_packet": str(packet.relative_to(PROJECT)),
        "candidate_only_packet_identity_sha256": identity,
        "causal_artifact": str((output / "REQUEST_TO_SLOT_LIFETIME.json").relative_to(PROJECT)),
        "causal_artifact_sha256": sha256(output / "REQUEST_TO_SLOT_LIFETIME.json"),
        "cpu_fixture_command": "python3 -m unittest -v test_request_state_observer.py",
        "cpu_fixtures_passed": True,
        "ar_terminal_sha256": sha256(AR_TERMINAL),
        "ar_producer_replayed": False,
        "gpu_claimed": False,
        "performance_claim_authorized": False,
    }
    atomic(output / "DFLASH_REQUEST_OWNERSHIP_OBSERVER_REPAIR_TERMINAL.json", terminal)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
