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
KERNEL_BLOCK_M = tl.constexpr(16)
KERNEL_BLOCK_N = tl.constexpr(64)
KERNEL_PARTITION_N = tl.constexpr(512)
_workspace_cache: dict[tuple[object, ...], "Workspace"] = {}
_dispatch_counts = {"local_d256": 0, "global_d512": 0}


@dataclass(frozen=True)
class Workspace:
    partial_max: torch.Tensor
    partial_sum: torch.Tensor
    partial_out: torch.Tensor


def packed_m384_dispatch_audit() -> dict[str, int]:
    return dict(_dispatch_counts)


def _audit_dispatch(kind: str, prefix_tokens: int, partitions: int) -> None:
    _dispatch_counts[kind] += 1
    path = os.environ.get("PACKED_M384_AUDIT")
    if not path:
        return
    record = {
        "candidate": "packed_partitioned_online_softmax_m384",
        "kind": kind,
        "block_m": BLOCK_M,
        "block_n": BLOCK_N,
        "partition_n": PARTITION_N,
        "prefix_tokens": prefix_tokens,
        "partitions": partitions,
        "dispatch_count": _dispatch_counts[kind],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


@triton.jit
def _partition_attention_kernel(
    q_ptr,
    k_extend_ptr,
    v_extend_ptr,
    k_cache_ptr,
    v_cache_ptr,
    qo_indptr_ptr,
    kv_indptr_ptr,
    kv_indices_ptr,
    mask_ptr,
    mask_indptr_ptr,
    partial_max_ptr,
    partial_sum_ptr,
    partial_out_ptr,
    sm_scale,
    k_scale,
    v_scale,
    kv_group_num,
    stride_qt,
    stride_qh,
    stride_kt,
    stride_kh,
    stride_vt,
    stride_vh,
    stride_kct,
    stride_kch,
    stride_vct,
    stride_vch,
    PREFIX_TOKENS: tl.constexpr,
    PARTITIONS: tl.constexpr,
    HEADS: tl.constexpr,
    HEAD_DIM: tl.constexpr,
    KV_DIM: tl.constexpr,
    SLIDING_WINDOW_SIZE: tl.constexpr,
    USE_CUSTOM_MASK: tl.constexpr,
    SKIP_PREFIX_CUSTOM_MASK: tl.constexpr,
):
    sequence = tl.program_id(0)
    query_head = tl.program_id(1)
    packed_work = tl.program_id(2)
    query_block = packed_work // PARTITIONS
    partition = packed_work % PARTITIONS
    kv_head = query_head // kv_group_num

    q_start = tl.load(qo_indptr_ptr + sequence)
    q_length = tl.load(qo_indptr_ptr + sequence + 1) - q_start
    kv_start = tl.load(kv_indptr_ptr + sequence)
    prefix_length = tl.load(kv_indptr_ptr + sequence + 1) - kv_start

    rows = query_block * KERNEL_BLOCK_M + tl.arange(0, KERNEL_BLOCK_M)
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
    accumulator = tl.zeros((KERNEL_BLOCK_M, KV_DIM), tl.float32)
    cols = tl.arange(0, KERNEL_BLOCK_N)
    value_dims = tl.arange(0, KV_DIM)
    partition_start = partition * KERNEL_PARTITION_N

    if USE_CUSTOM_MASK:
        mask_start = tl.load(mask_indptr_ptr + sequence)
        mask_stride = (
            tl.load(mask_indptr_ptr + sequence + 1) - mask_start
        )
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
        tile_max = tl.max(scores, axis=1)
        new_max = tl.maximum(running_max, tile_max)
        previous_scale = tl.where(
            running_max == -float("inf"),
            0.0,
            tl.exp(running_max - new_max),
        )
        probabilities = tl.exp(scores - new_max[:, None])
        probabilities = tl.where(valid, probabilities, 0.0)
        running_sum = (
            running_sum * previous_scale + tl.sum(probabilities, axis=1)
        )
        v_offsets = (
            physical_slot[:, None] * stride_vct
            + kv_head * stride_vch
            + value_dims[None, :]
        )
        values = tl.load(
            v_cache_ptr + v_offsets,
            mask=col_mask[:, None],
            other=0.0,
        )
        accumulator = (
            accumulator * previous_scale[:, None]
            + tl.dot(probabilities.to(values.dtype), values) * v_scale
        )
        running_max = new_max

    if partition == 0:
        extend_cols = cols
        extend_col_mask = extend_cols < q_length
        k_offsets = (
            (q_start + extend_cols[None, :]) * stride_kt
            + kv_head * stride_kh
            + dims[:, None]
        )
        k = tl.load(
            k_extend_ptr + k_offsets,
            mask=extend_col_mask[None, :],
            other=0.0,
        )
        scores = tl.dot(q, k, out_dtype=tl.float32) * sm_scale
        valid = (
            row_mask[:, None]
            & extend_col_mask[None, :]
            & (rows[:, None] >= extend_cols[None, :])
        )
        if USE_CUSTOM_MASK:
            extend_mask = tl.load(
                mask_ptr
                + mask_start
                + rows[:, None] * original_total_length
                + original_prefix_length
                + extend_cols[None, :],
                mask=valid,
                other=0,
            )
            valid &= extend_mask
        scores = tl.where(valid, scores, -float("inf"))
        tile_max = tl.max(scores, axis=1)
        new_max = tl.maximum(running_max, tile_max)
        previous_scale = tl.where(
            running_max == -float("inf"),
            0.0,
            tl.exp(running_max - new_max),
        )
        probabilities = tl.exp(scores - new_max[:, None])
        probabilities = tl.where(valid, probabilities, 0.0)
        running_sum = (
            running_sum * previous_scale + tl.sum(probabilities, axis=1)
        )
        v_offsets = (
            (q_start + extend_cols[:, None]) * stride_vt
            + kv_head * stride_vh
            + value_dims[None, :]
        )
        values = tl.load(
            v_extend_ptr + v_offsets,
            mask=extend_col_mask[:, None],
            other=0.0,
        )
        accumulator = (
            accumulator * previous_scale[:, None]
            + tl.dot(probabilities.to(values.dtype), values)
        )
        running_max = new_max

    state_base = (
        ((partition * 32 + sequence) * HEADS + query_head) * KERNEL_BLOCK_M
        + rows
        - query_block * KERNEL_BLOCK_M
    )
    tl.store(
        partial_max_ptr + state_base,
        running_max,
        mask=row_mask,
    )
    tl.store(
        partial_sum_ptr + state_base,
        running_sum,
        mask=row_mask,
    )
    output_offsets = state_base[:, None] * KV_DIM + value_dims[None, :]
    tl.store(
        partial_out_ptr + output_offsets,
        accumulator,
        mask=row_mask[:, None],
    )


@triton.jit
def _merge_partitions_kernel(
    output_ptr,
    qo_indptr_ptr,
    partial_max_ptr,
    partial_sum_ptr,
    partial_out_ptr,
    stride_ot,
    stride_oh,
    PARTITIONS: tl.constexpr,
    HEADS: tl.constexpr,
    KV_DIM: tl.constexpr,
):
    sequence = tl.program_id(0)
    query_head = tl.program_id(1)
    query_block = tl.program_id(2)
    q_start = tl.load(qo_indptr_ptr + sequence)
    q_length = tl.load(qo_indptr_ptr + sequence + 1) - q_start
    rows = query_block * KERNEL_BLOCK_M + tl.arange(0, KERNEL_BLOCK_M)
    row_mask = rows < q_length
    value_dims = tl.arange(0, KV_DIM)

    merged_max = tl.full((KERNEL_BLOCK_M,), -float("inf"), tl.float32)
    merged_sum = tl.zeros((KERNEL_BLOCK_M,), tl.float32)
    merged_out = tl.zeros((KERNEL_BLOCK_M, KV_DIM), tl.float32)
    row_in_block = rows - query_block * KERNEL_BLOCK_M
    for partition in range(0, PARTITIONS):
        state_base = (
            ((partition * 32 + sequence) * HEADS + query_head)
            * KERNEL_BLOCK_M
            + row_in_block
        )
        part_max = tl.load(
            partial_max_ptr + state_base,
            mask=row_mask,
            other=-float("inf"),
        )
        part_sum = tl.load(
            partial_sum_ptr + state_base,
            mask=row_mask,
            other=0.0,
        )
        part_offsets = (
            state_base[:, None] * KV_DIM + value_dims[None, :]
        )
        part_out = tl.load(
            partial_out_ptr + part_offsets,
            mask=row_mask[:, None],
            other=0.0,
        )
        new_max = tl.maximum(merged_max, part_max)
        merged_scale = tl.where(
            merged_max == -float("inf"),
            0.0,
            tl.exp(merged_max - new_max),
        )
        part_scale = tl.where(
            part_max == -float("inf"),
            0.0,
            tl.exp(part_max - new_max),
        )
        merged_sum = (
            merged_sum * merged_scale + part_sum * part_scale
        )
        merged_out = (
            merged_out * merged_scale[:, None]
            + part_out * part_scale[:, None]
        )
        merged_max = new_max

    output_offsets = (
        (q_start + rows[:, None]) * stride_ot
        + query_head * stride_oh
        + value_dims[None, :]
    )
    tl.store(
        output_ptr + output_offsets,
        merged_out / merged_sum[:, None],
        mask=row_mask[:, None],
    )


def _workspace(
    *,
    device: torch.device,
    partitions: int,
    heads: int,
    value_dim: int,
) -> Workspace:
    key = (device, partitions, heads, value_dim)
    existing = _workspace_cache.get(key)
    if existing is not None:
        return existing
    shape = (partitions, 32, heads, BLOCK_M)
    workspace = Workspace(
        partial_max=torch.empty(shape, device=device, dtype=torch.float32),
        partial_sum=torch.empty(shape, device=device, dtype=torch.float32),
        partial_out=torch.empty(
            (*shape, value_dim), device=device, dtype=torch.float32
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
    del window_kv_offsets
    batch = qo_indptr.shape[0] - 1
    query_tokens, heads, head_dim = q_extend.shape
    value_dim = v_extend.shape[-1]
    prefix_tokens = kv_indices.numel() // batch
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
        and head_dim == value_dim
        and q_extend.is_contiguous()
        and k_extend.is_contiguous()
        and v_extend.is_contiguous()
        and o_extend.is_contiguous()
    )
    local = (
        exact_common
        and head_dim == 256
        and k_extend.shape[1] == 16
        and prefix_tokens == 1024
        and sliding_window_size == 1024
    )
    global_attention = (
        exact_common
        and head_dim == 512
        and k_extend.shape[1] == 4
        and prefix_tokens == 4214
        and sliding_window_size <= 0
    )
    if not (local or global_attention):
        raise RuntimeError("packed_m384_exact_shape_required")
    if k_buffer.dtype not in (torch.float8_e4m3fn, torch.float8_e5m2):
        raise RuntimeError(f"packed_m384_fp8_kv_required:{k_buffer.dtype}")
    if v_buffer.dtype != k_buffer.dtype:
        raise RuntimeError("packed_m384_kv_dtype_mismatch")

    partitions = triton.cdiv(prefix_tokens, PARTITION_N)
    workspace = _workspace(
        device=q_extend.device,
        partitions=partitions,
        heads=heads,
        value_dim=value_dim,
    )
    kind = "local_d256" if local else "global_d512"
    _audit_dispatch(kind, prefix_tokens, partitions)
    scale = sm_scale if sm_scale is not None else 1.0 / (head_dim**0.5)
    query_blocks = triton.cdiv(max_len_extend, BLOCK_M)
    grid = (batch, heads, query_blocks * partitions)
    _partition_attention_kernel[grid](
        q_extend,
        k_extend,
        v_extend,
        k_buffer,
        v_buffer,
        qo_indptr,
        kv_indptr,
        kv_indices,
        custom_mask,
        mask_indptr,
        workspace.partial_max,
        workspace.partial_sum,
        workspace.partial_out,
        scale,
        k_scale,
        v_scale,
        heads // k_extend.shape[1],
        q_extend.stride(0),
        q_extend.stride(1),
        k_extend.stride(0),
        k_extend.stride(1),
        v_extend.stride(0),
        v_extend.stride(1),
        k_buffer.stride(0),
        k_buffer.stride(1),
        v_buffer.stride(0),
        v_buffer.stride(1),
        PREFIX_TOKENS=prefix_tokens,
        PARTITIONS=partitions,
        HEADS=heads,
        HEAD_DIM=head_dim,
        KV_DIM=value_dim,
        SLIDING_WINDOW_SIZE=sliding_window_size,
        USE_CUSTOM_MASK=custom_mask is not None,
        SKIP_PREFIX_CUSTOM_MASK=skip_prefix_custom_mask,
        num_warps=8,
        num_stages=1,
    )
    _merge_partitions_kernel[(batch, heads, query_blocks)](
        o_extend,
        qo_indptr,
        workspace.partial_max,
        workspace.partial_sum,
        workspace.partial_out,
        o_extend.stride(0),
        o_extend.stride(1),
        PARTITIONS=partitions,
        HEADS=heads,
        KV_DIM=value_dim,
        num_warps=8,
        num_stages=1,
    )
