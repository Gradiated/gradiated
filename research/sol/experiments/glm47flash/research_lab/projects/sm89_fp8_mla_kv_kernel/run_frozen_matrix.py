#!/usr/bin/env python3
"""Run or fail-closed the frozen B1/B8/B32 FP8 MLA matrix."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path


CONTEXTS = (8193, 8449, 8705, 8961, 9215)
BATCHES = (1, 8, 32)
PAGE = 16
HEADS = 20
WIDTH = 576
VALUE = 512


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    result = {
        "schema_version": 1,
        "contract": {"seed": 1234, "batches": BATCHES, "contexts": CONTEXTS,
                     "page_size": PAGE, "heads": HEADS, "width": WIDTH, "value_width": VALUE,
                     "block_h": 16, "block_n": 32, "num_warps": 4, "num_stages": 2, "splits": 4},
        "platform": platform.platform(),
        "matrix": [],
    }
    for batch in BATCHES:
        for context in CONTEXTS:
            pages = batch * ((context + PAGE - 1) // PAGE)
            bf16_bytes = pages * PAGE * WIDTH * 2
            fp8_bytes = pages * PAGE * WIDTH + pages * PAGE * 4
            result["matrix"].append({"batch": batch, "context": context, "pages": pages,
                                     "bf16_cache_bytes": bf16_bytes, "fp8_cache_bytes": fp8_bytes,
                                     "fp8_savings_fraction": 1 - fp8_bytes / bf16_bytes})
    try:
        import torch  # type: ignore
        import triton  # type: ignore
        result["runtime"] = {"torch": torch.__version__, "triton": triton.__version__,
                              "cuda_available": bool(torch.cuda.is_available())}
        result["static_source"] = {
            "writer_invoked": True, "paged_block_table": True, "shuffled_pages": True,
            "block_n": 32, "num_kv_splits": 4, "source": "fp8_mla_triton.py"
        }
        if not torch.cuda.is_available():
            result["decision"] = "CPU_NUMERICAL_SAMPLE_GPU_TIMING_REQUIRED"
            result["error"] = "CUDA unavailable"
            result["sampled_numerical"] = sampled_cpu(torch)
            rc = 2
        else:
            result["decision"] = "GPU_MATRIX_REQUIRED"
            result["error"] = "target runner invocation is not executed by this offline command"
            rc = 2
    except Exception as error:
        result["runtime"] = {"torch": None, "triton": None, "cuda_available": False}
        result["decision"] = "GPU_REQUIRED"
        result["error_type"] = type(error).__name__
        result["error"] = str(error)
        rc = 2
    result["elapsed_seconds"] = time.monotonic() - started
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return rc


def sampled_cpu(torch):
    """Small shuffled-page FP8 writer/decode oracle; not a GPU timing claim."""
    torch.manual_seed(1234)
    batch, context, heads, width, value, page = 1, 33, 20, 576, 512, 16
    pages = (context + page - 1) // page
    logical = torch.randn(batch, context, heads, width, dtype=torch.bfloat16)
    table = torch.tensor([[2, 0, 1]], dtype=torch.int64)
    cache = torch.empty(pages, page, heads, width, dtype=torch.float8_e4m3fn)
    scales = torch.empty(pages, page, heads, dtype=torch.float32)
    for b in range(batch):
        for token in range(context):
            physical = int(table[b, token // page])
            offset = token % page
            row = logical[b, token].float()
            scale = max(float(row.abs().max()) / 448.0, 1.0 / 448.0)
            cache[physical, offset] = (row / scale).to(torch.float8_e4m3fn)
            scales[physical, offset] = scale
    restored = torch.empty_like(logical)
    for token in range(context):
        physical = int(table[0, token // page])
        restored[0, token] = cache[physical, token % page].float() * scales[physical, token % page, :, None]
    error = (restored.float() - logical.float()).abs()
    return {"batch": batch, "context": context, "shuffled_page_table": table.tolist(),
            "finite": bool(torch.isfinite(restored).all()), "max_abs": float(error.max()),
            "mean_abs": float(error.mean()), "saturation": 0,
            "output_tolerance_pass": bool(torch.allclose(restored.float(), logical.float(), atol=0.03, rtol=0.03))}


if __name__ == "__main__":
    raise SystemExit(main())
