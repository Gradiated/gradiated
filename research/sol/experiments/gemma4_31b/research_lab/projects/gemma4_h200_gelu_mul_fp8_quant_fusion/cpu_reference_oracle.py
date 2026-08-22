#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import struct
from typing import Iterable


FP8_MAX = 448.0
GELU_ALPHA = 0.044715
GELU_BETA = 0.7978845608028654
EXACT_INTERMEDIATE = 21504


def float32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def bfloat16(value: float) -> float:
    bits = struct.unpack(">I", struct.pack(">f", float32(value)))[0]
    exponent = bits & 0x7F800000
    mantissa = bits & 0x007FFFFF
    if exponent == 0x7F800000 and mantissa:
        rounded = bits | 0x00400000
    else:
        rounded = bits + 0x7FFF + ((bits >> 16) & 1)
    return struct.unpack(">f", struct.pack(">I", rounded & 0xFFFF0000))[0]


def e4m3fn_decode(code: int) -> float:
    sign = -1.0 if code & 0x80 else 1.0
    exponent = (code >> 3) & 0xF
    mantissa = code & 0x7
    if exponent == 0:
        value = mantissa * (2.0**-9)
    elif exponent == 0xF:
        if mantissa == 0x7:
            return math.nan
        value = (1.0 + mantissa / 8.0) * (2.0**8)
    else:
        value = (1.0 + mantissa / 8.0) * (2.0 ** (exponent - 7))
    return math.copysign(value, sign)


POSITIVE_E4M3 = tuple(
    (code, e4m3fn_decode(code)) for code in range(0x7F)
)


def e4m3fn_encode(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("oracle accepts finite values only")
    sign = 0x80 if math.copysign(1.0, value) < 0 else 0
    magnitude = min(abs(value), FP8_MAX)
    code, _ = min(
        POSITIVE_E4M3,
        key=lambda item: (abs(item[1] - magnitude), item[0] & 1),
    )
    return sign | code


def stock_gelu_mul(gate: float, up: float) -> float:
    gate = bfloat16(gate)
    up = bfloat16(up)
    gate3 = float32(float32(gate * gate) * gate)
    argument = float32(GELU_BETA * float32(gate + GELU_ALPHA * gate3))
    cdf = float32(0.5 * float32(1.0 + math.tanh(argument)))
    return bfloat16(float32(float32(gate * cdf) * up))


def corrected_fused_gelu_mul(gate: float, up: float) -> float:
    gate = bfloat16(gate)
    up = bfloat16(up)
    gate3 = float32(float32(gate * gate) * gate)
    argument = float32(GELU_BETA * float32(gate + GELU_ALPHA * gate3))
    cdf = float32(0.5 * float32(1.0 + math.tanh(argument)))
    return bfloat16(float32(float32(gate * cdf) * up))


def rejected_two_round_gelu_mul(gate: float, up: float) -> float:
    gate = bfloat16(gate)
    up = bfloat16(up)
    gate3 = float32(float32(gate * gate) * gate)
    argument = float32(GELU_BETA * float32(gate + GELU_ALPHA * gate3))
    cdf = float32(0.5 * float32(1.0 + math.tanh(argument)))
    activated_gate = bfloat16(float32(gate * cdf))
    return bfloat16(float32(activated_gate * up))


def dynamic_quantize(row: list[float]) -> tuple[list[int], float]:
    maximum = max((abs(value) for value in row), default=0.0)
    scale = float32(maximum / FP8_MAX)
    if scale == 0.0:
        return [0x7E] * len(row), scale
    inverse_scale = float32(1.0 / scale)
    codes = [
        e4m3fn_encode(
            max(-FP8_MAX, min(FP8_MAX, float32(value * inverse_scale)))
        )
        for value in row
    ]
    return codes, scale


def dequantize(codes: list[int], scale: float) -> list[float]:
    return [float32(e4m3fn_decode(code) * scale) for code in codes]


def row_digest(codes: list[int], scale: float) -> str:
    payload = bytes(codes) + struct.pack(">f", scale)
    return hashlib.sha256(payload).hexdigest()


def consumer_probes(codes: list[int], scale: float) -> list[float]:
    activations = dequantize(codes, scale)
    outputs = []
    for probe in range(3):
        accumulator = 0.0
        for index, value in enumerate(activations):
            weight = ((index * (2 * probe + 3) + 11) % 31 - 15) / 16.0
            accumulator += value * weight
        outputs.append(bfloat16(accumulator * (0.125 * (probe + 1))))
    return outputs


def make_cases() -> list[dict]:
    mixed_gate = [
        -7.0,
        -3.25,
        -1.0,
        -0.125,
        -0.0,
        0.0,
        2.0**-20,
        0.125,
        0.75,
        1.0,
        2.5,
        6.0,
        15.5,
        -15.5,
        3.75,
        -2.25,
        0.333251953125,
    ]
    mixed_up = [
        0.0,
        -2.0,
        4.0,
        -8.0,
        16.0,
        -32.0,
        64.0,
        -128.0,
        0.03125,
        -0.0625,
        0.5,
        -1.5,
        3.0,
        -6.0,
        12.0,
        -24.0,
        48.0,
    ]
    exact_gate = [
        (((index * 37) % 257) - 128) / 19.0
        for index in range(EXACT_INTERMEDIATE)
    ]
    exact_up = [
        (((index * 53 + 7) % 263) - 131) / 23.0
        for index in range(EXACT_INTERMEDIATE)
    ]
    return [
        {"id": "all_zero_odd17", "gate": [0.0] * 17, "up": [0.0] * 17},
        {"id": "finite_saturation_tail17", "gate": mixed_gate, "up": mixed_up},
        {
            "id": "odd_row_count_3",
            "gate": mixed_gate * 3,
            "up": list(reversed(mixed_up)) * 3,
        },
        {
            "id": "representative_exact_width_21504",
            "gate": exact_gate,
            "up": exact_up,
        },
    ]


def compare_case(case: dict) -> dict:
    stock = [
        stock_gelu_mul(gate, up)
        for gate, up in zip(case["gate"], case["up"], strict=True)
    ]
    corrected = [
        corrected_fused_gelu_mul(gate, up)
        for gate, up in zip(case["gate"], case["up"], strict=True)
    ]
    rejected = [
        rejected_two_round_gelu_mul(gate, up)
        for gate, up in zip(case["gate"], case["up"], strict=True)
    ]
    stock_codes, stock_scale = dynamic_quantize(stock)
    corrected_codes, corrected_scale = dynamic_quantize(corrected)
    rejected_codes, rejected_scale = dynamic_quantize(rejected)
    stock_consumer = consumer_probes(stock_codes, stock_scale)
    corrected_consumer = consumer_probes(corrected_codes, corrected_scale)
    rejected_consumer = consumer_probes(rejected_codes, rejected_scale)
    corrected_match = (
        stock == corrected
        and stock_codes == corrected_codes
        and stock_scale == corrected_scale
        and stock_consumer == corrected_consumer
    )
    return {
        "id": case["id"],
        "elements": len(stock),
        "corrected_stock_activation_exact": stock == corrected,
        "corrected_stock_codes_exact": stock_codes == corrected_codes,
        "corrected_stock_scale_exact": stock_scale == corrected_scale,
        "corrected_stock_consumer_exact": stock_consumer == corrected_consumer,
        "corrected_pass": corrected_match,
        "stock_digest": row_digest(stock_codes, stock_scale),
        "corrected_digest": row_digest(corrected_codes, corrected_scale),
        "stock_scale": stock_scale,
        "fp8_max_code_count": sum(
            abs(e4m3fn_decode(code)) == FP8_MAX for code in stock_codes
        ),
        "zero_scale_stock_code": (
            stock_codes[0] if stock_scale == 0.0 and stock_codes else None
        ),
        "rejected_two_round_activation_mismatches": sum(
            left != right for left, right in zip(stock, rejected, strict=True)
        ),
        "rejected_two_round_code_mismatches": sum(
            left != right
            for left, right in zip(stock_codes, rejected_codes, strict=True)
        ),
        "rejected_two_round_scale_delta": abs(stock_scale - rejected_scale),
        "rejected_two_round_consumer_mismatches": sum(
            left != right
            for left, right in zip(
                stock_consumer, rejected_consumer, strict=True
            )
        ),
    }


def atomic_json(path: pathlib.Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    rows = [compare_case(case) for case in make_cases()]
    payload = {
        "schema_version": 1,
        "classification": "cpu_reference_oracle_pass",
        "semantics": {
            "activation": "GELU(tanh, FP32 expression) * up, one BF16 rounding",
            "quantization": "dynamic per-row E4M3FN, FP32 amax/448 scale",
            "zero_row": "stock c32 small-batch code +448 with scale 0",
            "consumer": "complete E4M3 dequantization plus three FP32 dot probes and BF16 output",
        },
        "rows": rows,
        "pass": all(row["corrected_pass"] for row in rows),
        "rejected_two_round_falsified": any(
            row["rejected_two_round_activation_mismatches"] > 0
            and row["rejected_two_round_consumer_mismatches"] > 0
            for row in rows
        ),
    }
    atomic_json(args.output, payload)
    return 0 if payload["pass"] and payload["rejected_two_round_falsified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
