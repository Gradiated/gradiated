from __future__ import annotations

import torch
import triton
import triton.language as tl


LOGICAL_RING_TOKENS = 1024
PHYSICAL_RING_TOKENS = 2048


@triton.jit
def _store_mirrored_ring_kv_kernel(
    K,
    V,
    K_RING,
    V_RING,
    REQUEST_IDS,
    ABSOLUTE_POSITIONS,
    K_SCALE: tl.constexpr,
    V_SCALE: tl.constexpr,
    LOGICAL_RING_TOKENS: tl.constexpr,
    PHYSICAL_RING_TOKENS: tl.constexpr,
    n_elements: tl.constexpr,
    row_elements: tl.constexpr,
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
    safe_request_ids = tl.maximum(request_ids, 0)
    ring_positions = absolute_positions & (LOGICAL_RING_TOKENS - 1)
    first = (
        (safe_request_ids * PHYSICAL_RING_TOKENS + ring_positions) * row_elements
        + within_row
    )
    second = first + LOGICAL_RING_TOKENS * row_elements
    k = tl.load(K + offsets, mask=valid, other=0.0) / K_SCALE
    v = tl.load(V + offsets, mask=valid, other=0.0) / V_SCALE
    tl.store(K_RING + first, k, mask=valid)
    tl.store(V_RING + first, v, mask=valid)
    tl.store(K_RING + second, k, mask=valid)
    tl.store(V_RING + second, v, mask=valid)


@triton.jit
def _store_mirrored_ring_bytes_kernel(
    K_BYTES,
    V_BYTES,
    K_RING_BYTES,
    V_RING_BYTES,
    REQUEST_IDS,
    ABSOLUTE_POSITIONS,
    LOGICAL_RING_TOKENS: tl.constexpr,
    PHYSICAL_RING_TOKENS: tl.constexpr,
    n_elements: tl.constexpr,
    row_elements: tl.constexpr,
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
    safe_request_ids = tl.maximum(request_ids, 0)
    ring_positions = absolute_positions & (LOGICAL_RING_TOKENS - 1)
    first = (
        (safe_request_ids * PHYSICAL_RING_TOKENS + ring_positions) * row_elements
        + within_row
    )
    second = first + LOGICAL_RING_TOKENS * row_elements
    k = tl.load(K_BYTES + offsets, mask=valid, other=0)
    v = tl.load(V_BYTES + offsets, mask=valid, other=0)
    tl.store(K_RING_BYTES + first, k, mask=valid)
    tl.store(V_RING_BYTES + first, v, mask=valid)
    tl.store(K_RING_BYTES + second, k, mask=valid)
    tl.store(V_RING_BYTES + second, v, mask=valid)


def _validate(k, v, k_ring, v_ring, request_ids, absolute_positions) -> None:
    if k.shape != v.shape or k.ndim != 3:
        raise ValueError("K/V must be matching [tokens, heads, dim] tensors")
    if k_ring.shape != v_ring.shape or k_ring.ndim != 4:
        raise ValueError("mirrored buffers must be matching four-dimensional tensors")
    if k_ring.shape[1] != PHYSICAL_RING_TOKENS:
        raise ValueError("mirrored buffers must contain exactly 2,048 physical tokens")
    if request_ids.numel() != k.shape[0]:
        raise ValueError("request-id count must equal token count")
    if absolute_positions.numel() != k.shape[0]:
        raise ValueError("position count must equal token count")


def store_mirrored_ring_kv(
    k,
    v,
    k_ring,
    v_ring,
    request_ids,
    absolute_positions,
    k_scale=1.0,
    v_scale=1.0,
):
    _validate(k, v, k_ring, v_ring, request_ids, absolute_positions)
    row_elements = k.shape[1] * k.shape[2]
    n_elements = k.numel()
    block = 1024
    return _store_mirrored_ring_kv_kernel[(triton.cdiv(n_elements, block),)](
        k,
        v,
        k_ring,
        v_ring,
        request_ids,
        absolute_positions,
        k_scale,
        v_scale,
        LOGICAL_RING_TOKENS=LOGICAL_RING_TOKENS,
        PHYSICAL_RING_TOKENS=PHYSICAL_RING_TOKENS,
        n_elements=n_elements,
        row_elements=row_elements,
        BLOCK=block,
        num_warps=8,
        num_stages=2,
    )


def store_mirrored_ring_kv_bytes(
    k,
    v,
    k_ring,
    v_ring,
    request_ids,
    absolute_positions,
):
    _validate(k, v, k_ring, v_ring, request_ids, absolute_positions)
    if any(tensor.element_size() != 1 for tensor in (k, v, k_ring, v_ring)):
        raise ValueError("byte store requires one-byte source and destination elements")
    row_elements = k.shape[1] * k.shape[2]
    n_elements = k.numel()
    block = 1024
    return _store_mirrored_ring_bytes_kernel[(triton.cdiv(n_elements, block),)](
        k.contiguous().view(torch.uint8),
        v.contiguous().view(torch.uint8),
        k_ring.view(torch.uint8),
        v_ring.view(torch.uint8),
        request_ids,
        absolute_positions,
        LOGICAL_RING_TOKENS=LOGICAL_RING_TOKENS,
        PHYSICAL_RING_TOKENS=PHYSICAL_RING_TOKENS,
        n_elements=n_elements,
        row_elements=row_elements,
        BLOCK=block,
        num_warps=8,
        num_stages=2,
    )


@triton.jit
def _restore_mirrored_ring_prefix_kernel(
    K_PAGED,
    V_PAGED,
    K_RING,
    V_RING,
    REQUEST_IDS,
    SEQ_LENS,
    KV_INDPTR,
    KV_INDICES,
    LOGICAL_RING_TOKENS: tl.constexpr,
    PHYSICAL_RING_TOKENS: tl.constexpr,
    row_elements: tl.constexpr,
    EXCLUDE_LAST: tl.constexpr,
    BLOCK: tl.constexpr,
):
    batch = tl.program_id(0)
    token = tl.program_id(1)
    element_block = tl.program_id(2)
    request_id = tl.load(REQUEST_IDS + batch)
    valid_request = request_id >= 0
    safe_request_id = tl.maximum(request_id, 0)
    seq_len = tl.load(SEQ_LENS + batch)
    start = tl.load(KV_INDPTR + batch)
    end = tl.load(KV_INDPTR + batch + 1)
    valid_token = valid_request & (start + token < end - EXCLUDE_LAST)
    paged_slot = tl.load(KV_INDICES + start + token, mask=valid_token, other=0)
    absolute_position = seq_len - (end - start) + token
    ring_position = absolute_position & (LOGICAL_RING_TOKENS - 1)
    elements = element_block * BLOCK + tl.arange(0, BLOCK)
    valid = valid_token & (elements < row_elements)
    source = paged_slot * row_elements + elements
    first = (
        (safe_request_id * PHYSICAL_RING_TOKENS + ring_position) * row_elements
        + elements
    )
    second = first + LOGICAL_RING_TOKENS * row_elements
    k = tl.load(K_PAGED + source, mask=valid, other=0.0)
    v = tl.load(V_PAGED + source, mask=valid, other=0.0)
    tl.store(K_RING + first, k, mask=valid)
    tl.store(V_RING + first, v, mask=valid)
    tl.store(K_RING + second, k, mask=valid)
    tl.store(V_RING + second, v, mask=valid)


def restore_mirrored_ring_prefix(
    k_paged,
    v_paged,
    k_ring,
    v_ring,
    request_ids,
    seq_lens,
    kv_indptr,
    kv_indices,
    exclude_last=True,
):
    row_elements = k_paged.shape[1] * k_paged.shape[2]
    block = 1024
    return _restore_mirrored_ring_prefix_kernel[
        (
            request_ids.numel(),
            k_ring.shape[1] // 2,
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
        LOGICAL_RING_TOKENS=LOGICAL_RING_TOKENS,
        PHYSICAL_RING_TOKENS=PHYSICAL_RING_TOKENS,
        row_elements=row_elements,
        EXCLUDE_LAST=exclude_last,
        BLOCK=block,
        num_warps=8,
        num_stages=2,
    )
