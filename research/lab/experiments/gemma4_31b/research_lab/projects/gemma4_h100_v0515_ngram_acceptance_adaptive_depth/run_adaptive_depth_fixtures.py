#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from adaptive_depth_contract import (
    AcceptedCarrier,
    ContractError,
    DepthAwareCorpusRouter,
    ProducerLane,
    ProducerRequest,
    analytical_work,
    graph_admissible,
    pack_target_rows,
    settle_acceptance,
    settle_scheduler,
)


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = (
    ROOT
    / "../gemma4_h100_v0515_ngram_price_normalized/packet/candidate-v0.5.15/source/python/sglang/srt"
).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_requests(
    count: int, generation: int = 0, namespace: str = "request"
) -> tuple[ProducerRequest, ...]:
    requests = []
    for index in range(count):
        seq_len = 16 + index + generation
        requests.append(
            ProducerRequest(
                rid=f"{namespace}-{index}",
                seq_len=seq_len,
                tail_tokens=(100 + index, 200 + generation, 300 + index),
                prefix_kv=tuple(10_000 * (index + 1) + slot for slot in range(seq_len)),
                out_cache_base=1_000_000 + 100 * index + 20 * generation,
            )
        )
    return tuple(requests)


def accepted_paths(request_ids: tuple[str, ...], depth: int) -> dict[str, tuple[int, ...]]:
    return {
        rid: tuple(range(1 + (index % min(depth, 4))))
        for index, rid in enumerate(request_ids)
    }


def expect_failure(name: str, operation) -> dict[str, str]:
    try:
        operation()
    except ContractError as error:
        return {"name": name, "result": "fail_closed", "error": str(error)}
    raise AssertionError(f"fixture_did_not_fail:{name}")


def main() -> None:
    router = DepthAwareCorpusRouter()

    low_requests = make_requests(7)
    low_lanes = router.produce(low_requests)
    low = pack_target_rows(low_lanes, 7)
    low_acceptance = settle_acceptance(
        low, accepted_paths(low.request_ids, low.depth)
    )
    low_carrier = AcceptedCarrier.from_acceptance(low_acceptance)
    low_graph = graph_admissible(low)
    assert low.depth == 12
    assert low.target_rows == 84
    assert low_graph == (True, "exact_depth_shape")
    assert router.corpora[12].match_calls == 1
    assert router.corpora[6].match_calls == 0

    high_requests = make_requests(8, generation=1)
    high_lanes = router.produce(high_requests)
    high = pack_target_rows(high_lanes, 8)
    high_acceptance = settle_acceptance(
        high, accepted_paths(high.request_ids, high.depth)
    )
    high_carrier = AcceptedCarrier.from_acceptance(high_acceptance)
    high_graph = graph_admissible(high)
    assert high.depth == 6
    assert high.target_rows == 48
    assert high_graph == (False, "depth_mismatch:6:12")
    assert router.corpora[12].match_calls == 1
    assert router.corpora[6].match_calls == 1
    assert router.corpora[6].erased == [f"request-{index}" for index in range(7)]

    permutation = (7, 0, 6, 1, 5, 2, 4, 3)
    permuted_requests = tuple(high_requests[index] for index in permutation)
    permuted_lanes = router.produce(permuted_requests)
    permuted = pack_target_rows(permuted_lanes, 8)
    for permuted_index, original_index in enumerate(permutation):
        original_slice = high.request_row_slice(original_index)
        permuted_slice = permuted.request_row_slice(permuted_index)
        assert high.draft_tokens[original_slice] == permuted.draft_tokens[permuted_slice]
        assert high.positions[original_slice] == permuted.positions[permuted_slice]
        original_tree_start = original_index * high.depth * high.depth
        permuted_tree_start = permuted_index * permuted.depth * permuted.depth
        assert high.tree_mask[
            original_tree_start : original_tree_start + high.depth * high.depth
        ] == permuted.tree_mask[
            permuted_tree_start : permuted_tree_start
            + permuted.depth * permuted.depth
        ]

    merge_router = DepthAwareCorpusRouter()
    merge_high = pack_target_rows(
        merge_router.produce(make_requests(8, generation=2, namespace="merged")),
        8,
    )
    merge_high_carrier = AcceptedCarrier.from_acceptance(
        settle_acceptance(
            merge_high, accepted_paths(merge_high.request_ids, merge_high.depth)
        )
    )
    mixed_carrier = low_carrier.filter((6, 0, 3)).merge(
        merge_high_carrier.filter((7, 2, 5, 0))
    )
    assert tuple(
        mixed_carrier.row_offsets[index + 1] - mixed_carrier.row_offsets[index]
        for index in range(len(mixed_carrier.request_ids))
    ) == (12, 12, 12, 6, 6, 6, 6)
    completed = {mixed_carrier.request_ids[1], mixed_carrier.request_ids[5]}
    scheduler_rows = settle_scheduler(mixed_carrier, completed)
    assert all(scheduler_rows[rid] == () for rid in completed)
    assert all(
        scheduler_rows[rid]
        for rid in set(mixed_carrier.request_ids) - completed
    )

    bad_lane = ProducerLane(
        request=high_requests[0],
        depth=12,
        draft_tokens=tuple(range(12)),
        tree_mask=tuple(
            tuple(column <= row for column in range(12)) for row in range(12)
        ),
    )
    failures = [
        expect_failure(
            "producer_consumer_depth",
            lambda: pack_target_rows((bad_lane,) + high_lanes[1:], 8),
        ),
        expect_failure(
            "tree_forward_edge",
            lambda: pack_target_rows(
                (
                    ProducerLane(
                        request=high_lanes[0].request,
                        depth=6,
                        draft_tokens=high_lanes[0].draft_tokens,
                        tree_mask=((True, True, False, False, False, False),)
                        + high_lanes[0].tree_mask[1:],
                    ),
                )
                + high_lanes[1:],
                8,
            ),
        ),
        expect_failure(
            "accept_row_oob",
            lambda: settle_acceptance(
                high,
                {
                    **accepted_paths(high.request_ids, high.depth),
                    high.request_ids[0]: (0, 6),
                },
            ),
        ),
        expect_failure(
            "carrier_terminal_offset",
            lambda: AcceptedCarrier(
                request_ids=("bad",),
                row_offsets=(0, 7),
                token_rows=(1, 2),
                accept_lens=(1,),
            ).validate(),
        ),
        expect_failure(
            "completed_request_unknown",
            lambda: settle_scheduler(high_carrier, {"not-present"}),
        ),
    ]

    low_work = analytical_work(7, 1024)
    high_work_8 = analytical_work(8, 1024)
    high_work_23 = analytical_work(23, 1024)
    high_work_24 = analytical_work(24, 1024)
    high_work_31 = analytical_work(31, 1024)
    assert low_work["eliminated_target_rows"] == 0
    assert high_work_8["eliminated_target_rows"] == 48
    assert high_work_8["eliminated_attention_mask_elements"] == 8 * (6 * 1024 + 108)

    source_bindings = {
        "ngram_info.py": SOURCE_ROOT / "speculative/ngram_info.py",
        "ngram_corpus.py": SOURCE_ROOT / "speculative/cpp_ngram/ngram_corpus.py",
        "ngram_worker.py": SOURCE_ROOT / "speculative/ngram_worker.py",
        "spec_info.py": SOURCE_ROOT / "speculative/spec_info.py",
        "decode_cuda_graph_runner.py": SOURCE_ROOT
        / "model_executor/runner/decode_cuda_graph_runner.py",
        "triton_backend.py": SOURCE_ROOT / "layers/attention/triton_backend.py",
        "spec_utils.py": SOURCE_ROOT / "speculative/spec_utils.py",
        "batch_result_processor.py": SOURCE_ROOT
        / "managers/scheduler_components/batch_result_processor.py",
    }
    output = {
        "schema_version": 1,
        "result": "all_cpu_state_fixtures_passed",
        "evidence_label": "synthetic_cpu_state_fixture_over_source_bound_contract",
        "fixtures": {
            "positive_depth_12": {
                "batch_size": low.batch_size,
                "depth": low.depth,
                "target_rows": low.target_rows,
                "qo_indptr": low.qo_indptr,
                "mask_elements": len(low.full_custom_mask),
                "kv_indices": len(low.kv_indices),
                "graph": low_graph,
            },
            "positive_depth_6": {
                "batch_size": high.batch_size,
                "depth": high.depth,
                "target_rows": high.target_rows,
                "qo_indptr": high.qo_indptr,
                "mask_elements": len(high.full_custom_mask),
                "kv_indices": len(high.kv_indices),
                "graph": high_graph,
            },
            "boundary_7_to_8": {
                "depths": [low.depth, high.depth],
                "producer_calls": {
                    str(depth): corpus.match_calls
                    for depth, corpus in sorted(router.corpora.items())
                },
                "depth_6_switch_resets": router.corpora[6].erased,
            },
            "permutation": {
                "order": permutation,
                "request_ids": permuted.request_ids,
                "per_request_tokens_positions_masks_preserved": True,
            },
            "mixed_completion_and_ragged_prior_rows": {
                "request_ids": mixed_carrier.request_ids,
                "row_offsets": mixed_carrier.row_offsets,
                "row_widths": [
                    mixed_carrier.row_offsets[index + 1]
                    - mixed_carrier.row_offsets[index]
                    for index in range(len(mixed_carrier.request_ids))
                ],
                "completed": sorted(completed),
                "scheduler_rows": {
                    rid: list(tokens) for rid, tokens in scheduler_rows.items()
                },
            },
            "acceptance_and_kv": {
                "accept_lens": high_acceptance.accept_lens,
                "num_correct_drafts": high_acceptance.num_correct_drafts,
                "accept_indices": high_acceptance.accept_indices,
                "kv_moves": high_acceptance.kv_moves,
                "ownership_validated": True,
            },
            "fail_closed": failures,
        },
        "analytical_work_examples": {
            "sequence_length": 1024,
            "running_requests_7": low_work,
            "running_requests_8": high_work_8,
            "running_requests_23": high_work_23,
            "running_requests_24": high_work_24,
            "running_requests_31": high_work_31,
        },
        "source_bindings": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in source_bindings.items()
        },
        "project_local_source": {
            "adaptive_depth_contract.py": sha256(ROOT / "adaptive_depth_contract.py"),
            "run_adaptive_depth_fixtures.py": sha256(
                ROOT / "run_adaptive_depth_fixtures.py"
            ),
        },
    }
    output_path = ROOT / "ADAPTIVE_DEPTH_CPU_FIXTURES.json"
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
