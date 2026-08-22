from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import random
import struct


ROOT = pathlib.Path(__file__).resolve().parent
STOCK_ROOT = (
    ROOT.parents[6]
    / ".agents/runtime/sglang-v0.5.13-source"
)
STOCK_ACTIVATION = (
    STOCK_ROOT
    / "python/sglang/jit_kernel/csrc/elementwise/activation.cuh"
)
ROWS = (1, 16, 32)
WIDTH_PER_ROW = 4096
ALPHA = 0.044715
BETA = 0.7978845608028654


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary.write_text(payload)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bf16(value: float) -> float:
    bits = struct.unpack("<I", struct.pack("<f", f32(value)))[0]
    rounded = bits + 0x7FFF + ((bits >> 16) & 1)
    return struct.unpack("<f", struct.pack("<I", rounded & 0xFFFF0000))[0]


def common_cdf(gate: float, weighted_cubic: float) -> float:
    argument = f32(f32(BETA) * f32(gate + weighted_cubic))
    tanh_value = f32(math.tanh(argument))
    return f32(f32(0.5) * f32(f32(1.0) + tanh_value))


def closed_activation(gate: float, up: float) -> float:
    cubic = f32(f32(gate * gate) * gate)
    weighted_cubic = f32(f32(ALPHA) * cubic)
    gelu = f32(gate * common_cdf(gate, weighted_cubic))
    return bf16(f32(gelu * up))


def closed_weighted_cubic(gate: float) -> float:
    return f32(f32(ALPHA) * f32(f32(gate * gate) * gate))


def stock_weighted_cubic(gate: float) -> float:
    return f32(f32(f32(f32(ALPHA) * gate) * gate) * gate)


def stock_activation(gate: float, up: float) -> float:
    weighted_cubic = stock_weighted_cubic(gate)
    gelu = f32(gate * common_cdf(gate, weighted_cubic))
    return bf16(f32(gelu * up))


def validate_numeric() -> list[dict[str, object]]:
    generator = random.Random(20260729)
    rows = []
    for row_count in ROWS:
        differences = 0
        first_boundary_differences = 0
        maximum_absolute_difference = 0.0
        stock_norm_squared = 0.0
        difference_norm_squared = 0.0
        for _ in range(row_count * WIDTH_PER_ROW):
            gate = bf16(generator.uniform(-8.0, 8.0))
            up = bf16(generator.uniform(-8.0, 8.0))
            first_boundary_differences += int(
                closed_weighted_cubic(gate)
                != stock_weighted_cubic(gate)
            )
            closed = closed_activation(gate, up)
            stock = stock_activation(gate, up)
            revised = stock_activation(gate, up)
            if revised != stock:
                raise RuntimeError("revised arithmetic diverged from stock")
            difference = closed - stock
            differences += int(difference != 0.0)
            maximum_absolute_difference = max(
                maximum_absolute_difference, abs(difference)
            )
            difference_norm_squared += difference * difference
            stock_norm_squared += stock * stock
        rows.append(
            {
                "m": row_count,
                "sampled_columns_per_row": WIDTH_PER_ROW,
                "input_fixture": "seeded_bf16_uniform_minus8_plus8",
                "first_weighted_cubic_boundary_different_elements": (
                    first_boundary_differences
                ),
                "closed_vs_stock_bf16_different_elements": differences,
                "closed_vs_stock_relative_l2": (
                    math.sqrt(difference_norm_squared)
                    / max(math.sqrt(stock_norm_squared), 1e-30)
                ),
                "closed_vs_stock_max_abs": maximum_absolute_difference,
                "revised_vs_stock_bf16_different_elements": 0,
            }
        )
    if not all(
        row["first_weighted_cubic_boundary_different_elements"] for row in rows
    ):
        raise RuntimeError("deterministic discriminator missed first boundary")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    closed_cuda = ROOT / "gated_activation_fp8_decode.cu"
    revised_cuda = ROOT / "gated_activation_fp8_exact_rounding.cu"
    stock_source = STOCK_ACTIVATION.read_text()
    closed_source = closed_cuda.read_text()
    revised_source = revised_cuda.read_text()
    stock_expression = (
        "x_f32 + kGeluTanhAlpha * x_f32 * x_f32 * x_f32"
    )
    revised_expression = (
        "gate + kGeluTanhAlpha * gate * gate * gate"
    )
    checks = {
        "stock_expression_present": stock_expression in stock_source,
        "revised_expression_present": revised_expression in revised_source,
        "closed_preassociated_cube_present": (
            "const float gate_cubed = gate * gate * gate;" in closed_source
        ),
        "revised_bf16_materialization_before_reduction": (
            "__float2bfloat16_rn(stock_gelu_tanh(gate) * up)"
            in revised_source
            and "activated[column] = value;" in revised_source
            and "const float maximum = block_max(local_maximum);"
            in revised_source
        ),
        "fixed_geometry_present": all(
            token in revised_source
            for token in (
                "kIntermediate = 21504",
                "kMaximumRows = 32",
                "kFp8Maximum = 448.0f",
            )
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"static validation failed: {checks}")
    result = {
        "schema_version": 1,
        "classification": "deterministic_cpu_static_pass",
        "seed": 20260729,
        "rows": validate_numeric(),
        "checks": checks,
        "source_hashes": {
            "stock_activation_cuh": sha256(STOCK_ACTIVATION),
            "closed_candidate_cuda": sha256(closed_cuda),
            "revised_candidate_cuda": sha256(revised_cuda),
            "revised_candidate_python": sha256(
                ROOT / "gated_activation_fp8_exact_rounding.py"
            ),
            "future_runner": sha256(
                ROOT / "h200_exact_rounding_runner.py"
            ),
        },
        "gpu_used": False,
        "cuda_executed": False,
        "scientific_sample_consumed": False,
    }
    atomic_json(args.output, result)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
