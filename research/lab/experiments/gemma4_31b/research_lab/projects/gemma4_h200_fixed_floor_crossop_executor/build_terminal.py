#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
CAMPAIGN = LAB / "CAMPAIGN.md"
PATHS = {
    "lossless_entropy_terminal": PROJECT.parent
    / "gemma4_h200_lossless_fp8_entropy_gemm"
    / "LOSSLESS_FP8_ENTROPY_GEMM_OFFLINE_TERMINAL.json",
    "attribution": PROJECT.parent
    / "gemma4_h200_dense_fp8_linear_schedule"
    / "inputs/evidence/ATTRIBUTION.json",
    "shape_map": PROJECT.parent
    / "gemma4_h200_dense_fp8_linear_schedule"
    / "inputs/evidence/FP8_LINEAR_SHAPE_MAP.json",
    "model_config": PROJECT.parent
    / "gemma4_h200_dense_fp8_linear_schedule"
    / "inputs/checkpoint/config.json",
    "runtime_bindings": PROJECT.parent
    / "gemma4_h200_v0513_fp8_qkv_residual_profile"
    / "BINDINGS.json",
    "profile_sqlite": PROJECT.parent
    / "gemma4_h200_v0513_fp8_qkv_residual_profile"
    / "artifacts/residual-profile-20260720t0821z/control-profile.sqlite",
    "pinned_gemma4_causal": PROJECT.parent
    / "gemma4_h200_fp8_layer_dataflow_fusion"
    / "inputs/source/gemma4_causal.py",
    "measured_qkv_source": PROJECT.parent
    / "gemma4_h200_qkv_epilogue_fusion"
    / "qkv_epilogue_discriminator.py",
    "measured_qkv_terminal": PROJECT.parent
    / "gemma4_h200_qkv_epilogue_fusion"
    / "artifacts/qkv-component-20260720t0026z/TERMINAL.json",
    "memory_pool_source": PROJECT.parent
    / "gemma4_h200_layerwise_mixed_kv_endpoint"
    / "inputs/pinned_source/mem_cache/memory_pool.py",
    "swa_memory_pool_source": PROJECT.parent
    / "gemma4_h200_layerwise_mixed_kv_endpoint"
    / "inputs/pinned_source/mem_cache/swa_memory_pool.py",
    "triton_attention_backend": PROJECT.parent
    / "gemma4_h200_ngram_tree_verify_attention"
    / "inputs/source/triton_backend.v0.5.13.py",
    "retained_deferred_local_kv": PROJECT.parent
    / "gemma4_h200_v0513_fp8_qkv_residual_profile"
    / "intervention/attention_deferred_local_kv.py",
    "campaign": CAMPAIGN,
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(path: pathlib.Path) -> dict[str, object]:
    return {
        "path": os.path.relpath(path.resolve(), PROJECT),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    validation_path = PROJECT / "OFFLINE_VALIDATION.json"
    validation = json.loads(validation_path.read_text())
    if not validation["passed"]:
        raise RuntimeError("offline validation did not pass")
    chain = validation["trace_reconstruction"]
    bound = validation["whole_request_bound"]
    candidate_source = PROJECT / "fused_qkv_kv_cache.py"
    candidate_hash = sha256(candidate_source)
    source_files = [
        candidate_source,
        PROJECT / "install_fused_qkv_cache.py",
        PROJECT / "exact_consumer.py",
        PROJECT / "offline_validate.py",
        PROJECT / "build_terminal.py",
    ]
    output = PROJECT / "FIXED_FLOOR_CROSSOP_OFFLINE_TERMINAL.json"
    result = {
        "schema_version": 1,
        "terminal_type": "fixed_floor_crossop_offline_positive",
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT.name,
        "answer": (
            "Yes for a bounded positive arm, not for the locked target by itself. "
            "Fuse the accepted QKV norm+RoPE producer with the E5M2 NHD KV-cache "
            "commit. The exact c32 trace exposes 0.322976317 seconds of removable "
            "retained-stack work and 19,520 launches. A 50%-realization complete "
            "bound predicts 0.6207671441 seconds/request, still above the "
            "0.5001192816 target, so only one exact H200 component consumer is admitted."
        ),
        "scope": {
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime": "SGLang v0.5.13",
            "sglang_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
            "target_gpu": "NVIDIA H200 SXM, SM90, 132 SMs",
            "workload": {
                "concurrency": 32,
                "requests": 32,
                "fresh_prompt_tokens": 117728,
                "cached_prompt_tokens": 17120,
                "prompt_tokens_per_request": 4214,
                "completion_tokens_per_request": 358,
                "prefill_chunk_tokens": 2048,
            },
            "provider_or_gpu_used_this_turn": False,
            "checkpoint_shards_read_or_copied_this_turn": False,
            "actual_spend_usd": 0.0,
        },
        "direct_inputs": {name: manifest(path) for name, path in PATHS.items()},
        "selected_boundary": {
            "single_candidate": True,
            "producer": {
                "python_path": "Gemma4Attention.forward",
                "measured_symbol": "_qkv_norm_rope_inplace_kernel",
                "output": "in-place BF16 packed QKV projection",
            },
            "consumer": {
                "python_path": (
                    "TritonAttnBackend.forward_extend -> "
                    "SWAKVPool.set_kv_buffer -> MHATokenToKVPool.set_kv_buffer"
                ),
                "symbols": [
                    "Tensor.clone",
                    "Tensor.div_",
                    "Tensor.to(torch.float8_e5m2)",
                    "sglang.jit_kernel.kvcache.store_cache/store_kvcache",
                ],
                "output": "uint8-backed torch.float8_e5m2 NHD K/V cache",
            },
            "selection_evidence": {
                "label": "measured",
                "profile_seconds": validation["profile"]["profile_seconds"],
                "profile_requests": validation["profile"]["requests"],
                "qkv": chain["qkv"],
                "cache_chain": chain["cache_chain"],
                "retained_stack_removable_seconds": chain[
                    "retained_stack_removable_seconds"
                ],
                "retained_stack_eliminated_launches": chain[
                    "retained_stack_eliminated_launches"
                ],
                "why_local_clones_are_not_double_counted": (
                    "The qualified stack already retains the deferred-local-KV patch, "
                    "so the local protective clone pair is excluded. Global clones and "
                    "both classes' divide/cast/store chain remain charged."
                ),
                "why_synchronization_is_not_selected": (
                    "Prior trace-to-source evidence binds the apparent scheduler "
                    "cudaStreamSynchronize wall to dependent model-step completion; "
                    "it is not an independent producer/consumer boundary."
                ),
            },
        },
        "exact_geometry": {
            "common": {
                "layers": 60,
                "q_heads": 32,
                "qkv_input_dtype": "torch.bfloat16",
                "cache_dtype": "torch.float8_e5m2",
                "cache_storage_dtype": "torch.uint8",
                "cache_layout": "NHD",
                "cache_slot_dtype": "torch.int64",
                "kv_scales": {"key": 1.0, "value": 1.0},
                "rms_norm_eps": 1e-6,
                "observed_profile_token_rows": [118, 1409, 1631, 2048],
                "required_decode_row": 32,
            },
            "local": {
                "layer_count": 50,
                "layer_rule": "(layer_id + 1) % 6 != 0",
                "kv_heads": 16,
                "head_dim": 256,
                "qkv_shape": ["M", 16384],
                "key_value_view_shape": ["M", 16, 256],
                "candidate_grid": ["M", 64],
                "threads_per_cta": 128,
                "rope": {
                    "theta": 10000.0,
                    "type": "default",
                    "partial_rotary_factor": 1.0,
                },
            },
            "global": {
                "layer_count": 10,
                "layer_rule": "(layer_id + 1) % 6 == 0",
                "kv_heads": 4,
                "head_dim": 512,
                "qkv_shape": ["M", 20480],
                "key_value_view_shape": ["M", 4, 512],
                "candidate_grid": ["M", 40],
                "threads_per_cta": 128,
                "rope": {
                    "theta": 1000000.0,
                    "type": "proportional",
                    "partial_rotary_factor": 0.25,
                },
            },
        },
        "baseline_path": {
            "global": [
                "_qkv_norm_rope_inplace_kernel writes BF16 Q/K/V",
                "two BF16 protective clones",
                "two in-place scale divides",
                "two BF16-to-E5M2 casts",
                "store_kvcache indexed NHD write",
                "attention consumes the committed cache",
            ],
            "local_retained_stack": [
                "_qkv_norm_rope_inplace_kernel writes BF16 Q/K/V",
                "attention consumes live BF16 K/V before deferred commit",
                "two in-place scale divides",
                "two BF16-to-E5M2 casts",
                "store_kvcache indexed NHD write",
            ],
        },
        "candidate": {
            "name": "qkv_norm_rope_e5m2_cache_epilogue",
            "source_complete": True,
            "source_manifest": [manifest(path) for path in source_files],
            "installation": {
                "input_sha256": validation["source"][
                    "pinned_gemma4_causal_sha256"
                ],
                "patched_sha256": validation["source"][
                    "patched_gemma4_causal_sha256"
                ],
                "action": (
                    "The hash-gated installer replaces Gemma4Attention's "
                    "norm+RoPE span, commits E5M2 cache inside the K/V producer CTAs, "
                    "and sets the downstream save_kv_cache flag false."
                ),
            },
            "implementation": {
                "kernel": "_qkv_norm_rope_cache_kernel",
                "baseline_comparator": "qkv_norm_rope_inplace(WRITE_CACHE=False)",
                "candidate_entry": "qkv_norm_rope_cache_store(WRITE_CACHE=True)",
                "cache_resolver": "resolve_cache_destination",
                "new_ctas": 0,
                "new_intermediate_tensors": 0,
                "semantic_change": False,
                "fallback": "fail closed on source, dtype, layout, scale, or shape mismatch",
            },
        },
        "physical_model": {
            "label": "derived from exact trace geometry and source semantics",
            "useful_operations": {
                "producer_per_head": (
                    "D squares + (D-1) reductions + rsqrt + D normalization "
                    "multiplies; Q/K add D weight multiplies and 3D RoPE "
                    "multiply/add operations. This is unchanged from the accepted producer."
                ),
                "cache_scale_divides_per_token": {
                    "local": 8192,
                    "global": 4096,
                    "note": (
                        "These exact K+V element counts move from two standalone "
                        "BF16 div kernels into the producer epilogue; scale=1.0 is "
                        "compile-time and may fold to identity."
                    ),
                },
            },
            "bytes": chain["physical_bytes"],
            "byte_accounting": {
                "local_current_bytes_per_kv_element": 9,
                "global_current_bytes_per_kv_element": 13,
                "candidate_compulsory_cache_write_bytes_per_kv_element": 1,
                "local_avoided_bytes_per_kv_element": 8,
                "global_avoided_bytes_per_kv_element": 12,
            },
            "grid": {
                "measured_qkv_launches": 3660,
                "candidate_qkv_launches": 3660,
                "eliminated_following_launches": chain[
                    "retained_stack_eliminated_launches"
                ],
                "measured_registers_per_thread": {
                    "local": 22,
                    "global": 26,
                },
                "measured_dynamic_shared_memory_bytes": 16,
                "candidate_preregistered_resource_gate": {
                    "registers_per_thread_max": 32,
                    "spills": 0,
                    "dynamic_shared_memory_bytes_max": 16,
                },
            },
            "predicted_counter_movement": {
                "cuda_kernel_launch_count": -chain[
                    "retained_stack_eliminated_launches"
                ],
                "dram_bytes": -chain["physical_bytes"]["avoided_bytes"],
                "qkv_kernel_count": 0,
                "qkv_kernel_duration": (
                    "increase from E5M2 stores in K/V CTAs; must remain below "
                    "50% of the eliminated chain duration for the conservative gate"
                ),
                "registers_per_thread": "expected +0..6; reject above 32 or any spill",
                "l2_write_bytes": (
                    "one compulsory E5M2 K/V cache write remains; clone/div/cast "
                    "intermediate traffic disappears"
                ),
            },
        },
        "correctness_contract": {
            "accepted_producer_prior": {
                "source_terminal": manifest(PATHS["measured_qkv_terminal"]),
                "maximum_observed_candidate_nrmse": 1.026862082653679e-5,
                "maximum_observed_candidate_max_abs": 0.015625,
                "note": (
                    "Measured on exact local/global c32 decode and M=2048 prefill "
                    "against the FP32 oracle."
                ),
            },
            "target_consumer_must_pass": [
                "candidate QKV versus WRITE_CACHE=False QKV normalized RMSE <= 1e-5",
                "candidate K cache bytes equal the unfused E5M2 cache consumer",
                "candidate V cache bytes equal the unfused E5M2 cache consumer",
                "all local/global M in {32,118,1409,1631,2048} pass",
                "every cache result is read into the persisted checksum",
                "every case has positive median component reduction",
                "candidate source and pinned memory_pool hashes match before CUDA entry",
            ],
            "production_preconditions": [
                "no KV-shared layer",
                "NHD uint8-backed torch.float8_e5m2 pool",
                "explicit positive K/V scale",
                "integral one-slot-per-token mapping",
                "BF16 packed QKV with contiguous inner dimension",
            ],
        },
        "complete_request_bound": bound,
        "decision": {
            "classification": "source_complete_positive_requires_exact_h200_consumer",
            "target_crossed_offline": False,
            "admit_one_target_gpu_component_consumer": True,
            "admit_endpoint": False,
            "stop_rules": [
                "Stop negative on any correctness, source-hash, spill, or resource gate failure.",
                "Stop negative if any exact geometry has non-positive median component reduction.",
                "Only after all component cases pass may a director decide whether to admit one c32 endpoint pair.",
            ],
        },
        "target_gpu_consumer": {
            "type": "command",
            "working_directory": str(PROJECT),
            "required_environment": (
                "Pinned SGLang image above with this project mounted at the same "
                "absolute path; one director-authorized H200 pool claim is required "
                "outside this command."
            ),
            "command": (
                f"PYTHONPATH={PROJECT} python3 {PROJECT / 'exact_consumer.py'} "
                f"--output {PROJECT / 'artifacts/h200_exact_consumer/TERMINAL.json'} "
                f"--expected-source-sha256 {candidate_hash} "
                "--tokens 32 118 1409 1631 2048 --warmups 5 --iterations 31"
            ),
            "expected_terminal": str(
                PROJECT / "artifacts/h200_exact_consumer/TERMINAL.json"
            ),
        },
        "offline_validation": manifest(validation_path),
        "limitations": [
            "No candidate CUDA kernel was compiled or executed in this zero-GPU turn.",
            "The 50%-realization complete bound is a conservative admission model, not a measurement.",
            "The candidate cannot independently close the locked campaign target.",
        ],
    }
    atomic_json(output, result)


if __name__ == "__main__":
    main()
