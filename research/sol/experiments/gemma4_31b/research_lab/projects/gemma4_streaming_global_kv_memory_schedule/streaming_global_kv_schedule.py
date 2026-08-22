"""Layer-local c32 schedule for the activated compact global-KV consumer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import multiresolution_global_kv as activated


ACTIVATED_SOURCE_SHA256 = (
    "47c1dd902dd287cab2403cb06790095a3e041df434e48ffe22832dfdad4d4880"
)
STREAM_CHUNK_TOKENS = 8


def verify_activated_source() -> None:
    observed = hashlib.sha256(Path(activated.__file__).read_bytes()).hexdigest()
    if observed != ACTIVATED_SOURCE_SHA256:
        raise RuntimeError(
            f"activated_source_digest_mismatch:{observed}:{ACTIVATED_SOURCE_SHA256}"
        )


@dataclass
class LayerRequest:
    phase: str
    q: activated.torch.Tensor
    exact_post_rope_k: activated.torch.Tensor
    exact_v: activated.torch.Tensor
    query_start: int
    summary_state: activated.IncrementalGlobalSummaryState
    protected_positions: Sequence[int] = ()
    commit_after_consume: bool = True


@dataclass(frozen=True)
class _EntryTensor:
    k: activated.torch.Tensor
    v: activated.torch.Tensor
    count: int
    causal_end: int


def _materialization_entries(
    state: activated.IncrementalGlobalSummaryState,
    exact_k: activated.torch.Tensor,
    exact_v: activated.torch.Tensor,
    query_start: int,
    query_count: int,
) -> list[_EntryTensor]:
    if query_start != state.committed_tokens:
        raise RuntimeError("summary_request_ownership_or_position_mismatch")
    query_end = query_start + query_count
    if exact_k.shape[0] < query_end or exact_k.shape != exact_v.shape:
        raise ValueError("exact_global_kv_sequence_mismatch")
    old_end = max(0, query_start - activated.RECENT_EXACT_TOKENS)
    complete_blocks = old_end // activated.SUMMARY_BLOCK_TOKENS
    entries = [
        _EntryTensor(k, v, count, (index + 1) * activated.SUMMARY_BLOCK_TOKENS - 1)
        for index, (k, v, count) in enumerate(
            zip(
                state.full_k[:complete_blocks],
                state.full_v[:complete_blocks],
                state.full_counts[:complete_blocks],
                strict=True,
            )
        )
    ]

    partial_start = complete_blocks * activated.SUMMARY_BLOCK_TOKENS
    if partial_start < old_end:
        block_index = complete_blocks
        if block_index < len(state.full_k):
            block_end = (block_index + 1) * activated.SUMMARY_BLOCK_TOKENS
            partial_k_sum = state.full_k[block_index] * state.full_counts[block_index]
            partial_v_sum = state.full_v[block_index] * state.full_counts[block_index]
            partial_count = state.full_counts[block_index]
            subtract_end = block_end
        else:
            partial_k_sum = state.partial_k.clone()
            partial_v_sum = state.partial_v.clone()
            partial_count = state.partial_count
            subtract_end = query_start
        for position in range(old_end, subtract_end):
            if position in state._protected:
                continue
            partial_k_sum.sub_(exact_k[position].float())
            partial_v_sum.sub_(exact_v[position].float())
            partial_count -= 1
        if partial_count:
            entries.append(
                _EntryTensor(
                    partial_k_sum / partial_count,
                    partial_v_sum / partial_count,
                    partial_count,
                    old_end - 1,
                )
            )

    exact_positions = sorted(
        {
            position
            for position in state.protected_positions
            if position < query_end
        }.union(range(old_end, query_end))
    )
    entries.extend(
        _EntryTensor(exact_k[position], exact_v[position], 1, position)
        for position in exact_positions
    )
    if len(entries) > activated.COMPACT_TILE_TOKENS:
        raise RuntimeError("compact_tile_overflow")
    return entries


def _entry_chunks(
    entries: Sequence[_EntryTensor], dtype: activated.torch.dtype
):
    for start in range(0, len(entries), STREAM_CHUNK_TOKENS):
        chunk = entries[start : start + STREAM_CHUNK_TOKENS]
        exemplar = chunk[0].k
        yield (
            activated.torch.stack([entry.k.to(dtype) for entry in chunk]),
            activated.torch.stack([entry.v.to(dtype) for entry in chunk]),
            activated.torch.tensor(
                [entry.count for entry in chunk],
                device=exemplar.device,
                dtype=activated.torch.int32,
            ),
            activated.torch.tensor(
                [entry.causal_end for entry in chunk],
                device=exemplar.device,
                dtype=activated.torch.int32,
            ),
        )


if activated.triton is not None:
    triton = activated.triton
    tl = activated.tl

    @triton.jit
    def _online_chunk_kernel(
        q_ptr,
        k_ptr,
        v_ptr,
        counts_ptr,
        causal_ends_ptr,
        running_max_ptr,
        running_sum_ptr,
        running_acc_ptr,
        query_position,
        chunk_count,
        scale: tl.constexpr,
        BLOCK_N: tl.constexpr,
        BLOCK_D: tl.constexpr,
    ):
        query_head = tl.program_id(0)
        kv_head = query_head // 8
        dimensions = tl.arange(0, BLOCK_D)
        keys = tl.arange(0, BLOCK_N)
        key_mask = keys < chunk_count
        q = tl.load(q_ptr + query_head * BLOCK_D + dimensions)
        k_offsets = (
            keys[None, :] * 4 * BLOCK_D
            + kv_head * BLOCK_D
            + dimensions[:, None]
        )
        k = tl.load(k_ptr + k_offsets, mask=key_mask[None, :], other=0.0)
        logits = tl.sum(q[:, None] * k, axis=0) * scale
        counts = tl.load(counts_ptr + keys, mask=key_mask, other=1).to(tl.float32)
        causal_ends = tl.load(
            causal_ends_ptr + keys, mask=key_mask, other=2**31 - 1
        )
        valid = key_mask & (causal_ends <= query_position)
        logits += tl.log(counts)
        logits = tl.where(valid, logits, float("-inf"))
        chunk_max = tl.max(logits, axis=0)
        old_max = tl.load(running_max_ptr + query_head)
        new_max = tl.maximum(old_max, chunk_max)
        old_scale = tl.where(
            old_max == float("-inf"), 0.0, tl.exp(old_max - new_max)
        )
        weights = tl.where(valid, tl.exp(logits - new_max), 0.0)
        chunk_sum = tl.sum(weights, axis=0)
        v_offsets = (
            keys[:, None] * 4 * BLOCK_D
            + kv_head * BLOCK_D
            + dimensions[None, :]
        )
        v = tl.load(v_ptr + v_offsets, mask=key_mask[:, None], other=0.0)
        chunk_acc = tl.sum(weights[:, None] * v, axis=0)
        acc_offsets = query_head * BLOCK_D + dimensions
        old_acc = tl.load(running_acc_ptr + acc_offsets)
        old_sum = tl.load(running_sum_ptr + query_head)
        tl.store(running_max_ptr + query_head, new_max)
        tl.store(running_sum_ptr + query_head, old_sum * old_scale + chunk_sum)
        tl.store(running_acc_ptr + acc_offsets, old_acc * old_scale + chunk_acc)

    @triton.jit
    def _online_finalize_kernel(
        output_ptr,
        running_sum_ptr,
        running_acc_ptr,
        BLOCK_D: tl.constexpr,
    ):
        query_head = tl.program_id(0)
        dimensions = tl.arange(0, BLOCK_D)
        offsets = query_head * BLOCK_D + dimensions
        denominator = tl.load(running_sum_ptr + query_head)
        output = tl.load(running_acc_ptr + offsets) / denominator
        tl.store(output_ptr + offsets, output)


def _consume_entries_row_into(
    q_row: activated.torch.Tensor,
    query_position: int,
    entries: Sequence[_EntryTensor],
) -> None:
    running_max = activated.torch.full(
        (32,), float("-inf"), device=q_row.device, dtype=activated.torch.float32
    )
    running_sum = activated.torch.zeros(
        (32,), device=q_row.device, dtype=activated.torch.float32
    )
    running_acc = activated.torch.zeros(
        (32, activated.GLOBAL_HEAD_DIM),
        device=q_row.device,
        dtype=activated.torch.float32,
    )
    if q_row.is_cuda and activated.triton is not None:
        for compact_k, compact_v, counts, causal_ends in _entry_chunks(
            entries, q_row.dtype
        ):
            _online_chunk_kernel[(32,)](
                q_row,
                compact_k,
                compact_v,
                counts,
                causal_ends,
                running_max,
                running_sum,
                running_acc,
                query_position,
                compact_k.shape[0],
                activated.GLOBAL_HEAD_DIM**-0.5,
                BLOCK_N=STREAM_CHUNK_TOKENS,
                BLOCK_D=activated.GLOBAL_HEAD_DIM,
                num_warps=8,
                num_stages=1,
            )
        _online_finalize_kernel[(32,)](
            q_row,
            running_sum,
            running_acc,
            BLOCK_D=activated.GLOBAL_HEAD_DIM,
            num_warps=8,
        )
        return

    q_grouped = q_row.float().view(4, 8, activated.GLOBAL_HEAD_DIM)
    acc_grouped = running_acc.view(4, 8, activated.GLOBAL_HEAD_DIM)
    max_grouped = running_max.view(4, 8)
    sum_grouped = running_sum.view(4, 8)
    for compact_k, compact_v, counts, causal_ends in _entry_chunks(
        entries, q_row.dtype
    ):
        logits = activated.torch.einsum(
            "hgd,khd->hgk", q_grouped, compact_k.float()
        )
        logits.mul_(activated.GLOBAL_HEAD_DIM**-0.5)
        logits.add_(counts.float().log().view(1, 1, -1))
        logits.masked_fill_(
            causal_ends.view(1, 1, -1) > query_position, float("-inf")
        )
        chunk_max = logits.max(dim=-1).values
        new_max = activated.torch.maximum(max_grouped, chunk_max)
        old_scale = activated.torch.where(
            activated.torch.isneginf(max_grouped),
            activated.torch.zeros_like(max_grouped),
            activated.torch.exp(max_grouped - new_max),
        )
        weights = activated.torch.exp(logits - new_max.unsqueeze(-1))
        chunk_sum = weights.sum(dim=-1)
        chunk_acc = activated.torch.einsum(
            "hgk,khd->hgd", weights, compact_v.float()
        )
        acc_grouped.mul_(old_scale.unsqueeze(-1)).add_(chunk_acc)
        sum_grouped.mul_(old_scale).add_(chunk_sum)
        max_grouped.copy_(new_max)
    q_row.copy_(
        (acc_grouped / sum_grouped.unsqueeze(-1))
        .to(q_row.dtype)
        .reshape(32, activated.GLOBAL_HEAD_DIM)
    )


def forward_layer_local_inplace(
    requests: Sequence[LayerRequest],
) -> dict[str, int]:
    """Consume a single model layer request-by-request with bounded scratch.

    Each request's compact tensors die before the next request is materialized.
    The query buffer is overwritten only after its query rows have been fully
    consumed by the attention kernel.
    """

    verify_activated_source()
    peak_compact_tokens = 0
    processed_query_rows = 0
    for request in requests:
        if request.phase not in activated.CLAIMED_PHASES:
            raise RuntimeError("unsupported_global_attention_phase")
        if tuple(request.protected_positions) != (
            request.summary_state.protected_positions
        ):
            raise RuntimeError("protected_position_identity_mismatch")
        activated.build_compact_block_plan(
            request.query_start,
            request.q.shape[0],
            protected_positions=request.protected_positions,
        )
        entries = _materialization_entries(
            request.summary_state,
            request.exact_post_rope_k,
            request.exact_v,
            request.query_start,
            request.q.shape[0],
        )
        peak_compact_tokens = max(peak_compact_tokens, len(entries))
        processed_query_rows += int(request.q.shape[0])
        for row in range(request.q.shape[0]):
            _consume_entries_row_into(
                request.q[row],
                request.query_start + row,
                entries,
            )
        if request.commit_after_consume:
            request.summary_state.append_committed(
                request.exact_post_rope_k[
                    request.query_start : request.query_start + request.q.shape[0]
                ],
                request.exact_v[
                    request.query_start : request.query_start + request.q.shape[0]
                ],
            )
        del entries
    return {
        "requests": len(requests),
        "processed_query_rows": processed_query_rows,
        "peak_live_request_materializations": min(len(requests), 1),
        "peak_compact_tokens": peak_compact_tokens,
    }
