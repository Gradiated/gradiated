#!/usr/bin/env python3
"""One-tensor 2:4 sparse-base plus low-rank-residual offline experiment.

The producer reads only the selected safetensors byte range, constructs 2:4
magnitude sparsity along the GEMM K dimension, quantizes every represented
matrix with row-scaled E4M3FN, and factorizes only the resulting residual.
The reference consumer executes the exact staged chain through BF16 output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
import os
import resource
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
TENSOR = "model.language_model.layers.29.mlp.down_proj.weight"
SHAPE = (5376, 21504)  # [out, in]
RANK_ALIGNMENT = 128
EXPECTED_RANK = 512
SEED = 20260727
OVERSAMPLE = 16
SYNTHETIC_ROWS = 32
H200_HBM_BYTES_PER_SECOND = 4.8e12
H200_FP8_FLOPS_PER_SECOND = 1.979e15
LAUNCH_RESERVE_US = 3.0
LOCKED_SECONDS_PER_REQUEST = 0.625149101968745
LAYERS = 60
TARGET_VERIFICATION_STEPS = 15
COMPLETE_REQUESTS = 32
EXACT_CONSUMERS = {
    32: {
        "measured_dense_us": 56.28800019621849,
        "weight_passes": 1,
        "evidence": "../gemma4_h200_fp8_layer_dataflow_fusion/artifacts/"
        "persisted-real-down-v2-repair-20260722t141230z/remote/component-v2/"
        "ROW_M32.json",
    },
    384: {
        "measured_dense_us": 149.61600303649902,
        "weight_passes": 2,
        "evidence": "../gemma4_h200_ngram_m384_fp8_cluster_schedule/"
        "COMPONENT_MEASUREMENTS.jsonl",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def bf16_round(x: np.ndarray) -> np.ndarray:
    """Round float32 to BF16 round-to-nearest-even, returned as float32."""
    bits = np.asarray(x, dtype=np.float32).view(np.uint32)
    rounded = bits + np.uint32(0x7FFF) + ((bits >> 16) & np.uint32(1))
    return (rounded & np.uint32(0xFFFF0000)).view(np.float32)


def fp8_positive_codebook() -> tuple[np.ndarray, np.ndarray]:
    values: list[float] = []
    codes: list[int] = []
    for exponent in range(16):
        for mantissa in range(8):
            if exponent == 15 and mantissa == 7:
                continue
            if exponent == 0:
                value = math.ldexp(mantissa / 8.0, -6)
            else:
                value = math.ldexp(1.0 + mantissa / 8.0, exponent - 7)
            values.append(value)
            codes.append((exponent << 3) | mantissa)
    order = np.argsort(values)
    return np.asarray(values, dtype=np.float32)[order], np.asarray(codes, dtype=np.uint8)[order]


FP8_VALUES, FP8_CODES = fp8_positive_codebook()


def fp8_encode_normalized(x: np.ndarray) -> np.ndarray:
    absolute = np.abs(np.asarray(x, dtype=np.float32))
    positions = np.searchsorted(FP8_VALUES, absolute)
    hi = np.minimum(positions, len(FP8_VALUES) - 1)
    lo = np.maximum(positions - 1, 0)
    choose_hi = (absolute - FP8_VALUES[lo]) > (FP8_VALUES[hi] - absolute)
    chosen = np.where(choose_hi, hi, lo)
    codes = FP8_CODES[chosen].copy()
    codes |= np.where(np.signbit(x), np.uint8(0x80), np.uint8(0))
    return codes


def fp8_decode_normalized(codes: np.ndarray) -> np.ndarray:
    raw = np.asarray(codes, dtype=np.uint8)
    sign = np.where((raw & 0x80) != 0, -1.0, 1.0).astype(np.float32)
    magnitude = raw & 0x7F
    exponent = magnitude >> 3
    mantissa = magnitude & 7
    result = np.empty(raw.shape, dtype=np.float32)
    subnormal = exponent == 0
    result[subnormal] = np.ldexp(
        mantissa[subnormal].astype(np.float32) / 8.0, -6
    )
    normal = ~subnormal
    result[normal] = np.ldexp(
        1.0 + mantissa[normal].astype(np.float32) / 8.0,
        exponent[normal].astype(np.int32) - 7,
    )
    return sign * result


def fp8_quantize_rows(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=np.float32)
    scales = np.maximum(np.max(np.abs(x), axis=1, keepdims=True) / 448.0, 1e-12)
    codes = fp8_encode_normalized(np.clip(x / scales, -448.0, 448.0))
    return codes, scales[:, 0].astype(np.float32)


def fp8_dequantize_rows(codes: np.ndarray, scales: np.ndarray) -> np.ndarray:
    return fp8_decode_normalized(codes) * np.asarray(scales, dtype=np.float32)[:, None]


def fp8_quantize_dynamic_rows(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return fp8_quantize_rows(x)


class SelectedTensor:
    def __init__(self, shard: Path):
        self.path = shard
        self.file = shard.open("rb")
        self.mm = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.header_len = struct.unpack("<Q", self.mm[:8])[0]
        self.data_base = 8 + self.header_len
        self.header = json.loads(self.mm[8 : self.data_base])

    def close(self) -> None:
        self.mm.close()
        self.file.close()

    def load(self) -> tuple[np.ndarray, dict[str, object]]:
        metadata = self.header[TENSOR]
        if metadata["dtype"] != "BF16" or tuple(metadata["shape"]) != SHAPE:
            raise ValueError(f"selected tensor contract mismatch: {metadata}")
        start, end = metadata["data_offsets"]
        count = SHAPE[0] * SHAPE[1]
        raw = np.frombuffer(
            self.mm,
            dtype="<u2",
            count=count,
            offset=self.data_base + start,
        )
        weight = (raw.astype(np.uint32) << 16).view(np.float32).reshape(SHAPE)
        identity = {
            "tensor": TENSOR,
            "dtype": metadata["dtype"],
            "shape": list(metadata["shape"]),
            "data_offsets_relative": [start, end],
            "byte_range_absolute_half_open": [
                self.data_base + start,
                self.data_base + end,
            ],
            "selected_payload_sha256": hashlib.sha256(
                memoryview(self.mm)[self.data_base + start : self.data_base + end]
            ).hexdigest(),
        }
        return weight, identity


def pack_sparse_2of4(
    weight: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rows, cols = weight.shape
    groups = weight.reshape(rows, cols // 4, 4)
    chosen = np.argpartition(np.abs(groups), 2, axis=2)[:, :, 2:]
    chosen.sort(axis=2)
    chosen_values = np.take_along_axis(groups, chosen, axis=2).reshape(rows, cols // 2)
    value_codes, scales = fp8_quantize_rows(chosen_values)
    masks = (
        (np.uint8(1) << chosen[:, :, 0].astype(np.uint8))
        | (np.uint8(1) << chosen[:, :, 1].astype(np.uint8))
    )
    metadata = masks[:, 0::2] | (masks[:, 1::2] << np.uint8(4))
    decoded = unpack_sparse_2of4(value_codes, scales, metadata, cols)
    return value_codes, scales, metadata, decoded


def unpack_sparse_2of4(
    value_codes: np.ndarray,
    scales: np.ndarray,
    metadata: np.ndarray,
    cols: int,
) -> np.ndarray:
    rows = value_codes.shape[0]
    group_count = cols // 4
    masks = np.empty((rows, group_count), dtype=np.uint8)
    masks[:, 0::2] = metadata & np.uint8(0x0F)
    masks[:, 1::2] = metadata >> np.uint8(4)
    values = fp8_dequantize_rows(value_codes, scales).reshape(rows, group_count, 2)
    output = np.zeros((rows, group_count, 4), dtype=np.float32)
    for position in range(4):
        before = np.zeros_like(masks, dtype=np.uint8)
        for prior in range(position):
            before += ((masks >> np.uint8(prior)) & np.uint8(1))
        present = ((masks >> np.uint8(position)) & np.uint8(1)).astype(bool)
        if np.any(present):
            selected = np.minimum(before, 1)
            output[:, :, position][present] = np.take_along_axis(
                values, selected[:, :, None], axis=2
            )[:, :, 0][present]
    return output.reshape(rows, cols)


def distribution_metrics(actual: np.ndarray, reference: np.ndarray) -> dict[str, object]:
    actual64 = np.asarray(actual, dtype=np.float64)
    reference64 = np.asarray(reference, dtype=np.float64)
    delta = actual64 - reference64
    reference_norm = max(float(np.linalg.norm(reference64)), 1e-30)
    actual_norm = max(float(np.linalg.norm(actual64)), 1e-30)
    return {
        "maximum_absolute_error": float(np.max(np.abs(delta))),
        "relative_l2_error": float(np.linalg.norm(delta) / reference_norm),
        "cosine_similarity": float(
            np.vdot(actual64.ravel(), reference64.ravel())
            / (actual_norm * reference_norm)
        ),
        "nonfinite_count": int(np.count_nonzero(~np.isfinite(actual))),
    }


def physical_row(rows: int, rank: int) -> dict[str, object]:
    out_features, in_features = SHAPE
    measured = EXACT_CONSUMERS[rows]["measured_dense_us"]
    passes = EXACT_CONSUMERS[rows]["weight_passes"]
    dense_weight = passes * (out_features * in_features + 4 * out_features)
    quant_input = 2 * rows * in_features + rows * in_features + 4 * rows
    dense_gemm = rows * in_features + 2 * rows * out_features
    dense_other = quant_input + dense_gemm
    dense_bytes = dense_weight + dense_other
    effective_bandwidth = dense_bytes / (measured * 1e-6)

    sparse_weight = passes * (
        out_features * in_features // 2
        + out_features * in_features // 8
        + 4 * out_features
    )
    factor_weight = passes * (
        rank * (in_features + out_features) + 4 * (rank + out_features)
    )
    sparse_gemm = rows * in_features + 2 * rows * out_features
    residual_b = rows * in_features + 2 * rows * rank
    quant_intermediate = 2 * rows * rank + rows * rank + 4 * rows
    residual_a = rows * rank + 2 * rows * out_features
    bf16_reduce = 6 * rows * out_features
    candidate_other = (
        quant_input
        + sparse_gemm
        + residual_b
        + quant_intermediate
        + residual_a
        + bf16_reduce
    )
    fixed_bytes = sparse_weight + candidate_other + passes * 4 * out_features
    bytes_per_rank = passes * (in_features + out_features + 4)
    memory_rank_limit = (
        ((measured - 4 * LAUNCH_RESERVE_US) * 1e-6 * effective_bandwidth)
        - fixed_bytes
    ) / bytes_per_rank
    fixed_flops = rows * out_features * in_features
    flops_per_rank = 2 * rows * (in_features + out_features)
    compute_rank_limit = (
        (measured - 4 * LAUNCH_RESERVE_US)
        * 1e-6
        * H200_FP8_FLOPS_PER_SECOND
        - fixed_flops
    ) / flops_per_rank
    aligned_limit = math.floor(
        min(memory_rank_limit, compute_rank_limit) / RANK_ALIGNMENT
    ) * RANK_ALIGNMENT

    total_bytes = sparse_weight + factor_weight + candidate_other
    sparse_flops = rows * out_features * in_features
    correction_flops = 2 * rows * rank * (in_features + out_features)
    compute_us = (
        sparse_flops + correction_flops
    ) / H200_FP8_FLOPS_PER_SECOND * 1e6
    memory_us = total_bytes / effective_bandwidth * 1e6
    candidate_us = max(compute_us, memory_us) + 4 * LAUNCH_RESERVE_US
    return {
        "rows": rows,
        "rank_limit_continuous": {
            "memory": memory_rank_limit,
            "compute": compute_rank_limit,
        },
        "maximum_128_aligned_rank": aligned_limit,
        "dense": {
            "measured_us": measured,
            "weight_and_scale_bytes": dense_weight,
            "other_compulsory_bytes": dense_other,
            "total_compulsory_bytes": dense_bytes,
            "calibrated_effective_bandwidth_bytes_per_second": effective_bandwidth,
            "launches": 2,
            "evidence": EXACT_CONSUMERS[rows]["evidence"],
        },
        "candidate": {
            "sparse_weight_value_metadata_scale_bytes": sparse_weight,
            "factor_weight_and_scale_bytes": factor_weight,
            "other_compulsory_bytes": candidate_other,
            "total_compulsory_bytes": total_bytes,
            "sparse_base_useful_flops": sparse_flops,
            "two_correction_gemm_useful_flops": correction_flops,
            "memory_time_us": memory_us,
            "compute_time_us": compute_us,
            "added_launch_reserve_us": 4 * LAUNCH_RESERVE_US,
            "modeled_time_us": candidate_us,
            "modeled_saved_us": measured - candidate_us,
            "modeled_reduction_fraction": (measured - candidate_us) / measured,
            "launches": 6,
            "launch_sequence": [
                "dynamic_per_token_E4M3_quantize_x",
                "2of4_sparse_E4M3_base_GEMM_to_BF16",
                "dense_E4M3_residual_B_GEMM_to_BF16",
                "dynamic_per_token_E4M3_quantize_intermediate",
                "dense_E4M3_residual_A_GEMM_to_BF16",
                "BF16_base_plus_correction_reduction",
            ],
        },
    }


def derive_rank() -> tuple[int, dict[str, object]]:
    rows = {m: physical_row(m, EXPECTED_RANK) for m in EXACT_CONSUMERS}
    derived = min(row["maximum_128_aligned_rank"] for row in rows.values())
    if derived != EXPECTED_RANK:
        raise RuntimeError(f"rank binding changed: expected {EXPECTED_RANK}, got {derived}")
    return derived, {
        "rank_alignment": RANK_ALIGNMENT,
        "derivation": "closed-form minimum of memory and compute inequalities; no rank sweep",
        "launch_reserve_us_per_added_launch": LAUNCH_RESERVE_US,
        "h200_peak_hbm_bytes_per_second": H200_HBM_BYTES_PER_SECOND,
        "h200_peak_fp8_flops_per_second": H200_FP8_FLOPS_PER_SECOND,
        "rows": rows,
    }


def randomized_residual_factors(
    residual: np.ndarray, rank: int
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    rng = np.random.default_rng(SEED)
    sketch_width = rank + OVERSAMPLE
    omega = rng.standard_normal(
        (residual.shape[1], sketch_width), dtype=np.float32
    ) / math.sqrt(sketch_width)
    y = residual @ omega
    # Exactly one power step improves the fixed-rank subspace without exploring rank.
    y = residual @ (residual.T @ y)
    q, _ = np.linalg.qr(y, mode="reduced")
    b = q.T @ residual
    gram = b @ b.T
    eigenvalues, uhat = np.linalg.eigh(gram.astype(np.float64))
    order = np.argsort(eigenvalues)[::-1][:rank]
    singular = np.sqrt(np.maximum(eigenvalues[order], 0.0)).astype(np.float32)
    left_basis = (q @ uhat[:, order].astype(np.float32)).astype(np.float32)
    safe_singular = np.maximum(singular, np.finfo(np.float32).tiny)
    right = (
        uhat[:, order].astype(np.float32).T @ b
    ) / safe_singular[:, None]
    root = np.sqrt(singular)
    factor_a = left_basis * root[None, :]
    factor_b = right * root[:, None]
    return factor_a, factor_b, {
        "algorithm": "deterministic randomized range finder, one power step, "
        "small Gram eigendecomposition",
        "seed": SEED,
        "rank": rank,
        "oversample": OVERSAMPLE,
        "power_steps": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()

    rank, physical = derive_rank()
    index_path = args.checkpoint / "model.safetensors.index.json"
    index = json.loads(index_path.read_text())
    shard_name = index["weight_map"][TENSOR]
    shard = SelectedTensor(args.checkpoint / shard_name)
    try:
        weight, tensor_identity = shard.load()
    finally:
        shard.close()
    original_weight = weight.copy()

    sparse_codes, sparse_scales, sparse_metadata, sparse_weight = pack_sparse_2of4(
        weight
    )
    residual = weight
    residual -= sparse_weight
    uncorrected_weight = distribution_metrics(sparse_weight, original_weight)

    factor_a, factor_b, factorization = randomized_residual_factors(residual, rank)
    factor_a_codes, factor_a_scales = fp8_quantize_rows(factor_a)
    factor_b_codes, factor_b_scales = fp8_quantize_rows(factor_b)
    factor_a_dq = fp8_dequantize_rows(factor_a_codes, factor_a_scales)
    factor_b_dq = fp8_dequantize_rows(factor_b_codes, factor_b_scales)

    corrected_delta_sq = 0.0
    reference_sq = 0.0
    corrected_max_abs = 0.0
    for start in range(0, SHAPE[0], 128):
        end = min(start + 128, SHAPE[0])
        reconstructed = sparse_weight[start:end] + factor_a_dq[start:end] @ factor_b_dq
        delta = reconstructed.astype(np.float64) - original_weight[start:end].astype(
            np.float64
        )
        corrected_delta_sq += float(np.sum(delta * delta))
        reference = original_weight[start:end].astype(np.float64)
        reference_sq += float(np.sum(reference * reference))
        corrected_max_abs = max(corrected_max_abs, float(np.max(np.abs(delta))))
    corrected_weight = {
        "maximum_absolute_error": corrected_max_abs,
        "relative_l2_error": math.sqrt(corrected_delta_sq / reference_sq),
        "nonfinite_count": 0,
    }

    rng = np.random.default_rng(SEED + 1)
    synthetic_input = bf16_round(
        rng.standard_normal((SYNTHETIC_ROWS, SHAPE[1]), dtype=np.float32)
    )
    input_codes, input_scales = fp8_quantize_dynamic_rows(synthetic_input)
    input_dq = fp8_dequantize_rows(input_codes, input_scales)
    reference_output = bf16_round(synthetic_input @ original_weight.T)
    sparse_output = bf16_round(input_dq @ sparse_weight.T)
    residual_intermediate = bf16_round(input_dq @ factor_b_dq.T)
    intermediate_codes, intermediate_scales = fp8_quantize_dynamic_rows(
        residual_intermediate
    )
    intermediate_dq = fp8_dequantize_rows(intermediate_codes, intermediate_scales)
    correction_output = bf16_round(intermediate_dq @ factor_a_dq.T)
    corrected_output = bf16_round(sparse_output + correction_output)
    uncorrected_output_error = distribution_metrics(sparse_output, reference_output)
    corrected_output_error = distribution_metrics(corrected_output, reference_output)

    representation_path = args.output / "SPARSE_LOWRANK_RESIDUAL_R512.npz"
    np.savez(
        representation_path,
        sparse_value_codes=sparse_codes,
        sparse_scales=sparse_scales,
        sparse_metadata=sparse_metadata,
        factor_a_codes=factor_a_codes,
        factor_a_scales=factor_a_scales,
        factor_b_codes=factor_b_codes,
        factor_b_scales=factor_b_scales,
    )
    synthetic_path = args.output / "SYNTHETIC_M32_INPUT.npy"
    np.save(synthetic_path, synthetic_input)

    request_saved = (
        physical["rows"][384]["candidate"]["modeled_saved_us"]
        * 1e-6
        * LAYERS
        * TARGET_VERIFICATION_STEPS
        / COMPLETE_REQUESTS
    )
    reconstruction_improvement = 1.0 - (
        corrected_weight["relative_l2_error"]
        / uncorrected_weight["relative_l2_error"]
    )
    output_improvement = 1.0 - (
        corrected_output_error["relative_l2_error"]
        / uncorrected_output_error["relative_l2_error"]
    )
    focused_checks = {
        "rank_is_closed_form_maximum": rank == EXPECTED_RANK,
        "rank_640_is_inadmissible_at_decode": physical["rows"][32][
            "maximum_128_aligned_rank"
        ]
        < 640,
        "sparse_group_masks_have_exactly_two_bits": bool(
            np.all(
                np.unpackbits(
                    np.stack(
                        [sparse_metadata & 0x0F, sparse_metadata >> 4], axis=-1
                    ).reshape(-1, 1),
                    axis=1,
                ).sum(axis=1)
                == 2
            )
        ),
        "sparse_pack_decode_roundtrip": bool(
            np.array_equal(
                sparse_weight,
                unpack_sparse_2of4(
                    sparse_codes, sparse_scales, sparse_metadata, SHAPE[1]
                ),
            )
        ),
        "fp8_zero_roundtrip": bool(
            fp8_decode_normalized(fp8_encode_normalized(np.asarray([0.0])))[0]
            == 0.0
        ),
        "fp8_max_roundtrip": bool(
            fp8_decode_normalized(fp8_encode_normalized(np.asarray([448.0])))[0]
            == 448.0
        ),
        "all_outputs_finite": bool(
            np.all(np.isfinite(reference_output))
            and np.all(np.isfinite(sparse_output))
            and np.all(np.isfinite(corrected_output))
        ),
        "correction_materially_improves_weight_error": reconstruction_improvement
        >= 0.25,
        "correction_materially_improves_output_error": output_improvement >= 0.25,
        "complete_physical_bound_positive_m32": physical["rows"][32]["candidate"][
            "modeled_saved_us"
        ]
        > 0,
        "complete_physical_bound_positive_m384": physical["rows"][384]["candidate"][
            "modeled_saved_us"
        ]
        > 0,
    }

    terminal = {
        "schema_version": 1,
        "generated_utc": utc_now(),
        "project": "gemma4_h200_2to4_lowrank_residual_recovery",
        "classification": "offline_result_pending_consumer_classification",
        "selection": {
            "projection_family": "down_proj",
            "layer": 29,
            "selection_rule": "single-tensor MLP projection, deterministic middle "
            "layer from the prior architecture-weighted screen; selected before "
            "reading tensor payload",
            "tensor": TENSOR,
            "source_layout": "row-major safetensors [out_features,in_features]",
            "shape": list(SHAPE),
            "source_dtype": "BF16",
            "sparse_grouping": "exactly 2 largest-magnitude values in each "
            "contiguous K-axis group of 4",
            "represented_dtype": "row-scaled E4M3FN values, FP32 scales, packed "
            "4-bit masks per group",
            "residual_rank": rank,
            "residual_factor_layouts": {
                "A": [SHAPE[0], rank],
                "B": [rank, SHAPE[1]],
            },
        },
        "identities": {
            "model": f"{MODEL}@{REVISION}",
            "checkpoint_index": {
                "path": str(index_path),
                "sha256": sha256(index_path),
            },
            "source_shard": {
                "path": str(args.checkpoint / shard_name),
                "known_content_address_sha256": "018912220f559f7025d60333e0996183cd538aa77ad6f4988a89ce47be681f10",
                "rehash_performed": False,
            },
            "selected_tensor_payload": tensor_identity,
            "producer_reference_consumer": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256(Path(__file__).resolve()),
            },
            "generated_representation": {
                "path": str(representation_path),
                "sha256": sha256(representation_path),
                "bytes": representation_path.stat().st_size,
            },
            "synthetic_input": {
                "path": str(synthetic_path),
                "sha256": sha256(synthetic_path),
                "bytes": synthetic_path.stat().st_size,
                "evidence_label": "synthetic deterministic input",
            },
        },
        "ownership_contract": {
            "producer": "load selected BF16 bytes -> magnitude 2:4 on K -> "
            "row-scaled E4M3FN sparse pack -> residual-only rank-512 factorization "
            "-> row-scaled E4M3FN factors",
            "sparse_consumer": "dynamic row-scaled E4M3FN input -> native 2:4 "
            "sparse GEMM -> BF16 base output",
            "residual_consumer_1": "same quantized input -> dense E4M3FN B GEMM "
            "-> BF16 [M,512]",
            "residual_consumer_2": "dynamic row-scaled E4M3FN intermediate -> "
            "dense E4M3FN A GEMM -> BF16 correction",
            "output_owner": "BF16 add consumes every base/correction element and "
            "returns row-major BF16 [M,5376] to the unchanged residual-add consumer",
            "scale_convention": "one FP32 scale per activation row and per represented "
            "weight/factor output row; FP32 accumulation, BF16 GEMM outputs",
        },
        "factorization": factorization,
        "error_evidence": {
            "weight_reconstruction": {
                "uncorrected_sparse_base": uncorrected_weight,
                "corrected_sparse_plus_rank512": corrected_weight,
                "relative_error_reduction_fraction": reconstruction_improvement,
                "evidence_label": "measured exact selected BF16 tensor with simulated "
                "E4M3FN representation",
            },
            "exact_shape_m32_output": {
                "input": "synthetic deterministic BF16-rounded Gaussian [32,21504]",
                "reference": "BF16-rounded dense source-weight matmul",
                "uncorrected_sparse_base": uncorrected_output_error,
                "corrected_sparse_plus_rank512": corrected_output_error,
                "relative_error_reduction_fraction": output_improvement,
                "evidence_label": "measured CPU reference consumer; no CUDA timing",
            },
        },
        "physical_bound": physical,
        "locked_request_bound": {
            "locked_seconds_per_request": LOCKED_SECONDS_PER_REQUEST,
            "counted_scope": "only measured M384 down projections across 60 layers "
            "and 15 observed target-verification steps; excludes any M32 credit",
            "modeled_saved_seconds_per_request": request_saved,
            "modeled_candidate_seconds_per_request": LOCKED_SECONDS_PER_REQUEST
            - request_saved,
            "modeled_reduction_fraction": request_saved
            / LOCKED_SECONDS_PER_REQUEST,
            "mapping": "M384_saved_us * 60 layers * 15 steps / 32 requests",
            "evidence_label": "derived attainable physical bound, not measured "
            "candidate timing or endpoint gain",
            "uncertainty": "Requires an exact maintained sparse E4M3 consumer to "
            "match the calibrated dense efficiency; launch reserve is 3 us for each "
            "of four added launches and no M32 request credit is counted.",
        },
        "focused_offline_checks": focused_checks,
        "resources": {
            "wall_seconds": time.monotonic() - started,
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "cuda_used": False,
            "gpu_claimed": False,
            "provider_or_endpoint_used": False,
            "actual_spend_usd": 0.0,
            "tensor_payloads_read": [TENSOR],
            "checkpoint_shards_copied_or_rehashed": False,
            "ranks_evaluated": [rank],
        },
    }
    atomic_json(args.output / "OFFLINE_RAW_TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
