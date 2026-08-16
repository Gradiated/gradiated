#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pathlib


HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 2 * INTERMEDIATE
LAYERS = 60
H200_HBM_BYTES_PER_SECOND = 4.8e12
H200_FP8_FLOPS_PER_SECOND = 1.979e15
H200_L2_BYTES = 50 * 1024 * 1024
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745
CONCURRENCY = 32
TARGET_VERIFICATION_STEPS = 15
M384_STOCK_GATE_US = 230.640
M384_STOCK_DOWN_US = 149.616
M32_STOCK_FULL_MLP_US = 125.48799812793732


def projection_flops(m: int, k: int, n: int) -> int:
    return 2 * m * k * n


def logical_mlp_bytes(m: int, weight_passes: int) -> dict[str, int]:
    weight = HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN
    weight_scale = 4 * (GATE_UP + HIDDEN)
    activation_and_output = (
        m * HIDDEN * 2  # initial BF16 read by quantizer
        + 2 * m * HIDDEN  # quantized input write + GEMM read
        + 2 * m * 4  # row scale write + read
        + 2 * m * GATE_UP * 2  # gate/up BF16 write + activation read
        + 2 * m * INTERMEDIATE * 2  # activation write + quantizer read
        + 2 * m * INTERMEDIATE  # down FP8 input write + GEMM read
        + 2 * m * 4  # row scale write + read
        + m * HIDDEN * 2  # final BF16 write
    )
    return {
        "weight_fp8": weight * weight_passes,
        "weight_scale_fp32": weight_scale * weight_passes,
        "activation_quant_intermediate_output": activation_and_output,
        "total": weight * weight_passes
        + weight_scale * weight_passes
        + activation_and_output,
    }


def tiles(m: int, tile_m: int, tile_n: int, cluster_m: int) -> dict[str, int]:
    gate_n_tiles = math.ceil(GATE_UP / tile_n)
    down_n_tiles = math.ceil(HIDDEN / tile_n)
    m_tiles = math.ceil(m / tile_m)
    scheduled_m_tiles = math.ceil(m_tiles / cluster_m) * cluster_m
    return {
        "m_tiles": m_tiles,
        "scheduled_m_tiles": scheduled_m_tiles,
        "padded_m_tiles": scheduled_m_tiles - m_tiles,
        "gate_up_cta_tiles": scheduled_m_tiles * gate_n_tiles,
        "down_cta_tiles": scheduled_m_tiles * down_n_tiles,
        "total_cta_tiles": scheduled_m_tiles * (gate_n_tiles + down_n_tiles),
    }


def model(m: int) -> dict[str, object]:
    flops = projection_flops(m, HIDDEN, GATE_UP) + projection_flops(
        m, INTERMEDIATE, HIDDEN
    )
    if m == 32:
        weight_passes = 1
        stock_tiles = tiles(m, 32, 64, 1)
        candidate_tiles = tiles(m, 32, 128, 1)
    else:
        weight_passes = 2
        stock_tiles = tiles(m, 128, 128, 2)
        candidate_tiles = tiles(m, 128, 256, 2)
    byte_model = logical_mlp_bytes(m, weight_passes)
    return {
        "rows": m,
        "flops_gate_up_plus_down": flops,
        "weight_passes_from_cluster_geometry": weight_passes,
        "bytes": byte_model,
        "arithmetic_intensity_flop_per_byte": flops / byte_model["total"],
        "h200_fp8_ridge_flop_per_byte": (
            H200_FP8_FLOPS_PER_SECOND / H200_HBM_BYTES_PER_SECOND
        ),
        "hbm_roofline_lower_bound_us": (
            byte_model["total"] / H200_HBM_BYTES_PER_SECOND * 1e6
        ),
        "stock_tiles": stock_tiles,
        "candidate_tiles": candidate_tiles,
        "cta_tile_reduction_fraction": (
            1
            - candidate_tiles["total_cta_tiles"] / stock_tiles["total_cta_tiles"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    m32 = model(32)
    m384 = model(384)
    measured_projection_us = M384_STOCK_GATE_US + M384_STOCK_DOWN_US
    qualified_batch_seconds = QUALIFIED_SECONDS_PER_REQUEST * CONCURRENCY
    conservative_projection_seconds = (
        measured_projection_us
        * 1e-6
        * LAYERS
        * TARGET_VERIFICATION_STEPS
    )
    value = {
        "schema_version": 1,
        "evidence_labels": {
            "geometry_and_byte_model": "analytical",
            "accelerator_limits": "vendor-reported inventory",
            "stock_component_times": "measured on retained H200 by exact-shape sibling projects",
            "whole_request_share": "derived",
        },
        "constants": {
            "hidden": HIDDEN,
            "intermediate": INTERMEDIATE,
            "gate_up_output": GATE_UP,
            "layers": LAYERS,
            "h200_hbm_bytes_per_second": H200_HBM_BYTES_PER_SECOND,
            "h200_fp8_flops_per_second": H200_FP8_FLOPS_PER_SECOND,
            "h200_l2_bytes": H200_L2_BYTES,
            "qualified_seconds_per_request": QUALIFIED_SECONDS_PER_REQUEST,
            "concurrency": CONCURRENCY,
            "target_verification_steps": TARGET_VERIFICATION_STEPS,
        },
        "m32": m32,
        "m384": m384,
        "measured_stock": {
            "m32_full_mlp_us": M32_STOCK_FULL_MLP_US,
            "m32_effective_modeled_bandwidth_bytes_per_second": (
                m32["bytes"]["total"] / (M32_STOCK_FULL_MLP_US * 1e-6)
            ),
            "m384_gate_up_us": M384_STOCK_GATE_US,
            "m384_down_us": M384_STOCK_DOWN_US,
            "m384_gate_plus_down_us": measured_projection_us,
        },
        "conservative_current_request_share": {
            "scope": (
                "only measured M384 gate/up+down projections; excludes positive "
                "M32 decode and MLP activation/quantization costs"
            ),
            "qualified_batch_seconds": qualified_batch_seconds,
            "projection_seconds_for_60_layers_15_steps": (
                conservative_projection_seconds
            ),
            "lower_bound_fraction": (
                conservative_projection_seconds / qualified_batch_seconds
            ),
            "request_gain_per_component_saved_microsecond": (
                LAYERS
                * TARGET_VERIFICATION_STEPS
                * 1e-6
                / qualified_batch_seconds
            ),
        },
        "minimum_h200_result": {
            "rule": (
                "bitwise equality at every consumer boundary and a strictly "
                "positive paired-bootstrap 95% lower bound on full-MLP saved "
                "time at both M32 and M384"
            ),
            "fixed_percentage_gate": None,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
