#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics


EXPECTED_PREFILL_M = {1409, 1631, 2048}
FP8_LINEAR_WALL_FRACTION = 0.24058942625425167
GATE_UP_FRACTION_OF_FP8 = 0.4479598989974649
GATE_UP_WALL_FRACTION = FP8_LINEAR_WALL_FRACTION * GATE_UP_FRACTION_OF_FP8
PROMOTION_GATE = 0.03


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
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.audit.read_text().splitlines() if line]
    runner = json.loads(args.runner_terminal.read_text())
    prefill = [row for row in rows if row.get("phase") == "prefill_real_consumer_measurement"]
    decode = [row for row in rows if row.get("phase") == "decode_fallback_runtime_invocation"]
    calls = [row for row in rows if row.get("phase") == "target_path_call"]
    observed_prefill_m = {int(row["shape_mnk"][0]) for row in prefill}
    call_counts: dict[int, int] = {}
    for row in calls:
        m = int(row["shape_mnk"][0])
        call_counts[m] = call_counts.get(m, 0) + 1
    correctness = bool(prefill) and all(
        row["projection"]["relative_l2"] <= 0.005
        and row["projection"]["cosine"] >= 0.9999
        and row["projection"]["reference_nonfinite"] == 0
        and row["projection"]["candidate_nonfinite"] == 0
        and row["unchanged_gelu_and_mul"]["relative_l2"] <= 0.005
        and row["unchanged_gelu_and_mul"]["cosine"] >= 0.9999
        and row["unchanged_gelu_and_mul"]["reference_nonfinite"] == 0
        and row["unchanged_gelu_and_mul"]["candidate_nonfinite"] == 0
        and row["returned_to_unchanged_gelu_and_mul"] is True
        for row in prefill
    )
    measured_by_m = {int(row["shape_mnk"][0]): row for row in prefill}
    weighted_stock = 0.0
    weighted_candidate = 0.0
    for m, count in call_counts.items():
        row = measured_by_m.get(m)
        if row is None:
            continue
        weighted_stock += count * float(row["stock"]["median_us"])
        weighted_candidate += count * float(row["candidate"]["median_us"])
    if weighted_stock:
        weighted_component_speedup = 1.0 - weighted_candidate / weighted_stock
    else:
        speedups = [float(row["candidate_speedup_fraction"]) for row in prefill]
        weighted_component_speedup = statistics.fmean(speedups) if speedups else float("-inf")
    predicted_whole_request_gain = weighted_component_speedup * GATE_UP_WALL_FRACTION
    exact_shapes = EXPECTED_PREFILL_M.issubset(observed_prefill_m) and any(
        row.get("shape_mnk") == [32, 43008, 5376] for row in decode
    )
    endpoint_semantics = runner.get("pass") is True and runner.get("complete_requests") == 32
    promote = (
        correctness
        and exact_shapes
        and endpoint_semantics
        and predicted_whole_request_gain >= PROMOTION_GATE
    )
    build_text = args.build_log.read_text(errors="replace")
    resources = sorted(set(re.findall(r"Used \d+ registers[^\n]*", build_text)))
    spills = sorted(set(re.findall(r"\d+ bytes spill stores, \d+ bytes spill loads", build_text)))
    value = {
        "schema_version": 1,
        "classification": "component_promote_endpoint" if promote else "component_no_endpoint_promotion",
        "pass": correctness and exact_shapes and endpoint_semantics,
        "correctness_pass": correctness,
        "exact_shape_pass": exact_shapes,
        "endpoint_semantics_pass": endpoint_semantics,
        "observed_prefill_m": sorted(observed_prefill_m),
        "decode_fallback_shapes": [row["shape_mnk"] for row in decode],
        "target_call_counts_by_m": {str(key): value for key, value in sorted(call_counts.items())},
        "component_speedup_fraction_weighted_by_observed_calls": weighted_component_speedup,
        "gate_up_wall_fraction": GATE_UP_WALL_FRACTION,
        "predicted_whole_request_gain_fraction": predicted_whole_request_gain,
        "promotion_gate_fraction": PROMOTION_GATE,
        "promote_endpoint": promote,
        "stock_launches_per_layer": 1,
        "candidate_launches_per_layer": 1,
        "stock_consumer_recharacterization": "one packed gate_up_proj GEMM, not two GEMM launches",
        "compiler_resource_lines": resources,
        "compiler_spill_lines": spills,
        "rows": prefill,
    }
    atomic(args.output, value)
    return 0 if value["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
