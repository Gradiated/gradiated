#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import random
import struct


HIDDEN = 5376
EPSILON = 1e-6
FP8_MAXIMUM = 448.0
DEQUANTIZED_RELATIVE_L2_TOLERANCE = 0.003
SCALE_ABSOLUTE_TOLERANCE = 2.5e-7


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def float32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def bfloat16(value: float) -> float:
    bits = struct.unpack(">I", struct.pack(">f", float32(value)))[0]
    exponent = bits & 0x7F800000
    mantissa = bits & 0x007FFFFF
    if exponent == 0x7F800000 and mantissa:
        return struct.unpack(">f", struct.pack(">I", bits | 0x00010000))[0]
    rounded = bits + 0x7FFF + ((bits >> 16) & 1)
    return struct.unpack(">f", struct.pack(">I", rounded & 0xFFFF0000))[0]


def fp8_positive_values() -> tuple[float, ...]:
    values = {0.0}
    for mantissa in range(1, 8):
        values.add(mantissa * 2.0**-9)
    for exponent in range(1, 15):
        for mantissa in range(8):
            values.add((1.0 + mantissa / 8.0) * 2.0 ** (exponent - 7))
    for mantissa in range(7):
        values.add((1.0 + mantissa / 8.0) * 2.0**8)
    return tuple(sorted(values))


FP8_POSITIVE = fp8_positive_values()


def fp8_e4m3fn(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("FP8 oracle accepts finite values only")
    sign = -1.0 if value < 0.0 else 1.0
    magnitude = min(abs(value), FP8_MAXIMUM)
    lower = 0
    upper = len(FP8_POSITIVE) - 1
    while lower < upper:
        middle = (lower + upper) // 2
        if FP8_POSITIVE[middle] < magnitude:
            lower = middle + 1
        else:
            upper = middle
    right = lower
    left = max(0, right - 1)
    left_distance = magnitude - FP8_POSITIVE[left]
    right_distance = FP8_POSITIVE[right] - magnitude
    if left_distance < right_distance:
        selected = left
    elif right_distance < left_distance:
        selected = right
    else:
        selected = left if left % 2 == 0 else right
    return sign * FP8_POSITIVE[selected]


def reference_row(
    row: list[float], weight: list[float]
) -> tuple[list[float], float]:
    square_sum = math.fsum(value * value for value in row)
    inverse_rms = 1.0 / math.sqrt(square_sum / HIDDEN + EPSILON)
    normalized = [
        bfloat16(value * inverse_rms * scale)
        for value, scale in zip(row, weight)
    ]
    maximum = max(abs(value) for value in normalized)
    quant_scale = float32(maximum / FP8_MAXIMUM)
    inverse_scale = 0.0 if quant_scale == 0.0 else 1.0 / quant_scale
    quantized = [
        fp8_e4m3fn(max(-FP8_MAXIMUM, min(FP8_MAXIMUM, value * inverse_scale)))
        for value in normalized
    ]
    return quantized, quant_scale


def candidate_row(
    row: list[float], weight: list[float]
) -> tuple[list[float], float]:
    partial = [float32(0.0) for _ in range(256)]
    for column, value in enumerate(row):
        lane = column % 256
        partial[lane] = float32(partial[lane] + float32(value * value))
    warp_totals = []
    for warp in range(8):
        lanes = partial[warp * 32 : (warp + 1) * 32]
        for offset in (16, 8, 4, 2, 1):
            previous = lanes
            lanes = previous.copy()
            for lane in range(32 - offset):
                lanes[lane] = float32(
                    previous[lane] + previous[lane + offset]
                )
        warp_totals.append(lanes[0])
    lanes = warp_totals + [0.0] * 24
    for offset in (16, 8, 4, 2, 1):
        previous = lanes
        lanes = previous.copy()
        for lane in range(32 - offset):
            lanes[lane] = float32(previous[lane] + previous[lane + offset])
    square_sum = lanes[0]
    inverse_rms = float32(
        1.0 / math.sqrt(float32(square_sum / HIDDEN + EPSILON))
    )
    normalized = [
        bfloat16(float32(float32(value * inverse_rms) * scale))
        for value, scale in zip(row, weight)
    ]
    maximum = max(abs(value) for value in normalized)
    quant_scale = float32(maximum / FP8_MAXIMUM)
    inverse_scale = 0.0 if quant_scale == 0.0 else float32(1.0 / quant_scale)
    quantized = [
        fp8_e4m3fn(
            max(
                -FP8_MAXIMUM,
                min(FP8_MAXIMUM, float32(value * inverse_scale)),
            )
        )
        for value in normalized
    ]
    return quantized, quant_scale


def compare(
    inputs: list[list[float]], weight: list[float]
) -> dict[str, object]:
    reference_dequantized: list[float] = []
    candidate_dequantized: list[float] = []
    byte_equivalent = 0
    total = 0
    maximum_scale_error = 0.0
    saturation = 0
    nonfinite = 0
    for row in inputs:
        reference_q, reference_scale = reference_row(row, weight)
        candidate_q, candidate_scale = candidate_row(row, weight)
        maximum_scale_error = max(
            maximum_scale_error, abs(reference_scale - candidate_scale)
        )
        for reference, candidate in zip(reference_q, candidate_q):
            reference_value = reference * reference_scale
            candidate_value = candidate * candidate_scale
            reference_dequantized.append(reference_value)
            candidate_dequantized.append(candidate_value)
            byte_equivalent += reference == candidate
            total += 1
            saturation += abs(candidate) == FP8_MAXIMUM
            nonfinite += not math.isfinite(candidate_value)
    difference_squared = math.fsum(
        (reference - candidate) ** 2
        for reference, candidate in zip(
            reference_dequantized, candidate_dequantized
        )
    )
    reference_squared = math.fsum(
        value * value for value in reference_dequantized
    )
    relative_l2 = math.sqrt(difference_squared) / max(
        math.sqrt(reference_squared), 1e-30
    )
    return {
        "dequantized_relative_l2_error": relative_l2,
        "quantized_value_match_fraction": byte_equivalent / total,
        "scale_max_abs_error": maximum_scale_error,
        "saturation_fraction": saturation / total,
        "nonfinite_count": nonfinite,
        "pass": (
            relative_l2 <= DEQUANTIZED_RELATIVE_L2_TOLERANCE
            and maximum_scale_error <= SCALE_ABSOLUTE_TOLERANCE
            and nonfinite == 0
        ),
    }


def random_rows(rows: int, seed: int) -> list[list[float]]:
    generator = random.Random(seed)
    return [
        [
            bfloat16(
                generator.gauss(0.0, 0.72)
                + (6.0 if column % 997 == 0 else 0.0)
            )
            for column in range(HIDDEN)
        ]
        for _ in range(rows)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    generator = random.Random(20260729)
    weight = [
        bfloat16(0.82 + 0.36 * generator.random()) for _ in range(HIDDEN)
    ]
    cases = {
        "production_m32_random": compare(
            random_rows(32, 2026072901), weight
        ),
        "zero_m1": compare([[0.0] * HIDDEN], weight),
        "tiny_m1": compare(
            [[bfloat16((-1.0 if i & 1 else 1.0) * 2.0**-20) for i in range(HIDDEN)]],
            weight,
        ),
        "extreme_m1": compare(
            [[bfloat16((-1.0 if i & 1 else 1.0) * (64.0 if i % 257 == 0 else 0.25)) for i in range(HIDDEN)]],
            weight,
        ),
    }
    from runtime_adapter import should_fuse

    dispatch = {
        "m1": should_fuse((1, HIDDEN), "torch.bfloat16"),
        "m32": should_fuse((32, HIDDEN), "torch.bfloat16"),
        "m33": should_fuse((33, HIDDEN), "torch.bfloat16"),
        "wrong_hidden": should_fuse((32, HIDDEN + 1), "torch.bfloat16"),
        "wrong_dtype": should_fuse((32, HIDDEN), "torch.float16"),
    }
    passed = (
        all(case["pass"] for case in cases.values())
        and dispatch
        == {
            "m1": True,
            "m32": True,
            "m33": False,
            "wrong_hidden": False,
            "wrong_dtype": False,
        }
    )
    result = {
        "schema_version": 1,
        "classification": (
            "cpu_oracle_pass" if passed else "cpu_oracle_failure"
        ),
        "pass": passed,
        "geometry": {
            "hidden_size": HIDDEN,
            "production_rows": 32,
            "dtype": "bfloat16",
            "output_dtype": "float8_e4m3fn",
            "scale": "per_token_float32",
            "epsilon": EPSILON,
        },
        "finite_tolerance": {
            "dequantized_relative_l2": DEQUANTIZED_RELATIVE_L2_TOLERANCE,
            "scale_max_abs": SCALE_ABSOLUTE_TOLERANCE,
            "basis": {
                "kind": "prior exact-H200 A/A-derived finite envelope",
                "observed_plain_path_max": 0.002190457424148917,
                "observed_shapes": [32, 118, 1409, 1631, 2048],
                "margin_factor": (
                    DEQUANTIZED_RELATIVE_L2_TOLERANCE
                    / 0.002190457424148917
                ),
            },
        },
        "cases": cases,
        "dispatch": dispatch,
    }
    if args.output:
        atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
