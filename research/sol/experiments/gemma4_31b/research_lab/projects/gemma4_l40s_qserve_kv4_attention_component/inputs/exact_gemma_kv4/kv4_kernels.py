"""Exact Gemma-4 KV4 producer and page-size-one decode consumer.

This deliberately implements only the two admitted shapes:
  local:  QH=32, KVH=16, D=256
  global: QH=32, KVH=4,  D=512

The decode schedule mirrors SGLang v0.5.13's grouped split-KV path, but loads
unsigned affine nibbles and dequantizes them inside the QK and P@V operands.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import triton
import triton.language as tl


MAX_SPLITS = 8
BLOCK_N = 32
MIN_BLOCK_KV = 32


@dataclass(frozen=True)
class Geometry:
    name: str
    q_heads: int
    kv_heads: int
    head_dim: int
    window: int | None

    @property
    def group(self) -> int:
        return self.q_heads // self.kv_heads


LOCAL = Geometry("local", 32, 16, 256, 1024)
GLOBAL = Geometry("global", 32, 4, 512, None)
GEOMETRIES = {"local": LOCAL, "global": GLOBAL}


@triton.jit
def _pack_affine_kv4(
    K,
    V,
    Slots,
    K4,
    V4,
    KScale,
    KZero,
    VScale,
    VZero,
    stride_km,
    stride_kh,
    stride_kd,
    stride_vm,
    stride_vh,
    stride_vd,
    stride_k4s,
    stride_k4h,
    stride_v4s,
    stride_v4h,
    stride_ss,
    stride_sh,
    KVH: tl.constexpr,
    D: tl.constexpr,
    BLOCK_D: tl.constexpr,
):
    row = tl.program_id(0)
    kvh = tl.program_id(1)
    slot = tl.load(Slots + row)
    offs = tl.arange(0, BLOCK_D)
    valid = (slot >= 0) & (offs < D)

    k = tl.load(
        K + row * stride_km + kvh * stride_kh + offs * stride_kd,
        mask=offs < D,
        other=0.0,
    ).to(tl.float32)
    v = tl.load(
        V + row * stride_vm + kvh * stride_vh + offs * stride_vd,
        mask=offs < D,
        other=0.0,
    ).to(tl.float32)
    k_for_min = tl.where(offs < D, k, float("inf"))
    k_for_max = tl.where(offs < D, k, -float("inf"))
    v_for_min = tl.where(offs < D, v, float("inf"))
    v_for_max = tl.where(offs < D, v, -float("inf"))
    k_min, k_max = tl.min(k_for_min, axis=0), tl.max(k_for_max, axis=0)
    v_min, v_max = tl.min(v_for_min, axis=0), tl.max(v_for_max, axis=0)
    k_range, v_range = k_max - k_min, v_max - v_min
    ks = tl.where(k_range > 0.0, k_range / 15.0, 1.0)
    vs = tl.where(v_range > 0.0, v_range / 15.0, 1.0)
    kz = tl.where(k_range > 0.0, -k_min / ks, 0.0)
    vz = tl.where(v_range > 0.0, -v_min / vs, 0.0)

    even = tl.arange(0, BLOCK_D // 2) * 2
    pair_mask = (slot >= 0) & (even < D)
    k0 = tl.maximum(0.0, tl.minimum(15.0, tl.floor(k[even] / ks + kz + 0.5))).to(tl.uint8)
    k1 = tl.maximum(0.0, tl.minimum(15.0, tl.floor(k[even + 1] / ks + kz + 0.5))).to(tl.uint8)
    v0 = tl.maximum(0.0, tl.minimum(15.0, tl.floor(v[even] / vs + vz + 0.5))).to(tl.uint8)
    v1 = tl.maximum(0.0, tl.minimum(15.0, tl.floor(v[even + 1] / vs + vz + 0.5))).to(tl.uint8)
    tl.store(
        K4 + slot * stride_k4s + kvh * stride_k4h + even // 2,
        k0 | (k1 << 4),
        mask=pair_mask,
    )
    tl.store(
        V4 + slot * stride_v4s + kvh * stride_v4h + even // 2,
        v0 | (v1 << 4),
        mask=pair_mask,
    )
    tl.store(KScale + slot * stride_ss + kvh * stride_sh, ks, mask=slot >= 0)
    tl.store(KZero + slot * stride_ss + kvh * stride_sh, kz, mask=slot >= 0)
    tl.store(VScale + slot * stride_ss + kvh * stride_sh, vs, mask=slot >= 0)
    tl.store(VZero + slot * stride_ss + kvh * stride_sh, vz, mask=slot >= 0)


@triton.jit
def _store_fp8(
    K,
    V,
    Slots,
    K8,
    V8,
    stride_km,
    stride_kh,
    stride_kd,
    stride_vm,
    stride_vh,
    stride_vd,
    stride_k8s,
    stride_k8h,
    stride_v8s,
    stride_v8h,
    D: tl.constexpr,
    BLOCK_D: tl.constexpr,
):
    row = tl.program_id(0)
    kvh = tl.program_id(1)
    slot = tl.load(Slots + row)
    offs = tl.arange(0, BLOCK_D)
    mask = (slot >= 0) & (offs < D)
    k = tl.load(K + row * stride_km + kvh * stride_kh + offs * stride_kd, mask=offs < D)
    v = tl.load(V + row * stride_vm + kvh * stride_vh + offs * stride_vd, mask=offs < D)
    tl.store(K8 + slot * stride_k8s + kvh * stride_k8h + offs, k, mask=mask)
    tl.store(V8 + slot * stride_v8s + kvh * stride_v8h + offs, v, mask=mask)


@triton.jit
def _kv4_decode_stage1(
    Q,
    K4,
    V4,
    KScale,
    KZero,
    VScale,
    VZero,
    KVIndptr,
    KVIndices,
    NumSplits,
    MidO,
    MidLSE,
    sm_scale,
    stride_qm,
    stride_qh,
    stride_k4s,
    stride_k4h,
    stride_v4s,
    stride_v4h,
    stride_ss,
    stride_sh,
    stride_mom,
    stride_moh,
    stride_mos,
    QH: tl.constexpr,
    KV_GROUP: tl.constexpr,
    D: tl.constexpr,
    BLOCK_D: tl.constexpr,
    BLOCK_H: tl.constexpr,
    BLOCK_N_: tl.constexpr,
):
    batch = tl.program_id(0)
    kv_head = tl.program_id(1)
    split = tl.program_id(2)
    heads = kv_head * KV_GROUP + tl.arange(0, BLOCK_H)
    head_mask = heads < (kv_head + 1) * KV_GROUP
    d = tl.arange(0, BLOCK_D)
    d_mask = d < D
    packed_d = d // 2

    begin = tl.load(KVIndptr + batch)
    seq_len = tl.load(KVIndptr + batch + 1) - begin
    splits = tl.load(NumSplits + batch)
    per_split = tl.cdiv(tl.cdiv(seq_len, splits), MIN_BLOCK_KV) * MIN_BLOCK_KV
    split_start = per_split * split
    split_end = tl.minimum(split_start + per_split, seq_len)

    q = tl.load(
        Q + batch * stride_qm + heads[:, None] * stride_qh + d[None, :],
        mask=head_mask[:, None] & d_mask[None, :],
        other=0.0,
    )
    e_max = tl.full([BLOCK_H], -float("inf"), tl.float32)
    e_sum = tl.zeros([BLOCK_H], tl.float32)
    acc = tl.zeros([BLOCK_H, BLOCK_D], tl.float32)

    if split_end > split_start:
        for start_n in tl.range(split_start, split_end, BLOCK_N_):
            n = start_n + tl.arange(0, BLOCK_N_)
            n_mask = n < split_end
            slots = tl.load(KVIndices + begin + n, mask=n_mask, other=0)
            kbyte = tl.load(
                K4 + slots[None, :] * stride_k4s + kv_head * stride_k4h + packed_d[:, None],
                mask=d_mask[:, None] & n_mask[None, :],
                other=0,
            )
            kn = tl.where((d[:, None] & 1) == 0, kbyte & 15, (kbyte >> 4) & 15)
            ks = tl.load(
                KScale + slots * stride_ss + kv_head * stride_sh,
                mask=n_mask,
                other=1.0,
            ).to(tl.float32)
            kz = tl.load(
                KZero + slots * stride_ss + kv_head * stride_sh,
                mask=n_mask,
                other=0.0,
            ).to(tl.float32)
            k = ((kn.to(tl.float32) - kz[None, :]) * ks[None, :]).to(q.dtype)
            qk = tl.dot(q, k) * sm_scale
            qk = tl.where(head_mask[:, None] & n_mask[None, :], qk, -float("inf"))

            vbyte = tl.load(
                V4 + slots[:, None] * stride_v4s + kv_head * stride_v4h + packed_d[None, :],
                mask=n_mask[:, None] & d_mask[None, :],
                other=0,
            )
            vn = tl.where((d[None, :] & 1) == 0, vbyte & 15, (vbyte >> 4) & 15)
            vs = tl.load(
                VScale + slots * stride_ss + kv_head * stride_sh,
                mask=n_mask,
                other=1.0,
            ).to(tl.float32)
            vz = tl.load(
                VZero + slots * stride_ss + kv_head * stride_sh,
                mask=n_mask,
                other=0.0,
            ).to(tl.float32)
            v = ((vn.to(tl.float32) - vz[:, None]) * vs[:, None]).to(q.dtype)

            next_max = tl.maximum(tl.max(qk, axis=1), e_max)
            old = tl.exp(e_max - next_max)
            p = tl.exp(qk - next_max[:, None])
            acc = acc * old[:, None] + tl.dot(p.to(v.dtype), v)
            e_sum = e_sum * old + tl.sum(p, axis=1)
            e_max = next_max

        out_ptr = (
            MidO
            + batch * stride_mom
            + heads[:, None] * stride_moh
            + split * stride_mos
            + d[None, :]
        )
        tl.store(out_ptr, acc / e_sum[:, None], mask=head_mask[:, None] & d_mask[None, :])
        lse_base = (batch * stride_mom + heads * stride_moh + split * stride_mos) // D
        tl.store(MidLSE + lse_base, e_max + tl.log(e_sum), mask=head_mask)


@triton.jit
def _decode_stage2(
    MidO,
    MidLSE,
    O,
    KVIndptr,
    NumSplits,
    stride_mom,
    stride_moh,
    stride_mos,
    stride_om,
    stride_oh,
    D: tl.constexpr,
    BLOCK_D: tl.constexpr,
):
    batch = tl.program_id(0)
    head = tl.program_id(1)
    d = tl.arange(0, BLOCK_D)
    d_mask = d < D
    seq_len = tl.load(KVIndptr + batch + 1) - tl.load(KVIndptr + batch)
    splits = tl.load(NumSplits + batch)
    per_split = tl.cdiv(tl.cdiv(seq_len, splits), MIN_BLOCK_KV) * MIN_BLOCK_KV
    e_max = -float("inf")
    e_sum = 0.0
    acc = tl.zeros([BLOCK_D], tl.float32)
    base = batch * stride_mom + head * stride_moh
    for split in tl.range(0, MAX_SPLITS):
        active = (per_split * split) < seq_len
        part = tl.load(MidO + base + split * stride_mos + d, mask=active & d_mask, other=0.0)
        lse = tl.load(MidLSE + (base + split * stride_mos) // D, mask=active, other=-float("inf"))
        next_max = tl.maximum(e_max, lse)
        old = tl.exp(e_max - next_max)
        new = tl.exp(lse - next_max)
        acc = acc * old + part * new
        e_sum = e_sum * old + new
        e_max = next_max
    value = tl.where(seq_len > 0, acc / e_sum, 0.0)
    tl.store(O + batch * stride_om + head * stride_oh + d, value, mask=d_mask)


def _geometry(q_heads: int, kv_heads: int, head_dim: int) -> Geometry:
    for geom in GEOMETRIES.values():
        if (q_heads, kv_heads, head_dim) == (geom.q_heads, geom.kv_heads, geom.head_dim):
            return geom
    raise ValueError(f"unsupported exact geometry q_heads={q_heads}, kv_heads={kv_heads}, d={head_dim}")


def append_kv4(k, v, slots, k4, v4, k_scale, k_zero, v_scale, v_zero):
    geom = _geometry(32, k.shape[1], k.shape[-1])
    return _pack_affine_kv4[(k.shape[0], geom.kv_heads)](
        k, v, slots, k4, v4, k_scale, k_zero, v_scale, v_zero,
        k.stride(0), k.stride(1), k.stride(2),
        v.stride(0), v.stride(1), v.stride(2),
        k4.stride(0), k4.stride(1), v4.stride(0), v4.stride(1),
        k_scale.stride(0), k_scale.stride(1),
        KVH=geom.kv_heads, D=geom.head_dim, BLOCK_D=geom.head_dim,
        num_warps=8, num_stages=1,
    )


def append_fp8(k, v, slots, k8, v8):
    geom = _geometry(32, k.shape[1], k.shape[-1])
    return _store_fp8[(k.shape[0], geom.kv_heads)](
        k, v, slots, k8, v8,
        k.stride(0), k.stride(1), k.stride(2),
        v.stride(0), v.stride(1), v.stride(2),
        k8.stride(0), k8.stride(1), v8.stride(0), v8.stride(1),
        D=geom.head_dim, BLOCK_D=geom.head_dim, num_warps=8, num_stages=1,
    )


def decode_kv4(q, cache, kv_indptr, kv_indices, num_splits):
    k4, v4, ks, kz, vs, vz = cache
    geom = _geometry(q.shape[1], k4.shape[1], k4.shape[-1] * 2)
    m = q.shape[0]
    mid_o = torch.empty((m, geom.q_heads, MAX_SPLITS, geom.head_dim), dtype=torch.float32, device=q.device)
    mid_lse = torch.empty((m, geom.q_heads, MAX_SPLITS), dtype=torch.float32, device=q.device)
    out = torch.empty_like(q)
    compiled1 = _kv4_decode_stage1[(m, geom.kv_heads, MAX_SPLITS)](
        q, k4, v4, ks, kz, vs, vz, kv_indptr, kv_indices, num_splits, mid_o, mid_lse,
        1.0 / math.sqrt(geom.head_dim),
        q.stride(0), q.stride(1),
        k4.stride(0), k4.stride(1), v4.stride(0), v4.stride(1),
        ks.stride(0), ks.stride(1),
        mid_o.stride(0), mid_o.stride(1), mid_o.stride(2),
        QH=geom.q_heads, KV_GROUP=geom.group, D=geom.head_dim,
        BLOCK_D=geom.head_dim, BLOCK_H=geom.group, BLOCK_N_=BLOCK_N,
        num_warps=4, num_stages=2,
    )
    compiled2 = _decode_stage2[(m, geom.q_heads)](
        mid_o, mid_lse, out, kv_indptr, num_splits,
        mid_o.stride(0), mid_o.stride(1), mid_o.stride(2),
        out.stride(0), out.stride(1),
        D=geom.head_dim, BLOCK_D=geom.head_dim, num_warps=4, num_stages=2,
    )
    return out, (compiled1, compiled2)
