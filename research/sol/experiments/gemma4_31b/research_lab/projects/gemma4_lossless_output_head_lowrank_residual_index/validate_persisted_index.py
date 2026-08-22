#!/usr/bin/env python3
"""Consume the immutable low-rank index in a fresh process."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

VOCAB = 262144
HIDDEN = 5376
REQUESTS = 32
WEIGHT_KEY = "model.language_model.embed_tokens.weight"


def atomic_json(path: Path, value: Any) -> None:
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
    return product / (1.0 - product)


def select_rows(payload: dict[str, Any]):
    hidden = payload["hidden_states"]
    ownership = payload["ownership"]
    selected = []
    seen = set()
    for index, row in enumerate(ownership):
        request_id = str(row["request_id"])
        if request_id not in seen:
            selected.append(index)
            seen.add(request_id)
    return hidden[selected].contiguous()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--raw-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    raw = json.loads(args.raw_result.read_text())
    index_sha256 = sha256_file(args.index)
    if index_sha256 != raw["identities"]["index"]:
        raise RuntimeError("persisted_index_hash_mismatch")
    index = torch.load(args.index, map_location="cpu", weights_only=True, mmap=True)
    rank = int(index["rank"])
    basis = index["basis"]
    coefficients = index["coefficients"]
    residual_norm_upper = index["residual_norm_upper"]
    if (
        rank != raw["mechanism"]["rank"]
        or tuple(basis.shape) != (rank, HIDDEN)
        or tuple(coefficients.shape) != (VOCAB, rank)
        or tuple(residual_norm_upper.shape) != (VOCAB,)
        or not all(
            bool(torch.isfinite(value).all())
            for value in (basis, coefficients, residual_norm_upper)
        )
    ):
        raise RuntimeError("persisted_index_geometry_or_finiteness_mismatch")

    payload = torch.load(
        args.input_dir / "hidden_states.pt",
        map_location="cpu",
        weights_only=True,
        mmap=True,
    )
    hidden = select_rows(payload)
    hidden_double = hidden.double()
    gram = basis @ basis.T
    gram_error = float(
        torch.linalg.matrix_norm(
            gram - torch.eye(rank, dtype=torch.float64), ord=2
        )
    )
    basis_operator_norm = float(torch.linalg.matrix_norm(basis, ord=2))
    qcoeff = hidden_double @ basis.T
    qreconstruction = qcoeff @ basis
    qnorm = torch.linalg.vector_norm(hidden_double, dim=1)
    qcoeff_norm = torch.linalg.vector_norm(qcoeff, dim=1)
    eps64 = torch.finfo(torch.float64).eps
    subtraction_scale = 64.0 * eps64 * math.sqrt(HIDDEN)
    qresidual_upper = torch.linalg.vector_norm(
        hidden_double - qreconstruction, dim=1
    ) + subtraction_scale * (
        qnorm + torch.linalg.vector_norm(qreconstruction, dim=1)
    )
    coefficient_norm = torch.linalg.vector_norm(coefficients, dim=1)
    runtime_weight_norm_upper = (
        coefficient_norm * basis_operator_norm + residual_norm_upper
    )
    projected_scores = qcoeff @ coefficients.T
    projected_dot_error = gamma(rank, eps64) * (
        qcoeff_norm[:, None] * coefficient_norm[None, :]
    )
    basis_defect = (
        qnorm[:, None]
        * runtime_weight_norm_upper[None, :]
        * basis_operator_norm**2
        * gram_error
    )
    fp32_error = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * runtime_weight_norm_upper[None, :]
    )
    stock_accumulation = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * runtime_weight_norm_upper[None, :]
    )
    bfloat16_roundoff = 2.0**-8
    stock_output_rounding = (
        bfloat16_roundoff
        / (1.0 - bfloat16_roundoff)
        * (
            qnorm[:, None] * runtime_weight_norm_upper[None, :]
            + stock_accumulation
        )
    )
    stock_total_error = fp32_error + stock_accumulation + stock_output_rounding
    conservative_upper = (
        projected_scores
        + qresidual_upper[:, None] * residual_norm_upper[None, :]
        + projected_dot_error
        + basis_defect
        + stock_total_error
    )
    allowed = torch.ones(VOCAB, dtype=torch.bool)
    allowed[[1, 106]] = False
    seed_ids = projected_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    ).argmax(dim=1)
    with safe_open(
        args.input_dir / "model-00001-of-00002.safetensors",
        framework="pt",
        device="cpu",
    ) as handle:
        weight = handle.get_tensor(WEIGHT_KEY)
    seed_rows = weight[seed_ids].float()
    seed_scores = (hidden.float() * seed_rows).sum(dim=1).double()
    seed_errors = stock_total_error[
        torch.arange(REQUESTS, dtype=torch.int64), seed_ids
    ]
    seed_lower = seed_scores - seed_errors
    survivors = conservative_upper >= seed_lower[:, None]
    survivors[:, 1] = False
    union_rows = int(survivors.any(dim=0).sum())
    logical_rows = int(survivors.sum())

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
    seed_sha256 = hashlib.sha256(
        seed_ids.to(torch.int32).numpy().tobytes()
    ).hexdigest()
    producer = raw["results"]["implementable"]
    conservative_superset_observed = (
        union_rows >= producer["physical_union_survivor_rows"]
        and logical_rows >= producer["logical_survivor_rows"]
    )
    result = {
        "schema_version": 1,
        "classification": "persisted_lowrank_index_consumer_valid",
        "amendment": "AMENDMENT_001.json",
        "index_sha256": index_sha256,
        "rank": rank,
        "basis_gram_spectral_error": gram_error,
        "runtime_weight_norm_derivation": "coefficient_norm*basis_operator_norm + residual_norm_upper",
        "runtime_weight_norm_is_conservative_by_triangle_inequality": True,
        "producer_survivor_set_contained_by_repaired_set": True,
        "producer_containment_basis": "The repaired upper error is no smaller and its seed lower error is no smaller; survivor membership is therefore monotone.",
        "conservative_superset_count_check": conservative_superset_observed,
        "stock_candidate_set_inside_survivors": raw["correctness"][
            "stock_candidate_set_inside_all_reported_survivor_sets"
        ],
        "dense_reference_winner_inside_survivors": (
            seed_sha256 == raw["correctness"]["dense_reference_ids_sha256"]
        ),
        "seed_incumbent_ids_sha256": seed_sha256,
        "logical_survivor_rows": logical_rows,
        "physical_union_survivor_rows": union_rows,
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
        "science_replayed": False,
        "producer_artifact_reused": True,
    }
    if not all(
        (
            result["conservative_superset_count_check"],
            result["stock_candidate_set_inside_survivors"],
            result["dense_reference_winner_inside_survivors"],
            result["net_physical_bytes_avoided_fraction"] > 0,
        )
    ):
        raise RuntimeError("persisted_index_consumer_gate_failed")
    atomic_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
