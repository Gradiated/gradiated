#!/usr/bin/env python3
"""Apply the single pre-import ParallelLMHead dispatch expansion for official W4 roots."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(os.environ.get("GLM_HEAD_SHARED_ROOT", "/workspace/model-awq"))
OUT = Path(os.environ.get("GLM_HEAD_SHARED_OUT", "/workspace/public-vllm-awq-batch/official-head-shared-w4-binding.json"))
SOURCE = Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py")
SCOPE = os.environ.get("GLM_SELECTIVE_W4_SCOPE", "combined")
VALID_SCOPES = {"combined", "head_only", "shared_only"}


def selected(name: str) -> bool:
    return (SCOPE in {"combined", "head_only"} and name == "lm_head.weight") or (
        SCOPE in {"combined", "shared_only"}
        and
        ".mlp.shared_experts." in name
        and ".layers.47." not in name
        and name.endswith(".weight")
    )


def main() -> None:
    if SCOPE not in VALID_SCOPES:
        raise RuntimeError(f"unsupported selective-W4 scope: {SCOPE}")
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())
    packed = [name for name in index["weight_map"] if name.endswith(".weight_packed") and selected(name.removesuffix("_packed"))]
    expected = {"combined": 139, "head_only": 1, "shared_only": 138}[SCOPE]
    if len(packed) != expected:
        raise RuntimeError(f"official selective W4 closure mismatch: {len(packed)} != {expected}")
    before = SOURCE.read_text()
    if SCOPE == "shared_only":
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "schema_version": 2,
            "scope": SCOPE,
            "adapter": "not_required_native_linear_only",
            "selected_weight_packed_count": len(packed),
            "source_sha256_before": hashlib.sha256(before.encode()).hexdigest(),
            "source_sha256_after": hashlib.sha256(before.encode()).hexdigest(),
        }, indent=2, sort_keys=True) + "\n")
        return
    import_line = "from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead\n"
    condition = "if isinstance(layer, LinearBase):"
    if before.count(condition) != 1:
        raise RuntimeError("unexpected pinned compressed-tensors dispatch layout")
    if import_line in before:
        after = before.replace(condition, "if isinstance(layer, (LinearBase, ParallelLMHead)):")
    else:
        needle = "from vllm.model_executor.layers.linear import (\n    LinearBase,"
        if before.count(needle) != 1:
            raise RuntimeError("unexpected pinned compressed-tensors import layout")
        after = before.replace(needle, import_line + needle).replace(condition, "if isinstance(layer, (LinearBase, ParallelLMHead)):")
    if after == before:
        raise RuntimeError("ParallelLMHead dispatch was already patched before bind")
    SOURCE.write_text(after)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema_version": 2,
        "scope": SCOPE,
        "adapter": "official_preimport_parallel_lm_head_selector_only",
        "selected_weight_packed_count": len(packed),
        "source_sha256_before": hashlib.sha256(before.encode()).hexdigest(),
        "source_sha256_after": hashlib.sha256(after.encode()).hexdigest(),
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
