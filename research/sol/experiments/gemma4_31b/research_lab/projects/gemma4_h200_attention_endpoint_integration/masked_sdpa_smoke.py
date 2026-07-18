#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import json
import pathlib

import torch
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel


def run(name: str, context: int, kv_heads: int, head_dim: int, backend: SDPBackend, repeat: bool) -> dict:
    torch.manual_seed(20260718 + context)
    query = torch.randn((1, 32, 1, head_dim), device="cuda", dtype=torch.bfloat16)
    key = torch.randn((1, kv_heads, context, head_dim), device="cuda", dtype=torch.bfloat16)
    value = torch.randn_like(key)
    mask = None if not repeat else torch.ones((1, 1, 1, context), device="cuda", dtype=torch.bool)
    if repeat:
        key = key.repeat_interleave(32 // kv_heads, dim=1)
        value = value.repeat_interleave(32 // kv_heads, dim=1)
    caught = None
    operators = []
    try:
        with sdpa_kernel(backend), torch.profiler.profile(
            activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]
        ) as profile:
            output = F.scaled_dot_product_attention(query, key, value, attn_mask=mask, enable_gqa=not repeat, scale=1.0)
            torch.cuda.synchronize()
        operators = sorted(event.key for event in profile.key_averages() if "attention" in event.key)
    except Exception as exc:
        caught = f"{type(exc).__name__}: {exc}"
        output = None
    return {
        "name": name,
        "pass": output is not None and bool(torch.isfinite(output).all()),
        "error": caught,
        "operators": operators,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
    }


def main() -> None:
    output = pathlib.Path("/work/masked-sdpa-smoke.json")
    rows = [
        run("local", 1024, 16, 256, SDPBackend.FLASH_ATTENTION, False),
        run("global", 4571, 4, 512, SDPBackend.EFFICIENT_ATTENTION, True),
    ]
    output.write_text(json.dumps({"pass": all(row["pass"] for row in rows), "rows": rows}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
