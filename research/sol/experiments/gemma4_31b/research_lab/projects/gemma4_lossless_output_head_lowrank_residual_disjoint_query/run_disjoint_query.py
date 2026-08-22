#!/usr/bin/env python3
"""Evaluate a frozen low-rank output-head index on disjoint exact queries."""
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


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def raw_tensor_sha256(tensor) -> str:
    return hashlib.sha256(
        tensor.contiguous().view(dtype=__import__("torch").uint8).numpy().tobytes()
    ).hexdigest()


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


def provenance_row(payload: dict[str, Any], storage_index: int) -> dict[str, Any]:
    row = payload["ownership"][storage_index]
    global_row = int(row["global_row"])
    return {
        "storage_index": storage_index,
        "global_row": global_row,
        "request_id": str(row["request_id"]),
        "capture_index": int(row["capture_index"]),
        "depth_index": int(row["depth_index"]),
        "position": int(payload["positions"][global_row].item()),
        "hidden_row_sha256": raw_tensor_sha256(payload["hidden_states"][storage_index]),
    }


def select_disjoint_rows(payload: dict[str, Any]) -> tuple[list[int], list[int]]:
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
    grouped: dict[str, list[int]] = {}
    request_order: list[str] = []
    for index, row in enumerate(ownership):
        request_id = str(row["request_id"])
        if request_id not in grouped:
            grouped[request_id] = []
            request_order.append(request_id)
        grouped[request_id].append(index)
    if len(request_order) != REQUESTS:
        raise RuntimeError("capture_request_count_mismatch")
    if any(len(grouped[request_id]) < 2 for request_id in request_order):
        raise RuntimeError("capture_lacks_second_row_for_request")
    fit_evaluation = [grouped[request_id][0] for request_id in request_order]
    held_out = [grouped[request_id][1] for request_id in request_order]
    return fit_evaluation, held_out


def traffic(rank: int, union_rows: int, logical_rows: int) -> dict[str, int]:
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    started = time.monotonic()
    torch.set_num_threads(min(16, torch.get_num_threads()))
    contract = json.loads(args.contract.read_text())
    deadline = parse_deadline(contract["absolute_deadline_utc"])
    require_before(deadline, "identity_validation")
    input_dir = args.project_dir / "inputs"
    index_path = args.project_dir / "artifacts" / "frozen_lowrank_index.pt"
    paths = {
        "capture": input_dir / "hidden_states.pt",
        "capture_terminal": input_dir / "EXACT_CAPTURE_TERMINAL.json",
        "weight_shard": input_dir / "model-00001-of-00002.safetensors",
        "checkpoint_index": input_dir / "model.safetensors.index.json",
        "config": input_dir / "config.json",
        "frozen_index": index_path,
    }
    expected = contract["inputs"]
    identity_started = time.monotonic()
    identities = {
        name: sha256_file(path)
        for name, path in paths.items()
        if name != "weight_shard"
    }
    for name, expected_field in (
        ("capture", "capture_sha256"),
        ("capture_terminal", "capture_terminal_sha256"),
        ("checkpoint_index", "checkpoint_index_sha256"),
        ("config", "config_sha256"),
        ("frozen_index", "frozen_index_sha256"),
    ):
        if identities[name] != expected[expected_field]:
            raise RuntimeError(f"{name}_hash_mismatch")
    if sha256_file(paths["weight_shard"]) != expected["weight_shard_sha256"]:
        raise RuntimeError("weight_shard_hash_mismatch")
    identities["weight_shard"] = expected["weight_shard_sha256"]

    config = json.loads(paths["config"].read_text())
    checkpoint_index = json.loads(paths["checkpoint_index"].read_text())
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

    index = torch.load(index_path, map_location="cpu", weights_only=True, mmap=True)
    rank = int(index["rank"])
    basis = index["basis"]
    coefficients = index["coefficients"]
    residual_norm_upper = index["residual_norm_upper"]
    if (
        rank != 32
        or tuple(basis.shape) != (rank, HIDDEN)
        or tuple(coefficients.shape) != (VOCAB, rank)
        or tuple(residual_norm_upper.shape) != (VOCAB,)
        or str(basis.dtype) != "torch.float64"
        or str(coefficients.dtype) != "torch.float64"
        or str(residual_norm_upper.dtype) != "torch.float64"
        or not all(
            bool(torch.isfinite(value).all())
            for value in (basis, coefficients, residual_norm_upper)
        )
        or str(index["tied_weight_tensor_sha256"])
        != expected["tied_weight_tensor_sha256"]
        or str(index["capture_sha256"]) != expected["capture_sha256"]
    ):
        raise RuntimeError("frozen_index_identity_geometry_or_finiteness_mismatch")

    payload = torch.load(
        paths["capture"], map_location="cpu", weights_only=True, mmap=True
    )
    fit_indices, held_out_indices = select_disjoint_rows(payload)
    fit_provenance = [provenance_row(payload, index) for index in fit_indices]
    held_out_provenance = [
        provenance_row(payload, index) for index in held_out_indices
    ]
    fit_storage = {row["storage_index"] for row in fit_provenance}
    held_out_storage = {row["storage_index"] for row in held_out_provenance}
    fit_global = {row["global_row"] for row in fit_provenance}
    held_out_global = {row["global_row"] for row in held_out_provenance}
    fit_ownership = {
        (
            row["request_id"],
            row["capture_index"],
            row["depth_index"],
            row["global_row"],
        )
        for row in fit_provenance
    }
    held_out_ownership = {
        (
            row["request_id"],
            row["capture_index"],
            row["depth_index"],
            row["global_row"],
        )
        for row in held_out_provenance
    }
    fit_row_hashes = {row["hidden_row_sha256"] for row in fit_provenance}
    held_out_row_hashes = {row["hidden_row_sha256"] for row in held_out_provenance}
    disjointness = {
        "selection_rule": "second capture-order row for every request in first-seen request order",
        "predecessor_fit_evaluation_rule": "first capture-order row for every request in first-seen request order",
        "fit_evaluation_rows": len(fit_provenance),
        "held_out_rows": len(held_out_provenance),
        "storage_indices_disjoint": fit_storage.isdisjoint(held_out_storage),
        "global_rows_disjoint": fit_global.isdisjoint(held_out_global),
        "ownership_tuples_disjoint": fit_ownership.isdisjoint(held_out_ownership),
        "hidden_bf16_row_hashes_disjoint": fit_row_hashes.isdisjoint(
            held_out_row_hashes
        ),
        "fit_evaluation_provenance_sha256": sha256_json(fit_provenance),
        "held_out_provenance_sha256": sha256_json(held_out_provenance),
    }
    if not (
        len(fit_storage) == REQUESTS
        and len(held_out_storage) == REQUESTS
        and len(fit_global) == REQUESTS
        and len(held_out_global) == REQUESTS
        and len(fit_ownership) == REQUESTS
        and len(held_out_ownership) == REQUESTS
        and len(fit_row_hashes) == REQUESTS
        and len(held_out_row_hashes) == REQUESTS
        and all(
            disjointness[field]
            for field in (
                "storage_indices_disjoint",
                "global_rows_disjoint",
                "ownership_tuples_disjoint",
                "hidden_bf16_row_hashes_disjoint",
            )
        )
    ):
        raise RuntimeError("held_out_rows_not_proven_disjoint")
    if [row["global_row"] for row in fit_provenance] != contract[
        "stock_control"
    ]["predecessor_fit_evaluation_global_rows"]:
        raise RuntimeError("predecessor_fit_evaluation_selection_mismatch")
    if [row["global_row"] for row in held_out_provenance] != contract[
        "candidate"
    ]["held_out_global_rows"]:
        raise RuntimeError("held_out_selection_mismatch")

    hidden = payload["hidden_states"][held_out_indices].contiguous()
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

    require_before(deadline, "scientific_discriminator")
    science_started_at = datetime.now(timezone.utc).isoformat()
    scan_started = time.monotonic()
    with safe_open(paths["weight_shard"], framework="pt", device="cpu") as handle:
        if WEIGHT_KEY not in handle.keys():
            raise RuntimeError("tied_weight_key_absent")
        weight = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError("tied_weight_geometry_or_dtype_mismatch")
    full_scores = torch.empty((REQUESTS, VOCAB), dtype=torch.float32)
    exact_weight_norm = torch.empty(VOCAB, dtype=torch.float64)
    tensor_digest = hashlib.sha256()
    row_chunk = 2048
    for row_start in range(0, VOCAB, row_chunk):
        require_before(deadline, "weight_scan")
        row_end = min(VOCAB, row_start + row_chunk)
        block_bf16 = weight[row_start:row_end].contiguous()
        tensor_digest.update(block_bf16.view(torch.uint8).numpy().tobytes())
        block_float = block_bf16.float()
        full_scores[:, row_start:row_end] = hidden.float() @ block_float.T
        exact_weight_norm[row_start:row_end] = torch.linalg.vector_norm(
            block_float.double(), dim=1
        )
    tied_weight_tensor_sha256 = tensor_digest.hexdigest()
    if tied_weight_tensor_sha256 != expected["tied_weight_tensor_sha256"]:
        raise RuntimeError("tied_weight_tensor_hash_mismatch")

    exact_stock_error = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * exact_weight_norm[None, :]
    )
    exact_stock_error = exact_stock_error + exact_stock_error
    exact_stock_error = exact_stock_error + (
        (2.0**-8 / (1.0 - 2.0**-8))
        * (
            qnorm[:, None] * exact_weight_norm[None, :]
            + gamma(HIDDEN, 2.0**-24)
            * (qnorm[:, None] * exact_weight_norm[None, :])
        )
    )
    allowed = torch.ones(VOCAB, dtype=torch.bool)
    allowed[[1, 106]] = False
    dense_lower, _ = (
        full_scores.double() - exact_stock_error
    ).masked_fill(~allowed[None, :], float("-inf")).max(dim=1)
    possible_stock_candidates = (
        full_scores.double() + exact_stock_error
    ) >= dense_lower[:, None]
    possible_stock_candidates[:, 1] = False
    dense_reference_ids = full_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    ).argmax(dim=1)

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
    runtime_stock_accumulation = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * runtime_weight_norm_upper[None, :]
    )
    runtime_stock_error = (
        runtime_stock_accumulation
        + runtime_stock_accumulation
        + (
            (2.0**-8 / (1.0 - 2.0**-8))
            * (
                qnorm[:, None] * runtime_weight_norm_upper[None, :]
                + runtime_stock_accumulation
            )
        )
    )
    conservative_upper = (
        projected_scores
        + qresidual_upper[:, None] * residual_norm_upper[None, :]
        + projected_dot_error
        + basis_defect
        + runtime_stock_error
    )
    seed_ids = projected_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    ).argmax(dim=1)
    seed_scores = full_scores[
        torch.arange(REQUESTS, dtype=torch.int64), seed_ids
    ].double()
    seed_errors = runtime_stock_error[
        torch.arange(REQUESTS, dtype=torch.int64), seed_ids
    ]
    seed_lower = seed_scores - seed_errors
    survivors = conservative_upper >= seed_lower[:, None]
    survivors[:, 1] = False
    stock_set_inside = bool((survivors | ~possible_stock_candidates).all())
    dense_inside = bool(
        survivors[
            torch.arange(REQUESTS, dtype=torch.int64), dense_reference_ids
        ].all()
    )
    union = survivors.any(dim=0)
    union_rows = int(union.sum())
    logical_rows = int(survivors.sum())
    charged_traffic = traffic(rank, union_rows, logical_rows)
    net_fraction = (
        charged_traffic["net_bytes_saved"] / charged_traffic["dense_weight_bytes"]
    )
    candidate_exact_ids = full_scores.masked_fill(
        ~(survivors & allowed[None, :]), float("-inf")
    ).argmax(dim=1)
    candidate_matches_dense = bool((candidate_exact_ids == dense_reference_ids).all())
    exact_set_pass = stock_set_inside and dense_inside and candidate_matches_dense
    net_positive = net_fraction > 0
    promote = exact_set_pass and net_positive
    if not exact_set_pass:
        classification = (
            "typed_falsification_frozen_lowrank_disjoint_stock_set_containment_failed"
        )
    elif not net_positive:
        classification = (
            "typed_falsification_frozen_lowrank_disjoint_net_physical_traffic_nonpositive"
        )
    else:
        classification = (
            "typed_reference_positive_frozen_lowrank_disjoint_exact_stock_set_and_net_physical_traffic"
        )
    result = {
        "schema_version": 1,
        "classification": classification,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "question": contract["question"],
        "identities": {
            **identities,
            "tied_weight_tensor": tied_weight_tensor_sha256,
            "contract": sha256_file(args.contract),
            "runner": sha256_file(Path(__file__).resolve()),
            "predecessor_terminal": expected["predecessor_terminal_sha256"],
        },
        "geometry": {
            "model": contract["stock_control"]["model"],
            "revision": contract["stock_control"]["revision"],
            "weight_key": WEIGHT_KEY,
            "weight_shape": [VOCAB, HIDDEN],
            "weight_dtype": str(weight.dtype),
            "capture_shape": list(payload["hidden_states"].shape),
            "capture_dtype": str(payload["hidden_states"].dtype),
            "requests": REQUESTS,
            "held_out_rows": REQUESTS,
            "fit_evaluation_provenance": fit_provenance,
            "held_out_provenance": held_out_provenance,
        },
        "disjointness": disjointness,
        "frozen_mechanism": {
            "name": "fixed_query_span_lowrank_residual_index",
            "rank": rank,
            "basis_and_index_tuned_after_holdout": False,
            "held_out_selection_tuned_after_result": False,
            "basis_gram_spectral_error": gram_error,
            "query_residual_norm_max": float(qresidual_upper.max()),
            "query_residual_norm_mean": float(qresidual_upper.mean()),
            "runtime_weight_norm_derivation": "coefficient_norm*basis_operator_norm + residual_norm_upper",
            "runtime_weight_norm_is_conservative_by_triangle_inequality": True,
        },
        "stock_consumer": contract["stock_control"]["stock_consumer"],
        "correctness": {
            "all_inputs_finite": True,
            "possible_stock_candidate_rows_mean": float(
                possible_stock_candidates.sum(dim=1).double().mean()
            ),
            "possible_stock_candidate_rows_max": int(
                possible_stock_candidates.sum(dim=1).max()
            ),
            "possible_stock_candidate_set_sha256": raw_tensor_sha256(
                possible_stock_candidates
            ),
            "survivor_set_sha256": raw_tensor_sha256(survivors),
            "stock_candidate_set_inside_all_survivor_sets": stock_set_inside,
            "dense_reference_winner_inside_all_survivor_sets": dense_inside,
            "candidate_exact_winners_match_dense_reference": candidate_matches_dense,
            "dense_reference_ids_sha256": raw_tensor_sha256(
                dense_reference_ids.to(torch.int32)
            ),
            "candidate_exact_ids_sha256": raw_tensor_sha256(
                candidate_exact_ids.to(torch.int32)
            ),
            "seed_incumbent_ids_sha256": raw_tensor_sha256(
                seed_ids.to(torch.int32)
            ),
        },
        "physical_result": {
            "logical_survivor_rows": logical_rows,
            "physical_union_survivor_rows": union_rows,
            "physical_union_survivor_fraction": union_rows / VOCAB,
            "gross_physical_member_weight_bytes_avoided_fraction": (
                1.0
                - charged_traffic["member_weight_bytes"]
                / charged_traffic["dense_weight_bytes"]
            ),
            "net_physical_bytes_avoided_fraction": net_fraction,
            "traffic": charged_traffic,
            "accounting_scope": "32-row physical union with projected index, basis, residual metadata, query projection, score and bound buffers, survivor materialization, exact BF16 member weights, and exact logits fully charged",
        },
        "decision": {
            "exact_stock_set_pass": exact_set_pass,
            "net_physical_traffic_positive": net_positive,
            "promote_to_h200_component": promote,
            "reason": (
                "The frozen rank-32 index passed the disjoint exact-stock-set and fully charged net physical traffic gates."
                if promote
                else (
                    "The frozen rank-32 index failed exact stock-set preservation on the preregistered disjoint rows."
                    if not exact_set_pass
                    else "The frozen rank-32 index preserved the exact stock set but did not reduce fully charged net physical traffic on the preregistered disjoint rows."
                )
            ),
        },
        "timing": {
            "identity_seconds": scan_started - identity_started,
            "weight_scan_and_discriminator_seconds": time.monotonic() - scan_started,
            "total_cpu_reference_seconds": time.monotonic() - started,
            "science_started_at_utc": science_started_at,
            "cpu_threads": torch.get_num_threads(),
        },
        "resource_use": {
            "actual_spend_usd": 0.0,
            "gpu_claimed": False,
            "gpu_invocations": 0,
            "provider_mutation": False,
            "endpoint_traffic": False,
            "shared_inputs_read_only": True,
        },
        "scope_and_limits": {
            "measured": "CPU/reference exact-stock-set containment and fully charged analytical physical traffic on 32 preregistered disjoint exact-capture rows.",
            "not_claimed": "H200 latency, endpoint speed, quality beyond exact stock semantics, or production economics.",
            "next_gate": (
                "One exact-consumer target-H200 component."
                if promote
                else "Close this frozen rank-32 transfer representation and choose a materially different output-head mechanism."
            ),
        },
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "classification": classification,
                "stock_set_certified": exact_set_pass,
                "union_rows": union_rows,
                "net_avoided_fraction": net_fraction,
                "promote_to_h200_component": promote,
                "total_seconds": result["timing"]["total_cpu_reference_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
