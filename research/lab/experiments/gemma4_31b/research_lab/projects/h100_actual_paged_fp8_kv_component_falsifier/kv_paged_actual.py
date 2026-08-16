#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import torch
import vllm
from vllm.model_executor.layers.attention.attention import unified_kv_cache_update
from vllm.v1.attention.ops.triton_unified_attention import unified_attention


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    result = {"schema_version": 1, "stage": args.stage, "pass": False,
              "all_actual_consumers_pass": False, "economic_both_envelopes_falsified": False,
              "sentinel": {"pass": False}, "useful_gpu_seconds": 0.0}
    started = time.perf_counter()
    try:
        torch.manual_seed(args.seed)
        if "H100" not in torch.cuda.get_device_name() or torch.cuda.get_device_properties(0).total_memory < 75 * 1024**3:
            raise RuntimeError("expected one full H100 SXM")
        result["runtime"] = {"vllm": vllm.__version__, "gpu": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "producer_signature": str(inspect.signature(unified_kv_cache_update)),
            "backend_signature": str(inspect.signature(unified_attention)),
            "producer_source_sha256": hashlib.sha256(inspect.getsource(unified_kv_cache_update).encode()).hexdigest(),
            "backend_source_sha256": hashlib.sha256(inspect.getsource(unified_attention).encode()).hexdigest()}
        # This is intentionally the real image producer, not reshape_and_cache or a direct fixture.
        # Context construction must succeed before the selected backend can consume its page table.
        key = torch.linspace(-0.75, 0.75, 8 * 16 * 256, device="cuda", dtype=torch.bfloat16).reshape(8, 16, 256)
        value = torch.linspace(0.5, -0.5, 8 * 16 * 256, device="cuda", dtype=torch.bfloat16).reshape(8, 16, 256)
        begin = torch.cuda.Event(enable_timing=True); end = torch.cuda.Event(enable_timing=True)
        begin.record()
        dependency = unified_kv_cache_update(key, value, "h100-local-sentinel")
        end.record(); end.synchronize()
        result["sentinel"] = {"pass": False, "producer": "unified_kv_cache_update", "backend": "unified_attention",
            "dependency_shape": list(dependency.shape), "elapsed_ms": begin.elapsed_time(end),
            "failure": "producer returned without a constructed local/global Attention context; refusing a direct backend stand-in"}
    except Exception as error:
        result["sentinel"] = {"pass": False, "producer": "unified_kv_cache_update", "backend": "unified_attention",
            "error_type": type(error).__name__, "error": str(error)[:4000],
            "required_geometry": {"local": [8, 32, 16, 256, 1024], "global": [8, 32, 4, 512, 4214]}}
    result["scientific_wall_seconds"] = time.perf_counter() - started
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
