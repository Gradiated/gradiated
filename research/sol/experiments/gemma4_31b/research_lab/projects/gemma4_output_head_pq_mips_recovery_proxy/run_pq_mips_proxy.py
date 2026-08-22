#!/usr/bin/env python3
"""Build and evaluate one frozen product-quantized output-head index."""
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
SUBSPACE_DIMENSIONS = 2
SUBSPACES = HIDDEN // SUBSPACE_DIMENSIONS
SCALAR_LEVELS = 16
CODEBOOK_ROWS = SCALAR_LEVELS * SCALAR_LEVELS
WEIGHT_KEY = "model.language_model.embed_tokens.weight"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def atomic_torch_save(path: Path, value: Any, torch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        torch.save(value, temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


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


def raw_tensor_sha256(tensor, torch) -> str:
    byte_view = tensor.contiguous().view(torch.uint8)
    return hashlib.sha256(byte_view.numpy().tobytes()).hexdigest()


def parse_deadline(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_before(deadline: datetime, phase: str) -> None:
    if datetime.now(timezone.utc) >= deadline:
        raise TimeoutError(f"absolute_deadline_reached_before_{phase}")


def standard_normal_lloyd_max_levels() -> list[float]:
    normalizer = math.sqrt(2.0 * math.pi)

    def density(value: float) -> float:
        return math.exp(-0.5 * value * value) / normalizer

    def distribution(value: float) -> float:
        return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))

    levels = [
        -2.75,
        -2.10,
        -1.70,
        -1.40,
        -1.14,
        -0.90,
        -0.67,
        -0.44,
        0.44,
        0.67,
        0.90,
        1.14,
        1.40,
        1.70,
        2.10,
        2.75,
    ]
    for _ in range(128):
        boundaries = [
            -math.inf,
            *[(levels[index] + levels[index + 1]) / 2 for index in range(15)],
            math.inf,
        ]
        updated = []
        for lower, upper in zip(boundaries, boundaries[1:]):
            lower_density = 0.0 if math.isinf(lower) else density(lower)
            upper_density = 0.0 if math.isinf(upper) else density(upper)
            lower_mass = 0.0 if lower == -math.inf else distribution(lower)
            upper_mass = 1.0 if upper == math.inf else distribution(upper)
            updated.append((lower_density - upper_density) / (upper_mass - lower_mass))
        if max(abs(left - right) for left, right in zip(levels, updated)) < 1e-13:
            levels = updated
            break
        levels = updated
    return levels


def gamma(operations: int, unit_roundoff: float) -> float:
    product = operations * unit_roundoff
    if product >= 1:
        raise RuntimeError("roundoff_bound_undefined")
    return product / (1.0 - product)


def provenance_row(payload: dict[str, Any], storage_index: int, torch) -> dict[str, Any]:
    row = payload["ownership"][storage_index]
    global_row = int(row["global_row"])
    return {
        "storage_index": storage_index,
        "global_row": global_row,
        "request_id": str(row["request_id"]),
        "capture_index": int(row["capture_index"]),
        "depth_index": int(row["depth_index"]),
        "position": int(payload["positions"][global_row].item()),
        "hidden_row_sha256": raw_tensor_sha256(
            payload["hidden_states"][storage_index], torch
        ),
    }


def select_batches(payload: dict[str, Any], torch) -> tuple[list[list[int]], list[list[int]]]:
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
    if any(len(grouped[request_id]) < 4 for request_id in request_order):
        raise RuntimeError("capture_lacks_four_rows_per_request")
    prior = [
        [grouped[request_id][depth] for request_id in request_order]
        for depth in (0, 1)
    ]
    selected = [
        [grouped[request_id][depth] for request_id in request_order]
        for depth in (2, 3)
    ]
    return prior, selected


def disjointness_report(
    payload: dict[str, Any],
    prior_indices: list[list[int]],
    selected_indices: list[list[int]],
    torch,
) -> dict[str, Any]:
    named_sets = {
        "prior_fit_evaluation": prior_indices[0],
        "prior_held_out": prior_indices[1],
        "selected_batch_0": selected_indices[0],
        "selected_batch_1": selected_indices[1],
    }
    provenance = {
        name: [provenance_row(payload, index, torch) for index in indices]
        for name, indices in named_sets.items()
    }

    def identities(rows: list[dict[str, Any]], field: str) -> set[Any]:
        if field == "ownership":
            return {
                (
                    row["request_id"],
                    row["capture_index"],
                    row["depth_index"],
                    row["global_row"],
                )
                for row in rows
            }
        return {row[field] for row in rows}

    comparisons = {}
    names = list(named_sets)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            comparisons[f"{left}__{right}"] = {
                "storage_indices_disjoint": identities(
                    provenance[left], "storage_index"
                ).isdisjoint(identities(provenance[right], "storage_index")),
                "global_rows_disjoint": identities(
                    provenance[left], "global_row"
                ).isdisjoint(identities(provenance[right], "global_row")),
                "ownership_tuples_disjoint": identities(
                    provenance[left], "ownership"
                ).isdisjoint(identities(provenance[right], "ownership")),
                "hidden_bf16_row_hashes_disjoint": identities(
                    provenance[left], "hidden_row_sha256"
                ).isdisjoint(identities(provenance[right], "hidden_row_sha256")),
            }
    all_disjoint = all(
        value
        for comparison in comparisons.values()
        for value in comparison.values()
    )
    if not all_disjoint:
        raise RuntimeError("selected_batches_not_disjoint_from_prior_sets")
    return {
        "selection_rules": {
            "prior_fit_evaluation": "first capture-order row per request",
            "prior_held_out": "second capture-order row per request",
            "selected_batch_0": "third capture-order row per request",
            "selected_batch_1": "fourth capture-order row per request",
        },
        "all_pairwise_disjoint": all_disjoint,
        "comparisons": comparisons,
        "provenance": provenance,
        "provenance_sha256": {
            name: sha256_json(rows) for name, rows in provenance.items()
        },
    }


def traffic(shortlist: int, union_rows: int) -> dict[str, int | float]:
    dense_weight_bytes = VOCAB * HIDDEN * 2
    pq_codes_bytes = VOCAB * SUBSPACES
    codebook_bytes = SUBSPACES * CODEBOOK_ROWS * SUBSPACE_DIMENSIONS * 2
    query_lookup_table_bytes = REQUESTS * SUBSPACES * CODEBOOK_ROWS * 4
    score_buffer_bytes = REQUESTS * VOCAB * 4
    query_input_bytes = REQUESTS * HIDDEN * 2
    candidate_id_bytes = REQUESTS * shortlist * 4
    exact_member_weight_bytes = union_rows * HIDDEN * 2
    exact_logit_bytes = REQUESTS * shortlist * 4
    candidate_total_bytes = sum(
        (
            pq_codes_bytes,
            codebook_bytes,
            query_lookup_table_bytes,
            score_buffer_bytes,
            query_input_bytes,
            candidate_id_bytes,
            exact_member_weight_bytes,
            exact_logit_bytes,
        )
    )
    net_bytes_saved = dense_weight_bytes - candidate_total_bytes
    return {
        "dense_weight_bytes": dense_weight_bytes,
        "pq_codes_bytes": pq_codes_bytes,
        "codebook_bytes": codebook_bytes,
        "query_lookup_table_bytes": query_lookup_table_bytes,
        "score_buffer_bytes": score_buffer_bytes,
        "query_input_bytes": query_input_bytes,
        "candidate_id_bytes": candidate_id_bytes,
        "exact_member_weight_bytes": exact_member_weight_bytes,
        "exact_logit_bytes": exact_logit_bytes,
        "candidate_total_bytes": candidate_total_bytes,
        "net_bytes_saved": net_bytes_saved,
        "net_bytes_avoided_fraction": net_bytes_saved / dense_weight_bytes,
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
    torch.use_deterministic_algorithms(True)
    contract = json.loads(args.contract.read_text())
    deadline = parse_deadline(contract["absolute_deadline_utc"])
    require_before(deadline, "identity_validation")
    expected = contract["inputs"]
    paths = {
        name: (args.project_dir / expected[f"{name}_path"]).resolve()
        for name in (
            "capture",
            "capture_terminal",
            "checkpoint_index",
            "config",
            "lowrank_terminal",
            "weight_shard",
        )
    }
    identity_started = time.monotonic()
    identities = {}
    for name, path in paths.items():
        observed = sha256_file(path)
        if observed != expected[f"{name}_sha256"]:
            raise RuntimeError(f"{name}_hash_mismatch")
        identities[name] = observed
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
    payload = torch.load(
        paths["capture"], map_location="cpu", weights_only=True, mmap=True
    )
    prior_indices, selected_indices = select_batches(payload, torch)
    disjointness = disjointness_report(
        payload, prior_indices, selected_indices, torch
    )
    identity_seconds = time.monotonic() - identity_started

    with safe_open(paths["weight_shard"], framework="pt", device="cpu") as handle:
        if WEIGHT_KEY not in handle.keys():
            raise RuntimeError("tied_weight_key_absent")
        weight = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError("tied_weight_geometry_or_dtype_mismatch")

    build_started = time.monotonic()
    tensor_digest = hashlib.sha256()
    hash_chunk = 32768
    for row_start in range(0, VOCAB, hash_chunk):
        require_before(deadline, "codebook_statistics")
        row_end = min(VOCAB, row_start + hash_chunk)
        block_bf16 = weight[row_start:row_end].contiguous()
        tensor_digest.update(bytes(block_bf16.view(torch.uint8).untyped_storage()))
    tied_weight_tensor_sha256 = tensor_digest.hexdigest()
    if tied_weight_tensor_sha256 != expected["tied_weight_tensor_sha256"]:
        raise RuntimeError("tied_weight_tensor_hash_mismatch")
    full_weight_float = weight.float()
    variances, means = torch.var_mean(
        full_weight_float, dim=0, correction=0
    )
    del full_weight_float
    means = means.double()
    scales = variances.double().clamp_min(torch.finfo(torch.float64).eps).sqrt()
    normalized_levels = torch.tensor(
        standard_normal_lloyd_max_levels(), dtype=torch.float64
    )
    scalar_codebooks = (
        means[:, None] + scales[:, None] * normalized_levels[None, :]
    ).to(torch.bfloat16)
    scalar_thresholds = (
        (scalar_codebooks[:, :-1].float() + scalar_codebooks[:, 1:].float()) / 2
    )
    codes = torch.empty((VOCAB, SUBSPACES), dtype=torch.uint8)
    row_chunk = 8192
    for row_start in range(0, VOCAB, row_chunk):
        require_before(deadline, "index_encoding")
        row_end = min(VOCAB, row_start + row_chunk)
        block = weight[row_start:row_end].float()
        quantized = torch.searchsorted(
            scalar_thresholds, block.T.contiguous(), right=False
        ).T
        codes[row_start:row_end] = (
            quantized[:, 0::2] + SCALAR_LEVELS * quantized[:, 1::2]
        ).to(torch.uint8)
        del block, quantized
    expanded_codebooks = torch.empty(
        (SUBSPACES, CODEBOOK_ROWS, SUBSPACE_DIMENSIONS), dtype=torch.bfloat16
    )
    low_code = torch.arange(CODEBOOK_ROWS, dtype=torch.int64) % SCALAR_LEVELS
    high_code = torch.arange(CODEBOOK_ROWS, dtype=torch.int64) // SCALAR_LEVELS
    expanded_codebooks[:, :, 0] = scalar_codebooks[0::2][:, low_code]
    expanded_codebooks[:, :, 1] = scalar_codebooks[1::2][:, high_code]
    index_path = args.project_dir / contract["artifact_contract"]["frozen_index"]
    index_payload = {
        "schema_version": 1,
        "name": contract["candidate"]["index_name"],
        "codes": codes,
        "codebooks": expanded_codebooks,
        "normalized_lloyd_max_levels": normalized_levels,
        "subspaces": SUBSPACES,
        "dimensions_per_subspace": SUBSPACE_DIMENSIONS,
        "codebook_rows": CODEBOOK_ROWS,
        "weight_tensor_sha256": tied_weight_tensor_sha256,
        "capture_rows_used_for_training": 0,
        "training_source": "all_output_weight_rows_only",
    }
    atomic_torch_save(index_path, index_payload, torch)
    index_sha256 = sha256_file(index_path)
    codes_sha256 = raw_tensor_sha256(codes, torch)
    codebooks_sha256 = raw_tensor_sha256(expanded_codebooks, torch)
    index_frozen_at_utc = datetime.now(timezone.utc).isoformat()
    index_mtime_ns = index_path.stat().st_mtime_ns
    index_build_seconds = time.monotonic() - build_started

    require_before(deadline, "held_out_evaluation")
    evaluation_started_at_utc = datetime.now(timezone.utc).isoformat()
    hidden = torch.cat(
        [payload["hidden_states"][indices] for indices in selected_indices], dim=0
    ).contiguous()
    hidden_float = hidden.float()
    exact_scores = torch.empty((2 * REQUESTS, VOCAB), dtype=torch.float32)
    approximate_scores = torch.empty((2 * REQUESTS, VOCAB), dtype=torch.float32)
    exact_weight_norm = torch.empty(VOCAB, dtype=torch.float64)
    score_started = time.monotonic()
    subspace_ids = torch.arange(SUBSPACES, dtype=torch.int64)[None, :]
    row_chunk = 2048
    for row_start in range(0, VOCAB, row_chunk):
        require_before(deadline, "held_out_weight_scoring")
        row_end = min(VOCAB, row_start + row_chunk)
        block_weight = weight[row_start:row_end].float()
        exact_scores[:, row_start:row_end] = hidden_float @ block_weight.T
        exact_weight_norm[row_start:row_end] = torch.linalg.vector_norm(
            block_weight.double(), dim=1
        )
        block_codes = codes[row_start:row_end].to(torch.int64)
        reconstructed = expanded_codebooks[
            subspace_ids, block_codes
        ].reshape(row_end - row_start, HIDDEN).float()
        approximate_scores[:, row_start:row_end] = hidden_float @ reconstructed.T
    scoring_seconds = time.monotonic() - score_started
    if index_path.stat().st_mtime_ns != index_mtime_ns:
        raise RuntimeError("frozen_index_mutated_during_evaluation")
    if sha256_file(index_path) != index_sha256:
        raise RuntimeError("frozen_index_hash_changed_during_evaluation")

    qnorm = torch.linalg.vector_norm(hidden.double(), dim=1)
    stock_error = gamma(HIDDEN, 2.0**-24) * (
        qnorm[:, None] * exact_weight_norm[None, :]
    )
    stock_error = stock_error + stock_error
    stock_error = stock_error + (
        (2.0**-8 / (1.0 - 2.0**-8))
        * (
            qnorm[:, None] * exact_weight_norm[None, :]
            + gamma(HIDDEN, 2.0**-24)
            * (qnorm[:, None] * exact_weight_norm[None, :])
        )
    )
    allowed = torch.ones(VOCAB, dtype=torch.bool)
    allowed[[1, 106]] = False
    dense_lower = (exact_scores.double() - stock_error).masked_fill(
        ~allowed[None, :], float("-inf")
    ).max(dim=1).values
    possible_stock_candidates = (
        exact_scores.double() + stock_error >= dense_lower[:, None]
    )
    possible_stock_candidates[:, 1] = False
    dense_reference_ids = exact_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    ).argmax(dim=1)
    ranking_scores = approximate_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    )
    ranking = torch.argsort(
        ranking_scores, dim=1, descending=True, stable=True
    )[:, : max(contract["candidate"]["shortlist_sizes"])]

    operating_points = []
    for shortlist in contract["candidate"]["shortlist_sizes"]:
        ids = ranking[:, :shortlist]
        membership = torch.zeros_like(possible_stock_candidates)
        membership.scatter_(1, ids, True)
        stock_counts = possible_stock_candidates.sum(dim=1)
        recalled_counts = (possible_stock_candidates & membership).sum(dim=1)
        full_recall = recalled_counts == stock_counts
        candidate_scores = exact_scores.gather(1, ids)
        exact_rescore_ids = ids.gather(
            1, candidate_scores.argmax(dim=1, keepdim=True)
        ).squeeze(1)
        exact_agreement = exact_rescore_ids == dense_reference_ids
        cutoff_scores = ranking_scores.gather(
            1, ids[:, -1:].contiguous()
        ).squeeze(1)
        stock_margins = (
            ranking_scores - cutoff_scores[:, None]
        ).masked_fill(~possible_stock_candidates, float("inf"))
        worst_stock_margin = stock_margins.min(dim=1).values
        missed_margins = (
            cutoff_scores[:, None] - ranking_scores
        ).masked_fill(~(possible_stock_candidates & ~membership), float("-inf"))
        missed_rows = possible_stock_candidates & ~membership
        batch_results = []
        for batch_index in range(2):
            start = batch_index * REQUESTS
            end = start + REQUESTS
            batch_ids = ids[start:end]
            union_ids = torch.unique(batch_ids.flatten(), sorted=True)
            missed = missed_rows[start:end]
            finite_missed_margins = missed_margins[start:end][missed]
            charged = traffic(shortlist, int(union_ids.numel()))
            batch_results.append(
                {
                    "batch_index": batch_index,
                    "complete_stock_candidate_recall": bool(
                        full_recall[start:end].all()
                    ),
                    "exact_rescore_greedy_agreement": bool(
                        exact_agreement[start:end].all()
                    ),
                    "stock_candidates_total": int(stock_counts[start:end].sum()),
                    "stock_candidates_recalled": int(
                        recalled_counts[start:end].sum()
                    ),
                    "stock_recall_fraction": float(
                        recalled_counts[start:end].sum()
                        / stock_counts[start:end].sum()
                    ),
                    "missed_stock_candidates": int(missed.sum()),
                    "miss_margin_cutoff_minus_candidate_max": (
                        float(finite_missed_margins.max())
                        if finite_missed_margins.numel()
                        else None
                    ),
                    "miss_margin_cutoff_minus_candidate_mean": (
                        float(finite_missed_margins.mean())
                        if finite_missed_margins.numel()
                        else None
                    ),
                    "worst_stock_candidate_margin_to_cutoff": float(
                        worst_stock_margin[start:end].min()
                    ),
                    "physical_union_rows": int(union_ids.numel()),
                    "physical_union_token_ids_sha256": raw_tensor_sha256(
                        union_ids.to(torch.int32), torch
                    ),
                    "exact_rescore_ids_sha256": raw_tensor_sha256(
                        exact_rescore_ids[start:end].to(torch.int32), torch
                    ),
                    "dense_reference_ids_sha256": raw_tensor_sha256(
                        dense_reference_ids[start:end].to(torch.int32), torch
                    ),
                    "traffic": charged,
                    "net_physical_traffic_positive": charged["net_bytes_saved"] > 0,
                }
            )
        operating_points.append(
            {
                "shortlist_size": shortlist,
                "complete_stock_candidate_recall_all_64": bool(full_recall.all()),
                "exact_rescore_greedy_agreement_all_64": bool(exact_agreement.all()),
                "missed_stock_candidates_all_64": int(missed_rows.sum()),
                "batches": batch_results,
            }
        )

    qualifying = [
        point
        for point in operating_points
        if point["complete_stock_candidate_recall_all_64"]
        and point["exact_rescore_greedy_agreement_all_64"]
        and all(
            batch["net_physical_traffic_positive"] for batch in point["batches"]
        )
    ]
    selected_shortlist = (
        min(point["shortlist_size"] for point in qualifying) if qualifying else None
    )
    promote = selected_shortlist is not None
    if promote:
        classification = (
            "typed_reference_positive_pq_mips_capture_recall_and_traffic"
        )
        reason = (
            f"The frozen pairwise PQ index preserved every possible stock candidate "
            f"and exact greedy output at shortlist {selected_shortlist}, with positive "
            "fully charged physical traffic in both c32 batches."
        )
    else:
        classification = "typed_falsification_fixed_pq_mips_capture_recall"
        reason = (
            "No preregistered shortlist simultaneously preserved the complete possible "
            "stock candidate set, exact greedy output, and positive fully charged "
            "physical traffic in both c32 batches."
        )
    selected_point = next(
        (
            point
            for point in operating_points
            if point["shortlist_size"] == selected_shortlist
        ),
        None,
    )
    output_head_seconds = contract["slo"]["inherited_output_consumer_seconds_per_request"]
    if selected_point is None:
        byte_bounds = None
    else:
        byte_bounds = [
            {
                "batch_index": batch["batch_index"],
                "byte_proportional_seconds_saved_upper_bound": (
                    output_head_seconds
                    * batch["traffic"]["net_bytes_avoided_fraction"]
                ),
            }
            for batch in selected_point["batches"]
        ]
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
            "frozen_index": index_sha256,
            "codes_tensor": codes_sha256,
            "codebooks_tensor": codebooks_sha256,
        },
        "geometry": {
            "model": contract["stock_control"]["model"],
            "revision": contract["stock_control"]["revision"],
            "weight_key": WEIGHT_KEY,
            "weight_shape": [VOCAB, HIDDEN],
            "weight_dtype": str(weight.dtype),
            "capture_shape": list(payload["hidden_states"].shape),
            "capture_dtype": str(payload["hidden_states"].dtype),
            "batches": 2,
            "rows_per_batch": REQUESTS,
        },
        "disjointness": disjointness,
        "frozen_index": {
            "name": contract["candidate"]["index_name"],
            "subspaces": SUBSPACES,
            "dimensions_per_subspace": SUBSPACE_DIMENSIONS,
            "codebook_rows": CODEBOOK_ROWS,
            "code_bits_per_subspace": 8,
            "effective_bits_per_weight_scalar": 4,
            "pq_codes_dtype": str(codes.dtype),
            "codebook_dtype": str(expanded_codebooks.dtype),
            "training_source": "all_output_weight_rows_only",
            "capture_rows_used_for_training": 0,
            "frozen_at_utc": index_frozen_at_utc,
            "evaluation_started_at_utc": evaluation_started_at_utc,
            "frozen_before_evaluation": index_frozen_at_utc
            < evaluation_started_at_utc,
            "tuned_after_evaluation": False,
            "normalized_lloyd_max_levels": normalized_levels.tolist(),
        },
        "stock_consumer": {
            "classification": "pinned_temperature_zero_greedy_with_min_token_stop_mask",
            "softcap": "30 * tanh(pre_softcap_logit / 30), monotone",
            "masked_stop_token_ids": [1],
            "conservatively_excluded_from_incumbents": [1, 106],
        },
        "correctness": {
            "all_inputs_finite": True,
            "possible_stock_candidate_rows_mean": float(
                possible_stock_candidates.sum(dim=1).double().mean()
            ),
            "possible_stock_candidate_rows_max": int(
                possible_stock_candidates.sum(dim=1).max()
            ),
            "possible_stock_candidate_set_sha256": raw_tensor_sha256(
                possible_stock_candidates, torch
            ),
            "dense_reference_ids_sha256": raw_tensor_sha256(
                dense_reference_ids.to(torch.int32), torch
            ),
            "operating_points": operating_points,
        },
        "decision": {
            "promote_to_h200_exact_consumer_component": promote,
            "close_fixed_pq_retrieval_proxy": not promote,
            "selected_shortlist_size": selected_shortlist,
            "reason": reason,
        },
        "economics": {
            "campaign_denominator_seconds_per_request": contract["slo"][
                "campaign_denominator_seconds_per_request"
            ],
            "campaign_target_seconds_per_request": contract["slo"][
                "campaign_target_seconds_per_request"
            ],
            "inherited_output_consumer_seconds_per_request": output_head_seconds,
            "selected_byte_proportional_bounds": byte_bounds,
            "interpretation": "Analytical byte-proportional upper bounds only; CPU runtime is not H200 or endpoint latency.",
        },
        "timing": {
            "cpu_threads": torch.get_num_threads(),
            "identity_seconds": identity_seconds,
            "index_build_seconds": index_build_seconds,
            "scoring_seconds": scoring_seconds,
            "total_cpu_reference_seconds": time.monotonic() - started,
        },
        "resource_use": {
            "actual_spend_usd": 0.0,
            "gpu_claimed": False,
            "gpu_invocations": 0,
            "provider_mutation": False,
            "endpoint_traffic": False,
            "shared_inputs_read_only": True,
            "additional_artifact_bytes": index_path.stat().st_size,
        },
        "scope_and_limits": {
            "measured": "CPU/reference asymmetric PQ ranking, exact BF16-weight rescore agreement, and analytical physical traffic on 64 preregistered exact-capture rows.",
            "not_claimed": "H200 latency, endpoint speed, quality beyond this capture, GPQA-Diamond, TauBench, or production economics.",
            "next_gate": (
                "Target-H200 exact-consumer component followed by GPQA-Diamond and "
                "TauBench recovery."
                if promote
                else "Close this fixed PQ retrieval proxy; trained or hierarchical approximate heads remain open."
            ),
        },
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "classification": classification,
                "selected_shortlist_size": selected_shortlist,
                "output": str(args.output),
                "index": str(index_path),
                "total_seconds": result["timing"]["total_cpu_reference_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
