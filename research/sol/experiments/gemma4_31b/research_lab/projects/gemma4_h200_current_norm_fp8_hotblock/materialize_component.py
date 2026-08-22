#!/usr/bin/env python3
"""Materialize and verify the four tensors bound for the offline component."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from safetensors import safe_open
from safetensors.torch import save_file


PROJECT = Path(__file__).resolve().parent
CHECKPOINT = Path(
    "/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/"
    "gemma4_h200_ngram_decode_equivalent_verifier/inputs/checkpoint"
)
INDEX = CHECKPOINT / "model.safetensors.index.json"
MANIFEST = Path(
    "/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/"
    "gemma4_c32_graph_gap_elision/inputs/packet/inputs/bound/CHECKPOINT_MANIFEST.json"
)
SHARD = CHECKPOINT / "model-00001-of-00002.safetensors"
OUTPUT = PROJECT / "inputs/gemma4-layer0-norm-qkv-component.safetensors"

KEYS = {
    "model.language_model.layers.0.input_layernorm.weight": "input_layernorm",
    "model.language_model.layers.0.self_attn.q_proj.weight": "q_proj",
    "model.language_model.layers.0.self_attn.k_proj.weight": "k_proj",
    "model.language_model.layers.0.self_attn.v_proj.weight": "v_proj",
}
EXPECTED_SHARD_SHA256 = (
    "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
)
EXPECTED_MANIFEST_SHA256 = (
    "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tensor_bytes(tensor) -> bytes:
    # NumPy does not understand bfloat16, so reinterpret its exact two-byte
    # representation as uint16 before obtaining bytes for the value hash.
    return tensor.detach().contiguous().view(__import__("torch").uint16).numpy().tobytes()


def tensor_record(tensor, source_shard: str) -> dict[str, object]:
    return {
        "dtype": str(tensor.dtype).removeprefix("torch."),
        "shape": list(tensor.shape),
        "stride": list(tensor.stride()),
        "numel": tensor.numel(),
        "bytes": tensor.numel() * tensor.element_size(),
        "source_shard": source_shard,
        "value_sha256": hashlib.sha256(tensor_bytes(tensor)).hexdigest(),
    }


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to replace existing finalized output: {OUTPUT}")
    if sha256_file(MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("checkpoint manifest identity mismatch")
    if sha256_file(INDEX) != "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2":
        raise RuntimeError("checkpoint index identity mismatch")
    if SHARD.stat().st_size != 49_784_788_364:
        raise RuntimeError("source shard size mismatch")
    shard_sha256 = sha256_file(SHARD)
    if shard_sha256 != EXPECTED_SHARD_SHA256:
        raise RuntimeError("source shard identity mismatch")

    with safe_open(str(SHARD), framework="pt", device="cpu") as source:
        if set(source.keys()) < set(KEYS):
            raise RuntimeError("one or more bound tensors are absent from source shard")
        tensors = {key: source.get_tensor(key) for key in KEYS}
        source_metadata = source.metadata() or {}

    records = {
        key: tensor_record(tensor, SHARD.name) for key, tensor in tensors.items()
    }
    metadata = {
        "format": source_metadata.get("format", "pt"),
        "component": "gemma4_layer0_norm_qkv",
        "source_checkpoint_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "source_checkpoint_index_sha256": sha256_file(INDEX),
        "source_shard_sha256": shard_sha256,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".part")
    if temporary.exists():
        raise RuntimeError(f"refusing to reuse stale temporary output: {temporary}")
    save_file(tensors, str(temporary), metadata=metadata)

    with safe_open(str(temporary), framework="pt", device="cpu") as finalized:
        if set(finalized.keys()) != set(KEYS):
            raise RuntimeError("finalized component contains keys outside the four bound tensors")
        for key, expected in tensors.items():
            actual = finalized.get_tensor(key)
            if actual.dtype != expected.dtype or tuple(actual.shape) != tuple(expected.shape):
                raise RuntimeError(f"finalized metadata mismatch for {key}")
            if tensor_bytes(actual) != tensor_bytes(expected):
                raise RuntimeError(f"finalized values mismatch for {key}")
        if finalized.metadata() != metadata:
            raise RuntimeError("finalized metadata mismatch")

    os.replace(temporary, OUTPUT)
    result = {
        "schema_version": 1,
        "operation": "offline_exact_component_materialization",
        "output": str(OUTPUT.relative_to(PROJECT)),
        "output_sha256": sha256_file(OUTPUT),
        "output_bytes": OUTPUT.stat().st_size,
        "tensor_count": len(KEYS),
        "tensors": records,
        "checkpoint_root": str(CHECKPOINT),
        "checkpoint_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "checkpoint_index": str(INDEX),
        "checkpoint_index_sha256": sha256_file(INDEX),
        "source_shard": SHARD.name,
        "source_shard_sha256": shard_sha256,
        "exact_values_verified_before_atomic_finalize": True,
        "exact_values_verified_after_atomic_finalize": True,
        "keys_are_exactly_bound_four": True,
    }
    terminal = PROJECT / "NORM_FP8_COMPONENT_READY.json"
    terminal_tmp = terminal.with_suffix(terminal.suffix + ".part")
    terminal_tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    json.loads(terminal_tmp.read_text())
    os.replace(terminal_tmp, terminal)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
