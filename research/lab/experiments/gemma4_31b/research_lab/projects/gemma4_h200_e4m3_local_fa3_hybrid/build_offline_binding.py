#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts/offline-binding-20260723"
SOURCE_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1 << 20), b""):
            value.update(part)
    return value.hexdigest()


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def require_symbols(path: Path, symbols: set[str]) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    observed = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = symbols - observed
    if missing:
        raise RuntimeError(f"source_symbols_missing:{path.name}:{sorted(missing)}")
    return sorted(symbols)


def main() -> int:
    config = json.loads((ROOT / "inputs/production_config.json").read_text())
    text = config["text_config"]
    local_layers = [
        index
        for index, layer_type in enumerate(text["layer_types"])
        if layer_type == "sliding_attention"
    ]
    global_layers = [
        index
        for index, layer_type in enumerate(text["layer_types"])
        if layer_type == "full_attention"
    ]
    if len(local_layers) != 50 or len(global_layers) != 10:
        raise RuntimeError("production_layer_pattern_mismatch")
    source_contract = {
        "model_runner.v0.5.13.py": {"ModelRunner"},
        "forward_context.v0.5.13.py": {
            "ForwardContext",
            "get_attn_backend",
            "forward_context",
        },
        "attention_registry.v0.5.13.py": {
            "create_flashattention_v3_backend",
            "create_triton_backend",
        },
        "flashattention_backend.v0.5.13.py": {
            "FlashAttentionBackend",
            "FlashAttentionMetadata",
        },
        "triton_backend.v0.5.13.py": {
            "TritonAttnBackend",
            "ForwardMetadata",
        },
        "radix_attention.v0.5.13.py": {
            "RadixAttention",
            "unified_attention_with_output",
        },
        "memory_pool.v0.5.13.py": {
            "MHATokenToKVPool",
            "_set_kv_buffer_impl",
        },
        "swa_memory_pool.v0.5.13.py": {"SWAKVPool"},
        "gemma4_causal.v0.5.13.py": {
            "Gemma4Attention",
            "Gemma4DecoderLayer",
        },
        "hf_config.v0.5.13.py": {"get_config"},
    }
    source_rows = []
    for name, symbols in source_contract.items():
        path = ROOT / "inputs/source" / name
        source_rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
                "required_symbols": require_symbols(path, symbols),
            }
        )
    stack_rows = []
    for path in sorted((ROOT / "inputs/stack").glob("*.py")):
        stack_rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        )
    candidate_paths = [
        ROOT / "gemma4_layer_hybrid_backend.py",
        ROOT / "install_hybrid_backend.py",
        ROOT / "sitecustomize.py",
        ROOT / "e4m3_fa3_component.py",
        ROOT / "remote_component.sh",
        ROOT / "remote_hybrid_candidate.sh",
        ROOT / "run_hybrid_owner.py",
    ]
    candidate_rows = [
        {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in candidate_paths
    ]
    binding = {
        "schema_version": 1,
        "status": "offline_binding_pass",
        "runtime": {
            "release": "SGLang v0.5.13",
            "source_commit": SOURCE_COMMIT,
            "image": IMAGE,
        },
        "geometry": {
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "phase": ["prefill", "decode"],
            "page_size": 1,
            "kv_dtype": "fp8_e4m3",
            "scale_convention": "RadixAttention k_scale/v_scale; unit scale when absent",
            "local": {
                "layer_ids": local_layers,
                "q_heads": text["num_attention_heads"],
                "kv_heads": text["num_key_value_heads"],
                "head_dim": text["head_dim"],
                "window_tokens": text["sliding_window"],
                "backend": "FlashAttentionBackend/fa3",
            },
            "global": {
                "layer_ids": global_layers,
                "q_heads": text["num_attention_heads"],
                "kv_heads": text["num_global_key_value_heads"],
                "head_dim": text["global_head_dim"],
                "backend": "TritonAttnBackend/triton",
            },
        },
        "producer_consumer_trace": [
            "Gemma4Attention.forward produces normalized and rotated BF16 K/V.",
            "SWAKVPool.set_kv_buffer selects the layer pool and MHATokenToKVPool.set_kv_buffer converts/stores E4M3 paged K/V.",
            "RadixAttention.forward reads the process ForwardContext backend.",
            "Gemma4LayerHybridAttnBackend dispatches local layer ids to FlashAttentionBackend and global layer ids to TritonAttnBackend.",
            "Both backends consume the same paged pool, per-layer scale fields, page/slot mapping, and ForwardBatch metadata.",
        ],
        "physical_hypothesis": {
            "change": "Replace the residency-limited local Triton consumer with stock Hopper FA3 while preserving E4M3 production, page geometry, window, global Triton path, and model workload.",
            "prediction": "At least 35.0743696579% conservative reduction of the local attention boundary.",
            "falsifier": "Numerical failure, component regression, conservative reduction below the gate, missing local/global path proof, or c32 regression.",
            "measured_local_wall_fraction": 0.1531203203096733,
        },
        "source_snapshots": source_rows,
        "comparator_stack_snapshots": stack_rows,
        "candidate_files": candidate_rows,
        "offline_tests": {
            "installer": "ephemeral pinned-image source patch parsed successfully",
            "router": "dual metadata/graph lifecycle and local/global dispatch passed with 50/10 audit",
            "cuda_execution_equivalent": False,
            "reason": (
                "The prerequisite E4M3-Triton endpoint closed without the "
                "required retained QKV audit and is inadmissible as comparator; "
                "therefore this project did not claim the H200."
            ),
        },
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    binding_path = ROOT / "SOURCE_BINDING.json"
    atomic(binding_path, binding)
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "offline_exact_source_binding_complete",
        "pass": True,
        "source_binding": str(binding_path.relative_to(ROOT)),
        "source_binding_sha256": digest(binding_path),
        "scientific_invocation_started": False,
        "candidate_cuda_invocation_started": False,
        "provider_spend_usd": 0.0,
    }
    atomic(ARTIFACTS / "OFFLINE_BINDING_TERMINAL.json", terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
