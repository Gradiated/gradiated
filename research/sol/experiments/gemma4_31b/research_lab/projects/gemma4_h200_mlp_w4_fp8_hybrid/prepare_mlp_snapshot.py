#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil

from safetensors import safe_open
from safetensors.torch import save_file


PROJECT = pathlib.Path(__file__).resolve().parent


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    index = json.loads((args.source / "model.safetensors.index.json").read_text())
    selected = {
        key: shard
        for key, shard in index["weight_map"].items()
        if ".mlp." in key
        and (
            key.endswith(".qweight")
            or key.endswith(".qzeros")
            or key.endswith(".scales")
        )
    }
    if len(selected) != 60 * 3 * 3:
        raise RuntimeError(f"unexpected_mlp_tensor_count:{len(selected)}")
    tensors = {}
    for shard_name in sorted(set(selected.values())):
        keys = [key for key, shard in selected.items() if shard == shard_name]
        with safe_open(
            str(args.source / shard_name), framework="pt", device="cpu"
        ) as handle:
            for key in keys:
                tensors[key] = handle.get_tensor(key).contiguous()
    shard = args.output / "mlp-awq.safetensors"
    save_file(tensors, shard)
    shard.chmod(0o444)
    for name in ("config.json", "quant_config.json"):
        shutil.copyfile(args.source / name, args.output / name)
        (args.output / name).chmod(0o444)
    atomic(
        args.output / "model.safetensors.index.json",
        {
            "metadata": {"format": "pt"},
            "weight_map": {key: shard.name for key in sorted(selected)},
        },
    )
    (args.output / "model.safetensors.index.json").chmod(0o444)
    terminal = {
        "schema_version": 1,
        "pass": True,
        "tensor_count": len(tensors),
        "bytes": shard.stat().st_size,
        "sha256": sha256(shard),
    }
    atomic(args.output / "MLP_SNAPSHOT_TERMINAL.json", terminal)
    (args.output / "MLP_SNAPSHOT_TERMINAL.json").chmod(0o444)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
