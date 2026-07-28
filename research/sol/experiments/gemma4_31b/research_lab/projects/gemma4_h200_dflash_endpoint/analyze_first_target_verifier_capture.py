#!/usr/bin/env python3
"""Reconstruct the bound request-25 DFlash verifier transition offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parent
CAPTURE_ROOT = PROJECT / "artifacts/candidate-only-owner-20260726t001857Z"
PACKET_ROOT = CAPTURE_ROOT / "packet"
BOUND_ROOT = PACKET_ROOT / "inputs/bound"

INPUTS = {
    "directive": (
        PROJECT / "DIRECTOR_FIRST_TARGET_VERIFIER_CAUSAL_REPAIR.json",
        "1880e7d1d946d6ad338d507d9691bb30e28c8eb35aeaa425977f10a746382d6a",
    ),
    "capture_terminal": (
        CAPTURE_ROOT / "DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_TERMINAL.json",
        "3eef108d6df6b93340b3cfe0a422b9620a25f63408b85beba4883f8c05a2bcdc",
    ),
    "capture_result": (
        CAPTURE_ROOT / "DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_RESULT.json",
        "cca4968e360d8969b96dae34e1186f8d655784db84a8d0a06540b3df06212913",
    ),
    "candidate_states": (
        CAPTURE_ROOT / "retrieved/states/dflash-depth4-c32.jsonl",
        "b00e778bc03e218bb98d97817831438b304ae64ca21d4e945be22209ce68f694",
    ),
    "candidate_endpoint_terminal": (
        CAPTURE_ROOT / "retrieved/results/dflash-depth4-c32/TERMINAL.json",
        "ea966215f852cb291f3cb5adee5e7376cbf36318450f7a014e17ab2583a33aa8",
    ),
    "ar_endpoint_terminal": (
        PROJECT
        / "artifacts/request-state-capture-owner-20260725T232227Z"
        / "retrieved-final/results/ar-c32/TERMINAL.json",
        "45b8120b452452b3ffcdc5282138e984140aa96b5802eef3d3ce66603a141af4",
    ),
    "worker_source": (
        BOUND_ROOT / "dflash_worker_v2.py",
        "8fbddb39f4b33b4ac55b1919bc58fa846acb60892886199251d3592a5223050f",
    ),
    "forward_batch_source": (
        BOUND_ROOT / "forward_batch_info.py",
        "c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516",
    ),
}

REQUEST_INDEX = 25
REQUEST_ID = "077dff09d0bc4ec1ad3af6ec056651b2"
REQUEST_SHA256 = "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def row_at(terminal: dict[str, Any], index: int) -> dict[str, Any]:
    rows = terminal["rows"]
    matches = [row for row in rows if int(row["index"]) == index]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one endpoint row at index {index}")
    return matches[0]


def source_line(source: str, needle: str) -> int:
    matches = [
        index
        for index, line in enumerate(source.splitlines(), start=1)
        if needle in line
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one source match for {needle!r}, got {matches}")
    return matches[0]


def source_lines(source: str, needle: str) -> list[int]:
    matches = [
        index
        for index, line in enumerate(source.splitlines(), start=1)
        if needle in line
    ]
    if not matches:
        raise AssertionError(f"expected at least one source match for {needle!r}")
    return matches


def parse_source_inventory(path: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, absolute_path = line.split(maxsplit=1)
        inventory[Path(absolute_path).name] = digest
    return inventory


def analyze() -> dict[str, Any]:
    integrity: dict[str, Any] = {}
    for name, (path, expected) in INPUTS.items():
        observed = sha256(path)
        if observed != expected:
            raise AssertionError(
                f"{name} hash mismatch: expected {expected}, observed {observed}"
            )
        integrity[name] = {
            "path": str(path.relative_to(PROJECT)),
            "sha256": observed,
        }

    directive = load_json(INPUTS["directive"][0])
    capture_terminal = load_json(INPUTS["capture_terminal"][0])
    capture_result = load_json(INPUTS["capture_result"][0])
    candidate_terminal = load_json(INPUTS["candidate_endpoint_terminal"][0])
    ar_terminal = load_json(INPUTS["ar_endpoint_terminal"][0])
    candidate_events = load_jsonl(INPUTS["candidate_states"][0])

    if capture_terminal["valid_scientific_capture"] is not True:
        raise AssertionError("source capture is not marked valid")
    if capture_terminal["ar_producer_replayed"] is not False:
        raise AssertionError("source capture unexpectedly replayed AR")
    if capture_result["observer_coverage"] != {
        "event_count": 64,
        "missing": [],
        "extra": [],
    }:
        raise AssertionError("candidate observer coverage is not exact")

    localization = capture_result["first_differing_captured_state"]
    expected_localization = {
        "request_index": REQUEST_INDEX,
        "request_id": REQUEST_ID,
        "phase": "first_target_step",
        "difference": {
            "field": "target_top1_first",
            "ar_expected": 3496,
            "candidate_observed": 759,
        },
    }
    if localization != expected_localization:
        raise AssertionError(f"unexpected localization: {localization}")

    ar_row = row_at(ar_terminal, REQUEST_INDEX)
    candidate_row = row_at(candidate_terminal, REQUEST_INDEX)
    if ar_row["request_sha256"] != REQUEST_SHA256:
        raise AssertionError("AR request-25 body identity changed")
    if candidate_row["request_sha256"] != REQUEST_SHA256:
        raise AssertionError("candidate request-25 body identity changed")
    if candidate_row["request_id"] != REQUEST_ID:
        raise AssertionError("candidate request-25 RID changed")

    events = {
        event["phase"]: event
        for event in candidate_events
        if event.get("request_id") == REQUEST_ID
    }
    if set(events) != {"target_prefill", "first_target_step"}:
        raise AssertionError(f"request-25 events incomplete: {sorted(events)}")
    prefill = events["target_prefill"]
    first_step = events["first_target_step"]

    if not (
        ar_row["token_ids"][:2] == [236814, 3496]
        and candidate_row["token_ids"][:2] == [236814, 759]
        and prefill["target_prefill_output"] == 236814
        and prefill["target_top1"] == 236814
        and prefill["target_output_matches_top1"] is True
        and prefill["sequence_length_after"] == 4214
    ):
        raise AssertionError("request-25 prefill/endpoint boundary changed")

    expected_first_step = {
        "verified_id": 236814,
        "draft_tokens": [236814, 174501, 74443, 104105],
        "target_top1": [759, 236814, 236761, 87096],
        "accepted_draft_count": 0,
        "accepted_prefix": [],
        "bonus_token": 759,
        "emitted_stream_tokens": [759],
        "commit_length": 1,
        "sequence_length_before": 4214,
        "sequence_length_after": 4215,
    }
    for field, expected in expected_first_step.items():
        if first_step[field] != expected:
            raise AssertionError(
                f"request-25 first-step {field}: "
                f"expected {expected!r}, observed {first_step[field]!r}"
            )

    worker_path = INPUTS["worker_source"][0]
    worker_source = worker_path.read_text(encoding="utf-8")
    target_forward_line = source_line(
        worker_source, "target_out = self.target_worker.forward_batch_generation("
    )
    adjustment_line = source_line(
        worker_source, "apply_dflash_verify_logits_adjustments("
    )
    target_predict_line = source_line(
        worker_source, "target_predict = torch.argmax("
    )
    triton_consumer_line = source_line(
        worker_source, "_compute_dflash_accept_bonus_triton_unchecked("
    )
    fallback_consumer_lines = source_lines(
        worker_source, "accept_len, bonus = compute_dflash_correct_drafts_and_bonus("
    )

    installed_inventory = parse_source_inventory(
        PACKET_ROOT / "EXPECTED_INSTALLED_SOURCE.sha256"
    )
    archived_v2_path = BOUND_ROOT / "dflash_info_v2.py"
    archived_v2_hash = sha256(archived_v2_path)
    executed_v2_hash = installed_inventory["dflash_info_v2.py"]
    if archived_v2_hash == executed_v2_hash:
        raise AssertionError("expected the known dflash_info_v2 source-identity gap")

    imported_unarchived = [
        module
        for module in ("dflash_info.py", "dflash_utils.py")
        if module not in installed_inventory and not (BOUND_ROOT / module).exists()
    ]
    if imported_unarchived != ["dflash_info.py", "dflash_utils.py"]:
        raise AssertionError(
            f"unexpected unarchived transition sources: {imported_unarchived}"
        )

    return {
        "schema_version": 1,
        "project": directive["project"],
        "classification": "capture_insufficient_for_cause",
        "decision": "no_offline_repair_candidate_emitted",
        "new_scientific_sample_consumed": False,
        "gpu_claimed": False,
        "endpoint_arm_replayed": False,
        "fresh_spend_usd": 0.0,
        "input_integrity": integrity,
        "request_25_transition": {
            "request_index": REQUEST_INDEX,
            "request_id": REQUEST_ID,
            "request_sha256": REQUEST_SHA256,
            "request_slot_at_capture": first_step["request_slot"],
            "ar_endpoint_prefix": ar_row["token_ids"][:2],
            "candidate_endpoint_prefix": candidate_row["token_ids"][:2],
            "matching_captured_prefill_boundary": {
                "target_prefill_output": prefill["target_prefill_output"],
                "target_top1": prefill["target_top1"],
                "sequence_length_after": prefill["sequence_length_after"],
                "prompt_cache_accounting": prefill["prompt_cache_accounting"],
                "kv_locations_sha256": prefill["kv_locations_sha256"],
                "kv_content_sha256": prefill["kv_content_sha256"],
            },
            "first_target_step": expected_first_step,
        },
        "causal_chain": {
            "first_incorrect_observable_symbol": {
                "symbol": "DFlashWorkerV2.forward_batch_generation.target_predict",
                "source": str(worker_path.relative_to(PROJECT)),
                "line": target_predict_line,
                "producer_expression": (
                    "torch.argmax(logits_output.next_token_logits, dim=-1)"
                ),
                "request_owned_value": first_step["target_top1"][0],
                "ar_target": ar_row["token_ids"][1],
            },
            "upstream_ambiguous_boundary": [
                {
                    "symbol": "TpModelWorker.forward_batch_generation",
                    "line": target_forward_line,
                    "role": "produces logits_output.next_token_logits and hidden_states",
                },
                {
                    "symbol": "apply_dflash_verify_logits_adjustments",
                    "line": adjustment_line,
                    "role": "may mutate next_token_logits before target_predict",
                },
            ],
            "downstream_consumer": {
                "symbols": [
                    "_compute_dflash_accept_bonus_triton_unchecked",
                    "compute_dflash_correct_drafts_and_bonus",
                ],
                "lines": [triton_consumer_line, *fallback_consumer_lines],
                "observed_decision": (
                    "draft_tokens[1]=174501 does not equal target_predict[0]=759; "
                    "accepted_draft_count=0 therefore selects bonus_token=759, "
                    "commit_length=1, and emits [759]"
                ),
                "consumer_consistent_with_input": True,
            },
        },
        "source_completeness": {
            "pass": False,
            "executed_dflash_info_v2_sha256": executed_v2_hash,
            "archived_dflash_info_v2_sha256": archived_v2_hash,
            "archived_copy_is_executed_copy": False,
            "unarchived_imported_transition_modules": imported_unarchived,
            "consequence": (
                "The exact verifier packaging and logit-adjustment implementations "
                "that executed cannot be audited or patched from the bound archive."
            ),
        },
        "capture_limit": {
            "distinguishable": [
                "prefill emitted/target top-1 is 236814",
                "verifier target top-1 row is [759,236814,236761,87096]",
                "acceptance and bonus consumption correctly propagate 759",
            ],
            "not_distinguishable": [
                "request-owned verifier positions and GPU versus CPU planning lengths",
                "the full four-slot verify KV mapping and pre-forward KV contents",
                "raw target logits before versus after logit adjustment",
                "target hidden state before the tied vocabulary head",
            ],
            "smallest_missing_state": (
                "One hash-bound request-25 record straddling "
                "TpModelWorker.forward_batch_generation: the exact pre-call "
                "ForwardBatch row (input_ids, positions, seq_lens, seq_lens_cpu, "
                "out_cache_loc, req_to_token prefix and pre-forward KV digest) plus "
                "the first-row raw top-1 before and after "
                "apply_dflash_verify_logits_adjustments."
            ),
        },
        "repair_candidate": None,
        "repair_gate": {
            "offline_request_25_replay_produced_3496": False,
            "previously_equal_boundaries_preserved_by_repair": None,
            "pass": False,
            "reason": (
                "No captured tensor can be changed offline to derive 3496, and "
                "emitting a patch against incomplete/non-executed source would be "
                "unsupported."
            ),
        },
        "claims": {
            "performance_authorized": False,
            "quality_preserved": False,
            "deployable": False,
            "gpu_reentry_authorized": False,
        },
        "next_action": (
            "Director disposition only. Do not replay either endpoint or claim a GPU; "
            "a later source-complete boundary probe would require explicit admission."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
