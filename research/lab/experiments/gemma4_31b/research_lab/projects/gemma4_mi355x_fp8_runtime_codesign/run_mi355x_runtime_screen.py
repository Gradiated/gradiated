#!/usr/bin/env python3
"""Offline exact-geometry MI355X runtime and physical-cost discriminator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE = next(parent for parent in PROJECT_DIR.parents if parent.name == "workspace")
LAB_DIR = PROJECT_DIR.parent.parent

CONFIG_PATH = (
    PROJECT_DIR.parent
    / "gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json"
)
INVENTORY_PATH = WORKSPACE / "research/factory/data/accelerator_inventory.json"
PRICE_PATH = WORKSPACE / "research/factory/data/gpu_prices.json"
BINDINGS_PATH = PROJECT_DIR / "SOURCE_BINDINGS.json"
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_FP8_RUNTIME_SCREEN.json"

MODEL_ID = "google/gemma-4-31B-it"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
CONFIG_SHA256 = "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"

PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
CACHE_FRACTION = Fraction(127, 1000)
FRESH_PROMPT_TOKENS = Fraction(PROMPT_TOKENS) * (1 - CACHE_FRACTION)
CONCURRENCY = 32
TARGET_DEPTH = 12
TARGET_VERIFICATION_CYCLES = 15

BASE_HURDLE_S = 0.625149101968745
PRICE_HURDLES = {
    "production_low_2_40": 0.6772448604661404,
    "production_base_2_60": BASE_HURDLE_S,
    "production_high_2_75": 0.5910500600431771,
    "experimental_2_95": 0.5509788695317752,
}

LOCAL = {
    "layers": 50,
    "head_dim": 256,
    "q_heads": 32,
    "kv_heads": 16,
    "window": 1024,
}
GLOBAL = {
    "layers": 10,
    "head_dim": 512,
    "q_heads": 32,
    "kv_heads": 4,
    "window": None,
}

HIDDEN = 5376
INTERMEDIATE = 21504
VOCAB = 262144

LINEAR_SHAPES = {
    "sliding_qkv": {
        "layers": 50,
        "k": HIDDEN,
        "n": 16384,
        "meaning": "Q=32x256, K=16x256, V=16x256",
    },
    "sliding_o": {
        "layers": 50,
        "k": 8192,
        "n": HIDDEN,
        "meaning": "32x256 attention output to hidden",
    },
    "global_qkv": {
        "layers": 10,
        "k": HIDDEN,
        "n": 20480,
        "meaning": "Q=32x512 plus duplicated K/V=4x512 under attention_k_eq_v",
    },
    "global_o": {
        "layers": 10,
        "k": 16384,
        "n": HIDDEN,
        "meaning": "32x512 attention output to hidden",
    },
    "gate_up": {
        "layers": 60,
        "k": HIDDEN,
        "n": 43008,
        "meaning": "packed gate and up projections",
    },
    "down": {
        "layers": 60,
        "k": INTERMEDIATE,
        "n": HIDDEN,
        "meaning": "MLP down projection",
    },
    "tied_lm_head": {
        "layers": 1,
        "k": HIDDEN,
        "n": VOCAB,
        "meaning": "BF16 tied embedding/output projection",
    },
}

SOURCE_ASSERTIONS = {
    "vllm/model_executor/models/gemma4.py": [
        "self.qkv_proj = QKVParallelLinear(",
        "quant_config=quant_config",
        "yield name.replace(\"k_proj\", \"v_proj\"), weight.clone()",
        "self.lm_head = ParallelLMHead(",
        "self.lm_head = self.lm_head.tie_weights(self.model.embed_tokens)",
    ],
    "vllm/model_executor/layers/quantization/fp8.py": [
        "if isinstance(layer, LinearBase):",
        "Fp8PerTensorOnlineLinearMethod",
        "elif isinstance(layer, Attention):",
        "return Fp8KVCacheMethod(self)",
    ],
    "vllm/model_executor/layers/quantization/online/fp8.py": [
        "class Fp8PerTensorOnlineLinearMethod",
        "qweight, weight_scale = ops.scaled_fp8_quant(layer.weight, scale=None)",
        "self.activation_quant_key = kFp8DynamicTensorSym",
        "return self.fp8_linear.apply_weights(layer, x, bias)",
    ],
    "vllm/model_executor/layers/quantization/utils/w8a8_utils.py": [
        "def cutlass_fp8_supported()",
        "if not current_platform.is_cuda():",
        "return False",
    ],
    "vllm/model_executor/kernels/linear/__init__.py": [
        "PlatformEnum.ROCM: [",
        "AiterPerTokenFp8ScaledMMLinearKernel",
        "ROCmFP8ScaledMMLinearKernel",
        "def init_fp8_linear_kernel(",
    ],
    "vllm/model_executor/kernels/linear/scaled_mm/aiter.py": [
        "requires per token activation scales and per channel weight scales.",
        "AiterPreshuffledPerTokenFp8ScaledMMLinearKernel",
        "AiterHipbMMPerTokenFp8ScaledMMLinearKernel",
    ],
    "vllm/model_executor/kernels/linear/scaled_mm/rocm.py": [
        "class ROCmFP8ScaledMMLinearKernel",
        "requires per tensor activation and weight scales.",
        "A.shape[0] <= 4",
        "output = torch._scaled_mm(",
    ],
    "vllm/model_executor/layers/vocab_parallel_embedding.py": [
        "quant_method = quant_config.get_quant_method(self, prefix=prefix)",
        "quant_method = UnquantizedEmbeddingMethod()",
        "return dispatch_unquantized_gemm()(layer, x, layer.weight, bias)",
        "class ParallelLMHead(VocabParallelEmbedding)",
    ],
    "vllm/model_executor/layers/layernorm.py": [
        "class RMSNorm(CustomOp)",
        "return ir.ops.rms_norm(",
        "return ir.ops.fused_add_rms_norm.maybe_inplace(",
    ],
    "vllm/platforms/rocm.py": [
        "def supports_fp8(cls) -> bool:",
        "return any(gfx in _GCN_ARCH for gfx in [\"gfx95\"])",
        "return torch.float8_e4m3fn",
        "AttentionBackendEnum.ROCM_AITER_FA",
        "AttentionBackendEnum.ROCM_AITER_UNIFIED_ATTN",
    ],
    "vllm/v1/attention/backends/rocm_aiter_fa.py": [
        "rocm_aiter_ops.flash_attn_varlen_func(",
        "from aiter.ops.triton.unified_attention import",
        "unified_attention(",
        "key_cache = key_cache.view(current_platform.fp8_dtype())",
    ],
    "aiter/ops/triton/attention/unified_attention.py": [
        "assert causal, \"Only causal attention is supported\"",
        "SLIDING_WINDOW = 1 + window_size[0]",
        "KV_CACHE_DTYPE = \"fp8\"",
        "num_queries_per_kv = num_query_heads // num_kv_heads",
    ],
    "aiter/ops/triton/_triton_kernels/attention/unified_attention.py": [
        "HEAD_SIZE_PADDED",
        "SLIDING_WINDOW",
        "acc = tl.zeros([BLOCK_M, HEAD_SIZE_PADDED], dtype=tl.float32)",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def fetch_repository(
    destination: Path,
    url: str,
    commit: str,
    paths: list[str],
) -> Path:
    run(["git", "init", "-q", str(destination)])
    run(["git", "-C", str(destination), "remote", "add", "origin", url])
    run(
        [
            "git",
            "-C",
            str(destination),
            "-c",
            "protocol.version=2",
            "fetch",
            "--depth",
            "1",
            "--filter=blob:none",
            "origin",
            commit,
        ]
    )
    run(["git", "-C", str(destination), "sparse-checkout", "init", "--no-cone"])
    subprocess.run(
        ["git", "-C", str(destination), "sparse-checkout", "set", "--stdin"],
        input="\n".join(f"/{path}" for path in paths) + "\n",
        text=True,
        check=True,
    )
    run(["git", "-C", str(destination), "checkout", "-q", "--detach", "FETCH_HEAD"])
    return destination


def source_root_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def verify_sources(
    bindings: dict[str, Any], vllm_root: Path, aiter_root: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    roots = {"vllm": vllm_root, "aiter": aiter_root}
    checks: dict[str, Any] = {}
    texts: dict[str, str] = {}

    for repo_name, repo in bindings["repositories"].items():
        root = roots[repo_name]
        observed_commit = source_root_commit(root)
        checks[f"{repo_name}_commit"] = {
            "expected": repo["commit"],
            "observed": observed_commit,
            "pass": observed_commit == repo["commit"],
        }
        for relative, expected_hash in repo["files"].items():
            path = root / relative
            observed_hash = sha256(path) if path.is_file() else None
            key = f"{repo_name}:{relative}"
            checks[key] = {
                "expected_sha256": expected_hash,
                "observed_sha256": observed_hash,
                "pass": observed_hash == expected_hash,
            }
            if path.is_file():
                texts[relative] = path.read_text(errors="replace")

    for relative, needles in SOURCE_ASSERTIONS.items():
        text = texts.get(relative, "")
        missing = [needle for needle in needles if needle not in text]
        checks[f"source_contract:{relative}"] = {
            "required_fragments": needles,
            "missing_fragments": missing,
            "pass": not missing,
        }

    failures = [key for key, row in checks.items() if not row["pass"]]
    if failures:
        raise RuntimeError(f"source binding failed: {failures}")
    return checks, texts


def attended_prefill_pairs(cache_tokens: int) -> tuple[int, int]:
    fresh_tokens = PROMPT_TOKENS - cache_tokens
    sliding = sum(
        min(LOCAL["window"], cache_tokens + offset)
        for offset in range(1, fresh_tokens + 1)
    )
    global_pairs = (
        fresh_tokens * cache_tokens + fresh_tokens * (fresh_tokens + 1) // 2
    )
    return sliding, global_pairs


def exact_geometry(config: dict[str, Any]) -> dict[str, Any]:
    text = config["text_config"]
    assertions = {
        "architecture": config["architectures"] == ["Gemma4ForConditionalGeneration"],
        "layers": text["num_hidden_layers"] == 60,
        "layer_pattern": (
            len(text["layer_types"]) == 60
            and all(
                layer
                == ("full_attention" if (index + 1) % 6 == 0 else "sliding_attention")
                for index, layer in enumerate(text["layer_types"])
            )
        ),
        "hidden": text["hidden_size"] == HIDDEN,
        "intermediate": text["intermediate_size"] == INTERMEDIATE,
        "heads": text["num_attention_heads"] == 32,
        "local_geometry": text["head_dim"] == 256
        and text["num_key_value_heads"] == 16
        and text["sliding_window"] == 1024,
        "global_geometry": text["global_head_dim"] == 512
        and text["num_global_key_value_heads"] == 4
        and text["attention_k_eq_v"] is True,
        "tied_head": text["vocab_size"] == VOCAB
        and text["tie_word_embeddings"] is True,
    }
    if not all(assertions.values()):
        raise RuntimeError(f"geometry assertion failed: {assertions}")

    sliding_params = (
        HIDDEN * 16384
        + 8192 * HIDDEN
        + HIDDEN * 43008
        + INTERMEDIATE * HIDDEN
    )
    global_params = (
        HIDDEN * 20480
        + 16384 * HIDDEN
        + HIDDEN * 43008
        + INTERMEDIATE * HIDDEN
    )
    transformer_params = 50 * sliding_params + 10 * global_params
    tied_head_params = VOCAB * HIDDEN

    shape_rows = []
    for name, row in LINEAR_SHAPES.items():
        n_tiles = math.ceil(row["n"] / 128)
        shape_rows.append(
            {
                "name": name,
                **row,
                "parameters_per_layer": row["k"] * row["n"],
                "k_divisible_by_128": row["k"] % 128 == 0,
                "n_divisible_by_128": row["n"] % 128 == 0,
                "decode_m32_n_tiles": n_tiles,
                "decode_m32_nominal_waves_over_256_cus": n_tiles / 256,
                "verification_m384_nominal_waves_over_256_cus_at_m_tile_128": (
                    3 * n_tiles / 256
                ),
            }
        )

    return {
        "assertions": assertions,
        "linear_shapes": shape_rows,
        "sliding_parameters_per_layer": sliding_params,
        "global_parameters_per_layer": global_params,
        "executed_transformer_linear_parameters": transformer_params,
        "tied_head_parameters": tied_head_params,
        "transformer_flops_per_token": 2 * transformer_params,
        "phases": {
            "prefill": {
                "fresh_prompt_tokens_per_request": float(FRESH_PROMPT_TOKENS),
                "runtime_m": "chunked aggregate across c32; current FP8 consumer is torch._scaled_mm",
            },
            "ordinary_decode": {
                "m": 32,
                "steps_conservatively_counted": OUTPUT_TOKENS,
                "runtime_consumer": "torch._scaled_mm for FP8 transformer linears; BF16 dispatch_unquantized_gemm for tied head",
            },
            "target_verification": {
                "target_cycles": TARGET_VERIFICATION_CYCLES,
                "rows_per_request": TARGET_DEPTH,
                "transformer_m": CONCURRENCY * TARGET_DEPTH,
                "semantic_head_shape": "12 independent M32 tied-head calls per target cycle",
                "guard": "Added on top of all 358 ordinary decode steps, deliberately overcounting target work rather than borrowing NVIDIA acceptance throughput.",
            },
        },
    }


def operation_bindings() -> list[dict[str, Any]]:
    fp8_linear_consumer = (
        "Fp8PerTensorOnlineLinearMethod.process_weights_after_loading "
        "-> ops.scaled_fp8_quant -> ROCmFP8ScaledMMLinearKernel.apply_scaled_mm "
        "-> rocm_per_tensor_float_w8a8_scaled_mm_impl -> torch._scaled_mm"
    )
    return [
        {
            "operation": "QKV, O, gate/up, and down linears",
            "phases": ["prefill", "ordinary_decode_m32", "target_verification_m384"],
            "producer": "BF16 checkpoint LinearBase weights; online per-tensor scaled_fp8_quant",
            "representation": "gfx950 OCP E4M3FN weight and activation, scalar FP32 scales, BF16 output",
            "layout": "runtime weight KxN at scaled-mm boundary",
            "consumer": fp8_linear_consumer,
            "status": "bound_current_consumer",
            "evidence_type": "source_backed",
        },
        {
            "operation": "AITER per-token/preshuffled FP8 GEMM",
            "phases": ["not_selected_by_online_per_tensor_route"],
            "producer": "requires per-token activation and per-channel weight scales",
            "consumer": "gemm_a8w8_bpreshuffle or hipb_mm",
            "status": "explicitly_unsupported_for_selected_producer",
            "reason": "ROCm makes cutlass_fp8_supported false, so the online producer selects per-tensor activation and weight scales; all AITER per-token candidates reject that contract before ROCmFP8ScaledMMLinearKernel accepts it.",
            "evidence_type": "source_backed",
        },
        {
            "operation": "Hybrid prefill attention",
            "phases": ["prefill"],
            "producer": "Gemma4Attention Q/K/V after Q/K/V RMSNorm and RoPE",
            "representation": "BF16 Q/K/V with FP8 E4M3FN cache permitted",
            "consumer": "RocmAiterFlashAttentionImpl -> rocm_aiter_ops.flash_attn_varlen_func",
            "layout": "paged NHD cache, 50x head256/window1024 and 10x head512/global",
            "status": "bound_current_consumer",
            "evidence_type": "source_backed",
        },
        {
            "operation": "Hybrid decode and multi-token attention",
            "phases": ["ordinary_decode_m32", "target_verification_m384"],
            "producer": "paged FP8 E4M3FN K/V cache and BF16 query",
            "consumer": "AITER Triton unified_attention with GQA index, sliding-window pruning, FP32 softmax/output accumulator",
            "layout": "[num_blocks, block_size, num_kv_heads, head_size]",
            "status": "bound_current_consumer_source_only",
            "evidence_type": "source_backed",
        },
        {
            "operation": "KV conversion/write",
            "phases": ["prefill", "decode", "target_verification"],
            "producer": "normalized K/V",
            "representation": "gfx950 E4M3FN cache with layer scales",
            "consumer": "RocmAiterFlashAttentionImpl cache view and reshape/cache path",
            "status": "bound_current_consumer_source_only",
            "evidence_type": "source_backed",
        },
        {
            "operation": "RMSNorm, residual, and activation",
            "phases": ["all"],
            "producer": "BF16 hidden state",
            "representation": "BF16 I/O with FP32 reduction semantics",
            "consumer": "RMSNorm.forward_native -> ir.ops.rms_norm/fused_add_rms_norm; Gemma GELU-tanh activation",
            "status": "bound_current_consumer",
            "evidence_type": "source_backed",
        },
        {
            "operation": "Tied output projection",
            "phases": ["decode", "target_verification"],
            "producer": "BF16 tied VocabParallelEmbedding weight",
            "representation": "BF16; FP8Config does not provide an embedding method, so the tied head remains unquantized",
            "consumer": "UnquantizedEmbeddingMethod.apply -> dispatch_unquantized_gemm",
            "status": "bound_current_consumer_bf16_boundary",
            "evidence_type": "source_backed",
        },
    ]


def physical_estimate(
    transformer_params: int,
    head_params: int,
    *,
    fp8_math_efficiency: float = 0.20,
    bf16_math_efficiency: float = 0.20,
    hbm_efficiency: float = 0.30,
    launch_us: float = 3.0,
    scheduler_reserve_s: float = 0.040,
) -> dict[str, Any]:
    fp8_peak = 5_000e12
    bf16_peak = 2_500e12
    hbm_bandwidth = 8_000e9
    effective_hbm = hbm_bandwidth * hbm_efficiency

    pref_535 = attended_prefill_pairs(535)
    pref_536 = attended_prefill_pairs(536)
    mix = ((Fraction(822, 1000), pref_535), (Fraction(178, 1000), pref_536))
    sliding_prefill_pairs = sum(weight * row[0] for weight, row in mix)
    global_prefill_pairs = sum(weight * row[1] for weight, row in mix)
    prefill_attention_flops = (
        LOCAL["layers"]
        * 4
        * LOCAL["q_heads"]
        * LOCAL["head_dim"]
        * sliding_prefill_pairs
        + GLOBAL["layers"]
        * 4
        * GLOBAL["q_heads"]
        * GLOBAL["head_dim"]
        * global_prefill_pairs
    )

    contexts = range(PROMPT_TOKENS, PROMPT_TOKENS + OUTPUT_TOKENS)
    decode_attention_flops = sum(
        LOCAL["layers"]
        * 4
        * LOCAL["q_heads"]
        * LOCAL["head_dim"]
        * min(LOCAL["window"], context)
        + GLOBAL["layers"]
        * 4
        * GLOBAL["q_heads"]
        * GLOBAL["head_dim"]
        * context
        for context in contexts
    )
    fp8_kv_bytes_per_token_layer = 4096
    decode_kv_read_bytes = sum(
        fp8_kv_bytes_per_token_layer
        * (
            LOCAL["layers"] * min(LOCAL["window"], context)
            + GLOBAL["layers"] * context
        )
        for context in contexts
    )

    # Separate non-GEMM traffic: four layer norms, two residual updates, Q/K/V
    # norms, RoPE, gated activation, and four dynamic-FP8 input conversions.
    norm_and_residual_bytes = 28 * HIDDEN
    sliding_extra_bytes = (
        4 * (8192 + 4096 + 4096)
        + 4 * (8192 + 4096)
        + 6 * INTERMEDIATE
        + 3 * (HIDDEN + 8192 + HIDDEN + INTERMEDIATE)
    )
    global_extra_bytes = (
        4 * (16384 + 2048 + 2048)
        + 4 * (16384 + 2048)
        + 6 * INTERMEDIATE
        + 3 * (HIDDEN + 16384 + HIDDEN + INTERMEDIATE)
    )
    non_gemm_bytes_per_token = (
        LOCAL["layers"] * (norm_and_residual_bytes + sliding_extra_bytes)
        + GLOBAL["layers"] * (norm_and_residual_bytes + global_extra_bytes)
    )

    prefill_chunks = math.ceil(
        CONCURRENCY * float(FRESH_PROMPT_TOKENS) / 8192
    )
    kernels_per_layer = 18
    launch_count_per_request = (
        prefill_chunks * 60 * kernels_per_layer / CONCURRENCY
        + OUTPUT_TOKENS * 60 * kernels_per_layer / CONCURRENCY
        + TARGET_VERIFICATION_CYCLES
        * (60 * kernels_per_layer + TARGET_DEPTH)
        / CONCURRENCY
    )

    verification_context = PROMPT_TOKENS + OUTPUT_TOKENS - 1
    verification_attention_flops = (
        TARGET_VERIFICATION_CYCLES
        * TARGET_DEPTH
        * (
            LOCAL["layers"]
            * 4
            * LOCAL["q_heads"]
            * LOCAL["head_dim"]
            * LOCAL["window"]
            + GLOBAL["layers"]
            * 4
            * GLOBAL["q_heads"]
            * GLOBAL["head_dim"]
            * verification_context
        )
    )
    # Twelve verification rows share each request's K/V tiles within a target
    # cycle; count one compulsory cache read per cycle and no L2 credit.
    verification_kv_read_bytes = (
        TARGET_VERIFICATION_CYCLES
        * fp8_kv_bytes_per_token_layer
        * (
            LOCAL["layers"] * LOCAL["window"]
            + GLOBAL["layers"] * verification_context
        )
    )

    line_items = [
        {
            "name": "prefill_fp8_transformer_linears",
            "resource": "dense_fp8_matrix_core",
            "seconds_per_request": (
                2
                * transformer_params
                * float(FRESH_PROMPT_TOKENS)
                / (fp8_peak * fp8_math_efficiency)
            ),
            "numerator_flops": 2
            * transformer_params
            * float(FRESH_PROMPT_TOKENS),
            "rule": "FLOPs / (5 PFLOP/s * 20%); no NVIDIA timing transfer",
        },
        {
            "name": "prefill_hybrid_attention",
            "resource": "max_bf16_tensor_or_compulsory_fp8_kv_hbm",
            "seconds_per_request": max(
                float(prefill_attention_flops)
                / (bf16_peak * bf16_math_efficiency),
                60
                * PROMPT_TOKENS
                * fp8_kv_bytes_per_token_layer
                / effective_hbm,
            ),
            "numerator_flops": int(prefill_attention_flops),
            "compulsory_unique_kv_bytes": 60
            * PROMPT_TOKENS
            * fp8_kv_bytes_per_token_layer,
            "rule": "max(compute, unique K/V HBM); K/V tiles are not charged once per query pair",
        },
        {
            "name": "prefill_norm_activation_conversion",
            "resource": "hbm",
            "seconds_per_request": (
                non_gemm_bytes_per_token
                * float(FRESH_PROMPT_TOKENS)
                / effective_hbm
            ),
            "bytes": non_gemm_bytes_per_token * float(FRESH_PROMPT_TOKENS),
            "rule": "separate unfused bytes at 30% HBM; GEMM weight/input/output traffic is not charged again",
        },
        {
            "name": "ordinary_decode_fp8_transformer_linears",
            "resource": "max_fp8_tensor_or_weight_hbm",
            "seconds_per_request": max(
                2 * transformer_params * OUTPUT_TOKENS / fp8_peak,
                transformer_params
                * OUTPUT_TOKENS
                / CONCURRENCY
                / effective_hbm,
            ),
            "weight_bytes": transformer_params
            * OUTPUT_TOKENS
            / CONCURRENCY,
            "rule": "one FP8 weight stream per c32 step, zero L2 credit; 30% HBM absorbs sub-wave N tiles/split scheduling",
        },
        {
            "name": "ordinary_decode_bf16_tied_head",
            "resource": "max_bf16_tensor_or_weight_hbm",
            "seconds_per_request": max(
                2 * head_params * OUTPUT_TOKENS / bf16_peak,
                2
                * head_params
                * OUTPUT_TOKENS
                / CONCURRENCY
                / effective_hbm,
            ),
            "weight_bytes": 2
            * head_params
            * OUTPUT_TOKENS
            / CONCURRENCY,
            "rule": "BF16 tied weight streamed once per c32 step",
        },
        {
            "name": "ordinary_decode_attention_kv",
            "resource": "max_bf16_tensor_or_fp8_kv_hbm",
            "seconds_per_request": max(
                decode_attention_flops / (bf16_peak * bf16_math_efficiency),
                decode_kv_read_bytes / effective_hbm,
            ),
            "numerator_flops": decode_attention_flops,
            "fp8_kv_read_bytes": decode_kv_read_bytes,
            "rule": "358 exact context positions, zero L2 credit",
        },
        {
            "name": "ordinary_decode_norm_activation_conversion",
            "resource": "hbm",
            "seconds_per_request": (
                non_gemm_bytes_per_token * OUTPUT_TOKENS / effective_hbm
            ),
            "bytes": non_gemm_bytes_per_token * OUTPUT_TOKENS,
            "rule": "separate non-GEMM bytes",
        },
        {
            "name": "target_verification_m384_transformer",
            "resource": "max_fp8_tensor_or_weight_hbm",
            "seconds_per_request": max(
                TARGET_VERIFICATION_CYCLES
                * TARGET_DEPTH
                * 2
                * transformer_params
                / (fp8_peak * fp8_math_efficiency),
                TARGET_VERIFICATION_CYCLES
                * transformer_params
                / CONCURRENCY
                / effective_hbm,
            ),
            "target_cycles": TARGET_VERIFICATION_CYCLES,
            "m": CONCURRENCY * TARGET_DEPTH,
            "rule": "15 M384 target passes added after all 358 ordinary decode steps",
        },
        {
            "name": "target_verification_bf16_tied_head",
            "resource": "max_bf16_tensor_or_repeated_weight_hbm",
            "seconds_per_request": max(
                TARGET_VERIFICATION_CYCLES
                * TARGET_DEPTH
                * 2
                * head_params
                / bf16_peak,
                TARGET_VERIFICATION_CYCLES
                * TARGET_DEPTH
                * 2
                * head_params
                / CONCURRENCY
                / effective_hbm,
            ),
            "rule": "preserve 12 independent M32 semantic head calls per cycle; no grouped-weight reuse credited",
        },
        {
            "name": "target_verification_attention_kv",
            "resource": "max_bf16_tensor_or_fp8_kv_hbm",
            "seconds_per_request": max(
                verification_attention_flops
                / (bf16_peak * bf16_math_efficiency),
                verification_kv_read_bytes / effective_hbm,
            ),
            "numerator_flops": verification_attention_flops,
            "fp8_kv_read_bytes": verification_kv_read_bytes,
            "rule": "12 query rows share one compulsory K/V read per request/cycle; no L2 credit",
        },
        {
            "name": "launch_reserve",
            "resource": "device_launch_latency",
            "seconds_per_request": launch_count_per_request * launch_us * 1e-6,
            "launch_count_per_request": launch_count_per_request,
            "microseconds_per_launch": launch_us,
            "rule": "18 launches/layer plus target head calls; intentionally does not credit graph launch elision",
        },
        {
            "name": "scheduler_service_reserve",
            "resource": "host_and_service",
            "seconds_per_request": scheduler_reserve_s,
            "rule": "fixed inferred reserve; must be replaced by endpoint evidence",
        },
    ]

    total = sum(row["seconds_per_request"] for row in line_items)
    component = sum(
        row["seconds_per_request"]
        for row in line_items
        if row["name"] not in {"launch_reserve", "scheduler_service_reserve"}
    )
    return {
        "assumptions": {
            "fp8_dense_peak_tflops_vendor_reported": 5000,
            "bf16_dense_peak_tflops_vendor_reported": 2500,
            "hbm_bandwidth_gb_s_vendor_reported": 8000,
            "fp8_math_efficiency_inferred_conservative": fp8_math_efficiency,
            "bf16_math_efficiency_inferred_conservative": bf16_math_efficiency,
            "hbm_efficiency_inferred_conservative": hbm_efficiency,
            "l2_credit_bytes": 0,
            "launch_us_inferred": launch_us,
            "scheduler_service_reserve_s_inferred": scheduler_reserve_s,
            "nvidia_throughput_or_efficiency_transferred": False,
        },
        "prefill_pair_geometry": {
            "cache_535_weight": 0.822,
            "cache_536_weight": 0.178,
            "sliding_pairs_per_layer": float(sliding_prefill_pairs),
            "global_pairs_per_layer": float(global_prefill_pairs),
        },
        "non_gemm_bytes_per_token": non_gemm_bytes_per_token,
        "line_items": line_items,
        "component_seconds_per_request": component,
        "launch_plus_service_reserve_seconds_per_request": total - component,
        "conservative_screen_seconds_per_request": total,
    }


def efficiency_threshold(
    transformer_params: int,
    head_params: int,
    field: str,
    low: float,
    high: float,
) -> float:
    for _ in range(80):
        middle = (low + high) / 2
        kwargs = {field: middle}
        result = physical_estimate(transformer_params, head_params, **kwargs)
        if result["conservative_screen_seconds_per_request"] <= BASE_HURDLE_S:
            high = middle
        else:
            low = middle
    return high


def memory_capacity(
    geometry: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    # Start from the full-model BF16 metadata and credit only the unique
    # transformer linears that online quantization halves. Add the duplicated
    # global K-as-V execution bytes explicitly.
    bf16_metadata_bytes = 62_546_177_752
    duplicated_global_v_bytes_fp8 = 10 * HIDDEN * (GLOBAL["kv_heads"] * GLOBAL["head_dim"])
    unique_transformer_params = (
        geometry["executed_transformer_linear_parameters"]
        - duplicated_global_v_bytes_fp8
    )
    static_bytes = (
        bf16_metadata_bytes
        - unique_transformer_params
        + duplicated_global_v_bytes_fp8
    )
    bf16_resident_kv_per_request = 764_641_280
    fp8_kv_c32 = bf16_resident_kv_per_request * CONCURRENCY // 2
    target_extra_fp8_kv = (
        TARGET_DEPTH
        * CONCURRENCY
        * 60
        * 4096
    )
    source_bound_bytes = static_bytes + fp8_kv_c32 + target_extra_fp8_kv
    conservative_two_x_envelope = 2 * source_bound_bytes
    device_bytes = 288_000_000_000
    return {
        "full_model_bf16_metadata_bytes": bf16_metadata_bytes,
        "online_fp8_static_model_bytes_upper_bound": static_bytes,
        "fp8_resident_kv_c32_bytes": fp8_kv_c32,
        "target_depth_12_extra_fp8_kv_bytes": target_extra_fp8_kv,
        "source_bound_resident_bytes": source_bound_bytes,
        "conservative_two_x_runtime_fragmentation_envelope_bytes": conservative_two_x_envelope,
        "mi355x_decimal_capacity_bytes": device_bytes,
        "two_x_envelope_margin_bytes": device_bytes - conservative_two_x_envelope,
        "fits_with_two_x_envelope": conservative_two_x_envelope < device_bytes,
        "interconnect_required": False,
        "topology": "single MI355X TP1; 256 CUs across eight XCDs; no peer or host traffic credited",
        "config_architecture": config["architectures"][0],
    }


def build_artifact(
    source_checks: dict[str, Any],
    source_bindings: dict[str, Any],
    config: dict[str, Any],
    inventory: dict[str, Any],
    prices: dict[str, Any],
) -> dict[str, Any]:
    geometry = exact_geometry(config)
    transformer_params = geometry["executed_transformer_linear_parameters"]
    head_params = geometry["tied_head_parameters"]
    estimate = physical_estimate(transformer_params, head_params)
    memory = memory_capacity(geometry, config)

    mi355x = next(row for row in inventory["accelerators"] if row["id"] == "amd-mi355x")
    price = next(row for row in prices["accelerators"] if row["id"] == "amd-mi355x")
    hardware_assertions = {
        "compute_units": mi355x["execution"]["compute_units"] == 256,
        "capacity": mi355x["memory"]["capacity_gb"] == 288,
        "bandwidth": mi355x["memory"]["bandwidth_gb_s"] == 8000,
        "l2": mi355x["cache"]["last_level_mb"] == 256,
        "bf16_peak": mi355x["peak_math"]["bf16_tflops"] == 2500,
        "fp8_peak": mi355x["peak_math"]["fp8_tflops"] == 5000,
        "planning_price": price["production_planning_usd_per_gpu_hour"] == 2.6,
        "price_range": price["production_evidence_range_usd_per_gpu_hour"]
        == [2.4, 2.75],
    }
    if not all(hardware_assertions.values()):
        raise RuntimeError(f"hardware assertion failed: {hardware_assertions}")

    screen_s = estimate["conservative_screen_seconds_per_request"]
    hurdle_results = {
        label: {
            "hurdle_seconds_per_request": hurdle,
            "screen_seconds_per_request": screen_s,
            "margin_seconds_per_request": hurdle - screen_s,
            "pass": screen_s <= hurdle,
        }
        for label, hurdle in PRICE_HURDLES.items()
    }
    base_pass = hurdle_results["production_base_2_60"]["pass"]
    source_pass = all(row["pass"] for row in source_checks.values())
    terminal = (
        "source_complete_mi355x_candidate"
        if source_pass and base_pass and memory["fits_with_two_x_envelope"]
        else "typed_none"
    )

    calculator_path = Path(__file__).resolve()
    component_gate = (
        BASE_HURDLE_S
        - estimate["launch_plus_service_reserve_seconds_per_request"]
    )
    return {
        "schema_version": 1,
        "terminal": terminal,
        "classification": terminal,
        "generated_from_observation_utc": source_bindings["observed_at_utc"],
        "scope": {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "mode": "text_only_non_reasoning",
            "workload": {
                "concurrency": CONCURRENCY,
                "prompt_tokens": PROMPT_TOKENS,
                "output_tokens": OUTPUT_TOKENS,
                "cache_fraction": float(CACHE_FRACTION),
                "fresh_prompt_tokens": float(FRESH_PROMPT_TOKENS),
                "target_depth": TARGET_DEPTH,
                "target_verification_cycles_conservatively_added": TARGET_VERIFICATION_CYCLES,
            },
            "hardware": "one AMD Instinct MI355X, TP1",
            "representation": "online per-tensor OCP E4M3FN transformer linears, FP8 E4M3FN KV, BF16 tied embedding/head and normalization outputs",
        },
        "identity": {
            "config": {
                "path": str(CONFIG_PATH),
                "sha256": sha256(CONFIG_PATH),
                "expected_sha256": CONFIG_SHA256,
                "pass": sha256(CONFIG_PATH) == CONFIG_SHA256,
            },
            "calculator": {
                "path": str(calculator_path),
                "sha256": sha256(calculator_path),
            },
            "source_bindings": {
                "path": str(BINDINGS_PATH),
                "sha256": sha256(BINDINGS_PATH),
            },
            "accelerator_inventory": {
                "path": str(INVENTORY_PATH),
                "sha256": sha256(INVENTORY_PATH),
            },
            "gpu_prices": {
                "path": str(PRICE_PATH),
                "sha256": sha256(PRICE_PATH),
            },
            "source_checks": source_checks,
            "hardware_assertions": hardware_assertions,
        },
        "geometry": geometry,
        "runtime_operation_bindings": operation_bindings(),
        "memory_and_topology": memory,
        "physical_cost_screen": {
            **estimate,
            "hurdles": hurdle_results,
            "stress_thresholds_holding_other_assumptions_fixed": {
                "minimum_fp8_math_efficiency_to_clear_base": efficiency_threshold(
                    transformer_params,
                    head_params,
                    "fp8_math_efficiency",
                    0.01,
                    0.50,
                ),
                "minimum_bf16_math_efficiency_to_clear_base": efficiency_threshold(
                    transformer_params,
                    head_params,
                    "bf16_math_efficiency",
                    0.01,
                    0.50,
                ),
                "minimum_hbm_efficiency_to_clear_base": efficiency_threshold(
                    transformer_params,
                    head_params,
                    "hbm_efficiency",
                    0.05,
                    0.90,
                ),
            },
            "evidence_boundary": "Analytical/inferred screening envelope. Vendor peaks are denominators only; no NVIDIA throughput, MI355X endpoint, quality, reliability, power, or deployability is claimed.",
        },
        "highest_uncertainty_discriminator": {
            "question": "Does the exact BF16 production checkpoint reach a current gfx950 FP8 GEMM and hybrid-attention consumer with its actual scale/layout contract?",
            "result": "pass_source_dispatch_with_explicit_aiter_linear_boundary",
            "observations": [
                "Online BF16 weights are materialized and quantized by scaled_fp8_quant.",
                "ROCm disables the CUTLASS per-token choice, so online FP8 uses per-tensor activation and weight scales.",
                "AITER per-token/preshuffled candidates reject that scale contract; ROCmFP8ScaledMMLinearKernel accepts it.",
                "At M32 and M384 the skinny M<=4 branch is false, so the first decision-bearing GEMM consumer is torch._scaled_mm/hipBLASLt.",
                "Hybrid attention reaches AITER flash/unified attention with sliding-window, GQA, and FP8 cache source support.",
                "The tied embedding/head remains BF16 and reaches the unquantized GEMM dispatcher.",
            ],
            "execution_type": "executed_local_cpu_source_discriminator",
            "pass": source_pass,
        },
        "later_exact_shape_falsifier": {
            "status": "ready_but_not_authorized_in_this_zero_spend_project",
            "hardware": "one MI355X/gfx950 TP1",
            "source": {
                "vllm_commit": source_bindings["repositories"]["vllm"]["commit"],
                "aiter_commit": source_bindings["repositories"]["aiter"]["commit"],
            },
            "arms": [
                "Online-quantize BF16 synthetic weights through Fp8PerTensorOnlineLinearMethod and run every exact transformer shape at M32 and M384 through the selected ROCm consumer.",
                "Run local head256/GQA2/window1024 and global head512/GQA8/context4571 AITER FP8-KV attention at decode M32 and verification M384.",
                "Run the BF16 [32,5376]x[5376,262144] tied-head baseline, preserving 12 independent calls for each target cycle.",
            ],
            "oracle": "BF16 torch reference; finite complete output, argmax identity for head fixtures, relative-L2 <=0.02 and cosine >=0.995 for FP8 linears/attention; no fallback.",
            "timing": "warm profiler-off p50/p95 with compilation excluded; aggregate exact counts from this artifact",
            "numerical_gate": {
                "component_seconds_per_request_max": component_gate,
                "launch_plus_service_reserve_seconds_per_request": estimate[
                    "launch_plus_service_reserve_seconds_per_request"
                ],
                "whole_request_hurdle_seconds_per_request": BASE_HURDLE_S,
            },
            "predicted_counter_change": {
                "prefill_and_m384": ">=20% dense FP8/BF16 matrix peak on compulsory work",
                "decode_weight_stream": ">=30% of 8 TB/s aggregate HBM with zero L2 credit in the model",
                "global_attention": "head512 FP32 accumulator compiles without decision-bearing spills/fallback; if register/LDS pressure pushes the aggregate over the gate, the route is falsified",
            },
            "strongest_supported_baseline": "Pinned vLLM ROCm per-tensor torch._scaled_mm plus AITER flash/unified attention; no NVIDIA timing baseline.",
            "wall_clock_bound_minutes": 20,
            "maximum_provider_spend_usd_if_later_authorized_at_2_95_per_hour": 2.95
            * 20
            / 60,
            "current_authorized_provider_spend_usd": 0.0,
        },
        "unsupported_and_unmeasured_boundaries": [
            "No MI355X kernel or endpoint executed; source completeness is not measurement readiness.",
            "AITER per-token/preshuffled FP8 linear kernels are not reachable from the selected online per-tensor producer without changing the representation contract.",
            "The exact global head512 AITER compile/resource behavior is source-supported but unmeasured and is the first GPU tripwire.",
            "The tied embedding/head remains BF16; this screen does not invent an unsupported FP8 tied-weight embedding path.",
            "The analytical estimate deliberately counts all 358 ordinary decode steps plus 15 depth-12 target passes, but it does not prove exact vLLM n-gram integration or accepted-token behavior.",
            "No GPQA-Diamond, TauBench, checkpoint-quality, feature, reliability, power, or production-capacity claim is made.",
            "The $2.75/hour and $2.95/hour sensitivity hurdles do not clear this conservative screen; only the $2.40 and $2.60 production cases do.",
        ],
        "decision": {
            "result": terminal,
            "base_rate_pass": base_pass,
            "source_dispatch_pass": source_pass,
            "memory_fit_pass": memory["fits_with_two_x_envelope"],
            "interpretation": (
                "A content-bound current ROCm route exists and its deliberately conservative, zero-L2, no-NVIDIA-transfer physical screen is below the $2.60/hour hurdle. Preserve it as one bounded later MI355X exact-shape falsifier, not as a deployment or throughput claim."
                if terminal == "source_complete_mi355x_candidate"
                else "The current source or conservative physical screen does not clear the base production hurdle."
            ),
        },
        "prohibited_actions_respected": [
            "no GPU claim",
            "no accelerator execution",
            "no provider contact or mutation",
            "no wait on the H100 owner",
            "zero provider spend",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-root", type=Path)
    parser.add_argument("--aiter-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bindings = load_json(BINDINGS_PATH)
    config = load_json(CONFIG_PATH)
    inventory = load_json(INVENTORY_PATH)
    prices = load_json(PRICE_PATH)

    if bool(args.vllm_root) != bool(args.aiter_root):
        raise SystemExit("--vllm-root and --aiter-root must be supplied together")

    if args.vllm_root:
        source_checks, _ = verify_sources(
            bindings, args.vllm_root.resolve(), args.aiter_root.resolve()
        )
    else:
        with tempfile.TemporaryDirectory(prefix="mi355x-source-") as temp:
            temp_root = Path(temp)
            roots = {}
            for repo_name, repo in bindings["repositories"].items():
                roots[repo_name] = fetch_repository(
                    temp_root / repo_name,
                    repo["url"],
                    repo["commit"],
                    sorted(repo["files"]),
                )
            source_checks, _ = verify_sources(
                bindings, roots["vllm"], roots["aiter"]
            )

    artifact = build_artifact(
        source_checks, bindings, config, inventory, prices
    )
    atomic_json(args.output.resolve(), artifact)
    print(
        json.dumps(
            {
                "terminal": artifact["terminal"],
                "screen_seconds_per_request": artifact["physical_cost_screen"][
                    "conservative_screen_seconds_per_request"
                ],
                "base_hurdle_seconds_per_request": BASE_HURDLE_S,
                "output": str(args.output.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
