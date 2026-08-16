#!/usr/bin/env python3
"""Pure, CPU-safe scientific contract for the H100 direct FP8 packet."""

CASES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("merged_gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
)
DECODE_M = (8, 16, 32)
PREFILL_M = 3679
OUTPUT_TOKENS = 358
PLANNING_CEILING = 0.5479752315195353


def selected(stage):
    if stage == "primary":
        return ((CASES[0], 8),)
    if stage == "conditional":
        return tuple((case, m) for case in CASES for m in (*DECODE_M, PREFILL_M))
    raise ValueError(f"unknown stage: {stage}")


def aggregate(rows):
    expected = {(case[0], m) for case in CASES for m in (*DECODE_M, PREFILL_M)}
    observed = {(row["case"], row["m"]) for row in rows}
    if len(rows) != 24 or observed != expected:
        raise RuntimeError("expected exactly six unique shapes at M8/M16/M32/M3679")
    prefill = [row for row in rows if row["m"] == PREFILL_M]
    prefill_s = sum(
        row["architecture_multiplicity"]
        * row["candidate_timing"]["cuda_event"]["p50_ms"]
        for row in prefill
    ) / 1000
    by_concurrency = {}
    for concurrency in DECODE_M:
        decode = [row for row in rows if row["m"] == concurrency]
        decode_s = sum(
            row["architecture_multiplicity"]
            * row["candidate_timing"]["cuda_event"]["p50_ms"]
            for row in decode
        ) * OUTPUT_TOKENS / concurrency / 1000
        total = prefill_s + decode_s
        by_concurrency[str(concurrency)] = {
            "concurrency": concurrency,
            "prefill_linear_seconds_per_request": prefill_s,
            "decode_linear_seconds_per_request": decode_s,
            "linear_component_floor_seconds_per_request": total,
            "planning_service_ceiling_seconds_per_request": PLANNING_CEILING,
            "planning_falsified_by_linear_lower_bound": total > PLANNING_CEILING,
            "admission_permitted_if_below": False,
            "decode_normalization": (
                f"architecture weighting, multiply by 358, divide by c{concurrency} exactly once"
            ),
            "prefill_normalization": "architecture weighting, no concurrency division",
        }
    return {
        "by_concurrency": by_concurrency,
        "omissions": [
            "vocabulary head",
            "attention and KV movement",
            "KV cache writer",
            "norm/rotary/activation/sampling/scheduler/service overhead",
            "FP8 production and quantization",
        ],
        "decision_boundary": (
            "Only an above-ceiling linear lower bound falsifies H100 planning economics; "
            "a below-ceiling result is not endpoint or FP8 admission."
        ),
    }
