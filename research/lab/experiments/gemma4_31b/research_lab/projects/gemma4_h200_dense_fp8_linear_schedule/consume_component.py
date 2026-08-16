#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re


EXPECTED_PREFILL_M = {1409, 1631, 2048}
DOWN_WALL_SECONDS = 1.251315209
PROFILE_WALL_SECONDS = 23.038600455
PROMOTION_GATE = 0.05
ECONOMIC_CEILING_SECONDS_PER_REQUEST = 0.6381105231


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=pathlib.Path, required=True)
    parser.add_argument("--runner-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--build-log", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--sync-terminal", type=pathlib.Path)
    parser.add_argument("--sync-binding", type=pathlib.Path)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.audit.read_text().splitlines() if line]
    runner = json.loads(args.runner_terminal.read_text())
    prefill = [row for row in rows if row.get("phase") == "prefill_real_consumer_measurement"]
    production_prefill = [row for row in prefill if int(row["shape_mnk"][0]) in EXPECTED_PREFILL_M]
    decode = [row for row in rows if row.get("phase") == "decode_fallback_runtime_invocation"]
    observed_prefill_m = {int(row["shape_mnk"][0]) for row in prefill}
    correctness = bool(prefill) and all(
        row["relative_l2"] <= 0.005
        and row["cosine"] >= 0.9999
        and row["reference_nonfinite"] == 0
        and row["candidate_nonfinite"] == 0
        and row["returned_to_unchanged_downstream_consumer"] is True
        for row in prefill
    )
    speedups = [float(row["candidate_speedup_fraction"]) for row in production_prefill]
    weighted_component_speedup = sum(speedups) / len(speedups) if speedups else float("-inf")
    predicted_whole_request_gain = weighted_component_speedup * DOWN_WALL_SECONDS / PROFILE_WALL_SECONDS
    exact_shapes = EXPECTED_PREFILL_M.issubset(observed_prefill_m) and any(
        row.get("shape_mnk") == [32, 5376, 21504] for row in decode
    )
    endpoint_semantics = runner.get("pass") is True and runner.get("complete_requests") == 32
    sync_result = None
    sync_stack_promote = False
    if args.sync_terminal is not None or args.sync_binding is not None:
        if args.sync_terminal is None or args.sync_binding is None:
            raise ValueError("sync_terminal_and_binding_must_be_supplied_together")
        terminal_bytes = args.sync_terminal.read_bytes()
        binding = json.loads(args.sync_binding.read_text())
        terminal_sha256 = hashlib.sha256(terminal_bytes).hexdigest()
        if terminal_sha256 != binding["sha256"]:
            raise ValueError("sync_terminal_hash_mismatch")
        terminal = json.loads(terminal_bytes)
        control = terminal.get("control", {})
        candidate = terminal.get("candidate", {})
        sync_compatible = bool(
            terminal.get("pass") is True
            and control.get("complete_requests") == 32
            and candidate.get("complete_requests") == 32
            and binding.get("immutable_binding_sha256")
            == "cebc435c4eb1e5716c4aa9bd854785a3e7cac4b0665c96ea6a44040b3e96fb62"
        )
        sync_candidate_seconds = float(terminal["candidate_service_seconds_per_request"])
        stacked_seconds = sync_candidate_seconds * (1.0 - predicted_whole_request_gain)
        sync_stack_promote = sync_compatible and stacked_seconds <= ECONOMIC_CEILING_SECONDS_PER_REQUEST
        sync_result = {
            "compatible": sync_compatible,
            "classification": terminal.get("classification"),
            "candidate_service_seconds_per_request": sync_candidate_seconds,
            "stacked_predicted_service_seconds_per_request": stacked_seconds,
            "economic_ceiling_seconds_per_request": ECONOMIC_CEILING_SECONDS_PER_REQUEST,
            "terminal_sha256": terminal_sha256,
        }
    standalone_promote = predicted_whole_request_gain >= PROMOTION_GATE
    promote = correctness and exact_shapes and endpoint_semantics and (standalone_promote or sync_stack_promote)
    build_text = args.build_log.read_text(errors="replace")
    resources = sorted(set(re.findall(r"Used \d+ registers[^\n]*", build_text)))
    value = {
        "schema_version": 1,
        "classification": "component_promote_endpoint" if promote else "component_no_endpoint_promotion",
        "pass": correctness and exact_shapes and endpoint_semantics,
        "correctness_pass": correctness,
        "exact_shape_pass": exact_shapes,
        "endpoint_semantics_pass": endpoint_semantics,
        "observed_prefill_m": sorted(observed_prefill_m),
        "decode_fallback_shapes": [row["shape_mnk"] for row in decode],
        "component_speedup_fraction_mean_of_shape_medians": weighted_component_speedup,
        "predicted_whole_request_gain_fraction": predicted_whole_request_gain,
        "promotion_gate_fraction": PROMOTION_GATE,
        "standalone_promotion_pass": standalone_promote,
        "sync_stack_promotion_pass": sync_stack_promote,
        "sync_result": sync_result,
        "promote_endpoint": promote,
        "compiler_resource_lines": resources,
        "rows": prefill,
    }
    atomic(args.output, value)
    return 0 if value["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
