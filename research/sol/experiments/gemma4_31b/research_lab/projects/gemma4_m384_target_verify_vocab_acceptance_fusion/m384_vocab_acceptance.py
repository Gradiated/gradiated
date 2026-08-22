from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


Matrix = Sequence[Sequence[float]]


@dataclass(frozen=True)
class TileLocalProcessors:
    request_for_row: Sequence[int]
    additive_penalty: Optional[Matrix] = None
    scaling_penalty: Optional[Matrix] = None
    logit_bias: Optional[Matrix] = None
    allowed_token: Optional[Sequence[Sequence[bool]]] = None


@dataclass(frozen=True)
class GreedyDispatch:
    is_all_greedy: bool
    return_logprob: bool
    has_custom_logit_processor: bool
    tile_local_processors: bool
    tensor_parallel_size: int


@dataclass(frozen=True)
class GreedyCommit:
    accept_indices: tuple[tuple[int, ...], ...]
    accepted_tokens: tuple[tuple[int, ...], ...]
    num_correct_drafts: tuple[int, ...]
    committed_cache_locs: tuple[tuple[int, ...], ...]
    freed_cache_locs: tuple[tuple[int, ...], ...]
    kv_committed_lens: tuple[int, ...]
    seq_lens: tuple[int, ...]
    finished: tuple[bool, ...]


def fast_path_eligible(dispatch: GreedyDispatch) -> bool:
    return (
        dispatch.is_all_greedy
        and not dispatch.return_logprob
        and not dispatch.has_custom_logit_processor
        and dispatch.tile_local_processors
        and dispatch.tensor_parallel_size == 1
    )


def round_float32_to_bfloat16(value: float) -> float:
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    exponent = bits & 0x7F800000
    mantissa = bits & 0x007FFFFF
    if exponent == 0x7F800000 and mantissa != 0:
        rounded = bits | 0x00400000
    else:
        rounded = bits + 0x7FFF + ((bits >> 16) & 1)
    return struct.unpack("<f", struct.pack("<I", rounded & 0xFFFF0000))[0]


def project_one(hidden: Sequence[float], weight: Sequence[float]) -> float:
    accumulator = 0.0
    for hidden_value, weight_value in zip(hidden, weight):
        accumulator += hidden_value * weight_value
    return round_float32_to_bfloat16(accumulator)


def postprocess_one(
    value: float,
    row: int,
    token: int,
    processors: TileLocalProcessors,
    softcap: float,
) -> float:
    value = softcap * math.tanh(value / softcap)
    request = processors.request_for_row[row]
    if processors.additive_penalty is not None:
        value += processors.additive_penalty[request][token]
    if processors.scaling_penalty is not None:
        scale = processors.scaling_penalty[request][token]
        value = value * scale if value < 0 else value / scale
    if processors.logit_bias is not None:
        value += processors.logit_bias[request][token]
    if (
        processors.allowed_token is not None
        and not processors.allowed_token[request][token]
    ):
        return -math.inf
    return value


def materialized_control(
    hidden_states: Matrix,
    lm_head_weight: Matrix,
    processors: TileLocalProcessors,
    softcap: float = 30.0,
) -> tuple[list[list[float]], list[int]]:
    materialized: list[list[float]] = []
    selected: list[int] = []
    for row, hidden in enumerate(hidden_states):
        logits = [
            postprocess_one(
                project_one(hidden, weight), row, token, processors, softcap
            )
            for token, weight in enumerate(lm_head_weight)
        ]
        materialized.append(logits)
        selected.append(argmax_lowest_id(logits))
    return materialized, selected


def fused_tiled_greedy_candidate(
    hidden_states: Matrix,
    lm_head_weight: Matrix,
    processors: TileLocalProcessors,
    vocab_tile: int,
    softcap: float = 30.0,
) -> list[int]:
    if vocab_tile <= 0:
        raise ValueError("vocab_tile must be positive")
    selected: list[int] = []
    vocab_size = len(lm_head_weight)
    for row, hidden in enumerate(hidden_states):
        best_value = -math.inf
        best_token = 0
        for tile_start in range(0, vocab_size, vocab_tile):
            tile_stop = min(tile_start + vocab_tile, vocab_size)
            tile_value = -math.inf
            tile_token = tile_start
            for token in range(tile_start, tile_stop):
                value = postprocess_one(
                    project_one(hidden, lm_head_weight[token]),
                    row,
                    token,
                    processors,
                    softcap,
                )
                if value > tile_value or (
                    value == tile_value and token < tile_token
                ):
                    tile_value = value
                    tile_token = token
            if tile_value > best_value or (
                tile_value == best_value and tile_token < best_token
            ):
                best_value = tile_value
                best_token = tile_token
        selected.append(best_token)
    return selected


def fused_tiled_greedy_acceptance_candidate(
    hidden_states: Matrix,
    lm_head_weight: Matrix,
    processors: TileLocalProcessors,
    vocab_tile: int,
    candidates: Sequence[Sequence[int]],
    retrieve_index: Sequence[Sequence[int]],
    retrieve_next_token: Sequence[Sequence[int]],
    retrieve_next_sibling: Sequence[Sequence[int]],
    softcap: float = 30.0,
) -> tuple[list[int], list[list[int]], list[int], list[int]]:
    selected = fused_tiled_greedy_candidate(
        hidden_states,
        lm_head_weight,
        processors,
        vocab_tile,
        softcap,
    )
    accept_indices, predicts, num_correct_drafts = tree_greedy_accept(
        selected,
        candidates,
        retrieve_index,
        retrieve_next_token,
        retrieve_next_sibling,
    )
    return selected, accept_indices, predicts, num_correct_drafts


def tiled_argmax_from_logits(
    row_count: int,
    vocab_size: int,
    vocab_tile: int,
    value_at: Callable[[int, int], float],
) -> list[int]:
    selected: list[int] = []
    for row in range(row_count):
        best_value = -math.inf
        best_token = 0
        for tile_start in range(0, vocab_size, vocab_tile):
            tile_stop = min(tile_start + vocab_tile, vocab_size)
            for token in range(tile_start, tile_stop):
                value = value_at(row, token)
                if value > best_value or (
                    value == best_value and token < best_token
                ):
                    best_value = value
                    best_token = token
        selected.append(best_token)
    return selected


def argmax_lowest_id(values: Sequence[float]) -> int:
    best_token = 0
    best_value = values[0]
    for token, value in enumerate(values[1:], 1):
        if value > best_value:
            best_value = value
            best_token = token
    return best_token


def tree_greedy_accept(
    target_predict: Sequence[int],
    candidates: Sequence[Sequence[int]],
    retrieve_index: Sequence[Sequence[int]],
    retrieve_next_token: Sequence[Sequence[int]],
    retrieve_next_sibling: Sequence[Sequence[int]],
) -> tuple[list[list[int]], list[int], list[int]]:
    batch_size = len(candidates)
    draft_token_num = len(candidates[0])
    accept_indices = [[-1] * draft_token_num for _ in range(batch_size)]
    predicts = [-1] * len(target_predict)
    num_correct_drafts = [0] * batch_size
    for request in range(batch_size):
        last_accepted = retrieve_index[request][0]
        accept_indices[request][0] = last_accepted
        current = 0
        for depth in range(1, draft_token_num):
            current = retrieve_next_token[request][current]
            while current != -1:
                draft_index = retrieve_index[request][current]
                draft_token = candidates[request][current]
                target_token = target_predict[last_accepted]
                if draft_token == target_token:
                    predicts[last_accepted] = target_token
                    num_correct_drafts[request] += 1
                    accept_indices[request][
                        num_correct_drafts[request]
                    ] = draft_index
                    last_accepted = draft_index
                    break
                current = retrieve_next_sibling[request][current]
            if current == -1:
                break
        predicts[last_accepted] = target_predict[last_accepted]
    return accept_indices, predicts, num_correct_drafts


def commit_greedy_acceptance(
    accept_indices: Sequence[Sequence[int]],
    predicts: Sequence[int],
    num_correct_drafts: Sequence[int],
    out_cache_locs: Sequence[Sequence[int]],
    initial_kv_committed_lens: Sequence[int],
    initial_seq_lens: Sequence[int],
    stop_token_ids: Sequence[set[int]],
) -> GreedyCommit:
    final_indices: list[tuple[int, ...]] = []
    accepted_tokens: list[tuple[int, ...]] = []
    committed_cache_locs: list[tuple[int, ...]] = []
    freed_cache_locs: list[tuple[int, ...]] = []
    committed_lens: list[int] = []
    seq_lens: list[int] = []
    finished: list[bool] = []
    corrected_drafts: list[int] = []
    for request, row in enumerate(accept_indices):
        valid = [index for index in row if index != -1]
        tokens: list[int] = []
        kept: list[int] = []
        is_finished = False
        for index in valid:
            token = predicts[index]
            kept.append(index)
            tokens.append(token)
            if token in stop_token_ids[request]:
                is_finished = True
                break
        accepted_count = len(kept)
        corrected_drafts.append(max(0, accepted_count - 1))
        final_indices.append(tuple(kept))
        accepted_tokens.append(tuple(tokens))
        locs = out_cache_locs[request]
        committed_cache_locs.append(tuple(locs[:accepted_count]))
        freed_cache_locs.append(tuple(locs[accepted_count:]))
        committed_lens.append(
            initial_kv_committed_lens[request] + accepted_count
        )
        seq_lens.append(initial_seq_lens[request] + accepted_count)
        finished.append(is_finished)
    return GreedyCommit(
        accept_indices=tuple(final_indices),
        accepted_tokens=tuple(accepted_tokens),
        num_correct_drafts=tuple(corrected_drafts),
        committed_cache_locs=tuple(committed_cache_locs),
        freed_cache_locs=tuple(freed_cache_locs),
        kv_committed_lens=tuple(committed_lens),
        seq_lens=tuple(seq_lens),
        finished=tuple(finished),
    )


def stock_filtered_probabilities(
    logits: Sequence[float],
    temperature: float,
    top_k: int,
    top_p: float,
) -> list[float]:
    scaled = [value / temperature for value in logits]
    maximum = max(scaled)
    unnormalized = [math.exp(value - maximum) for value in scaled]
    normalizer = sum(unnormalized)
    probabilities = [value / normalizer for value in unnormalized]
    ranked = sorted(range(len(probabilities)), key=lambda token: (-probabilities[token], token))
    if top_k > 0:
        ranked = ranked[:top_k]
    top_k_mass = sum(probabilities[token] for token in ranked)
    top_k_probabilities = {
        token: probabilities[token] / top_k_mass for token in ranked
    }
    cumulative = 0.0
    kept: list[int] = []
    for token in ranked:
        probability = top_k_probabilities[token]
        if cumulative > top_p:
            break
        kept.append(token)
        cumulative += probability
    kept_mass = sum(top_k_probabilities[token] for token in kept)
    filtered = [0.0] * len(probabilities)
    for token in kept:
        filtered[token] = top_k_probabilities[token] / kept_mass
    return filtered


def tree_target_only_sampling_accept(
    target_probabilities: Sequence[Sequence[float]],
    candidates: Sequence[Sequence[int]],
    retrieve_index: Sequence[Sequence[int]],
    retrieve_next_token: Sequence[Sequence[int]],
    retrieve_next_sibling: Sequence[Sequence[int]],
    acceptance_coins: Sequence[Sequence[float]],
    final_coins: Sequence[float],
    threshold_single: float = 1.0,
    threshold_acc: float = 1.0,
) -> tuple[list[list[int]], list[int], list[int]]:
    batch_size = len(candidates)
    draft_token_num = len(candidates[0])
    predicts = [-1] * len(target_probabilities)
    accept_indices = [[-1] * draft_token_num for _ in range(batch_size)]
    num_correct_drafts = [0] * batch_size
    for request in range(batch_size):
        probability_row = request * draft_token_num
        last_accepted = retrieve_index[request][0]
        accept_indices[request][0] = last_accepted
        current = 0
        probability_accumulator = 0.0
        coin = acceptance_coins[request][0]
        rejected: dict[int, float] = {}
        for depth in range(1, draft_token_num):
            current = retrieve_next_token[request][current]
            while current != -1:
                draft_index = retrieve_index[request][current]
                draft_token = candidates[request][current]
                probability = target_probabilities[probability_row][draft_token]
                probability_accumulator += probability
                if (
                    coin <= probability_accumulator / threshold_acc
                    or probability >= threshold_single
                ):
                    probability_accumulator = 0.0
                    probability_row = request * draft_token_num + current
                    coin = acceptance_coins[request][current]
                    predicts[last_accepted] = draft_token
                    num_correct_drafts[request] += 1
                    accept_indices[request][
                        num_correct_drafts[request]
                    ] = draft_index
                    last_accepted = draft_index
                    rejected = {}
                    break
                rejected[draft_token] = target_probabilities[probability_row][draft_token]
                current = retrieve_next_sibling[request][current]
            if current == -1:
                break
        residual = [
            max(probability - rejected.get(token, 0.0), 0.0)
            for token, probability in enumerate(target_probabilities[probability_row])
        ]
        total = sum(residual)
        target = final_coins[request] * total
        cumulative = 0.0
        sampled = len(residual) - 1
        last_valid = -1
        for token, probability in enumerate(residual):
            if probability <= 0:
                continue
            last_valid = token
            cumulative += probability
            if cumulative > target:
                sampled = token
                break
        if total == 0 and last_valid != -1:
            sampled = last_valid
        predicts[last_accepted] = sampled
    return accept_indices, predicts, num_correct_drafts
