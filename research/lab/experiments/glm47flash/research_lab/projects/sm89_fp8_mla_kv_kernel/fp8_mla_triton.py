"""Minimal paged FP8 MLA writer/decode backport for the pinned Triton image."""

import triton
import triton.language as tl

FP8_MAX = 448.0


@triton.jit
def write_fp8_cache(x, cache, scales, block_table, batch, context, n_heads: tl.constexpr,
                    d_model: tl.constexpr, PAGE_SIZE: tl.constexpr, BLOCK_D: tl.constexpr):
    """Write logical [batch, context, heads, d] into shuffled physical pages."""
    token_id = tl.program_id(0)
    head = tl.program_id(1)
    bid = token_id // context
    token = token_id % context
    logical_page = token // PAGE_SIZE
    page_offset = token % PAGE_SIZE
    physical_page = tl.load(block_table + bid * ((context + PAGE_SIZE - 1) // PAGE_SIZE) + logical_page)
    offsets = tl.arange(0, BLOCK_D)
    mask = offsets < d_model
    src = x + ((bid * context + token) * n_heads + head) * d_model
    values = tl.load(src + offsets, mask=mask, other=0.0).to(tl.float32)
    scale = tl.maximum(tl.max(tl.abs(values), axis=0) / FP8_MAX, 1.0 / FP8_MAX)
    dst = cache + ((physical_page * PAGE_SIZE + page_offset) * n_heads + head) * d_model
    tl.store(dst + offsets, values / scale, mask=mask)
    tl.store(scales + (physical_page * PAGE_SIZE + page_offset) * n_heads + head, scale)


@triton.jit
def decode_fp8_mla(q, cache, scales, block_table, lengths, out, lse, n_heads: tl.constexpr,
                   d_model: tl.constexpr, d_value: tl.constexpr, PAGE_SIZE: tl.constexpr,
                   BLOCK_N: tl.constexpr, BLOCK_D: tl.constexpr, BLOCK_V: tl.constexpr,
                   NUM_KV_SPLITS: tl.constexpr, MAX_CONTEXT: tl.constexpr):
    """Paged decode with BLOCK_N token tiles and one independent split program."""
    bid = tl.program_id(0)
    head = tl.program_id(1)
    split = tl.program_id(2)
    q_offsets = tl.arange(0, BLOCK_D)
    v_offsets = tl.arange(0, BLOCK_V)
    q_ptr = q + (bid * n_heads + head) * d_model
    query = tl.load(q_ptr + q_offsets, mask=q_offsets < d_model, other=0.0).to(tl.float32)
    length = tl.load(lengths + bid)
    split_width = (MAX_CONTEXT + NUM_KV_SPLITS - 1) // NUM_KV_SPLITS
    split_start = split * split_width
    split_end = tl.minimum(split_start + split_width, length)
    m = tl.full((), -float("inf"), tl.float32)
    z = tl.zeros((), tl.float32)
    acc = tl.zeros((BLOCK_V,), tl.float32)
    for tile in range(0, split_width, BLOCK_N):
        tokens = split_start + tile + tl.arange(0, BLOCK_N)
        valid = tokens < split_end
        logical_pages = tokens // PAGE_SIZE
        page_offsets = tokens % PAGE_SIZE
        physical = tl.load(block_table + bid * ((MAX_CONTEXT + PAGE_SIZE - 1) // PAGE_SIZE) + logical_pages,
                           mask=valid, other=0)
        row = physical * PAGE_SIZE + page_offsets
        scale = tl.load(scales + row * n_heads + head, mask=valid, other=1.0)
        key_ptr = cache + (row[:, None] * n_heads + head) * d_model + q_offsets[None, :]
        keys = tl.load(key_ptr, mask=valid[:, None] & (q_offsets[None, :] < d_model), other=0.0).to(tl.float32) * scale[:, None]
        scores = tl.sum(keys * query[None, :], axis=1) * (d_value ** -0.5)
        scores = tl.where(valid, scores, -float("inf"))
        tile_m = tl.max(scores, axis=0)
        new_m = tl.maximum(m, tile_m)
        old_weight = tl.exp(m - new_m)
        weights = tl.exp(scores - new_m)
        value_ptr = cache + (row[:, None] * n_heads + head) * d_model + v_offsets[None, :]
        values = tl.load(value_ptr, mask=valid[:, None] & (v_offsets[None, :] < d_value), other=0.0).to(tl.float32) * scale[:, None]
        acc = acc * old_weight + tl.sum(weights[:, None] * values, axis=0)
        z = z * old_weight + tl.sum(weights, axis=0)
        m = new_m
    out_ptr = out + ((bid * n_heads + head) * NUM_KV_SPLITS + split) * d_value
    tl.store(out_ptr + v_offsets, acc, mask=v_offsets < d_value)
    tl.store(lse + (bid * n_heads + head) * NUM_KV_SPLITS + split, m + tl.log(z))
