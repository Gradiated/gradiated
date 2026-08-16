#!/usr/bin/env python3
"""Exercise training and inference at the exact production shapes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from causal_parallel_offset_head import (
    HeadConfig,
    batched_tied_logits,
    build_torch_module,
    parameter_count,
    prefix_weighted_loss,
    service_bytes,
    service_flops,
)


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--device", default="meta")
    args = parser.parse_args()
    import torch

    config = HeadConfig()
    module = build_torch_module(config).to(device=args.device, dtype=torch.bfloat16)
    actual_parameter_count = sum(parameter.numel() for parameter in module.parameters())
    taps = [
        torch.empty(
            (32, config.hidden_size), device=args.device, dtype=torch.bfloat16
        )
        for _ in config.tap_layers
    ]
    offset_hidden = module(taps)
    tied_weight = torch.empty(
        (config.vocab_size, config.hidden_size),
        device=args.device,
        dtype=torch.bfloat16,
    )
    logits = batched_tied_logits(offset_hidden, tied_weight, config.softcap)
    targets = torch.zeros(
        (32, config.depth), device=args.device, dtype=torch.int64
    )
    weights = torch.ones(config.depth, device=args.device, dtype=torch.float32)
    loss = prefix_weighted_loss(logits, targets, weights)
    result = {
        "schema_version": 1,
        "classification": "exact_shape_training_and_inference_fixture",
        "pass": (
            tuple(offset_hidden.shape) == (32, 16, 5376)
            and tuple(logits.shape) == (32, 16, 262144)
            and tuple(loss.shape) == ()
            and actual_parameter_count == parameter_count(config)
        ),
        "device": args.device,
        "torch": torch.__version__,
        "geometry": {
            "tap_shapes": [list(tap.shape) for tap in taps],
            "tap_dtype": str(taps[0].dtype),
            "offset_hidden_shape": list(offset_hidden.shape),
            "offset_hidden_dtype": str(offset_hidden.dtype),
            "tied_weight_shape": list(tied_weight.shape),
            "tied_weight_dtype": str(tied_weight.dtype),
            "logits_shape": list(logits.shape),
            "logits_dtype": str(logits.dtype),
            "row_order": "request_major_offset_minor",
        },
        "parameter_count": parameter_count(config),
        "actual_module_parameter_count": actual_parameter_count,
        "service_flops_c32_d16": service_flops(config, 32),
        "service_bytes_c32_d16": service_bytes(config, 32),
        "source_sha256": sha256(pathlib.Path(__file__).with_name(
            "causal_parallel_offset_head.py"
        )),
        "evidence_label": (
            "executed PyTorch operator graph on meta tensors; exact allocation, "
            "CUDA execution, numerics, and timing remain unclaimed"
        ),
    }
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
