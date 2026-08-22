#!/usr/bin/env python3
"""CPU reference for a certified partial-dot Gemma vocabulary-head search."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

VOCAB = 262144
HIDDEN = 5376
REQUESTS = 32
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
PRIOR_WEIGHT_ARTIFACT_SHA256 = (
    "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
)
CAPTURE_SHA256 = "ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54"
CAPTURE_TERMINAL_SHA256 = (
    "fc7297d3bf51e9118e0cf5bde4eec7c2bd22dc2d07a6608c3b19f8b55d55a9bc"
)
CONFIG_SHA256 = "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"
INDEX_SHA256 = "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
GEMMA4_SOURCE_SHA256 = (
    "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
)
LOGITS_SOURCE_SHA256 = (
    "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def gamma(operations: int, unit_roundoff: float = 2.0**-24) -> float:
    product = operations * unit_roundoff
    if product >= 1:
        raise RuntimeError("roundoff_bound_undefined")
    return product / (1.0 - product)


def select_capture_rows(payload: dict[str, Any], rows_per_request: int):
    import torch

    hidden = payload["hidden_states"]
    ownership = payload["ownership"]
    if (
        tuple(hidden.shape) != (1536, HIDDEN)
        or hidden.dtype != torch.bfloat16
        or len(ownership) != hidden.shape[0]
        or not bool(torch.isfinite(hidden.float()).all())
    ):
        raise RuntimeError("capture_geometry_dtype_or_finiteness_mismatch")
    request_order = list(dict.fromkeys(str(row["request_id"]) for row in ownership))
    if len(request_order) != REQUESTS:
        raise RuntimeError("capture_request_count_mismatch")
    selected: list[int] = []
    per_request: dict[str, list[int]] = {request_id: [] for request_id in request_order}
    for index, row in enumerate(ownership):
        request_id = str(row["request_id"])
        if len(per_request[request_id]) >= rows_per_request:
            continue
        per_request[request_id].append(index)
        selected.append(index)
    expected = REQUESTS * rows_per_request
    if len(selected) != expected:
        raise RuntimeError("capture_selection_incomplete")
    return hidden[selected].contiguous(), [ownership[index] for index in selected]


def bounded_norm_square(sum_float32, coordinates: int, upper: bool):
    rounding = gamma(max(1, coordinates - 1))
    if upper:
        return sum_float32.double() / (1.0 - rounding)
    return (sum_float32.double() / (1.0 + rounding)).clamp_min(0)


def safe_max_excluding(values, ids):
    import torch

    copy = values.clone()
    copy[torch.arange(values.shape[0]), ids] = float("-inf")
    return copy.max(dim=1).values


def traffic_metrics(active, selected_dimensions: int) -> dict[str, float | int]:
    queries, vocabulary = active.shape
    union_active = active.any(dim=0)
    selected_fraction = selected_dimensions / HIDDEN
    residual_fraction = 1.0 - selected_fraction
    logical_active_fraction = float(active.double().mean().item())
    union_active_fraction = float(union_active.double().mean().item())
    logical_traffic_fraction = (
        selected_fraction + residual_fraction * logical_active_fraction
    )
    physical_traffic_fraction = (
        selected_fraction + residual_fraction * union_active_fraction
    )
    return {
        "queries": queries,
        "active_rows_mean": float(active.sum(dim=1).double().mean().item()),
        "active_rows_min": int(active.sum(dim=1).min().item()),
        "active_rows_max": int(active.sum(dim=1).max().item()),
        "logical_active_row_fraction": logical_active_fraction,
        "physical_union_active_rows": int(union_active.sum().item()),
        "physical_union_active_row_fraction": union_active_fraction,
        "logical_weight_traffic_fraction": logical_traffic_fraction,
        "logical_weight_bytes_avoided_fraction": 1.0 - logical_traffic_fraction,
        "physical_weight_traffic_fraction": physical_traffic_fraction,
        "physical_weight_bytes_avoided_fraction": 1.0 - physical_traffic_fraction,
        "dense_weight_bytes": VOCAB * HIDDEN * 2,
        "selected_weight_bytes": VOCAB * selected_dimensions * 2,
        "physical_residual_weight_bytes": int(
            union_active.sum().item() * (HIDDEN - selected_dimensions) * 2
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight-shard", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--capture-terminal", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--gemma4-source", type=Path, required=True)
    parser.add_argument("--logits-source", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows-per-request", type=int, default=1)
    parser.add_argument(
        "--dimensions", default="256,512,1024,2048,3072,4096,4864"
    )
    parser.add_argument("--coordinate-chunk", type=int, default=256)
    parser.add_argument("--weight-row-chunk", type=int, default=8192)
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    started = time.monotonic()
    identities = {
        "capture": sha256_file(args.capture),
        "capture_terminal": sha256_file(args.capture_terminal),
        "config": sha256_file(args.config),
        "index": sha256_file(args.index),
        "gemma4_source": sha256_file(args.gemma4_source),
        "logits_source": sha256_file(args.logits_source),
        "contract": sha256_file(args.contract),
        "runner": sha256_file(Path(__file__).resolve()),
    }
    expected = {
        "capture": CAPTURE_SHA256,
        "capture_terminal": CAPTURE_TERMINAL_SHA256,
        "config": CONFIG_SHA256,
        "index": INDEX_SHA256,
        "gemma4_source": GEMMA4_SOURCE_SHA256,
        "logits_source": LOGITS_SOURCE_SHA256,
    }
    for name, digest in expected.items():
        if identities[name] != digest:
            raise RuntimeError(f"{name}_hash_mismatch")
    config = json.loads(args.config.read_text())
    index = json.loads(args.index.read_text())
    mapped_shard = index["weight_map"].get(WEIGHT_KEY)
    if mapped_shard != args.weight_shard.name:
        raise RuntimeError("pinned_index_weight_shard_mapping_mismatch")
    text_config = config["text_config"]
    if (
        text_config["hidden_size"] != HIDDEN
        or text_config["vocab_size"] != VOCAB
        or not text_config["tie_word_embeddings"]
        or text_config["final_logit_softcapping"] != 30.0
    ):
        raise RuntimeError("pinned_config_geometry_mismatch")
    payload = torch.load(
        args.capture, map_location="cpu", weights_only=True, mmap=True
    )
    hidden_bf16, selected_ownership = select_capture_rows(
        payload, args.rows_per_request
    )
    hidden = hidden_bf16.float()
    dimensions = sorted({int(value) for value in args.dimensions.split(",")})
    if not dimensions or dimensions[0] <= 0 or dimensions[-1] >= HIDDEN:
        raise RuntimeError("invalid_dimension_sweep")
    checkpoints = dimensions + [HIDDEN]
    if any(value % args.coordinate_chunk for value in checkpoints):
        raise RuntimeError("dimensions_must_align_to_coordinate_chunk")

    with safe_open(args.weight_shard, framework="pt", device="cpu") as handle:
        if WEIGHT_KEY not in handle.keys():
            raise RuntimeError("tied_weight_key_absent")
        weight = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError("tied_weight_geometry_or_dtype_mismatch")

    stats_started = time.monotonic()
    weight_column_square = torch.zeros(HIDDEN, dtype=torch.float64)
    weight_row_square_float = torch.zeros(VOCAB, dtype=torch.float32)
    weight_digest = hashlib.sha256()
    for row_start in range(0, VOCAB, args.weight_row_chunk):
        row_end = min(VOCAB, row_start + args.weight_row_chunk)
        block_bf16 = weight[row_start:row_end].contiguous()
        weight_digest.update(block_bf16.view(torch.uint8).numpy().tobytes())
        block = block_bf16.float()
        squared = block.square()
        weight_column_square += squared.sum(dim=0, dtype=torch.float64)
        weight_row_square_float[row_start:row_end] = squared.sum(dim=1)
    identities["tied_weight_tensor"] = weight_digest.hexdigest()
    identities["prior_extracted_tied_weight_safetensors"] = (
        PRIOR_WEIGHT_ARTIFACT_SHA256
    )
    weight_total_square_upper = bounded_norm_square(
        weight_row_square_float, HIDDEN, upper=True
    )
    hidden_square = hidden.double().square()
    hidden_total_square = hidden_square.sum(dim=1)
    hidden_column_square_mean = hidden_square.mean(dim=0)
    importance = hidden_column_square_mean * weight_column_square / VOCAB
    coordinate_order = torch.argsort(importance, descending=True)
    coordinate_order_sha256 = hashlib.sha256(
        coordinate_order.to(torch.int32).numpy().tobytes()
    ).hexdigest()
    stats_seconds = time.monotonic() - stats_started

    sweep_started = time.monotonic()
    queries = hidden.shape[0]
    partial_scores = torch.zeros((queries, VOCAB), dtype=torch.float32)
    selected_weight_square_float = torch.zeros(VOCAB, dtype=torch.float32)
    selected_hidden_square = torch.zeros(queries, dtype=torch.float64)
    snapshots: dict[int, dict[str, Any]] = {}
    for coordinate_start in range(0, HIDDEN, args.coordinate_chunk):
        coordinate_end = coordinate_start + args.coordinate_chunk
        coordinates = coordinate_order[coordinate_start:coordinate_end]
        weight_chunk = weight[:, coordinates].float().contiguous()
        hidden_chunk = hidden[:, coordinates].contiguous()
        partial_scores.add_(hidden_chunk @ weight_chunk.T)
        selected_weight_square_float.add_(weight_chunk.square().sum(dim=1))
        selected_hidden_square.add_(
            hidden_chunk.double().square().sum(dim=1)
        )
        if coordinate_end in checkpoints:
            snapshots[coordinate_end] = {
                "scores": partial_scores.clone(),
                "weight_square_float": selected_weight_square_float.clone(),
                "hidden_square": selected_hidden_square.clone(),
            }
    sweep_seconds = time.monotonic() - sweep_started

    full = snapshots[HIDDEN]
    full_scores = full["scores"]
    weight_total_norm_upper = weight_total_square_upper.sqrt()
    hidden_total_norm = hidden_total_square.sqrt()
    reference_roundoff = gamma(2 * HIDDEN + HIDDEN // args.coordinate_chunk)
    reference_error = (
        reference_roundoff
        * hidden_total_norm[:, None]
        * weight_total_norm_upper[None, :]
    )
    stock_accumulation_error = (
        gamma(HIDDEN)
        * hidden_total_norm[:, None]
        * weight_total_norm_upper[None, :]
    )
    bfloat16_roundoff = 2.0**-8
    stock_output_rounding_error = (
        bfloat16_roundoff
        / (1.0 - bfloat16_roundoff)
        * (
            hidden_total_norm[:, None] * weight_total_norm_upper[None, :]
            + stock_accumulation_error
        )
    )
    stock_total_error = (
        reference_error + stock_accumulation_error + stock_output_rounding_error
    )
    reference_ids = full_scores.argmax(dim=1)
    reference_values = full_scores[
        torch.arange(queries), reference_ids
    ]
    reference_runner_up = safe_max_excluding(full_scores, reference_ids)
    exact_real_winner_certified = bool(
        (
            reference_values
            - reference_error[torch.arange(queries), reference_ids]
            > safe_max_excluding(full_scores + reference_error, reference_ids)
        )
        .all()
        .item()
    )
    stock_winner_certified_from_cpu = bool(
        (
            reference_values
            - stock_total_error[torch.arange(queries), reference_ids]
            > safe_max_excluding(full_scores + stock_total_error, reference_ids)
        )
        .all()
        .item()
    )

    rows: list[dict[str, Any]] = []
    for selected_dimensions in dimensions:
        snapshot = snapshots[selected_dimensions]
        scores = snapshot["scores"]
        selected_weight_square_upper = bounded_norm_square(
            snapshot["weight_square_float"], selected_dimensions, upper=True
        )
        selected_weight_square_lower = bounded_norm_square(
            snapshot["weight_square_float"], selected_dimensions, upper=False
        )
        residual_weight_square_upper = (
            weight_total_square_upper - selected_weight_square_lower
        ).clamp_min(0)
        selected_hidden_square_exact = snapshot["hidden_square"]
        residual_hidden_square = (
            hidden_total_square - selected_hidden_square_exact
        ).clamp_min(0)
        selected_weight_norm_upper = selected_weight_square_upper.sqrt()
        residual_weight_norm_upper = residual_weight_square_upper.sqrt()
        selected_hidden_norm = selected_hidden_square_exact.sqrt()
        residual_hidden_norm = residual_hidden_square.sqrt()
        partial_error = (
            gamma(
                2 * selected_dimensions
                + selected_dimensions // args.coordinate_chunk
            )
            * selected_hidden_norm[:, None]
            * selected_weight_norm_upper[None, :]
        )
        exact_real_upper = (
            scores
            + partial_error
            + residual_hidden_norm[:, None] * residual_weight_norm_upper[None, :]
        )
        stock_upper = exact_real_upper + (
            stock_accumulation_error + stock_output_rounding_error
        )

        seed_ids = scores.argmax(dim=1)
        seed_real_lower = (
            full_scores[torch.arange(queries), seed_ids]
            - reference_error[torch.arange(queries), seed_ids]
        )
        seed_stock_lower = (
            full_scores[torch.arange(queries), seed_ids]
            - stock_total_error[torch.arange(queries), seed_ids]
        )
        oracle_real_lower = (full_scores - reference_error).max(dim=1).values
        oracle_stock_lower = (full_scores - stock_total_error).max(dim=1).values
        active_seed_real = exact_real_upper >= seed_real_lower[:, None]
        active_oracle_real = exact_real_upper >= oracle_real_lower[:, None]
        active_seed_stock = stock_upper >= seed_stock_lower[:, None]
        active_oracle_stock = stock_upper >= oracle_stock_lower[:, None]
        reference_inside = {
            "seed_real": bool(
                active_seed_real[
                    torch.arange(queries), reference_ids
                ].all().item()
            ),
            "oracle_real": bool(
                active_oracle_real[
                    torch.arange(queries), reference_ids
                ].all().item()
            ),
            "seed_stock": bool(
                active_seed_stock[
                    torch.arange(queries), reference_ids
                ].all().item()
            ),
            "oracle_stock": bool(
                active_oracle_stock[
                    torch.arange(queries), reference_ids
                ].all().item()
            ),
        }
        rows.append(
            {
                "selected_dimensions": selected_dimensions,
                "selected_dimension_fraction": selected_dimensions / HIDDEN,
                "reference_winner_inside_all_survivor_sets": all(
                    reference_inside.values()
                ),
                "reference_winner_inside": reference_inside,
                "implementable_seed_exact_real": traffic_metrics(
                    active_seed_real, selected_dimensions
                ),
                "oracle_incumbent_exact_real": traffic_metrics(
                    active_oracle_real, selected_dimensions
                ),
                "implementable_seed_stock_bf16": traffic_metrics(
                    active_seed_stock, selected_dimensions
                ),
                "oracle_incumbent_stock_bf16": traffic_metrics(
                    active_oracle_stock, selected_dimensions
                ),
                "resident_index": {
                    "permuted_tied_weight_bytes": VOCAB * HIDDEN * 2,
                    "residual_norm_metadata_bytes": VOCAB * 4,
                    "coordinate_permutation_bytes": HIDDEN * 4,
                    "duplicate_selected_index_bytes_if_not_repacked": (
                        VOCAB * selected_dimensions * 2
                    ),
                },
            }
        )

    best_oracle_stock = max(
        rows,
        key=lambda row: row["oracle_incumbent_stock_bf16"][
            "physical_weight_bytes_avoided_fraction"
        ],
    )
    best_implementable_stock = max(
        rows,
        key=lambda row: row["implementable_seed_stock_bf16"][
            "physical_weight_bytes_avoided_fraction"
        ],
    )
    promote = (
        best_implementable_stock["implementable_seed_stock_bf16"][
            "physical_weight_bytes_avoided_fraction"
        ]
        >= 0.20
        and all(row["reference_winner_inside_all_survivor_sets"] for row in rows)
    )
    decision = (
        "reference_pruning_candidate"
        if promote
        else "typed_falsification_lossless_bound_too_loose"
    )
    result = {
        "schema_version": 1,
        "classification": "lossless_output_head_branch_bound_reference_terminal",
        "decision": decision,
        "promote_to_h200_component": promote,
        "identities": identities,
        "geometry": {
            "model": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "weight_key": WEIGHT_KEY,
            "weight_shape": [VOCAB, HIDDEN],
            "weight_dtype": str(weight.dtype),
            "capture_shape": list(payload["hidden_states"].shape),
            "capture_dtype": str(payload["hidden_states"].dtype),
            "sample_rows": queries,
            "requests": REQUESTS,
            "rows_per_request": args.rows_per_request,
            "selected_capture_rows": [
                {
                    "global_row": row["global_row"],
                    "request_id": row["request_id"],
                    "capture_index": row["capture_index"],
                    "depth_index": row["depth_index"],
                    "position": int(
                        payload["positions"][int(row["global_row"])].item()
                    ),
                }
                for row in selected_ownership
            ],
            "final_logit_softcapping": 30.0,
        },
        "stock_consumer": {
            "projection": "hidden_states.to(lm_head.weight.dtype) @ lm_head.weight.T",
            "weight_tying": "lm_head is model.embed_tokens at PP1; checkpoint embed_tokens is routed into ParallelLMHead on the last PP rank",
            "post_projection": "tensor-parallel gather/scatter, buffer copy, monotone fused softcap at 30, then logits/sampler consumer",
            "top1_effect": "strictly monotone softcap does not change a unique pre-softcap winner; the reference additionally charges a conservative BF16 matmul/output-rounding envelope",
        },
        "mechanism": {
            "name": "fixed_coordinate_partial_dot_residual_cauchy",
            "coordinate_order": "descending mean_capture_hidden_square times tied_weight_column_square",
            "coordinate_order_sha256": coordinate_order_sha256,
            "exact_real_bound": "partial_dot + FP32 guard + residual_hidden_l2 * residual_weight_row_l2",
            "stock_bound": "exact-real bound plus conservative FP32 accumulation and BF16 output-rounding envelopes",
            "implementable_incumbent": "full rescore lower bound for the row with maximum partial score",
            "oracle_incumbent": "best lower bound across full dense reference; this can only overstate attainable pruning",
            "all_vocabulary_rows_reachable": True,
        },
        "correctness": {
            "all_inputs_finite": True,
            "all_reference_winners_inside_all_survivor_sets": all(
                row["reference_winner_inside_all_survivor_sets"] for row in rows
            ),
            "exact_real_dense_winner_certified_from_cpu_interval": (
                exact_real_winner_certified
            ),
            "stock_bf16_dense_winner_certified_from_cpu_interval": (
                stock_winner_certified_from_cpu
            ),
            "reference_top1_ids_sha256": hashlib.sha256(
                reference_ids.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
            "minimum_reference_margin": float(
                (reference_values - reference_runner_up).min().item()
            ),
            "skipped_row_certificate": "For every inactive row, its conservative stock upper bound is strictly below a feasible incumbent row's conservative stock lower bound.",
        },
        "sweep": rows,
        "best_oracle_stock_bf16": {
            "selected_dimensions": best_oracle_stock["selected_dimensions"],
            **best_oracle_stock["oracle_incumbent_stock_bf16"],
        },
        "best_implementable_stock_bf16": {
            "selected_dimensions": best_implementable_stock[
                "selected_dimensions"
            ],
            **best_implementable_stock["implementable_seed_stock_bf16"],
        },
        "timing": {
            "weight_stats_and_tensor_hash_seconds": stats_seconds,
            "coordinate_sweep_seconds": sweep_seconds,
            "total_cpu_reference_seconds": time.monotonic() - started,
            "cpu_threads": torch.get_num_threads(),
            "cpu_count": os.cpu_count(),
            "performance_scope": "diagnostic CPU runtime only; not transferable to H200",
        },
        "resource_use": {
            "provider_spend_usd": 0.0,
            "gpu_claimed": False,
            "gpu_invocations": 0,
            "provider_mutation": False,
            "checkpoint_downloaded": False,
            "shared_checkpoint_read_only": True,
        },
        "interpretation": {
            "promotion_gate_physical_weight_bytes_avoided_fraction": 0.20,
            "component_only": True,
            "endpoint_speed_claim": False,
            "transfer_limit": "The result measures certified row/byte pruning for one deterministic real row per request. It does not measure H200 traversal, gather, dispatch, or endpoint latency.",
        },
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "decision": decision,
                "sample_rows": queries,
                "best_oracle_stock_avoided_fraction": result[
                    "best_oracle_stock_bf16"
                ]["physical_weight_bytes_avoided_fraction"],
                "best_implementable_stock_avoided_fraction": result[
                    "best_implementable_stock_bf16"
                ]["physical_weight_bytes_avoided_fraction"],
                "total_seconds": result["timing"]["total_cpu_reference_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
