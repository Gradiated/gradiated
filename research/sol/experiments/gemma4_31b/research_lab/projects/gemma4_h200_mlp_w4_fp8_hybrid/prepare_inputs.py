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
W4_KEYS = (
    "model.language_model.layers.0.mlp.gate_proj.qweight",
    "model.language_model.layers.0.mlp.gate_proj.qzeros",
    "model.language_model.layers.0.mlp.gate_proj.scales",
    "model.language_model.layers.0.mlp.up_proj.qweight",
    "model.language_model.layers.0.mlp.up_proj.qzeros",
    "model.language_model.layers.0.mlp.up_proj.scales",
    "model.language_model.layers.0.mlp.down_proj.qweight",
    "model.language_model.layers.0.mlp.down_proj.qzeros",
    "model.language_model.layers.0.mlp.down_proj.scales",
)


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


def immutable_copy(source: pathlib.Path, destination: pathlib.Path) -> None:
    if destination.is_file() and destination.stat().st_size == source.stat().st_size:
        if sha256(destination) == sha256(source):
            destination.chmod(0o444)
            return
    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    shutil.copyfile(source, temporary)
    if sha256(temporary) != sha256(source):
        raise RuntimeError(f"copy_hash_mismatch:{source.name}")
    temporary.chmod(0o444)
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--w4-source", type=pathlib.Path, required=True)
    args = parser.parse_args()
    source = args.w4_source.resolve()
    snapshot = PROJECT / "inputs" / "w4_checkpoint"
    snapshot.mkdir(parents=True, exist_ok=True)
    admitted = (
        "model-00001-of-00002.safetensors",
        "model-00002-of-00002.safetensors",
        "model.safetensors.index.json",
        "config.json",
        "quant_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "processor_config.json",
        "model-files.sha256",
    )
    for name in admitted:
        immutable_copy(source / name, snapshot / name)

    index = json.loads((snapshot / "model.safetensors.index.json").read_text())
    tensors = {}
    tensor_metadata = {}
    opened = {}
    try:
        for key in W4_KEYS:
            shard_name = index["weight_map"][key]
            handle = opened.setdefault(
                shard_name,
                safe_open(str(snapshot / shard_name), framework="pt", device="cpu"),
            )
            tensor = handle.get_tensor(key).contiguous()
            tensors[key] = tensor
            tensor_metadata[key] = {
                "dtype": str(tensor.dtype),
                "shape": list(tensor.shape),
                "source_shard": shard_name,
            }
    finally:
        opened.clear()
    component = PROJECT / "inputs" / "layer0_mlp_awq.safetensors"
    temporary = component.with_suffix(".safetensors.part")
    save_file(tensors, temporary)
    os.replace(temporary, component)
    component.chmod(0o444)

    rows = []
    for path in sorted(snapshot.iterdir()):
        if path.is_file():
            rows.append(
                {
                    "path": str(path.relative_to(PROJECT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    programs = []
    for name in (
        "hybrid_component.py",
        "remote_hybrid.sh",
        "run_bench_owner.py",
        "MIXED_W4_FP8_BINDING.json",
    ):
        path = PROJECT / name
        programs.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "pass": True,
        "representation": {
            "format": "AWQ W4",
            "bits": 4,
            "group_size": 128,
            "zero_point": True,
            "component_snapshot": {
                "path": str(component.relative_to(PROJECT)),
                "bytes": component.stat().st_size,
                "sha256": sha256(component),
                "tensors": tensor_metadata,
            },
            "checkpoint": rows,
        },
        "programs": programs,
        "physical_hypothesis": {
            "change": "Replace only decode MLP gate/up and down FP8 GEMMs with SGLang AWQ-Marlin W4A16.",
            "prediction": "At M=32, packed weights plus scales/zero-points reduce compulsory MLP weight bytes by more than 35%, reducing DRAM bytes and warm projection time without adding a projection launch.",
            "falsifier": "Incorrect complete MLP outputs, absent AWQ-Marlin symbols, or a call-weighted whole-request bound below 3%.",
        },
    }
    atomic(PROJECT / "GPU_INPUT_MANIFEST.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
