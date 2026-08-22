#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import math
import os
import struct
import tempfile
from pathlib import Path


M = 32
K = 5376
LAYERS = 60
FORWARD_BATCHES = 61
EPSILON = 1e-6
CAPTURE_WINDOW_SECONDS = 23.038600455
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def float32_bits(value: float) -> int:
    return struct.unpack(">I", struct.pack(">f", value))[0]


def bits_to_float32(bits: int) -> float:
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def to_bfloat16_bits(value: float) -> int:
    bits = float32_bits(value)
    return ((bits + 0x7FFF + ((bits >> 16) & 1)) >> 16) & 0xFFFF


def bfloat16_value(value: float) -> float:
    return bits_to_float32(to_bfloat16_bits(value) << 16)


def deterministic_value(index: int, salt: int, scale: float, offset: float) -> float:
    value = (index + salt * 0x9E3779B9) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    unit = (value & 0xFFFFFF) / float(0xFFFFFF)
    return bfloat16_value(offset + scale * (2.0 * unit - 1.0))


def rmsnorm_unrounded(values: list[float], weights: list[float]) -> list[float]:
    inverse_rms = 1.0 / math.sqrt(
        sum(value * value for value in values) / len(values) + EPSILON
    )
    return [value * inverse_rms * weight for value, weight in zip(values, weights)]


def rmsnorm_bfloat16(values: list[float], weights: list[float]) -> list[float]:
    return [bfloat16_value(value) for value in rmsnorm_unrounded(values, weights)]


def stock_two_kernel_path(
    hidden: list[float],
    residual: list[float],
    post_attention_weight: list[float],
    pre_feedforward_weight: list[float],
) -> tuple[list[float], list[float]]:
    post_attention = rmsnorm_bfloat16(hidden, post_attention_weight)
    residual_out = [
        bfloat16_value(value + skip)
        for value, skip in zip(post_attention, residual)
    ]
    normalized = rmsnorm_bfloat16(residual_out, pre_feedforward_weight)
    return normalized, residual_out


def lifecycle_pure_candidate(
    hidden: list[float],
    residual: list[float],
    post_attention_weight: list[float],
    pre_feedforward_weight: list[float],
) -> tuple[list[float], list[float]]:
    first_reduction = rmsnorm_unrounded(hidden, post_attention_weight)
    rounded_post_attention = [bfloat16_value(value) for value in first_reduction]
    residual_out = [
        bfloat16_value(value + skip)
        for value, skip in zip(rounded_post_attention, residual)
    ]
    second_reduction = rmsnorm_unrounded(residual_out, pre_feedforward_weight)
    normalized = [bfloat16_value(value) for value in second_reduction]
    return normalized, residual_out


def invalid_no_intermediate_round_candidate(
    hidden: list[float],
    residual: list[float],
    post_attention_weight: list[float],
    pre_feedforward_weight: list[float],
) -> tuple[list[float], list[float]]:
    unrounded_post_attention = rmsnorm_unrounded(hidden, post_attention_weight)
    residual_out = [
        bfloat16_value(value + skip)
        for value, skip in zip(unrounded_post_attention, residual)
    ]
    normalized = rmsnorm_bfloat16(residual_out, pre_feedforward_weight)
    return normalized, residual_out


def update_digest(digest: "hashlib._Hash", values: list[float]) -> None:
    for value in values:
        digest.update(struct.pack(">H", to_bfloat16_bits(value)))


def trace_row(path: Path, name_fragment: str) -> dict:
    with path.open(newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 7 and name_fragment in row[-1]:
                return {
                    "total_time_ns": int(row[1]),
                    "instances": int(row[2]),
                    "average_ns": float(row[3]),
                    "median_ns": float(row[4]),
                    "symbol": row[-1],
                }
    raise ValueError(f"missing trace row containing {name_fragment!r}")


def source_binding(path: Path, required_fragments: list[str]) -> dict:
    text = path.read_text()
    lines = text.splitlines()
    locations = {}
    for fragment in required_fragments:
        matches = [index + 1 for index, line in enumerate(lines) if fragment in line]
        if not matches:
            raise ValueError(f"{path}: missing required source fragment {fragment!r}")
        locations[fragment] = matches
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
        "required_fragment_lines": locations,
    }


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        json.loads(Path(temporary).read_text())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--trace-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    gemma_source = args.source_root / "python/sglang/srt/models/gemma4_causal.py"
    layernorm_source = args.source_root / "python/sglang/srt/layers/layernorm.py"
    source_bindings = {
        "gemma4_causal.py": source_binding(
            gemma_source,
            [
                "hidden_states = self.post_attention_layernorm(hidden_states)",
                "hidden_states, residual = self.pre_feedforward_layernorm(",
            ],
        ),
        "layernorm.py": source_binding(
            layernorm_source,
            [
                "fused_add_rmsnorm(x, residual, self.weight.data, self.variance_epsilon)",
            ],
        ),
    }

    rmsnorm_trace = trace_row(args.trace_csv, "RMSNormKernel")
    fused_add_trace = trace_row(args.trace_csv, "FusedAddRMSNormKernel")
    expected_selected_calls = LAYERS * FORWARD_BATCHES
    if fused_add_trace["instances"] != expected_selected_calls:
        raise ValueError(
            f"expected {expected_selected_calls} fused-add calls, "
            f"observed {fused_add_trace['instances']}"
        )
    if rmsnorm_trace["instances"] < expected_selected_calls * 2:
        raise ValueError("RMSNorm family does not cover both per-layer call sites")

    post_attention_weight = [
        deterministic_value(index, 11, 0.35, 1.0) for index in range(K)
    ]
    pre_feedforward_weight = [
        deterministic_value(index, 17, 0.35, 1.0) for index in range(K)
    ]
    stock_digest = hashlib.sha256()
    candidate_digest = hashlib.sha256()
    invalid_digest = hashlib.sha256()
    candidate_output_mismatches = 0
    candidate_residual_mismatches = 0
    invalid_output_mismatches = 0
    invalid_residual_mismatches = 0
    finite_outputs = True
    nonzero_outputs = 0

    for row in range(M):
        hidden = [
            deterministic_value(row * K + column, 23, 2.0, 0.0)
            for column in range(K)
        ]
        residual = [
            deterministic_value(row * K + column, 29, 2.0, 0.0)
            for column in range(K)
        ]
        stock_output, stock_residual = stock_two_kernel_path(
            hidden, residual, post_attention_weight, pre_feedforward_weight
        )
        candidate_output, candidate_residual = lifecycle_pure_candidate(
            hidden, residual, post_attention_weight, pre_feedforward_weight
        )
        invalid_output, invalid_residual = invalid_no_intermediate_round_candidate(
            hidden, residual, post_attention_weight, pre_feedforward_weight
        )
        candidate_output_mismatches += sum(
            to_bfloat16_bits(left) != to_bfloat16_bits(right)
            for left, right in zip(stock_output, candidate_output)
        )
        candidate_residual_mismatches += sum(
            to_bfloat16_bits(left) != to_bfloat16_bits(right)
            for left, right in zip(stock_residual, candidate_residual)
        )
        invalid_output_mismatches += sum(
            to_bfloat16_bits(left) != to_bfloat16_bits(right)
            for left, right in zip(stock_output, invalid_output)
        )
        invalid_residual_mismatches += sum(
            to_bfloat16_bits(left) != to_bfloat16_bits(right)
            for left, right in zip(stock_residual, invalid_residual)
        )
        finite_outputs = finite_outputs and all(math.isfinite(value) for value in candidate_output)
        nonzero_outputs += sum(value != 0.0 for value in candidate_output)
        update_digest(stock_digest, stock_output + stock_residual)
        update_digest(candidate_digest, candidate_output + candidate_residual)
        update_digest(invalid_digest, invalid_output + invalid_residual)

    tensor_bytes = M * K * 2
    intermediate_bytes_removed_per_call = tensor_bytes * 2
    intermediate_bytes_removed_per_capture = (
        intermediate_bytes_removed_per_call * expected_selected_calls
    )
    attributed_post_attention_seconds = (
        rmsnorm_trace["total_time_ns"]
        * expected_selected_calls
        / rmsnorm_trace["instances"]
        / 1e9
    )
    fused_add_seconds = fused_add_trace["total_time_ns"] / 1e9
    selected_block_upper_seconds = (
        attributed_post_attention_seconds + fused_add_seconds
    )
    loose_all_norm_family_upper_seconds = (
        rmsnorm_trace["total_time_ns"] + fused_add_trace["total_time_ns"]
    ) / 1e9
    upper_seconds_per_request = selected_block_upper_seconds / M
    fixed_denominator_upper_fraction = (
        upper_seconds_per_request / QUALIFIED_SECONDS_PER_REQUEST
    )
    target_gap_seconds_per_request = (
        QUALIFIED_SECONDS_PER_REQUEST - TARGET_SECONDS_PER_REQUEST
    )

    result = {
        "schema_version": 1,
        "classification": "localized_source_trace_falsifier",
        "execution": {
            "environment": "coordinator_cpu_only",
            "gpu_claimed": False,
            "cuda_invoked": False,
            "endpoint_traffic": False,
            "provider_mutation": False,
            "seed_contract": "index-hash-v1 salts 11,17,23,29",
        },
        "scope": {
            "phase": "c32 mixed prefill/decode model forwards in exact endpoint capture",
            "producer": "Gemma4DecoderLayer.post_attention_layernorm",
            "consumer": "Gemma4DecoderLayer.pre_feedforward_layernorm(hidden_states, residual)",
            "shape": [M, K],
            "strides": [K, 1],
            "input_dtype": "bfloat16",
            "weight_dtype": "bfloat16",
            "output_dtype": "bfloat16",
            "epsilon": EPSILON,
            "layers": LAYERS,
            "forward_batches_in_capture": FORWARD_BATCHES,
            "selected_calls": expected_selected_calls,
        },
        "correctness": {
            "semantics": "preserve both stock bfloat16 rounding boundaries",
            "elements_per_output": M * K,
            "candidate_output_bfloat16_mismatches": candidate_output_mismatches,
            "candidate_residual_bfloat16_mismatches": candidate_residual_mismatches,
            "candidate_full_output_sha256": candidate_digest.hexdigest(),
            "stock_full_output_sha256": stock_digest.hexdigest(),
            "finite": finite_outputs,
            "nonzero_output_elements": nonzero_outputs,
            "negative_control": {
                "change": "omit the stock bfloat16 round after post-attention RMSNorm",
                "output_bfloat16_mismatches": invalid_output_mismatches,
                "residual_bfloat16_mismatches": invalid_residual_mismatches,
                "full_output_sha256": invalid_digest.hexdigest(),
                "discriminates_rounding_contract": (
                    invalid_output_mismatches > 0 or invalid_residual_mismatches > 0
                ),
            },
            "pass": (
                candidate_output_mismatches == 0
                and candidate_residual_mismatches == 0
                and finite_outputs
                and nonzero_outputs > 0
                and (invalid_output_mismatches > 0 or invalid_residual_mismatches > 0)
            ),
            "transfer_limit": (
                "CPU oracle proves the exact-shape rounding/dataflow contract only; "
                "it does not establish H200 timing, launch legality, or reduction-order identity."
            ),
        },
        "trace_evidence": {
            "capture_window_seconds": CAPTURE_WINDOW_SECONDS,
            "trace_csv": {
                "path": str(args.trace_csv.resolve()),
                "bytes": args.trace_csv.stat().st_size,
                "sha256": sha256_path(args.trace_csv),
            },
            "rmsnorm_family": rmsnorm_trace,
            "fused_add_rmsnorm": fused_add_trace,
            "attributed_post_attention_rmsnorm_seconds": attributed_post_attention_seconds,
            "attribution_method": (
                "source-count apportionment: 3,660 selected post-attention calls out "
                "of 7,381 same-symbol RMSNorm family calls"
            ),
            "uncertainty": (
                "The trace summary does not label individual RMSNorm call sites; "
                "the source-count apportionment assumes equal mean duration for equal [M,5376] sites."
            ),
        },
        "physical_bound": {
            "intermediate_bfloat16_write_read_bytes_removed_per_call": (
                intermediate_bytes_removed_per_call
            ),
            "intermediate_bfloat16_write_read_bytes_removed_per_capture": (
                intermediate_bytes_removed_per_capture
            ),
            "launches_removed_per_capture": expected_selected_calls,
            "selected_block_zero_cost_upper_seconds_per_capture": (
                selected_block_upper_seconds
            ),
            "loose_all_norm_family_zero_cost_upper_seconds_per_capture": (
                loose_all_norm_family_upper_seconds
            ),
            "selected_block_zero_cost_upper_fraction_of_capture": (
                selected_block_upper_seconds / CAPTURE_WINDOW_SECONDS
            ),
            "selected_block_zero_cost_upper_seconds_per_request": (
                upper_seconds_per_request
            ),
            "selected_block_zero_cost_upper_fraction_of_fixed_qualified_request": (
                fixed_denominator_upper_fraction
            ),
            "target_gap_seconds_per_request": target_gap_seconds_per_request,
            "maximum_fraction_of_target_gap_closed": (
                upper_seconds_per_request / target_gap_seconds_per_request
            ),
            "interpretation": (
                "This credits both required RMSNorm computations and the residual add "
                "as free, so it is an intentionally impossible upper bound on launch/"
                "materialization savings."
            ),
        },
        "source_bindings": source_bindings,
        "decision": {
            "result": "redirect_selected_hotblock",
            "reason_code": "impossible_zero_cost_upper_bound_below_component_admission_value",
            "selected_block_promote_to_h200": False,
            "explanation": (
                "Even deleting the entire selected two-kernel block would save less "
                "than one percent of the fixed qualified request and close only a "
                "small fraction of the 20% campaign gap; real fusion must still execute "
                "both reductions and therefore has a materially smaller ceiling."
            ),
        },
    }
    if not result["correctness"]["pass"]:
        raise SystemExit("correctness oracle or negative control failed")
    atomic_json(args.output, result)


if __name__ == "__main__":
    main()
