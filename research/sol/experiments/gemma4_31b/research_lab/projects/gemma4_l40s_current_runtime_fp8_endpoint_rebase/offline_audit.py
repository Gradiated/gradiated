#!/usr/bin/env python3
"""Recompute the exact optimistic L40S memory lower bound and source gates."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parent
WORKLOAD_ROOT = PROJECT.parent / "gemma4_prefill_cuda_graph_padding_rebase/inputs/workload"
CHECKPOINT_TERMINAL = (
    PROJECT.parent
    / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json"
)
FACTORY = Path("/root/workspace/research/factory")
EXPECTED_COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
EXPOSED_L40S_MIB = 46068


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute(source: Path) -> dict:
    config = json.loads((WORKLOAD_ROOT / "MODEL_CONFIG.json").read_text())
    workload = json.loads((WORKLOAD_ROOT / "WORKLOAD.json").read_text())
    text = config["text_config"]
    local_layers = text["layer_types"].count("sliding_attention")
    full_layers = text["layer_types"].count("full_attention")
    hidden = text["hidden_size"]
    intermediate = text["intermediate_size"]
    local_q = text["num_attention_heads"] * text["head_dim"]
    local_kv = text["num_key_value_heads"] * text["head_dim"]
    full_q = text["num_attention_heads"] * text["global_head_dim"]
    full_kv = text["num_global_key_value_heads"] * text["global_head_dim"]
    mlp = hidden * (2 * intermediate) + intermediate * hidden
    local_linear = hidden * (local_q + 2 * local_kv) + local_q * hidden + mlp
    full_linear = hidden * (full_q + 2 * full_kv) + full_q * hidden + mlp
    fp8_linear_bytes = local_layers * local_linear + full_layers * full_linear
    tied_embedding_bf16_bytes = text["vocab_size"] * hidden * 2

    # At the final decode step, 357 generated tokens are already resident.
    full_tokens = workload["shared_prefix_tokens"] + workload["concurrency"] * (
        workload["prompt_tokens"]
        - workload["shared_prefix_tokens"]
        + workload["output_tokens"]
        - 1
    )
    swa_tokens = workload["concurrency"] * text["sliding_window"]
    full_e5m2_kv_bytes = full_tokens * full_layers * full_kv * 2
    swa_e5m2_kv_bytes = swa_tokens * local_layers * local_kv * 2
    minimum = (
        fp8_linear_bytes
        + tied_embedding_bf16_bytes
        + full_e5m2_kv_bytes
        + swa_e5m2_kv_bytes
    )
    physical = EXPOSED_L40S_MIB * 1024 * 1024

    source_files = {
        "gemma4_causal.py": "python/sglang/srt/models/gemma4_causal.py",
        "fp8.py": "python/sglang/srt/layers/quantization/fp8.py",
        "kv_cache_dtype.py": "python/sglang/srt/mem_cache/kv_cache_dtype.py",
        "memory_pool.py": "python/sglang/srt/mem_cache/memory_pool.py",
        "swa_memory_pool.py": "python/sglang/srt/mem_cache/swa_memory_pool.py",
        "radix_attention.py": "python/sglang/srt/layers/radix_attention.py",
        "triton_backend.py": "python/sglang/srt/layers/attention/triton_backend.py",
        "logits_processor.py": "python/sglang/srt/layers/logits_processor.py",
        "sampler.py": "python/sglang/srt/layers/sampler.py",
        "gemma4_detector.py": "python/sglang/srt/function_call/gemma4_detector.py",
        "server_args.py": "python/sglang/srt/server_args.py",
        "Dockerfile": "docker/Dockerfile",
    }
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    sources = {
        name: {"relative_path": relative, "sha256": sha256(source / relative)}
        for name, relative in source_files.items()
    }
    fp8_source = (source / source_files["fp8.py"]).read_text()
    kv_source = (source / source_files["kv_cache_dtype.py"]).read_text()
    swa_source = (source / source_files["swa_memory_pool.py"]).read_text()
    gemma_source = (source / source_files["gemma4_causal.py"]).read_text()
    parser_source = (source / source_files["gemma4_detector.py"]).read_text()

    for program in ("exact_c32_consumer.py", "l40s_endpoint_owner.py"):
        ast.parse((PROJECT / program).read_text())
    return {
        "commit": commit,
        "source_hashes": sources,
        "source_gates": {
            "selected_commit_exact": commit == EXPECTED_COMMIT,
            "dynamic_fp8_default": 'activation_scheme: str = "dynamic"' in fp8_source,
            "fp8_min_capability_sm80": "return 100 if self.use_mxfp8 else 80"
            in fp8_source,
            "e5m2_dtype_mapping": 'server_args_kv_cache_dtype == "fp8_e5m2"'
            in kv_source
            and "torch.float8_e5m2" in kv_source,
            "separate_swa_and_full_pools": "self.swa_kv_pool"
            in swa_source
            and "self.full_kv_pool" in swa_source,
            "separate_k_and_v_storage": "k_size, v_size" in swa_source,
            "attention_k_eq_v_runtime_duplication": "should_dup_k_to_v" in gemma_source,
            "gemma_tool_parser": "Gemma4Detector" in parser_source,
        },
        "bound_hashes": {
            "qualified_terminal": sha256(WORKLOAD_ROOT / "QUALIFIED_TERMINAL.json"),
            "workload": sha256(WORKLOAD_ROOT / "WORKLOAD.json"),
            "model_config": sha256(WORKLOAD_ROOT / "MODEL_CONFIG.json"),
            "launch": sha256(WORKLOAD_ROOT / "LAUNCH.json"),
            "checkpoint_terminal": sha256(CHECKPOINT_TERMINAL),
            "gpu_prices": sha256(FACTORY / "data/gpu_prices.json"),
            "accelerator_inventory": sha256(
                FACTORY / "data/accelerator_inventory.json"
            ),
        },
        "geometry": {
            "local_layers": local_layers,
            "full_layers": full_layers,
            "local_linear_elements_per_layer": local_linear,
            "full_linear_elements_per_layer": full_linear,
            "fp8_linear_bytes": fp8_linear_bytes,
            "tied_embedding_bf16_bytes": tied_embedding_bf16_bytes,
            "peak_full_tokens_lower_bound": full_tokens,
            "peak_swa_tokens_lower_bound": swa_tokens,
            "full_e5m2_kv_bytes": full_e5m2_kv_bytes,
            "swa_e5m2_kv_bytes": swa_e5m2_kv_bytes,
            "minimum_resident_bytes": minimum,
            "minimum_resident_gib": minimum / 2**30,
            "exposed_l40s_bytes": physical,
            "exposed_l40s_gib": physical / 2**30,
            "headroom_bytes": physical - minimum,
            "fits": minimum <= physical,
        },
        "program_hashes": {
            "exact_c32_consumer.py": sha256(PROJECT / "exact_c32_consumer.py"),
            "l40s_endpoint_owner.py": sha256(PROJECT / "l40s_endpoint_owner.py"),
            "offline_audit.py": sha256(PROJECT / "offline_audit.py"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = compute(args.source)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"commit={result['commit']} "
            f"minimum_gib={result['geometry']['minimum_resident_gib']:.12f} "
            f"physical_gib={result['geometry']['exposed_l40s_gib']:.12f} "
            f"fits={result['geometry']['fits']}"
        )
    return 0 if all(result["source_gates"].values()) and not result["geometry"]["fits"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
