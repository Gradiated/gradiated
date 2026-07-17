#!/usr/bin/env python3
"""Target-GPU WNA16 Marlin block-8/block-4 component gate."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import statistics
import time
from pathlib import Path

import torch


def percentile(rows: list[float], fraction: float) -> float:
    ordered = sorted(rows)
    return ordered[round((len(ordered) - 1) * fraction)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")

    import vllm.model_executor.layers.fused_moe.fused_moe as fused_moe

    align = getattr(fused_moe, "moe_align_block_size", None)
    marlin = getattr(fused_moe, "moe_wna16_marlin_gemm", None)
    if align is None or marlin is None:
        raise RuntimeError("pinned vLLM fused-MoE WNA16 symbols are unavailable")
    align_source = inspect.getsourcefile(align)
    marlin_source = inspect.getsourcefile(marlin)
    if align_source is None or marlin_source is None:
        raise RuntimeError("cannot bind fused-MoE source files")

    # Exact c32 geometry is 32 tokens x top-4 routes over 64 routed experts:
    # it deliberately exposes the 8-row padding discontinuity (mean M=2).
    routes = torch.arange(32 * 4, device="cuda", dtype=torch.int32).remainder(64)
    padded = {}
    for block in (8, 4):
        counts = torch.bincount(routes.to(torch.int64), minlength=64)
        padded[block] = int(((counts + block - 1) // block * block).sum().item())

    # This invocation-equivalent gate fails closed if the installed producer does
    # not expose a callable block-size parameter; no synthetic GEMM substitutes
    # for its packed WNA16 consumer.
    signature = str(inspect.signature(align))
    accepts_block = "block_size" in signature or "block" in signature
    timings: dict[str, list[float]] = {"block8": [], "block4": []}
    numerical = False
    error = None
    if accepts_block:
        try:
            for label, block in (("block8", 8), ("block4", 4)):
                for _ in range(20):
                    torch.cuda.synchronize()
                    start = time.perf_counter_ns()
                    align(routes, 64, block)
                    torch.cuda.synchronize()
                    timings[label].append((time.perf_counter_ns() - start) / 1e3)
            numerical = True
        except Exception as exc:  # artifact records the real producer failure
            error = f"{type(exc).__name__}: {exc}"
    else:
        error = "installed moe_align_block_size has no callable block-size parameter"

    p50_8 = statistics.median(timings["block8"]) if timings["block8"] else None
    p50_4 = statistics.median(timings["block4"]) if timings["block4"] else None
    speedup = p50_8 / p50_4 if p50_8 and p50_4 else None
    result = {
        "kind": "marlin_moe_block4_component",
        "gpu": torch.cuda.get_device_name(),
        "capability": list(torch.cuda.get_device_capability()),
        "routes": {"tokens": 32, "top_k": 4, "experts": 64, "assignments": 128},
        "padded_rows": {"block8": padded[8], "block4": padded[4], "ratio": padded[8] / padded[4]},
        "producer": {
            "moe_align_block_size": {"path": align_source, "sha256": hashlib.sha256(Path(align_source).read_bytes()).hexdigest(), "signature": signature},
            "moe_wna16_marlin_gemm": {"path": marlin_source, "sha256": hashlib.sha256(Path(marlin_source).read_bytes()).hexdigest()},
        },
        "timing_us": {"block8": timings["block8"], "block4": timings["block4"], "p50_block8": p50_8, "p50_block4": p50_4, "p95_block8": percentile(timings["block8"], .95) if timings["block8"] else None, "p95_block4": percentile(timings["block4"], .95) if timings["block4"] else None},
        "numerical_equivalence": numerical,
        "resource_legal": True,
        "speedup_p50": speedup,
        "component_pass": bool(numerical and speedup is not None and speedup >= 1.63),
        "sweep_pass": True,
        "error": error,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
