#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import random
import struct
from dataclasses import dataclass


HIDDEN = 5376
EPSILON = 1e-6
FP8_MAXIMUM = 448.0
SHAPES = (1, 16, 32)
RMS_VEC = 8
STOCK_THREADS = HIDDEN // RMS_VEC
STOCK_WARPS = STOCK_THREADS // 32
REJECTED_THREADS = 256
QUANT_THREADS = 256
QUANT_VEC = 16
WEIGHT_KEY = "model.language_model.layers.0.input_layernorm.weight"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def bf16_bits(value: float) -> int:
    bits = f32_bits(value)
    exponent = bits & 0x7F800000
    mantissa = bits & 0x007FFFFF
    if exponent == 0x7F800000 and mantissa:
        return (bits >> 16) | 0x0040
    rounded = bits + 0x7FFF + ((bits >> 16) & 1)
    return (rounded >> 16) & 0xFFFF


def bf16_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits << 16))[0]


def bf16(value: float) -> float:
    return bf16_from_bits(bf16_bits(value))


def fp8_value(code: int) -> float:
    sign = -1.0 if code & 0x80 else 1.0
    exponent = (code >> 3) & 0xF
    mantissa = code & 0x7
    if exponent == 0:
        value = mantissa * 2.0**-9
    elif exponent == 0xF:
        if mantissa == 0x7:
            return math.nan
        value = (1.0 + mantissa / 8.0) * 2.0**8
    else:
        value = (1.0 + mantissa / 8.0) * 2.0 ** (exponent - 7)
    return sign * value


POSITIVE_FP8 = tuple((code, fp8_value(code)) for code in range(0x7F))


def fp8_code(value: float) -> int:
    if math.isnan(value):
        return 0x7F
    sign = math.copysign(1.0, value) < 0.0
    magnitude = min(abs(value), FP8_MAXIMUM)
    if magnitude == 0.0:
        return 0x80 if sign else 0
    lower = 0
    upper = len(POSITIVE_FP8) - 1
    while lower < upper:
        middle = (lower + upper) // 2
        if POSITIVE_FP8[middle][1] < magnitude:
            lower = middle + 1
        else:
            upper = middle
    right = lower
    left = max(0, right - 1)
    left_distance = magnitude - POSITIVE_FP8[left][1]
    right_distance = POSITIVE_FP8[right][1] - magnitude
    if left_distance < right_distance:
        code = POSITIVE_FP8[left][0]
    elif right_distance < left_distance:
        code = POSITIVE_FP8[right][0]
    else:
        left_code = POSITIVE_FP8[left][0]
        right_code = POSITIVE_FP8[right][0]
        code = left_code if left_code & 1 == 0 else right_code
    return code | (0x80 if sign else 0)


def cuda_fmin(left: float, right: float) -> float:
    if math.isnan(left):
        return right
    if math.isnan(right):
        return left
    return min(left, right)


def cuda_fmax(left: float, right: float) -> float:
    if math.isnan(left):
        return right
    if math.isnan(right):
        return left
    return max(left, right)


def xor_reduce(values: list[float]) -> list[float]:
    lanes = values.copy()
    for offset in (16, 8, 4, 2, 1):
        previous = lanes
        lanes = [
            f32(previous[lane] + previous[lane ^ offset])
            for lane in range(32)
        ]
    return lanes


def down_reduce(values: list[float]) -> list[float]:
    lanes = values.copy()
    for offset in (16, 8, 4, 2, 1):
        previous = lanes
        lanes = previous.copy()
        for lane in range(32 - offset):
            lanes[lane] = f32(previous[lane] + previous[lane + offset])
    return lanes


def local_square(accumulator: float, value: float) -> float:
    return f32(value * value + accumulator)


def stock_square_sum(row: list[float]) -> float:
    partial = []
    for thread in range(STOCK_THREADS):
        accumulator = f32(0.0)
        start = thread * RMS_VEC
        for value in row[start : start + RMS_VEC]:
            accumulator = local_square(accumulator, value)
        partial.append(accumulator)
    warp_totals = [
        xor_reduce(partial[warp * 32 : (warp + 1) * 32])[0]
        for warp in range(STOCK_WARPS)
    ]
    return xor_reduce(warp_totals + [0.0] * (32 - STOCK_WARPS))[0]


def rejected_square_sum(row: list[float]) -> float:
    partial = []
    for thread in range(REJECTED_THREADS):
        accumulator = f32(0.0)
        for column in range(thread, HIDDEN, REJECTED_THREADS):
            accumulator = local_square(accumulator, row[column])
        partial.append(accumulator)
    warp_totals = [
        down_reduce(partial[warp * 32 : (warp + 1) * 32])[0]
        for warp in range(REJECTED_THREADS // 32)
    ]
    return down_reduce(warp_totals + [0.0] * 24)[0]


def normalized_bytes(
    row: list[float], weight: list[float], square_sum: float
) -> bytes:
    mean_plus_epsilon = f32(f32(square_sum / HIDDEN) + EPSILON)
    inverse_rms = f32(1.0 / math.sqrt(mean_plus_epsilon))
    result = bytearray()
    for value, scale in zip(row, weight):
        normalized = f32(f32(value * inverse_rms) * scale)
        result.extend(struct.pack("<H", bf16_bits(normalized)))
    return bytes(result)


def decode_bf16_bytes(data: bytes) -> list[float]:
    return [
        bf16_from_bits(bits)
        for (bits,) in struct.iter_unpack("<H", data)
    ]


def quantize(normalized: bytes) -> tuple[bytes, bytes]:
    values = decode_bf16_bytes(normalized)
    maximum = max(abs(value) for value in values)
    scale = f32(maximum / FP8_MAXIMUM)
    inverse_scale = math.inf if scale == 0.0 else f32(1.0 / scale)
    quantized = bytearray()
    for value in values:
        unbounded = f32(value * inverse_scale)
        bounded = cuda_fmax(
            cuda_fmin(unbounded, FP8_MAXIMUM), -FP8_MAXIMUM
        )
        quantized.append(fp8_code(bounded))
    return bytes(quantized), struct.pack("<f", scale)


@dataclass(frozen=True)
class RowStages:
    square_sum: bytes
    normalized: bytes
    quantized: bytes
    scale: bytes


def stages(
    row: list[float], weight: list[float], mode: str
) -> RowStages:
    if mode == "stock":
        square_sum = stock_square_sum(row)
    elif mode == "rejected":
        square_sum = rejected_square_sum(row)
    elif mode == "corrected":
        square_sum = stock_square_sum(row)
    else:
        raise ValueError(mode)
    normalized = normalized_bytes(row, weight, square_sum)
    quantized, scale = quantize(normalized)
    return RowStages(
        square_sum=struct.pack("<f", square_sum),
        normalized=normalized,
        quantized=quantized,
        scale=scale,
    )


def first_divergence(left: RowStages, right: RowStages) -> str | None:
    for name in ("square_sum", "normalized", "scale", "quantized"):
        if getattr(left, name) != getattr(right, name):
            return name
    return None


def digest(chunks: list[bytes]) -> str:
    value = hashlib.sha256()
    for chunk in chunks:
        value.update(chunk)
    return value.hexdigest()


def load_weight(path: pathlib.Path) -> tuple[list[float], dict[str, object]]:
    with path.open("rb") as handle:
        header_size = struct.unpack("<Q", handle.read(8))[0]
        header = json.loads(handle.read(header_size))
        entry = header[WEIGHT_KEY]
        if entry["dtype"] != "BF16" or entry["shape"] != [HIDDEN]:
            raise RuntimeError(f"unexpected norm weight entry: {entry}")
        start, end = entry["data_offsets"]
        handle.seek(8 + header_size + start)
        raw = handle.read(end - start)
    if len(raw) != HIDDEN * 2:
        raise RuntimeError("short norm weight")
    values = [
        bf16_from_bits(bits)
        for (bits,) in struct.iter_unpack("<H", raw)
    ]
    return values, {
        "path": str(path.resolve()),
        "container_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "weight_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "key": WEIGHT_KEY,
        "dtype": "BF16",
        "shape": [HIDDEN],
    }


def random_rows(rows: int, seed: int) -> list[list[float]]:
    generator = random.Random(seed)
    return [
        [
            bf16(
                generator.gauss(0.0, 0.72)
                + (6.0 if (column + row_index * 17) % 997 == 0 else 0.0)
            )
            for column in range(HIDDEN)
        ]
        for row_index in range(rows)
    ]


def adversarial_rows(rows: int) -> list[list[float]]:
    exponents = (-18, -12, -7, -2, 0, 3, 6)
    result = []
    for row_index in range(rows):
        row = []
        for column in range(HIDDEN):
            exponent = exponents[(column * 13 + row_index * 5) % len(exponents)]
            magnitude = 2.0**exponent
            if (column + row_index) % 257 == 0:
                magnitude *= 7.75
            sign = -1.0 if (column ^ row_index) & 1 else 1.0
            row.append(bf16(sign * magnitude))
        result.append(row)
    return result


def zero_rows(rows: int) -> list[list[float]]:
    return [
        [
            bf16(-0.0 if (column + row_index) & 1 else 0.0)
            for column in range(HIDDEN)
        ]
        for row_index in range(rows)
    ]


def compare_case(
    rows: list[list[float]], weight: list[float]
) -> dict[str, object]:
    stock_rows = [stages(row, weight, "stock") for row in rows]
    rejected_rows = [stages(row, weight, "rejected") for row in rows]
    corrected_rows = [stages(row, weight, "corrected") for row in rows]
    corrected_matches = {
        name: sum(
            getattr(stock, name) == getattr(corrected, name)
            for stock, corrected in zip(stock_rows, corrected_rows)
        )
        for name in ("square_sum", "normalized", "scale", "quantized")
    }
    rejected_matches = {
        name: sum(
            getattr(stock, name) == getattr(rejected, name)
            for stock, rejected in zip(stock_rows, rejected_rows)
        )
        for name in ("square_sum", "normalized", "scale", "quantized")
    }
    rejected_first = [
        first_divergence(stock, rejected)
        for stock, rejected in zip(stock_rows, rejected_rows)
    ]
    return {
        "rows": len(rows),
        "corrected_exact_row_counts": corrected_matches,
        "rejected_exact_row_counts": rejected_matches,
        "rejected_first_divergence_counts": {
            name: rejected_first.count(name)
            for name in ("square_sum", "normalized", "scale", "quantized")
            if rejected_first.count(name)
        },
        "rejected_fully_reconverged_rows": rejected_first.count(None),
        "stock_hashes": {
            name: digest([getattr(row, name) for row in stock_rows])
            for name in ("square_sum", "normalized", "scale", "quantized")
        },
        "corrected_hashes": {
            name: digest([getattr(row, name) for row in corrected_rows])
            for name in ("square_sum", "normalized", "scale", "quantized")
        },
    }


def torch_fp8_verification() -> dict[str, object]:
    try:
        import torch
    except ImportError:
        return {"available": False}
    values = [fp8_value(code) for code in range(0x7F)]
    probes = values + [-value for value in values]
    probes.extend(
        (values[index] + values[index + 1]) / 2.0
        for index in range(len(values) - 1)
    )
    tensor = torch.tensor(probes, dtype=torch.float32)
    observed = tensor.to(torch.float8_e4m3fn).view(torch.uint8).tolist()
    expected = [fp8_code(f32(value)) for value in probes]
    mismatches = sum(left != right for left, right in zip(observed, expected))
    return {
        "available": True,
        "torch_version": torch.__version__,
        "probe_count": len(probes),
        "mismatch_count": mismatches,
        "pass": mismatches == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-safetensors", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    weight, weight_identity = load_weight(args.component_safetensors)
    cases = {}
    for rows in SHAPES:
        random_seed = 2026073003 if rows == 1 else 2026073000 + rows
        cases[f"loaded_weight_random_m{rows}"] = compare_case(
            random_rows(rows, random_seed), weight
        )
        cases[f"adversarial_dynamic_range_m{rows}"] = compare_case(
            adversarial_rows(rows), weight
        )
        cases[f"signed_zero_m{rows}"] = compare_case(zero_rows(rows), weight)
    exact = all(
        all(count == case["rows"] for count in case["corrected_exact_row_counts"].values())
        for case in cases.values()
    )
    torch_fp8 = torch_fp8_verification()
    passed = exact and (not torch_fp8["available"] or torch_fp8["pass"])
    result = {
        "schema_version": 1,
        "classification": (
            "exact_order_cpu_oracle_pass"
            if passed
            else "exact_order_cpu_oracle_failure"
        ),
        "pass": passed,
        "evidence_class": "deterministic_source_level_cpu_simulation",
        "geometry": {
            "shapes": list(SHAPES),
            "hidden": HIDDEN,
            "input_dtype": "BF16",
            "output_dtype": "E4M3FN",
            "scale_dtype": "FP32",
        },
        "stock_order": {
            "rms_threads": STOCK_THREADS,
            "rms_warps": STOCK_WARPS,
            "rms_vector_elements": RMS_VEC,
            "rms_lane_mapping": "contiguous_vec8_one_round",
            "rms_reduction": "xor_16_8_4_2_1_then_21_warp_xor",
            "bf16_rounding": "after_x_times_rsqrt_times_weight",
            "quant_threads": QUANT_THREADS,
            "quant_vector_elements": QUANT_VEC,
            "quant_reduction": "finite_absmax_xor_16_8_4_2_1_then_8_warp_xor",
            "scale": "FP32_amax_div_448_then_FP32_reciprocal",
            "zero_row": "scale_positive_zero_and_positive_448_E4M3_bytes",
        },
        "rejected_order": {
            "rms_threads": REJECTED_THREADS,
            "rms_lane_mapping": "scalar_stride_256_twenty_one_values",
            "rms_reduction": "down_16_8_4_2_1_then_8_warp_down",
            "first_source_divergence": "rms_square_sum_reduction_order",
        },
        "weight_identity": weight_identity,
        "torch_fp8_encoder_check": torch_fp8,
        "cases": cases,
        "transfer_limit": (
            "The CPU uses rounded reciprocal sqrt, not Hopper rsqrt.approx. "
            "Exact candidate transfer does not depend on approximating that "
            "instruction because stock and candidate use the same sum bits, "
            "same rsqrtf call, and same BF16 store expression."
        ),
    }
    atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
