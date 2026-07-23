#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def link(source: pathlib.Path, destination: pathlib.Path) -> None:
    if destination.exists():
        destination.unlink()
    os.link(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=pathlib.Path, required=True)
    parser.add_argument("--w4", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    current_index = json.loads(
        (args.current / "model.safetensors.index.json").read_text()
    )
    w4_index = json.loads((args.w4 / "model.safetensors.index.json").read_text())
    weight_map = {
        key: value
        for key, value in current_index["weight_map"].items()
        if not (
            ".mlp.gate_proj.weight" in key
            or ".mlp.up_proj.weight" in key
            or ".mlp.down_proj.weight" in key
        )
    }
    mlp_w4 = {
        key: f"w4-{value}"
        for key, value in w4_index["weight_map"].items()
        if ".mlp." in key
        and (
            key.endswith(".qweight")
            or key.endswith(".qzeros")
            or key.endswith(".scales")
        )
    }
    weight_map.update(mlp_w4)
    for path in args.current.iterdir():
        if path.is_file() and path.name != "model.safetensors.index.json":
            link(path, args.output / path.name)
    for name in sorted(set(w4_index["weight_map"].values())):
        link(args.w4 / name, args.output / f"w4-{name}")
    config = json.loads((args.current / "config.json").read_text())
    config["quantization_config"] = {
        "quant_method": "awq",
        "bits": 4,
        "group_size": 128,
        "zero_point": True,
        "version": "gemm",
        "modules_to_not_convert": [
            "model.language_model.embed_tokens",
            "lm_head",
            "model.embed_vision",
        ],
    }
    atomic(args.output / "config.json", config)
    quant = {
        "quant_method": "awq",
        "bits": 4,
        "group_size": 128,
        "zero_point": True,
        "version": "gemm",
        "modules_to_not_convert": config["quantization_config"][
            "modules_to_not_convert"
        ],
    }
    atomic(args.output / "quantize_config.json", quant)
    atomic(args.output / "quant_config.json", quant)
    atomic(
        args.output / "model.safetensors.index.json",
        {"metadata": current_index.get("metadata", {}), "weight_map": weight_map},
    )
    terminal = {
        "schema_version": 1,
        "pass": (
            len(mlp_w4) == 60 * 3 * 3
            and not any(
                key.endswith(".weight") and ".mlp." in key for key in weight_map
            )
        ),
        "current_entries": len(current_index["weight_map"]),
        "hybrid_entries": len(weight_map),
        "w4_mlp_entries": len(mlp_w4),
        "expected_w4_mlp_entries": 60 * 3 * 3,
    }
    atomic(args.output / "HYBRID_CHECKPOINT_TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
