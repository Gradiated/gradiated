#!/usr/bin/env python3
"""Build the hash-bound B200 FP8 cross-operator discriminator."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
RESIDUAL_PROJECT = PROJECTS / "gemma4_b200_fp8_residual_hotpath"
ENDPOINT_PROJECT = PROJECTS / "gemma4_b200_dynamic_fp8_endpoint"
RESIDUAL = RESIDUAL_PROJECT / "B200_FP8_RESIDUAL_DISCRIMINATOR.json"
ENDPOINT = (
    ENDPOINT_PROJECT
    / "artifacts/b200-dynamic-fp8-repair2-20260728t1517z/FINAL_TERMINAL.json"
)
CONFIG = ENDPOINT_PROJECT / "inputs/bf16-source/config.json"
RUNNER = PROJECT / "b200_cross_operator_consumer.py"
OUTPUT = PROJECT / "B200_FP8_CROSS_OPERATOR_DISCRIMINATOR.json"
PINNED = RESIDUAL_PROJECT / "evidence/pinned_runtime"

EXPECTED = {
    CONFIG: "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    ENDPOINT: "2873d1b8d311153e903aeb525d59cd61620ecc1129120cfc81e2ec1f5d68ae86",
    PINNED / "ScaledMMLinearKernel.py": (
        "8618ebb23f1b7e14a4ad2534a4c19c32adf52b30b925b8453a18085a174d4471"
    ),
    PINNED / "cutlass.py": (
        "e212907776b61fd6618e6b812cee9a471ca83140a4710ca447bc6c11cc1d8488"
    ),
    PINNED / "fp8.py": (
        "f2612966aaefa1dd4596a50da361628f64cd590eb3e6bbf6e1b4cfa488334d7e"
    ),
    PINNED / "gemma4.py": (
        "e16b28577c7cdca4876d26636564ed411fc7ce4a25b724456ee906d8129eed20"
    ),
    RESIDUAL: "59a91ecd82e55c388f02b3a948c6650d8f260c0d1d92202513059441d9c32415",
}
COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
REMOTE_SOURCE_HASHES = {
    "vllm/_custom_ops.py": (
        "8990c0c4de5dadbb2d1ff57f02d6a7f9133df29bb9070179ada3363461b40093"
    ),
    "vllm/compilation/passes/fusion/rms_quant_fusion.py": (
        "147c11e8c89e93a70fc01275d8aebf5c37caca37482f762390396b0be6ad25b7"
    ),
    "vllm/config/compilation.py": (
        "ac12008b54dcf778db658786502d160a70a6a1120533584da1e4976c9756ce38"
    ),
    "vllm/config/vllm.py": (
        "58aebc9654b3d62c9707be62df47ac43254b52218d9ea38c43d3026485ff9e01"
    ),
    "vllm/model_executor/layers/layernorm.py": (
        "8b4e0b93d1d76f0394bb28f40528bdfb250e16f22a83add184d3c2651f915623"
    ),
    "vllm/model_executor/layers/quantization/input_quant_fp8.py": (
        "6d09f1b7f8191303c4ebcc454cbf2bfb6319fbec1cb12c9842720e2f8ef75a18"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    json.loads(temporary.read_text())
    temporary.replace(path)


def source_url(path: str) -> str:
    return f"https://github.com/vllm-project/vllm/blob/{COMMIT}/{path}"


def main() -> int:
    for path, expected in EXPECTED.items():
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError(f"input_hash_mismatch:{path}:{observed}:{expected}")
    endpoint = json.loads(ENDPOINT.read_text())
    residual = json.loads(RESIDUAL.read_text())
    config = json.loads(CONFIG.read_text())["text_config"]
    assert endpoint["candidate"]["service_seconds_per_request"] == 0.633995593312477
    assert config["hidden_size"] == 5376
    assert config["intermediate_size"] == 21504
    assert config["num_hidden_layers"] == 60
    assert config["rms_norm_eps"] == 1e-6
    assert not config["enable_moe_block"]
    assert not config["use_double_wide_mlp"]
    assert config["hidden_size_per_layer_input"] == 0
    assert residual["production_geometry"]["fp8_gemms_per_decode_step"] == 240

    m, k, n = 32, 5376, 43008
    layers = config["num_hidden_layers"]
    steps = 358
    calls = layers * steps
    elements = m * k
    scale_bytes = m * 4
    stock_bytes_if_add_separate = elements * 9 + scale_bytes
    candidate_bytes = elements * 7 + scale_bytes
    eliminated_bytes_per_call = stock_bytes_if_add_separate - candidate_bytes
    eliminated_bytes_batch = eliminated_bytes_per_call * calls
    gate_up_weight_bytes_batch = k * n * calls
    gate_up_flops_batch = 2 * m * k * n * calls
    candidate_service = endpoint["candidate"]["service_seconds_per_request"]
    target_service = 0.500119281574996
    service_gap = candidate_service - target_service
    required_batch_saving = service_gap * m
    required_us_per_call = required_batch_saving / calls * 1e6
    ideal_hbm_seconds = eliminated_bytes_batch / 8e12
    sensitivity_10us_batch = calls * 10e-6 + ideal_hbm_seconds

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "classification": (
            "hash_bound_exact_consumer_with_primary_mechanism_typed_rejection"
        ),
        "decision": (
            "Reject fused residual-add/RMSNorm/dynamic-FP8 quantization as a "
            "primary B200 residual lane because the pinned default O2 Inductor "
            "path already owns RMSNorm+quant fusion. Retain the exact consumer "
            "only as a cheap stackable discriminator for the residual-add "
            "prologue; do not claim a bench before director review."
        ),
        "authoritative_identities": {
            "endpoint_terminal": {
                "path": str(ENDPOINT.relative_to(PROJECTS.parent)),
                "sha256": sha256(ENDPOINT),
                "batch_seconds": endpoint["candidate"]["batch_seconds"],
                "service_seconds_per_request": candidate_service,
                "requests": endpoint["candidate"]["complete_requests"],
                "workload": endpoint["candidate"]["identity"]["workload"],
            },
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "config_sha256": sha256(CONFIG),
                "hidden_size": k,
                "intermediate_size": config["intermediate_size"],
                "layers": layers,
                "rms_norm_eps": config["rms_norm_eps"],
                "moe_enabled": config["enable_moe_block"],
                "ple_hidden_size": config["hidden_size_per_layer_input"],
            },
            "runtime": {
                "image": (
                    "docker.io/vllm/vllm-openai:gemma4@sha256:"
                    "952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
                ),
                "vllm_commit": COMMIT,
                "vllm_version": "0.19.1.dev6+g6d4a8e6d2",
                "local_installed_source_hashes": {
                    path.name: sha256(path)
                    for path in (
                        PINNED / "gemma4.py",
                        PINNED / "fp8.py",
                        PINNED / "ScaledMMLinearKernel.py",
                        PINNED / "cutlass.py",
                    )
                },
                "relevant_commit_source": {
                    path: {"sha256": digest, "url": source_url(path)}
                    for path, digest in REMOTE_SOURCE_HASHES.items()
                },
            },
            "hardware": {
                "id": "nvidia-b200-sxm",
                "programming_target": "sm_100",
                "hbm_bytes_per_second_vendor_prior": 8e12,
                "fp8_flops_per_second_vendor_prior": 4.5e15,
            },
        },
        "source_trace": [
            {
                "order": 1,
                "symbol": "Gemma4DecoderLayer.forward",
                "claim": (
                    "The post-attention output is RMS-normalized, added to the "
                    "pre-attention residual, copied to residual, then "
                    "pre-feedforward RMS-normalized and passed to Gemma4MLP."
                ),
                "evidence": "pinned_source",
                "source_sha256": sha256(PINNED / "gemma4.py"),
            },
            {
                "order": 2,
                "symbols": [
                    "Gemma4MLP.forward",
                    "MergedColumnParallelLinear(gate_up_proj)",
                    "Fp8OnlineLinearMethod.apply",
                ],
                "claim": (
                    "Every dense decoder layer sends the pre-feedforward "
                    "RMSNorm output into one runtime-dynamic-FP8 gate_up "
                    "projection with K=5376 and N=43008."
                ),
                "evidence": "pinned_source_plus_exact_config",
            },
            {
                "order": 3,
                "symbols": [
                    "FP8ScaledMMLinearKernel.apply_weights",
                    "QuantFP8.forward_native",
                    "CutlassFP8ScaledMMLinearKernel.apply_scaled_mm",
                ],
                "claim": (
                    "The producer emits per-token E4M3 activations and FP32 "
                    "scales; the first decision-bearing consumer is BF16 "
                    "Cutlass scaled-MM output."
                ),
                "evidence": "pinned_source",
            },
            {
                "order": 4,
                "symbols": [
                    "enable_norm_fusion",
                    "CompilationConfig.custom_ops",
                    "RMSNormQuantFusionPass",
                ],
                "claim": (
                    "At the launcher's default O2 Inductor configuration, "
                    "custom ops are disabled and the pinned source explicitly "
                    "delegates RMSNorm+FP8-quant fusion to Inductor. The custom "
                    "fusion pass is enabled only when RMSNorm or quant_fp8 is "
                    "forced to a custom op."
                ),
                "evidence": "pinned_commit_source",
            },
            {
                "order": 5,
                "symbol": "rms_norm_dynamic_per_token_quant",
                "claim": (
                    "The same pinned extension already provides a residual-aware "
                    "fused RMSNorm+dynamic-per-token-quant primitive, so a new "
                    "kernel would duplicate a supported mechanism."
                ),
                "evidence": "pinned_commit_source",
            },
        ],
        "selected_hot_block": {
            "phase": "decode",
            "name": "post_attention_residual_pre_ff_rms_quant_gate_up",
            "input_contract": {
                "post_attention_norm": {
                    "shape": [m, k],
                    "dtype": "bfloat16",
                    "layout": "contiguous_row_major",
                },
                "residual": {
                    "shape": [m, k],
                    "dtype": "bfloat16",
                    "layout": "contiguous_row_major",
                    "must_be_preserved_as_residual_out": True,
                },
                "pre_feedforward_norm_weight": {
                    "shape": [k],
                    "dtype": "bfloat16",
                },
                "gate_up_weight": {
                    "shape": [k, n],
                    "dtype": "float8_e4m3fn",
                    "layout": "cutlass_transposed_KN",
                    "scale": "online_weight_per_tensor_fp32",
                },
            },
            "output_contract": {
                "residual_out": {"shape": [m, k], "dtype": "bfloat16"},
                "activation": {
                    "shape": [m, k],
                    "dtype": "float8_e4m3fn",
                    "scale_shape": [m, 1],
                    "scale_dtype": "float32",
                    "scale_granularity": "per_token",
                },
                "gate_up_output": {"shape": [m, n], "dtype": "bfloat16"},
            },
            "calls_per_decode_step": layers,
            "calls_per_endpoint_batch": calls,
            "share_of_decode_fp8_gemms": layers
            / residual["production_geometry"]["fp8_gemms_per_decode_step"],
        },
        "implementation": {
            "type": "existing_pinned_primitive_exact_consumer",
            "path": RUNNER.name,
            "sha256": sha256(RUNNER),
            "candidate_path": (
                "rms_norm_dynamic_per_token_quant(residual=...) -> "
                "cutlass_scaled_mm"
            ),
            "stock_path": (
                "torch.compile of exact RMSNorm.forward_static + "
                "QuantFP8.forward_native expressions -> cutlass_scaled_mm"
            ),
            "fresh_process": True,
            "first_call_arm_synchronization": True,
            "full_output_consumed": True,
            "semantic_class": "numerically_equivalent_semantics_preserving",
            "runtime_source_hash_fail_closed": True,
            "dispatcher_modified": False,
            "offline_describe_check": "passed",
            "target_execution": "not_run_scope_forbids_bench_claim",
        },
        "non_overlapping_accounting": {
            "identity": (
                "Only the residual-add prologue before the already-fused "
                "RMSNorm+quant boundary is credited. Gate-up GEMM, its "
                "dispatcher, all other linears, attention/KV, tied head, "
                "prefill, and scheduler time remain unchanged."
            ),
            "per_call": {
                "elements": elements,
                "stock_logical_activation_bytes_if_add_is_separate": (
                    stock_bytes_if_add_separate
                ),
                "candidate_logical_activation_bytes": candidate_bytes,
                "eliminated_bytes_interval": [0, eliminated_bytes_per_call],
                "launches_eliminated_interval": [0, 1],
                "unchanged_gate_up_weight_bytes": k * n,
                "unchanged_gate_up_useful_flops": 2 * m * k * n,
            },
            "endpoint_batch": {
                "calls": calls,
                "eliminated_bytes_interval": [0, eliminated_bytes_batch],
                "launches_eliminated_interval": [0, calls],
                "unchanged_gate_up_weight_bytes": gate_up_weight_bytes_batch,
                "unchanged_gate_up_useful_flops": gate_up_flops_batch,
            },
            "zero_lower_bound_reason": (
                "The retained endpoint did not preserve generated Inductor "
                "code or a kernel trace, so the residual add may already be "
                "folded into the compiler-generated RMSNorm+quant prologue."
            ),
            "upper_interval_reason": (
                "If the residual add is a separate kernel, the fused candidate "
                "removes one reread of the BF16 residual_out tensor and one "
                "launch; residual_out itself must still be written because the "
                "post-MLP residual consumer needs it."
            ),
            "m32_dispatch_overlap": {
                "overlap": False,
                "reason": (
                    "This intervention changes neither scaled-MM inputs, tile "
                    "selection, weight bytes, GEMM output, nor "
                    "cutlass_gemm_sm100_fp8_dispatch."
                ),
            },
        },
        "physical_hypothesis": {
            "candidate_change": (
                "Use the pinned residual-aware fused RMSNorm+dynamic-per-token "
                "FP8 primitive so residual_out is produced once while the "
                "normalized value goes directly to E4M3 without a BF16 "
                "intermediate."
            ),
            "predicted_counter_change": {
                "pre_gemm_kernel_launches_per_call": {
                    "stock_interval": [1, 2],
                    "candidate": 1,
                },
                "logical_activation_bytes_delta_per_call": [
                    -eliminated_bytes_per_call,
                    0,
                ],
                "gate_up_gemm_cycles": "unchanged",
                "gate_up_dram_weight_bytes": "unchanged",
                "cutlass_dispatch_symbol": "unchanged",
                "candidate_failure_mode": (
                    "Pinned documentation predicts NVIDIA Inductor's existing "
                    "fusion is faster than the custom CUDA primitive; the "
                    "candidate may therefore regress despite equivalent launch "
                    "count."
                ),
            },
            "falsifier": (
                "Generated stock path has one pre-GEMM kernel, or the direct "
                "candidate fails correctness or projects below 0.002 s/request."
            ),
        },
        "correctness": {
            "oracle": (
                "Compile the exact pinned RMSNorm.forward_static and "
                "QuantFP8.forward_native expressions, feed both stock and "
                "candidate E4M3/scales to the unchanged Cutlass scaled-MM, and "
                "consume residual_out, dequantized activation, and full BF16 "
                "gate-up output."
            ),
            "cases": [
                "production M32xK5376 gate_up N43008",
                "zero residual",
                "zero post-attention input",
                "tiny and high-amplitude finite rows",
            ],
            "tolerance": {
                "finite": True,
                "cosine_min": 0.99999,
                "relative_l2_max": 0.005,
                "max_abs_max": 0.02,
            },
            "scale_contract": (
                "E4M3 dynamic per-token FP32 [M,1], including zero/tiny-row "
                "minimum-scale guard; no saturation or nonfinite output."
            ),
        },
        "whole_request_relevance": {
            "candidate_service_seconds_per_request": candidate_service,
            "target_service_seconds_per_request": target_service,
            "gap_seconds_per_request": service_gap,
            "required_batch_saving_seconds": required_batch_saving,
            "required_delta_us_per_selected_call_to_close_target": (
                required_us_per_call
            ),
            "ideal_hbm_only_saving_seconds_per_request_at_vendor_peak": (
                ideal_hbm_seconds / m
            ),
            "synthetic_10us_launch_sensitivity": {
                "label": "derived_sensitivity_not_measurement_or_upper_bound",
                "batch_saving_seconds": sensitivity_10us_batch,
                "service_saving_seconds_per_request": sensitivity_10us_batch / m,
                "fraction_of_remaining_gap": (
                    sensitivity_10us_batch / m / service_gap
                ),
            },
            "formula": (
                "delta_service_s = 21480 * measured_delta_us_per_call / "
                "1e6 / 32"
            ),
            "interpretation": (
                "Even a generous 10-us launch sensitivity addresses only about "
                "5% of the remaining target gap. This is stackable work, not a "
                "primary route."
            ),
        },
        "smallest_future_b200_measurement": {
            "authorization": "director_review_required_no_current_bench_claim",
            "venue": (
                "one already-assigned nvidia-b200-sxm bench with the exact "
                "pinned image; no endpoint request"
            ),
            "command": (
                "python3 b200_cross_operator_consumer.py --output "
                "<fresh-project-local-output>"
            ),
            "arms": [
                "default O2 Inductor source-equivalent boundary plus unchanged gate_up",
                "pinned residual-aware fused CUDA primitive plus unchanged gate_up",
            ],
            "timing": (
                "same process, first-call synchronize per arm, profiler-off "
                "warm CUDA events, 8 warmups and 40 samples"
            ),
            "path_proof": (
                "fail closed on vLLM source hashes; persist extension hash, "
                "runner hash, first-call markers, and generated Inductor "
                "kernel count"
            ),
            "decision": (
                "Reopen a narrow model integration only if every numerical "
                "guard passes and production-weighted projection is at least "
                "0.002 s/request. Otherwise accept the typed rejection without "
                "endpoint replay."
            ),
            "counters_only_if_positive": [
                "pre-GEMM kernel count",
                "DRAM bytes over the boundary",
                "registers and spills for the fused primitive",
            ],
        },
        "typed_rejections": [
            {
                "classification": "mechanism_already_realized_by_default_compiler",
                "mechanism": "new RMSNorm plus dynamic-FP8 quant kernel",
                "reason": (
                    "Pinned O2 configuration disables custom RMSNorm/quant ops "
                    "specifically because Inductor handles their fusion."
                ),
            },
            {
                "classification": "global_reduction_boundary_not_epilogue_safe",
                "mechanism": "fold post-MLP RMSNorm into down-projection epilogue",
                "reason": (
                    "RMSNorm needs a complete 5376-wide row reduction while "
                    "the scaled-MM owns independent output tiles, and the "
                    "normalized output participates in a residual add. A "
                    "CUTLASS tile epilogue cannot preserve this contract "
                    "without a cross-tile reduction or another stage."
                ),
            },
        ],
        "scope": {
            "actual_spend_usd": 0.0,
            "gpu_claimed": False,
            "provider_operations": False,
            "endpoint_requests_submitted": False,
            "scientific_sample_consumed": False,
            "dispatcher_modified": False,
            "researcher_profile": "deep",
        },
    }
    atomic_json(OUTPUT, artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
