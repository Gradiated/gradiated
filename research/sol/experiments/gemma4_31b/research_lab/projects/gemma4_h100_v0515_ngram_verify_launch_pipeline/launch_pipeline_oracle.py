#!/usr/bin/env python3
"""CPU oracle for the depth-12 NGRAM verify launch-pipeline candidate."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Iterable


DEPTH = 12


def reference_full_mask(
    seq_lens: list[int], tree_masks: list[list[list[bool]]]
) -> list[bool]:
    output: list[bool] = []
    for seq_len, tree_mask in zip(seq_lens, tree_masks, strict=True):
        for query_row in range(DEPTH):
            output.extend([True] * seq_len)
            output.extend(tree_mask[query_row])
    return output


def packed_cpu_full_mask(
    seq_lens: list[int],
    tree_masks: list[list[list[bool]]],
    graph_batch_size: int,
    padded_seq_len: int = 1,
) -> tuple[list[bool], list[int]]:
    """Candidate layout plus the all-True CUDA-graph padding suffix."""
    if graph_batch_size < len(seq_lens):
        raise ValueError("graph batch cannot be smaller than the live batch")
    mask: list[bool] = []
    indptr = [0]
    rows = list(zip(seq_lens, tree_masks, strict=True))
    empty_tree = [[True] * DEPTH for _ in range(DEPTH)]
    rows.extend(
        (padded_seq_len, empty_tree)
        for _ in range(graph_batch_size - len(seq_lens))
    )
    for seq_len, tree_mask in rows:
        for query_row in range(DEPTH):
            mask.extend([True] * seq_len)
            mask.extend(tree_mask[query_row])
        indptr.append(len(mask))
    return mask, indptr


@dataclass
class Request:
    rid: str
    slot: int
    generation: int
    kv_committed_len: int
    max_output_tokens: int
    output_ids: list[int] = field(default_factory=list)
    retracted: bool = False
    finished: bool = False


def settle_scheduler_result(
    requests: list[Request],
    padded_tokens: list[int],
    accept_lens: list[int],
    stride: int = DEPTH,
) -> list[list[int]]:
    if len(accept_lens) != len(requests):
        raise ValueError("accept_lens must have one entry per live request")
    accepted: list[list[int]] = []
    for row, (req, accept_len) in enumerate(zip(requests, accept_lens, strict=True)):
        if not 1 <= accept_len <= stride:
            raise ValueError("accept length includes the bonus and must be in [1, 12]")
        tokens = padded_tokens[row * stride : row * stride + accept_len]
        if req.retracted or req.finished:
            accepted.append(tokens)
            continue
        retained = tokens
        req.kv_committed_len += len(tokens)
        req.output_ids.extend(tokens)
        req.finished = len(req.output_ids) >= req.max_output_tokens
        accepted.append(retained)
    return accepted


def event_chain(candidate: bool) -> list[dict[str, object]]:
    chain = [
        ("accepted_result_cpu_visibility", "host", True, False),
        ("ngram_corpus_synchronize_and_batch_get", "cpu", True, False),
        ("draft_and_tree_mask_h2d", "copy", True, False),
        ("reconstruct_tree_indices", "cuda_kernel", True, False),
    ]
    if candidate:
        chain.append(("packed_full_mask_single_h2d", "copy", False, True))
    else:
        chain.extend(
            [
                ("per_row_device_ones", "cuda_op_x_live_rows", False, True),
                ("per_row_tree_mask_h2d", "copy_x_live_rows", False, True),
                ("per_row_cat_and_bool_cast", "cuda_ops_x_live_rows", False, True),
                ("final_row_cat", "cuda_op", False, True),
            ]
        )
    chain.extend(
        [
            ("assign_verify_cache_locations", "cuda_kernel", True, False),
            ("cuda_graph_static_input_and_attention_metadata_fill", "cuda", True, False),
            ("target_model_hybrid_attention_graph_replay", "cuda_graph", True, False),
            ("eagle_sample_and_accept_index", "cuda", True, False),
            ("accepted_kv_move", "cuda", True, False),
            ("result_copy_stream_d2h_and_event", "copy_event", True, False),
            ("resolve_tokens_commit_kv_emit_and_finish", "host", True, False),
        ]
    )
    return [
        {
            "name": name,
            "kind": kind,
            "compulsory": compulsory,
            "candidate_changed": changed,
        }
        for name, kind, compulsory, changed in chain
    ]


def make_tree(seed: int) -> list[list[bool]]:
    return [
        [column <= row and ((row + column + seed) % 3 != 0) for column in range(DEPTH)]
        for row in range(DEPTH)
    ]


def flattened_rows(rows: Iterable[Iterable[int]]) -> list[int]:
    output: list[int] = []
    for row in rows:
        row_list = list(row)
        output.extend(row_list)
        output.extend([-1] * (DEPTH - len(row_list)))
    return output


def run_oracle() -> dict[str, object]:
    seq_lens = [0, 1, 17, 1023, 4096]
    trees = [make_tree(seed) for seed in range(len(seq_lens))]
    reference = reference_full_mask(seq_lens, trees)
    candidate, indptr = packed_cpu_full_mask(seq_lens, trees, graph_batch_size=8)
    assert candidate[: len(reference)] == reference
    assert all(candidate[len(reference) :])
    expected_indptr = [0]
    for seq_len in seq_lens + [1, 1, 1]:
        expected_indptr.append(expected_indptr[-1] + DEPTH * (seq_len + DEPTH))
    assert indptr == expected_indptr

    requests = [
        Request("zero", 0, 1, 100, 20),
        Request("partial", 1, 1, 200, 20),
        Request("full", 2, 1, 300, 20),
        Request("complete", 3, 1, 400, 2),
    ]
    rows = [
        [1000],
        [2000, 2001, 2002, 2003, 2004],
        list(range(3000, 3012)),
        [4000, 4001, 4002, 4003],
    ]
    accepted = settle_scheduler_result(
        requests, flattened_rows(rows), [1, 5, 12, 4]
    )
    assert [len(row) for row in accepted] == [1, 5, 12, 4]
    assert [req.kv_committed_len for req in requests] == [101, 205, 312, 404]
    assert requests[-1].finished

    old_generation = requests[-1].generation
    replacement = Request("reused", slot=3, generation=old_generation + 1, kv_committed_len=9, max_output_tokens=3)
    stale = requests[-1]
    stale.retracted = True
    settle_scheduler_result([stale], flattened_rows([[9999]]), [1])
    reused_accepted = settle_scheduler_result(
        [replacement], flattened_rows([[5000, 5001]]), [2]
    )
    assert stale.kv_committed_len == 404
    assert replacement.kv_committed_len == 11
    assert replacement.output_ids == [5000, 5001]

    return {
        "schema_version": 1,
        "result": "pass",
        "depth": DEPTH,
        "cases": {
            "zero_correct_drafts_bonus_only": True,
            "partial_acceptance": True,
            "full_depth_12_acceptance": True,
            "mixed_batch_rows": True,
            "padded_graph_rows_all_true": True,
            "request_completion_marks_finished_and_blocks_later_settlement": True,
            "request_slot_reuse_generation_isolated": True,
        },
        "mask": {
            "live_rows": len(seq_lens),
            "graph_rows": 8,
            "live_mask_elements": len(reference),
            "padded_mask_elements": len(candidate),
            "reference_equal": True,
        },
        "acceptance": {
            "accepted_lengths": [len(row) for row in accepted],
            "reused_request_accepted": reused_accepted,
        },
        "baseline_event_chain": event_chain(candidate=False),
        "candidate_event_chain": event_chain(candidate=True),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_oracle(),
            sort_keys=True,
            separators=(",", ":") if args.compact else None,
            indent=None if args.compact else 2,
        )
    )


if __name__ == "__main__":
    main()
