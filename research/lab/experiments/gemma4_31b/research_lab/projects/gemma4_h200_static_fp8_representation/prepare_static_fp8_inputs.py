#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file


WEIGHT_KEY = "model.language_model.layers.0.mlp.down_proj.weight"
WEIGHT_SHAPE = (5376, 21504)
SOURCE_SHARD_SHA256 = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
FP8_MAX = 448.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def materialize(source_shard: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    bf16_path = output_dir / "layer0_down_proj_bf16.safetensors"
    representation_path = output_dir / "layer0_down_proj_static_fp8.safetensors"

    with safe_open(str(source_shard), framework="pt", device="cpu") as source:
        raw = source.get_tensor(WEIGHT_KEY)
    if raw.dtype != torch.bfloat16 or tuple(raw.shape) != WEIGHT_SHAPE:
        raise RuntimeError(f"exact weight mismatch: {raw.dtype} {tuple(raw.shape)}")

    save_file({"weight": raw.contiguous()}, bf16_path)
    weight_scale = (raw.float().abs().amax(dim=1) / FP8_MAX).clamp_min(1e-8)
    fp8_weight = torch.empty(WEIGHT_SHAPE, dtype=torch.float8_e4m3fn)
    for start in range(0, WEIGHT_SHAPE[0], 32):
        stop = min(start + 32, WEIGHT_SHAPE[0])
        fp8_weight[start:stop] = (
            raw[start:stop].float() / weight_scale[start:stop, None]
        ).to(torch.float8_e4m3fn)

    generator = torch.Generator(device="cpu").manual_seed(2026072201)
    calibration = torch.empty((256, WEIGHT_SHAPE[1]), dtype=torch.float32)
    calibration.normal_(mean=0.0, std=0.7, generator=generator)
    calibration_absmax = calibration.abs().amax()
    activation_scale = (calibration_absmax * 1.05 / FP8_MAX).clamp_min(1e-8).reshape(1)
    save_file(
        {
            "weight": fp8_weight.contiguous(),
            "weight_scale": weight_scale.contiguous(),
            "activation_scale": activation_scale.contiguous(),
        },
        representation_path,
    )

    rows = []
    for path, role in (
        (bf16_path, "exact BF16 reference tensor"),
        (representation_path, "serialized static FP8 producer artifact"),
    ):
        rows.append(
            {
                "path": str(path.relative_to(output_dir.parent)),
                "remote_name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "role": role,
            }
        )
    producer = {
        "schema_version": 1,
        "producer": "prepare_static_fp8_inputs.py",
        "source": {
            "checkpoint_key": WEIGHT_KEY,
            "checkpoint_shard_name": source_shard.name,
            "checkpoint_shard_sha256": SOURCE_SHARD_SHA256,
            "dtype": str(raw.dtype),
            "shape": list(raw.shape),
        },
        "representation": {
            "weight_dtype": str(fp8_weight.dtype),
            "weight_scale_granularity": "per_output_channel",
            "activation_dtype": str(fp8_weight.dtype),
            "activation_scale_granularity": "static_per_tensor",
            "activation_calibration_seed": 2026072201,
            "activation_calibration_tokens": 256,
            "activation_calibration_distribution": "synthetic_normal_mean_0_std_0.7",
            "activation_calibration_absmax": calibration_absmax.item(),
            "activation_scale_headroom": 1.05,
            "activation_scale": activation_scale.item(),
        },
        "files": rows,
    }
    atomic_json(output_dir.parent / "PRODUCER_MANIFEST.json", producer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-shard", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.source_shard.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
