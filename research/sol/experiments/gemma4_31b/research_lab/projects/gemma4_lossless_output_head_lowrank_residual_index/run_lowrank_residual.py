#!/usr/bin/env python3
"""Evaluate one conservative query-span low-rank output-head index."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VOCAB = 262144
HIDDEN = 5376
REQUESTS = 32
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
EXPECTED_TENSOR_SHA256 = (
    "1053f051b1b894bb5f80eb52cdd434b8028aaad27c3006fcfdec48ac8c46d98d"
)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def gamma(operations: int, unit_roundoff: float) -> float:
    product = operations * unit_roundoff
    if product >= 1:
        raise RuntimeError("roundoff_bound_undefined")
    return product / (1.0 - product)


def parse_deadline(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_before(deadline: datetime, phase: str) -> None:
    if datetime.now(timezone.utc) >= deadline:
        raise TimeoutError(f"absolute_deadline_reached_before_{phase}")


def select_capture_rows(payload: dict[str, Any]):
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
    seen: set[str] = set()
    for index, row in enumerate(ownership):
        request_id = str(row["request_id"])
        if request_id not in seen:
            selected.append(index)
            seen.add(request_id)
    if len(selected) != REQUESTS:
        raise RuntimeError("capture_selection_incomplete")
    return hidden[selected].contiguous(), [ownership[index] for index in selected]


def arm_result(
    name: str,
    lower,
    upper,
    possible_winners,
    dense_reference_ids,
    rank: int,
) -> dict[str, Any]:
    import torch

    survivors = upper >= lower[:, None]
    survivors[:, 1] = False
    possible_inside = bool((survivors | ~possible_winners).all().item())
    dense_inside = bool(
        survivors[
            torch.arange(REQUESTS, dtype=torch.int64), dense_reference_ids
        ].all()
    )
    union = survivors.any(dim=0)
    union_rows = int(union.sum().item())
    logical_rows = int(survivors.sum().item())
    dense_weight_bytes = VOCAB * HIDDEN * 2
    member_weight_bytes = union_rows * HIDDEN * 2
    projected_weight_bytes = VOCAB * rank * 8
    residual_norm_bytes = VOCAB * 8
    basis_bytes = rank * HIDDEN * 8
    query_input_bytes = REQUESTS * HIDDEN * 2
    query_coefficient_bytes = REQUESTS * rank * 8
    projected_score_output_bytes = REQUESTS * VOCAB * 8
    residual_bound_read_write_bytes = 2 * projected_score_output_bytes
    survivor_mask_bytes = REQUESTS * VOCAB
    survivor_token_id_bytes = logical_rows * 4
    exact_logit_bytes = logical_rows * 8
    candidate_total_bytes = sum(
        (
            member_weight_bytes,
            projected_weight_bytes,
            residual_norm_bytes,
            basis_bytes,
            query_input_bytes,
            query_coefficient_bytes,
            projected_score_output_bytes,
            residual_bound_read_write_bytes,
            survivor_mask_bytes,
            survivor_token_id_bytes,
            exact_logit_bytes,
        )
    )
    return {
        "name": name,
        "stock_candidate_set_inside_survivors": possible_inside,
        "dense_reference_winner_inside_survivors": dense_inside,
        "logical_survivor_rows": logical_rows,
        "logical_survivor_fraction": logical_rows / (REQUESTS * VOCAB),
        "physical_union_survivor_rows": union_rows,
        "physical_union_survivor_fraction": union_rows / VOCAB,
        "gross_physical_member_weight_bytes_avoided_fraction": (
            1.0 - member_weight_bytes / dense_weight_bytes
        ),
        "net_physical_bytes_avoided_fraction": (
            1.0 - candidate_total_bytes / dense_weight_bytes
        ),
        "traffic": {
            "dense_weight_bytes": dense_weight_bytes,
            "member_weight_bytes": member_weight_bytes,
            "projected_weight_index_bytes": projected_weight_bytes,
            "residual_norm_metadata_bytes": residual_norm_bytes,
            "basis_bytes": basis_bytes,
            "query_input_bytes": query_input_bytes,
            "query_coefficient_bytes": query_coefficient_bytes,
            "projected_score_output_bytes": projected_score_output_bytes,
            "residual_bound_read_write_bytes": residual_bound_read_write_bytes,
            "survivor_mask_bytes": survivor_mask_bytes,
            "survivor_token_id_bytes": survivor_token_id_bytes,
            "exact_logit_bytes": exact_logit_bytes,
            "candidate_total_bytes": candidate_total_bytes,
            "net_bytes_saved": dense_weight_bytes - candidate_total_bytes,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--spectrum-output", type=Path, required=True)
    parser.add_argument("--index-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    started = time.monotonic()
    torch.set_num_threads(min(16, torch.get_num_threads()))
    contract = json.loads(args.contract.read_text())
    deadline = parse_deadline(contract["absolute_deadline_utc"])
    require_before(deadline, "identity_validation")
    paths = {
        "capture": args.input_dir / "hidden_states.pt",
        "capture_terminal": args.input_dir / "EXACT_CAPTURE_TERMINAL.json",
        "weight_shard": args.input_dir / "model-00001-of-00002.safetensors",
        "index": args.input_dir / "model.safetensors.index.json",
        "config": args.input_dir / "config.json",
    }
    identities = {
        name: sha256_file(paths[name])
        for name in ("capture", "capture_terminal", "index", "config")
    }
    expected = contract["inputs"]
    for name, field in (
        ("capture", "capture_sha256"),
        ("capture_terminal", "capture_terminal_sha256"),
        ("index", "checkpoint_index_sha256"),
        ("config", "config_sha256"),
    ):
        if identities[name] != expected[field]:
            raise RuntimeError(f"{name}_hash_mismatch")
    config = json.loads(paths["config"].read_text())
    checkpoint_index = json.loads(paths["index"].read_text())
    text_config = config["text_config"]
    if (
        text_config["hidden_size"] != HIDDEN
        or text_config["vocab_size"] != VOCAB
        or not text_config["tie_word_embeddings"]
        or text_config["final_logit_softcapping"] != 30.0
        or checkpoint_index["weight_map"].get(WEIGHT_KEY)
        != paths["weight_shard"].name
    ):
        raise RuntimeError("pinned_model_geometry_or_mapping_mismatch")

    payload = torch.load(
        paths["capture"], map_location="cpu", weights_only=True, mmap=True
    )
    hidden, selected_ownership = select_capture_rows(payload)
    hidden_double = hidden.double()
    spectrum_started = time.monotonic()
    _, singular_values, basis = torch.linalg.svd(
        hidden_double, full_matrices=False
    )
    tolerance = (
        float(singular_values.max())
        * torch.finfo(torch.float64).eps
        * max(hidden_double.shape)
    )
    rank = int((singular_values > tolerance).sum().item())
    if rank < 1 or rank > REQUESTS:
        raise RuntimeError("query_span_rank_invalid")
    basis = basis[:rank].contiguous()
    gram = basis @ basis.T
    gram_error = float(
        torch.linalg.matrix_norm(
            gram - torch.eye(rank, dtype=torch.float64), ord=2
        )
    )
    basis_operator_norm = float(torch.linalg.matrix_norm(basis, ord=2))
    singular_energy = singular_values.square()
    cumulative_energy = singular_energy.cumsum(0) / singular_energy.sum()
    qcoeff = hidden_double @ basis.T
    qreconstruction = qcoeff @ basis
    qresidual = hidden_double - qreconstruction
    qnorm = torch.linalg.vector_norm(hidden_double, dim=1)
    qcoeff_norm = torch.linalg.vector_norm(qcoeff, dim=1)
    qreconstruction_norm = torch.linalg.vector_norm(qreconstruction, dim=1)
    qresidual_norm = torch.linalg.vector_norm(qresidual, dim=1)
    eps64 = torch.finfo(torch.float64).eps
    subtraction_scale = 64.0 * eps64 * math.sqrt(HIDDEN)
    qresidual_upper = qresidual_norm + subtraction_scale * (
        qnorm + qreconstruction_norm
    )

    with safe_open(paths["weight_shard"], framework="pt", device="cpu") as handle:
        if WEIGHT_KEY not in handle.keys():
            raise RuntimeError("tied_weight_key_absent")
        weight = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError("tied_weight_geometry_or_dtype_mismatch")

    coefficients = torch.empty((VOCAB, rank), dtype=torch.float64)
    residual_norm_upper = torch.empty(VOCAB, dtype=torch.float64)
    weight_norm = torch.empty(VOCAB, dtype=torch.float64)
    coefficient_norm = torch.empty(VOCAB, dtype=torch.float64)
    full_scores = torch.empty((REQUESTS, VOCAB), dtype=torch.float32)
    tensor_digest = hashlib.sha256()
    scan_started = time.monotonic()
    row_chunk = 2048
    for row_start in range(0, VOCAB, row_chunk):
        require_before(deadline, "weight_scan")
        row_end = min(VOCAB, row_start + row_chunk)
        block_bf16 = weight[row_start:row_end].contiguous()
        tensor_digest.update(block_bf16.view(torch.uint8).numpy().tobytes())
        block_float = block_bf16.float()
        full_scores[:, row_start:row_end] = hidden.float() @ block_float.T
        block = block_float.double()
        block_coefficients = block @ basis.T
        block_reconstruction = block_coefficients @ basis
        block_residual = block - block_reconstruction
        block_norm = torch.linalg.vector_norm(block, dim=1)
        reconstruction_norm = torch.linalg.vector_norm(
            block_reconstruction, dim=1
        )
        coefficients[row_start:row_end] = block_coefficients
        coefficient_norm[row_start:row_end] = torch.linalg.vector_norm(
            block_coefficients, dim=1
        )
        weight_norm[row_start:row_end] = block_norm
        residual_norm_upper[row_start:row_end] = torch.linalg.vector_norm(
            block_residual, dim=1
        ) + subtraction_scale * (block_norm + reconstruction_norm)
    observed_tensor_digest = tensor_digest.hexdigest()
    if observed_tensor_digest != EXPECTED_TENSOR_SHA256:
        raise RuntimeError("tied_weight_tensor_hash_mismatch")

    require_before(deadline, "oracle_discriminator")
    fp32_error = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * weight_norm[None, :]
    )
    stock_accumulation = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * weight_norm[None, :]
    )
    bfloat16_roundoff = 2.0**-8
    stock_output_rounding = (
        bfloat16_roundoff
        / (1.0 - bfloat16_roundoff)
        * (
            qnorm[:, None] * weight_norm[None, :]
            + stock_accumulation
        )
    )
    stock_total_error = fp32_error + stock_accumulation + stock_output_rounding
    lower_matrix = full_scores.double() - stock_total_error
    upper_matrix = full_scores.double() + stock_total_error
    allowed = torch.ones(VOCAB, dtype=torch.bool)
    allowed[[1, 106]] = False
    oracle_lower, oracle_ids = lower_matrix.masked_fill(
        ~allowed[None, :], float("-inf")
    ).max(dim=1)
    possible_winners = upper_matrix >= oracle_lower[:, None]
    possible_winners[:, 1] = False
    dense_reference_ids = full_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    ).argmax(dim=1)

    projected_scores = qcoeff @ coefficients.T
    projected_dot_error = gamma(rank, eps64) * (
        qcoeff_norm[:, None] * coefficient_norm[None, :]
    )
    basis_defect = (
        qnorm[:, None]
        * weight_norm[None, :]
        * basis_operator_norm**2
        * gram_error
    )
    conservative_upper = (
        projected_scores
        + qresidual_upper[:, None] * residual_norm_upper[None, :]
        + projected_dot_error
        + basis_defect
        + stock_total_error
    )
    oracle = arm_result(
        "optimistic_oracle_incumbent",
        oracle_lower,
        conservative_upper,
        possible_winners,
        dense_reference_ids,
        rank,
    )
    discriminator_pass = (
        oracle["gross_physical_member_weight_bytes_avoided_fraction"] >= 0.10
    )
    spectrum = {
        "schema_version": 1,
        "classification": (
            "lowrank_oracle_gross_union_gate_pass"
            if discriminator_pass
            else "typed_falsification_lowrank_oracle_gross_union_below_10_percent"
        ),
        "rank": rank,
        "rank_fraction_of_hidden": rank / HIDDEN,
        "singular_values": [float(value) for value in singular_values],
        "cumulative_energy": [float(value) for value in cumulative_energy],
        "basis_gram_spectral_error": gram_error,
        "query_residual_norm_max": float(qresidual_upper.max()),
        "oracle": oracle,
        "gate": {
            "required_gross_union_avoidance_fraction": 0.10,
            "passed": discriminator_pass,
        },
        "timing": {
            "spectrum_seconds": scan_started - spectrum_started,
            "weight_scan_and_bound_seconds": time.monotonic() - scan_started,
        },
    }
    atomic_json(args.spectrum_output, spectrum)

    if not discriminator_pass:
        result = {
            "schema_version": 1,
            "classification": "typed_falsification_lowrank_oracle_union_too_dense",
            "discriminator": spectrum,
            "index_persisted": False,
            "resource_use": {
                "actual_spend_usd": 0.0,
                "gpu_claimed": False,
                "gpu_invocations": 0,
                "provider_mutation": False,
            },
            "total_cpu_reference_seconds": time.monotonic() - started,
        }
        atomic_json(args.output, result)
        return 0

    require_before(deadline, "index_persistence")
    index_payload = {
        "schema_version": 1,
        "rank": rank,
        "basis": basis,
        "coefficients": coefficients,
        "residual_norm_upper": residual_norm_upper,
        "tied_weight_tensor_sha256": observed_tensor_digest,
        "capture_sha256": identities["capture"],
    }
    temporary_index = args.index_output.with_suffix(".pt.tmp")
    torch.save(index_payload, temporary_index)
    temporary_index.replace(args.index_output)
    index_sha256 = sha256_file(args.index_output)

    seed_ids = projected_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    ).argmax(dim=1)
    seed_lower = lower_matrix[
        torch.arange(REQUESTS, dtype=torch.int64), seed_ids
    ]
    implementable = arm_result(
        "implementable_projected_seed_incumbent",
        seed_lower,
        conservative_upper,
        possible_winners,
        dense_reference_ids,
        rank,
    )
    correctness = all(
        (
            oracle["stock_candidate_set_inside_survivors"],
            oracle["dense_reference_winner_inside_survivors"],
            implementable["stock_candidate_set_inside_survivors"],
            implementable["dense_reference_winner_inside_survivors"],
        )
    )
    net_positive = implementable["net_physical_bytes_avoided_fraction"] > 0
    promote = correctness and net_positive
    if not correctness:
        decision = "typed_falsification_lowrank_stock_set_containment_failed"
    elif not net_positive:
        decision = "typed_falsification_lowrank_net_physical_traffic_nonpositive"
    else:
        decision = "reference_positive_lowrank_net_traffic_in_sample"
    inherited_head_seconds = (
        contract["slo"]["campaign_denominator_seconds_per_request"]
        * contract["slo"]["inherited_output_consumer_interval_fraction"]
    )
    net_fraction = implementable["net_physical_bytes_avoided_fraction"]
    result = {
        "schema_version": 1,
        "classification": "lossless_output_head_lowrank_residual_reference_terminal",
        "decision": decision,
        "promote": promote,
        "identities": {
            **identities,
            "weight_shard": expected["weight_shard_sha256"],
            "tied_weight_tensor": observed_tensor_digest,
            "contract": sha256_file(args.contract),
            "runner": sha256_file(Path(__file__).resolve()),
            "index": index_sha256,
        },
        "geometry": {
            "model": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "weight_key": WEIGHT_KEY,
            "weight_shape": [VOCAB, HIDDEN],
            "weight_dtype": str(weight.dtype),
            "capture_shape": list(payload["hidden_states"].shape),
            "capture_dtype": str(payload["hidden_states"].dtype),
            "sample_rows": REQUESTS,
            "requests": REQUESTS,
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
        },
        "stock_consumer": {
            "classification": "pinned_temperature_zero_greedy_with_min_token_stop_mask",
            "softcap": "30 * tanh(pre_softcap_logit / 30), monotone",
            "masked_stop_token_ids": [1],
            "conservatively_excluded_from_incumbents": [1, 106],
            "candidate_set_requirement": "Every possible non-stop argmax under the inherited conservative numeric envelope remains in the survivor set.",
            "stock_rounding_scope": "Guarded CPU FP32 reference error plus stock BF16 accumulation and BF16 output-rounding envelopes.",
        },
        "mechanism": {
            "name": "fixed_query_span_lowrank_residual_index",
            "rank": rank,
            "rank_fraction_of_hidden": rank / HIDDEN,
            "basis_training": "same 32 exact evaluation hidden rows",
            "basis_dtype": "torch.float64",
            "coefficient_dtype": "torch.float64",
            "layout": "original token-ID order; no tied-weight permutation or duplication",
            "bound": "projected dot + guarded query-residual times guarded row-residual norm + basis-idempotence defect + stock envelope",
            "all_vocabulary_rows_reachable": True,
        },
        "correctness": {
            "all_inputs_finite": True,
            "stock_candidate_set_inside_all_reported_survivor_sets": correctness,
            "possible_stock_candidate_rows_mean": float(
                possible_winners.sum(dim=1).double().mean()
            ),
            "possible_stock_candidate_rows_max": int(
                possible_winners.sum(dim=1).max()
            ),
            "dense_reference_ids_sha256": hashlib.sha256(
                dense_reference_ids.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
            "oracle_incumbent_ids_sha256": hashlib.sha256(
                oracle_ids.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
            "seed_incumbent_ids_sha256": hashlib.sha256(
                seed_ids.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
            "basis_gram_spectral_error": gram_error,
            "query_residual_norm_max": float(qresidual_upper.max()),
        },
        "results": {
            "oracle_discriminator": oracle,
            "implementable": implementable,
        },
        "storage": {
            "projected_weight_index_bytes": coefficients.numel() * 8,
            "residual_norm_metadata_bytes": residual_norm_upper.numel() * 8,
            "basis_bytes": basis.numel() * 8,
            "total_additional_runtime_storage_bytes": (
                coefficients.numel() * 8
                + residual_norm_upper.numel() * 8
                + basis.numel() * 8
            ),
            "tied_output_weight_storage_duplicated": False,
            "index_file_bytes": args.index_output.stat().st_size,
            "index_build_is_offline": True,
        },
        "economics": {
            "campaign_denominator_seconds_per_request": contract["slo"][
                "campaign_denominator_seconds_per_request"
            ],
            "campaign_target_seconds_per_request": contract["slo"][
                "campaign_target_seconds_per_request"
            ],
            "inherited_output_consumer_interval_fraction": contract["slo"][
                "inherited_output_consumer_interval_fraction"
            ],
            "inherited_output_consumer_seconds_per_request": inherited_head_seconds,
            "analytical_net_seconds_saved_upper_bound": inherited_head_seconds
            * net_fraction,
            "analytical_service_seconds_per_request_lower_bound": contract["slo"][
                "campaign_denominator_seconds_per_request"
            ]
            - inherited_head_seconds * net_fraction,
            "interpretation": "Byte-proportional analytical upper bound only; CPU timing and the in-sample query basis do not transfer to an endpoint.",
        },
        "timing": {
            **spectrum["timing"],
            "total_cpu_reference_seconds": time.monotonic() - started,
            "cpu_threads": torch.get_num_threads(),
            "performance_scope": "diagnostic CPU build and traversal only",
        },
        "resource_use": {
            "actual_spend_usd": 0.0,
            "provider_spend_usd": 0.0,
            "gpu_claimed": False,
            "gpu_invocations": 0,
            "provider_mutation": False,
            "shared_inputs_read_only": True,
        },
        "scope_and_limits": {
            "measured": "Exact-stock-set containment and analytical physical traffic on the same 32 rows.",
            "inferred": "A low-rank residual head can be physically favorable when the serving query distribution remains inside this learned span.",
            "not_claimed": "Held-out query pruning, H200 latency, endpoint speed, quality, or production economics.",
            "next_gate": "Disjoint-query reference validation before any target-H200 component.",
        },
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "decision": decision,
                "rank": rank,
                "oracle_gross_avoided_fraction": oracle[
                    "gross_physical_member_weight_bytes_avoided_fraction"
                ],
                "implementable_union_rows": implementable[
                    "physical_union_survivor_rows"
                ],
                "implementable_net_avoided_fraction": net_fraction,
                "stock_set_certified": correctness,
                "total_seconds": time.monotonic() - started,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
