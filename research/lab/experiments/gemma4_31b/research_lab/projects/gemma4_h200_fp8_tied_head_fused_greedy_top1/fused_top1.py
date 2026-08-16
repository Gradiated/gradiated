from __future__ import annotations

import torch
import triton
import triton.language as tl


HIDDEN = 5376
VOCAB = 262144
BLOCK_M = 16
BLOCK_N = 64
BLOCK_K = 64
PARTIALS = VOCAB // BLOCK_N


@triton.jit
def _fp8_gemm_partial_top1(
    a,
    b,
    scale_a,
    scale_b,
    partial_values,
    partial_indices,
    m: tl.constexpr,
    stride_am: tl.constexpr,
    stride_ak: tl.constexpr,
    stride_bk: tl.constexpr,
    stride_bn: tl.constexpr,
    block_m: tl.constexpr,
    block_n: tl.constexpr,
    block_k: tl.constexpr,
    hidden: tl.constexpr,
    vocab: tl.constexpr,
    partials: tl.constexpr,
):
    pid_n = tl.program_id(0)
    pid_m = tl.program_id(1)
    offs_m = pid_m * block_m + tl.arange(0, block_m)
    offs_n = pid_n * block_n + tl.arange(0, block_n)
    offs_k = tl.arange(0, block_k)
    accumulator = tl.zeros((block_m, block_n), dtype=tl.float32)
    for start_k in range(0, hidden, block_k):
        a_tile = tl.load(
            a
            + offs_m[:, None] * stride_am
            + (start_k + offs_k[None, :]) * stride_ak,
            mask=offs_m[:, None] < m,
            other=0.0,
        )
        b_tile = tl.load(
            b
            + (start_k + offs_k[:, None]) * stride_bk
            + offs_n[None, :] * stride_bn
        )
        accumulator = tl.dot(a_tile, b_tile, accumulator)

    row_max = tl.max(accumulator, axis=1)
    matching_indices = tl.where(
        accumulator == row_max[:, None],
        offs_n[None, :],
        vocab,
    )
    row_index = tl.min(matching_indices, axis=1)
    output_offset = offs_m * partials + pid_n
    combined_scale = tl.load(scale_a) * tl.load(scale_b)
    tl.store(
        partial_values + output_offset,
        row_max * combined_scale,
        mask=offs_m < m,
    )
    tl.store(partial_indices + output_offset, row_index, mask=offs_m < m)


@triton.jit
def _reduce_partial_top1(
    partial_values,
    partial_indices,
    token_ids,
    top_values,
    partials: tl.constexpr,
    block_partials: tl.constexpr,
    vocab: tl.constexpr,
):
    row = tl.program_id(0)
    offsets = tl.arange(0, block_partials)
    values = tl.load(
        partial_values + row * partials + offsets,
        mask=offsets < partials,
        other=-float("inf"),
    )
    indices = tl.load(
        partial_indices + row * partials + offsets,
        mask=offsets < partials,
        other=vocab,
    )
    maximum = tl.max(values, axis=0)
    matching_indices = tl.where(values == maximum, indices, vocab)
    token = tl.min(matching_indices, axis=0)
    tl.store(token_ids + row, token)
    tl.store(top_values + row, maximum)


def fp8_greedy_top1(
    q_hidden: torch.Tensor,
    fp8_weight: torch.Tensor,
    activation_scale: torch.Tensor,
    weight_scale: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    if q_hidden.ndim != 2 or q_hidden.shape[1] != HIDDEN:
        raise ValueError(f"expected q_hidden [M,{HIDDEN}], got {tuple(q_hidden.shape)}")
    if not 1 <= q_hidden.shape[0] <= 32:
        raise ValueError(f"expected 1 <= M <= 32, got {q_hidden.shape[0]}")
    if q_hidden.dtype != torch.float8_e4m3fn:
        raise TypeError(f"expected E4M3 activation, got {q_hidden.dtype}")
    if (
        tuple(fp8_weight.shape) != (HIDDEN, VOCAB)
        or fp8_weight.dtype != torch.float8_e4m3fn
        or fp8_weight.stride() != (1, HIDDEN)
    ):
        raise ValueError(
            "expected column-major E4M3 weight "
            f"[{HIDDEN},{VOCAB}] stride (1,{HIDDEN}), got "
            f"{tuple(fp8_weight.shape)} {fp8_weight.dtype} {fp8_weight.stride()}"
        )
    if activation_scale.numel() != 1 or weight_scale.numel() != 1:
        raise ValueError("only predecessor per-tensor scales are supported")

    m = q_hidden.shape[0]
    partial_values = torch.empty(
        (m, PARTIALS), device=q_hidden.device, dtype=torch.float32
    )
    partial_indices = torch.empty(
        (m, PARTIALS), device=q_hidden.device, dtype=torch.int32
    )
    token_ids = torch.empty((m,), device=q_hidden.device, dtype=torch.int64)
    top_values = torch.empty((m,), device=q_hidden.device, dtype=torch.float32)
    grid = (PARTIALS, triton.cdiv(m, BLOCK_M))
    _fp8_gemm_partial_top1[grid](
        q_hidden,
        fp8_weight,
        activation_scale,
        weight_scale,
        partial_values,
        partial_indices,
        m=m,
        stride_am=q_hidden.stride(0),
        stride_ak=q_hidden.stride(1),
        stride_bk=fp8_weight.stride(0),
        stride_bn=fp8_weight.stride(1),
        block_m=BLOCK_M,
        block_n=BLOCK_N,
        block_k=BLOCK_K,
        hidden=HIDDEN,
        vocab=VOCAB,
        partials=PARTIALS,
        num_warps=8,
        num_stages=3,
    )
    _reduce_partial_top1[(m,)](
        partial_values,
        partial_indices,
        token_ids,
        top_values,
        partials=PARTIALS,
        block_partials=PARTIALS,
        vocab=VOCAB,
        num_warps=8,
    )
    return token_ids, top_values, partial_values, partial_indices
