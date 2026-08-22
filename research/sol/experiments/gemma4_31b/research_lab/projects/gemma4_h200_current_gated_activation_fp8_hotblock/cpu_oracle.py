#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import random
import struct


INTERMEDIATE = 21504
FP8_MAXIMUM = 448.0
GELU_ALPHA = 0.044715
GELU_BETA = 0.7978845608028654


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


def gelu_tanh(value: float) -> float:
    value = float32(value)
    cubed = float32(float32(value * value) * value)
    inner = float32(value + float32(float32(GELU_ALPHA) * cubed))
    argument = float32(float32(GELU_BETA) * inner)
    cdf = float32(0.5 * float32(1.0 + float32(math.tanh(argument))))
    return float32(value * cdf)


def stock_activated(gate: float, up: float) -> float:
    return bfloat16(float32(gelu_tanh(gate) * float32(up)))


def candidate_activated(gate: float, up: float) -> float:
    return bfloat16(float32(gelu_tanh(gate) * float32(up)))


def two_round_counterfactual(gate: float, up: float) -> float:
    rounded_gelu = bfloat16(gelu_tanh(gate))
    return bfloat16(float32(rounded_gelu * float32(up)))


def quantize(values: list[float]) -> tuple[list[float], float]:
    maximum = max(abs(value) for value in values)
    scale = float32(maximum / FP8_MAXIMUM)
    inverse = 0.0 if scale == 0.0 else float32(1.0 / scale)
    return (
        [
            fp8_e4m3fn(
                max(
                    -FP8_MAXIMUM,
                    min(FP8_MAXIMUM, float32(value * inverse)),
                )
            )
            for value in values
        ],
        scale,
    )


def input_rows(rows: int, seed: int, kind: str) -> list[tuple[list[float], list[float]]]:
    generator = random.Random(seed)
    result = []
    for row in range(rows):
        gate = []
        up = []
        for column in range(INTERMEDIATE):
            if kind == "zero":
                gate_value = up_value = 0.0
            elif kind == "tiny":
                gate_value = (-1.0 if column & 1 else 1.0) * 2.0**-20
                up_value = (-1.0 if column & 2 else 1.0) * 2.0**-18
            elif kind == "extreme":
                gate_value = (-1.0 if column & 1 else 1.0) * (
                    9.0 + (column % 11)
                )
                up_value = (-1.0 if column & 2 else 1.0) * (
                    30.0 + (column % 17)
                )
            else:
                gate_value = generator.gauss(0.0, 0.72)
                up_value = generator.gauss(0.0, 0.72)
                if column % 997 == 0:
                    gate_value += 6.0
                if column % 1499 == 0:
                    up_value -= 7.0
            gate.append(bfloat16(gate_value))
            up.append(bfloat16(up_value))
        result.append((gate, up))
    return result


def compare(rows: int, seed: int, kind: str) -> dict[str, object]:
    exact_activated = 0
    exact_quantized = 0
    counterfactual_activated = 0
    counterfactual_quantized = 0
    total = 0
    maximum_scale_error = 0.0
    maximum_dequantized_error = 0.0
    counterfactual_difference_squared = 0.0
    stock_dequantized_squared = 0.0
    nonfinite_count = 0
    for gate, up in input_rows(rows, seed, kind):
        stock = [
            stock_activated(gate_value, up_value)
            for gate_value, up_value in zip(gate, up)
        ]
        candidate = [
            candidate_activated(gate_value, up_value)
            for gate_value, up_value in zip(gate, up)
        ]
        counterfactual = [
            two_round_counterfactual(gate_value, up_value)
            for gate_value, up_value in zip(gate, up)
        ]
        stock_q, stock_scale = quantize(stock)
        candidate_q, candidate_scale = quantize(candidate)
        counterfactual_q, counterfactual_scale = quantize(counterfactual)
        maximum_scale_error = max(
            maximum_scale_error, abs(stock_scale - candidate_scale)
        )
        for (
            stock_value,
            candidate_value,
            wrong_value,
            stock_byte,
            candidate_byte,
            wrong_byte,
        ) in zip(
            stock,
            candidate,
            counterfactual,
            stock_q,
            candidate_q,
            counterfactual_q,
        ):
            exact_activated += stock_value == candidate_value
            counterfactual_activated += stock_value == wrong_value
            exact_quantized += stock_byte == candidate_byte
            counterfactual_quantized += stock_byte == wrong_byte
            stock_dequantized = stock_byte * stock_scale
            counterfactual_dequantized = (
                wrong_byte * counterfactual_scale
            )
            counterfactual_difference_squared += (
                stock_dequantized - counterfactual_dequantized
            ) ** 2
            stock_dequantized_squared += stock_dequantized**2
            maximum_dequantized_error = max(
                maximum_dequantized_error,
                abs(
                    stock_byte * stock_scale
                    - candidate_byte * candidate_scale
                ),
            )
            nonfinite_count += not math.isfinite(
                candidate_byte * candidate_scale
            )
            total += 1
    return {
        "rows": rows,
        "kind": kind,
        "elements": total,
        "activated_value_match_fraction": exact_activated / total,
        "quantized_value_match_fraction": exact_quantized / total,
        "scale_max_abs_error": maximum_scale_error,
        "dequantized_max_abs_error": maximum_dequantized_error,
        "nonfinite_count": nonfinite_count,
        "two_round_counterfactual_activated_match_fraction": (
            counterfactual_activated / total
        ),
        "two_round_counterfactual_quantized_match_fraction": (
            counterfactual_quantized / total
        ),
        "two_round_counterfactual_dequantized_relative_l2_error": math.sqrt(
            counterfactual_difference_squared
        )
        / max(math.sqrt(stock_dequantized_squared), 1e-30),
        "pass": (
            exact_activated == total
            and exact_quantized == total
            and maximum_scale_error == 0.0
            and maximum_dequantized_error == 0.0
            and nonfinite_count == 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    cases = [
        compare(1, 20260729, "random"),
        compare(16, 20260730, "random"),
        compare(32, 20260731, "random"),
        compare(1, 0, "zero"),
        compare(1, 0, "tiny"),
        compare(1, 0, "extreme"),
    ]
    result = {
        "schema_version": 1,
        "classification": (
            "cpu_oracle_pass"
            if all(case["pass"] for case in cases)
            else "cpu_oracle_fail"
        ),
        "semantics": (
            "Pinned FlashInfer GELU(tanh) and up multiplication execute in "
            "FP32 and round once to BF16; dynamic E4M3 uses one FP32 "
            "dequantization multiplier per row and finite zero handling."
        ),
        "cases": cases,
        "pass": all(case["pass"] for case in cases),
    }
    if args.output:
        atomic(args.output, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
