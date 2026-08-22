#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path

import torch

from centroid_block_discriminator import (
    EXPECTED_CAPTURE_SHA256,
    MODEL,
    REVISION,
    SafeTensorView,
    WEIGHT_KEY,
    percentile,
    select_request_representative_rows,
    sha256_file,
    update_best,
)


EXPECTED_WEIGHT_TENSOR_SHA256 = (
    "1053f051b1b894bb5f80eb52cdd434b8028aaad27c3006fcfdec48ac8c46d98d"
)


def select_basis_rows(capture):
    selected = [
        row["global_row"]
        for row in capture["ownership"]
        if row["capture_index"] == 2
    ]
    if len(selected) != 384:
        raise ValueError(f"expected 384 basis rows, found {len(selected)}")
    return selected


def build_basis(hidden_states, basis_rows, rank):
    started = time.perf_counter()
    training = hidden_states[basis_rows].double()
    _, singular_values, basis = torch.linalg.svd(training, full_matrices=False)
    basis = basis[:rank].contiguous()
    gram = basis @ basis.T
    defect = float(
        torch.linalg.matrix_norm(
            gram - torch.eye(rank, dtype=torch.float64), ord=2
        )
    )
    return {
        "basis": basis,
        "singular_values": singular_values[:rank],
        "orthogonality_defect": defect,
        "construction_seconds": time.perf_counter() - started,
    }


def build_index(weight, basis_info, chunk_rows):
    basis = basis_info["basis"]
    vocab, hidden = weight.shape
    rank = basis.shape[0]
    projected = torch.empty((vocab, rank), dtype=torch.float64)
    residual_norm = torch.empty(vocab, dtype=torch.float64)
    leakage_norm = torch.empty(vocab, dtype=torch.float64)
    weight_norm = torch.empty(vocab, dtype=torch.float64)
    started = time.perf_counter()
    for first in range(0, vocab, chunk_rows):
        last = min(first + chunk_rows, vocab)
        rows = weight[first:last].double()
        projection = rows @ basis.T
        residual = rows - projection @ basis
        leakage = residual @ basis.T
        projected[first:last] = projection
        residual_norm[first:last] = torch.linalg.vector_norm(residual, dim=1)
        leakage_norm[first:last] = torch.linalg.vector_norm(leakage, dim=1)
        weight_norm[first:last] = torch.linalg.vector_norm(rows, dim=1)
    return {
        "basis": basis,
        "projected": projected,
        "residual_norm": residual_norm,
        "leakage_norm": leakage_norm,
        "weight_norm": weight_norm,
        "basis_construction_seconds": basis_info["construction_seconds"],
        "index_construction_seconds": time.perf_counter() - started,
        "orthogonality_defect": basis_info["orthogonality_defect"],
        "singular_values": basis_info["singular_values"],
    }


def index_bytes(index):
    tensors = (
        index["basis"],
        index["projected"],
        index["residual_norm"],
        index["leakage_norm"],
        index["weight_norm"],
    )
    return sum(tensor.numel() * tensor.element_size() for tensor in tensors)


def certified_top1(
    weight,
    hidden,
    index,
    block_size,
    traversal_batch_blocks,
):
    basis = index["basis"]
    h = hidden.double()
    q = basis @ h
    h_parallel = q @ basis
    h_residual = h - h_parallel
    h_norm = float(torch.linalg.vector_norm(h))
    q_norm = float(torch.linalg.vector_norm(q))
    h_residual_norm = float(torch.linalg.vector_norm(h_residual))
    projected_scores = index["projected"] @ q
    residual_allowance = (
        index["residual_norm"] * h_residual_norm
        + index["leakage_norm"] * q_norm
    )
    guard = 1e-10 * (
        projected_scores.abs() + residual_allowance + index["weight_norm"] * h_norm
    ) + 1e-10
    token_upper = projected_scores + residual_allowance + guard
    block_upper = token_upper.reshape(-1, block_size).amax(dim=1)
    order = torch.argsort(block_upper, descending=True, stable=True)
    best_score = -math.inf
    best_lower = -math.inf
    best_token = weight.shape[0]
    evaluated_blocks = []
    started = time.perf_counter()
    for first in range(0, len(order), traversal_batch_blocks):
        if best_lower > -math.inf and float(block_upper[int(order[first])]) < best_lower:
            break
        chosen = order[first : first + traversal_batch_blocks]
        row_ids = (
            chosen[:, None] * block_size
            + torch.arange(block_size, dtype=torch.int64)[None, :]
        ).reshape(-1)
        rows = weight[row_ids].double()
        scores = rows @ h
        best_score, best_token = update_best(
            scores, row_ids, best_score, best_token
        )
        exact_guard = (
            1e-10 * index["weight_norm"][row_ids] * h_norm + 1e-10
        )
        best_lower = max(best_lower, float((scores - exact_guard).max()))
        evaluated_blocks.extend(int(block) for block in chosen)
    elapsed = time.perf_counter() - started
    evaluated_set = set(evaluated_blocks)
    skipped = [
        block for block in range(len(block_upper)) if block not in evaluated_set
    ]
    maximum_skipped_upper = max(
        (float(block_upper[block]) for block in skipped), default=-math.inf
    )
    certified = maximum_skipped_upper < best_lower
    return {
        "top1_id": best_token,
        "top1_score": best_score,
        "best_lower_bound": best_lower,
        "maximum_skipped_upper": maximum_skipped_upper if skipped else None,
        "certificate_gap": (
            best_lower - maximum_skipped_upper if skipped else None
        ),
        "certified": certified,
        "evaluated_blocks": len(evaluated_blocks),
        "evaluated_rows": len(evaluated_blocks) * block_size,
        "query_residual_norm_fraction": h_residual_norm / h_norm,
        "seconds": elapsed,
    }


def dense_top1(weight, hidden, chunk_rows):
    h = hidden.double()
    best_score = -math.inf
    best_token = weight.shape[0]
    started = time.perf_counter()
    for first in range(0, weight.shape[0], chunk_rows):
        last = min(first + chunk_rows, weight.shape[0])
        scores = weight[first:last].double() @ h
        ids = torch.arange(first, last, dtype=torch.int64)
        best_score, best_token = update_best(
            scores, ids, best_score, best_token
        )
    return {
        "top1_id": best_token,
        "top1_score": best_score,
        "seconds": time.perf_counter() - started,
    }


def run(args):
    torch.set_num_threads(args.threads)
    checkpoint = Path(args.checkpoint)
    capture_path = Path(args.capture)
    output = Path(args.output)
    config = json.loads((checkpoint / "config.json").read_text())
    text = config["text_config"]
    if (
        text["hidden_size"] != 5376
        or text["vocab_size"] != 262144
        or not config["tie_word_embeddings"]
        or not text["tie_word_embeddings"]
    ):
        raise ValueError("checkpoint geometry does not match the admitted tied head")
    capture_hash = sha256_file(capture_path)
    if capture_hash != EXPECTED_CAPTURE_SHA256:
        raise ValueError(f"capture hash mismatch: {capture_hash}")
    capture = torch.load(capture_path, map_location="cpu", weights_only=True)
    hidden_states = capture["hidden_states"]
    if tuple(hidden_states.shape) != (1536, 5376):
        raise ValueError("capture tensor geometry mismatch")
    weight_path = checkpoint / "model-00001-of-00002.safetensors"
    weight_view = SafeTensorView(weight_path, WEIGHT_KEY)
    try:
        weight = weight_view.tensor
        if tuple(weight.shape) != (262144, 5376):
            raise ValueError("weight tensor geometry mismatch")
        weight_tensor_hash = weight_view.tensor_sha256()
        if weight_tensor_hash != EXPECTED_WEIGHT_TENSOR_SHA256:
            raise ValueError(f"weight tensor hash mismatch: {weight_tensor_hash}")
        basis_rows = select_basis_rows(capture)
        basis_info = build_basis(hidden_states, basis_rows, args.rank)
        index = build_index(weight, basis_info, args.index_chunk_rows)
        selected = select_request_representative_rows(capture)
        rows = []
        for ordinal, global_row in enumerate(selected):
            candidate = certified_top1(
                weight,
                hidden_states[global_row],
                index,
                args.block_size,
                args.traversal_batch_blocks,
            )
            dense = dense_top1(weight, hidden_states[global_row], args.dense_chunk_rows)
            candidate.update(
                {
                    "dense_top1_id": dense["top1_id"],
                    "dense_top1_score": dense["top1_score"],
                    "dense_seconds": dense["seconds"],
                    "agreement": candidate["top1_id"] == dense["top1_id"],
                    "global_row": global_row,
                    "request_ordinal": ordinal,
                }
            )
            rows.append(candidate)
            print(
                json.dumps(
                    {
                        "row": ordinal + 1,
                        "evaluated_fraction": candidate["evaluated_rows"]
                        / weight.shape[0],
                        "residual_norm_fraction": candidate[
                            "query_residual_norm_fraction"
                        ],
                        "agreement": candidate["agreement"],
                        "certified": candidate["certified"],
                    }
                ),
                flush=True,
            )
        vocab, hidden = weight.shape
        rank = args.rank
        evaluated_fractions = [
            row["evaluated_rows"] / vocab for row in rows
        ]
        bound_flops = (
            2 * vocab * rank
            + 4 * rank * hidden
            + 8 * vocab
            + vocab // args.block_size * args.block_size
        )
        verification_flops = [
            2 * row["evaluated_rows"] * hidden for row in rows
        ]
        total_work_fractions = [
            (bound_flops + verification) / (2 * vocab * hidden)
            for verification in verification_flops
        ]
        resident_index_bytes = index_bytes(index)
        dense_weight_bytes = 2 * vocab * hidden
        total_byte_fractions = [
            (
                resident_index_bytes
                + 2 * row["evaluated_rows"] * hidden
            )
            / dense_weight_bytes
            for row in rows
        ]
        candidate_times = [row["seconds"] for row in rows]
        dense_times = [row["dense_seconds"] for row in rows]
        residual_fractions = [
            row["query_residual_norm_fraction"] for row in rows
        ]
        head_seconds = 0.010869238160550593
        qualified_seconds = 0.625149101968745
        conservative_head_fraction = max(
            max(total_work_fractions), max(total_byte_fractions)
        )
        conservative_head_saving = (
            head_seconds * max(0.0, 1.0 - conservative_head_fraction)
        )
        result = {
            "schema_version": 1,
            "classification": "lowrank_anisotropic_block_discriminator_result",
            "identity": {
                "model": MODEL,
                "revision": REVISION,
                "weight_key": WEIGHT_KEY,
                "weight_tensor_raw_bf16_sha256": weight_tensor_hash,
                "weight_shard_sha256": "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa",
                "capture_sha256": capture_hash,
                "prior_centroid_terminal_sha256": "5a7db872acc7fc2a303afbd8b22c4a7f08b085c8dcece937a59c07e5a9af1141",
            },
            "geometry": {
                "vocab": vocab,
                "hidden": hidden,
                "rank": rank,
                "block_size": args.block_size,
                "blocks": vocab // args.block_size,
                "basis_training_rows": len(basis_rows),
                "basis_training_selection": "capture_index=2, all 12 depths and all 32 requests",
                "evaluated_rows": len(rows),
                "evaluation_selection": "capture_index=3, depth_index=11, one row per each of 32 requests",
                "weight_dtype": str(weight.dtype),
                "index_dtype": "torch.float64",
            },
            "mechanism": {
                "name": "rank384_shared_subspace_per_token_residual_block_bound",
                "semantics": "certified greedy/top-1 only",
                "full_softmax_or_sampling_equivalence": False,
                "bound": "p_i dot q + ||w_i-p_iB||_2 ||h-qB||_2 + ||(w_i-p_iB)B^T||_2 ||q||_2, aggregated by 128-row block",
                "basis_source": "SVD of disjoint prior capture_index=2 rows",
                "numeric_guard": "FP64 component-relative 1e-10 guard plus explicit residual-to-basis leakage norm",
            },
            "basis": {
                "orthogonality_defect_spectral": index[
                    "orthogonality_defect"
                ],
                "heldout_query_residual_norm_fraction_mean": sum(
                    residual_fractions
                )
                / len(residual_fractions),
                "heldout_query_residual_norm_fraction_min": min(
                    residual_fractions
                ),
                "heldout_query_residual_norm_fraction_max": max(
                    residual_fractions
                ),
            },
            "agreement": {
                "matching_rows": sum(row["agreement"] for row in rows),
                "total_rows": len(rows),
                "fraction": sum(row["agreement"] for row in rows) / len(rows),
                "all_skips_certified": all(row["certified"] for row in rows),
            },
            "evaluated_vocabulary_fraction": {
                "mean": sum(evaluated_fractions) / len(evaluated_fractions),
                "minimum": min(evaluated_fractions),
                "maximum": max(evaluated_fractions),
                "p50": percentile(evaluated_fractions, 0.5),
                "p90": percentile(evaluated_fractions, 0.9),
            },
            "index": {
                "bytes": resident_index_bytes,
                "gib": resident_index_bytes / 2**30,
                "basis_construction_seconds": index[
                    "basis_construction_seconds"
                ],
                "weight_index_construction_seconds": index[
                    "index_construction_seconds"
                ],
                "resident_weight_copy_required": False,
            },
            "overhead": {
                "bound_flops_per_row": bound_flops,
                "bound_equivalent_dense_fraction": bound_flops
                / (2 * vocab * hidden),
                "verification_flops_per_row_mean": sum(verification_flops)
                / len(rows),
                "total_analytical_head_work_fraction_mean": sum(
                    total_work_fractions
                )
                / len(rows),
                "total_analytical_head_work_fraction_max": max(
                    total_work_fractions
                ),
                "dense_weight_bytes_per_row": dense_weight_bytes,
                "index_bytes_read_per_row": resident_index_bytes,
                "total_streamed_byte_fraction_mean": sum(total_byte_fractions)
                / len(rows),
                "total_streamed_byte_fraction_max": max(total_byte_fractions),
                "candidate_cpu_seconds_p50": percentile(candidate_times, 0.5),
                "dense_cpu_seconds_p50": percentile(dense_times, 0.5),
                "timing_scope": "coordinator CPU diagnostic only; not target hardware or endpoint performance",
            },
            "whole_request_relevance": {
                "qualified_dense_seconds_per_request": qualified_seconds,
                "historical_h200_head_seconds_per_request": head_seconds,
                "conservative_worst_row_head_fraction": conservative_head_fraction,
                "ideal_head_seconds_saved_at_worst_observed_row": conservative_head_saving,
                "ideal_whole_request_fraction": conservative_head_saving
                / qualified_seconds,
                "interpretation": "component-derived upper bound only; no target-hardware or endpoint claim",
            },
            "rows": rows,
        }
        promote = (
            result["agreement"]["fraction"] == 1.0
            and result["agreement"]["all_skips_certified"]
            and result["overhead"]["total_analytical_head_work_fraction_max"]
            < 0.9
            and result["overhead"]["total_streamed_byte_fraction_max"] < 0.9
        )
        dense_or_worse = (
            result["overhead"]["total_analytical_head_work_fraction_mean"]
            >= 1.0
            or result["overhead"]["total_streamed_byte_fraction_mean"] >= 1.0
        )
        if promote:
            classification = "advance_target_hardware_component"
            reason = "certified worst-row work and streamed bytes are both below 90% of dense"
        elif dense_or_worse:
            classification = "close_broader_certified_index_line"
            reason = "the materially tighter certified index still leaves mean work or traffic at dense"
        else:
            classification = "reject_lowrank_anisotropic_mechanism"
            reason = "the certified saving is positive but below the preregistered materiality gate"
        result["decision"] = {
            "classification": classification,
            "promote": promote,
            "close_broader_line": dense_or_worse,
            "reason": reason,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, output)
        print(json.dumps(result["decision"]), flush=True)
    finally:
        weight_view.close()


def self_test():
    torch.manual_seed(11)
    training = torch.randn(8, 12, dtype=torch.float64)
    _, singular_values, basis = torch.linalg.svd(training, full_matrices=False)
    basis_info = {
        "basis": basis[:4].contiguous(),
        "singular_values": singular_values[:4],
        "orthogonality_defect": float(
            torch.linalg.matrix_norm(
                basis[:4] @ basis[:4].T
                - torch.eye(4, dtype=torch.float64),
                ord=2,
            )
        ),
        "construction_seconds": 0.0,
    }
    weight = torch.randn(32, 12).to(torch.bfloat16)
    hidden = torch.randn(12).to(torch.bfloat16)
    index = build_index(weight, basis_info, 8)
    candidate = certified_top1(weight, hidden, index, 4, 2)
    dense = dense_top1(weight, hidden, 8)
    assert candidate["certified"]
    assert candidate["top1_id"] == dense["top1_id"]
    print(
        json.dumps(
            {"self_test": "passed", "candidate": candidate, "dense": dense}
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint")
    parser.add_argument("--capture")
    parser.add_argument("--output")
    parser.add_argument("--rank", type=int, default=384)
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--index-chunk-rows", type=int, default=512)
    parser.add_argument("--traversal-batch-blocks", type=int, default=16)
    parser.add_argument("--dense-chunk-rows", type=int, default=8192)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.checkpoint, args.capture, args.output)):
        parser.error("--checkpoint, --capture, and --output are required")
    run(args)


if __name__ == "__main__":
    main()
