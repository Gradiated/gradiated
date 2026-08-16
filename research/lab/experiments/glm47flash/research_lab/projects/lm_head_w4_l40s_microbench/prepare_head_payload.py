#!/usr/bin/env python3
"""Build the compact exact-head W4 input required by the target-GPU benchmark."""

import argparse
import hashlib
import json
from pathlib import Path

import torch
from safetensors import safe_open


ROWS = 154880
COLS = 2048
GROUP = 32
MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=MODEL)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    index = json.loads((args.model_dir / "model.safetensors.index.json").read_text())
    shard = args.model_dir / index["weight_map"]["lm_head.weight"]
    packed = torch.empty((COLS // 8, ROWS), dtype=torch.int32)
    scales = torch.empty((COLS // GROUP, ROWS), dtype=torch.bfloat16)
    source_sq = error_sq = 0.0
    with safe_open(str(shard), framework="pt", device="cpu") as reader:
        view = reader.get_slice("lm_head.weight")
        for begin in range(0, ROWS, 256):
            end = min(begin + 256, ROWS)
            weight = view[begin:end, :].to(torch.float32)
            scale = weight.reshape(end - begin, COLS // GROUP, GROUP).abs().amax(-1) / 7
            scale = torch.where(scale == 0, torch.ones_like(scale), scale).to(torch.bfloat16)
            quant = torch.round(weight.reshape(end - begin, COLS // GROUP, GROUP) / scale.float().unsqueeze(-1)).clamp(-8, 7).to(torch.int32).reshape(end - begin, COLS)
            decoded = quant.float() * scale.float().repeat_interleave(GROUP, dim=1)
            source_sq += float(weight.square().sum())
            error_sq += float((decoded - weight).square().sum())
            unsigned = (quant + 8).t().contiguous()
            packed[:, begin:end] = sum(unsigned[i::8] << (4 * i) for i in range(8))
            scales[:, begin:end] = scale.t()
    qweight = args.output_dir / "lm_head_qweight.pt"
    scale_path = args.output_dir / "lm_head_scales.pt"
    torch.save(packed, qweight)
    torch.save(scales, scale_path)
    manifest = {
        "source_head_sha256": "9cf128f300306127d2eae6c5dffaf03840a83923b14c853dd3507c2d3bba5eb0",
        "shape": [ROWS, COLS], "group_size": GROUP, "quantization": "symmetric_int4_group32_unsigned_bias8",
        "qweight": {"file": qweight.name, "sha256": digest(qweight), "bytes": qweight.stat().st_size, "shape": list(packed.shape)},
        "scales": {"file": scale_path.name, "sha256": digest(scale_path), "bytes": scale_path.stat().st_size, "shape": list(scales.shape)},
        "relative_l2": (error_sq / source_sq) ** 0.5,
    }
    (args.output_dir / "payload-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
