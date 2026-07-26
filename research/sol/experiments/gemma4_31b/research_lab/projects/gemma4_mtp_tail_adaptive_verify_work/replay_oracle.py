#!/usr/bin/env python3
"""Replay the exact depth-1 MTP stream and bound adaptive fallback latency."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


EXPECTED = {
    "boundary": "7fe983448c88632d7f036da8d3ad8e23a58b821f7b1a5f2bff79dab9d4c550f6",
    "accepted_depth": "b8e51f929b1766fd33362c851059ea03f01cfcdd7fbf607fb2693590839f19e0",
    "control_terminal": "a6e69ac9534ae433fc45d3b5d3ea241fe63321d33423cdd52d17128d8072d278",
    "mtp_terminal": "80f3fc810ce4d9d5943d7387c7b3b6fb9e0097dfae9b7bf466f143303402f44b",
    "source_binding": "4b8e5edeb276b02317a85dd71a136a4002535467f08134edd3d77ce6de1300ce",
    "worker_source": "ffd537efe8c28cecdbef1f5984f5f90f81f655ec3c1a65dca68f25d2b9a24d99",
    "verify_source": "2948d3a52dd1915f7efc9f175c8b0d65f50b803fc4028647c91564cda597e82f",
    "scheduler_source": "3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4",
    "result_processor_source": "9c764afffb106e966fde110851de73bb6a3d0f2415343a574a255e91f86851de",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def default_inputs(project: Path) -> dict[str, Path]:
    sibling = project.parent / "sglang_v0512_h200_gemma4_mtp_endpoint"
    retrieved = (
        sibling
        / "artifacts"
        / "mtp-candidate-repair-20260723t0658z"
        / "retrieved"
    )
    source = sibling / "inputs" / "accepted_depth" / "runtime_source"
    return {
        "boundary": sibling / "MTP_OVERLAP_REOPENING.json",
        "accepted_depth": retrieved / "mtp-audit" / "accepted-depth.jsonl",
        "control_terminal": retrieved / "control" / "TERMINAL.json",
        "mtp_terminal": retrieved / "mtp" / "TERMINAL.json",
        "source_binding": sibling / "ACCEPTED_DEPTH_SOURCE_BINDING.json",
        "worker_source": source / "sglang_srt_speculative_frozen_kv_mtp_worker.py",
        "verify_source": source / "sglang_srt_speculative_eagle_info.py",
        "scheduler_source": source / "sglang_srt_managers_scheduler.py",
        "result_processor_source": (
            source / "sglang_srt_managers_scheduler_components_batch_result_processor.py"
        ),
    }


def validate_inputs(inputs: dict[str, Path]) -> list[dict[str, Any]]:
    bindings = []
    for name, path in inputs.items():
        actual = sha256(path)
        expected = EXPECTED[name]
        if actual != expected:
            raise ValueError(f"{name}: expected {expected}, got {actual}: {path}")
        bindings.append(
            {
                "name": name,
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": actual,
            }
        )
    return bindings


def replay(
    accepted_depth_path: Path,
    control_terminal: dict[str, Any],
    mtp_terminal: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with accepted_depth_path.open(encoding="utf-8") as handle:
        raw_events = [json.loads(line) for line in handle if line.strip()]
    if len(raw_events) % 2:
        raise ValueError("accepted-depth stream must alternate draft and verify events")

    output_limit = 358
    request_count = 32
    emitted = [1] * request_count
    accepts = [0] * request_count
    verifies = [0] * request_count
    finish_iteration: list[int | None] = [None] * request_count
    active = list(range(request_count))
    cumulative_assistant_s = 0.0
    cumulative_verify_s = 0.0
    reconstructed: list[dict[str, Any]] = []

    control_rows = control_terminal["rows"]
    boundary_row = max(control_rows, key=lambda row: row["ttft_seconds"])
    if boundary_row["decode_seconds"] != min(
        row["decode_seconds"] for row in control_rows
    ):
        raise ValueError("last-prefill control row is not the shortest decode trajectory")
    stock_rounds = output_limit - 1
    stock_round_s = boundary_row["decode_seconds"] / stock_rounds
    control_boundary_s = boundary_row["ttft_seconds"]

    cutoff_rows = [
        {
            "cutoff_iterations": 0,
            "mtp_component_s": 0.0,
            "fallback_rounds": stock_rounds,
            "fallback_s": boundary_row["decode_seconds"],
            "optimistic_total_s": control_terminal["batch_seconds"],
            "uses_mtp": False,
        }
    ]

    for event_offset in range(0, len(raw_events), 2):
        assistant_event = raw_events[event_offset]
        verify_event = raw_events[event_offset + 1]
        iteration = event_offset // 2 + 1
        if assistant_event.get("event") != "assistant_forward":
            raise ValueError(f"iteration {iteration}: assistant event missing")
        if verify_event.get("event") != "target_verify":
            raise ValueError(f"iteration {iteration}: verify event missing")
        batch_size = len(active)
        if assistant_event["batch_size"] != batch_size:
            raise ValueError(f"iteration {iteration}: assistant batch mismatch")
        if verify_event["batch_size"] != batch_size:
            raise ValueError(f"iteration {iteration}: verify batch mismatch")
        depths = verify_event["accepted_drafts_per_request"]
        if len(depths) != batch_size or any(depth not in (0, 1) for depth in depths):
            raise ValueError(f"iteration {iteration}: invalid accepted-depth vector")
        if sum(depths) != verify_event["accepted_drafts_total"]:
            raise ValueError(f"iteration {iteration}: accepted total mismatch")
        if verify_event["accepted_tokens_total"] != batch_size + sum(depths):
            raise ValueError(f"iteration {iteration}: emitted total mismatch")

        active_before = list(active)
        cumulative_assistant_s += assistant_event["elapsed_ms"] / 1000.0
        cumulative_verify_s += verify_event["elapsed_ms"] / 1000.0
        active_after = []
        for request_id, depth in zip(active_before, depths):
            verifies[request_id] += 1
            accepts[request_id] += depth
            emitted[request_id] += 1 + depth
            if emitted[request_id] > output_limit:
                raise ValueError(f"request {request_id}: output overshoot")
            if emitted[request_id] == output_limit:
                finish_iteration[request_id] = iteration
            else:
                active_after.append(request_id)
        active = active_after
        fallback_rounds = max(
            (output_limit - emitted[request_id] for request_id in active), default=0
        )
        mtp_component_s = cumulative_assistant_s + cumulative_verify_s
        fallback_s = fallback_rounds * stock_round_s
        optimistic_total_s = control_boundary_s + mtp_component_s + fallback_s
        reconstructed.append(
            {
                "iteration": iteration,
                "batch_size": batch_size,
                "active_request_ids_before": active_before,
                "accepted_drafts_per_request": depths,
                "accepted_drafts_total": sum(depths),
                "emitted_tokens_total": batch_size + sum(depths),
                "assistant_elapsed_ms": assistant_event["elapsed_ms"],
                "target_verify_elapsed_ms": verify_event["elapsed_ms"],
                "active_request_ids_after": active,
                "fallback_rounds_after": fallback_rounds,
                "cumulative_assistant_s": cumulative_assistant_s,
                "cumulative_target_verify_s": cumulative_verify_s,
                "optimistic_cutoff_total_s": optimistic_total_s,
            }
        )
        cutoff_rows.append(
            {
                "cutoff_iterations": iteration,
                "mtp_component_s": mtp_component_s,
                "fallback_rounds": fallback_rounds,
                "fallback_s": fallback_s,
                "optimistic_total_s": optimistic_total_s,
                "uses_mtp": True,
            }
        )

    if active or any(count != output_limit for count in emitted):
        raise ValueError("trace did not finish every request at exactly 358 tokens")
    if sum(verifies) != 6544 or sum(accepts) != 4880:
        raise ValueError("trace totals disagree with admitted historical boundary")
    if len(reconstructed) != 354:
        raise ValueError("expected 354 draft/verify iterations")

    first_shrink = next(row for row in reconstructed if row["batch_size"] < 32)
    # The cutoff just before the first smaller batch is the last bs=32 iteration.
    tail_cutoff = cutoff_rows[first_shrink["iteration"] - 1]
    best_speculative = min(
        (row for row in cutoff_rows if row["uses_mtp"]),
        key=lambda row: row["optimistic_total_s"],
    )
    by_batch: dict[int, dict[str, float | int]] = defaultdict(
        lambda: {
            "iterations": 0,
            "request_verifies": 0,
            "accepted_drafts": 0,
            "assistant_s": 0.0,
            "target_verify_s": 0.0,
        }
    )
    for row in reconstructed:
        bucket = by_batch[row["batch_size"]]
        bucket["iterations"] += 1
        bucket["request_verifies"] += row["batch_size"]
        bucket["accepted_drafts"] += row["accepted_drafts_total"]
        bucket["assistant_s"] += row["assistant_elapsed_ms"] / 1000.0
        bucket["target_verify_s"] += row["target_verify_elapsed_ms"] / 1000.0

    request_rows = [
        {
            "request_id": request_id,
            "accepted_drafts": accepts[request_id],
            "verify_iterations": verifies[request_id],
            "finish_iteration": finish_iteration[request_id],
            "emitted_tokens": emitted[request_id],
            "mtp_target_positions": 2 * verifies[request_id],
            "stock_target_positions": output_limit - 1,
        }
        for request_id in range(request_count)
    ]
    stock_target_positions = request_count * (output_limit - 1)
    full_mtp_target_positions = 2 * sum(verifies)
    rejected_drafts = sum(verifies) - sum(accepts)
    clairvoyant_target_positions = 2 * sum(accepts) + rejected_drafts
    if clairvoyant_target_positions != stock_target_positions:
        raise ValueError("depth-1 target-position conservation failed")

    summary = {
        "schema_version": 1,
        "evidence_class": {
            "event_stream": "measured",
            "source_semantics": "source-bound",
            "cutoff_oracle": "derived_from_measured",
            "request_local_work_oracle": "analytical_clairvoyant_lower_bound",
        },
        "workload": {
            "requests": request_count,
            "prompt_tokens_per_request": 4214,
            "output_tokens_per_request": output_limit,
            "first_tokens_before_trace": request_count,
        },
        "replay": {
            "iterations": len(reconstructed),
            "request_verifies": sum(verifies),
            "accepted_drafts": sum(accepts),
            "rejected_drafts": rejected_drafts,
            "emitted_tokens_after_first": sum(emitted) - request_count,
            "emitted_tokens_total": sum(emitted),
            "assistant_s": cumulative_assistant_s,
            "target_verify_s": cumulative_verify_s,
            "first_shrink_iteration": first_shrink["iteration"] - 1,
            "batch_aggregates": {str(key): value for key, value in sorted(by_batch.items())},
            "requests": request_rows,
        },
        "fallback_calibration": {
            "method": "last-prefill control row: 357 sequential stock decode rounds",
            "control_row_index": boundary_row["index"],
            "control_boundary_ttft_s": control_boundary_s,
            "control_decode_rounds": stock_rounds,
            "control_decode_s": boundary_row["decode_seconds"],
            "stock_round_s": stock_round_s,
            "control_batch_s": control_terminal["batch_seconds"],
        },
        "global_cutoff_oracle": {
            "model": (
                "control boundary TTFT + measured MTP component prefix + "
                "remaining longest-request rounds * fastest exact stock round; "
                "switching and endpoint overhead omitted"
            ),
            "best_overall": cutoff_rows[0],
            "best_with_at_least_one_mtp_iteration": best_speculative,
            "best_speculative_delta_vs_control_s": (
                best_speculative["optimistic_total_s"]
                - control_terminal["batch_seconds"]
            ),
            "tail_cutoff_before_first_shrink": tail_cutoff,
            "full_mtp_modeled_s": cutoff_rows[-1]["optimistic_total_s"],
            "full_mtp_measured_s": mtp_terminal["batch_seconds"],
            "cutoffs": cutoff_rows,
        },
        "request_local_target_work_oracle": {
            "stock_target_positions": stock_target_positions,
            "full_mtp_target_positions": full_mtp_target_positions,
            "full_mtp_excess_target_positions": (
                full_mtp_target_positions - stock_target_positions
            ),
            "clairvoyant_policy": (
                "use MTP only on request-iterations whose next depth-1 draft "
                "will be accepted; use stock decode on every rejection"
            ),
            "clairvoyant_target_positions": clairvoyant_target_positions,
            "clairvoyant_target_positions_saved": (
                stock_target_positions - clairvoyant_target_positions
            ),
            "clairvoyant_assistant_request_forwards": sum(accepts),
            "conclusion": (
                "At proposal depth 1, every accepted draft exchanges two target "
                "positions for two emitted tokens and every rejected draft is "
                "strictly extra work. Even future knowledge cannot reduce target "
                "positions below stock, and any realizable policy adds assistant work."
            ),
        },
    }
    return reconstructed, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    project = Path(__file__).resolve().parent
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project / "artifacts" / "adaptive-verify-oracle-v1",
    )
    args = parser.parse_args()
    inputs = default_inputs(project)
    bindings = validate_inputs(inputs)
    control = load_json(inputs["control_terminal"])
    mtp = load_json(inputs["mtp_terminal"])
    if not control["pass"] or not mtp["pass"]:
        raise ValueError("historical endpoint pair is not complete and interpretable")
    stream, oracle = replay(inputs["accepted_depth"], control, mtp)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stream_path = args.output_dir / "RECONSTRUCTED_EVENT_STREAM.jsonl"
    with stream_path.open("w", encoding="utf-8") as handle:
        for row in stream:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    oracle_path = args.output_dir / "ADAPTIVE_VERIFY_ORACLE.json"
    dump_json(oracle_path, oracle)

    terminal = {
        "schema_version": 1,
        "result_type": "mechanism_falsified",
        "mechanism": "request-local depth-1 MTP target-work adaptation",
        "decision": "do_not_implement_or_claim_gpu",
        "reason": (
            "The exact cutoff oracle selects zero MTP iterations. The best "
            "speculative cutoff is slower than the same-session control even "
            "after omitting switching/endpoint overhead. More fundamentally, "
            "a clairvoyant request-local policy saves zero target positions at "
            "depth 1 and still requires positive assistant work."
        ),
        "quality": {
            "target_semantics": "unchanged; analysis only",
            "exact_trace_replay": True,
            "all_requests_finished_at_358_tokens": True,
        },
        "oracle_key_results": {
            "same_session_control_s": control["batch_seconds"],
            "best_cutoff_iterations": 0,
            "best_speculative_cutoff_iterations": oracle["global_cutoff_oracle"][
                "best_with_at_least_one_mtp_iteration"
            ]["cutoff_iterations"],
            "best_speculative_optimistic_s": oracle["global_cutoff_oracle"][
                "best_with_at_least_one_mtp_iteration"
            ]["optimistic_total_s"],
            "tail_cutoff_optimistic_s": oracle["global_cutoff_oracle"][
                "tail_cutoff_before_first_shrink"
            ]["optimistic_total_s"],
            "clairvoyant_target_positions_saved": 0,
            "full_mtp_excess_target_positions": oracle[
                "request_local_target_work_oracle"
            ]["full_mtp_excess_target_positions"],
        },
        "source_semantics": {
            "worker": "batch-wide draft -> target verify -> accepted KV commit -> next seed",
            "verify_width": "speculative_num_steps + 1 = 2 target positions/request",
            "commit": "accepted tokens append to output_ids and advance kv_committed_len",
            "scheduler": "finished requests are filtered after speculative result processing",
        },
        "artifacts": {
            "oracle": str(oracle_path.resolve()),
            "oracle_sha256": sha256(oracle_path),
            "event_stream": str(stream_path.resolve()),
            "event_stream_sha256": sha256(stream_path),
            "replay_script": str(Path(__file__).resolve()),
            "replay_script_sha256": sha256(Path(__file__).resolve()),
            "inputs": bindings,
        },
        "spend": {
            "gpu_seconds": 0,
            "provider_mutation": False,
            "actual_spend_usd": 0.0,
        },
        "consumption": {
            "offline_oracle_result_consumed": True,
            "gpu_scientific_sample_consumed": False,
            "replay_allowed": False,
        },
    }
    terminal_path = project / "MTP_TAIL_ADAPTIVE_VERIFY_RESULT.json"
    dump_json(terminal_path, terminal)
    print(json.dumps(terminal, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
