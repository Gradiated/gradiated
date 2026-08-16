#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import torch
from safetensors import safe_open


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads((args.export / "config.json").read_text())
    quantization = config.get("quantization_config") or {}
    quant_algo = str(quantization.get("quant_algo", ""))
    shards = sorted(args.export.glob("*.safetensors"))
    dtype_counts: Counter[str] = Counter()
    scale_tensors = 0
    sampled_fp8 = []
    scale_failures = []
    tensor_count = 0

    for shard in shards:
        with safe_open(shard, framework="pt", device="cpu") as handle:
            for key in handle.keys():
                tensor_count += 1
                view = handle.get_slice(key)
                dtype = str(view.get_dtype())
                dtype_counts[dtype] += 1
                if "scale" in key.lower():
                    tensor = handle.get_tensor(key).float()
                    scale_tensors += 1
                    if tensor.numel() == 0 or not torch.isfinite(tensor).all() or not (tensor > 0).all():
                        scale_failures.append(key)
                elif "F8" in dtype and len(sampled_fp8) < 8:
                    shape = tuple(int(x) for x in view.get_shape())
                    if math.prod(shape) <= 64_000_000:
                        tensor = handle.get_tensor(key).flatten()
                        stride = max(1, tensor.numel() // 4096)
                        sample = tensor[::stride][:4096].float()
                        sampled_fp8.append(
                            {
                                "key": key,
                                "shape": shape,
                                "finite": bool(torch.isfinite(sample).all()),
                                "sample_abs_max": float(sample.abs().max()) if sample.numel() else None,
                            }
                        )

    passed = bool(
        shards
        and "FP8" in quant_algo
        and sum(count for dtype, count in dtype_counts.items() if "F8" in dtype) > 0
        and scale_tensors > 0
        and not scale_failures
        and sampled_fp8
        and all(row["finite"] for row in sampled_fp8)
    )
    result = {
        "schema_version": 1,
        "pass": passed,
        "quant_algo": quant_algo,
        "quantization_config": quantization,
        "shard_count": len(shards),
        "tensor_count": tensor_count,
        "dtype_counts": dict(sorted(dtype_counts.items())),
        "scale_tensor_count": scale_tensors,
        "scale_failures": scale_failures,
        "sampled_fp8_tensors": sampled_fp8,
        "policy": "all scale tensors finite and positive; up to eight <=64M-element FP8 tensors sampled at <=4096 values each",
    }
    atomic_json(args.output, result)
    return 0 if passed else 41


if __name__ == "__main__":
    raise SystemExit(main())
