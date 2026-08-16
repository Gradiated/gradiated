#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import time


VOCAB = 262_144
HIDDEN = 5_376
ROWS = 384
REQUESTS = 32
DEPTH = 12
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
EXPECTED_WEIGHT_SHA256 = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
EXPECTED_CAPTURE_SHA256 = "80625b878e7479cd626250396f4be1a319e781245335600cd285037ce00fc66d"
EXPECTED_STATIC_TERMINAL_SHA256 = "12cdd51e1a1081f95deee4325a558c45e6dfac52abbff5b75ee0c522d385d0ee"
EXPECTED_H200_CONTROL_IDS_SHA256 = "e1ebaa70d782fcec41a707c186f8eac634b07bfb127ac2631d1f8f5b0cfab6aa"
CANDIDATE_ROWS = [
    1,
    8,
    32,
    64,
    128,
    256,
    512,
    1_024,
    2_048,
    4_096,
    8_192,
    16_384,
    32_768,
    65_536,
    131_072,
    262_144,
]
COORDINATE_DIMENSIONS = [128, 256, 512, 1_024, 2_048, 4_096]
H200_HBM_BYTES_PER_SECOND = 4.8e12
H200_BF16_OPS_PER_SECOND = 989.5e12
H200_INT8_OPS_PER_SECOND = 1_979e12
ROUTING_FIXED_SECONDS = 0.00025


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def tensor_sha(value) -> str:
    return hashlib.sha256(value.detach().contiguous().cpu().numpy().tobytes()).hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def exact_curve(scores, reference_id: int, approximate_scores, torch) -> tuple[list[dict[str, object]], int]:
    order = torch.argsort(approximate_scores, descending=True, stable=True)
    target_rank = int(torch.where(order == reference_id)[0][0]) + 1
    curve = []
    for candidate_rows in CANDIDATE_ROWS:
        candidates = order[:candidate_rows]
        exact_local = int(candidates[torch.argmax(scores[candidates])])
        curve.append(
            {
                "candidate_rows": candidate_rows,
                "candidate_fraction": candidate_rows / VOCAB,
                "retrieved_reference_top1": target_rank <= candidate_rows,
                "exact_rescored_top1": exact_local,
                "top1_recall": float(exact_local == reference_id),
            }
        )
    return curve, target_rank


def quantized_scores(weight, hidden, levels: int, quantize_hidden: bool, torch):
    started = time.monotonic()
    output = torch.empty((VOCAB,), dtype=torch.float32)
    if quantize_hidden:
        hidden_scale = hidden.abs().amax() / levels
        hidden_quantized = torch.round(hidden / hidden_scale).clamp(-levels, levels)
        hidden_for_score = hidden_quantized
    else:
        hidden_scale = torch.tensor(1.0)
        hidden_for_score = hidden
    chunk_rows = 4_096
    for start in range(0, VOCAB, chunk_rows):
        stop = min(VOCAB, start + chunk_rows)
        rows = weight[start:stop].float()
        scales = rows.abs().amax(dim=1).clamp_min(1.0e-12) / levels
        quantized = torch.round(rows / scales[:, None]).clamp(-levels, levels)
        output[start:stop] = torch.mv(quantized, hidden_for_score) * scales * hidden_scale
    return output, time.monotonic() - started


def coordinate_scores(weight, hidden, dimensions, torch):
    started = time.monotonic()
    return torch.mv(weight[:, dimensions].float(), hidden[dimensions]), time.monotonic() - started


def physical_bound(
    *,
    index_bytes: int,
    candidate_rows: int,
    approximate_ops: int,
    approximate_peak_ops_per_second: float,
    score_bytes: int,
) -> dict[str, object]:
    exact_weight_bytes = candidate_rows * HIDDEN * 2
    candidate_id_bytes = candidate_rows * 4
    fused_bytes = index_bytes + exact_weight_bytes + candidate_id_bytes
    materialized_bytes = fused_bytes + 2 * score_bytes
    exact_ops = 2 * ROWS * candidate_rows * HIDDEN
    approximate_compute_seconds = approximate_ops / (0.25 * approximate_peak_ops_per_second)
    exact_compute_seconds = exact_ops / (0.25 * H200_BF16_OPS_PER_SECOND)
    fused_memory_seconds = fused_bytes / (0.50 * H200_HBM_BYTES_PER_SECOND)
    materialized_memory_seconds = materialized_bytes / (0.50 * H200_HBM_BYTES_PER_SECOND)
    return {
        "index_bytes": index_bytes,
        "exact_candidate_weight_bytes_capture_lower_bound": exact_weight_bytes,
        "candidate_id_bytes": candidate_id_bytes,
        "fused_total_hbm_bytes_capture_lower_bound": fused_bytes,
        "materialized_score_total_hbm_bytes_capture_bound": materialized_bytes,
        "fused_bytes_fraction_of_dense_bf16_weight": fused_bytes / (VOCAB * HIDDEN * 2),
        "materialized_bytes_fraction_of_dense_bf16_weight": materialized_bytes / (VOCAB * HIDDEN * 2),
        "approximate_arithmetic_ops_384_rows": approximate_ops,
        "exact_candidate_arithmetic_ops_384_rows": exact_ops,
        "h200_analytical_seconds": {
            "assumptions": {
                "hbm_bandwidth_bytes_per_second_vendor_reported": H200_HBM_BYTES_PER_SECOND,
                "bf16_ops_per_second_vendor_reported": H200_BF16_OPS_PER_SECOND,
                "int8_ops_per_second_inferred_from_hopper_fp8_rate": H200_INT8_OPS_PER_SECOND,
                "effective_hbm_fraction": 0.50,
                "effective_math_fraction": 0.25,
                "fixed_routing_seconds_inherited_analytical_allowance": ROUTING_FIXED_SECONDS,
            },
            "approximate_compute_floor": approximate_compute_seconds,
            "exact_compute_floor": exact_compute_seconds,
            "fused_memory_floor": fused_memory_seconds,
            "materialized_memory_floor": materialized_memory_seconds,
            "fused_additive_bound": approximate_compute_seconds
            + exact_compute_seconds
            + fused_memory_seconds
            + ROUTING_FIXED_SECONDS,
            "materialized_additive_bound": approximate_compute_seconds
            + exact_compute_seconds
            + materialized_memory_seconds
            + ROUTING_FIXED_SECONDS,
        },
    }


def stratification(curve: list[dict[str, object]]) -> dict[str, object]:
    return {
        "row_order": "request_major_depth_minor",
        "request_count": REQUESTS,
        "depth_count": DEPTH,
        "by_candidate_rows": [
            {
                "candidate_rows": point["candidate_rows"],
                "by_request_recall": [point["top1_recall"]] * REQUESTS,
                "by_depth_recall": [point["top1_recall"]] * DEPTH,
            }
            for point in curve
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", required=True, type=pathlib.Path)
    parser.add_argument("--capture", required=True, type=pathlib.Path)
    parser.add_argument("--static-terminal", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    torch.set_num_threads(min(16, torch.get_num_threads()))
    identities = {
        "weight_sha256": sha256(args.weight),
        "capture_sha256": sha256(args.capture),
        "static_terminal_sha256": sha256(args.static_terminal),
        "runner_sha256": sha256(pathlib.Path(__file__)),
    }
    if identities["weight_sha256"] != EXPECTED_WEIGHT_SHA256:
        raise RuntimeError(f"weight_sha256_mismatch:{identities['weight_sha256']}")
    if identities["capture_sha256"] != EXPECTED_CAPTURE_SHA256:
        raise RuntimeError(f"capture_sha256_mismatch:{identities['capture_sha256']}")
    if identities["static_terminal_sha256"] != EXPECTED_STATIC_TERMINAL_SHA256:
        raise RuntimeError(f"static_terminal_sha256_mismatch:{identities['static_terminal_sha256']}")

    payload = torch.load(args.capture, map_location="cpu", weights_only=True)
    hidden_rows = payload["hidden_states"]
    proposals = payload["proposals"]
    if tuple(hidden_rows.shape) != (ROWS, HIDDEN) or hidden_rows.dtype != torch.bfloat16:
        raise RuntimeError(f"hidden_contract:{tuple(hidden_rows.shape)}:{hidden_rows.dtype}")
    if tuple(proposals.shape) != (ROWS,) or proposals.dtype not in (torch.int32, torch.int64):
        raise RuntimeError(f"proposal_contract:{tuple(proposals.shape)}:{proposals.dtype}")
    if not bool(torch.isfinite(hidden_rows.float()).all()):
        raise RuntimeError("hidden_nonfinite")
    unique_hidden, inverse = torch.unique(hidden_rows, dim=0, return_inverse=True)
    hidden = unique_hidden[0].float()

    with safe_open(args.weight, framework="pt", device="cpu") as handle:
        keys = list(handle.keys())
        if WEIGHT_KEY not in keys:
            raise RuntimeError("tied_weight_key_missing")
        weight = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError(f"weight_contract:{tuple(weight.shape)}:{weight.dtype}")

    reference_started = time.monotonic()
    reference_scores = torch.mv(weight.float(), hidden)
    reference_seconds = time.monotonic() - reference_started
    top_values, top_ids = torch.topk(reference_scores, 2)
    reference_id = int(top_ids[0])
    repeated_reference_ids = torch.full((ROWS,), reference_id, dtype=torch.int64)
    control_hash = tensor_sha(repeated_reference_ids)
    if control_hash != EXPECTED_H200_CONTROL_IDS_SHA256:
        raise RuntimeError(f"h200_control_identity_mismatch:{control_hash}")

    methods: list[dict[str, object]] = []
    score_bytes = ROWS * VOCAB * 4

    for name, levels, bits in [
        ("rowwise_symmetric_w8a8", 127, 8),
        ("rowwise_symmetric_w4a8", 7, 4),
    ]:
        approximate_scores, cpu_seconds = quantized_scores(
            weight, hidden, levels, quantize_hidden=True, torch=torch
        )
        curve, target_rank = exact_curve(reference_scores, reference_id, approximate_scores, torch)
        minimum_exact = next(point["candidate_rows"] for point in curve if point["top1_recall"] == 1.0)
        index_bytes = math.ceil(VOCAB * HIDDEN * bits / 8) + VOCAB * 2
        methods.append(
            {
                "name": name,
                "representation": {
                    "weight_codes": f"symmetric signed {bits}-bit, rowwise scale",
                    "activation_codes": "symmetric signed INT8, per hidden row scale",
                    "index_uses_only_tied_weight_geometry": True,
                    "h200_native": bits == 8,
                },
                "cpu_discovery_seconds": cpu_seconds,
                "reference_top1_approximate_rank": target_rank,
                "minimum_tested_candidate_rows_for_exact_top1": minimum_exact,
                "recall_curve": curve,
                "physical_bound": physical_bound(
                    index_bytes=index_bytes,
                    candidate_rows=minimum_exact,
                    approximate_ops=2 * ROWS * VOCAB * HIDDEN,
                    approximate_peak_ops_per_second=H200_INT8_OPS_PER_SECOND,
                    score_bytes=score_bytes,
                ),
            }
        )

    moment_started = time.monotonic()
    second_moment = torch.zeros((HIDDEN,), dtype=torch.float64)
    for start in range(0, VOCAB, 4_096):
        rows = weight[start : start + 4_096].float()
        second_moment += rows.square().sum(dim=0, dtype=torch.float64)
    dimension_order = torch.argsort(second_moment, descending=True, stable=True)
    moment_seconds = time.monotonic() - moment_started
    for dimensions_count in COORDINATE_DIMENSIONS:
        dimensions = dimension_order[:dimensions_count]
        approximate_scores, cpu_seconds = coordinate_scores(weight, hidden, dimensions, torch)
        curve, target_rank = exact_curve(reference_scores, reference_id, approximate_scores, torch)
        minimum_exact = next(point["candidate_rows"] for point in curve if point["top1_recall"] == 1.0)
        index_bytes = VOCAB * dimensions_count * 2 + dimensions_count * 2
        methods.append(
            {
                "name": f"weight_variance_bf16_coordinates_{dimensions_count}",
                "representation": {
                    "weight_codes": "BF16 coordinates selected by tied-weight second moment",
                    "activation_codes": "matching BF16/FP32 query coordinates",
                    "index_uses_only_tied_weight_geometry": True,
                    "h200_native": True,
                },
                "cpu_discovery_seconds": cpu_seconds,
                "index_construction_second_moment_seconds_shared": moment_seconds,
                "reference_top1_approximate_rank": target_rank,
                "minimum_tested_candidate_rows_for_exact_top1": minimum_exact,
                "recall_curve": curve,
                "physical_bound": physical_bound(
                    index_bytes=index_bytes,
                    candidate_rows=minimum_exact,
                    approximate_ops=2 * ROWS * VOCAB * dimensions_count,
                    approximate_peak_ops_per_second=H200_BF16_OPS_PER_SECOND,
                    score_bytes=score_bytes,
                ),
            }
        )

    viable_native = [
        method
        for method in methods
        if method["representation"]["h200_native"]
        and method["minimum_tested_candidate_rows_for_exact_top1"] < VOCAB
    ]
    best = min(
        viable_native,
        key=lambda method: method["physical_bound"]["h200_analytical_seconds"][
            "materialized_additive_bound"
        ],
    )
    best_materialized_seconds = best["physical_bound"]["h200_analytical_seconds"][
        "materialized_additive_bound"
    ]
    diverse_enough = int(unique_hidden.shape[0]) >= 32
    credible_component_advantage = best_materialized_seconds < 0.02480787181854248
    continue_to_h200 = diverse_enough and credible_component_advantage
    best_curve = best["recall_curve"]

    result = {
        "schema_version": 1,
        "classification": "adaptive_retrieval_vocab_offline_terminal",
        "evidence_labels": {
            "recall_and_candidate_curves": "measured on exact hash-bound capture",
            "cpu_timings": "measured discovery cost only; not transferable to H200",
            "h200_device_properties": "vendor-reported shared inventory",
            "h200_time_bounds": "analytical additive bounds, not measured",
            "production_path": "inferred integration plan",
        },
        "source": {
            **identities,
            "weight_path": str(args.weight.resolve()),
            "weight_key": WEIGHT_KEY,
            "capture_path": str(args.capture.resolve()),
            "static_terminal_path": str(args.static_terminal.resolve()),
        },
        "geometry": {
            "rows": ROWS,
            "requests": REQUESTS,
            "depth": DEPTH,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "weight_dtype": str(weight.dtype),
            "hidden_dtype": str(hidden_rows.dtype),
            "row_order": "request_major_depth_minor",
        },
        "capture_audit": {
            "unique_hidden_rows": int(unique_hidden.shape[0]),
            "unique_proposal_ids": int(torch.unique(proposals).numel()),
            "proposal_ids": [int(value) for value in torch.unique(proposals)],
            "inverse_unique_row_counts": [
                int((inverse == index).sum()) for index in range(int(unique_hidden.shape[0]))
            ],
            "all_rows_identical": int(unique_hidden.shape[0]) == 1,
            "interpretation": (
                "The bound 384-row serialization contains one repeated hidden state and "
                "proposal ID zero. Request/depth recall is therefore 384 replications of "
                "one decision and cannot establish workload-level retrieval quality."
            ),
        },
        "full_head_reference_top1_identity": {
            "token_id": reference_id,
            "repeated_384_ids_sha256": control_hash,
            "matches_prior_h200_control_ids_sha256": True,
            "top1_score_fp32": float(top_values[0]),
            "top2_token_id": int(top_ids[1]),
            "top2_score_fp32": float(top_values[1]),
            "top1_margin_fp32": float(top_values[0] - top_values[1]),
            "cpu_reference_seconds": reference_seconds,
            "softcap_note": "The stock fused softcap is monotone, so pre-softcap dot-product argmax is identical.",
        },
        "top1_recall_by_candidate_fraction": methods,
        "request_and_depth_stratification": {
            "method": best["name"],
            **stratification(best_curve),
        },
        "best_native_geometry": {
            "method": best["name"],
            "candidate_rows": best["minimum_tested_candidate_rows_for_exact_top1"],
            "candidate_fraction": best["minimum_tested_candidate_rows_for_exact_top1"] / VOCAB,
            "index_bytes": best["physical_bound"]["index_bytes"],
            "physical_bound": best["physical_bound"],
        },
        "dense_comparators": {
            "stock_component_median_seconds": 0.02480787181854248,
            "strongest_historical_dense_component_median_seconds": 0.004182975769042969,
            "dense_bf16_weight_bytes": VOCAB * HIDDEN * 2,
            "dense_bf16_arithmetic_ops_384_rows": 2 * ROWS * VOCAB * HIDDEN,
        },
        "routing_overhead": {
            "required_operations": [
                "rowwise activation quantization or coordinate gather",
                "approximate matrix product against immutable retrieval index",
                "fused per-row top-k without dense score materialization",
                "candidate-ID compaction and tied-BF16 row gather",
                "exact candidate dot products and stable argmax",
            ],
            "materialized_score_bytes_written_and_read": 2 * score_bytes,
            "fused_topk_score_storage_lower_bound_bytes": 0,
            "fixed_allowance_seconds_in_bound": ROUTING_FIXED_SECONDS,
            "unmeasured": [
                "actual CUTLASS/SGLang kernel latency",
                "per-output scale epilogue cost",
                "request-specific gather locality",
                "CUDA graph compatibility",
            ],
        },
        "h200_geometry_and_first_consumer_path": {
            "chip": {
                "sm_count": 132,
                "l2_bytes": 50_000_000,
                "hbm_bandwidth_bytes_per_second": H200_HBM_BYTES_PER_SECOND,
                "bf16_ops_per_second": H200_BF16_OPS_PER_SECOND,
                "int8_or_fp8_ops_per_second": H200_INT8_OPS_PER_SECOND,
            },
            "exact_shape": [ROWS, VOCAB, HIDDEN],
            "mapping": (
                "Quantize each BF16 hidden row to INT8, run an M=384 N=262144 "
                "K=5376 W8A8 GEMM over the immutable rowwise-scaled tied-weight "
                "index, fuse per-row top-k, gather only selected BF16 tied rows, "
                "and exact-score those rows before the stock monotone softcap/argmax."
            ),
            "tile_prior": (
                "A 128x128x64 Hopper tensor-core decomposition gives three M tiles, "
                "2048 N tiles, and 84 K steps; 6144 output tiles are enough to fill "
                "132 SMs. The index is HBM-resident, while scale metadata and a fused "
                "top-k working set can fit in L2."
            ),
            "first_consumer": (
                "SGLang LogitsProcessor target-verify hidden_states -> retrieval "
                "GEMM/top-k -> exact tied-row scorer -> existing softcap and greedy argmax."
            ),
            "falsifier": (
                "A target-H200 component must hash-bind the same weight and a genuinely "
                "diverse capture, preserve every full-head top-1, and beat 24.808 ms "
                "including routing; the 4.183 ms dense component is the stronger "
                "practical comparator."
            ),
        },
        "decision": {
            "continue_to_h200_consumer": continue_to_h200,
            "result": (
                "do_not_admit_h200_from_degenerate_capture"
                if not diverse_enough
                else "continue_to_exact_shape_h200_consumer"
                if credible_component_advantage
                else "close_representation_physical_bound_negative"
            ),
            "physical_advantage_on_bound_state": credible_component_advantage,
            "capture_diversity_gate": diverse_enough,
            "reason": (
                f"{best['name']} recovers the bound reference at "
                f"{best['minimum_tested_candidate_rows_for_exact_top1']}/{VOCAB} "
                f"candidates with an analytical materialized-score bound of "
                f"{best_materialized_seconds * 1e3:.3f} ms, but the 384-row capture "
                "contains one unique hidden state. That is insufficient to spend a "
                "GPU claim or claim request/depth robustness."
            ),
            "next_action": (
                "Close this admission without GPU work. A successor may recapture "
                "genuinely distinct verifier hidden states, hash-bind them, and rerun "
                "this same offline W8A8/coordinate retrieval consumer before any H200 claim."
            ),
        },
        "spend": {
            "gpu_claimed": False,
            "ssh_used": False,
            "paid_requests": 0,
            "actual_spend_usd": 0.0,
        },
    }
    atomic(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "reference_id": reference_id,
                "unique_hidden_rows": int(unique_hidden.shape[0]),
                "best_method": best["name"],
                "best_candidate_rows": best["minimum_tested_candidate_rows_for_exact_top1"],
                "decision": result["decision"]["result"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
