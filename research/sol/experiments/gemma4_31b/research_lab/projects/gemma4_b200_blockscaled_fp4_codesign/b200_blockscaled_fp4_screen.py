#!/usr/bin/env python3
"""Exact-geometry, non-overlapping screen for Gemma 4 31B NVFP4 on B200.

This is an offline accounting program.  It validates the pinned Gemma config
and tensor index, then compares the only current Gemma-specific, quality-backed
NVFP4 coverage (MLP-only) with the retained dense-FP8 text-linear comparator.
It deliberately does not predict B200 endpoint throughput from peak FLOPS or
nominal bandwidth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parent
DEFAULT_BOUND = (
    PROJECT.parent
    / "gemma4_h200_ngram_persistent_grouped_lm_head"
    / "inputs"
    / "bound"
)
DEFAULT_SHAPE_MAP = (
    PROJECT.parent
    / "gemma4_h200_dense_fp8_linear_schedule"
    / "inputs"
    / "evidence"
    / "FP8_LINEAR_SHAPE_MAP.json"
)
DEFAULT_MIXED_BINDING = (
    PROJECT.parent
    / "gemma4_h200_mlp_w4_fp8_hybrid"
    / "MIXED_W4_FP8_BINDING.json"
)

EXPECTED = {
    "config_sha256": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    "index_sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
    "shape_map_sha256": "7c09e1e336d25fa89bfe8341af4c054af84175fca7a55365ca6528a9beee09e4",
    "mixed_binding_sha256": "939210b7ca17d34eee1d39d08b9e21ac6c353aae57f94e4753caa8718c8e3ef1",
}

UPSTREAM = {
    "nvidia_nvfp4_checkpoint": {
        "repo": "nvidia/Gemma-4-31B-IT-NVFP4",
        "revision": "4135a98a9b728a548947683219633b25682223ac",
        "url": "https://huggingface.co/nvidia/Gemma-4-31B-IT-NVFP4",
        "used_storage_bytes": 32665647434,
        "index_total_size_bytes": 32633255032,
        "producer": {"name": "modelopt", "version": "0.37.0"},
        "quant_algo": "NVFP4",
        "group_size": 16,
        "kv_cache": "FP8",
        "coverage": "MLP projections only; lm_head, vision, and every attention projection are ignored",
        "retrieved_utc": "2026-07-26T00:20:00Z",
    },
    "vllm": {
        "revision": "d30b1ecd1bdf7c3d92f3b444c4538efd8fbb40ac",
        "url": "https://github.com/vllm-project/vllm",
        "files": {
            "vllm/model_executor/layers/quantization/modelopt.py": "6732d6c46718f9f0a98ca1fd04ed730ac299c4f506b62adfd5029c8112a93207",
            "vllm/model_executor/kernels/linear/nvfp4/cutlass.py": "a0e5e3c25c19c351aa5c8a25346a6c01f1618745bbb2ace4e2f9d8a9200d7146",
            "vllm/_custom_ops.py": "63f5af42eb0326f3d0b8ce18f71164f24530a7b2c805da1d3e39838f230e86b4",
            "csrc/libtorch_stable/quantization/fp4/nvfp4_scaled_mm_kernels.cu": "91a85bfdbdd46d9a6a2d934428af0a25d1f1d3361a42d79fe632f55759fc63e3",
        },
    },
    "modelopt": {
        "revision": "d143276c39a995edea89dd98224bd423bce80867",
        "url": "https://github.com/NVIDIA/Model-Optimizer",
        "files": {
            "modelopt_recipes/configs/ptq/presets/model/nvfp4.yaml": "d3652a3caaa8613d8400f459e388ae647ab1f7668d96177ad87d5f0ba0f2a8fd",
            "modelopt_recipes/configs/ptq/units/w4a4_nvfp4_nvfp4.yaml": "2682bc6150b295646f9d3061feb2963680cd62d216b9ff5619eebd3f75a1e0dc",
            "modelopt_recipes/configs/numerics/nvfp4.yaml": "cea91c0276a335195b8f515623360d14a2df8458128b2507bf2ffd6488fa1768",
        },
    },
    "cutlass": {
        "revision": "e64a9136dd929639e5f7c969fe5af3bf7415cd4f",
        "url": "https://github.com/NVIDIA/cutlass",
        "dispatch_policy_sha256": "fcce5fffb3118b15fea5aa59e39bea15ddd18c28c858b434ced889045968117c",
    },
}

QUALITY_PRIOR = {
    "source": "https://huggingface.co/nvidia/Gemma-4-31B-IT-NVFP4",
    "calibration": {
        "method": "ModelOpt post-training max calibration",
        "dataset": "cnn_dailymail",
        "training": False,
    },
    "reported_bf16_vs_nvfp4": {
        "GPQA_Diamond": [85.80, 85.35],
        "AIME": [87.92, 87.60],
        "MMLU_Pro": [85.25, 84.94],
        "LiveCodeBench": [82.49, 82.27],
        "SciCode": [33.61, 33.18],
        "TerminalBench_Hard": [27.08, 27.08],
    },
    "evidence_label": "vendor_reported_model_card",
    "limit": (
        "This establishes a concrete MLP-only recovery recipe and a useful quality prior. "
        "It is not the campaign's exact-revision, prompt-distribution, or response-equivalence qualification."
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_json(path: Path, expected: str) -> dict[str, Any]:
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {path}: expected {expected}, got {actual}")
    return json.loads(path.read_text())


def ceil_div(x: int, y: int) -> int:
    return (x + y - 1) // y


def activation_traffic(m: int, k: int, n: int) -> dict[str, int]:
    # vLLM/CUTLASS uses an SM100 128x4 scale-factor layout.  One 512-byte
    # scale tile covers 128 rows by 64 values in K (four groups of 16).
    return {
        "m": m,
        "k": k,
        "n": n,
        "bf16_input_read_bytes": m * k * 2,
        "packed_fp4_write_bytes": m * k // 2,
        "padded_ue4m3_scale_write_bytes": ceil_div(m, 128) * ceil_div(k, 64) * 512,
        "bf16_gemm_output_write_bytes": m * n * 2,
        "scale_row_padding_factor": ceil_div(m, 128) * 128 / m,
    }


def weight_record(name: str, k: int, n: int) -> dict[str, Any]:
    elements = k * n
    scale_bytes = ceil_div(n, 128) * ceil_div(k, 64) * 512
    logical_scale_bytes = elements // 16
    if scale_bytes != logical_scale_bytes:
        raise RuntimeError(f"unexpected scale padding for {name}")
    return {
        "name": name,
        "k": k,
        "n": n,
        "elements_per_layer": elements,
        "bf16_bytes_per_layer": elements * 2,
        "dense_fp8_bytes_per_layer": elements,
        "nvfp4_value_bytes_per_layer": elements // 2,
        "nvfp4_ue4m3_scale_bytes_per_layer": scale_bytes,
        "nvfp4_total_bytes_per_layer_excluding_two_global_scalars": elements * 9 // 16,
        "cutlass_alignment": {
            "k_multiple_32": k % 32 == 0,
            "n_multiple_32": n % 32 == 0,
            "scale_padding_bytes": scale_bytes - logical_scale_bytes,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bound", type=Path, default=DEFAULT_BOUND)
    parser.add_argument("--shape-map", type=Path, default=DEFAULT_SHAPE_MAP)
    parser.add_argument("--mixed-binding", type=Path, default=DEFAULT_MIXED_BINDING)
    parser.add_argument(
        "--output", type=Path, default=PROJECT / "B200_BLOCKSCALED_FP4_SCREEN.json"
    )
    args = parser.parse_args()

    config = checked_json(args.bound / "config.json", EXPECTED["config_sha256"])
    index = checked_json(
        args.bound / "model.safetensors.index.json", EXPECTED["index_sha256"]
    )
    shape_map = checked_json(args.shape_map, EXPECTED["shape_map_sha256"])
    mixed = checked_json(args.mixed_binding, EXPECTED["mixed_binding_sha256"])

    text = config["text_config"]
    geometry = {
        "layers": text["num_hidden_layers"],
        "hidden": text["hidden_size"],
        "intermediate": text["intermediate_size"],
        "q_heads": text["num_attention_heads"],
        "kv_heads": text["num_key_value_heads"],
        "head_dim": text["head_dim"],
        "vocab": text["vocab_size"],
        "sliding_window": text["sliding_window"],
        "full_attention_layers": sum(
            layer_type == "full_attention" for layer_type in text["layer_types"]
        ),
        "sliding_attention_layers": sum(
            layer_type == "sliding_attention" for layer_type in text["layer_types"]
        ),
        "tied_embeddings": config["tie_word_embeddings"],
    }
    expected_geometry = {
        "layers": 60,
        "hidden": 5376,
        "intermediate": 21504,
        "q_heads": 32,
        "kv_heads": 16,
        "head_dim": 256,
        "vocab": 262144,
        "sliding_window": 1024,
        "full_attention_layers": 10,
        "sliding_attention_layers": 50,
        "tied_embeddings": True,
    }
    if geometry != expected_geometry:
        raise RuntimeError(f"unexpected Gemma geometry: {geometry}")

    weight_map = index["weight_map"]
    tensors: list[str] = []
    for layer in range(geometry["layers"]):
        for projection in ("gate_proj", "up_proj", "down_proj"):
            name = f"model.language_model.layers.{layer}.mlp.{projection}.weight"
            if name not in weight_map:
                raise RuntimeError(f"missing exact tensor {name}")
            tensors.append(name)

    h = geometry["hidden"]
    intermediate = geometry["intermediate"]
    qkv = (geometry["q_heads"] + 2 * geometry["kv_heads"]) * geometry["head_dim"]
    attn_out_k = geometry["q_heads"] * geometry["head_dim"]
    layers = geometry["layers"]

    weights = [
        weight_record("merged_gate_up", h, 2 * intermediate),
        weight_record("down", intermediate, h),
        weight_record("merged_qkv", h, qkv),
        weight_record("o", attn_out_k, h),
    ]
    mlp_elements = layers * (3 * h * intermediate)
    attention_elements = layers * (h * qkv + attn_out_k * h)
    all_linear_elements = mlp_elements + attention_elements
    dense_fp8_all_linear_bytes = all_linear_elements
    nvfp4_mlp_bytes = mlp_elements * 9 // 16 + layers * 3 * 8
    bf16_attention_bytes = attention_elements * 2
    admissible_bytes = nvfp4_mlp_bytes + bf16_attention_bytes
    admissible_saved_bytes = dense_fp8_all_linear_bytes - admissible_bytes
    admissible_saved_fraction = admissible_saved_bytes / dense_fp8_all_linear_bytes
    all_linear_nvfp4_bytes = all_linear_elements * 9 // 16 + layers * 4 * 8
    all_linear_saved_fraction = 1 - all_linear_nvfp4_bytes / dense_fp8_all_linear_bytes

    families = {row["projection"]: row for row in shape_map["projection_families"]}
    measured_fp8_family_seconds = sum(row["seconds"] for row in families.values())
    measured_mlp_family_seconds = (
        families["gate_up_proj"]["seconds"] + families["down_proj"]["seconds"]
    )
    measured_mlp_fraction_of_fp8_family = (
        measured_mlp_family_seconds / measured_fp8_family_seconds
    )
    fp8_linear_wall_fraction = mixed["measured_relevance"][
        "fp8_linear_wall_fraction"
    ]
    contextual_h200_affected_wall_fraction = (
        measured_mlp_fraction_of_fp8_family * fp8_linear_wall_fraction
    )

    qualified_h200 = 0.625149101968745
    threshold_b200 = 0.315609255362861
    required_service_reduction = 1 - threshold_b200 / qualified_h200
    required_realized_bandwidth_ratio_if_all_work_were_weight_stream = (
        admissible_bytes / dense_fp8_all_linear_bytes
    ) / (threshold_b200 / qualified_h200)

    falsifier = PROJECT / "b200_nvfp4_exact_shape_falsifier.py"
    if not falsifier.exists():
        raise RuntimeError(f"missing falsifier: {falsifier}")

    result: dict[str, Any] = {
        "schema_version": 1,
        "terminal": "typed_none",
        "classification": "current_quality_backed_mlp_only_nvfp4_scope_insufficient",
        "decision": (
            "Do not provision B200 for this current Gemma-specific NVFP4 route. "
            "The executable quality-backed path is MLP-only; its BF16 attention "
            "exclusions leave only a 4.095% text-linear weight-byte reduction "
            "against the retained dense-FP8 comparator. The all-linear NVFP4 "
            "counterfactual has useful traffic geometry but no exact Gemma quality recovery."
        ),
        "scope": {
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "workload": {
                "mode": "text-only non-reasoning",
                "concurrency": 32,
                "prompt_tokens_per_request": 4214,
                "output_tokens_per_request": 358,
                "cached_prompt_tokens_per_request": 535,
                "ordinary_decode_component_rows": 32,
                "target_verification_proxy_rows": 384,
            },
            "comparator": {
                "representation": "retained H200 dense FP8 text-linear stack",
                "qualified_seconds_per_request": qualified_h200,
            },
            "b200_base_case_threshold_seconds_per_request": threshold_b200,
            "required_whole_request_reduction_fraction": required_service_reduction,
        },
        "exact_geometry": {
            **geometry,
            "merged_projection_shapes_mkn": {
                "ordinary_decode_m32": [
                    [32, 43008, 5376],
                    [32, 5376, 21504],
                    [32, 16384, 5376],
                    [32, 5376, 8192],
                ],
                "target_verification_proxy_m384": [
                    [384, 43008, 5376],
                    [384, 5376, 21504],
                    [384, 16384, 5376],
                    [384, 5376, 8192],
                ],
            },
            "affected_exact_tensors": {
                "count": len(tensors),
                "names": tensors,
                "index_tensor_count": len(weight_map),
            },
            "weight_families": weights,
        },
        "current_producer_consumer_path": {
            "producer": {
                "offline": (
                    "ModelOpt 0.37.0 max PTQ; E2M1 values, one E4M3 scale per "
                    "16 values, plus per-tensor FP32 double scales"
                ),
                "runtime_activation": (
                    "vllm._custom_ops.scaled_fp4_quant; BF16/FP16 to packed "
                    "E2M1 plus swizzled UE4M3 block scales"
                ),
                "adjacent_epilogue": (
                    "gate/up GEMM writes BF16; SiLU-and-multiply followed by "
                    "down-input quantization can fuse as torch.ops._C.silu_and_mul_nvfp4_quant"
                ),
            },
            "consumer": {
                "loader": "ModelOptNvFp4LinearMethod",
                "forced_backend": "--linear-backend cutlass",
                "abi": "cutlass_scaled_fp4_mm(A_fp4, B_fp4, SFA_ue4m3, SFB_ue4m3, alpha_fp32, BF16)",
                "architecture": "CUTLASS OpClassBlockScaledTensorOp, ArchTag Sm100",
                "m32_tile": {
                    "tile_mnk": [256, 128, 256],
                    "cluster": [2, 1, 1],
                    "per_sm_tile_mnk": [128, 128, 256],
                    "scheduler": "non-persistent",
                },
                "m384_tile": {
                    "tile_mnk": [256, 256, 256],
                    "cluster": [2, 1, 1],
                    "per_sm_tile_mnk": [128, 256, 256],
                    "scheduler": "PersistentScheduler",
                },
            },
            "identities": UPSTREAM,
        },
        "traffic_screen": {
            "evidence_label": "analytical_exact_geometry",
            "candidate_quality_backed_coverage": "MLP-only NVFP4 plus BF16 attention",
            "mlp_elements": mlp_elements,
            "attention_linear_elements": attention_elements,
            "all_text_linear_elements": all_linear_elements,
            "dense_fp8_all_text_linear_weight_bytes": dense_fp8_all_linear_bytes,
            "candidate_nvfp4_mlp_weight_and_scale_bytes": nvfp4_mlp_bytes,
            "candidate_bf16_attention_linear_weight_bytes": bf16_attention_bytes,
            "candidate_all_text_linear_weight_bytes": admissible_bytes,
            "candidate_saved_bytes_vs_dense_fp8": admissible_saved_bytes,
            "candidate_saved_fraction_vs_dense_fp8": admissible_saved_fraction,
            "all_linear_nvfp4_counterfactual": {
                "bytes": all_linear_nvfp4_bytes,
                "saved_fraction_vs_dense_fp8": all_linear_saved_fraction,
                "admissible": False,
                "reason": (
                    "The current Gemma derivative explicitly ignores all attention "
                    "projections; no exact-revision, all-linear NVFP4 calibration or "
                    "quality result is available."
                ),
            },
            "l2_residency": {
                "b200_l2_bytes_vendor_decimal": 126000000,
                "merged_gate_up_nvfp4_bytes_per_layer": 130056192,
                "down_nvfp4_bytes_per_layer": 65028096,
                "whole_mlp_nvfp4_bytes_per_layer": 195084288,
                "conclusion": (
                    "The merged gate/up alone exceeds the 126-MB L2 and the full MLP "
                    "is 195.084 MB; compulsory decode weight streaming remains."
                ),
            },
            "runtime_activation_and_output_bytes": {
                "m32_gate_up": activation_traffic(32, h, 2 * intermediate),
                "m32_down": activation_traffic(32, intermediate, h),
                "m384_gate_up": activation_traffic(384, h, 2 * intermediate),
                "m384_down": activation_traffic(384, intermediate, h),
                "note": (
                    "M32 block-scale rows pad 4x to the 128-row scale layout. "
                    "M384 is row-tile exact. These bytes are reported separately "
                    "and are not subtracted again from weight savings."
                ),
            },
            "required_realized_bandwidth_ratio_if_everything_were_only_weight_stream": (
                required_realized_bandwidth_ratio_if_all_work_were_weight_stream
            ),
            "limit": (
                "This ratio is a necessary parameterized gate, not a B200 throughput "
                "prediction. Nominal 8-TB/s bandwidth and peak FP4 FLOPS are not used "
                "to emit endpoint seconds."
            ),
        },
        "non_overlapping_request_accounting": {
            "candidate_bucket": "MLP projection weights, scales, activation quantization, SiLU/gate, and MLP outputs only",
            "excluded_unchanged_buckets": [
                "all attention Q/K/V/O projections (BF16 in the quality-backed checkpoint)",
                "attention and KV-cache traffic",
                "prefill scheduling and paged-attention work",
                "output head and tied embedding",
                "vision tower",
                "sampling, scheduler, graph, host, and network residual",
            ],
            "target_verification_m384": (
                "A separate exact-shape proxy row for kernel saturation; it is not "
                "added to ordinary decode or counted as campaign endpoint work."
            ),
            "contextual_h200_profile": {
                "measured_mlp_fraction_of_fp8_linear_family": measured_mlp_fraction_of_fp8_family,
                "measured_fp8_linear_fraction_of_profile_wall": fp8_linear_wall_fraction,
                "product_fraction": contextual_h200_affected_wall_fraction,
                "zero_cost_mlp_contextual_floor_seconds_per_request": (
                    qualified_h200 * (1 - contextual_h200_affected_wall_fraction)
                ),
                "limit": (
                    "The product is exact-model H200 context only. It is not transferred "
                    "to B200 and is not the terminal proof."
                ),
            },
        },
        "quality_recovery": QUALITY_PRIOR,
        "cheapest_exact_shape_falsifier": {
            "status": "implemented_reopen_only_not_authorized",
            "runner": falsifier.name,
            "runner_sha256": sha256(falsifier),
            "hardware": "one B200 SM100 with at least 4 GiB free HBM",
            "strongest_supported_baseline": (
                "same current vLLM commit, CUTLASS SM100 FP8 dynamic activation "
                "quantization plus static FP8 weights"
            ),
            "candidate": (
                "same current vLLM commit, CUTLASS SM100 NVFP4 dynamic activation "
                "quantization, fused SiLU*up-to-NVFP4, and NVFP4 weights"
            ),
            "exact_rows": [
                {"m": 32, "gate_up_nk": [43008, 5376], "down_nk": [5376, 21504]},
                {"m": 384, "gate_up_nk": [43008, 5376], "down_nk": [5376, 21504]},
            ],
            "predicted_physical_change": (
                "MLP static value+scale bytes fall 43.75% versus dense FP8; "
                "dram__bytes_read.sum should fall in the projection regions, while "
                "M32 exposes 4x activation-scale row padding and M384 tests saturation."
            ),
            "counters": [
                "dram__bytes_read.sum",
                "dram__bytes_write.sum",
                "sm__cycles_active.avg",
                "smsp__inst_executed.sum",
            ],
            "correctness": (
                "finite outputs plus cosine similarity and normalized RMSE against "
                "the same BF16 synthetic exact-shape MLP; this is a kernel oracle, "
                "not a model-quality qualification"
            ),
            "source_identity": UPSTREAM["vllm"],
            "runtime_build": (
                "Build vLLM revision d30b1ecd... from its Dockerfile (CUDA 13.0.3) "
                "and resolve the resulting image digest before any claim."
            ),
            "expected_measurement_wall_minutes": 8,
            "maximum_provider_exposure_minutes": 12,
            "maximum_spend_usd_at_5_15_per_hour": 1.03,
            "current_authorized_spend_usd": 0.0,
            "reopen_gate": (
                "Do not run merely to test the closed MLP-only route. Reopen only after "
                "an exact Gemma all-linear quality recovery or another current supported "
                "coverage that preserves at least 30% non-overlapping text-linear bytes."
            ),
        },
        "typed_negative": {
            "type": "quality_backed_coverage_and_nonoverlapping_reduction_insufficient",
            "measured_or_derived_facts": [
                f"Required whole-request reduction: {required_service_reduction:.9%}.",
                f"Current admissible MLP-only route saves {admissible_saved_fraction:.9%} of text-linear weight bytes versus dense FP8.",
                "The published recovery explicitly excludes all 60 layers' attention projections.",
                f"All-linear NVFP4 would save {all_linear_saved_fraction:.9%}, but is quality-unsafe in this exact scope.",
            ],
            "not_claimed": [
                "No B200 endpoint throughput was inferred.",
                "No B200 GPU or provider resource was claimed or created.",
                "No nominal-bandwidth or peak-FLOP extrapolation was used as a result.",
                "No vendor-reported quality result was promoted to campaign equivalence.",
            ],
            "reopen_condition": (
                "A content-addressed Gemma 4 31B checkpoint with attention plus MLP "
                "NVFP4/FP6 coverage and concrete calibration/equivalence evidence, "
                "or a current consumer that preserves equivalent quality while saving "
                "at least 30% of non-overlapping text-linear bytes. Then run the bounded "
                "exact-shape falsifier before an endpoint."
            ),
        },
        "inputs": {
            str(args.bound / "config.json"): EXPECTED["config_sha256"],
            str(args.bound / "model.safetensors.index.json"): EXPECTED["index_sha256"],
            str(args.shape_map): EXPECTED["shape_map_sha256"],
            str(args.mixed_binding): EXPECTED["mixed_binding_sha256"],
            str(Path(__file__).resolve()): sha256(Path(__file__).resolve()),
            str(falsifier.resolve()): sha256(falsifier.resolve()),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "terminal": result["terminal"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
