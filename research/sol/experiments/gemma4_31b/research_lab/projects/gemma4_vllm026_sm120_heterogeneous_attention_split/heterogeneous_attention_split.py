#!/usr/bin/env python3
"""Fail-closed Gemma 4 local/global attention dispatch for vLLM 0.26.0."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_REVISION = "568afb3a13806beb53bb2e6bd518269357b237c0"
DISPATCH = {
    "backend_per_kind": {
        "sliding_window": "TRITON_ATTN",
        "full_attention": "FLEX_ATTENTION",
    }
}
SOURCE_FILES = (
    "vllm/model_executor/models/gemma4.py",
    "vllm/model_executor/layers/attention/attention.py",
    "vllm/v1/attention/selector.py",
    "vllm/v1/attention/backends/triton_attn.py",
    "vllm/v1/attention/backends/flex_attention.py",
    "vllm/v1/worker/gpu_model_runner.py",
    "vllm/v1/kv_cache_interface.py",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_text_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    outer = json.loads(path.read_text())
    return outer, outer.get("text_config", outer)


def _source_contract(source_root: Path) -> tuple[list[str], dict[str, str]]:
    contents = {
        relative: (source_root / relative).read_text() for relative in SOURCE_FILES
    }
    for relative, text in contents.items():
        ast.parse(text, filename=relative)

    checks = {
        "selector derives full/sliding kind": (
            "get_attn_spec_kind(" in contents["vllm/v1/attention/selector.py"]
            and "attention_config.backend_per_kind.get(kind.value, backend)"
            in contents["vllm/v1/attention/selector.py"]
        ),
        "Gemma4 binds per-layer head size and window": all(
            marker in contents["vllm/model_executor/models/gemma4.py"]
            for marker in (
                '"global_head_dim", config.head_dim',
                "head_dim = config.head_dim",
                "per_layer_sliding_window=sliding_window",
            )
        ),
        "runner groups distinct backend/spec/head consumers": all(
            marker in contents["vllm/v1/worker/gpu_model_runner.py"]
            for marker in (
                "layers[layer_name].get_attn_backend()",
                "layer_kv_cache_spec",
                "num_heads_q",
                "AttentionGroup(",
            )
        ),
        "Triton preserves sliding and multimodal prefix": all(
            marker in contents["vllm/v1/attention/backends/triton_attn.py"]
            for marker in (
                "def supports_mm_prefix",
                "def supports_sliding_window",
                "mm_prefix_clamp_sliding_window",
                "window_size=self.sliding_window",
            )
        ),
        "Flex preserves full-attention multimodal prefix and GQA": all(
            marker in contents["vllm/v1/attention/backends/flex_attention.py"]
            for marker in (
                "def supports_mm_prefix",
                "mask_mod = or_masks(mask_mod, prefix_lm_mask_mod)",
                "enable_gqa = self.num_kv_heads != self.num_heads",
            )
        ),
        "Triton and Flex expose identical NHD layered stride": (
            "return (1, 0, 3, 2, 4)"
            in contents["vllm/v1/attention/backends/triton_attn.py"]
            and "return (1, 0, 3, 2, 4)"
            in contents["vllm/v1/attention/backends/flex_attention.py"]
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    hashes = {
        relative: sha256_bytes(contents[relative].encode()) for relative in SOURCE_FILES
    }
    return failures, hashes


def _git_revision(source_root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def evaluate(source_root: Path, config_path: Path) -> dict[str, Any]:
    outer, config = load_text_config(config_path)
    layer_types = config.get("layer_types") or []
    failures: list[str] = []

    expected = {
        "num_hidden_layers": 60,
        "num_attention_heads": 32,
        "num_key_value_heads": 16,
        "head_dim": 256,
        "global_head_dim": 512,
        "sliding_window": 1024,
        "num_kv_shared_layers": 0,
        "attention_k_eq_v": True,
        "num_global_key_value_heads": 4,
        "attn_logit_softcapping": None,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            failures.append(f"model_config.{key}={config.get(key)!r}, expected {value!r}")
    if layer_types.count("sliding_attention") != 50:
        failures.append("model_config must contain exactly 50 sliding_attention layers")
    if layer_types.count("full_attention") != 10:
        failures.append("model_config must contain exactly 10 full_attention layers")
    if outer.get("architectures") != ["Gemma4ForConditionalGeneration"]:
        failures.append("outer architecture is not Gemma4ForConditionalGeneration")

    source_failures, source_hashes = _source_contract(source_root)
    failures.extend(f"source_contract: {failure}" for failure in source_failures)
    revision = _git_revision(source_root)
    if revision != EXPECTED_REVISION:
        failures.append(f"vLLM revision {revision!r}, expected {EXPECTED_REVISION!r}")

    base = {
        "schema_version": 1,
        "vllm_revision": revision,
        "source_hashes": source_hashes,
        "model_geometry": {
            "layers": 60,
            "sliding_layers": 50,
            "full_layers": 10,
            "q_heads": 32,
            "local_kv_heads": 16,
            "global_kv_heads": 4,
            "local_head_dim": 256,
            "global_head_dim": 512,
            "sliding_window": 1024,
        },
    }
    if failures:
        return {
            **base,
            "classification": "typed_none",
            "none_type": "exact_dispatch_precondition_failed",
            "failures": failures,
        }
    return {
        **base,
        "classification": "exact_layer_aware_dispatch",
        "attention_config": DISPATCH,
        "consumer_binding": {
            "sliding_window": {
                "backend": "TRITON_ATTN",
                "layers": 50,
                "q_layout": "[T,32,256]",
                "k_v_layout": "[T,16,256]",
                "mask": "(causal OR same_mm_prefix_block) AND window_1024",
            },
            "full_attention": {
                "backend": "FLEX_ATTENTION",
                "layers": 10,
                "q_layout": "[T,32,512]",
                "k_v_layout": "[T,4,512]",
                "mask": "causal OR same_mm_prefix_block",
            },
            "kv_cache": {
                "logical": "[num_blocks,num_kv_heads,block_size,2*head_dim]",
                "physical": "[num_blocks,block_size,num_kv_heads,2*head_dim]",
                "layout": "NHD",
                "ownership": "per-layer; num_kv_shared_layers=0",
                "dtype": "BF16/auto only for this candidate",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-source", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.vllm_source.resolve(), args.model_config.resolve())
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(encoded)
        json.loads(temporary.read_text())
        temporary.replace(args.output)
    else:
        print(encoded, end="")
    return 0 if result["classification"] != "typed_none" else 2


if __name__ == "__main__":
    raise SystemExit(main())
