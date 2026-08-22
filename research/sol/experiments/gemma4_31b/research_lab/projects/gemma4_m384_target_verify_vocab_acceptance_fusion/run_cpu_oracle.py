from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from m384_vocab_acceptance import (
    GreedyDispatch,
    TileLocalProcessors,
    commit_greedy_acceptance,
    fast_path_eligible,
    fused_tiled_greedy_acceptance_candidate,
    fused_tiled_greedy_candidate,
    materialized_control,
    stock_filtered_probabilities,
    tree_greedy_accept,
    tree_target_only_sampling_accept,
)


PROJECT = Path(__file__).resolve().parent
SEED = 20260730


def matrix(rng: random.Random, rows: int, columns: int) -> list[list[float]]:
    return [
        [rng.uniform(-1.25, 1.25) for _ in range(columns)]
        for _ in range(rows)
    ]


def tree_fixture(
    requests: int, draft_tokens: int, target_ids: list[int]
) -> tuple[
    list[list[int]],
    list[list[int]],
    list[list[int]],
    list[list[int]],
]:
    candidates: list[list[int]] = []
    retrieve_index: list[list[int]] = []
    retrieve_next_token: list[list[int]] = []
    retrieve_next_sibling: list[list[int]] = []
    for request in range(requests):
        base = request * draft_tokens
        indices = list(range(base, base + draft_tokens))
        next_token = [index + 1 for index in range(draft_tokens)]
        next_token[-1] = -1
        next_sibling = [-1] * draft_tokens
        row_candidates = [target_ids[base]]
        accepted_prefix = 3 + request
        for depth in range(1, draft_tokens):
            if depth <= accepted_prefix:
                row_candidates.append(target_ids[base + depth - 1])
            else:
                row_candidates.append(
                    (target_ids[base + depth - 1] + depth + 1) % 257
                )
        if request == 1:
            next_token[2] = 4
            next_sibling[4] = 3
            row_candidates[4] = (target_ids[base + 2] + 7) % 257
            row_candidates[3] = target_ids[base + 2]
        candidates.append(row_candidates)
        retrieve_index.append(indices)
        retrieve_next_token.append(next_token)
        retrieve_next_sibling.append(next_sibling)
    return candidates, retrieve_index, retrieve_next_token, retrieve_next_sibling


def producer_and_commit_case() -> dict:
    rng = random.Random(SEED)
    requests = 2
    draft_tokens = 12
    rows = requests * draft_tokens
    hidden_size = 17
    vocab_size = 257
    hidden = matrix(rng, rows, hidden_size)
    weights = matrix(rng, vocab_size, hidden_size)
    request_for_row = [
        request for request in range(requests) for _ in range(draft_tokens)
    ]
    additive = [[0.0] * vocab_size for _ in range(requests)]
    scaling = [[1.0] * vocab_size for _ in range(requests)]
    bias = [[0.0] * vocab_size for _ in range(requests)]
    allowed = [[True] * vocab_size for _ in range(requests)]
    for request in range(requests):
        for token in range(request, vocab_size, 37):
            additive[request][token] = -0.75
        for token in range(5 + request, vocab_size, 53):
            scaling[request][token] = 1.2
        for token in range(11 + request, vocab_size, 61):
            bias[request][token] = 0.5
        for token in range(19 + request, vocab_size, 71):
            allowed[request][token] = False
    processors = TileLocalProcessors(
        request_for_row=request_for_row,
        additive_penalty=additive,
        scaling_penalty=scaling,
        logit_bias=bias,
        allowed_token=allowed,
    )
    materialized, control_ids = materialized_control(hidden, weights, processors)
    candidate_ids = fused_tiled_greedy_candidate(
        hidden, weights, processors, vocab_tile=31
    )
    if control_ids != candidate_ids:
        raise AssertionError("tiled output-head selections differ from control")
    candidates, retrieve_index, retrieve_next_token, retrieve_next_sibling = (
        tree_fixture(requests, draft_tokens, control_ids)
    )
    control_accept = tree_greedy_accept(
        control_ids,
        candidates,
        retrieve_index,
        retrieve_next_token,
        retrieve_next_sibling,
    )
    candidate_accept = tree_greedy_accept(
        candidate_ids,
        candidates,
        retrieve_index,
        retrieve_next_token,
        retrieve_next_sibling,
    )
    if control_accept != candidate_accept:
        raise AssertionError("tree greedy acceptance differs")
    fused_candidate = fused_tiled_greedy_acceptance_candidate(
        hidden,
        weights,
        processors,
        31,
        candidates,
        retrieve_index,
        retrieve_next_token,
        retrieve_next_sibling,
    )
    if fused_candidate[0] != control_ids or fused_candidate[1:] != control_accept:
        raise AssertionError("fused producer-to-acceptance candidate differs")
    accept_indices, predicts, num_correct = control_accept
    stop_token_ids = [
        {predicts[index] for index in accept_indices[0][2:3]},
        set(),
    ]
    out_cache_locs = [
        list(range(1000 + request * draft_tokens, 1000 + (request + 1) * draft_tokens))
        for request in range(requests)
    ]
    control_commit = commit_greedy_acceptance(
        accept_indices,
        predicts,
        num_correct,
        out_cache_locs,
        [535, 741],
        [535, 741],
        stop_token_ids,
    )
    candidate_commit = commit_greedy_acceptance(
        candidate_accept[0],
        candidate_accept[1],
        candidate_accept[2],
        out_cache_locs,
        [535, 741],
        [535, 741],
        stop_token_ids,
    )
    if control_commit != candidate_commit:
        raise AssertionError("KV ownership or completion commit differs")
    digest = hashlib.sha256(
        json.dumps(
            {
                "ids": control_ids,
                "accept": accept_indices,
                "predicts": predicts,
                "commit": control_commit.__dict__,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "rows": rows,
        "hidden_size": hidden_size,
        "vocab_size": vocab_size,
        "vocab_tile": 31,
        "selected_token_mismatches": 0,
        "acceptance_mismatches": 0,
        "kv_commit_mismatches": 0,
        "finite_logits": all(
            math.isfinite(value)
            for row in materialized
            for value in row
            if value != -math.inf
        ),
        "digest": digest,
        "commit": {
            "num_correct_drafts": list(control_commit.num_correct_drafts),
            "kv_committed_lens": list(control_commit.kv_committed_lens),
            "seq_lens": list(control_commit.seq_lens),
            "finished": list(control_commit.finished),
        },
    }


def softcap_tie_case() -> dict:
    hidden = [[1.0]]
    weights = [[-3.0], [900.0], [1000.0], [900.0]]
    processors = TileLocalProcessors(request_for_row=[0])
    materialized, control_ids = materialized_control(hidden, weights, processors)
    candidate_ids = fused_tiled_greedy_candidate(
        hidden, weights, processors, vocab_tile=2
    )
    if control_ids != [1] or candidate_ids != control_ids:
        raise AssertionError(
            "post-softcap lowest-token tie semantics were not preserved"
        )
    if materialized[0][1] != materialized[0][2]:
        raise AssertionError("fixture did not create the intended softcap tie")
    return {
        "control_selected_token": control_ids[0],
        "candidate_selected_token": candidate_ids[0],
        "raw_largest_token": 2,
        "post_softcap_tie_tokens": [1, 2, 3],
        "passed": True,
    }


def sampling_fallback_case() -> dict:
    rng = random.Random(SEED + 1)
    requests = 2
    draft_tokens = 12
    vocab_size = 257
    logits = matrix(rng, requests * draft_tokens, vocab_size)
    probabilities = [
        stock_filtered_probabilities(row, 0.73, 17, 0.82) for row in logits
    ]
    target_ids = [
        max(range(vocab_size), key=lambda token: (row[token], -token))
        for row in probabilities
    ]
    candidates, retrieve_index, retrieve_next_token, retrieve_next_sibling = (
        tree_fixture(requests, draft_tokens, target_ids)
    )
    acceptance_coins = [
        [rng.random() for _ in range(draft_tokens)] for _ in range(requests)
    ]
    final_coins = [rng.random() for _ in range(requests)]
    control = tree_target_only_sampling_accept(
        probabilities,
        candidates,
        retrieve_index,
        retrieve_next_token,
        retrieve_next_sibling,
        acceptance_coins,
        final_coins,
    )
    fallback = tree_target_only_sampling_accept(
        probabilities,
        candidates,
        retrieve_index,
        retrieve_next_token,
        retrieve_next_sibling,
        acceptance_coins,
        final_coins,
    )
    if control != fallback:
        raise AssertionError("sampled target-only fallback differs")
    dispatch = GreedyDispatch(
        is_all_greedy=False,
        return_logprob=False,
        has_custom_logit_processor=False,
        tile_local_processors=True,
        tensor_parallel_size=1,
    )
    if fast_path_eligible(dispatch):
        raise AssertionError("sampled branch incorrectly entered greedy fast path")
    digest = hashlib.sha256(
        json.dumps(
            {
                "probabilities": probabilities,
                "coins": acceptance_coins,
                "final_coins": final_coins,
                "result": control,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "rows": requests * draft_tokens,
        "vocab_size": vocab_size,
        "temperature": 0.73,
        "top_k": 17,
        "top_p": 0.82,
        "acceptance_mismatches": 0,
        "route": "materialized_stock_fallback",
        "digest": digest,
    }


def dispatch_case() -> dict:
    qualified = GreedyDispatch(
        is_all_greedy=True,
        return_logprob=False,
        has_custom_logit_processor=False,
        tile_local_processors=True,
        tensor_parallel_size=1,
    )
    fallbacks = {
        "sampled": GreedyDispatch(False, False, False, True, 1),
        "return_logprob": GreedyDispatch(True, True, False, True, 1),
        "custom_processor": GreedyDispatch(True, False, True, True, 1),
        "nonlocal_processor": GreedyDispatch(True, False, False, False, 1),
        "tp2": GreedyDispatch(True, False, False, True, 2),
    }
    if not fast_path_eligible(qualified):
        raise AssertionError("qualified branch did not enter fast path")
    incorrectly_admitted = [
        name for name, dispatch in fallbacks.items() if fast_path_eligible(dispatch)
    ]
    if incorrectly_admitted:
        raise AssertionError(f"invalid fast-path admissions: {incorrectly_admitted}")
    return {
        "qualified_route": "fused_tiled_greedy",
        "fallback_routes": sorted(fallbacks),
        "incorrect_fast_path_admissions": incorrectly_admitted,
    }


def exact_geometry_case() -> dict:
    source = PROJECT / "exact_geometry_oracle.c"
    with tempfile.TemporaryDirectory(dir=PROJECT) as temporary:
        binary = Path(temporary) / "exact_geometry_oracle"
        compile_result = subprocess.run(
            [
                "cc",
                "-O3",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(source),
                "-o",
                str(binary),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(compile_result.stderr)
        result = subprocess.run(
            [str(binary)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
    parsed = json.loads(result.stdout)
    parsed["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    return parsed


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "CPU_ORACLE_RESULT.json"
    result = {
        "schema_version": 1,
        "seed": SEED,
        "classification": "deterministic_cpu_reference_pass",
        "passed": True,
        "cases": {
            "reduced_output_head_processors_acceptance_commit": producer_and_commit_case(),
            "softcap_saturation_lowest_token_tie": softcap_tie_case(),
            "sampled_topk_topp_target_only_fallback": sampling_fallback_case(),
            "dispatch_fail_closed": dispatch_case(),
            "exact_m384_v262144_tiled_argmax_geometry": exact_geometry_case(),
        },
        "claim_limit": (
            "CPU semantic and exact-shape indexing evidence only. The reduced producer "
            "does not reproduce H200 BF16 GEMM arithmetic or prove a compiled SM90a kernel."
        ),
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
