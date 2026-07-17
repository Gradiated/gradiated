#!/usr/bin/env python3
"""Matched BF16/FP8-storage MLA component measurement at GLM-4.7 Flash geometry."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

SOURCE = Path("/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_decode_attention.py")
SOURCE_SHA256 = "cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4"
DTYPE_BYTES = {"bf16": 2, "fp8_e4m3fn": 1}


def timing(torch, fn, warmups=30, repetitions=120):
    for _ in range(warmups):
        fn()
    torch.cuda.synchronize()
    values = []
    for _ in range(repetitions):
        start, end = torch.cuda.Event(True), torch.cuda.Event(True)
        start.record(); fn(); end.record()
        end.synchronize()
        values.append(start.elapsed_time(end) * 1000)
    values.sort()
    return {"samples": len(values), "mean_us": statistics.fmean(values),
            "p50_us": values[len(values)//2], "p95_us": values[math.ceil(.95*len(values))-1],
            "min_us": values[0], "max_us": values[-1]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=470147)
    args = parser.parse_args()
    import torch
    import vllm.v1.attention.ops.triton_decode_attention as kernels
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != SOURCE_SHA256:
        raise RuntimeError(f"unexpected vLLM decode source {source_hash}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    torch.manual_seed(args.seed)
    batch, context, heads, rank, rope, value_width, page = 8, 8193, 20, 512, 64, 512, 16
    blocks = batch * math.ceil(context / page)
    query = torch.randn(batch, heads, rank + rope, dtype=torch.bfloat16, device="cuda")
    bf16_cache = torch.randn(blocks, page, 1, rank + rope, dtype=torch.bfloat16, device="cuda")
    block_table = torch.arange(blocks, device="cuda", dtype=torch.int32).reshape(batch, -1)
    lengths = torch.full((batch,), context, dtype=torch.int32, device="cuda")
    scale = value_width ** -0.5
    logits = torch.empty(batch, heads, 4, value_width + 1, dtype=torch.float32, device="cuda")
    output = torch.zeros(batch, heads, value_width, dtype=torch.bfloat16, device="cuda")
    lse = torch.zeros(batch, heads, dtype=torch.bfloat16, device="cuda")
    grid = (batch, math.ceil(heads / 16), 4)

    def mla(cache):
        kernels._fwd_grouped_kernel_stage1[grid](
            query, cache, cache[..., :rank], scale, block_table, lengths, logits,
            block_table.stride(0), query.stride(0), query.stride(1), cache.stride(-3),
            cache.stride(-2), cache.stride(-3), cache.stride(-2), logits.stride(0),
            logits.stride(1), logits.stride(2), kv_group_num=heads, q_head_num=heads,
            BLOCK_DMODEL=rank, BLOCK_DPE=rope, BLOCK_DV=value_width, BLOCK_N=32,
            BLOCK_H=16, NUM_KV_SPLITS=4, PAGE_SIZE=page, logit_cap=0.0,
            num_warps=4, num_stages=2, Lk=rank + rope, Lv=value_width)
        kernels._decode_softmax_reducev_fwd(logits, query, output, lse, cache[..., :rank], lengths, 4)

    fp8_scale = bf16_cache.float().abs().amax() / 448.0
    fp8_cache = (bf16_cache.float() / fp8_scale).to(torch.float8_e4m3fn)
    dequant = torch.empty_like(bf16_cache)
    def fp8_mla():
        dequant.copy_((fp8_cache.float() * fp8_scale).to(torch.bfloat16))
        mla(dequant)
    torch.cuda.synchronize()
    mla(bf16_cache)
    bf16_t = timing(torch, lambda: mla(bf16_cache))
    fp8_t = timing(torch, fp8_mla)
    restored = (fp8_cache.float() * fp8_scale).to(torch.bfloat16)
    error = (restored.float() - bf16_cache.float()).abs()
    result = {
        "schema_version": 1, "seed": args.seed, "shape": {
            "batch": batch, "context_tokens": context, "heads": heads, "kv_lora_rank": rank,
            "rope_head_dim": rope, "value_width": value_width, "page_size": page,
            "blocks": blocks},
        "device": {"name": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability())},
        "source_sha256": source_hash, "quantization": {"format": "float8_e4m3fn", "scale": fp8_scale.item()},
        "storage": {"bf16_bytes": bf16_cache.numel()*2, "fp8_bytes": fp8_cache.numel(),
                    "reduction": 1.0 - fp8_cache.numel()/bf16_cache.numel()/2.0},
        "bf16_attention": bf16_t, "fp8_storage_dequant_attention": fp8_t,
        "time_change": fp8_t["p50_us"]/bf16_t["p50_us"] - 1.0,
        "restore_error": {"max_abs": error.max().item(), "mean_abs": error.mean().item(),
                           "rms": error.square().mean().sqrt().item()},
        "decision": "FP8_STORAGE_COMPONENT_MEASURED_NO_SERVER_INTEGRATION"}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    started = time.time()
    main()
