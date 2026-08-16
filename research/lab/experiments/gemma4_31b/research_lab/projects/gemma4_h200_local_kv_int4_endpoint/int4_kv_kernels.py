from __future__ import annotations

import triton
import triton.language as tl

from sglang.srt.layers.attention.triton_ops.decode_attention import (
    _decode_softmax_reducev_fwd,
)


@triton.jit
def _pack_group64_signed_int4(
    source,
    locations,
    packed,
    scales,
    source_stride_token,
    source_stride_head,
    packed_stride_token,
    packed_stride_head,
    scale_stride_token,
    scale_stride_head,
    token_count: tl.constexpr,
    head_count: tl.constexpr,
    cache_tokens: tl.constexpr,
):
    program = tl.program_id(0)
    group = program % 4
    head = (program // 4) % head_count
    token = program // (4 * head_count)
    location = tl.load(locations + token, mask=token < token_count, other=-1)
    valid = (token < token_count) & (location >= 0) & (location < cache_tokens)
    pair = tl.arange(0, 32)
    dim0 = group * 64 + pair * 2
    dim1 = dim0 + 1
    base = token * source_stride_token + head * source_stride_head
    value0 = tl.load(source + base + dim0, mask=valid, other=0.0).to(tl.float32)
    value1 = tl.load(source + base + dim1, mask=valid, other=0.0).to(tl.float32)
    amax = tl.maximum(tl.max(tl.abs(value0), axis=0), tl.max(tl.abs(value1), axis=0))
    scale = tl.where(amax > 0.0, amax / 7.0, 1.0)
    quant0 = tl.maximum(-7.0, tl.minimum(7.0, tl.extra.cuda.libdevice.rint(value0 / scale))).to(tl.int32)
    quant1 = tl.maximum(-7.0, tl.minimum(7.0, tl.extra.cuda.libdevice.rint(value1 / scale))).to(tl.int32)
    byte = (quant0 & 15) | ((quant1 & 15) << 4)
    packed_base = (
        location * packed_stride_token
        + head * packed_stride_head
        + group * 32
    )
    tl.store(packed + packed_base + pair, byte.to(tl.uint8), mask=valid)
    scale_offset = location * scale_stride_token + head * scale_stride_head + group
    tl.store(scales + scale_offset, scale.to(tl.float16), mask=valid)


def pack_group64_signed_int4(
    source,
    locations,
    packed,
    scales,
):
    if source.shape[-1] != 256 or packed.shape[-1] != 128 or scales.shape[-1] != 4:
        raise ValueError("group64 INT4 producer is frozen to head_dim=256")
    if source.shape[0] != locations.numel() or source.shape[1] != packed.shape[1]:
        raise ValueError("producer shape mismatch")
    grid = (source.shape[0] * source.shape[1] * 4,)
    return _pack_group64_signed_int4[grid](
        source,
        locations,
        packed,
        scales,
        source.stride(0),
        source.stride(1),
        packed.stride(0),
        packed.stride(1),
        scales.stride(0),
        scales.stride(1),
        token_count=source.shape[0],
        head_count=source.shape[1],
        cache_tokens=packed.shape[0],
        num_warps=1,
        num_stages=1,
    )


@triton.jit
def _int4_grouped_stage1(
    Q,
    K_PACKED,
    V_PACKED,
    K_SCALES,
    V_SCALES,
    KV_INDPTR,
    KV_INDICES,
    ATT_OUT,
    ATT_LSE,
    NUM_KV_SPLITS,
    stride_qbs,
    stride_qh,
    stride_pkt,
    stride_pkh,
    stride_pvt,
    stride_pvh,
    stride_skt,
    stride_skh,
    stride_svt,
    stride_svh,
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
    mask_h = (cur_head < (cur_head_id + 1) * valid_block_h) & (
        cur_head < q_head_num
    )
    offs_d = tl.arange(0, BLOCK_DMODEL)
    offs_dv = tl.arange(0, BLOCK_DV)
    packed_d = offs_d // 2
    packed_dv = offs_dv // 2
    high_d = (offs_d & 1) != 0
    high_dv = (offs_dv & 1) != 0
    group_d = offs_d // 64
    group_dv = offs_dv // 64
    kv_start = tl.load(KV_INDPTR + cur_batch)
    sequence_length = tl.load(KV_INDPTR + cur_batch + 1) - kv_start
    kv_splits = tl.load(NUM_KV_SPLITS + cur_batch)
    kv_length_per_split = (
        tl.cdiv(tl.cdiv(sequence_length, kv_splits), MIN_BLOCK_KV)
        * MIN_BLOCK_KV
    )
    split_start = kv_length_per_split * split_kv_id
    split_end = tl.minimum(split_start + kv_length_per_split, sequence_length)
    q_offsets = cur_batch * stride_qbs + cur_head[:, None] * stride_qh + offs_d[None, :]
    e_max = tl.zeros([BLOCK_H], dtype=tl.float32) - float("inf")
    e_sum = tl.zeros([BLOCK_H], dtype=tl.float32)
    accumulator = tl.zeros([BLOCK_H, BLOCK_DV], dtype=tl.float32)
    if split_end > split_start:
        q = tl.load(Q + q_offsets, mask=mask_h[:, None], other=0.0).to(tl.float16)
        for start_n in tl.range(split_start, split_end, BLOCK_N):
            offs_n = start_n + tl.arange(0, BLOCK_N)
            token_mask = offs_n < split_end
            kv_location = tl.load(
                KV_INDICES + kv_start + offs_n,
                mask=token_mask,
                other=0,
            )
            k_offsets = (
                kv_location[None, :] * stride_pkt
                + cur_kv_head * stride_pkh
                + packed_d[:, None]
            )
            k_byte = tl.load(
                K_PACKED + k_offsets,
                mask=token_mask[None, :],
                other=0,
            ).to(tl.int32)
            k_nibble = tl.where(high_d[:, None], k_byte >> 4, k_byte & 15)
            k_signed = tl.where(k_nibble > 7, k_nibble - 16, k_nibble)
            k_scale_offsets = (
                kv_location[None, :] * stride_skt
                + cur_kv_head * stride_skh
                + group_d[:, None]
            )
            k_scale = tl.load(
                K_SCALES + k_scale_offsets,
                mask=token_mask[None, :],
                other=0.0,
            )
            k = (k_signed.to(tl.float32) * k_scale).to(tl.float16)
            qk = tl.dot(q, k)
            qk *= 1.0 / 16.0
            qk = tl.where(mask_h[:, None] & token_mask[None, :], qk, -float("inf"))
            v_offsets = (
                kv_location[:, None] * stride_pvt
                + cur_kv_head * stride_pvh
                + packed_dv[None, :]
            )
            v_byte = tl.load(
                V_PACKED + v_offsets,
                mask=token_mask[:, None],
                other=0,
            ).to(tl.int32)
            v_nibble = tl.where(high_dv[None, :], v_byte >> 4, v_byte & 15)
            v_signed = tl.where(v_nibble > 7, v_nibble - 16, v_nibble)
            v_scale_offsets = (
                kv_location[:, None] * stride_svt
                + cur_kv_head * stride_svh
                + group_dv[None, :]
            )
            v_scale = tl.load(
                V_SCALES + v_scale_offsets,
                mask=token_mask[:, None],
                other=0.0,
            )
            v = (v_signed.to(tl.float32) * v_scale).to(tl.float16)
            next_max = tl.maximum(tl.max(qk, 1), e_max)
            previous_scale = tl.exp(e_max - next_max)
            probability = tl.exp(qk - next_max[:, None])
            accumulator *= previous_scale[:, None]
            accumulator += tl.dot(probability.to(tl.float16), v)
            e_sum = e_sum * previous_scale + tl.sum(probability, 1)
            e_max = next_max
        output_offsets = (
            cur_batch * stride_mid_ob
            + cur_head[:, None] * stride_mid_oh
            + split_kv_id * stride_mid_os
            + offs_dv[None, :]
        )
        tl.store(
            ATT_OUT + output_offsets,
            accumulator / e_sum[:, None],
            mask=mask_h[:, None],
        )
        lse_offsets = (
            cur_batch * stride_mid_ob
            + cur_head * stride_mid_oh
            + split_kv_id * stride_mid_os
        ) // BLOCK_DV
        tl.store(ATT_LSE + lse_offsets, e_max + tl.log(e_sum), mask=mask_h)


def int4_paged_decode_attention(
    q,
    k_packed,
    v_packed,
    k_scales,
    v_scales,
    output,
    kv_indptr,
    kv_indices,
    attn_logits,
    attn_lse,
    num_kv_splits,
    max_kv_splits,
):
    if q.shape[1:] != (32, 256):
        raise ValueError("consumer is frozen to Gemma local [32, 32, 256]")
    if k_packed.shape[1:] != (16, 128) or k_scales.shape[1:] != (16, 4):
        raise ValueError("packed local KV layout mismatch")
    grid = (q.shape[0], 16, max_kv_splits)
    compiled = _int4_grouped_stage1[grid](
        q,
        k_packed,
        v_packed,
        k_scales,
        v_scales,
        kv_indptr,
        kv_indices,
        attn_logits,
        attn_lse,
        num_kv_splits,
        q.stride(0),
        q.stride(1),
        k_packed.stride(0),
        k_packed.stride(1),
        v_packed.stride(0),
        v_packed.stride(1),
        k_scales.stride(0),
        k_scales.stride(1),
        v_scales.stride(0),
        v_scales.stride(1),
        attn_logits.stride(0),
        attn_logits.stride(1),
        attn_logits.stride(2),
        kv_group_num=2,
        q_head_num=32,
        BLOCK_DMODEL=256,
        BLOCK_DV=256,
        BLOCK_N=32,
        BLOCK_H=16,
        MIN_BLOCK_KV=32,
        num_warps=4,
        num_stages=2,
    )
    _decode_softmax_reducev_fwd(
        attn_logits,
        attn_lse,
        q,
        output,
        1.0,
        output.new_empty((1, 16, 256)),
        kv_indptr,
        num_kv_splits,
        max_kv_splits,
    )
    return compiled
