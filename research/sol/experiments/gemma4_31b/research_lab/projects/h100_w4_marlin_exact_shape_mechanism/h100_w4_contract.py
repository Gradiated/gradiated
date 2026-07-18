#!/usr/bin/env python3
import argparse
import json
import math


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
H100_SXM_SMS = 132
H100_SXM_BANDWIDTH_BYTES_S = 3.35e12
H100_SXM_BF16_FLOPS_S = 989.5e12
H100_SXM_L2_BYTES = 50 * 1024**2
AWQ_INTERLEAVE = (0, 2, 4, 6, 1, 3, 5, 7)
AWQ_REVERSE = (0, 4, 1, 5, 2, 6, 3, 7)


def selected(stage: str):
    if stage == "sentinel":
        return ((CASES[0], 8),)
    if stage == "sweep":
        return tuple((case, m) for case in CASES for m in (*DECODE_M, PREFILL_M))
    raise ValueError(f"unknown stage: {stage}")


def awq_pack_row(values: list[int]) -> list[int]:
    if len(values) % 8:
        raise ValueError("AWQ uint4 packing requires a multiple of eight columns")
    packed = []
    for start in range(0, len(values), 8):
        group = values[start : start + 8]
        word = 0
        for shift, source in enumerate(AWQ_INTERLEAVE):
            word |= (group[source] & 0xF) << (4 * shift)
        packed.append(word)
    return packed


def awq_to_standard_row(packed: list[int]) -> list[int]:
    result = []
    for word in packed:
        unpacked = [(word >> (4 * shift)) & 0xF for shift in range(8)]
        result.extend(unpacked[index] for index in AWQ_REVERSE)
    return result


def split_prefill(m: int) -> list[int]:
    splits = []
    remaining = m
    while remaining:
        part = min(remaining // 64, 16) * 64
        if part == 0:
            part = remaining
        splits.append(part)
        remaining -= part
    return splits


def marlin_config(m: int) -> dict[str, object]:
    if m <= 8:
        thread_m, thread_k, thread_n, threads = 8, 128, 128, 256
    elif m <= 16:
        thread_m, thread_k, thread_n, threads = 16, 128, 128, 256
    else:
        thread_m, thread_k, thread_n, threads = min(math.ceil(m / 16), 4) * 16, 64, 256, 256
    sh_a = 4 * thread_m * thread_k * 2
    sh_b = 4 * thread_k * thread_n // 2
    sh_red = thread_m * (thread_n + 8) * 2
    sh_bias = thread_n * 2
    temporary = max(sh_b, sh_red, min(sh_b, sh_red) + sh_bias)
    sh_scales = 4 * thread_n * 2
    sh_zero_points = sh_scales // 4
    return {
        "thread_m": thread_m,
        "thread_k": thread_k,
        "thread_n": thread_n,
        "threads": threads,
        "resident_warps_per_sm_upper_bound": threads // 32,
        "warp_occupancy_upper_bound": (threads // 32) / 64,
        "computed_shared_bytes": temporary + sh_a + sh_scales + sh_zero_points,
        "launched_blocks": H100_SXM_SMS,
        "launch_blocks_per_sm": 1,
    }


def analytic_row(case: tuple[str, int, int, int], m: int) -> dict[str, object]:
    name, k, n, multiplicity = case
    weight_bytes = k * n * (0.5 + 2 / 128 + 0.5 / 128)
    io_bytes = 2 * m * (k + n)
    total_bytes = weight_bytes + io_bytes
    flops = 2 * m * k * n
    intensity = flops / total_bytes
    return {
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "logical_w4_weight_scale_zp_bytes": weight_bytes,
        "activation_output_bytes": io_bytes,
        "logical_arithmetic_intensity_flop_per_byte": intensity,
        "h100_sxm_ridge_flop_per_byte": H100_SXM_BF16_FLOPS_S / H100_SXM_BANDWIDTH_BYTES_S,
        "nominal_roofline_limiter": "memory" if intensity < H100_SXM_BF16_FLOPS_S / H100_SXM_BANDWIDTH_BYTES_S else "compute",
        "logical_weights_fit_50_mib_l2": weight_bytes <= H100_SXM_L2_BYTES,
        "marlin_config": marlin_config(m),
        "host_launch_splits": split_prefill(m),
        "host_launch_configs": [marlin_config(split) for split in split_prefill(m)],
    }


def aggregate(rows: list[dict[str, object]], timing_key: str = "cold_candidate_timing") -> dict[str, object]:
    expected = {(case[0], m) for case in CASES for m in (*DECODE_M, PREFILL_M)}
    observed = {(str(row["case"]), int(row["m"])) for row in rows}
    if len(rows) != 24 or observed != expected:
        raise RuntimeError("expected exactly six unique shapes at M8/M16/M32/M3679")
    prefill_s = sum(
        int(row["architecture_multiplicity"])
        * float(row[timing_key]["cuda_event"]["p50_ms"])
        for row in rows
        if int(row["m"]) == PREFILL_M
    ) / 1000
    by_concurrency = {}
    for concurrency in DECODE_M:
        decode_s = sum(
            int(row["architecture_multiplicity"])
            * float(row[timing_key]["cuda_event"]["p50_ms"])
            for row in rows
            if int(row["m"]) == concurrency
        ) * OUTPUT_TOKENS / concurrency / 1000
        floor = prefill_s + decode_s
        by_concurrency[str(concurrency)] = {
            "prefill_linear_seconds_per_request": prefill_s,
            "decode_linear_seconds_per_request": decode_s,
            "linear_component_floor_seconds_per_request": floor,
            "planning_service_ceiling_seconds_per_request": PLANNING_CEILING,
            "planning_falsified_by_linear_lower_bound": floor > PLANNING_CEILING,
            "admission_permitted_if_below": False,
        }
    return {"timing_basis": timing_key, "by_concurrency": by_concurrency}


def paired_aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    candidate = aggregate(rows, "cold_candidate_timing")
    bf16 = aggregate(rows, "cold_bf16_comparator_timing")
    relative = {}
    for concurrency in DECODE_M:
        key = str(concurrency)
        w4_floor = candidate["by_concurrency"][key]["linear_component_floor_seconds_per_request"]
        bf16_floor = bf16["by_concurrency"][key]["linear_component_floor_seconds_per_request"]
        relative[key] = {
            "w4_linear_floor_seconds_per_request": w4_floor,
            "bf16_linear_floor_seconds_per_request": bf16_floor,
            "w4_linear_reduction_fraction": 1 - w4_floor / bf16_floor,
            "w4_planning_ceiling_falsified": w4_floor > PLANNING_CEILING,
            "whole_request_five_percent_claim_permitted": False,
        }
    return {
        "w4_cold": candidate,
        "bf16_cold": bf16,
        "relative": relative,
        "claim_boundary": "Component reduction and an under-ceiling W4 floor establish plausibility only; omitted request work prevents a whole-request claim.",
    }


def self_test() -> dict[str, object]:
    quantized = [0, 15, 3, 12, 7, 8, 1, 14, 5, 10, 2, 13, 6, 9, 4, 11]
    packed = awq_pack_row(quantized)
    recovered = awq_to_standard_row(packed)
    poisoned = list(packed)
    poisoned[0] ^= 0x1
    poisoned_recovered = awq_to_standard_row(poisoned)
    analytics = [analytic_row(case, m) for case, m in selected("sweep")]
    synthetic_rows = []
    for case, m in selected("sweep"):
        synthetic_rows.append(
            {
                "case": case[0],
                "m": m,
                "architecture_multiplicity": case[3],
                "cold_candidate_timing": {"cuda_event": {"p50_ms": 1.0}},
                "cold_bf16_comparator_timing": {"cuda_event": {"p50_ms": 2.0}},
            }
        )
    synthetic_aggregate = aggregate(synthetic_rows)
    synthetic_paired = paired_aggregate(synthetic_rows)
    checks = {
        "awq_interleave_roundtrip": recovered == quantized,
        "single_nibble_poison_detected": poisoned_recovered != quantized,
        "all_exact_shapes_divisible_by_group_128": all(case[1] % 128 == 0 for case in CASES),
        "all_exact_outputs_divisible_by_marlin_min_n_64": all(case[2] % 64 == 0 for case in CASES),
        "exactly_24_sweep_rows": len(analytics) == 24,
        "m8_m16_m32_nominal_memory_limited": all(row["nominal_roofline_limiter"] == "memory" for row in analytics if row["m"] in DECODE_M),
        "m3679_nominal_compute_limited": all(row["nominal_roofline_limiter"] == "compute" for row in analytics if row["m"] == PREFILL_M),
        "one_cta_per_sm_caps_warp_occupancy": all(row["marlin_config"]["warp_occupancy_upper_bound"] == 0.125 for row in analytics),
        "m3679_host_split_is_1024_1024_1024_576_31": split_prefill(PREFILL_M) == [1024, 1024, 1024, 576, 31],
        "aggregation_applies_multiplicity_decode_steps_and_concurrency_once": abs(
            synthetic_aggregate["by_concurrency"]["16"]["linear_component_floor_seconds_per_request"]
            - (0.24 + 0.24 * OUTPUT_TOKENS / 16)
        ) < 1e-12,
        "paired_aggregation_keeps_bf16_and_w4_distinct": abs(
            synthetic_paired["relative"]["16"]["w4_linear_reduction_fraction"] - 0.5
        ) < 1e-12,
    }
    return {
        "schema_version": 1,
        "pass": all(checks.values()),
        "checks": checks,
        "packed_fixture_hex": [hex(word) for word in packed],
        "analytics": analytics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("--self-test is required")
    result = self_test()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
