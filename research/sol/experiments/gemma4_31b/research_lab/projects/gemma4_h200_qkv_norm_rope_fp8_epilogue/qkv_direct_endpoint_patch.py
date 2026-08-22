#!/usr/bin/env python3
"""Source-bound Gemma4 decode-c32 direct Q/E5M2-KV endpoint adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib

import torch
import triton
import triton.language as tl


EXPECTED_GEMMA4_SHA256 = (
    "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
)
EXPECTED_TRITON_BACKEND_SHA256 = (
    "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d"
)
EXPECTED_RADIX_ATTENTION_SHA256 = (
    "9b1ef7de85b9f0fe9720954edbf94c2b4abd7a57fef7e4dac2500ff3dcdf7be9"
)
BATCH = 32
NUM_Q_HEADS = 32
EPS = 1e-6
_AUDITED: set[tuple[int, int, int, str]] = set()

ANCHOR = "        qkv, _ = self.qkv_proj(hidden_states)\n"
INSERT = """        qkv, _ = self.qkv_proj(hidden_states)
        from qkv_direct_endpoint_patch import try_direct_qkv_to_cache
        direct_q = try_direct_qkv_to_cache(
            self, qkv, positions, forward_batch
        )
        if direct_q is not None:
            attn_output = self.attn(
                direct_q,
                None,
                None,
                forward_batch=forward_batch,
                save_kv_cache=False,
            )
            if attn_output.dim() == 3:
                attn_output = attn_output.flatten(-2, -1)
            output, _ = self.o_proj(attn_output)
            return output
"""


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_jsonl(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(
            descriptor,
            (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@triton.jit
def _qkv_norm_rope_direct_fp8_cache_kernel(
    qkv_ptr,
    q_weight_ptr,
    k_weight_ptr,
    positions_ptr,
    cos_sin_cache_ptr,
    cache_locs_ptr,
    q_out_ptr,
    k_cache_ptr,
    v_cache_ptr,
    stride_qkv_token,
    stride_q_token,
    stride_q_head,
    stride_cache_token,
    stride_cache_head,
    NUM_Q_HEADS: tl.constexpr,
    NUM_KV_HEADS: tl.constexpr,
    HEAD_DIM: tl.constexpr,
    ROTARY_DIM: tl.constexpr,
    Q_SIZE: tl.constexpr,
    KV_SIZE: tl.constexpr,
    EPSILON: tl.constexpr,
    BLOCK: tl.constexpr,
):
    token = tl.program_id(0)
    slot = tl.program_id(1)
    offsets = tl.arange(0, BLOCK)
    mask = offsets < HEAD_DIM
    is_q = slot < NUM_Q_HEADS
    is_k = (slot >= NUM_Q_HEADS) & (slot < NUM_Q_HEADS + NUM_KV_HEADS)
    head = tl.where(
        is_q,
        slot,
        tl.where(is_k, slot - NUM_Q_HEADS, slot - NUM_Q_HEADS - NUM_KV_HEADS),
    )
    segment = tl.where(is_q, 0, tl.where(is_k, Q_SIZE, Q_SIZE + KV_SIZE))
    base = token * stride_qkv_token + segment + head * HEAD_DIM

    value = tl.load(qkv_ptr + base + offsets, mask=mask, other=0.0).to(tl.float32)
    inverse_rms = tl.rsqrt(tl.sum(value * value, axis=0) / HEAD_DIM + EPSILON)
    q_weight = tl.load(q_weight_ptr + offsets, mask=mask, other=1.0).to(tl.float32)
    k_weight = tl.load(k_weight_ptr + offsets, mask=mask, other=1.0).to(tl.float32)
    weight = tl.where(is_q, q_weight, tl.where(is_k, k_weight, 1.0))
    normalized = (value * inverse_rms * weight).to(tl.bfloat16).to(tl.float32)

    rotary_half = ROTARY_DIM // 2
    pair_offsets = tl.where(
        offsets < rotary_half, offsets + rotary_half, offsets - rotary_half
    )
    pair_value = tl.load(
        qkv_ptr + base + pair_offsets,
        mask=mask & (offsets < ROTARY_DIM),
        other=0.0,
    ).to(tl.float32)
    pair_q_weight = tl.load(
        q_weight_ptr + pair_offsets,
        mask=mask & (offsets < ROTARY_DIM),
        other=1.0,
    ).to(tl.float32)
    pair_k_weight = tl.load(
        k_weight_ptr + pair_offsets,
        mask=mask & (offsets < ROTARY_DIM),
        other=1.0,
    ).to(tl.float32)
    pair_weight = tl.where(
        is_q, pair_q_weight, tl.where(is_k, pair_k_weight, 1.0)
    )
    pair_normalized = (
        pair_value * inverse_rms * pair_weight
    ).to(tl.bfloat16).to(tl.float32)
    position = tl.load(positions_ptr + token)
    trig_offset = offsets % rotary_half
    cosine = tl.load(
        cos_sin_cache_ptr + position * ROTARY_DIM + trig_offset,
        mask=mask & (offsets < ROTARY_DIM),
        other=1.0,
    ).to(tl.float32)
    sine = tl.load(
        cos_sin_cache_ptr + position * ROTARY_DIM + rotary_half + trig_offset,
        mask=mask & (offsets < ROTARY_DIM),
        other=0.0,
    ).to(tl.float32)
    rotated = tl.where(
        offsets < rotary_half,
        normalized * cosine - pair_normalized * sine,
        normalized * cosine + pair_normalized * sine,
    )
    output = tl.where((is_q | is_k) & (offsets < ROTARY_DIM), rotated, normalized)
    output = output.to(tl.bfloat16).to(tl.float32)

    q_offset = token * stride_q_token + head * stride_q_head + offsets
    cache_loc = tl.load(cache_locs_ptr + token)
    cache_offset = cache_loc * stride_cache_token + head * stride_cache_head + offsets
    tl.store(q_out_ptr + q_offset, output, mask=mask & is_q)
    tl.store(k_cache_ptr + cache_offset, output, mask=mask & is_k)
    tl.store(v_cache_ptr + cache_offset, output, mask=mask & ~(is_q | is_k))


def _eligible(self, qkv: torch.Tensor, positions: torch.Tensor, forward_batch):
    if self.is_kv_shared_layer or not forward_batch.forward_mode.is_decode():
        return None
    if (
        qkv.shape[0] != BATCH
        or qkv.dtype != torch.bfloat16
        or not qkv.is_cuda
        or qkv.stride() != (qkv.shape[1], 1)
        or positions.shape != (BATCH,)
        or self.num_heads != NUM_Q_HEADS
        or self.q_norm.scale_shift != 0.0
        or self.k_norm.scale_shift != 0.0
        or self.v_norm.with_scale
    ):
        return None
    from sglang.srt.model_executor.forward_context import get_attn_backend

    backend = get_attn_backend()
    if backend.__class__.__module__ != "sglang.srt.layers.attention.triton_backend":
        return None
    pool = backend.token_to_kv_pool
    local = self.attn.sliding_window_size is not None and self.attn.sliding_window_size > -1
    if local:
        if not backend.use_sliding_window_kv_pool:
            return None
        cache_locs = backend.forward_metadata.swa_out_cache_loc
    else:
        cache_locs = forward_batch.out_cache_loc
    if cache_locs is None or cache_locs.shape != (BATCH,):
        return None
    k_cache = pool.get_key_buffer(self.attn.layer_id)
    v_cache = pool.get_value_buffer(self.attn.layer_id)
    if (
        k_cache.dtype != torch.float8_e5m2
        or v_cache.dtype != torch.float8_e5m2
        or k_cache.ndim != 3
        or v_cache.ndim != 3
        or k_cache.shape[1:] != (self.num_kv_heads, self.head_dim)
        or v_cache.shape[1:] != (self.num_kv_heads, self.head_dim)
        or k_cache.stride(-1) != 1
        or v_cache.stride() != k_cache.stride()
        or self.attn.k_scale is not None
        or self.attn.v_scale is not None
    ):
        return None
    return backend, cache_locs, k_cache, v_cache, local


def try_direct_qkv_to_cache(self, qkv, positions, forward_batch):
    """Return direct Q or None; None preserves the byte-for-byte stock path."""
    admitted = _eligible(self, qkv, positions, forward_batch)
    if admitted is None:
        return None
    backend, cache_locs, k_cache, v_cache, local = admitted
    q_out = torch.empty(
        (BATCH, NUM_Q_HEADS, self.head_dim), dtype=qkv.dtype, device=qkv.device
    )
    rotary_dim = int(self.rotary_emb.rotary_dim)
    _qkv_norm_rope_direct_fp8_cache_kernel[
        (BATCH, NUM_Q_HEADS + 2 * self.num_kv_heads)
    ](
        qkv,
        self.q_norm.weight.data,
        self.k_norm.weight.data,
        positions,
        self.rotary_emb.cos_sin_cache,
        cache_locs,
        q_out,
        k_cache,
        v_cache,
        qkv.stride(0),
        q_out.stride(0),
        q_out.stride(1),
        k_cache.stride(0),
        k_cache.stride(1),
        NUM_Q_HEADS=NUM_Q_HEADS,
        NUM_KV_HEADS=self.num_kv_heads,
        HEAD_DIM=self.head_dim,
        ROTARY_DIM=rotary_dim,
        Q_SIZE=self.q_size,
        KV_SIZE=self.kv_size,
        EPSILON=self.q_norm.eps,
        BLOCK=triton.next_power_of_2(self.head_dim),
        num_warps=8 if self.head_dim == 512 else 4,
    )
    key = (self.num_heads, self.num_kv_heads, self.head_dim, "local" if local else "global")
    audit = os.environ.get("QKV_DIRECT_PATH_PROOF")
    if audit and key not in _AUDITED:
        append_jsonl(
            pathlib.Path(audit),
            {
                "schema_version": 1,
                "candidate_symbol": "_qkv_norm_rope_direct_fp8_cache_kernel",
                "producer": "Gemma4Attention.qkv_proj/QKVParallelLinear",
                "first_consumer": "TritonAttnBackend.forward_decode/decode_attention_fwd",
                "geometry": {
                    "batch": BATCH,
                    "num_q_heads": self.num_heads,
                    "num_kv_heads": self.num_kv_heads,
                    "head_dim": self.head_dim,
                    "rotary_dim": rotary_dim,
                    "scope": key[-1],
                },
                "cache_ownership": {
                    "pool_class": type(backend.token_to_kv_pool).__name__,
                    "layer_id": self.attn.layer_id,
                    "location_source": (
                        "forward_metadata.swa_out_cache_loc"
                        if local
                        else "forward_batch.out_cache_loc"
                    ),
                    "cache_dtype": str(k_cache.dtype),
                },
                "stock_cache_write_bypassed": True,
            },
        )
        _AUDITED.add(key)
    return q_out


def install(source: pathlib.Path, audit: pathlib.Path) -> dict[str, object]:
    original = source.read_bytes()
    observed = hashlib.sha256(original).hexdigest()
    if observed != EXPECTED_GEMMA4_SHA256:
        raise RuntimeError(f"pinned Gemma4 source mismatch:{observed}")
    text = original.decode()
    if text.count(ANCHOR) != 1:
        raise RuntimeError("Gemma4Attention qkv producer anchor is not unique")
    patched = text.replace(ANCHOR, INSERT, 1).encode()
    temporary = source.with_suffix(source.suffix + ".qkv-direct-part")
    temporary.write_bytes(patched)
    os.replace(temporary, source)
    value = {
        "schema_version": 1,
        "pass": True,
        "source": str(source),
        "original_sha256": observed,
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "candidate_import": "qkv_direct_endpoint_patch.try_direct_qkv_to_cache",
        "fallback": "unchanged stock Gemma4Attention path",
    }
    audit.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=pathlib.Path(
            "/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py"
        ),
    )
    parser.add_argument("--audit", type=pathlib.Path, required=True)
    args = parser.parse_args()
    install(args.source, args.audit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
