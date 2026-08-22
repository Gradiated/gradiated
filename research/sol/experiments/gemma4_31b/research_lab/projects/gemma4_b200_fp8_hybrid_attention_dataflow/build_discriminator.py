from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
PROJECTS = LAB / "projects"

EXPECTED_HASHES = {
    "comparator": "2873d1b8d311153e903aeb525d59cd61620ecc1129120cfc81e2ec1f5d68ae86",
    "residual_exclusion": "59a91ecd82e55c388f02b3a948c6650d8f260c0d1d92202513059441d9c32415",
    "cross_operator_exclusion": "777e1e54f10a2a26a6b4dcf08518a2a994bce35edb8988d2906d992fba592506",
    "config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    "stock_gemma4": "e16b28577c7cdca4876d26636564ed411fc7ce4a25b724456ee906d8129eed20",
    "candidate_gemma4": "9d5ad4b96bc439d6c9814250bf532c6be5aaeecde890da40682bd251d16ad11f",
}

PATHS = {
    "comparator": PROJECTS
    / "gemma4_b200_dynamic_fp8_endpoint"
    / "artifacts"
    / "b200-dynamic-fp8-repair2-20260728t1517z"
    / "FINAL_TERMINAL.json",
    "residual_exclusion": PROJECTS
    / "gemma4_b200_fp8_residual_hotpath"
    / "B200_FP8_RESIDUAL_DISCRIMINATOR.json",
    "cross_operator_exclusion": PROJECTS
    / "gemma4_b200_fp8_cross_operator_executor"
    / "B200_FP8_CROSS_OPERATOR_DISCRIMINATOR.json",
    "config": PROJECT / "inputs" / "config.json",
    "stock_gemma4": PROJECT / "inputs" / "pinned_runtime" / "gemma4.py",
    "candidate_gemma4": PROJECT / "candidate" / "gemma4.py",
    "patch": PROJECT / "GEMMA4_K_EQ_V_QK_PROJECTION.patch",
    "component_runner": PROJECT / "b200_k_eq_v_component.py",
}

SOURCE_PATHS = {
    "vllm/model_executor/models/gemma4.py": PATHS["stock_gemma4"],
    "vllm/model_executor/layers/linear.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "model_executor"
    / "layers"
    / "linear.py",
    "vllm/config/cache.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "config"
    / "cache.py",
    "vllm/platforms/cuda.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "platforms"
    / "cuda.py",
    "vllm/v1/core/kv_cache_utils.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "v1"
    / "core"
    / "kv_cache_utils.py",
    "vllm/v1/kv_cache_interface.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "v1"
    / "kv_cache_interface.py",
    "vllm/v1/worker/gpu_model_runner.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "v1"
    / "worker"
    / "gpu_model_runner.py",
    "vllm/v1/attention/backends/flashinfer.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "v1"
    / "attention"
    / "backends"
    / "flashinfer.py",
    "vllm/v1/attention/backends/flash_attn.py": PROJECT
    / "inputs"
    / "pinned_runtime"
    / "v1"
    / "attention"
    / "backends"
    / "flash_attn.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_inputs() -> dict[str, dict]:
    loaded = {}
    for name, expected in EXPECTED_HASHES.items():
        observed = sha256(PATHS[name])
        require(observed == expected, f"{name}: expected {expected}, observed {observed}")
        if PATHS[name].suffix == ".json":
            loaded[name] = load_json(PATHS[name])

    stock = PATHS["stock_gemma4"].read_text()
    candidate = PATHS["candidate_gemma4"].read_text()
    compile(candidate, str(PATHS["candidate_gemma4"]), "exec")
    required_stock = [
        "yield name.replace(\"k_proj\", \"v_proj\"), weight.clone()",
        "q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size]",
        "self.qkv_proj = QKVParallelLinear(",
    ]
    required_candidate = [
        "self.compute_k_eq_v_once = use_k_eq_v and tp_size == 1",
        "self.qk_proj = MergedColumnParallelLinear(",
        "q, k = qk.split([self.q_size, self.kv_size], dim=-1)",
        "v = k",
        "(\"qk_proj\", \"k_proj\", 1)",
        "if get_tensor_model_parallel_world_size() != 1:",
    ]
    for fragment in required_stock:
        require(fragment in stock, f"missing stock source fragment: {fragment}")
    for fragment in required_candidate:
        require(fragment in candidate, f"missing candidate source fragment: {fragment}")

    with tempfile.TemporaryDirectory(dir=PROJECT) as tmp:
        root = Path(tmp)
        target = root / "vllm" / "model_executor" / "models" / "gemma4.py"
        target.parent.mkdir(parents=True)
        shutil.copy2(PATHS["stock_gemma4"], target)
        subprocess.run(
            ["patch", "--batch", "--forward", "-p1", "-i", str(PATHS["patch"])],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        require(
            sha256(target) == EXPECTED_HASHES["candidate_gemma4"],
            "patch output does not match candidate source",
        )
    return loaded


def build() -> dict:
    loaded = verify_inputs()
    config = loaded["config"]["text_config"]
    comparator = loaded["comparator"]
    residual = loaded["residual_exclusion"]
    cross = loaded["cross_operator_exclusion"]

    layers = config["layer_types"]
    local_indices = [i for i, layer_type in enumerate(layers) if layer_type == "sliding_attention"]
    global_indices = [i for i, layer_type in enumerate(layers) if layer_type == "full_attention"]
    require(len(layers) == config["num_hidden_layers"] == 60, "layer count mismatch")
    require(len(local_indices) == 50 and len(global_indices) == 10, "hybrid count mismatch")
    require(global_indices == list(range(5, 60, 6)), "five-local/one-global order mismatch")
    require(config["attention_k_eq_v"] is True, "global K=V contract absent")
    require(config["num_kv_shared_layers"] == 0, "cross-layer KV sharing changes scope")

    concurrency = 32
    prompt_tokens = 4214
    decode_steps = 358
    m = concurrency
    hidden = config["hidden_size"]
    q_heads = config["num_attention_heads"]
    local_kv_heads = config["num_key_value_heads"]
    global_kv_heads = config["num_global_key_value_heads"]
    local_dim = config["head_dim"]
    global_dim = config["global_head_dim"]
    window = config["sliding_window"]
    dtype_bytes = 2
    base_block = 16

    local_q = q_heads * local_dim
    local_kv = local_kv_heads * local_dim
    global_q = q_heads * global_dim
    global_kv = global_kv_heads * global_dim
    stock_global_qkv = global_q + 2 * global_kv
    candidate_global_qk = global_q + global_kv
    require((local_q, local_kv) == (8192, 4096), "local width mismatch")
    require((global_q, global_kv) == (16384, 2048), "global width mismatch")
    require(stock_global_qkv == 20480 and candidate_global_qk == 18432, "global output mismatch")

    local_bytes_per_token_layer = 2 * local_kv_heads * local_dim * dtype_bytes
    global_bytes_per_token_layer = 2 * global_kv_heads * global_dim * dtype_bytes
    local_block = base_block
    global_block = base_block * local_bytes_per_token_layer // global_bytes_per_token_layer
    local_page_bytes = local_block * local_bytes_per_token_layer
    global_page_bytes = global_block * global_bytes_per_token_layer
    require(local_page_bytes == global_page_bytes == 262144, "page unification mismatch")

    seq_lens = list(range(prompt_tokens, prompt_tokens + decode_steps))
    local_pages = [
        (seq_len - 1) // local_block - (seq_len - window) // local_block + 1
        for seq_len in seq_lens
    ]
    global_pages = [math.ceil(seq_len / global_block) for seq_len in seq_lens]

    local_calls = len(local_indices) * decode_steps
    global_calls = len(global_indices) * decode_steps
    total_calls = local_calls + global_calls
    local_kv_reads = (
        len(local_indices)
        * decode_steps
        * concurrency
        * window
        * local_bytes_per_token_layer
    )
    global_kv_reads = (
        len(global_indices)
        * concurrency
        * sum(seq_lens)
        * global_bytes_per_token_layer
    )
    local_kv_writes = (
        len(local_indices)
        * decode_steps
        * concurrency
        * local_bytes_per_token_layer
    )
    global_kv_writes = (
        len(global_indices)
        * decode_steps
        * concurrency
        * global_bytes_per_token_layer
    )
    require(
        local_kv_reads + global_kv_reads
        == residual["non_overlapping_accounting"]["categories"][4][
            "logical_kv_read_bytes_lower_bound"
        ],
        "KV read accounting does not reconcile with exclusion artifact",
    )
    require(
        local_kv_writes + global_kv_writes
        == residual["non_overlapping_accounting"]["categories"][4][
            "logical_kv_write_bytes"
        ],
        "KV write accounting does not reconcile with exclusion artifact",
    )

    removed_weight_per_call = hidden * global_kv
    removed_output_per_call = m * global_kv * dtype_bytes
    removed_flops_per_call = 2 * m * hidden * global_kv
    removed_weight_batch = global_calls * removed_weight_per_call
    removed_output_batch = global_calls * removed_output_per_call
    removed_flops_batch = global_calls * removed_flops_per_call
    removed_logical_batch = removed_weight_batch + removed_output_batch
    transformer_weight_bytes = residual["non_overlapping_accounting"]["categories"][3][
        "compulsory_weight_bytes_lower_bound"
    ]

    service = comparator["candidate"]["service_seconds_per_request"]
    target = 0.500119281574996
    gap = service - target
    hbm_sensitivity_batch = removed_logical_batch / 8_000_000_000_000

    source_hashes = {name: sha256(path) for name, path in SOURCE_PATHS.items()}
    implementation = {
        "type": "hash_bound_production_source_patch",
        "semantic_class": "semantics_preserving_tp1_exact_geometry",
        "stock_source": "inputs/pinned_runtime/gemma4.py",
        "stock_sha256": sha256(PATHS["stock_gemma4"]),
        "candidate_source": "candidate/gemma4.py",
        "candidate_sha256": sha256(PATHS["candidate_gemma4"]),
        "patch": "GEMMA4_K_EQ_V_QK_PROJECTION.patch",
        "patch_sha256": sha256(PATHS["patch"]),
        "generator": "build_discriminator.py",
        "generator_sha256": sha256(Path(__file__)),
        "component_runner": "b200_k_eq_v_component.py",
        "component_runner_sha256": sha256(PATHS["component_runner"]),
        "source_path": "Gemma4Attention.forward(hidden_states) -> qk_proj -> unchanged q_norm/k_norm/v_norm/rotary_emb -> unchanged Attention.forward",
        "checkpoint_path": "Gemma4ForCausalLM.load_weights._weight_iterator -> Gemma4Model.load_weights -> qk_proj shards [q,k]",
        "first_decision_bearing_consumer": "vllm.model_executor.layers.attention.Attention.forward",
        "fallback": "TP!=1 retains stock QKVParallelLinear and materialized V",
        "dispatcher_modified": False,
        "rmsnorm_fp8_fusion_modified": False,
        "offline_checks": {
            "exact_stock_hash": True,
            "patch_apply": "passed",
            "candidate_python_compile": "passed",
            "candidate_matches_patch_output": True,
            "exact_config_geometry": "passed",
        },
        "target_execution": "not_run_scope_forbids_cuda_and_bench_claim",
    }

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "classification": "hash_bound_source_complete_global_k_eq_v_candidate_unmeasured",
        "decision": "Retain the TP=1 global K=V projection-elision patch for one B200 component discriminator. It deletes exact recurring work without touching attention/KV semantics, but the HBM-only sensitivity is small and no endpoint gain is claimed.",
        "scope": {
            "researcher_profile": "deep",
            "gpu_claimed": False,
            "provider_operations": False,
            "endpoint_requests_submitted": False,
            "cuda_executed": False,
            "scientific_sample_consumed": False,
            "actual_spend_usd": 0.0,
        },
        "authoritative_identities": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "config_path": "inputs/config.json",
                "config_sha256": sha256(PATHS["config"]),
            },
            "runtime": {
                "image": "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79",
                "vllm_commit": "6d4a8e6d204a9b2827544003b26321fff62923da",
                "vllm_version": "0.19.1.dev6+g6d4a8e6d2",
                "source_hashes": source_hashes,
                "source_note": "gemma4.py is copied from the immutable runtime image; supporting files are immutable raw snapshots at the pinned vLLM commit.",
            },
            "hardware": {
                "id": "nvidia-b200-sxm",
                "programming_target": "sm_100",
                "hbm_bytes_per_second_vendor_prior": 8_000_000_000_000,
                "fp8_flops_per_second_vendor_prior": 4_500_000_000_000_000,
                "transferability": "priors_not_workload_measurements",
            },
            "workload": {
                "identity": "c32/4214/358/text-only/non-reasoning",
                "concurrency": concurrency,
                "prompt_tokens_per_request": prompt_tokens,
                "decode_steps": decode_steps,
                "decode_m": m,
                "tensor_parallel_size": 1,
            },
            "three_admitted_artifacts": {
                "comparator": {
                    "path": str(PATHS["comparator"].relative_to(LAB)),
                    "sha256": sha256(PATHS["comparator"]),
                    "valid_field": "candidate.service_seconds_per_request",
                },
                "residual_exclusion": {
                    "path": str(PATHS["residual_exclusion"].relative_to(LAB)),
                    "sha256": sha256(PATHS["residual_exclusion"]),
                },
                "cross_operator_exclusion": {
                    "path": str(PATHS["cross_operator_exclusion"].relative_to(LAB)),
                    "sha256": sha256(PATHS["cross_operator_exclusion"]),
                },
            },
        },
        "exact_hybrid_geometry": {
            "layer_order": "five sliding_attention then one full_attention, repeated ten times",
            "layers": 60,
            "local_layers": {
                "count": len(local_indices),
                "indices": local_indices,
                "query_heads": q_heads,
                "kv_heads": local_kv_heads,
                "head_dim": local_dim,
                "query_width": local_q,
                "k_width": local_kv,
                "v_width": local_kv,
                "qkv_output_width": local_q + 2 * local_kv,
                "sliding_window_tokens": window,
            },
            "global_layers": {
                "count": len(global_indices),
                "indices": global_indices,
                "query_heads": q_heads,
                "kv_heads": global_kv_heads,
                "head_dim": global_dim,
                "query_width": global_q,
                "raw_k_width": global_kv,
                "stock_materialized_raw_v_width": global_kv,
                "stock_qkv_output_width": stock_global_qkv,
                "candidate_qk_output_width": candidate_global_qk,
                "attention_k_eq_v_before_distinct_norms": True,
            },
            "cache": {
                "dtype": "bfloat16",
                "dtype_evidence": "inferred_from_auto_cache_dtype_plus_bfloat16_model_dtype_in_admitted_residual_artifact",
                "layout": {
                    "local_inferred_backend": "FlashInfer on SM100, HND required",
                    "global_inferred_backend": "FlashAttention v4 because FlashInfer supports head sizes only through 256 while global d=512",
                    "dynamic_execution_observed": False,
                },
                "base_default_block_tokens": base_block,
                "local": {
                    "block_tokens": local_block,
                    "bytes_per_token_per_layer": local_bytes_per_token_layer,
                    "page_bytes_per_layer": local_page_bytes,
                    "logical_pages_intersecting_window_per_step": {
                        "min": min(local_pages),
                        "max": max(local_pages),
                        "sum_over_steps": sum(local_pages),
                    },
                },
                "global": {
                    "raw_default_block_tokens": base_block,
                    "unified_block_tokens": global_block,
                    "bytes_per_token_per_layer": global_bytes_per_token_layer,
                    "page_bytes_per_layer": global_page_bytes,
                    "logical_pages_per_request_per_step": {
                        "min": min(global_pages),
                        "max": max(global_pages),
                        "sum_over_steps": sum(global_pages),
                    },
                },
                "hybrid_groups": {
                    "count": 6,
                    "layers_per_group": 10,
                    "local_groups": 5,
                    "global_groups": 1,
                    "page_bytes_per_layer_equalized": True,
                },
            },
        },
        "source_and_call_accounting": {
            "phase": "decode_only",
            "local": {
                "layer_calls_per_step": len(local_indices),
                "layer_calls_over_completion": local_calls,
                "qkv_scaled_mm_calls_over_completion": local_calls,
                "attention_calls_over_completion": local_calls,
                "kv_append_calls_over_completion": local_calls,
                "candidate_delta": 0,
            },
            "global": {
                "layer_calls_per_step": len(global_indices),
                "layer_calls_over_completion": global_calls,
                "stock_qkv_scaled_mm_calls_over_completion": global_calls,
                "candidate_qk_scaled_mm_calls_over_completion": global_calls,
                "attention_calls_over_completion": global_calls,
                "kv_append_calls_over_completion": global_calls,
            },
            "metadata": {
                "hybrid_group_metadata_build_calls_per_step": 6,
                "hybrid_group_metadata_build_calls_over_completion": 6
                * decode_steps,
                "candidate_delta": 0,
                "gpu_kernel_launches": "unmeasured_not_inferred_from_host_build_calls",
            },
            "launch_delta": {
                "scaled_mm": 0,
                "attention": 0,
                "kv_append": 0,
                "metadata": 0,
                "claim": "The mechanism narrows one existing global projection launch; it eliminates no launch.",
            },
            "symbols": [
                "Gemma4ForCausalLM.load_weights._weight_iterator",
                "Gemma4Model.load_weights",
                "Gemma4Attention.forward",
                "MergedColumnParallelLinear",
                "RMSNorm",
                "rotary_emb",
                "Attention.forward",
            ],
        },
        "non_overlapping_byte_and_flop_accounting": {
            "baseline_attention_kv_unchanged": {
                "local_logical_kv_read_bytes": local_kv_reads,
                "global_logical_kv_read_bytes": global_kv_reads,
                "total_logical_kv_read_bytes": local_kv_reads + global_kv_reads,
                "local_logical_kv_write_bytes": local_kv_writes,
                "global_logical_kv_write_bytes": global_kv_writes,
                "total_logical_kv_write_bytes": local_kv_writes + global_kv_writes,
                "candidate_delta_bytes": 0,
                "reason": "Distinct post-normalization K and V plus every cache page and attention read remain mandatory and unchanged.",
            },
            "candidate_credit_per_global_call": {
                "deleted_fp8_weight_bytes": removed_weight_per_call,
                "deleted_bf16_raw_v_output_bytes": removed_output_per_call,
                "deleted_useful_fp8_gemm_flops": removed_flops_per_call,
                "deleted_attention_or_kv_bytes": 0,
                "deleted_launches": 0,
            },
            "candidate_credit_endpoint_batch": {
                "calls": global_calls,
                "deleted_logical_fp8_weight_bytes": removed_weight_batch,
                "deleted_logical_bf16_raw_v_output_bytes": removed_output_batch,
                "deleted_logical_bytes_total": removed_logical_batch,
                "deleted_useful_fp8_gemm_flops": removed_flops_batch,
                "resident_model_fp8_weight_bytes_removed": len(global_indices)
                * removed_weight_per_call,
            },
            "candidate_credit_per_request": {
                "deleted_logical_fp8_weight_bytes": removed_weight_batch / concurrency,
                "deleted_logical_bf16_raw_v_output_bytes": removed_output_batch
                / concurrency,
                "deleted_useful_fp8_gemm_flops": removed_flops_batch / concurrency,
            },
            "evidence_labels": {
                "weight_and_output_bytes": "derived_logical_not_measured_hbm_transactions",
                "flops": "derived_useful_fp8_gemm_flops",
                "attention_kv_bytes": "reconciled_to_admitted_residual_artifact",
            },
            "exclusions": {
                "m32_dispatcher": {
                    "overlap": False,
                    "reason": "The candidate keeps cutlass_gemm_sm100_fp8_dispatch and its M32 tile policy byte-identical; only 2048 N columns cease to exist in 3580 global projection calls.",
                    "factorial_interaction": "The M32 dispatcher can independently tune both N=20480 stock and N=18432 candidate shapes; no dispatcher timing is credited here.",
                },
                "cross_operator_rmsnorm_fp8": {
                    "overlap": False,
                    "reason": "The candidate ends at the self-attention consumer and changes neither post-attention residuals nor MLP RMSNorm/dynamic-FP8 fusion.",
                },
                "attention_kv": {
                    "overlap": False,
                    "reason": "No page-table, metadata, KV read/write, attention FLOP, output projection, prefill, head, scheduler, or endpoint time is credited.",
                },
            },
        },
        "implementation": implementation,
        "correctness_semantics": {
            "proof_obligation": "For each full-attention TP=1 layer, checkpoint K is the sole raw K/V weight. Stock duplicates it into two QKV shards; candidate loads it once and aliases the one raw K output before the unchanged, distinct K-norm+RoPE and V-norm paths. Therefore Attention.forward receives the same semantic Q/K/V tensors.",
            "stock_source_fact": "The exact runtime duplicates k_proj with weight.clone() into v_proj and splits both materialized outputs.",
            "candidate_source_fact": "The patch loads q_proj/k_proj into qk_proj, assigns v = k before either normalization, and leaves q_norm, k_norm, v_norm, rotary_emb, Attention.forward, cache dtype, and cache layout unchanged.",
            "numerical_risk": "Changing GEMM N may change accumulation scheduling even when each retained column is mathematically identical; target execution must compare the retained Q/K and first-consumer attention output.",
            "future_oracle": {
                "inputs": "exact M32x5376 production hidden rows and exact ten global q_proj/k_proj checkpoint shards",
                "consume": "raw retained Q/K, post-norm+RoPE Q/K, post-v_norm V, and full Attention.forward output",
                "guards": {
                    "finite": True,
                    "cosine_min": 0.99999,
                    "relative_l2_max": 0.005,
                    "max_abs_max": 0.02,
                    "stock_raw_k_equals_stock_raw_v": "bitwise",
                },
                "boundary_cases": [
                    "M=32 production batch",
                    "zero hidden rows",
                    "tiny and high-amplitude finite rows",
                    "sequence lengths 4214, 4224, 4571",
                    "global page boundary at 32 tokens",
                ],
            },
        },
        "physical_hypothesis": {
            "causal_change": "Remove the duplicated global V columns from the runtime-dynamic-FP8 QKV projection while retaining one raw K tensor for both downstream normalization paths.",
            "projection_geometry": {
                "stock": {"m": 32, "k": hidden, "n": stock_global_qkv},
                "candidate": {"m": 32, "k": hidden, "n": candidate_global_qk},
                "n_reduction_fraction": global_kv / stock_global_qkv,
                "n128_tiles": {"stock": stock_global_qkv // 128, "candidate": candidate_global_qk // 128},
            },
            "predicted_sm100_counter_change": {
                "global_qkv_grid_ctas_per_unsplit_n_dimension": {"stock": 160, "candidate": 144},
                "global_qkv_useful_tensor_flops": "-10%",
                "global_qkv_logical_weight_bytes": "-10%",
                "global_qkv_bf16_output_bytes": "-10%",
                "scaled_mm_launches": "unchanged",
                "activation_quant_launches_and_bytes": "unchanged",
                "attention_and_kv_counters": "unchanged",
                "registers_spills_and_shared_memory_per_cta": "predicted unchanged because the Cutlass kernel and tile are unchanged",
            },
            "falsifier": "Reject if retained Q/K or the first-consumer output violates the oracle, if source/path proof shows V remains materialized, or if weighted warm global-QKV latency does not improve beyond noise.",
            "main_risk": "Both shapes may occupy the same grid wave and the remaining 144 CTAs may already saturate HBM, limiting latency benefit despite exact work deletion.",
        },
        "whole_request_relevance": {
            "measured_dynamic_fp8_service_seconds_per_request": service,
            "target_service_seconds_per_request": target,
            "remaining_gap_seconds_per_request": gap,
            "deleted_fraction_of_decode_transformer_logical_weight_bytes": removed_weight_batch
            / transformer_weight_bytes,
            "vendor_peak_hbm_sensitivity_not_upper_bound": {
                "batch_seconds": hbm_sensitivity_batch,
                "service_seconds_per_request": hbm_sensitivity_batch / concurrency,
                "fraction_of_remaining_gap": (hbm_sensitivity_batch / concurrency)
                / gap,
            },
            "vendor_peak_fp8_sensitivity_not_upper_bound": {
                "batch_seconds": removed_flops_batch / 4_500_000_000_000_000,
                "service_seconds_per_request": removed_flops_batch
                / 4_500_000_000_000_000
                / concurrency,
            },
            "interpretation": "The exact deletion is stackable but cannot close the campaign gap alone. Component timing is justified only as a cheap discriminator because launch count and attention/KV traffic are unchanged.",
        },
        "smallest_real_b200_component": {
            "authorization": "future_director_reservation_required_no_current_bench_claim",
            "venue": "one assigned nvidia-b200-sxm with the exact pinned image and project-local hash-bound source/config snapshot",
            "command": "python3 b200_k_eq_v_component.py --checkpoint <immutable-project-local-bf16-source> --hidden <immutable-project-local-m32-hidden.pt> --hidden-sha256 <sha256> --output <fresh-project-local-output.json>",
            "required_harness_contract": "Load exact layer-5 q_proj/k_proj shards and a hash-bound M32 production hidden capture, synchronize each arm after its first untimed call, consume the real FlashAttention first-consumer output over the exact global page geometry, then time profiler-off paired/alternating warm projection distributions.",
            "timing": "8 warmups and 40 paired alternating CUDA-event samples per arm; weight the one exact global shape by ten calls per decode step",
            "path_proof": "persist config, stock/candidate source, loaded checkpoint shard, extension/shared-object, selected backend, selected scaled-MM kernel, and output hashes",
            "counters_only_if_timing_discriminates": [
                "global QKV grid CTA count",
                "tensor instructions",
                "DRAM bytes",
                "kernel cycles",
                "registers and spills",
            ],
            "decision": "Retain any correct reproducible positive component delta for later integration; reject this mechanism if outputs fail or weighted latency is indistinguishable/regressive. Do not replay an endpoint for a negative component.",
        },
        "next_materially_distinct_boundary_if_negative": {
            "name": "local_window_page_traversal_and_kv_append",
            "why_distinct": "It targets the 50 local layers' 64-65 page window traversal and KV append/metadata path, not projection columns, M32 dispatch, or RMSNorm/FP8 fusion.",
            "exact_baseline": {
                "local_attention_calls_over_completion": local_calls,
                "local_kv_append_calls_over_completion": local_calls,
                "local_logical_page_references_over_steps_across_five_groups_and_c32": 5
                * concurrency
                * sum(local_pages),
                "local_logical_kv_read_bytes": local_kv_reads,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT / "B200_FP8_HYBRID_ATTENTION_DISCRIMINATOR.json",
    )
    args = parser.parse_args()
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with temporary.open() as handle:
        json.load(handle)
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}))


if __name__ == "__main__":
    main()
