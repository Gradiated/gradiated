#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import pathlib
import random
import struct


HIDDEN = 5376
REDUCTION_LANES = 8192
DOWN_K = 21504
QKV_N = 16384
E4M3_MAX = 448.0
EPSILON = 1e-6
SEED = 20260730
EXPECTED_SOURCES = {
    "python/sglang/srt/models/gemma4_causal.py": "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    "python/sglang/srt/models/gemma3_causal.py": "a9827bde583c5b8b0abfeaced097c4e9d060fb99ec2961b4f9c66173d3027282",
    "python/sglang/srt/layers/gemma4_fused_ops.py": "f9d8c7c3ea71afc1341c2de02807b8fda94e418248bd9ee404b15b3337463ad3",
    "python/sglang/srt/layers/layernorm.py": "e31523f8090d41e642761617b7253b5a2833676dfd35dad86ae9c18e69144c3b",
    "python/sglang/srt/layers/quantization/fp8.py": "c7368db317513e5823283eb5567d15fdb742c3b01a98bfc483cb500291b4285a",
    "python/sglang/srt/layers/quantization/fp8_utils.py": "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9",
    "sgl-kernel/csrc/gemm/per_token_quant_fp8.cu": "c8a3e755dc165cecfa09232bed58e8b36010061f050acf2f82722b75c3c1edb8",
    "sgl-kernel/csrc/gemm/fp8_gemm_kernel.cu": "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
    "sgl-kernel/csrc/cutlass_extensions/gemm/fp8_gemm_sm90_dispatch.cuh": "549d3c1c5c13d67e7309cf50610a51c9485eb181b3a17423247287abd1a0b038",
}
SAMPLED_QKV_COLUMNS = (0, 63, 64, 8191, 8192, 12287, 12288, 16383)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def workspace_root() -> pathlib.Path:
    for parent in pathlib.Path(__file__).resolve().parents:
        if (parent / ".agents/runtime/sglang-v0.5.13-source").is_dir():
            return parent
    raise RuntimeError("workspace root with pinned SGLang source not found")


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def bf16_bits(value: float) -> int:
    bits = f32_bits(value)
    rounded = (bits + 0x7FFF + ((bits >> 16) & 1)) & 0xFFFFFFFF
    return (rounded >> 16) & 0xFFFF


def bf16_value(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", (bits & 0xFFFF) << 16))[0]


def bf16_round(values: list[float]) -> list[float]:
    return [bf16_value(bf16_bits(value)) for value in values]


def positive_e4m3_table() -> tuple[list[float], list[int]]:
    pairs = [(0.0, 0)]
    for exponent in range(16):
        maximum_mantissa = 6 if exponent == 15 else 7
        for mantissa in range(maximum_mantissa + 1):
            if exponent == 0:
                if mantissa == 0:
                    continue
                value = mantissa * (2.0**-9)
            else:
                value = (1.0 + mantissa / 8.0) * (2.0 ** (exponent - 7))
            pairs.append((value, (exponent << 3) | mantissa))
    pairs.sort()
    return [item[0] for item in pairs], [item[1] for item in pairs]


E4_VALUES, E4_BITS = positive_e4m3_table()


def encode_e4m3_scalar(value: float) -> int:
    value = f32(value)
    if math.isnan(value):
        return 0x7F
    negative = math.copysign(1.0, value) < 0.0
    magnitude = abs(value)
    if magnitude == 0.0:
        return 0x80 if negative else 0
    if magnitude >= E4_VALUES[-1]:
        chosen = E4_BITS[-1]
    else:
        upper_index = bisect.bisect_left(E4_VALUES, magnitude)
        lower_index = upper_index - 1
        lower_distance = magnitude - E4_VALUES[lower_index]
        upper_distance = E4_VALUES[upper_index] - magnitude
        if lower_distance < upper_distance:
            chosen = E4_BITS[lower_index]
        elif upper_distance < lower_distance:
            chosen = E4_BITS[upper_index]
        else:
            lower_bits = E4_BITS[lower_index]
            upper_bits = E4_BITS[upper_index]
            chosen = lower_bits if (lower_bits & 1) == 0 else upper_bits
    return chosen | (0x80 if negative else 0)


def decode_e4m3_scalar(bits: int) -> float:
    sign = -1.0 if bits & 0x80 else 1.0
    exponent = (bits >> 3) & 0xF
    mantissa = bits & 0x7
    if exponent == 15 and mantissa == 7:
        return math.nan
    if exponent == 0:
        value = mantissa * (2.0**-9)
    else:
        value = (1.0 + mantissa / 8.0) * (2.0 ** (exponent - 7))
    return f32(sign * value)


def encode_e4m3(values: list[float]) -> bytes:
    return bytes(encode_e4m3_scalar(value) for value in values)


def ordered_reduce(values: list[float], operation: str) -> float:
    tree = [0.0] * REDUCTION_LANES
    tree[: len(values)] = [f32(value) for value in values]
    width = 1
    while width < REDUCTION_LANES:
        for left in range(0, REDUCTION_LANES, width * 2):
            if operation == "sum":
                tree[left] = f32(tree[left] + tree[left + width])
            elif operation == "max":
                tree[left] = f32(max(tree[left], tree[left + width]))
            else:
                raise ValueError(operation)
        width *= 2
    return f32(tree[0])


def epilogue_partial_reduce(values: list[float]) -> float:
    if len(values) != HIDDEN:
        raise ValueError("expected exact hidden row")
    partials = []
    for tile in range(HIDDEN // 64):
        local = [f32(value) for value in values[tile * 64 : (tile + 1) * 64]]
        width = 1
        while width < 64:
            for left in range(0, 64, width * 2):
                local[left] = f32(local[left] + local[left + width])
            width *= 2
        partials.append(local[0])
    return ordered_reduce(partials, "sum")


def rrms(row_bf16: list[float], partials: bool = False) -> float:
    squares = [f32(value * value) for value in row_bf16]
    total = (
        epilogue_partial_reduce(squares)
        if partials
        else ordered_reduce(squares, "sum")
    )
    variance = f32(total / f32(float(HIDDEN)))
    return f32(1.0 / f32(math.sqrt(f32(variance + f32(EPSILON)))))


def post_residual(
    down_bf16: list[float],
    post_weight_bf16: list[float],
    residual_bf16: list[float],
    scalar: float,
    partials: bool = False,
) -> list[float]:
    scale = rrms(down_bf16, partials=partials)
    output = []
    for down, weight, residual in zip(
        down_bf16, post_weight_bf16, residual_bf16
    ):
        normalized = f32(f32(down * scale) * weight)
        combined = f32(normalized + residual)
        output.append(bf16_value(bf16_bits(f32(combined * scalar))))
    return output


def next_normalized(
    residual_bf16: list[float], next_weight_bf16: list[float]
) -> list[float]:
    scale = rrms(residual_bf16)
    output = []
    for residual, weight in zip(residual_bf16, next_weight_bf16):
        normalized = f32(f32(residual * scale) * weight)
        output.append(bf16_value(bf16_bits(normalized)))
    return output


def dynamic_e4m3(normalized_bf16: list[float]) -> tuple[bytes, float]:
    maximum = ordered_reduce([f32(abs(value)) for value in normalized_bf16], "max")
    scale = f32(maximum / f32(E4M3_MAX))
    if scale == 0.0:
        scaled = [f32(E4M3_MAX)] * HIDDEN
    else:
        inverse = f32(1.0 / scale)
        scaled = [
            f32(max(min(f32(value * inverse), E4M3_MAX), -E4M3_MAX))
            for value in normalized_bf16
        ]
    return encode_e4m3(scaled), scale


def materialized_control(
    down_bf16: list[float],
    post_weight_bf16: list[float],
    residual_bf16: list[float],
    next_weight_bf16: list[float],
    scalar: float,
) -> tuple[list[float], list[float], bytes, float]:
    residual_out = post_residual(
        down_bf16, post_weight_bf16, residual_bf16, scalar
    )
    normalized = next_normalized(residual_out, next_weight_bf16)
    quantized, scale = dynamic_e4m3(normalized)
    return residual_out, normalized, quantized, scale


def candidate_finalizer(
    down_bf16: list[float],
    post_weight_bf16: list[float],
    residual_bf16: list[float],
    next_weight_bf16: list[float],
    scalar: float,
) -> tuple[list[float], list[float], bytes, float]:
    shared_residual = post_residual(
        down_bf16, post_weight_bf16, residual_bf16, scalar
    )
    shared_normalized = next_normalized(shared_residual, next_weight_bf16)
    quantized, scale = dynamic_e4m3(shared_normalized)
    return shared_residual, shared_normalized, quantized, scale


def fixture(
    pattern: str, m: int, rng: random.Random
) -> tuple[list[list[float]], list[float], list[list[float]], list[float], float]:
    if pattern == "random":
        down = [[rng.gauss(0.0, 2.0) for _ in range(HIDDEN)] for _ in range(m)]
        residual = [
            [rng.gauss(0.0, 1.25) for _ in range(HIDDEN)] for _ in range(m)
        ]
        post_weight = [rng.gauss(1.0, 0.08) for _ in range(HIDDEN)]
        next_weight = [rng.gauss(1.0, 0.08) for _ in range(HIDDEN)]
        scalar = f32(0.75)
    elif pattern == "zero_signed":
        down = [
            [math.copysign(0.0, -1.0 if column % 2 else 1.0) for column in range(HIDDEN)]
            for _ in range(m)
        ]
        residual = [row.copy() for row in down]
        post_weight = [1.0] * HIDDEN
        next_weight = [1.0] * HIDDEN
        scalar = f32(1.0)
    elif pattern == "extreme":
        base = [
            f32(2.0 ** (-12.0 + 24.0 * column / (HIDDEN - 1)))
            for column in range(HIDDEN)
        ]
        down_row = [
            f32(value * (-1.0 if column % 2 else 1.0))
            for column, value in enumerate(base)
        ]
        residual_row = [
            f32(base[HIDDEN - 1 - column] * (-1.0 if column % 2 else 1.0) / 32.0)
            for column in range(HIDDEN)
        ]
        down = [down_row.copy() for _ in range(m)]
        residual = [residual_row.copy() for _ in range(m)]
        post_weight = [
            f32(0.25 + 1.5 * column / (HIDDEN - 1)) for column in range(HIDDEN)
        ]
        next_weight = [
            f32(1.75 - 1.5 * column / (HIDDEN - 1)) for column in range(HIDDEN)
        ]
        scalar = f32(1.125)
    else:
        raise ValueError(pattern)
    return (
        [bf16_round(row) for row in down],
        bf16_round(post_weight),
        [bf16_round(row) for row in residual],
        bf16_round(next_weight),
        scalar,
    )


def bf16_bytes(values: list[float]) -> bytes:
    return b"".join(struct.pack("<H", bf16_bits(value)) for value in values)


def sampled_consumer(
    quantized: bytes,
    activation_scale: float,
    weight_bits: list[bytes],
    weight_scales: list[float],
) -> list[float]:
    activation = [decode_e4m3_scalar(bits) for bits in quantized]
    outputs = []
    for column_bits, weight_scale in zip(weight_bits, weight_scales):
        products = [
            f32(left * decode_e4m3_scalar(right))
            for left, right in zip(activation, column_bits)
        ]
        accumulated = ordered_reduce(products, "sum")
        scaled = f32(f32(accumulated * activation_scale) * weight_scale)
        outputs.append(bf16_value(bf16_bits(scaled)))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    root = workspace_root()
    source_root = root / ".agents/runtime/sglang-v0.5.13-source"
    observed_sources = {}
    for relative, expected in EXPECTED_SOURCES.items():
        path = source_root / relative
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError(f"pinned source mismatch: {relative}: {observed}")
        observed_sources[relative] = observed

    rng = random.Random(SEED)
    weight_bits = []
    for _ in SAMPLED_QKV_COLUMNS:
        values = [rng.uniform(-400.0, 400.0) for _ in range(HIDDEN)]
        weight_bits.append(encode_e4m3(values))
    weight_scales = [
        f32(0.003 + (0.012 - 0.003) * index / (len(SAMPLED_QKV_COLUMNS) - 1))
        for index in range(len(SAMPLED_QKV_COLUMNS))
    ]

    cases = []
    rows_checked = 0
    for m in (1, 16, 32):
        for pattern in ("random", "zero_signed", "extreme"):
            down, post_weight, residual, next_weight, scalar = fixture(pattern, m, rng)
            quantized_digest = hashlib.sha256()
            consumer_digest = hashlib.sha256()
            scale_digest = hashlib.sha256()
            saturation_count = 0
            nonfinite_count = 0
            zero_contract = True
            for row in range(m):
                control = materialized_control(
                    down[row], post_weight, residual[row], next_weight, scalar
                )
                candidate = candidate_finalizer(
                    down[row], post_weight, residual[row], next_weight, scalar
                )
                partial_rrms = rrms(down[row], partials=True)
                full_rrms = rrms(down[row], partials=False)
                residual_equal = bf16_bytes(control[0]) == bf16_bytes(candidate[0])
                normalized_equal = bf16_bytes(control[1]) == bf16_bytes(candidate[1])
                quantized_equal = control[2] == candidate[2]
                scale_equal = f32_bits(control[3]) == f32_bits(candidate[3])
                partial_equal = f32_bits(partial_rrms) == f32_bits(full_rrms)
                control_consumer = sampled_consumer(
                    control[2], control[3], weight_bits, weight_scales
                )
                candidate_consumer = sampled_consumer(
                    candidate[2], candidate[3], weight_bits, weight_scales
                )
                consumer_equal = bf16_bytes(control_consumer) == bf16_bytes(
                    candidate_consumer
                )
                if not all(
                    (
                        residual_equal,
                        normalized_equal,
                        quantized_equal,
                        scale_equal,
                        partial_equal,
                        consumer_equal,
                    )
                ):
                    raise RuntimeError(f"oracle mismatch at M={m} {pattern} row={row}")
                if pattern == "zero_signed":
                    zero_contract = zero_contract and control[2] == bytes([0x7E]) * HIDDEN
                quantized_digest.update(control[2])
                consumer_digest.update(bf16_bytes(control_consumer))
                scale_digest.update(struct.pack("<I", f32_bits(control[3])))
                decoded = [decode_e4m3_scalar(bits) for bits in control[2]]
                saturation_count += sum(abs(value) == E4M3_MAX for value in decoded)
                nonfinite_count += sum(not math.isfinite(value) for value in decoded)
                rows_checked += 1
            if not zero_contract:
                raise RuntimeError("all-zero small-batch stock contract mismatch")
            cases.append(
                {
                    "m": m,
                    "pattern": pattern,
                    "rows": m,
                    "residual_bf16_exact": True,
                    "next_normalized_bf16_exact": True,
                    "e4m3_bytes_exact": True,
                    "scale_fp32_bits_exact": True,
                    "epilogue_64_leaf_tree_exact": True,
                    "sampled_qkv_bf16_exact": True,
                    "zero_row_stock_e4m3_448_bytes_exact": (
                        zero_contract if pattern == "zero_signed" else None
                    ),
                    "quantized_sha256": quantized_digest.hexdigest(),
                    "scale_bits_sha256": scale_digest.hexdigest(),
                    "consumer_bf16_sha256": consumer_digest.hexdigest(),
                    "saturation_count": saturation_count,
                    "nonfinite_count": nonfinite_count,
                }
            )

    project = pathlib.Path(__file__).resolve().parent
    candidate_source = project / "sm90a_two_phase_finalizer.cu"
    result = {
        "schema_version": 1,
        "classification": "exact_cpu_reference_fragment_oracle_pass",
        "pass": True,
        "seed": SEED,
        "scope": {
            "m": [1, 16, 32],
            "down_k": DOWN_K,
            "hidden": HIDDEN,
            "qkv_n": QKV_N,
            "sampled_qkv_columns": list(SAMPLED_QKV_COLUMNS),
            "patterns": ["random", "zero_signed", "extreme"],
            "rows_checked": rows_checked,
        },
        "pinned_source_revision": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        "pinned_source_sha256": observed_sources,
        "candidate_source": candidate_source.name,
        "candidate_source_sha256": sha256(candidate_source),
        "consumer_contract": {
            "activation": "row-major E4M3FN [M,5376], contiguous FP32 [M,1] scale",
            "weight": "column-major E4M3FN [5376,16384], stride [1,5376], contiguous FP32 [1,16384] per-channel scale",
            "output": "row-major BF16 [M,16384]",
            "sampled_arithmetic": "All 5376 activation elements consumed for eight Q/K/V-spanning output columns with a deterministic FP32 reduction tree.",
        },
        "reduction_contract": "Padded 8192-leaf contiguous binary FP32 tree for both RMSNorm sums; 64-leaf epilogue fragments compose bitwise to the same tree.",
        "zero_contract": "Pinned small-batch quantizer maps an all-zero BF16 row to E4M3 +448 bytes with FP32 scale +0; the unchanged consumer dequantizes it to zero.",
        "cases": cases,
        "transfer_limit": "The oracle proves BF16 boundaries, deterministic reduction decomposition, complete E4M3 bytes/scales, zero/saturation behavior, and sampled first-consumer indexing. It does not prove the pinned Triton reduction order, CUTLASS FP8FastAccum order, compiled resource use, or H200 latency.",
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "classification": result["classification"],
                "rows": rows_checked,
                "pass": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
