from __future__ import annotations

from dataclasses import dataclass

import torch
import triton
import triton.language as tl


@triton.jit
def _qkv_norm_rope_cache_kernel(
    qkv,
    q_weight,
    k_weight,
    positions,
    cos_sin_cache,
    cache_slots,
    k_cache,
    v_cache,
    qkv_stride_m,
    cache_stride_token,
    cache_stride_head,
    cache_slots_count,
    NUM_Q_HEADS: tl.constexpr,
    NUM_KV_HEADS: tl.constexpr,
    HEAD_DIM: tl.constexpr,
    HALF_DIM: tl.constexpr,
    Q_SIZE: tl.constexpr,
    KV_SIZE: tl.constexpr,
    EPS: tl.constexpr,
    K_SCALE: tl.constexpr,
    V_SCALE: tl.constexpr,
    WRITE_CACHE: tl.constexpr,
    BLOCK_HALF: tl.constexpr,
):
    token = tl.program_id(0)
    head_slot = tl.program_id(1)
    half_offsets = tl.arange(0, BLOCK_HALF)
    half_mask = half_offsets < HALF_DIM

    is_q = head_slot < NUM_Q_HEADS
    is_k = (head_slot >= NUM_Q_HEADS) & (
        head_slot < NUM_Q_HEADS + NUM_KV_HEADS
    )
    is_v = head_slot >= NUM_Q_HEADS + NUM_KV_HEADS
    head = tl.where(
        is_q,
        head_slot,
        tl.where(
            is_k,
            head_slot - NUM_Q_HEADS,
            head_slot - NUM_Q_HEADS - NUM_KV_HEADS,
        ),
    )
    segment = tl.where(is_q, 0, tl.where(is_k, Q_SIZE, Q_SIZE + KV_SIZE))
    base = token * qkv_stride_m + segment + head * HEAD_DIM

    x0 = tl.load(qkv + base + half_offsets, mask=half_mask, other=0.0).to(
        tl.float32
    )
    x1 = tl.load(
        qkv + base + HALF_DIM + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    sum_squares = tl.sum(x0 * x0 + x1 * x1, axis=0)
    inverse_rms = tl.rsqrt(sum_squares / HEAD_DIM + EPS)

    q_weight0 = tl.load(
        q_weight + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    q_weight1 = tl.load(
        q_weight + HALF_DIM + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    k_weight0 = tl.load(
        k_weight + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    k_weight1 = tl.load(
        k_weight + HALF_DIM + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    weight0 = tl.where(is_q, q_weight0, tl.where(is_k, k_weight0, 1.0))
    weight1 = tl.where(is_q, q_weight1, tl.where(is_k, k_weight1, 1.0))
    normalized0 = x0 * inverse_rms * weight0
    normalized1 = x1 * inverse_rms * weight1

    position = tl.load(positions + token)
    cache_base = position * HEAD_DIM
    cosine = tl.load(
        cos_sin_cache + cache_base + half_offsets,
        mask=half_mask,
        other=1.0,
    ).to(tl.float32)
    sine = tl.load(
        cos_sin_cache + cache_base + HALF_DIM + half_offsets,
        mask=half_mask,
        other=0.0,
    ).to(tl.float32)
    rotated0 = normalized0 * cosine - normalized1 * sine
    rotated1 = normalized1 * cosine + normalized0 * sine
    output0 = tl.where(is_v, normalized0, rotated0).to(tl.bfloat16)
    output1 = tl.where(is_v, normalized1, rotated1).to(tl.bfloat16)
    tl.store(qkv + base + half_offsets, output0, mask=half_mask)
    tl.store(
        qkv + base + HALF_DIM + half_offsets,
        output1,
        mask=half_mask,
    )

    if WRITE_CACHE:
        slot = tl.load(cache_slots + token)
        slot_valid = (slot >= 0) & (slot < cache_slots_count)
        cache_base = slot * cache_stride_token + head * cache_stride_head
        tl.store(
            k_cache + cache_base + half_offsets,
            output0 / K_SCALE,
            mask=half_mask & slot_valid & is_k,
        )
        tl.store(
            k_cache + cache_base + HALF_DIM + half_offsets,
            output1 / K_SCALE,
            mask=half_mask & slot_valid & is_k,
        )
        tl.store(
            v_cache + cache_base + half_offsets,
            output0 / V_SCALE,
            mask=half_mask & slot_valid & is_v,
        )
        tl.store(
            v_cache + cache_base + HALF_DIM + half_offsets,
            output1 / V_SCALE,
            mask=half_mask & slot_valid & is_v,
        )


@dataclass(frozen=True)
class CacheDestination:
    slots: torch.Tensor
    key: torch.Tensor
    value: torch.Tensor


def _validate_common(
    qkv: torch.Tensor,
    q_weight: torch.Tensor,
    k_weight: torch.Tensor,
    positions: torch.Tensor,
    cos_sin_cache: torch.Tensor,
    num_q_heads: int,
    num_kv_heads: int,
    head_dim: int,
) -> None:
    expected_width = (num_q_heads + 2 * num_kv_heads) * head_dim
    if qkv.device.type != "cuda":
        raise ValueError("qkv must be a CUDA tensor")
    if qkv.dtype != torch.bfloat16 or qkv.ndim != 2:
        raise ValueError("qkv must be rank-2 bfloat16")
    if qkv.shape[1] != expected_width or qkv.stride(1) != 1:
        raise ValueError(
            f"qkv must have width {expected_width} and a contiguous inner dimension"
        )
    if head_dim not in (256, 512) or head_dim % 2:
        raise ValueError("the exact Gemma 4 head dimensions are 256 and 512")
    for name, weight in (("q_weight", q_weight), ("k_weight", k_weight)):
        if (
            weight.device != qkv.device
            or weight.dtype != torch.bfloat16
            or weight.numel() != head_dim
            or not weight.is_contiguous()
        ):
            raise ValueError(f"{name} must be contiguous bfloat16[{head_dim}] on CUDA")
    if (
        positions.device != qkv.device
        or positions.dtype not in (torch.int32, torch.int64)
        or positions.ndim != 1
        or positions.numel() != qkv.shape[0]
    ):
        raise ValueError("positions must be one integral CUDA element per token")
    if (
        cos_sin_cache.device != qkv.device
        or cos_sin_cache.dtype != torch.float32
        or cos_sin_cache.ndim != 2
        or cos_sin_cache.shape[1] != head_dim
        or not cos_sin_cache.is_contiguous()
    ):
        raise ValueError("cos_sin_cache must be contiguous float32[max_position, D]")


def _launch(
    qkv: torch.Tensor,
    q_weight: torch.Tensor,
    k_weight: torch.Tensor,
    positions: torch.Tensor,
    cos_sin_cache: torch.Tensor,
    *,
    num_q_heads: int,
    num_kv_heads: int,
    head_dim: int,
    eps: float,
    destination: CacheDestination | None,
    k_scale: float,
    v_scale: float,
) -> None:
    _validate_common(
        qkv,
        q_weight,
        k_weight,
        positions,
        cos_sin_cache,
        num_q_heads,
        num_kv_heads,
        head_dim,
    )
    write_cache = destination is not None
    if write_cache:
        slots = destination.slots
        key = destination.key
        value = destination.value
        if (
            slots.device != qkv.device
            or slots.dtype not in (torch.int32, torch.int64)
            or slots.ndim != 1
            or slots.numel() != qkv.shape[0]
        ):
            raise ValueError("cache slots must be one integral CUDA element per token")
        expected_tail = (num_kv_heads, head_dim)
        for name, buffer in (("key", key), ("value", value)):
            if (
                buffer.device != qkv.device
                or buffer.dtype != torch.float8_e5m2
                or buffer.ndim != 3
                or tuple(buffer.shape[1:]) != expected_tail
                or buffer.stride(2) != 1
            ):
                raise ValueError(
                    f"{name} cache must be NHD float8_e5m2[:, {num_kv_heads}, {head_dim}]"
                )
        if key.shape != value.shape or key.stride() != value.stride():
            raise ValueError("key/value caches must have identical shapes and strides")
        cache_slots_count = key.shape[0]
        cache_stride_token = key.stride(0)
        cache_stride_head = key.stride(1)
    else:
        slots = positions
        key = qkv
        value = qkv
        cache_slots_count = 1
        cache_stride_token = 1
        cache_stride_head = 1

    block_size = triton.next_power_of_2(head_dim)
    grid = (qkv.shape[0], num_q_heads + 2 * num_kv_heads)
    _qkv_norm_rope_cache_kernel[grid](
        qkv,
        q_weight,
        k_weight,
        positions,
        cos_sin_cache,
        slots,
        key,
        value,
        qkv.stride(0),
        cache_stride_token,
        cache_stride_head,
        cache_slots_count,
        NUM_Q_HEADS=num_q_heads,
        NUM_KV_HEADS=num_kv_heads,
        HEAD_DIM=head_dim,
        HALF_DIM=head_dim // 2,
        Q_SIZE=num_q_heads * head_dim,
        KV_SIZE=num_kv_heads * head_dim,
        EPS=eps,
        K_SCALE=k_scale,
        V_SCALE=v_scale,
        WRITE_CACHE=write_cache,
        BLOCK_HALF=block_size // 2,
        num_warps=4,
    )


def qkv_norm_rope_inplace(
    qkv: torch.Tensor,
    q_weight: torch.Tensor,
    k_weight: torch.Tensor,
    positions: torch.Tensor,
    cos_sin_cache: torch.Tensor,
    *,
    num_q_heads: int,
    num_kv_heads: int,
    head_dim: int,
    eps: float,
) -> None:
    _launch(
        qkv,
        q_weight,
        k_weight,
        positions,
        cos_sin_cache,
        num_q_heads=num_q_heads,
        num_kv_heads=num_kv_heads,
        head_dim=head_dim,
        eps=eps,
        destination=None,
        k_scale=1.0,
        v_scale=1.0,
    )


def qkv_norm_rope_cache_store(
    qkv: torch.Tensor,
    q_weight: torch.Tensor,
    k_weight: torch.Tensor,
    positions: torch.Tensor,
    cos_sin_cache: torch.Tensor,
    destination: CacheDestination,
    *,
    num_q_heads: int,
    num_kv_heads: int,
    head_dim: int,
    eps: float,
    k_scale: float,
    v_scale: float,
) -> None:
    if not (k_scale > 0.0 and v_scale > 0.0):
        raise ValueError("KV scales must be positive")
    _launch(
        qkv,
        q_weight,
        k_weight,
        positions,
        cos_sin_cache,
        num_q_heads=num_q_heads,
        num_kv_heads=num_kv_heads,
        head_dim=head_dim,
        eps=eps,
        destination=destination,
        k_scale=k_scale,
        v_scale=v_scale,
    )


def resolve_cache_destination(layer, forward_batch) -> CacheDestination:
    from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool
    from sglang.srt.model_executor.forward_context import get_attn_backend

    backend = get_attn_backend()
    pool = backend.token_to_kv_pool
    slots = forward_batch.out_cache_loc
    layer_index = layer.layer_id
    if isinstance(pool, SWAKVPool):
        layer_index, is_swa = pool.layers_mapping[layer.layer_id]
        if is_swa:
            slots = backend.forward_metadata.swa_out_cache_loc
            pool = pool.swa_kv_pool
        else:
            pool = pool.full_kv_pool
    if pool.kv_cache_layout != "nhd":
        raise ValueError(f"unsupported KV layout: {pool.kv_cache_layout}")
    if pool.dtype != torch.float8_e5m2 or pool.store_dtype != torch.uint8:
        raise ValueError("candidate requires the v0.5.13 uint8-backed E5M2 KV cache")
    key, value = pool.get_kv_buffer(layer_index)
    return CacheDestination(slots, key, value)
