#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


SOURCE_HASHES = {
    "flashattention_backend.py": "5f0b17d2b4313f83d918f956ec4529e72c985c5824fd7f5bec7623496f4b740a",
    "triton_backend.py": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "memory_pool.py": "37f9915a2945c7bb389212eed65eb770cb9e3fa6976d0778b6831d2ac29d7bdd",
    "swa_memory_pool.py": "36830cdb84cc344ffb7bac9ff30ba9a41b488d67893a5015ecbba584e95a9858",
}
LOCAL_WALL_FRACTION = 0.1531203203096733
REQUIRED_REDUCTION = 0.3507436965788028


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def timed_ms(fn) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    fn()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def source_identity() -> dict[str, Any]:
    import sglang.srt.layers.attention.flashattention_backend as flash_module
    import sglang.srt.layers.attention.triton_backend as triton_module
    import sglang.srt.mem_cache.memory_pool as pool_module
    import sglang.srt.mem_cache.swa_memory_pool as swa_module

    observed = {}
    for module in (flash_module, triton_module, pool_module, swa_module):
        path = Path(module.__file__).resolve()
        observed[path.name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    mismatches = {
        name: row["sha256"]
        for name, row in observed.items()
        if SOURCE_HASHES.get(name) != row["sha256"]
    }
    if mismatches:
        raise RuntimeError(f"pinned_source_mismatch:{mismatches}")
    return observed


def make_pool(context: int, batch_size: int):
    from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool

    slots = context * batch_size + 1
    pool = SWAKVPool(
        size=slots,
        size_swa=slots,
        page_size=1,
        dtype=torch.float8_e4m3fn,
        head_num=4,
        head_dim=512,
        v_head_dim=512,
        swa_head_num=16,
        swa_head_dim=256,
        swa_v_head_dim=256,
        swa_attention_layer_ids=[0],
        full_attention_layer_ids=[5],
        enable_kvcache_transpose=False,
        enable_alt_stream=False,
        device="cuda",
    )
    pool.register_mapping(torch.arange(slots + 1, dtype=torch.int64, device="cuda"))
    return pool, slots


def make_layer():
    from sglang.srt.layers.radix_attention import RadixAttention

    return RadixAttention(
        num_heads=32,
        head_dim=256,
        scaling=1 / math.sqrt(256),
        num_kv_heads=16,
        layer_id=0,
        v_head_dim=256,
        sliding_window_size=1023,
    ).cuda()


def make_backends(pool, metadata):
    from sglang.srt.layers.attention.flashattention_backend import (
        FlashAttentionBackend,
    )
    from sglang.srt.layers.attention.triton_backend import TritonAttnBackend
    from sglang.srt.layers.attention.triton_ops.decode_attention import (
        decode_attention_fwd,
    )
    from sgl_kernel.flash_attn import flash_attn_with_kvcache

    triton = object.__new__(TritonAttnBackend)
    triton.token_to_kv_pool = pool
    triton.forward_metadata = metadata["triton"]
    triton.use_mla = False
    triton.use_sliding_window_kv_pool = True
    triton.swa_v_head_dim = 256
    triton.max_kv_splits = 8
    triton.decode_attention_fwd = torch.compiler.disable(decode_attention_fwd)
    triton.use_pdl = False

    fa3 = object.__new__(FlashAttentionBackend)
    fa3.token_to_kv_pool = pool
    fa3.forward_metadata = metadata["fa3"]
    fa3.use_mla = False
    fa3.use_sliding_window_kv_pool = True
    fa3.kv_cache_dtype_str = "fp8_e4m3"
    fa3.kv_cache_dtype = torch.float8_e4m3fn
    fa3.has_local_attention = False
    fa3.attention_chunk_size = 1024
    fa3.topk = 0
    fa3.num_splits = 0
    fa3.fa_impl_ver = 3
    fa3.flash_attn_with_kvcache = flash_attn_with_kvcache
    return triton, fa3


def make_metadata(
    batch_size: int,
    context: int,
    req_to_slots: torch.Tensor,
    current_slots: torch.Tensor,
):
    from sglang.srt.layers.attention.flashattention_backend import (
        FlashAttentionMetadata,
    )
    from sglang.srt.layers.attention.triton_backend import ForwardMetadata

    indptr = torch.arange(
        0,
        (batch_size + 1) * context,
        step=context,
        dtype=torch.int32,
        device="cuda",
    )
    indices = req_to_slots.flatten().to(torch.int64)
    splits = torch.full((batch_size,), 8, dtype=torch.int32, device="cuda")
    triton = ForwardMetadata(
        attn_logits=torch.empty(
            (batch_size, 32, 8, 512), dtype=torch.float32, device="cuda"
        ),
        attn_lse=torch.empty(
            (batch_size, 32, 8), dtype=torch.float32, device="cuda"
        ),
        max_extend_len=None,
        num_kv_splits=splits,
        kv_indptr=indptr,
        kv_indices=indices,
        qo_indptr=None,
        custom_mask=None,
        mask_indptr=None,
        window_kv_indptr=indptr,
        window_kv_indices=indices,
        window_num_kv_splits=splits,
        window_kv_offsets=None,
        swa_attn_logits=torch.empty(
            (batch_size, 32, 8, 256), dtype=torch.float32, device="cuda"
        ),
        swa_out_cache_loc=current_slots,
    )
    cu_query = torch.arange(
        batch_size + 1, dtype=torch.int32, device="cuda"
    )
    fa3 = FlashAttentionMetadata(
        cache_seqlens_int32=torch.full(
            (batch_size,), context, dtype=torch.int32, device="cuda"
        ),
        max_seq_len_q=1,
        max_seq_len_k=context,
        cu_seqlens_q=cu_query,
        cu_seqlens_k=indptr,
        page_table=req_to_slots.to(torch.int32),
        swa_page_table=req_to_slots.to(torch.int32),
        swa_out_cache_loc=current_slots,
    )
    return {"triton": triton, "fa3": fa3}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--context", type=int, default=1024)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=21)
    parser.add_argument("--seed", type=int, default=20260723)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    sources = source_identity()
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    pool, _ = make_pool(args.context, args.batch_size)
    layer = make_layer()
    req_to_slots = (
        torch.arange(
            1,
            args.batch_size * args.context + 1,
            dtype=torch.int64,
            device="cuda",
        )
        .view(args.batch_size, args.context)
        .contiguous()
    )
    current_slots = req_to_slots[:, -1]
    metadata = make_metadata(
        args.batch_size, args.context, req_to_slots, current_slots
    )
    triton, fa3 = make_backends(pool, metadata)
    q = (
        torch.randn(
            (args.batch_size, 32, 256), dtype=torch.bfloat16, device="cuda"
        )
        / math.sqrt(256)
    ).contiguous()
    k_cache = (
        torch.randn(
            (args.batch_size * args.context, 16, 256),
            dtype=torch.bfloat16,
            device="cuda",
        )
        / math.sqrt(256)
    ).contiguous()
    v_cache = torch.randn_like(k_cache).contiguous()
    pool.set_kv_buffer(
        layer,
        req_to_slots.flatten(),
        k_cache,
        v_cache,
        layer.k_scale,
        layer.v_scale,
        swa_loc=req_to_slots.flatten(),
    )
    k_current = k_cache.view(args.batch_size, args.context, 16, 256)[:, -1]
    v_current = v_cache.view(args.batch_size, args.context, 16, 256)[:, -1]
    forward_batch = SimpleNamespace(
        batch_size=args.batch_size,
        out_cache_loc=current_slots,
        _attn_output=torch.empty_like(q),
        spec_info=None,
    )
    triton_output = TritonAttnBackend.forward_decode(
        triton,
        q,
        k_current,
        v_current,
        layer,
        forward_batch,
        save_kv_cache=False,
    )
    fa3_output = FlashAttentionBackend.forward_decode(
        fa3,
        q,
        k_current,
        v_current,
        layer,
        forward_batch,
        save_kv_cache=False,
    )
    torch.cuda.synchronize()
    atomic(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "scientific_invocation_started": True,
            "updated_unix_s": time.time(),
        },
    )
    delta = fa3_output.float() - triton_output.float()
    relative_l2 = float(
        torch.linalg.vector_norm(delta)
        / torch.linalg.vector_norm(triton_output.float()).clamp_min(1e-12)
    )
    cosine = float(
        torch.nn.functional.cosine_similarity(
            fa3_output.float().flatten(),
            triton_output.float().flatten(),
            dim=0,
        )
    )
    numerical = {
        "all_finite": bool(
            torch.isfinite(fa3_output).all().item()
            and torch.isfinite(triton_output).all().item()
        ),
        "relative_l2": relative_l2,
        "cosine": cosine,
        "max_abs_error": float(delta.abs().max()),
        "mean_abs_error": float(delta.abs().mean()),
        "triton_norm": float(torch.linalg.vector_norm(triton_output.float())),
        "fa3_norm": float(torch.linalg.vector_norm(fa3_output.float())),
        "triton_dtype": str(triton_output.dtype),
        "fa3_dtype": str(fa3_output.dtype),
    }
    numerical_pass = (
        numerical["all_finite"] and relative_l2 <= 0.05 and cosine >= 0.99
    )

    def producer():
        pool.set_kv_buffer(
            layer,
            current_slots,
            k_current,
            v_current,
            layer.k_scale,
            layer.v_scale,
            swa_loc=current_slots,
        )

    def triton_consumer():
        TritonAttnBackend.forward_decode(
            triton,
            q,
            k_current,
            v_current,
            layer,
            forward_batch,
            save_kv_cache=False,
        )

    def fa3_consumer():
        FlashAttentionBackend.forward_decode(
            fa3,
            q,
            k_current,
            v_current,
            layer,
            forward_batch,
            save_kv_cache=False,
        )

    for _ in range(args.warmups):
        producer()
        triton_consumer()
        producer()
        fa3_consumer()
    consumer_samples = {"triton": [], "fa3": []}
    boundary_samples = {"triton": [], "fa3": []}
    for iteration in range(args.iterations):
        order = ["triton", "fa3"]
        if iteration % 2:
            order.reverse()
        for name in order:
            fn = triton_consumer if name == "triton" else fa3_consumer
            consumer_samples[name].append(timed_ms(fn))
            boundary_samples[name].append(timed_ms(lambda fn=fn: (producer(), fn())))
    consumer = {name: distribution(values) for name, values in consumer_samples.items()}
    boundary = {name: distribution(values) for name, values in boundary_samples.items()}
    consumer_reduction = 1 - consumer["fa3"]["median_ms"] / consumer["triton"]["median_ms"]
    boundary_reduction = 1 - boundary["fa3"]["median_ms"] / boundary["triton"]["median_ms"]
    conservative_reduction = min(consumer_reduction, boundary_reduction)
    component_pass = numerical_pass and conservative_reduction > 0
    bound_pass = component_pass and conservative_reduction >= REQUIRED_REDUCTION
    terminal = {
        "schema_version": 1,
        "status": (
            "component_bound_pass"
            if bound_pass
            else "component_insufficient_bound"
            if component_pass
            else "component_numerical_or_performance_negative"
        ),
        "component_pass": component_pass,
        "conditional_endpoint_admitted": bound_pass,
        "geometry": {
            "phase": "decode",
            "batch_size": args.batch_size,
            "context_tokens": args.context,
            "page_size": 1,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "window_tokens": 1024,
            "kv_dtype": "torch.float8_e4m3fn",
            "query_dtype": "torch.bfloat16",
        },
        "producer": {
            "symbol": "SWAKVPool.set_kv_buffer -> MHATokenToKVPool.set_kv_buffer",
            "scale_convention": "unit scale; BF16 K/V converted to E4M3 at store",
            "nonzero_input": True,
            "swa_mapping": "identity project-local exact paged component fixture",
        },
        "consumers": {
            "control": "TritonAttnBackend.forward_decode/decode_attention_fwd",
            "candidate": "FlashAttentionBackend.forward_decode/sgl_kernel.flash_attn_with_kvcache(ver=3)",
        },
        "numerical": numerical,
        "consumer_only": consumer,
        "producer_consumer_boundary": boundary,
        "consumer_reduction_fraction": consumer_reduction,
        "producer_consumer_reduction_fraction": boundary_reduction,
        "conservative_reduction_fraction": conservative_reduction,
        "required_reduction_fraction": REQUIRED_REDUCTION,
        "estimated_whole_request_reduction_fraction": (
            conservative_reduction * LOCAL_WALL_FRACTION
        ),
        "path_proof": {
            "local_backend": "FlashAttentionBackend",
            "global_backend": "TritonAttnBackend",
            "fallback_count": 0,
            "source": sources,
        },
        "device": {
            "name": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
        },
        "identity": {
            "torch": torch.__version__,
            "seed": args.seed,
        },
    }
    atomic(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    state = json.loads(invocation.read_text())
    state["scientific_terminal_recorded"] = True
    state["updated_unix_s"] = time.time()
    atomic(invocation, state)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if component_pass else 2


if __name__ == "__main__":
    from sglang.srt.layers.attention.flashattention_backend import (
        FlashAttentionBackend,
    )
    from sglang.srt.layers.attention.triton_backend import TritonAttnBackend

    raise SystemExit(main())
