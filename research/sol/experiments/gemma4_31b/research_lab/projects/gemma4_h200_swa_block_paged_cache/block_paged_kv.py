from __future__ import annotations

import triton
import triton.language as tl

from sglang.srt.layers.attention.triton_ops.decode_attention import (
    _decode_softmax_reducev_fwd,
)


@triton.jit
def _tanh(x):
    return 2 * tl.sigmoid(2 * x) - 1


@triton.jit
def _block_paged_grouped_stage1(
    Q,
    K_CACHE,
    V_CACHE,
    BLOCK_TABLE,
    BLOCK_INDPTR,
    FIRST_OFFSETS,
    sm_scale_withk,
    kv_indptr,
    Att_Out,
    Att_Lse,
    num_kv_splits,
    stride_qbs,
    stride_qh,
    stride_buf_kt,
    stride_buf_kh,
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
    PAGE_TOKENS: tl.constexpr,
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

    kv_start = tl.load(kv_indptr + cur_batch)
    seq_len = tl.load(kv_indptr + cur_batch + 1) - kv_start
    block_start = tl.load(BLOCK_INDPTR + cur_batch)
    first_offset = tl.load(FIRST_OFFSETS + cur_batch)
    kv_splits = tl.load(num_kv_splits + cur_batch)
    offs_q = cur_batch * stride_qbs + cur_head[:, None] * stride_qh + offs_d[None, :]

    kv_len_per_split = (
        tl.cdiv(tl.cdiv(seq_len, kv_splits), MIN_BLOCK_KV) * MIN_BLOCK_KV
    )
    split_kv_start = kv_len_per_split * split_kv_id
    split_kv_end = tl.minimum(split_kv_start + kv_len_per_split, seq_len)

    e_max = tl.zeros([BLOCK_H], dtype=tl.float32) - float("inf")
    e_sum = tl.zeros([BLOCK_H], dtype=tl.float32)
    acc = tl.zeros([BLOCK_H, BLOCK_DV], dtype=tl.float32)
    base_offs_k = cur_kv_head * stride_buf_kh + offs_d[:, None]
    base_offs_v = cur_kv_head * stride_buf_vh + offs_dv[None, :]

    if split_kv_end > split_kv_start:
        q = tl.load(Q + offs_q, mask=mask_h[:, None] & mask_d[None, :], other=0.0)
        q_k = q.to(K_CACHE.dtype.element_ty)
        for start_n in tl.range(split_kv_start, split_kv_end, BLOCK_N):
            offs_n = start_n + tl.arange(0, BLOCK_N)
            valid_token = offs_n < split_kv_end
            physical_position = first_offset + offs_n
            logical_page = physical_position // PAGE_TOKENS
            in_page = physical_position - logical_page * PAGE_TOKENS
            physical_page = tl.load(
                BLOCK_TABLE + block_start + logical_page,
                mask=valid_token,
                other=-1,
            )
            valid_token = valid_token & (physical_page >= 0)
            physical_token = physical_page * PAGE_TOKENS + in_page

            offs_buf_k = physical_token[None, :] * stride_buf_kt + base_offs_k
            k = tl.load(
                K_CACHE + offs_buf_k,
                mask=valid_token[None, :] & mask_d[:, None],
                other=0.0,
            )
            qk = tl.dot(q_k, k)
            qk *= sm_scale_withk
            if logit_cap > 0:
                qk = logit_cap * _tanh(qk / logit_cap)
            qk = tl.where(
                mask_h[:, None] & valid_token[None, :], qk, float("-inf")
            )

            offs_buf_v = physical_token[:, None] * stride_buf_vt + base_offs_v
            v = tl.load(
                V_CACHE + offs_buf_v,
                mask=valid_token[:, None] & mask_dv[None, :],
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


def block_paged_decode_attention(
    q,
    k_cache,
    v_cache,
    output,
    kv_indptr,
    block_table,
    block_indptr,
    first_offsets,
    attn_logits,
    attn_lse,
    num_kv_splits,
    max_kv_splits,
    sm_scale,
    k_scale,
    v_scale,
):
    if k_cache.shape != v_cache.shape:
        raise ValueError("K/V cache shapes differ")
    if q.shape[0] > block_indptr.numel() - 1:
        raise ValueError("block table is smaller than the padded query batch")
    if first_offsets.numel() != q.shape[0]:
        raise ValueError("first-offset count must match the padded query batch")
    page_tokens = 16
    block_n = 32
    block_h = 16
    block_dmodel = triton.next_power_of_2(k_cache.shape[-1])
    block_dv = triton.next_power_of_2(v_cache.shape[-1])
    kv_group_num = q.shape[1] // k_cache.shape[1]
    grid = (
        q.shape[0],
        triton.cdiv(q.shape[1], min(block_h, kv_group_num)),
        max_kv_splits,
    )
    compiled = _block_paged_grouped_stage1[grid](
        q,
        k_cache,
        v_cache,
        block_table,
        block_indptr,
        first_offsets,
        sm_scale * k_scale,
        kv_indptr,
        attn_logits,
        attn_lse,
        num_kv_splits,
        q.stride(0),
        q.stride(1),
        k_cache.stride(0),
        k_cache.stride(1),
        v_cache.stride(0),
        v_cache.stride(1),
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
        Lk=k_cache.shape[-1],
        Lv=v_cache.shape[-1],
        PAGE_TOKENS=page_tokens,
        num_warps=4,
        num_stages=2,
    )
    _decode_softmax_reducev_fwd(
        attn_logits,
        attn_lse,
        q,
        output,
        v_scale,
        v_cache,
        kv_indptr,
        num_kv_splits,
        max_kv_splits,
    )
    return compiled
