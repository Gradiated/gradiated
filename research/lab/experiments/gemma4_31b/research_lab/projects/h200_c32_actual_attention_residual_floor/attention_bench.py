#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

import torch
from vllm.vllm_flash_attn.flash_attn_interface import flash_attn_varlen_func
from vllm.v1.attention.ops.triton_unified_attention import unified_attention

BATCH = 32
STRICT = 0.47201182295214134
LENIENT = 0.47751364375858635
LINEARS_HEAD = 0.22476958992984145


def atomic(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def percentile(values, p):
    values = sorted(values)
    return values[int((len(values) - 1) * p)]


def call(q, k, v, cuq, cuk, context, window):
    return flash_attn_varlen_func(q, k, v, 1, cuq, context, cuk, causal=True,
                                  window_size=window, fa_version=3)


def measure(name, heads_q, heads_kv, dim, context, window):
    if name == "global":
        block = 16; blocks_per = (context + block - 1) // block
        q = torch.randn((BATCH, heads_q, dim), device="cuda", dtype=torch.bfloat16)
        k = torch.zeros((BATCH * blocks_per, block, heads_kv, dim), device="cuda", dtype=torch.bfloat16)
        v = k
        out = torch.empty_like(q); cuq = torch.arange(0, BATCH + 1, device="cuda", dtype=torch.int32)
        lengths = torch.full((BATCH,), context, device="cuda", dtype=torch.int32)
        table = torch.arange(BATCH * blocks_per, device="cuda", dtype=torch.int32).reshape(BATCH, blocks_per)
        scale = dim ** -0.5; descale = torch.ones((BATCH, heads_kv), device="cuda", dtype=torch.float32)
        def run():
            unified_attention(q, k, v, out, cuq, 1, lengths, context, scale, True, -1, table, 0.0,
                              None, descale, descale)
            return out
    else:
        q = torch.randn((BATCH, heads_q, dim), device="cuda", dtype=torch.bfloat16)
        k = torch.zeros((BATCH * context, heads_kv, dim), device="cuda", dtype=torch.bfloat16)
        v = torch.zeros_like(k)
        cuq = torch.arange(0, BATCH + 1, device="cuda", dtype=torch.int32)
        cuk = torch.arange(0, (BATCH + 1) * context, context, device="cuda", dtype=torch.int32)
        def run(): return call(q, k, v, cuq, cuk, context, window)
    for _ in range(3):
        warm = run()
        if not bool(torch.isfinite(warm).all()):
            raise RuntimeError("warmup output is nonfinite")
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    cuda, wall, checksum = [], [], 0.0
    for _ in range(8):
        start, end = torch.cuda.Event(True), torch.cuda.Event(True)
        torch.cuda.synchronize(); begun = time.perf_counter(); start.record()
        out = run()
        end.record(); end.synchronize()
        cuda.append(start.elapsed_time(end)); wall.append((time.perf_counter() - begun) * 1000)
        if not bool(torch.isfinite(out).all()):
            raise RuntimeError("timed output is nonfinite")
        checksum += float(out.float().sum())
    return {"regime": name, "context": context, "q_heads": heads_q, "kv_heads": heads_kv,
            "head_dim": dim, "window": list(window), "k_equals_v": name == "global",
            "cuda_ms": {"raw": cuda, "p50": statistics.median(cuda), "p95": percentile(cuda, .95)},
            "wall_ms": {"raw": wall, "p50": statistics.median(wall), "p95": percentile(wall, .95)},
            "finite_consumed_checksum": checksum, "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(), "pass": True}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--stage", required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--seed", type=int, required=True); args = parser.parse_args()
    started = time.perf_counter(); result = {"schema_version": 1, "stage": args.stage, "pass": False,
      "all_actual_consumers_pass": False, "economic_both_envelopes_falsified": False, "rows": [],
      "consumer": "pinned vLLM FlashAttention varlen (sliding) plus pinned vLLM Triton unified_attention (global head_dim=512)",
      "geometry": {"batch": BATCH, "sliding": [32,16,256,1024], "global": [32,4,512,[4214,4571]]}}
    try:
        torch.manual_seed(args.seed); torch.cuda.manual_seed_all(args.seed)
        prop = torch.cuda.get_device_properties(0)
        if "H200" not in torch.cuda.get_device_name() or prop.total_memory < 130 * 1024**3: raise RuntimeError("expected full H200")
        import vllm.vllm_flash_attn.flash_attn_interface as fa
        result["runtime"] = {"gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability()),
          "torch": torch.__version__, "cuda": torch.version.cuda, "vllm": __import__('vllm').__version__,
          "module_file": fa.__file__, "module_sha256": hashlib.sha256(Path(fa.__file__).read_bytes()).hexdigest(),
          "symbol": flash_attn_varlen_func.__qualname__}
        result["rows"].append(measure("sliding", 32, 16, 256, 1024, (1023, 0)))
        for context in range(4214, 4572): result["rows"].append(measure("global", 32, 4, 512, context, (-1, -1)))
        sliding = result["rows"][0]["cuda_ms"]["p50"]
        globals_ms = sum(row["cuda_ms"]["p50"] for row in result["rows"][1:])
        attention = (50 * sliding + 10 * globals_ms) * 358 / BATCH / 1000
        total = LINEARS_HEAD + attention
        result.update({"attention_seconds_per_request": attention, "combined_seconds_per_request": total,
          "combined_exceeds_strict": total > STRICT, "combined_exceeds_lenient": total > LENIENT,
          "all_actual_consumers_pass": len(result["rows"]) == 359 and all(r["pass"] for r in result["rows"]), "pass": True})
    except Exception as error: result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
    result["benchmark_wall_seconds"] = time.perf_counter() - started; result["useful_gpu_seconds"] = sum(sum(r.get("wall_ms",{}).get("raw",[])) for r in result["rows"])/1000
    atomic(args.output, result); return 0 if result["pass"] else 1

if __name__ == "__main__": raise SystemExit(main())
