from __future__ import annotations

import triton
import triton.language as tl

from sglang.srt.layers.attention.triton_ops.decode_attention import (
    _decode_softmax_reducev_fwd,
)


@triton.jit
def _store_ring_kv_kernel(
    K,
    V,
    K_RING,
    V_RING,
    REQUEST_IDS,
    ABSOLUTE_POSITIONS,
    K_SCALE: tl.constexpr,
    V_SCALE: tl.constexpr,
    n_elements: tl.constexpr,
    row_elements: tl.constexpr,
    ring_tokens: tl.constexpr,
    BLOCK: tl.constexpr,
):
    offsets = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    source_mask = offsets < n_elements
    token_offsets = offsets // row_elements
    within_row = offsets - token_offsets * row_elements
    request_ids = tl.load(REQUEST_IDS + token_offsets, mask=source_mask, other=-1)
    absolute_positions = tl.load(
        ABSOLUTE_POSITIONS + token_offsets, mask=source_mask, other=0
    )
    valid = source_mask & (request_ids >= 0)
    ring_positions = absolute_positions & (ring_tokens - 1)
    destination_offsets = (
        (request_ids * ring_tokens + ring_positions) * row_elements + within_row
    )
    k = tl.load(K + offsets, mask=valid, other=0.0) / K_SCALE
    v = tl.load(V + offsets, mask=valid, other=0.0) / V_SCALE
    tl.store(K_RING + destination_offsets, k, mask=valid)
    tl.store(V_RING + destination_offsets, v, mask=valid)


def store_ring_kv(
    k,
    v,
    k_ring,
    v_ring,
    request_ids,
    absolute_positions,
    k_scale=1.0,
    v_scale=1.0,
):
    if k.shape != v.shape:
        raise ValueError(f"K/V shape mismatch: {k.shape} != {v.shape}")
    if k.ndim != 3:
        raise ValueError(f"expected [tokens, heads, dim], got {k.shape}")
    if request_ids.numel() != k.shape[0]:
        raise ValueError("request-id count must equal token count")
    if absolute_positions.numel() != k.shape[0]:
        raise ValueError("position count must equal token count")
    if k_ring.shape != v_ring.shape or k_ring.ndim != 4:
        raise ValueError("ring buffers must be matching [requests, tokens, heads, dim]")
    row_elements = k.shape[1] * k.shape[2]
    n_elements = k.numel()
    block = 1024
    return _store_ring_kv_kernel[(triton.cdiv(n_elements, block),)](
        k,
        v,
        k_ring,
        v_ring,
        request_ids,
        absolute_positions,
        k_scale,
        v_scale,
        n_elements=n_elements,
        row_elements=row_elements,
        ring_tokens=k_ring.shape[1],
        BLOCK=block,
        num_warps=8,
        num_stages=2,
    )


@triton.jit
def _restore_ring_prefix_kernel(
    K_PAGED,
    V_PAGED,
    K_RING,
    V_RING,
    REQUEST_IDS,
    SEQ_LENS,
    KV_INDPTR,
    KV_INDICES,
    LAST_POSITIONS,
    row_elements: tl.constexpr,
    ring_tokens: tl.constexpr,
    EXCLUDE_LAST: tl.constexpr,
    FORCE: tl.constexpr,
    BLOCK: tl.constexpr,
):
    batch = tl.program_id(0)
    token_block = tl.program_id(1)
    element_block = tl.program_id(2)
    request_id = tl.load(REQUEST_IDS + batch)
    valid_request = request_id >= 0
    safe_request_id = tl.maximum(request_id, 0)
    seq_len = tl.load(SEQ_LENS + batch)
    previous = tl.load(LAST_POSITIONS + safe_request_id)
    reset = (previous != seq_len - 2) | FORCE
    start = tl.load(KV_INDPTR + batch)
    end = tl.load(KV_INDPTR + batch + 1)
    token = token_block
    valid_token = valid_request & reset & (start + token < end - EXCLUDE_LAST)
    paged_slot = tl.load(KV_INDICES + start + token, mask=valid_token, other=0)
    absolute_position = seq_len - (end - start) + token
    ring_position = absolute_position & (ring_tokens - 1)
    elements = element_block * BLOCK + tl.arange(0, BLOCK)
    valid = valid_token & (elements < row_elements)
    source = paged_slot * row_elements + elements
    destination = (
        (safe_request_id * ring_tokens + ring_position) * row_elements + elements
    )
    tl.store(
        K_RING + destination,
        tl.load(K_PAGED + source, mask=valid, other=0.0),
        mask=valid,
    )
    tl.store(
        V_RING + destination,
        tl.load(V_PAGED + source, mask=valid, other=0.0),
        mask=valid,
    )


@triton.jit
def _mark_ring_positions_kernel(REQUEST_IDS, SEQ_LENS, LAST_POSITIONS, n: tl.constexpr):
    offset = tl.program_id(0) * 32 + tl.arange(0, 32)
    valid = offset < n
    request_id = tl.load(REQUEST_IDS + offset, mask=valid, other=-1)
    valid = valid & (request_id >= 0)
    request_id = tl.maximum(request_id, 0)
    seq_len = tl.load(SEQ_LENS + offset, mask=valid, other=0)
    tl.store(LAST_POSITIONS + request_id, seq_len - 1, mask=valid)


def restore_ring_prefix_if_needed(
    k_paged,
    v_paged,
    k_ring,
    v_ring,
    request_ids,
    seq_lens,
    kv_indptr,
    kv_indices,
    last_positions,
    exclude_last=True,
    force=False,
):
    """Copy a request's chronological prefix only when its ring ownership resets."""
    row_elements = k_paged.shape[1] * k_paged.shape[2]
    block = 1024
    _restore_ring_prefix_kernel[
        (
            request_ids.numel(),
            k_ring.shape[1],
            triton.cdiv(row_elements, block),
        )
    ](
        k_paged,
        v_paged,
        k_ring,
        v_ring,
        request_ids,
        seq_lens,
        kv_indptr,
        kv_indices,
        last_positions,
        row_elements=row_elements,
        ring_tokens=k_ring.shape[1],
        EXCLUDE_LAST=exclude_last,
        FORCE=force,
        BLOCK=block,
        num_warps=8,
        num_stages=2,
    )


def mark_ring_positions(request_ids, seq_lens, last_positions):
    return _mark_ring_positions_kernel[(triton.cdiv(request_ids.numel(), 32),)](
        request_ids,
        seq_lens,
        last_positions,
        n=request_ids.numel(),
        num_warps=1,
    )


@triton.jit
def _tanh(x):
    return 2 * tl.sigmoid(2 * x) - 1


@triton.jit
def _zero_padded_output_kernel(
    OUTPUT,
    REQUEST_IDS,
    n_elements: tl.constexpr,
    row_elements: tl.constexpr,
    BLOCK: tl.constexpr,
):
    offsets = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    valid = offsets < n_elements
    rows = offsets // row_elements
    request_ids = tl.load(REQUEST_IDS + rows, mask=valid, other=-1)
    tl.store(OUTPUT + offsets, 0.0, mask=valid & (request_ids < 0))


@triton.jit
def _ring_grouped_stage1(
    Q,
    K_RING,
    V_RING,
    REQUEST_IDS,
    sm_scale_withk,
    seq_lens,
    ring_starts,
    Att_Out,
    Att_Lse,
    num_kv_splits,
    stride_qbs,
    stride_qh,
    stride_buf_kr,
    stride_buf_kt,
    stride_buf_kh,
    stride_buf_vr,
    stride_buf_vt,
    stride_buf_vh,
    stride_mid_ob,
    stride_mid_oh,
    stride_mid_os,
    kv_group_num: tl.constexpr,
    q_head_num: tl.constexpr,
    BLOCK_DMODEL: tl.constexpr,
    BLOCK_DV: tl.constexpr,
    BLOCK_N: tl.constexpr,
    BLOCK_H: tl.constexpr,
    MIN_BLOCK_KV: tl.constexpr,
    logit_cap: tl.constexpr,
    Lk: tl.constexpr,
    Lv: tl.constexpr,
    RING_TOKENS: tl.constexpr,
):
    cur_batch = tl.program_id(0)
    cur_head_id = tl.program_id(1)
    cur_kv_head = cur_head_id // tl.cdiv(kv_group_num, BLOCK_H)
    split_kv_id = tl.program_id(2)

    if BLOCK_H < kv_group_num:
        valid_block_h: tl.constexpr = BLOCK_H
    else:
        valid_block_h: tl.constexpr = kv_group_num
    cur_head = cur_head_id * valid_block_h + tl.arange(0, BLOCK_H)
    mask_h = cur_head < (cur_head_id + 1) * valid_block_h
    mask_h = mask_h & (cur_head < q_head_num)

    offs_d = tl.arange(0, BLOCK_DMODEL)
    offs_dv = tl.arange(0, BLOCK_DV)
    mask_d = offs_d < Lk
    mask_dv = offs_dv < Lv

    cur_batch_seq_len = tl.load(seq_lens + cur_batch)
    cur_ring_start = tl.load(ring_starts + cur_batch)
    cur_ring_row = tl.load(REQUEST_IDS + cur_batch)
    valid_request = cur_ring_row >= 0
    cur_ring_row = tl.maximum(cur_ring_row, 0)
    cur_batch_seq_len = tl.where(valid_request, cur_batch_seq_len, 0)
    kv_splits = tl.load(num_kv_splits + cur_batch)
    offs_q = cur_batch * stride_qbs + cur_head[:, None] * stride_qh + offs_d[None, :]

    kv_len_per_split = (
        tl.cdiv(tl.cdiv(cur_batch_seq_len, kv_splits), MIN_BLOCK_KV) * MIN_BLOCK_KV
    )
    split_kv_start = kv_len_per_split * split_kv_id
    split_kv_end = tl.minimum(split_kv_start + kv_len_per_split, cur_batch_seq_len)

    e_max = tl.zeros([BLOCK_H], dtype=tl.float32) - float("inf")
    e_sum = tl.zeros([BLOCK_H], dtype=tl.float32)
    acc = tl.zeros([BLOCK_H, BLOCK_DV], dtype=tl.float32)
    base_offs_k = (
        cur_ring_row * stride_buf_kr
        + cur_kv_head * stride_buf_kh
        + offs_d[:, None]
    )
    base_offs_v = (
        cur_ring_row * stride_buf_vr
        + cur_kv_head * stride_buf_vh
        + offs_dv[None, :]
    )

    if split_kv_end > split_kv_start:
        q = tl.load(Q + offs_q, mask=mask_h[:, None] & mask_d[None, :], other=0.0)
        q_k = q.to(K_RING.dtype.element_ty)
        for start_n in tl.range(split_kv_start, split_kv_end, BLOCK_N):
            offs_n = start_n + tl.arange(0, BLOCK_N)
            mask_n = offs_n < split_kv_end
            ring_positions = (cur_ring_start + offs_n) & (RING_TOKENS - 1)
            offs_buf_k = ring_positions[None, :] * stride_buf_kt + base_offs_k
            k = tl.load(
                K_RING + offs_buf_k,
                mask=mask_n[None, :] & mask_d[:, None],
                other=0.0,
            )
            qk = tl.dot(q_k, k)
            qk *= sm_scale_withk
            if logit_cap > 0:
                qk = logit_cap * _tanh(qk / logit_cap)
            qk = tl.where(mask_h[:, None] & mask_n[None, :], qk, float("-inf"))

            offs_buf_v = ring_positions[:, None] * stride_buf_vt + base_offs_v
            v = tl.load(
                V_RING + offs_buf_v,
                mask=mask_n[:, None] & mask_dv[None, :],
                other=0.0,
            )
            next_e_max = tl.maximum(tl.max(qk, 1), e_max)
            previous_scale = tl.exp(e_max - next_e_max)
            p = tl.exp(qk - next_e_max[:, None])
            acc *= previous_scale[:, None]
            acc += tl.dot(p.to(v.dtype), v)
            e_sum = e_sum * previous_scale + tl.sum(p, 1)
            e_max = next_e_max

        offs_mid_o = (
            cur_batch * stride_mid_ob
            + cur_head[:, None] * stride_mid_oh
            + split_kv_id * stride_mid_os
            + offs_dv[None, :]
        )
        tl.store(
            Att_Out + offs_mid_o,
            acc / e_sum[:, None],
            mask=mask_h[:, None] & mask_dv[None, :],
        )
        offs_mid_lse = (
            cur_batch * stride_mid_ob
            + cur_head * stride_mid_oh
            + split_kv_id * stride_mid_os
        ) // Lv
        tl.store(Att_Lse + offs_mid_lse, e_max + tl.log(e_sum), mask=mask_h)


def ring_decode_attention(
    q,
    k_ring,
    v_ring,
    output,
    seq_lens,
    ring_starts,
    kv_indptr,
    attn_logits,
    attn_lse,
    num_kv_splits,
    max_kv_splits,
    sm_scale,
    k_scale,
    v_scale,
    request_ids=None,
):
    if k_ring.shape != v_ring.shape:
        raise ValueError("K/V ring shapes differ")
    if k_ring.shape[1] != 1024:
        raise ValueError("candidate is bound to the exact 1,024-token ring")
    if q.shape[0] > k_ring.shape[0]:
        raise ValueError("ring capacity is below padded batch size")
    if request_ids is None:
        import torch

        request_ids = torch.arange(q.shape[0], dtype=torch.int32, device=q.device)
    if request_ids.numel() != q.shape[0]:
        raise ValueError("request-id count must equal padded query batch")
    block_n = 32
    block_h = 16
    block_dmodel = triton.next_power_of_2(k_ring.shape[-1])
    block_dv = triton.next_power_of_2(v_ring.shape[-1])
    kv_group_num = q.shape[1] // k_ring.shape[2]
    grid = (
        q.shape[0],
        triton.cdiv(q.shape[1], min(block_h, kv_group_num)),
        max_kv_splits,
    )
    compiled = _ring_grouped_stage1[grid](
        q,
        k_ring,
        v_ring,
        request_ids,
        sm_scale * k_scale,
        seq_lens,
        ring_starts,
        attn_logits,
        attn_lse,
        num_kv_splits,
        q.stride(0),
        q.stride(1),
        k_ring.stride(0),
        k_ring.stride(1),
        k_ring.stride(2),
        v_ring.stride(0),
        v_ring.stride(1),
        v_ring.stride(2),
        attn_logits.stride(0),
        attn_logits.stride(1),
        attn_logits.stride(2),
        kv_group_num=kv_group_num,
        q_head_num=q.shape[1],
        BLOCK_DMODEL=block_dmodel,
        BLOCK_DV=block_dv,
        BLOCK_N=block_n,
        BLOCK_H=block_h,
        MIN_BLOCK_KV=32,
        logit_cap=0.0,
        Lk=k_ring.shape[-1],
        Lv=v_ring.shape[-1],
        RING_TOKENS=k_ring.shape[1],
        num_warps=4,
        num_stages=2,
    )
    _decode_softmax_reducev_fwd(
        attn_logits,
        attn_lse,
        q,
        output,
        v_scale,
        v_ring,
        kv_indptr,
        num_kv_splits,
        max_kv_splits,
    )
    output_elements = output.numel()
    output_row_elements = output_elements // output.shape[0]
    _zero_padded_output_kernel[(triton.cdiv(output_elements, 256),)](
        output,
        request_ids,
        n_elements=output_elements,
        row_elements=output_row_elements,
        BLOCK=256,
        num_warps=4,
    )
    return compiled
