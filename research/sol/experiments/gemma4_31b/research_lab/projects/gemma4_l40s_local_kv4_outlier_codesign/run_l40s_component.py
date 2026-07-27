#!/usr/bin/env python3
"""Checkpoint-free later SM89 component; deliberately not invoked offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
import time

import torch

from sglang_local_kv4_outlier import load_extension


COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
TRITON_BACKEND_SHA256 = "e2b0fd4a3ec3c783ae7026f4cb8a7292c1203388a6c9ea5b90e604d3a149f3dc"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-source", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    observed_commit = subprocess.run(
        ["git", "-C", str(args.sglang_source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    backend = (
        args.sglang_source
        / "python/sglang/srt/layers/attention/triton_backend.py"
    )
    if observed_commit != COMMIT or sha256(backend) != TRITON_BACKEND_SHA256:
        raise RuntimeError("selected current-runtime identity mismatch")
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (8, 9):
        raise RuntimeError("typed_hardware_boundary: exact NVIDIA SM89 required")

    extension = load_extension()
    device = "cuda"
    batch, query_heads, kv_heads, dim, tokens = 32, 32, 16, 256, 1024
    slots = batch * tokens
    cache_k = torch.empty((slots, kv_heads, 144), dtype=torch.uint8, device=device)
    cache_v = torch.empty_like(cache_k)
    generator = torch.Generator(device=device).manual_seed(20260727)
    for start in range(0, slots, 64):
        count = min(64, slots - start)
        loc = torch.arange(start, start + count, dtype=torch.int64, device=device)
        k = torch.randn(
            (count, kv_heads, dim),
            dtype=torch.bfloat16,
            device=device,
            generator=generator,
        )
        v = torch.randn(
            (count, kv_heads, dim),
            dtype=torch.bfloat16,
            device=device,
            generator=generator,
        )
        extension.pack(k, loc, cache_k)
        extension.pack(v, loc, cache_v)
    q = torch.randn(
        (batch, query_heads, dim),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    qo_indptr = torch.arange(batch + 1, dtype=torch.int32, device=device)
    kv_indptr = torch.arange(
        0, slots + 1, tokens, dtype=torch.int32, device=device
    )
    kv_indices = torch.arange(slots, dtype=torch.int64, device=device)
    (args.artifact_root / "science_started").write_text(
        json.dumps({"epoch": time.time(), "operation": "corrected_fused_consumer"})
        + "\n"
    )
    output = extension.paged_attention(
        q,
        cache_k,
        cache_v,
        qo_indptr,
        kv_indptr,
        kv_indices,
        1024,
        1,
        1.0 / math.sqrt(dim),
        True,
    )
    torch.cuda.synchronize()
    terminal = {
        "schema_version": 1,
        "classification": "component_smoke_only",
        "runtime_commit": observed_commit,
        "sm": list(torch.cuda.get_device_capability()),
        "shape": [batch, query_heads, tokens, dim],
        "finite": bool(torch.isfinite(output).all().item()),
        "output_l1": float(output.float().abs().sum().item()),
        "warning": "This smoke consumes the real custom consumer but is not an E5M2 timing comparison.",
    }
    (args.artifact_root / "COMPONENT_TERMINAL.json").write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n"
    )
    return 0 if terminal["finite"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
