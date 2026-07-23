#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import statistics


COMPARATOR = 0.6556567115001144
SCHEDULER_GAP_SHARE = 0.048096


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def token_rows(value: dict) -> list[list[int]]:
    rows = sorted(value["rows"], key=lambda row: row["index"])
    return [row["token_ids"] for row in rows]


def component(args: argparse.Namespace) -> int:
    control = load(args.control)
    candidate = load(args.candidate)
    control_runner = load(args.control_runner)
    candidate_runner = load(args.candidate_runner)
    expected_candidate_blocks = [7, 8, 6]
    token_equal = token_rows(control) == token_rows(candidate)
    positions_equal = (
        control["start_positions"] == candidate["start_positions"]
        and control["end_positions"] == candidate["end_positions"]
    )
    transitions = candidate.get("kv_transitions", [])
    transition_pass = (
        len(transitions) == 3
        and all(row.get("locations_unique") for row in transitions)
        and [row.get("block_len") for row in transitions]
        == expected_candidate_blocks
        and [row.get("output_lengths") for row in transitions]
        == [[8], [16], [22]]
    )
    boundary_ratio = candidate["decode_boundaries"] / control["decode_boundaries"]
    timing_ratio = (
        candidate["elapsed_decode_wall_seconds"]
        / control["elapsed_decode_wall_seconds"]
    )
    measured_timing_positive = math.isfinite(timing_ratio) and timing_ratio < 1
    conservative_reduction = SCHEDULER_GAP_SHARE * (1 - boundary_ratio)
    predicted = COMPARATOR * (1 - conservative_reduction)
    passed = all(
        [
            control.get("pass") is True,
            candidate.get("pass") is True,
            control_runner.get("pass") is True,
            candidate_runner.get("pass") is True,
            token_equal,
            positions_equal,
            transition_pass,
            candidate.get("finite_outputs") is True,
            candidate.get("block_lengths") == expected_candidate_blocks,
            control.get("decode_boundaries") == 21,
            candidate.get("decode_boundaries") == 3,
            candidate.get("model_graph_replays") == 21,
            measured_timing_positive,
            conservative_reduction > 0,
        ]
    )
    output = {
        "schema_version": 1,
        "stage": "component",
        "pass": passed,
        "classification": (
            "component_pass_positive_bound"
            if passed
            else "component_numerical_semantic_or_bound_reject"
        ),
        "token_id_equality": token_equal,
        "position_transition_equality": positions_equal,
        "kv_transition_pass": transition_pass,
        "finite_outputs": candidate.get("finite_outputs"),
        "logical_blocks": [8, 8, 6],
        "candidate_decode_replay_blocks": expected_candidate_blocks,
        "control_decode_boundaries": control.get("decode_boundaries"),
        "candidate_decode_boundaries": candidate.get("decode_boundaries"),
        "control_host_result_syncs": control.get("host_result_syncs"),
        "candidate_host_result_syncs": candidate.get("host_result_syncs"),
        "model_graph_replays": candidate.get("model_graph_replays"),
        "host_boundary_ratio": boundary_ratio,
        "host_boundaries_reduction_fraction": 1 - boundary_ratio,
        "control_decode_wall_seconds": control.get("elapsed_decode_wall_seconds"),
        "candidate_decode_wall_seconds": candidate.get(
            "elapsed_decode_wall_seconds"
        ),
        "measured_decode_wall_ratio": timing_ratio,
        "measured_timing_positive": measured_timing_positive,
        "scheduler_gap_share_input": SCHEDULER_GAP_SHARE,
        "conservative_whole_request_reduction_fraction": conservative_reduction,
        "conservative_candidate_seconds_per_request_bound": predicted,
        "qualified_comparator_seconds_per_request": COMPARATOR,
        "endpoint_gate": passed,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 20


def stream_token_texts(path: pathlib.Path, limit: int) -> list[str]:
    values: list[str] = []
    for line in path.read_text().splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        event = json.loads(line[6:])
        choices = event.get("choices") or []
        if not choices:
            continue
        choice = choices[0]
        if choice.get("finish_reason") is not None and choice.get("text", "") == "":
            continue
        if event.get("usage") is not None and choice.get("text", "") == "":
            continue
        values.append(str(choice.get("text", "")))
        if len(values) == limit:
            break
    return values


def component_recovered(args: argparse.Namespace) -> int:
    candidate = load(args.candidate)
    candidate_runner = load(args.candidate_runner)
    expected_candidate_blocks = [7, 8, 6]
    transitions = candidate.get("kv_transitions", [])
    topology_pass = (
        candidate.get("pass") is True
        and candidate.get("finite_outputs") is True
        and candidate.get("block_lengths") == expected_candidate_blocks
        and candidate.get("decode_boundaries") == 3
        and candidate.get("host_result_syncs") == 3
        and candidate.get("model_graph_replays") == 21
        and len(candidate.get("rows", [])) == 32
        and all(row.get("token_count") == 22 for row in candidate["rows"])
        and len(transitions) == 3
        and all(row.get("locations_unique") for row in transitions)
        and [row.get("block_len") for row in transitions]
        == expected_candidate_blocks
        and [row.get("output_lengths") for row in transitions]
        == [[8], [16], [22]]
        and candidate_runner.get("pass") is True
    )
    text_rows_equal = True
    text_row_lengths: list[list[int]] = []
    for index in range(32):
        control = stream_token_texts(
            args.control_runner_dir / f"response-{index:02d}.sse", 22
        )
        contender = stream_token_texts(
            args.candidate_runner_dir / f"response-{index:02d}.sse", 22
        )
        text_rows_equal = text_rows_equal and control == contender
        text_row_lengths.append([len(control), len(contender)])
    output = {
        "schema_version": 1,
        "stage": "component",
        "pass": False,
        "classification": "component_reject_control_token_ids_unrecoverable",
        "candidate_topology_pass": topology_pass,
        "candidate_finite_outputs": candidate.get("finite_outputs"),
        "decoded_token_event_equality": text_rows_equal,
        "decoded_token_event_row_lengths": text_row_lengths,
        "token_id_equality": None,
        "token_id_equality_reason": (
            "The completed stock producer persisted SSE text but its result "
            "consumer did not persist token IDs; the pinned tokenizer is not "
            "injective over streamed token text, so exact stock IDs cannot be "
            "reconstructed without replaying the consumed producer."
        ),
        "candidate_decode_replay_blocks": candidate.get("block_lengths"),
        "candidate_decode_boundaries": candidate.get("decode_boundaries"),
        "candidate_host_result_syncs": candidate.get("host_result_syncs"),
        "candidate_model_graph_replays": candidate.get("model_graph_replays"),
        "candidate_kv_transitions": transitions,
        "endpoint_gate": False,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 20


def gpu_summary(path: pathlib.Path) -> dict[str, float | None]:
    values: dict[str, list[float]] = {
        "utilization_gpu_pct": [],
        "memory_used_mib": [],
        "power_w": [],
    }
    with path.open() as handle:
        for row in csv.DictReader(handle):
            for key in values:
                raw = row.get(key)
                if raw is None:
                    continue
                try:
                    value = float(raw.strip())
                except ValueError:
                    continue
                if math.isfinite(value):
                    values[key].append(value)
    return {
        f"{key}_{stat}": (
            None
            if not rows
            else statistics.mean(rows)
            if stat == "mean"
            else statistics.median(rows)
        )
        for key, rows in values.items()
        for stat in ("mean", "median")
    }


def endpoint(args: argparse.Namespace) -> int:
    component_result = load(args.component)
    control = load(args.control)
    candidate = load(args.candidate)
    runner = load(args.runner)
    token_equal = token_rows(control) == token_rows(candidate)
    expected_blocks = [7] + [8] * 43 + [6]
    block_pass = candidate.get("block_lengths") == expected_blocks
    rows_pass = (
        len(candidate.get("rows", [])) == 32
        and all(row.get("token_count") == 358 for row in candidate["rows"])
    )
    cache = runner.get("cache", {})
    accounting = (
        cache.get("cached_prompt_tokens_delta") == 17120
        and cache.get("uncached_prompt_tokens_delta") == 117728
    )
    latency = float(runner["service_seconds_per_request"])
    valid = all(
        [
            component_result.get("pass") is True,
            control.get("pass") is True,
            candidate.get("pass") is True,
            runner.get("pass") is True,
            token_equal,
            block_pass,
            rows_pass,
            accounting,
            candidate.get("finite_outputs") is True,
            candidate.get("decode_boundaries") == 45,
            candidate.get("model_graph_replays") == 357,
            runner.get("complete_requests") == 32,
            math.isfinite(latency),
        ]
    )
    result_pass = valid and latency < COMPARATOR
    output = {
        "schema_version": 1,
        "status": "terminal",
        "classification": (
            "endpoint_positive"
            if result_pass
            else "endpoint_nonpositive_or_invalid"
        ),
        "pass": result_pass,
        "valid": valid,
        "token_id_equality": token_equal,
        "fixed_block_schedule_pass": block_pass,
        "finite_32x358_pass": rows_pass and candidate.get("finite_outputs") is True,
        "cache_accounting_pass": accounting,
        "candidate_decode_boundaries": candidate.get("decode_boundaries"),
        "candidate_model_graph_replays": candidate.get("model_graph_replays"),
        "candidate_seconds_per_request": latency,
        "qualified_comparator_seconds_per_request": COMPARATOR,
        "reduction_fraction": 1 - latency / COMPARATOR,
        "complete_request_throughput": runner.get("complete_request_throughput"),
        "output_tokens_per_second": runner.get("output_tokens_per_second"),
        "gpu": gpu_summary(args.gpu),
        "component": component_result,
        "quality_claim_authorized": False,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0 if valid else 20


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    component_parser = subparsers.add_parser("component")
    component_parser.add_argument("--control", type=pathlib.Path, required=True)
    component_parser.add_argument("--candidate", type=pathlib.Path, required=True)
    component_parser.add_argument(
        "--control-runner", type=pathlib.Path, required=True
    )
    component_parser.add_argument(
        "--candidate-runner", type=pathlib.Path, required=True
    )
    component_parser.add_argument("--output", type=pathlib.Path, required=True)
    recovered_parser = subparsers.add_parser("component-recovered")
    recovered_parser.add_argument(
        "--control-runner-dir", type=pathlib.Path, required=True
    )
    recovered_parser.add_argument(
        "--candidate-runner-dir", type=pathlib.Path, required=True
    )
    recovered_parser.add_argument("--candidate", type=pathlib.Path, required=True)
    recovered_parser.add_argument(
        "--candidate-runner", type=pathlib.Path, required=True
    )
    recovered_parser.add_argument("--output", type=pathlib.Path, required=True)
    endpoint_parser = subparsers.add_parser("endpoint")
    endpoint_parser.add_argument("--component", type=pathlib.Path, required=True)
    endpoint_parser.add_argument("--control", type=pathlib.Path, required=True)
    endpoint_parser.add_argument("--candidate", type=pathlib.Path, required=True)
    endpoint_parser.add_argument("--runner", type=pathlib.Path, required=True)
    endpoint_parser.add_argument("--gpu", type=pathlib.Path, required=True)
    endpoint_parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.command == "component":
        return component(args)
    if args.command == "component-recovered":
        return component_recovered(args)
    return endpoint(args)


if __name__ == "__main__":
    raise SystemExit(main())
