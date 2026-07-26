from __future__ import annotations

import json
import os
from dataclasses import dataclass

import torch
import triton
import triton.language as tl


BLOCK_M = 16
BLOCK_N = 64
PARTITION_N = 512
VALUE_BLOCK = 64
LOCAL_PREFIX_CAPACITY = 1024
GLOBAL_PREFIX_CAPACITY = 4608
KERNEL_BLOCK_M = tl.constexpr(16)
KERNEL_BLOCK_N = tl.constexpr(64)
KERNEL_PARTITION_N = tl.constexpr(512)
KERNEL_VALUE_BLOCK = tl.constexpr(64)
_workspace_cache: dict[tuple[object, ...], "Workspace"] = {}
_dispatch_counts = {"local_d256": 0, "global_d512": 0}


@dataclass(frozen=True)
class Workspace:
    partial_max: torch.Tensor
    partial_sum: torch.Tensor
    merged_max: torch.Tensor
    merged_sum: torch.Tensor
    scores: torch.Tensor


def packed_m384_dispatch_audit() -> dict[str, int]:
    return dict(_dispatch_counts)


def _audit_dispatch(kind: str, prefix_tokens: int, partitions: int) -> None:
    _dispatch_counts[kind] += 1
    path = os.environ.get("PACKED_M384_AUDIT")
    if not path:
        return
    record = {
        "candidate": "packed_score_producer_value_consumer_m384",
        "kind": kind,
        "block_m": BLOCK_M,
        "block_n": BLOCK_N,
        "partition_n": PARTITION_N,
        "value_block": VALUE_BLOCK,
        "prefix_tokens": prefix_tokens,
        "partitions": partitions,
        "dispatch_count": _dispatch_counts[kind],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


@triton.jit
def _score_partition_kernel(
    q_ptr,
    k_extend_ptr,
    k_cache_ptr,
    qo_indptr_ptr,
    kv_indptr_ptr,
    kv_indices_ptr,
    mask_ptr,
    mask_indptr_ptr,
    partial_max_ptr,
    partial_sum_ptr,
    scores_ptr,
    sm_scale,
    k_scale,
    kv_group_num,
    stride_qt,
    stride_qh,
    stride_kt,
    stride_kh,
    stride_kct,
    stride_kch,
    PREFIX_TOKENS: tl.constexpr,
    SCORE_STRIDE: tl.constexpr,
    PARTITIONS: tl.constexpr,
    HEADS: tl.constexpr,
    HEAD_DIM: tl.constexpr,
    SLIDING_WINDOW_SIZE: tl.constexpr,
    USE_CUSTOM_MASK: tl.constexpr,
    SKIP_PREFIX_CUSTOM_MASK: tl.constexpr,
):
    sequence = tl.program_id(0)
    query_head = tl.program_id(1)
    partition = tl.program_id(2)
    kv_head = query_head // kv_group_num
    q_start = tl.load(qo_indptr_ptr + sequence)
    q_length = tl.load(qo_indptr_ptr + sequence + 1) - q_start
    kv_start = tl.load(kv_indptr_ptr + sequence)
    prefix_length = tl.load(kv_indptr_ptr + sequence + 1) - kv_start

    rows = tl.arange(0, KERNEL_BLOCK_M)
    row_mask = rows < q_length
    dims = tl.arange(0, HEAD_DIM)
    q_offsets = (
        (q_start + rows[:, None]) * stride_qt
        + query_head * stride_qh
        + dims[None, :]
    )
    q = tl.load(q_ptr + q_offsets, mask=row_mask[:, None], other=0.0)
    running_max = tl.full((KERNEL_BLOCK_M,), -float("inf"), tl.float32)
    running_sum = tl.zeros((KERNEL_BLOCK_M,), tl.float32)
    cols = tl.arange(0, KERNEL_BLOCK_N)
    partition_start = partition * KERNEL_PARTITION_N
    score_row_base = (
        (sequence * HEADS + query_head) * KERNEL_BLOCK_M + rows
    ) * SCORE_STRIDE

    if USE_CUSTOM_MASK:
        mask_start = tl.load(mask_indptr_ptr + sequence)
        mask_stride = tl.load(mask_indptr_ptr + sequence + 1) - mask_start
        original_total_length = mask_stride // q_length
        original_prefix_length = original_total_length - q_length
        window_offset = original_prefix_length - prefix_length

    for tile in range(0, KERNEL_PARTITION_N // KERNEL_BLOCK_N):
        prefix_col = partition_start + tile * KERNEL_BLOCK_N + cols
        col_mask = prefix_col < prefix_length
        physical_slot = tl.load(
            kv_indices_ptr + kv_start + prefix_col,
            mask=col_mask,
            other=0,
        )
        k_offsets = (
            physical_slot[None, :] * stride_kct
            + kv_head * stride_kch
            + dims[:, None]
        )
        k = tl.load(
            k_cache_ptr + k_offsets,
            mask=col_mask[None, :],
            other=0.0,
        )
        scores = tl.dot(q.to(k.dtype), k) * (sm_scale * k_scale)
        valid = row_mask[:, None] & col_mask[None, :]
        if SLIDING_WINDOW_SIZE > 0:
            valid &= (
                prefix_length + rows[:, None]
                <= prefix_col[None, :] + SLIDING_WINDOW_SIZE
            )
        if USE_CUSTOM_MASK and not SKIP_PREFIX_CUSTOM_MASK:
            prefix_mask = tl.load(
                mask_ptr
                + mask_start
                + rows[:, None] * original_total_length
                + window_offset
                + prefix_col[None, :],
                mask=valid,
                other=0,
            )
            valid &= prefix_mask
        scores = tl.where(valid, scores, -float("inf"))
        persisted_scores = scores.to(tl.bfloat16)
        tl.store(
            scores_ptr + score_row_base[:, None] + prefix_col[None, :],
            persisted_scores,
            mask=row_mask[:, None] & col_mask[None, :],
        )
        scores = persisted_scores.to(tl.float32)
        tile_max = tl.max(scores, axis=1)
        new_max = tl.maximum(running_max, tile_max)
        old_scale = tl.where(
            running_max == -float("inf"),
            0.0,
            tl.exp(running_max - new_max),
        )
        probabilities = tl.where(
            valid, tl.exp(scores - new_max[:, None]), 0.0
        )
        running_sum = (
            running_sum * old_scale + tl.sum(probabilities, axis=1)
        )
        running_max = new_max

    if partition == 0:
        extend_col = cols
        extend_mask = extend_col < q_length
        k_offsets = (
            (q_start + extend_col[None, :]) * stride_kt
            + kv_head * stride_kh
            + dims[:, None]
        )
        k = tl.load(
            k_extend_ptr + k_offsets,
            mask=extend_mask[None, :],
            other=0.0,
        )
        scores = tl.dot(q, k, out_dtype=tl.float32) * sm_scale
        valid = (
            row_mask[:, None]
            & extend_mask[None, :]
            & (rows[:, None] >= extend_col[None, :])
        )
        if USE_CUSTOM_MASK:
            custom = tl.load(
                mask_ptr
                + mask_start
                + rows[:, None] * original_total_length
                + original_prefix_length
                + extend_col[None, :],
                mask=valid,
                other=0,
            )
            valid &= custom
        scores = tl.where(valid, scores, -float("inf"))
        persisted_scores = scores.to(tl.bfloat16)
        tl.store(
            scores_ptr
            + score_row_base[:, None]
            + PREFIX_TOKENS
            + extend_col[None, :],
            persisted_scores,
            mask=row_mask[:, None] & extend_mask[None, :],
        )
        scores = persisted_scores.to(tl.float32)
        tile_max = tl.max(scores, axis=1)
        new_max = tl.maximum(running_max, tile_max)
        old_scale = tl.where(
            running_max == -float("inf"),
            0.0,
            tl.exp(running_max - new_max),
        )
        probabilities = tl.where(
            valid, tl.exp(scores - new_max[:, None]), 0.0
        )
        running_sum = (
            running_sum * old_scale + tl.sum(probabilities, axis=1)
        )
        running_max = new_max

    state_base = (
        ((partition * 32 + sequence) * HEADS + query_head)
        * KERNEL_BLOCK_M
        + rows
    )
    tl.store(partial_max_ptr + state_base, running_max, mask=row_mask)
    tl.store(partial_sum_ptr + state_base, running_sum, mask=row_mask)


@triton.jit
def _merge_state_kernel(
    partial_max_ptr,
    partial_sum_ptr,
    merged_max_ptr,
    merged_sum_ptr,
    qo_indptr_ptr,
    PARTITIONS: tl.constexpr,
    HEADS: tl.constexpr,
):
    sequence = tl.program_id(0)
    query_head = tl.program_id(1)
    q_start = tl.load(qo_indptr_ptr + sequence)
    q_length = tl.load(qo_indptr_ptr + sequence + 1) - q_start
    rows = tl.arange(0, KERNEL_BLOCK_M)
    row_mask = rows < q_length
    merged_max = tl.full((KERNEL_BLOCK_M,), -float("inf"), tl.float32)
    merged_sum = tl.zeros((KERNEL_BLOCK_M,), tl.float32)
    for partition in range(0, PARTITIONS):
        state_base = (
            ((partition * 32 + sequence) * HEADS + query_head)
            * KERNEL_BLOCK_M
            + rows
        )
        part_max = tl.load(
            partial_max_ptr + state_base,
            mask=row_mask,
            other=-float("inf"),
        )
        part_sum = tl.load(
            partial_sum_ptr + state_base, mask=row_mask, other=0.0
        )
        new_max = tl.maximum(merged_max, part_max)
        old_scale = tl.where(
            merged_max == -float("inf"),
            0.0,
            tl.exp(merged_max - new_max),
        )
        part_scale = tl.where(
            part_max == -float("inf"),
            0.0,
            tl.exp(part_max - new_max),
        )
        merged_sum = merged_sum * old_scale + part_sum * part_scale
        merged_max = new_max
    merged_base = (
        (sequence * HEADS + query_head) * KERNEL_BLOCK_M + rows
    )
    tl.store(merged_max_ptr + merged_base, merged_max, mask=row_mask)
    tl.store(merged_sum_ptr + merged_base, merged_sum, mask=row_mask)


@triton.jit
def _value_consumer_kernel(
    v_extend_ptr,
    v_cache_ptr,
    output_ptr,
    qo_indptr_ptr,
    kv_indptr_ptr,
    kv_indices_ptr,
    merged_max_ptr,
    merged_sum_ptr,
    scores_ptr,
    v_scale,
    kv_group_num,
    stride_vt,
    stride_vh,
    stride_vct,
    stride_vch,
    stride_ot,
    stride_oh,
    PREFIX_TOKENS: tl.constexpr,
    SCORE_STRIDE: tl.constexpr,
    PARTITIONS: tl.constexpr,
    HEADS: tl.constexpr,
    VALUE_DIM: tl.constexpr,
):
    sequence = tl.program_id(0)
    query_head = tl.program_id(1)
    value_split = tl.program_id(2)
    kv_head = query_head // kv_group_num
    q_start = tl.load(qo_indptr_ptr + sequence)
    q_length = tl.load(qo_indptr_ptr + sequence + 1) - q_start
    kv_start = tl.load(kv_indptr_ptr + sequence)
    prefix_length = tl.load(kv_indptr_ptr + sequence + 1) - kv_start
    rows = tl.arange(0, KERNEL_BLOCK_M)
    row_mask = rows < q_length
    cols = tl.arange(0, KERNEL_BLOCK_N)
    value_dims = value_split * KERNEL_VALUE_BLOCK + tl.arange(
        0, KERNEL_VALUE_BLOCK
    )
    value_mask = value_dims < VALUE_DIM
    merged_base = (
        (sequence * HEADS + query_head) * KERNEL_BLOCK_M + rows
    )
    global_max = tl.load(
        merged_max_ptr + merged_base, mask=row_mask, other=-float("inf")
    )
    denominator = tl.load(
        merged_sum_ptr + merged_base, mask=row_mask, other=1.0
    )
    score_row_base = merged_base * SCORE_STRIDE
    accumulator = tl.zeros(
        (KERNEL_BLOCK_M, KERNEL_VALUE_BLOCK), tl.float32
    )

    for partition in range(0, PARTITIONS):
        partition_start = partition * KERNEL_PARTITION_N
        for tile in range(0, KERNEL_PARTITION_N // KERNEL_BLOCK_N):
            prefix_col = partition_start + tile * KERNEL_BLOCK_N + cols
            col_mask = prefix_col < prefix_length
            score = tl.load(
                scores_ptr + score_row_base[:, None] + prefix_col[None, :],
                mask=row_mask[:, None] & col_mask[None, :],
                other=-float("inf"),
            )
            probability = tl.where(
                row_mask[:, None] & col_mask[None, :],
                tl.exp(score - global_max[:, None]),
                0.0,
            )
            physical_slot = tl.load(
                kv_indices_ptr + kv_start + prefix_col,
                mask=col_mask,
                other=0,
            )
            v_offsets = (
                physical_slot[:, None] * stride_vct
                + kv_head * stride_vch
                + value_dims[None, :]
            )
            values = tl.load(
                v_cache_ptr + v_offsets,
                mask=col_mask[:, None] & value_mask[None, :],
                other=0.0,
            )
            accumulator += (
                tl.dot(probability.to(values.dtype), values) * v_scale
            )

    extend_col = cols
    extend_mask = extend_col < q_length
    score = tl.load(
        scores_ptr
        + score_row_base[:, None]
        + PREFIX_TOKENS
        + extend_col[None, :],
        mask=row_mask[:, None] & extend_mask[None, :],
        other=-float("inf"),
    )
    probability = tl.where(
        row_mask[:, None] & extend_mask[None, :],
        tl.exp(score - global_max[:, None]),
        0.0,
    )
    v_offsets = (
        (q_start + extend_col[:, None]) * stride_vt
        + kv_head * stride_vh
        + value_dims[None, :]
    )
    values = tl.load(
        v_extend_ptr + v_offsets,
        mask=extend_mask[:, None] & value_mask[None, :],
        other=0.0,
    )
    accumulator += tl.dot(probability.to(values.dtype), values)
    output_offsets = (
        (q_start + rows[:, None]) * stride_ot
        + query_head * stride_oh
        + value_dims[None, :]
    )
    tl.store(
        output_ptr + output_offsets,
        accumulator / denominator[:, None],
        mask=row_mask[:, None] & value_mask[None, :],
    )


def _workspace(
    *,
    device: torch.device,
    partitions: int,
    heads: int,
    prefix_tokens: int,
) -> Workspace:
    score_stride = prefix_tokens + BLOCK_N
    key = (device, partitions, heads, score_stride)
    existing = _workspace_cache.get(key)
    if existing is not None:
        return existing
    state_shape = (partitions, 32, heads, BLOCK_M)
    merged_shape = (32, heads, BLOCK_M)
    workspace = Workspace(
        partial_max=torch.empty(state_shape, device=device, dtype=torch.float32),
        partial_sum=torch.empty(state_shape, device=device, dtype=torch.float32),
        merged_max=torch.empty(merged_shape, device=device, dtype=torch.float32),
        merged_sum=torch.empty(merged_shape, device=device, dtype=torch.float32),
        scores=torch.empty(
            (32, heads, BLOCK_M, score_stride),
            device=device,
            dtype=torch.bfloat16,
        ),
    )
    _workspace_cache[key] = workspace
    return workspace


def extend_attention_fwd(
    q_extend,
    k_extend,
    v_extend,
    o_extend,
    k_buffer,
    v_buffer,
    qo_indptr,
    kv_indptr,
    kv_indices,
    custom_mask,
    is_causal,
    mask_indptr,
    max_len_extend,
    k_scale,
    v_scale,
    sm_scale=None,
    logit_cap=0.0,
    skip_prefix_custom_mask=True,
    sliding_window_size=-1,
    sinks=None,
    window_kv_offsets=None,
    xai_temperature_len=-1,
):
    batch = qo_indptr.shape[0] - 1
    query_tokens, heads, head_dim = q_extend.shape
    exact_common = (
        torch.cuda.get_device_capability() == (9, 0)
        and batch == 32
        and query_tokens == 384
        and heads == 32
        and max_len_extend == 12
        and is_causal
        and logit_cap == 0.0
        and sinks is None
        and xai_temperature_len == -1
        and head_dim == v_extend.shape[-1]
        and q_extend.is_contiguous()
        and k_extend.is_contiguous()
        and v_extend.is_contiguous()
        and o_extend.is_contiguous()
    )
    local = (
        exact_common
        and head_dim == 256
        and k_extend.shape[1] == 16
        and sliding_window_size == 1024
    )
    global_attention = (
        exact_common
        and head_dim == 512
        and k_extend.shape[1] == 4
        and sliding_window_size <= 0
    )
    if not (local or global_attention):
        raise RuntimeError("packed_m384_exact_shape_required")
    if k_buffer.dtype not in (torch.float8_e4m3fn, torch.float8_e5m2):
        raise RuntimeError(f"packed_m384_fp8_kv_required:{k_buffer.dtype}")
    if v_buffer.dtype != k_buffer.dtype:
        raise RuntimeError("packed_m384_kv_dtype_mismatch")

    prefix_capacity = (
        LOCAL_PREFIX_CAPACITY if local else GLOBAL_PREFIX_CAPACITY
    )
    partitions = triton.cdiv(prefix_capacity, PARTITION_N)
    workspace = _workspace(
        device=q_extend.device,
        partitions=partitions,
        heads=heads,
        prefix_tokens=prefix_capacity,
    )
    kind = "local_d256" if local else "global_d512"
    _audit_dispatch(kind, prefix_capacity, partitions)
    scale = sm_scale if sm_scale is not None else 1.0 / (head_dim**0.5)
    score_stride = prefix_capacity + BLOCK_N
    del window_kv_offsets
    _score_partition_kernel[(batch, heads, partitions)](
        q_extend,
        k_extend,
        k_buffer,
        qo_indptr,
        kv_indptr,
        kv_indices,
        custom_mask,
        mask_indptr,
        workspace.partial_max,
        workspace.partial_sum,
        workspace.scores,
        scale,
        k_scale,
        heads // k_extend.shape[1],
        q_extend.stride(0),
        q_extend.stride(1),
        k_extend.stride(0),
        k_extend.stride(1),
        k_buffer.stride(0),
        k_buffer.stride(1),
        PREFIX_TOKENS=prefix_capacity,
        SCORE_STRIDE=score_stride,
        PARTITIONS=partitions,
        HEADS=heads,
        HEAD_DIM=head_dim,
        SLIDING_WINDOW_SIZE=sliding_window_size,
        USE_CUSTOM_MASK=custom_mask is not None,
        SKIP_PREFIX_CUSTOM_MASK=skip_prefix_custom_mask,
        num_warps=8,
        num_stages=1,
    )
    _merge_state_kernel[(batch, heads)](
        workspace.partial_max,
        workspace.partial_sum,
        workspace.merged_max,
        workspace.merged_sum,
        qo_indptr,
        PARTITIONS=partitions,
        HEADS=heads,
        num_warps=4,
        num_stages=1,
    )
    value_splits = triton.cdiv(head_dim, VALUE_BLOCK)
    _value_consumer_kernel[(batch, heads, value_splits)](
        v_extend,
        v_buffer,
        o_extend,
        qo_indptr,
        kv_indptr,
        kv_indices,
        workspace.merged_max,
        workspace.merged_sum,
        workspace.scores,
        v_scale,
        heads // k_extend.shape[1],
        v_extend.stride(0),
        v_extend.stride(1),
        v_buffer.stride(0),
        v_buffer.stride(1),
        o_extend.stride(0),
        o_extend.stride(1),
        PREFIX_TOKENS=prefix_capacity,
        SCORE_STRIDE=score_stride,
        PARTITIONS=partitions,
        HEADS=heads,
        VALUE_DIM=head_dim,
        num_warps=4,
        num_stages=1,
    )
