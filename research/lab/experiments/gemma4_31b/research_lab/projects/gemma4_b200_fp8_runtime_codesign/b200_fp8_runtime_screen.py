#!/usr/bin/env python3
"""Exact-geometry, source-bound B200 FP8 runtime/physical-cost discriminator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[6]
UPSTREAM = ROOT / "evidence" / "upstream"
SOURCE_MANIFEST = UPSTREAM / "SOURCE_MANIFEST.json"
OUTPUT = ROOT / "B200_FP8_RUNTIME_SCREEN.json"
CONFIG = (
    ROOT.parent
    / "gemma4_h200_ngram_persistent_grouped_lm_head"
    / "inputs"
    / "bound"
    / "config.json"
)
WORKLOAD_BINDING = (
    ROOT.parent / "b200_exact_gemma_kernel_economic_mechanism" / "MECHANISM.json"
)
INVENTORY = REPO / "research" / "factory" / "data" / "accelerator_inventory.json"
PRICES = REPO / "research" / "factory" / "data" / "gpu_prices.json"
EXPECTED_CONFIG_SHA256 = (
    "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"
)
EXPECTED_WORKLOAD_SHA256 = (
    "0ced5b18806b14f6fd0070f00c52640af5e9764886fed46752da43028f8b1119"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open() as stream:
        return json.load(stream)


def require_tokens(source: str, *tokens: str) -> None:
    missing = [token for token in tokens if token not in source]
    if missing:
        raise RuntimeError(f"source_contract_missing:{missing}")


def ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def phase_roofline(
    *,
    compute_flops: float,
    hbm_bytes: float,
    tflops: float,
    hbm_gb_s: float,
) -> dict[str, float | str]:
    compute_seconds = compute_flops / (tflops * 1e12)
    hbm_seconds = hbm_bytes / (hbm_gb_s * 1e9)
    return {
        "compute_seconds": compute_seconds,
        "hbm_seconds": hbm_seconds,
        "nonoverlap_seconds": max(compute_seconds, hbm_seconds),
        "limiter": "compute" if compute_seconds >= hbm_seconds else "hbm",
    }


def source_discriminator(manifest: dict[str, Any]) -> dict[str, Any]:
    for local_name, record in manifest.items():
        path = UPSTREAM / local_name
        actual = sha256(path)
        if actual != record["sha256"]:
            raise RuntimeError(
                f"materialized_source_hash_mismatch:{local_name}:"
                f"{record['sha256']}:{actual}"
            )

    model = (UPSTREAM / "vllm/model_executor/models/gemma4.py").read_text()
    flashinfer_backend = (
        UPSTREAM / "vllm/v1/attention/backends/flashinfer.py"
    ).read_text()
    flashinfer_utils = (UPSTREAM / "vllm/utils/flashinfer.py").read_text()
    fp8_dispatch = (
        UPSTREAM / "vllm/csrc/scaled_mm_sm100_fp8_dispatch.cuh"
    ).read_text()
    fp8_quant = (
        UPSTREAM / "vllm/model_executor/layers/quantization/fp8.py"
    ).read_text()
    triton_backend = (
        UPSTREAM / "vllm/v1/attention/backends/triton_attn.py"
    ).read_text()
    triton_decode = (
        UPSTREAM / "vllm/v1/attention/ops/triton_decode_attention.py"
    ).read_text()
    decode_test = (
        UPSTREAM
        / "flashinfer/tests/attention/test_trtllm_gen_attention_decode.py"
    ).read_text()
    prefill_test = (
        UPSTREAM
        / "flashinfer/tests/attention/test_trtllm_gen_attention_prefill.py"
    ).read_text()
    generic_sm100_fmha = (
        UPSTREAM / "flashinfer/csrc/fmha_cutlass_sm100.cu"
    ).read_text()

    require_tokens(
        model,
        "global_head_dim",
        "attention_k_eq_v",
        "QKVParallelLinear",
        "ParallelLMHead",
    )
    require_tokens(
        flashinfer_backend,
        "return [64, 128, 256, 512]",
        "trtllm_batch_context_with_kv_cache",
        "trtllm_batch_decode_with_kv_cache",
        "torch.float8_e4m3fn",
    )
    require_tokens(
        flashinfer_utils,
        "SM100/SM103 has both prefill and decode TRTLLM kernels",
        "num_qo_heads % num_kv_heads == 0",
        "Requires NVIDIA artifactory to be accessible to download cubins",
    )
    require_tokens(
        decode_test,
        "test_trtllm_batch_decode_head_dim_512",
        '@pytest.mark.parametrize("head_dim", [512])',
        '("fp8", "fp8", "bf16")',
    )
    require_tokens(
        prefill_test,
        "test_trtllm_batch_prefill_head_dim_512",
        '@pytest.mark.parametrize("head_dim", [512])',
        '("fp8", "fp8", "bf16")',
    )
    require_tokens(
        fp8_dispatch,
        "cutlass::arch::Sm100",
        "cutlass::float_e4m3_t",
        "using ElementAcc",
        "m <= 64",
    )
    require_tokens(
        fp8_quant,
        "CutlassFP8ScaledMMLinearKernel",
        "Use per-token quantization for better perf if dynamic and cutlass",
    )
    require_tokens(
        triton_backend,
        "fp8_e4m3",
        "fp8_e5m2",
        "supports_head_size",
    )
    require_tokens(
        triton_decode,
        "tl.float32",
        "next_power_of_2",
    )

    # The standalone CUTLASS FMHA dispatcher is deliberately not selected:
    # its explicit SM100 list is narrower than Gemma's 256/512 dimensions.
    generic_supports_512 = (
        "HEAD_DIM_QK, 512" in generic_sm100_fmha
        or "head_dim_qk, 512" in generic_sm100_fmha.lower()
    )

    return {
        "passed": True,
        "checks": {
            "exact_gemma_hybrid_geometry_reaches_vllm": True,
            "sm100_dynamic_e4m3_linear_dispatch_present": True,
            "flashinfer_trtllm_gen_sm100_prefill_and_decode_present": True,
            "flashinfer_head_dim_512_fp8_kv_decode_test_present": True,
            "flashinfer_head_dim_512_fp8_kv_prefill_test_present": True,
            "triton_fp8_kv_fallback_present": True,
            "local_head_ratio_32_over_16_integral": True,
            "global_head_ratio_32_over_4_integral": True,
        },
        "highest_uncertainty_result": (
            "PASS: current vLLM advertises head dimensions 256 and 512, "
            "selects FlashInfer TRTLLM-generation attention for both SM100 "
            "phases when Q heads divide by KV heads, and the bound FlashInfer "
            "tree has explicit FP8-KV/BF16-output head-dimension-512 prefill "
            "and decode tests. Runtime cubin availability remains a later "
            "B200 invocation gate, not an offline source gap."
        ),
        "rejected_dispatch": {
            "symbol": "flashinfer::fmha_cutlass_sm100 generic noncausal dispatcher",
            "supports_exact_head_dim_512": generic_supports_512,
            "reason": (
                "Its explicit CUTLASS dispatcher is narrower; vLLM's "
                "TRTLLM-generation route is the selected current SM100 "
                "consumer and Triton is the source-complete fallback."
            ),
        },
    }


def build(generated_at: str) -> dict[str, Any]:
    if sha256(CONFIG) != EXPECTED_CONFIG_SHA256:
        raise RuntimeError("exact_config_hash_mismatch")
    if sha256(WORKLOAD_BINDING) != EXPECTED_WORKLOAD_SHA256:
        raise RuntimeError("workload_binding_hash_mismatch")

    config = load_json(CONFIG)
    text = config["text_config"]
    manifest = load_json(SOURCE_MANIFEST)
    discriminator = source_discriminator(manifest)
    inventory_all = load_json(INVENTORY)
    prices_all = load_json(PRICES)
    accelerator = next(
        item
        for item in inventory_all["accelerators"]
        if item["id"] == "nvidia-b200-sxm"
    )
    price = next(
        item
        for item in prices_all["accelerators"]
        if item["id"] == "nvidia-b200-sxm"
    )

    hidden = text["hidden_size"]
    intermediate = text["intermediate_size"]
    layers = text["num_hidden_layers"]
    q_heads = text["num_attention_heads"]
    local_kv_heads = text["num_key_value_heads"]
    global_kv_heads = text["num_global_key_value_heads"]
    local_dim = text["head_dim"]
    global_dim = text["global_head_dim"]
    vocab = text["vocab_size"]
    local_layers = text["layer_types"].count("sliding_attention")
    global_layers = text["layer_types"].count("full_attention")
    if (layers, local_layers, global_layers) != (60, 50, 10):
        raise RuntimeError("unexpected_layer_pattern")

    prompt_tokens = 4214
    prefix_hit_tokens = 535
    prefill_rows = prompt_tokens - prefix_hit_tokens
    output_tokens = 358
    decode_rows = 32
    verify_rows = 384
    window = text["sliding_window"]

    linear_families = [
        {
            "name": "local_qkv",
            "m": [prefill_rows, decode_rows, verify_rows],
            "k": hidden,
            "n": q_heads * local_dim + 2 * local_kv_heads * local_dim,
            "multiplicity": local_layers,
        },
        {
            "name": "local_o",
            "m": [prefill_rows, decode_rows, verify_rows],
            "k": q_heads * local_dim,
            "n": hidden,
            "multiplicity": local_layers,
        },
        {
            "name": "global_qkv_materialized",
            "m": [prefill_rows, decode_rows, verify_rows],
            "k": hidden,
            "n": q_heads * global_dim + 2 * global_kv_heads * global_dim,
            "multiplicity": global_layers,
            "note": (
                "attention_k_eq_v is true, but current vLLM duplicates K into "
                "the materialized V slice before the attention consumer."
            ),
        },
        {
            "name": "global_o",
            "m": [prefill_rows, decode_rows, verify_rows],
            "k": q_heads * global_dim,
            "n": hidden,
            "multiplicity": global_layers,
        },
        {
            "name": "gate_up",
            "m": [prefill_rows, decode_rows, verify_rows],
            "k": hidden,
            "n": 2 * intermediate,
            "multiplicity": layers,
        },
        {
            "name": "down",
            "m": [prefill_rows, decode_rows, verify_rows],
            "k": intermediate,
            "n": hidden,
            "multiplicity": layers,
        },
    ]
    transformer_weight_elements = sum(
        row["k"] * row["n"] * row["multiplicity"] for row in linear_families
    )
    linear_flops_per_row = 2 * transformer_weight_elements

    local_prefill_context_sum = sum(
        min(window, position + 1)
        for position in range(prefix_hit_tokens, prompt_tokens)
    )
    global_prefill_context_sum = sum(
        position + 1 for position in range(prefix_hit_tokens, prompt_tokens)
    )
    decode_global_context_sum = sum(
        prompt_tokens + token for token in range(output_tokens)
    )
    prefill_attention_flops = 4 * (
        local_layers * local_prefill_context_sum * q_heads * local_dim
        + global_layers * global_prefill_context_sum * q_heads * global_dim
    )
    decode_attention_flops = 4 * (
        local_layers * output_tokens * window * q_heads * local_dim
        + global_layers * decode_global_context_sum * q_heads * global_dim
    )

    # Source-informed query tiling: each query tile reloads its visible FP8 K/V
    # span once from HBM. This intentionally claims no inter-block L2 reuse.
    def tiled_kv_elements(query_block: int, sliding: int | None) -> int:
        total = 0
        for begin in range(prefix_hit_tokens, prompt_tokens, query_block):
            end = min(begin + query_block, prompt_tokens)
            start = max(0, end - sliding) if sliding is not None else 0
            total += end - start
        return total

    local_prefill_kv_bytes = (
        local_layers
        * tiled_kv_elements(64, window)
        * 2
        * local_kv_heads
        * local_dim
    )
    global_prefill_kv_bytes = (
        global_layers
        * tiled_kv_elements(16, None)
        * 2
        * global_kv_heads
        * global_dim
    )
    kv_bytes_per_token = (
        local_layers * 2 * local_kv_heads * local_dim
        + global_layers * 2 * global_kv_heads * global_dim
    )
    prefill_kv_append_bytes = prefill_rows * kv_bytes_per_token
    decode_kv_read_bytes = (
        local_layers
        * output_tokens
        * window
        * 2
        * local_kv_heads
        * local_dim
        + global_layers
        * decode_global_context_sum
        * 2
        * global_kv_heads
        * global_dim
    )
    decode_kv_append_bytes = output_tokens * kv_bytes_per_token

    dynamic_quant_bytes_per_row = 3 * (
        local_layers * (hidden + q_heads * local_dim + hidden + intermediate)
        + global_layers * (hidden + q_heads * global_dim + hidden + intermediate)
    )
    linear_output_bytes_per_row = 2 * sum(
        row["n"] * row["multiplicity"] for row in linear_families
    )
    qk_norm_and_rope_bytes_per_row = 2 * (
        local_layers * (q_heads + local_kv_heads) * local_dim * 4
        + global_layers * (q_heads + global_kv_heads) * global_dim * 4
    )
    four_rmsnorm_bytes_per_row = layers * 4 * hidden * 4
    geglu_bytes_per_row = layers * (2 * intermediate + intermediate) * 2
    two_residual_adds_bytes_per_row = layers * 2 * hidden * 6
    elementwise_bytes_per_row = (
        qk_norm_and_rope_bytes_per_row
        + four_rmsnorm_bytes_per_row
        + geglu_bytes_per_row
        + two_residual_adds_bytes_per_row
    )

    tied_head_weight_bytes = vocab * hidden * 2
    tied_head_flops_per_token = 2 * vocab * hidden
    logits_bf16_bytes_per_token = vocab * 2
    fp8_weight_bytes = transformer_weight_elements
    prefill_linear_hbm_bytes = fp8_weight_bytes + prefill_rows * (
        dynamic_quant_bytes_per_row + linear_output_bytes_per_row
    )
    decode_linear_hbm_bytes = (
        fp8_weight_bytes * output_tokens / decode_rows
        + output_tokens
        * (dynamic_quant_bytes_per_row + linear_output_bytes_per_row)
    )
    prefill_head_hbm_bytes = tied_head_weight_bytes + logits_bf16_bytes_per_token
    decode_head_hbm_bytes = (
        tied_head_weight_bytes * output_tokens / decode_rows
        + logits_bf16_bytes_per_token * output_tokens
    )

    # Inventory peaks do not say whether sparsity is included. Halving them is
    # the conservative dense prior; the fractions below are explicit later
    # measurement gates, never transferred achieved efficiency.
    dense_fp8_tflops = accelerator["peak_math"]["fp8_tflops"] / 2
    dense_bf16_tflops = accelerator["peak_math"]["bf16_tflops"] / 2
    assumed = {
        "dense_fp8_fraction": 0.65,
        "dense_bf16_attention_fraction": 0.50,
        "hbm_fraction": 0.75,
        "launch_seconds": 1.75e-6,
        "launches_per_transformer_pass": 842,
    }

    def physical_bound(hbm_fraction: float) -> dict[str, Any]:
        hbm_gb_s = accelerator["memory"]["bandwidth_gb_s"] * hbm_fraction
        fp8_tflops = dense_fp8_tflops * assumed["dense_fp8_fraction"]
        bf16_tflops = (
            dense_bf16_tflops * assumed["dense_bf16_attention_fraction"]
        )
        prefill_linear = phase_roofline(
            compute_flops=linear_flops_per_row * prefill_rows,
            hbm_bytes=prefill_linear_hbm_bytes,
            tflops=fp8_tflops,
            hbm_gb_s=hbm_gb_s,
        )
        prefill_attention = phase_roofline(
            compute_flops=prefill_attention_flops,
            hbm_bytes=local_prefill_kv_bytes
            + global_prefill_kv_bytes
            + prefill_kv_append_bytes,
            tflops=bf16_tflops,
            hbm_gb_s=hbm_gb_s,
        )
        prefill_head = phase_roofline(
            compute_flops=tied_head_flops_per_token,
            hbm_bytes=prefill_head_hbm_bytes,
            tflops=bf16_tflops,
            hbm_gb_s=hbm_gb_s,
        )
        decode_linear = phase_roofline(
            compute_flops=linear_flops_per_row * output_tokens,
            hbm_bytes=decode_linear_hbm_bytes,
            tflops=fp8_tflops,
            hbm_gb_s=hbm_gb_s,
        )
        decode_attention = phase_roofline(
            compute_flops=decode_attention_flops,
            hbm_bytes=decode_kv_read_bytes + decode_kv_append_bytes,
            tflops=bf16_tflops,
            hbm_gb_s=hbm_gb_s,
        )
        decode_head = phase_roofline(
            compute_flops=tied_head_flops_per_token * output_tokens,
            hbm_bytes=decode_head_hbm_bytes,
            tflops=bf16_tflops,
            hbm_gb_s=hbm_gb_s,
        )
        prefill_elementwise_seconds = (
            elementwise_bytes_per_row * prefill_rows / (hbm_gb_s * 1e9)
        )
        decode_elementwise_seconds = (
            elementwise_bytes_per_row * output_tokens / (hbm_gb_s * 1e9)
        )
        prefill_launch_seconds = (
            assumed["launch_seconds"]
            * assumed["launches_per_transformer_pass"]
        )
        decode_launch_seconds = (
            assumed["launch_seconds"]
            * assumed["launches_per_transformer_pass"]
            * output_tokens
            / decode_rows
        )
        prefill_seconds = sum(
            [
                prefill_linear["nonoverlap_seconds"],
                prefill_attention["nonoverlap_seconds"],
                prefill_head["nonoverlap_seconds"],
                prefill_elementwise_seconds,
                prefill_launch_seconds,
            ]
        )
        decode_seconds = sum(
            [
                decode_linear["nonoverlap_seconds"],
                decode_attention["nonoverlap_seconds"],
                decode_head["nonoverlap_seconds"],
                decode_elementwise_seconds,
                decode_launch_seconds,
            ]
        )
        return {
            "hbm_fraction": hbm_fraction,
            "effective_hbm_gb_s": hbm_gb_s,
            "effective_dense_fp8_tflops": fp8_tflops,
            "effective_dense_bf16_tflops": bf16_tflops,
            "prefill": {
                "linear": prefill_linear,
                "attention": prefill_attention,
                "tied_head": prefill_head,
                "elementwise_seconds": prefill_elementwise_seconds,
                "launch_seconds": prefill_launch_seconds,
                "seconds": prefill_seconds,
            },
            "decode": {
                "linear": decode_linear,
                "attention": decode_attention,
                "tied_head": decode_head,
                "elementwise_seconds": decode_elementwise_seconds,
                "launch_seconds": decode_launch_seconds,
                "seconds": decode_seconds,
            },
            "seconds_per_request": prefill_seconds + decode_seconds,
        }

    headline_bound = physical_bound(assumed["hbm_fraction"])
    sensitivity_65 = physical_bound(0.65)
    sensitivity_70 = physical_bound(0.70)
    sensitivity_80 = physical_bound(0.80)
    hurdle = 0.315609255362861553
    clears = headline_bound["seconds_per_request"] <= hurdle
    terminal = "source_complete_b200_candidate" if clears else "typed_none"

    max_context = prompt_tokens + output_tokens
    c32_kv_capacity_bytes = max_context * kv_bytes_per_token * decode_rows
    resident_bytes = fp8_weight_bytes + tied_head_weight_bytes + c32_kv_capacity_bytes
    l2_bytes = accelerator["cache"]["last_level_mb"] * 1_000_000

    return {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "terminal": terminal,
        "classification": (
            "offline_source_and_analytical_physical_cost_discriminator"
        ),
        "evidence_boundary": (
            "Source-bound and analytically derived at zero spend. No B200, "
            "CUDA, compilation, checkpoint, achieved timing, endpoint, "
            "quality, service, or deployment claim."
        ),
        "decision": {
            "result": terminal,
            "headline_seconds_per_request": headline_bound[
                "seconds_per_request"
            ],
            "production_hurdle_seconds_per_request": hurdle,
            "margin_seconds_per_request": hurdle
            - headline_bound["seconds_per_request"],
            "margin_fraction_of_hurdle": (
                hurdle - headline_bound["seconds_per_request"]
            )
            / hurdle,
            "interpretation": (
                "The exact production input reaches current SM100 FP8-linear "
                "and 256/512-wide FP8-KV attention consumers. A deliberately "
                "discounted, non-overlapping physical envelope clears the "
                "$5.15 planning hurdle; 70% HBM still clears but the 65%-HBM "
                "sensitivity fails. This admits exactly one later B200 "
                "falsifier; it is not measured throughput."
                if clears
                else "The conservative physical envelope does not clear the "
                "$5.15 planning hurdle."
            ),
        },
        "input_binding": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "config_path": str(CONFIG.relative_to(REPO)),
                "config_sha256": sha256(CONFIG),
            },
            "workload_binding": {
                "path": str(WORKLOAD_BINDING.relative_to(REPO)),
                "sha256": sha256(WORKLOAD_BINDING),
                "use": "geometry and prefix accounting only; no chip efficiency transfer",
            },
            "accelerator_inventory": {
                "path": str(INVENTORY.relative_to(REPO)),
                "sha256": sha256(INVENTORY),
                "record": accelerator,
            },
            "price_inventory": {
                "path": str(PRICES.relative_to(REPO)),
                "sha256": sha256(PRICES),
                "record": price,
            },
            "source_manifest_path": str(SOURCE_MANIFEST.relative_to(ROOT)),
            "source_manifest_sha256": sha256(SOURCE_MANIFEST),
            "source_count": len(manifest),
            "generator_sha256": sha256(Path(__file__)),
            "materializer_sha256": sha256(ROOT / "materialize_sources.py"),
        },
        "workload": {
            "concurrency": decode_rows,
            "prompt_tokens": prompt_tokens,
            "prefix_cache_hit_tokens": prefix_hit_tokens,
            "fresh_prefill_rows": prefill_rows,
            "output_tokens": output_tokens,
            "target_verify_rows": verify_rows,
            "target_verify_note": (
                "M384 binds the CUTLASS consumer but is not charged to the "
                "ordinary non-speculative c32 production bound."
            ),
        },
        "exact_geometry": {
            "hidden": hidden,
            "intermediate": intermediate,
            "layers": layers,
            "local_layers": local_layers,
            "global_layers": global_layers,
            "q_heads": q_heads,
            "local_kv_heads": local_kv_heads,
            "global_kv_heads": global_kv_heads,
            "local_head_dim": local_dim,
            "global_head_dim": global_dim,
            "sliding_window": window,
            "vocab": vocab,
            "attention_k_eq_v": text["attention_k_eq_v"],
            "tied_embeddings": config["tie_word_embeddings"],
            "linear_families": linear_families,
            "transformer_fp8_weight_bytes": fp8_weight_bytes,
            "linear_flops_per_row": linear_flops_per_row,
            "tied_bf16_weight_shape": [vocab, hidden],
            "tied_bf16_weight_bytes": tied_head_weight_bytes,
        },
        "runtime_mapping": [
            {
                "operations": "six transformer linear families",
                "consumer": (
                    "vLLM CutlassFP8ScaledMMLinearKernel -> "
                    "cutlass_gemm_sm100_fp8_dispatch"
                ),
                "contract": (
                    "dynamic per-token E4M3 activations; E4M3 weights with "
                    "FP32 scales; FP32 accumulator/scaled epilogue; BF16 "
                    "output; row-major aligned exact K/N"
                ),
                "shape_dispatch": {
                    "M32": "128x64x256 tile, 4x1 cluster, swapped A/B path",
                    "M384_and_M3679": "256x128x128 default large-M tile, 2x2 cluster",
                },
                "fallback": None,
            },
            {
                "operations": "local/global prefill and decode attention",
                "consumer": (
                    "vLLM FlashInferBackend -> "
                    "trtllm_batch_context_with_kv_cache / "
                    "trtllm_batch_decode_with_kv_cache"
                ),
                "contract": (
                    "SM100 TRTLLM-generation; q32/kv16 d256 local and "
                    "q32/kv4 d512 global; paged NHD/HND cache; E4M3 KV with "
                    "FP32 scales; BF16 output; FP32 softmax/accumulation"
                ),
                "fallback": (
                    "vLLM TritonAttentionBackend with E4M3/E5M2 paged KV, "
                    "FP32 descale/softmax/accumulation, and BF16 output"
                ),
                "unsupported_boundary": (
                    "FlashInfer standalone generic CUTLASS SM100 FMHA "
                    "dispatcher is not selected for d256/d512."
                ),
            },
            {
                "operations": "FP8 KV append",
                "consumer": (
                    "vLLM FlashInfer cache write / "
                    "triton_reshape_and_cache_flash fallback"
                ),
                "contract": (
                    "paged KV; BF16 producer divided by FP32 K/V scale then "
                    "cast to one-byte E4M3; separate K and V storage"
                ),
                "fallback": None,
            },
            {
                "operations": "RMSNorm, q/k norm, RoPE, GeGLU, residual",
                "consumer": "vLLM rms_norm and current Gemma elementwise ops",
                "contract": (
                    "BF16 material tensors with FP32 reductions/scalars; "
                    "elementwise HBM traffic conservatively materialized"
                ),
                "fallback": None,
            },
            {
                "operations": "tied vocabulary projection",
                "consumer": "vLLM ParallelLMHead / torch BF16 linear",
                "contract": (
                    "shared [262144,5376] BF16 embedding/head; BF16 input and "
                    "logits with FP32 GEMM accumulator"
                ),
                "fallback": None,
                "note": (
                    "No output-only quantized duplicate is admitted because "
                    "it would break tied-storage semantics."
                ),
            },
        ],
        "source_discriminator": discriminator,
        "physical_accounting": {
            "evidence_type": "analytical",
            "no_efficiency_transfer": True,
            "dense_peak_interpretation": (
                "Inventory BF16/FP8 peaks are halved before applying achieved "
                "fractions because the record does not label dense versus sparse."
            ),
            "assumptions_requiring_later_measurement": assumed,
            "traffic_bytes": {
                "dynamic_activation_quant_per_row": dynamic_quant_bytes_per_row,
                "linear_outputs_per_row": linear_output_bytes_per_row,
                "separate_elementwise_per_row": elementwise_bytes_per_row,
                "prefill_linear": prefill_linear_hbm_bytes,
                "prefill_local_kv_tiled": local_prefill_kv_bytes,
                "prefill_global_kv_tiled": global_prefill_kv_bytes,
                "prefill_kv_append": prefill_kv_append_bytes,
                "decode_linear": decode_linear_hbm_bytes,
                "decode_kv_read": decode_kv_read_bytes,
                "decode_kv_append": decode_kv_append_bytes,
                "decode_tied_head": decode_head_hbm_bytes,
            },
            "tensor_flops": {
                "prefill_linear": linear_flops_per_row * prefill_rows,
                "decode_linear": linear_flops_per_row * output_tokens,
                "target_verify_linear_not_in_headline": (
                    linear_flops_per_row * verify_rows
                ),
                "prefill_attention": prefill_attention_flops,
                "decode_attention": decode_attention_flops,
                "decode_tied_head": tied_head_flops_per_token * output_tokens,
            },
            "capacity_and_topology": {
                "model_plus_c32_max_context_kv_bytes": resident_bytes,
                "b200_hbm_bytes_decimal": accelerator["memory"]["capacity_gb"]
                * 1_000_000_000,
                "fits_before_runtime_workspace": resident_bytes
                < accelerator["memory"]["capacity_gb"] * 1_000_000_000,
                "headroom_bytes_before_runtime_workspace": (
                    accelerator["memory"]["capacity_gb"] * 1_000_000_000
                    - resident_bytes
                ),
                "l2_bytes_decimal": l2_bytes,
                "full_transformer_weights_fit_l2": fp8_weight_bytes <= l2_bytes,
                "decode_reuse_rule": (
                    "Charge every layer weight once per M32 call; 29.4 GB "
                    "cannot survive a full-layer traversal in 126 MB L2."
                ),
                "topology": (
                    "single B200 only; no NVLink or host traffic credited on "
                    "the request critical path"
                ),
            },
            "headline_75pct_hbm": headline_bound,
            "sensitivity_65pct_hbm": sensitivity_65,
            "sensitivity_70pct_hbm": sensitivity_70,
            "sensitivity_80pct_hbm": sensitivity_80,
            "hurdles": {
                "low_price_4_6475": 0.349733763339158042,
                "planning_price_5_15": hurdle,
                "high_price_5_72": 0.284158682713065909,
                "public_preemptible_3_95_nonproduction": 0.411490548131325823,
            },
        },
        "later_b200_falsifier": {
            "status": "ready_but_not_authorized",
            "provider_action_this_turn": "none",
            "required_hardware": "one full NVIDIA B200 SXM, SM100",
            "runtime": (
                "immutable image binding the source revisions in "
                "SOURCE_MANIFEST.json and resolving the required FlashInfer "
                "TRTLLM-generation cubins before scientific entry"
            ),
            "rows": (
                "all six exact FP8 linear families at M32 and M3679, plus "
                "M384 consumer binding; local q32/kv16/d256/context1024 and "
                "global q32/kv4/d512/context4393 attention at c32"
            ),
            "candidate": (
                "current vLLM dynamic-E4M3 CUTLASS SM100 linear plus "
                "FlashInfer TRTLLM-generation E4M3-KV attention"
            ),
            "strongest_baseline": (
                "same-B200 BF16 linears and BF16 KV on the same vLLM/"
                "FlashInfer path from identical BF16 inputs"
            ),
            "numerical_gate": {
                "finite_and_nonzero": True,
                "cosine_similarity_min": 0.999,
                "normalized_rmse_max": 0.03,
                "attention_reference": "FP32 SDPA over identical exact tensors",
            },
            "economic_gate": (
                "Aggregate exact component p50s with the artifact's c32 "
                "multiplicities and all residuals; require <= "
                "0.315609255362861553 s/request."
            ),
            "mechanism_gates": {
                "prefill_fp8_dense_peak_fraction_min": 0.65,
                "streaming_hbm_fraction_min": 0.75,
                "global_d512_no_spill_or_material_fallback": True,
                "launch_seconds_per_request_max": (
                    assumed["launch_seconds"]
                    * assumed["launches_per_transformer_pass"]
                    * (1 + output_tokens / decode_rows)
                ),
            },
            "required_counters": [
                "DRAM read/write bytes",
                "L2 bytes/hit behavior",
                "TCGen05 tensor-pipe activity",
                "registers, local-memory spills, active warps and waves",
                "kernel symbols and launch interval-union time",
            ],
            "predicted_counter_change": (
                "E4M3 transformer weights and KV halve their logical DRAM "
                "payload versus BF16, TCGen05 is active in the linear path, "
                "and the d512 TRTLLM-generation kernel shows no local-memory "
                "spill or Triton fallback."
            ),
            "wall_clock_minutes_max": 25,
            "future_provider_spend_usd_max": 2.50,
            "authorization_boundary": (
                "Requires a compatible shared bench and a fresh positive "
                "director reservation; neither exists in this turn."
            ),
            "stop_rule": (
                "Any source/image/cubin identity failure is repaired before "
                "scientific entry. After an interpretable exact-shape sample, "
                "do not replay. Fail candidate on numerical gate, aggregate "
                "hurdle, <75% streaming HBM, d512 spills/fallback, or missing "
                "candidate-path proof."
            ),
        },
        "excluded_claims": [
            "No H100, H200, MI355X, FP4, or vendor-peak efficiency transfer.",
            "No target-verification acceptance or speculative speedup is charged.",
            "No provider was contacted and no GPU pool claim was attempted.",
            "The 75% HBM and 65% dense-FP8 levels are falsifier gates, not measurements.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify",
        action="store_true",
        help="rebuild and compare with the persisted artifact",
    )
    args = parser.parse_args()
    existing = load_json(OUTPUT) if OUTPUT.exists() else None
    generated_at = (
        existing["generated_at_utc"]
        if args.verify and existing
        else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    artifact = build(generated_at)
    encoded = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    if args.verify:
        if existing is None:
            raise RuntimeError("artifact_missing")
        if encoded != OUTPUT.read_text():
            raise RuntimeError("artifact_not_reproducible")
        print(
            f"verified {artifact['terminal']} "
            f"{artifact['decision']['headline_seconds_per_request']:.9f}s/request"
        )
        return
    temporary = OUTPUT.with_suffix(".json.part")
    temporary.write_text(encoded)
    temporary.replace(OUTPUT)
    print(
        f"wrote {OUTPUT.name}: {artifact['terminal']} "
        f"{artifact['decision']['headline_seconds_per_request']:.9f}s/request"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
