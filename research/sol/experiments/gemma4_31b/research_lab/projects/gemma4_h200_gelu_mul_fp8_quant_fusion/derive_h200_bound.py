#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
REPOSITORY = PROJECT.parents[6]
PINNED_SOURCE = REPOSITORY / ".agents/runtime/sglang-v0.5.13-source"
FIXED_DENOMINATOR_S = 0.625149101968745
PROFILE_ELIGIBLE_BOUND_S = 0.400125843
PROFILE_REQUESTS = 32
H200_SMS = 132
H200_HBM_BYTES_PER_S = 4.8e12
M = 32
K = 21504
GATE_UP = 2 * K


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path: pathlib.Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    binding = json.loads(
        (PROJECT / "evidence/PINNED_SOURCE_BINDING.json").read_text()
    )
    observed = {}
    for relative, expected in binding["source_files"].items():
        path = PINNED_SOURCE / relative
        observed[relative] = digest(path)
        if observed[relative] != expected:
            raise RuntimeError(
                f"pinned source mismatch: {relative}: "
                f"{observed[relative]} != {expected}"
            )

    prior = json.loads(
        (PROJECT / "evidence/PRIOR_H200_COMPONENT_SNAPSHOT.json").read_text()
    )
    prior_m32 = next(row for row in prior["rows"] if row["tokens"] == 32)
    prior_m2048 = next(row for row in prior["rows"] if row["tokens"] == 2048)

    stock_input_read = M * GATE_UP * 2
    stock_activation_write = M * K * 2
    stock_quant_reads = 2 * M * K * 2
    stock_quantized_write = M * K
    scale_write = M * 4
    stock_bytes = (
        stock_input_read
        + stock_activation_write
        + stock_quant_reads
        + stock_quantized_write
        + scale_write
    )
    candidate_bytes = stock_input_read + stock_quantized_write + scale_write
    removed_bytes = stock_bytes - candidate_bytes
    compulsory_interface_removed_bytes = (
        stock_activation_write + M * K * 2
    )

    candidate_dynamic_shared = K * 2
    candidate_static_shared = (256 // 32) * 4 + 4
    candidate_shared = candidate_dynamic_shared + candidate_static_shared
    h200_shared_per_sm = 228 * 1024
    active_blocks_by_shared = h200_shared_per_sm // candidate_shared
    absolute_upper_s_per_request = (
        PROFILE_ELIGIBLE_BOUND_S / PROFILE_REQUESTS
    )

    payload = {
        "schema_version": 1,
        "classification": "analytical_h200_bound_with_diagnostic_measured_prior",
        "source_identity_pass": True,
        "source_hashes": observed,
        "geometry": {
            "phase": "decode",
            "tokens": M,
            "gate_up_shape": [M, GATE_UP],
            "activation_shape": [M, K],
            "down_gemm_mnk": [M, 5376, K],
            "gate_up_dtype": "bfloat16",
            "activation_dtype": "bfloat16",
            "quantized_dtype": "float8_e4m3fn",
            "scale_dtype": "float32",
        },
        "h200": {
            "evidence_class": "shared_inventory_vendor_reported",
            "programming_target": "sm_90",
            "sms": H200_SMS,
            "hbm_bandwidth_gb_s": 4800,
            "shared_memory_per_sm_kib": 228,
            "maximum_shared_memory_per_block_kib": 227,
            "register_file_per_sm_kib": 256,
            "maximum_warps_per_sm": 64,
        },
        "bytes": {
            "stock": {
                "gate_up_read": stock_input_read,
                "activation_write": stock_activation_write,
                "quantizer_two_pass_activation_read": stock_quant_reads,
                "quantized_write": stock_quantized_write,
                "scale_write": scale_write,
                "total": stock_bytes,
            },
            "candidate": {
                "gate_up_read": stock_input_read,
                "quantized_write": stock_quantized_write,
                "scale_write": scale_write,
                "total": candidate_bytes,
            },
            "removed": removed_bytes,
            "removed_mib": removed_bytes / (1024 * 1024),
            "removed_scope": "logical global-memory traffic: one BF16 write plus both stock quantizer read passes",
            "compulsory_interface_removed": compulsory_interface_removed_bytes,
            "compulsory_interface_removed_mib": (
                compulsory_interface_removed_bytes / (1024 * 1024)
            ),
            "compulsory_interface_scope": "one BF16 producer write plus at least one consumer read; the second quantizer read may hit cache",
            "reduction_fraction": removed_bytes / stock_bytes,
            "stock_hbm_floor_us": stock_bytes / H200_HBM_BYTES_PER_S * 1e6,
            "candidate_hbm_floor_us": (
                candidate_bytes / H200_HBM_BYTES_PER_S * 1e6
            ),
            "hbm_floor_savings_us": (
                removed_bytes / H200_HBM_BYTES_PER_S * 1e6
            ),
            "compulsory_interface_hbm_floor_savings_us": (
                compulsory_interface_removed_bytes
                / H200_HBM_BYTES_PER_S
                * 1e6
            ),
            "scope": "producer boundary only; logical global traffic is exact from source, while realized HBM/DRAM traffic depends on cache and requires counters",
        },
        "launch_and_waves": {
            "stock": [
                {
                    "symbol": "gelu_tanh_and_mul",
                    "launches": 1,
                    "blocks": M,
                    "threads_per_block": 1024,
                    "grid_waves": M / H200_SMS,
                },
                {
                    "symbol": "per_token_quant_fp8_small_batch_kernel",
                    "launches": 1,
                    "blocks": M,
                    "threads_per_block": 256,
                    "grid_waves": M / H200_SMS,
                },
            ],
            "candidate": {
                "symbol": "fused_gelu_mul_dynamic_fp8_kernel",
                "launches": 1,
                "blocks": M,
                "threads_per_block": 256,
                "grid_waves": M / H200_SMS,
            },
            "launches_removed": 1,
            "interpretation": "All c32 grids are one partial wave; launch elimination and per-block work, not wave count alone, decide latency.",
        },
        "resources": {
            "candidate_dynamic_shared_bytes_per_block": candidate_dynamic_shared,
            "candidate_static_shared_bytes_per_block": candidate_static_shared,
            "candidate_total_shared_bytes_per_block": candidate_shared,
            "shared_memory_legal": candidate_shared <= 227 * 1024,
            "active_blocks_per_sm_upper_bound_from_shared": active_blocks_by_shared,
            "registers_per_thread": "unknown_until_sm90_compile",
            "register_falsifier": "Compile with ptxas verbose; reject spills or a launch resource error. At c32 the grid admits at most one block on only 32 of 132 SMs, so additional residency is not a target.",
        },
        "diagnostic_prior_h200": {
            "scope": prior["scope_warning"],
            "m32": {
                "stock_boundary_ms": prior_m32["control_boundary_ms"],
                "invalid_candidate_boundary_ms": prior_m32[
                    "invalid_candidate_boundary_ms"
                ],
                "descriptive_boundary_delta_us": (
                    prior_m32["control_boundary_ms"]
                    - prior_m32["invalid_candidate_boundary_ms"]
                )
                * 1000,
                "stock_component_ms": prior_m32["control_component_ms"],
                "invalid_candidate_component_ms": prior_m32[
                    "invalid_candidate_component_ms"
                ],
                "descriptive_component_delta_us": (
                    prior_m32["control_component_ms"]
                    - prior_m32["invalid_candidate_component_ms"]
                )
                * 1000,
                "numerical_pass": False,
            },
            "m2048": {
                "stock_boundary_ms": prior_m2048["control_boundary_ms"],
                "invalid_candidate_boundary_ms": prior_m2048[
                    "invalid_candidate_boundary_ms"
                ],
                "regression_fraction": (
                    prior_m2048["invalid_candidate_boundary_ms"]
                    / prior_m2048["control_boundary_ms"]
                    - 1
                ),
                "decision": "stock fallback above M=128",
            },
        },
        "whole_request": {
            "fixed_denominator_s_per_request": FIXED_DENOMINATOR_S,
            "campaign_target_s_per_request": 0.500119281574996,
            "profile_all_eligible_activation_plus_quant_s_per_batch": (
                PROFILE_ELIGIBLE_BOUND_S
            ),
            "profile_requests": PROFILE_REQUESTS,
            "absolute_upper_bound_s_per_request": absolute_upper_s_per_request,
            "absolute_upper_bound_fraction_of_fixed_denominator": (
                absolute_upper_s_per_request / FIXED_DENOMINATOR_S
            ),
            "bound_scope": "Impossible best case that deletes all measured GeluAndMul plus down-quant time at every profile shape; the M<=128 candidate realizes only a subset.",
            "campaign_gap_closed_at_absolute_upper_bound_fraction": (
                absolute_upper_s_per_request
                / (FIXED_DENOMINATOR_S - 0.500119281574996)
            ),
            "endpoint_claim": False,
        },
        "predictions": {
            "c32_logical_global_bytes": "decrease by 4,128,768 per layer call",
            "c32_compulsory_interface_bytes": "decrease by 2,752,512 per layer call",
            "c32_dram_bytes": "decrease expected between the compulsory-interface and logical-global bounds; exact magnitude requires counters",
            "c32_launches": "decrease from two to one before unchanged GEMM",
            "dram_read_bytes": "decrease; exact magnitude requires counters",
            "registers_and_spills": "unknown until compile",
            "shared_memory": "increase to 43,044 bytes per candidate block",
            "large_m": "unchanged because M>128 dispatches stock",
        },
        "falsifier": {
            "correctness": "Any exact-consumer BF16 mismatch at M=1,7,31,32,33,118.",
            "mechanism": "No decrease in producer DRAM bytes or launch count.",
            "performance": "Corrected producer-plus-down-consumer median is not lower than stock at every admitted M.",
            "transfer": "A component pass does not establish endpoint gain; run a matched fixed-denominator endpoint.",
        },
        "candidate": {
            "source": "candidate/fused_gelu_mul_dynamic_fp8_sm90.cu",
            "source_sha256": digest(
                PROJECT / "candidate/fused_gelu_mul_dynamic_fp8_sm90.cu"
            ),
            "runtime_integration": "candidate/apply_runtime_integration.py",
            "runtime_integration_sha256": digest(
                PROJECT / "candidate/apply_runtime_integration.py"
            ),
            "gpu_contract": "exact_consumer_gpu_contract.py",
            "gpu_contract_sha256": digest(
                PROJECT / "exact_consumer_gpu_contract.py"
            ),
        },
    }
    if not payload["resources"]["shared_memory_legal"]:
        raise RuntimeError("candidate exceeds SM90 shared-memory limit")
    if removed_bytes != 4_128_768:
        raise RuntimeError(f"unexpected byte bound: {removed_bytes}")
    if compulsory_interface_removed_bytes != 2_752_512:
        raise RuntimeError(
            "unexpected compulsory interface byte bound: "
            f"{compulsory_interface_removed_bytes}"
        )
    if math.ceil(M / H200_SMS) != 1:
        raise RuntimeError("c32 must be one partial wave")
    atomic_json(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
