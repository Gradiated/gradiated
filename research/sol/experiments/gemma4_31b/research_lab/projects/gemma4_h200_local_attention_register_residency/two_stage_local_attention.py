#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from typing import Any

import torch
import triton
import triton.language as tl

from sglang.srt.layers.attention.triton_ops import extend_attention as _baseline


BLOCK_M = 64
BLOCK_N = 64
BLOCK_D = 256
BLOCK_DV_SLICE = 128
VALUE_SLICES = 2
KEY_TILES = 17
_WORKSPACES: dict[tuple[Any, ...], tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = {}
_AUDITED = False
_BASELINE_FWD = _baseline.extend_attention_fwd


@triton.jit
def _qk_softmax_stage(
    Q,
    K_Extend,
    K_Buffer,
    Probabilities,
    BlockMax,
    BlockSum,
    qo_indptr,
    kv_indptr,
    kv_indices,
    sm_scale,
    k_scale,
    kv_group_num,
    stride_qbs,
    stride_qh,
    stride_kbs,
    stride_kh,
    stride_buf_kbs,
    stride_buf_kh,
    stride_pb,
    stride_ph,
    stride_pq,
    stride_pt,
    stride_pm,
    stride_pn,
    stride_sb,
    stride_sh,
    stride_sq,
    stride_st,
    stride_sm,
    SLIDING_WINDOW_SIZE: tl.constexpr,
    BLOCK_M: tl.constexpr,
    BLOCK_N: tl.constexpr,
    BLOCK_D: tl.constexpr,
    KEY_TILES: tl.constexpr,
):
    cur_seq = tl.program_id(0)
    cur_head = tl.program_id(1)
    cur_block_m = tl.program_id(2)
    cur_kv_head = cur_head // kv_group_num

    extend_start = tl.load(qo_indptr + cur_seq)
    extend_len = tl.load(qo_indptr + cur_seq + 1) - extend_start
    if cur_block_m * BLOCK_M >= extend_len:
        return
    prefix_index_start = tl.load(kv_indptr + cur_seq)
    prefix_len = tl.load(kv_indptr + cur_seq + 1) - prefix_index_start
    total_len = prefix_len + extend_len

    offs_m = tl.arange(0, BLOCK_M)
    offs_n = tl.arange(0, BLOCK_N)
    offs_d = tl.arange(0, BLOCK_D)
    query_in_seq = cur_block_m * BLOCK_M + offs_m
    query_position = prefix_len + query_in_seq
    mask_m = query_in_seq < extend_len
    window_start = tl.maximum(0, prefix_len + cur_block_m * BLOCK_M - SLIDING_WINDOW_SIZE)
    q_offsets = (
        (extend_start + query_in_seq[:, None]) * stride_qbs
        + cur_head * stride_qh
        + offs_d[None, :]
    )
    q = tl.load(Q + q_offsets, mask=mask_m[:, None], other=0.0)
    for cur_key_tile in range(KEY_TILES):
        key_position = window_start + cur_key_tile * BLOCK_N + offs_n
        mask_key = key_position < total_len
        attention_mask = (
            mask_m[:, None]
            & mask_key[None, :]
            & (key_position[None, :] <= query_position[:, None])
            & (
                key_position[None, :] + SLIDING_WINDOW_SIZE
                >= query_position[:, None]
            )
        )
        qk = tl.zeros([BLOCK_M, BLOCK_N], dtype=tl.float32)

        prefix_key_mask = mask_key & (key_position < prefix_len)
        has_prefix = tl.max(prefix_key_mask.to(tl.int32), axis=0) != 0
        if has_prefix:
            prefix_slot = tl.load(
                kv_indices + prefix_index_start + key_position,
                mask=prefix_key_mask,
                other=0,
            )
            prefix_offsets = (
                prefix_slot[None, :] * stride_buf_kbs
                + cur_kv_head * stride_buf_kh
                + offs_d[:, None]
            )
            prefix_k = tl.load(
                K_Buffer + prefix_offsets,
                mask=prefix_key_mask[None, :],
                other=0.0,
            )
            qk += tl.dot(q.to(prefix_k.dtype), prefix_k) * k_scale

        extend_key_mask = mask_key & (key_position >= prefix_len)
        has_extend = tl.max(extend_key_mask.to(tl.int32), axis=0) != 0
        if has_extend:
            extend_position = key_position - prefix_len
            extend_offsets = (
                (extend_start + extend_position[None, :]) * stride_kbs
                + cur_kv_head * stride_kh
                + offs_d[:, None]
            )
            extend_k = tl.load(
                K_Extend + extend_offsets,
                mask=extend_key_mask[None, :],
                other=0.0,
            )
            qk += tl.dot(q, extend_k, out_dtype=tl.float32)

        qk *= sm_scale
        qk = tl.where(attention_mask, qk, float("-inf"))
        row_max = tl.max(qk, axis=1)
        safe_max = tl.where(row_max == float("-inf"), -1.0e20, row_max)
        probabilities = tl.exp(qk - safe_max[:, None])
        row_sum = tl.sum(probabilities, axis=1)

        probability_offsets = (
            cur_seq * stride_pb
            + cur_head * stride_ph
            + cur_block_m * stride_pq
            + cur_key_tile * stride_pt
            + offs_m[:, None] * stride_pm
            + offs_n[None, :] * stride_pn
        )
        stat_offsets = (
            cur_seq * stride_sb
            + cur_head * stride_sh
            + cur_block_m * stride_sq
            + cur_key_tile * stride_st
            + offs_m * stride_sm
        )
        tl.store(Probabilities + probability_offsets, probabilities)
        tl.store(BlockMax + stat_offsets, safe_max)
        tl.store(BlockSum + stat_offsets, row_sum)


@triton.jit
def _value_stage(
    V_Extend,
    O,
    V_Buffer,
    Probabilities,
    BlockMax,
    BlockSum,
    qo_indptr,
    kv_indptr,
    kv_indices,
    v_scale,
    kv_group_num,
    stride_vbs,
    stride_vh,
    stride_obs,
    stride_oh,
    stride_buf_vbs,
    stride_buf_vh,
    stride_pb,
    stride_ph,
    stride_pq,
    stride_pt,
    stride_pm,
    stride_pn,
    stride_sb,
    stride_sh,
    stride_sq,
    stride_st,
    stride_sm,
    SLIDING_WINDOW_SIZE: tl.constexpr,
    BLOCK_M: tl.constexpr,
    BLOCK_N: tl.constexpr,
    BLOCK_DV_SLICE: tl.constexpr,
    KEY_TILES: tl.constexpr,
    VALUE_SLICES: tl.constexpr,
):
    cur_seq = tl.program_id(0)
    cur_head = tl.program_id(1)
    packed = tl.program_id(2)
    cur_block_m = packed // VALUE_SLICES
    value_slice = packed % VALUE_SLICES
    cur_kv_head = cur_head // kv_group_num

    extend_start = tl.load(qo_indptr + cur_seq)
    extend_len = tl.load(qo_indptr + cur_seq + 1) - extend_start
    if cur_block_m * BLOCK_M >= extend_len:
        return
    prefix_index_start = tl.load(kv_indptr + cur_seq)
    prefix_len = tl.load(kv_indptr + cur_seq + 1) - prefix_index_start
    total_len = prefix_len + extend_len

    offs_m = tl.arange(0, BLOCK_M)
    offs_n = tl.arange(0, BLOCK_N)
    offs_dv = value_slice * BLOCK_DV_SLICE + tl.arange(0, BLOCK_DV_SLICE)
    query_in_seq = cur_block_m * BLOCK_M + offs_m
    mask_m = query_in_seq < extend_len
    window_start = tl.maximum(0, prefix_len + cur_block_m * BLOCK_M - SLIDING_WINDOW_SIZE)

    running_max = tl.zeros([BLOCK_M], dtype=tl.float32) - float("inf")
    denominator = tl.zeros([BLOCK_M], dtype=tl.float32)
    accumulator = tl.zeros([BLOCK_M, BLOCK_DV_SLICE], dtype=tl.float32)
    for key_tile in range(KEY_TILES):
        key_position = window_start + key_tile * BLOCK_N + offs_n
        mask_key = key_position < total_len
        probability_offsets = (
            cur_seq * stride_pb
            + cur_head * stride_ph
            + cur_block_m * stride_pq
            + key_tile * stride_pt
            + offs_m[:, None] * stride_pm
            + offs_n[None, :] * stride_pn
        )
        stat_offsets = (
            cur_seq * stride_sb
            + cur_head * stride_sh
            + cur_block_m * stride_sq
            + key_tile * stride_st
            + offs_m * stride_sm
        )
        probabilities = tl.load(Probabilities + probability_offsets)
        tile_max = tl.load(BlockMax + stat_offsets, mask=mask_m, other=-1.0e20)
        tile_sum = tl.load(BlockSum + stat_offsets, mask=mask_m, other=0.0)
        next_max = tl.maximum(running_max, tile_max)
        prior_scale = tl.exp(running_max - next_max)
        tile_scale = tl.exp(tile_max - next_max)
        scaled_probabilities = probabilities.to(tl.float32) * tile_scale[:, None]
        denominator = denominator * prior_scale + tile_sum * tile_scale
        accumulator *= prior_scale[:, None]

        prefix_key_mask = mask_key & (key_position < prefix_len)
        has_prefix = tl.max(prefix_key_mask.to(tl.int32), axis=0) != 0
        if has_prefix:
            prefix_slot = tl.load(
                kv_indices + prefix_index_start + key_position,
                mask=prefix_key_mask,
                other=0,
            )
            prefix_offsets = (
                prefix_slot[:, None] * stride_buf_vbs
                + cur_kv_head * stride_buf_vh
                + offs_dv[None, :]
            )
            prefix_v = tl.load(
                V_Buffer + prefix_offsets,
                mask=prefix_key_mask[:, None],
                other=0.0,
            )
            accumulator += (
                tl.dot(scaled_probabilities.to(prefix_v.dtype), prefix_v) * v_scale
            )

        extend_key_mask = mask_key & (key_position >= prefix_len)
        has_extend = tl.max(extend_key_mask.to(tl.int32), axis=0) != 0
        if has_extend:
            extend_position = key_position - prefix_len
            extend_offsets = (
                (extend_start + extend_position[:, None]) * stride_vbs
                + cur_kv_head * stride_vh
                + offs_dv[None, :]
            )
            extend_v = tl.load(
                V_Extend + extend_offsets,
                mask=extend_key_mask[:, None],
                other=0.0,
            )
            accumulator += tl.dot(scaled_probabilities.to(extend_v.dtype), extend_v)
        running_max = next_max

    output_offsets = (
        (extend_start + query_in_seq[:, None]) * stride_obs
        + cur_head * stride_oh
        + offs_dv[None, :]
    )
    tl.store(
        O + output_offsets,
        accumulator / tl.maximum(denominator, 1.0e-20)[:, None],
        mask=mask_m[:, None],
    )


def _workspace(
    q_extend: torch.Tensor,
    batch_size: int,
    head_num: int,
    query_blocks: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    key = (q_extend.device.index, batch_size, head_num, query_blocks)
    workspace = _WORKSPACES.get(key)
    if workspace is None:
        shape = (batch_size, head_num, query_blocks, KEY_TILES, BLOCK_M)
        probabilities = torch.empty((*shape, BLOCK_N), device=q_extend.device, dtype=torch.bfloat16)
        block_max = torch.empty(shape, device=q_extend.device, dtype=torch.float32)
        block_sum = torch.empty(shape, device=q_extend.device, dtype=torch.float32)
        workspace = probabilities, block_max, block_sum
        _WORKSPACES[key] = workspace
    return workspace


def _candidate_supported(
    q_extend: torch.Tensor,
    k_extend: torch.Tensor,
    v_extend: torch.Tensor,
    custom_mask: torch.Tensor | None,
    is_causal: bool,
    sliding_window_size: int,
    logit_cap: float,
    sinks: torch.Tensor | None,
    xai_temperature_len: int,
) -> bool:
    return bool(
        q_extend.is_cuda
        and torch.cuda.get_device_capability(q_extend.device) == (9, 0)
        and q_extend.shape[1:] == (32, 256)
        and k_extend.shape[1:] == (16, 256)
        and v_extend.shape[1:] == (16, 256)
        and custom_mask is None
        and is_causal
        and sliding_window_size == 1024
        and logit_cap == 0.0
        and sinks is None
        and xai_temperature_len <= 0
    )


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
    if not _candidate_supported(
        q_extend,
        k_extend,
        v_extend,
        custom_mask,
        is_causal,
        sliding_window_size,
        logit_cap,
        sinks,
        xai_temperature_len,
    ):
        return _BASELINE_FWD(
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
            sm_scale,
            logit_cap,
            skip_prefix_custom_mask,
            sliding_window_size,
            sinks,
            window_kv_offsets,
            xai_temperature_len,
        )

    batch_size = qo_indptr.shape[0] - 1
    head_num = q_extend.shape[1]
    query_blocks = triton.cdiv(max_len_extend, BLOCK_M)
    probabilities, block_max, block_sum = _workspace(
        q_extend, batch_size, head_num, query_blocks
    )
    scale = sm_scale or 1.0 / math.sqrt(q_extend.shape[-1])
    kv_group_num = q_extend.shape[1] // k_extend.shape[1]

    global _AUDITED
    if not _AUDITED:
        audit_path = os.environ.get("LOCAL_ATTENTION_RESIDENCY_AUDIT")
        if audit_path:
            with open(audit_path, "a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "candidate_path": "extend_attention_fwd.local_head256_two_stage_blockprob_vslice2",
                            "stages": ["block_local_qk_softmax", "normalized_v_slice2"],
                            "qk_recomputed": False,
                            "q_heads": 32,
                            "kv_heads": 16,
                            "qk_head_dim": 256,
                            "v_head_dim": 256,
                            "sliding_window_size": 1024,
                            "probability_dtype": "bfloat16",
                            "query_tile": BLOCK_M,
                            "key_tile": BLOCK_N,
                            "value_splits": VALUE_SLICES,
                            "value_slice": BLOCK_DV_SLICE,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        _AUDITED = True

    probability_strides = probabilities.stride()
    stat_strides = block_max.stride()
    _qk_softmax_stage[(batch_size, head_num, query_blocks)](
        q_extend,
        k_extend,
        k_buffer,
        probabilities,
        block_max,
        block_sum,
        qo_indptr,
        kv_indptr,
        kv_indices,
        scale,
        k_scale,
        kv_group_num,
        q_extend.stride(0),
        q_extend.stride(1),
        k_extend.stride(0),
        k_extend.stride(1),
        k_buffer.stride(0),
        k_buffer.stride(1),
        *probability_strides,
        *stat_strides,
        SLIDING_WINDOW_SIZE=sliding_window_size,
        BLOCK_M=BLOCK_M,
        BLOCK_N=BLOCK_N,
        BLOCK_D=BLOCK_D,
        KEY_TILES=KEY_TILES,
        num_warps=8,
        num_stages=1,
    )
    _value_stage[(batch_size, head_num, query_blocks * VALUE_SLICES)](
        v_extend,
        o_extend,
        v_buffer,
        probabilities,
        block_max,
        block_sum,
        qo_indptr,
        kv_indptr,
        kv_indices,
        v_scale,
        kv_group_num,
        v_extend.stride(0),
        v_extend.stride(1),
        o_extend.stride(0),
        o_extend.stride(1),
        v_buffer.stride(0),
        v_buffer.stride(1),
        *probability_strides,
        *stat_strides,
        SLIDING_WINDOW_SIZE=sliding_window_size,
        BLOCK_M=BLOCK_M,
        BLOCK_N=BLOCK_N,
        BLOCK_DV_SLICE=BLOCK_DV_SLICE,
        KEY_TILES=KEY_TILES,
        VALUE_SLICES=VALUE_SLICES,
        num_warps=8,
        num_stages=1,
    )


def workspace_bytes(batch_size: int, max_len_extend: int, head_num: int = 32) -> int:
    query_blocks = triton.cdiv(max_len_extend, BLOCK_M)
    elements = batch_size * head_num * query_blocks * KEY_TILES * BLOCK_M
    return elements * (BLOCK_N * 2 + 4 + 4)
