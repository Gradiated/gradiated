#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pathlib
import time

import torch
import torch.nn.functional as F

from sglang.srt.layers.attention.gemma4_attention_endpoint import route_attention


def metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict:
    actual_float = actual.float()
    reference_float = reference.float()
    difference = actual_float - reference_float
    return {
        "finite": bool(torch.isfinite(actual_float).all()),
        "normalized_rmse": float(torch.sqrt(torch.mean(difference * difference)) / torch.sqrt(torch.mean(reference_float * reference_float))),
        "cosine_similarity": float(F.cosine_similarity(actual_float.flatten(), reference_float.flatten(), dim=0)),
    }


def run_case(name: str, context: int, kv_heads: int, head_dim: int, local: bool) -> dict:
    torch.manual_seed(20260718 + context + head_dim)
    query = torch.randn((12, 32, 1, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    key = torch.randn((12, kv_heads, context, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    value = torch.randn((12, kv_heads, context, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    reference = F.scaled_dot_product_attention(
        query,
        key.repeat_interleave(32 // kv_heads, dim=1),
        value.repeat_interleave(32 // kv_heads, dim=1),
        enable_gqa=False,
    )
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.perf_counter()
    output, telemetry = route_attention(query, key, value, local=local)
    torch.cuda.synchronize()
    wall_ms = (time.perf_counter() - started) * 1000
    oracle = metrics(output, reference)
    return {
        "name": name,
        "context": context,
        "kv_heads": kv_heads,
        "head_dim": head_dim,
        "local": local,
        "wall_ms": wall_ms,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "telemetry": telemetry,
        "oracle": oracle,
        "pass": oracle["finite"] and oracle["normalized_rmse"] <= 0.02 and oracle["cosine_similarity"] >= 0.999,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows = [
        run_case("local_decode", 1024, 16, 256, True),
        run_case("global_decode_peak", 4571, 4, 512, False),
    ]
    result = {"schema_version": 1, "kind": "gemma4_attention_endpoint_numerical_oracle", "pass": all(row["pass"] for row in rows), "rows": rows}
    temporary = args.output.with_suffix(".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0 if result["pass"] else 73


if __name__ == "__main__":
    raise SystemExit(main())
