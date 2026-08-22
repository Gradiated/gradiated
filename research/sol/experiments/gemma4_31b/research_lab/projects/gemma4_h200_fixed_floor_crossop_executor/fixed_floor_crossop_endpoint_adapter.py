#!/usr/bin/env python3
"""Build and audit the exact production QKV-to-E5M2 endpoint adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib

from install_fused_qkv_cache import (
    ATTENTION_SAVE,
    CANDIDATE_FORWARD,
    EXPECTED_GEMMA4_CAUSAL_SHA256,
    IMPORT_ANCHOR,
    IMPORT_REPLACEMENT,
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: bytes | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    if isinstance(value, bytes):
        temporary.write_bytes(value)
    else:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def candidate_bytes(runtime_source: pathlib.Path) -> bytes:
    source = runtime_source.read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED_GEMMA4_CAUSAL_SHA256:
        raise RuntimeError("pinned_gemma4_causal_source_mismatch")
    source_text = source.decode()
    class_start = source_text.index("class Gemma4Attention")
    source_forward = source_text.index("    def forward(\n", class_start)
    source_body = source_text.index("        qkv, _ = self.qkv_proj(hidden_states)\n", source_forward)
    source_end = source_text.index("        attn_output = self.attn(\n", source_body)
    if source_text.count(IMPORT_ANCHOR) != 1:
        raise RuntimeError("candidate_adapter_import_anchor_not_unique")
    candidate_text = source_text.replace(IMPORT_ANCHOR, IMPORT_REPLACEMENT, 1)
    shift = len(IMPORT_REPLACEMENT) - len(IMPORT_ANCHOR)
    source_body += shift
    source_end += shift
    candidate_text = candidate_text[:source_body] + CANDIDATE_FORWARD + candidate_text[source_end:]
    decoder_start = candidate_text.index("class Gemma4DecoderLayer", source_body)
    prefix, suffix = candidate_text[:decoder_start], candidate_text[decoder_start:]
    if prefix.count(ATTENTION_SAVE) != 1:
        raise RuntimeError("candidate_adapter_save_cache_anchor_not_unique")
    candidate_text = prefix.replace(ATTENTION_SAVE, "            save_kv_cache=False,\n", 1) + suffix
    compile(candidate_text, str(runtime_source), "exec")
    candidate = candidate_text.encode()
    original = b"from fused_qkv_kv_cache import (\n"
    replacement = b"from fixed_floor_crossop_endpoint_adapter import (\n"
    if candidate.count(original) != 1:
        raise RuntimeError("candidate_adapter_import_anchor_not_unique")
    return candidate.replace(original, replacement, 1)


def append_audit(value: dict) -> None:
    destination = os.environ.get("FIXED_FLOOR_CROSSOP_AUDIT")
    if not destination:
        return
    path = pathlib.Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(descriptor, (json.dumps(value, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def qkv_norm_rope_cache_store(*args, **kwargs):
    from fused_qkv_kv_cache import qkv_norm_rope_cache_store as implementation

    result = implementation(*args, **kwargs)
    qkv = args[0]
    destination = args[5]
    head_dim = int(kwargs["head_dim"])
    append_audit(
        {
            "event": "qkv_norm_rope_e5m2_cache_commit",
            "head_dim": head_dim,
            "class": "local" if head_dim == 256 else "global",
            "qkv_dtype": str(qkv.dtype),
            "qkv_shape": list(qkv.shape),
            "cache_key_dtype": str(destination.key.dtype),
            "cache_value_dtype": str(destination.value.dtype),
            "cache_slots_dtype": str(destination.slots.dtype),
            "num_q_heads": int(kwargs["num_q_heads"]),
            "num_kv_heads": int(kwargs["num_kv_heads"]),
            "finite_qkv": "not_observed_during_cuda_graph_capture",
        }
    )
    return result


def resolve_cache_destination(*args, **kwargs):
    from fused_qkv_kv_cache import resolve_cache_destination as implementation

    return implementation(*args, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-source", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-output", type=pathlib.Path, required=True)
    parser.add_argument("--binding-output", type=pathlib.Path, required=True)
    arguments = parser.parse_args()
    candidate = candidate_bytes(arguments.runtime_source)
    atomic(arguments.candidate_output, candidate)
    atomic(
        arguments.binding_output,
        {
            "schema_version": 1,
            "runtime_source": str(arguments.runtime_source),
            "runtime_source_sha256": sha256(arguments.runtime_source),
            "candidate_gemma4_causal_sha256": hashlib.sha256(candidate).hexdigest(),
            "adapter_sha256": sha256(pathlib.Path(__file__)),
            "candidate_import": "fixed_floor_crossop_endpoint_adapter",
            "candidate_invocation_proof": "FIXED_FLOOR_CROSSOP_AUDIT JSONL emits local/global QKV-to-E5M2 cache commits",
        },
    )


if __name__ == "__main__":
    main()
