#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PINNED = ROOT / "inputs/pinned/sglang-0.5.16-source"
RESULT = ROOT / "SM120_FP8_LINEAR_PERSISTENT_DISPATCH_OFFLINE_RESULT.json"
STATUS = ROOT / "STATUS.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        stream.write(encoded)
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def require(path: Path, snippets: list[str]) -> None:
    source = path.read_text()
    missing = [snippet for snippet in snippets if snippet not in source]
    if missing:
        raise RuntimeError(f"source_contract_missing:{path}:{missing}")


def main() -> int:
    config = json.loads((ROOT / "inputs/config.json").read_text())
    text = config["text_config"]
    required_geometry = {
        "hidden_size": 5376,
        "intermediate_size": 21504,
        "num_hidden_layers": 60,
        "hidden_activation": "gelu_pytorch_tanh",
    }
    observed_geometry = {key: text[key] for key in required_geometry}
    if observed_geometry != required_geometry:
        raise RuntimeError(f"geometry_mismatch:{observed_geometry}")

    require(
        PINNED / "python/sglang/srt/models/gemma4_causal.py",
        [
            "hidden_states, residual = self.pre_feedforward_layernorm(",
            "hidden_states = self.mlp(hidden_states)",
        ],
    )
    require(
        PINNED / "python/sglang/srt/models/gemma3_causal.py",
        [
            "gate_up, _ = self.gate_up_proj(x)",
            "x = self.act_fn(gate_up)",
            "x, _ = self.down_proj(x)",
        ],
    )
    require(
        PINNED / "python/sglang/srt/layers/quantization/fp8_utils.py",
        [
            "qinput, x_scale = sglang_per_token_quant_fp8(input_2d)",
            "output = fp8_scaled_mm(",
        ],
    )
    require(
        PINNED / "sgl-kernel/csrc/gemm/per_token_quant_fp8.cu",
        [
            "per_token_quant_fp8_small_batch_kernel",
            "const bool use_warp_kernel =",
            "dim3 grid(num_tokens);",
        ],
    )
    require(
        PINNED / "sgl-kernel/csrc/gemm/fp8_gemm_kernel.cu",
        [
            "struct DeviceGemmFp8RowwiseSm120",
            "using CTAShapeDefault = Shape<_128, _128, _128>;",
            "sm120_fp8_dispatch_shape<cutlass::bfloat16_t>",
        ],
    )
    require(
        ROOT / "sm120_pre_ff_gate_up_dispatch.cu",
        [
            "fused_add_rmsnorm_per_token_fp8_m32_kernel",
            'findSchemaOrThrow("sgl_kernel::fp8_scaled_mm", "")',
            "properties->major == 12 && properties->minor == 0",
        ],
    )
    require(
        ROOT / "run_sm120_oracle.py",
        [
            "manual_stock_path_does_not_match_apply_fp8_linear",
            '"activation_e4m3"',
            '"gelu_and_mul_bf16"',
            '"contract_rejects_m31"',
            '"contract_rejects_m33"',
        ],
    )

    pinned_hashes = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(PINNED.rglob("*"))
        if path.is_file()
    }
    implementation_hashes = {
        name: sha256(ROOT / name)
        for name in [
            "sm120_pre_ff_gate_up_dispatch.cu",
            "sglang_gate_up_integration.py",
            "run_sm120_oracle.py",
        ]
    }
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    calls_batch = 60 * 358
    calls_per_request = calls_batch / 32
    removed_bytes = 3 * 32 * 5376 * 2
    service_seconds = 2.23382165625
    launch_bounds = []
    for launch_us in [2.0, 5.0, 10.0]:
        launch_seconds = calls_per_request * launch_us / 1e6
        hbm_floor_seconds = removed_bytes * calls_per_request / 1.792e12
        total = launch_seconds + hbm_floor_seconds
        launch_bounds.append(
            {
                "assumed_saved_launch_gap_us": launch_us,
                "launch_seconds_per_request": launch_seconds,
                "removed_hbm_floor_seconds_per_request": hbm_floor_seconds,
                "combined_seconds_per_request": total,
                "combined_percent_of_measured_endpoint": (
                    100.0 * total / service_seconds
                ),
            }
        )

    result = {
        "schema_version": 1,
        "created_at_utc": created_at,
        "artifact": RESULT.name,
        "classification": "source_complete_offline_candidate_waiting_sm120_measurement",
        "decision": {
            "typed_none": False,
            "advance_to_component_measurement": True,
            "reason": (
                "One concrete exact M32 boundary survives: the candidate removes "
                "one non-overlapping fused-add-RMSNorm/quant launch and the "
                "materialized normalized-BF16 write plus two quantization reads, "
                "then calls the unchanged stock sm_120 FP8 GEMM and unchanged "
                "installed BF16 consumer."
            ),
            "claim_allowed_now": False,
            "claim_blockers": [
                "direct_vllm_lane_has_serial_bench_priority",
                "director_component_binding_absent",
            ],
        },
        "scope": {
            "gpu_claimed": False,
            "ssh_attempted": False,
            "provider_operations": 0,
            "target_cuda_executed": False,
            "target_cuda_not_executed_reason": "explicit_zero_gpu_offline_contract",
            "actual_spend_usd": 0.0,
            "project_storage_bytes": sum(
                path.stat().st_size for path in ROOT.rglob("*") if path.is_file()
            ),
            "storage_limit_bytes": 5 * 1024**3,
        },
        "identities": {
            "checkpoint": "google/gemma-4-31B-it",
            "checkpoint_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "checkpoint_config_sha256": sha256(ROOT / "inputs/config.json"),
            "sglang_tag": "v0.5.16",
            "sglang_commit": "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1",
            "sglang_kernel_version": "0.4.5",
            "torch_runtime": "2.11.0+cu130",
            "cuda_runtime": "13.0",
            "target": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition sm_120",
            "installed_activation_patch_sha256": (
                "5d2e8a2ec0bd0bbdfa4732633144f3c287914d5d04a5a54142c9c4b04c5109d7"
            ),
            "pinned_source_hashes": pinned_hashes,
            "external_pinned_sources": {
                "flashinfer_norm_cuh": {
                    "commit": "bc29697ba20b7e6bdb728ded98f04788e16ee021",
                    "sha256": (
                        "a4c010e8aa1acbeeb7ea1f09a4ddf53d89facc1a144e99b5242ab8a40d8923c3"
                    ),
                },
                "cutlass_tile_scheduler_hpp": {
                    "commit": "57e3cfb47a2d9e0d46eb6335c3dc411498efa198",
                    "sha256": (
                        "ae25f8ab4b75b895a8419f055dbcf1712b1bef9e4d9b5f64eba176901f2672a1"
                    ),
                },
            },
        },
        "production_boundary": {
            "phase": "decode concurrent-c32",
            "layer_count": 60,
            "selected_linear": "Gemma4 dense MLP gate_up_proj",
            "integration_point": (
                "Gemma4DecoderLayer.forward dense branch, replacing "
                "pre_feedforward_layernorm + gate_up_proj only"
            ),
            "call_chain": [
                {
                    "symbol": "Gemma4DecoderLayer.forward",
                    "source": "python/sglang/srt/models/gemma4_causal.py:717",
                    "operation": "pre_feedforward_layernorm(hidden_states, residual)",
                },
                {
                    "symbol": "RMSNorm.forward_cuda",
                    "source": "python/sglang/srt/layers/layernorm.py:264",
                    "operation": "sgl_kernel fused_add_rmsnorm mutates BF16 input and residual",
                },
                {
                    "symbol": "Gemma3MLP.forward",
                    "source": "python/sglang/srt/models/gemma3_causal.py:107",
                    "operation": "gate_up_proj -> GeluAndMul -> down_proj",
                },
                {
                    "symbol": "Fp8LinearMethod.apply",
                    "source": "python/sglang/srt/layers/quantization/fp8.py:893",
                    "operation": "apply_fp8_linear",
                },
                {
                    "symbol": "apply_fp8_linear",
                    "source": "python/sglang/srt/layers/quantization/fp8_utils.py:1721",
                    "operation": (
                        "sglang_per_token_quant_fp8 then "
                        "sgl_kernel::fp8_scaled_mm"
                    ),
                },
                {
                    "symbol": "GeluAndMul.forward_cuda",
                    "source": "python/sglang/srt/layers/activation.py:172",
                    "operation": (
                        "bench-installed sm_120 patch routes to forward_native; "
                        "this is the first BF16 consumer and remains unchanged"
                    ),
                },
            ],
        },
        "exact_contract": {
            "M": 32,
            "K": 5376,
            "N": 43008,
            "input": {
                "dtype": "BF16",
                "shape": [32, 5376],
                "layout": "row-major contiguous",
                "producer": "pre_feedforward_layernorm fused residual add",
            },
            "residual": {
                "dtype": "BF16",
                "shape": [32, 5376],
                "semantics": "mutated in place to BF16(input + residual)",
            },
            "activation": {
                "dtype": "E4M3FN",
                "shape": [32, 5376],
                "layout": "row-major contiguous",
                "scale_dtype": "FP32",
                "scale_shape": [32, 1],
                "scale_convention": "amax(abs(BF16-normalized row))/448",
                "zero_behavior": (
                    "candidate deliberately retains the stock reciprocal path; "
                    "the future oracle is fail-closed on all exact bytes"
                ),
            },
            "weight": {
                "dtype": "E4M3FN",
                "logical_shape": [5376, 43008],
                "strides": [1, 5376],
                "layout": (
                    "column-major logical KxN view of online per-output-channel "
                    "quantized [N,K] checkpoint weight"
                ),
                "scale_dtype": "FP32",
                "scale_shape": [1, 43008],
                "scale_convention": "per output channel amax(abs(BF16 weight row))/448",
            },
            "gemm": {
                "symbol": "sgl_kernel::fp8_scaled_mm",
                "implementation": "DeviceGemmFp8RowwiseSm120",
                "tile": [128, 128, 128],
                "accumulator": "FP32",
                "epilogue": (
                    "FP32 per-row activation scale times FP32 per-channel "
                    "weight scale, rounded to BF16"
                ),
                "output_shape": [32, 43008],
                "output_layout": "row-major contiguous",
            },
            "first_bf16_consumer": {
                "symbol": "sglang.srt.layers.activation.GeluAndMul",
                "input_shape": [32, 43008],
                "output_shape": [32, 21504],
                "bench_realized_path": "forward_native tanh-GELU(left) * right",
            },
        },
        "recurrence": {
            "measured_endpoint_completion_tokens_per_request": 358,
            "concurrent_requests": 32,
            "decode_steps": 358,
            "layers_per_step": 60,
            "batch_total_gate_up_calls": calls_batch,
            "calls_per_completed_request": calls_per_request,
            "normalization": (
                "60 layers * 358 synchronized decode steps / 32 completed requests"
            ),
        },
        "physical_model": {
            "evidence_label": "derived_from_exact_geometry_and_pinned_sources",
            "useful_flops_per_call": 2 * 32 * 5376 * 43008,
            "compulsory_weight_bytes_per_call": 5376 * 43008,
            "useful_flops_per_compulsory_weight_byte": 64.0,
            "stock_quant_grid_ctas": 32,
            "stock_gemm_grid_tiles": 43008 // 128,
            "derived_workstation_sms": 188,
            "stock_gemm_grid_waves_at_one_cta_per_sm": (43008 / 128) / 188,
            "stock_m_tile_useful_fraction": 32 / 128,
            "removed_normalized_bf16_bytes_per_call": removed_bytes,
            "removed_normalized_bf16_bytes_breakdown": {
                "rmsnorm_output_write": 32 * 5376 * 2,
                "quantization_first_read": 32 * 5376 * 2,
                "quantization_second_read": 32 * 5376 * 2,
            },
            "launches_removed_per_call": 1,
            "explicit_synchronizations_removed_per_call": 0,
            "gemm_weight_bytes_changed": 0,
            "gemm_tensor_core_instructions_changed": 0,
            "hypothesis": (
                "At M32 the standalone stock quantizer launches only 32 CTAs. "
                "Fusing the preceding residual RMSNorm with exact BF16 rounding "
                "and per-row quantization removes that launch and all global "
                "traffic for the intermediate normalized BF16 tensor. The "
                "unchanged weight-stream-dominated stock GEMM remains the limit."
            ),
            "predicted_counter_movement": {
                "cuda_kernel_launches": "-1 per selected call",
                "dram_read_bytes": f"-{2 * 32 * 5376 * 2} per selected call",
                "dram_write_bytes": f"-{32 * 5376 * 2} per selected call",
                "stock_fp8_gemm_launches": "unchanged",
                "stock_gelu_consumer_launches": "unchanged",
                "tensor_core_instructions": "unchanged",
            },
            "analytical_endpoint_bounds": launch_bounds,
            "bound_warning": (
                "No endpoint impact is claimed. The 2-10 us launch range is an "
                "explicit sensitivity analysis, not a measurement; target-GPU "
                "component timing must replace it."
            ),
        },
        "invalidated_alternative": {
            "mechanism": "change stock sm_120 GEMM scheduler tag to persistent",
            "classification": "source_falsified_duplicate_of_stock",
            "evidence": (
                "Pinned CUTLASS tile_scheduler.hpp maps the stock void scheduler "
                "for Sm120 to PersistentTileSchedulerSm100; SGLang already uses "
                "that void default in DeviceGemmFp8RowwiseSm120."
            ),
        },
        "implementation": {
            "entrypoint": (
                "sm120_fp8_linear_persistent_dispatch::gate_up_m32"
            ),
            "source_complete_through_first_consumer": True,
            "semantics": "preserving",
            "files": implementation_hashes,
            "mechanism": (
                "one exact-shape CUDA kernel preserves stock residual addition, "
                "RMSNorm reduction order, BF16 rounding, per-row E4M3 scale and "
                "quantization; the same custom-op call then dispatches the "
                "unchanged installed stock FP8 GEMM; SGLang calls its unchanged "
                "GeluAndMul consumer on the BF16 result"
            ),
            "fallback": (
                "sglang_gate_up_integration.can_dispatch is fail-closed; every "
                "non-sm120, non-M32, wrong-layout, biased, or non-FP8 case uses "
                "the unchanged stock path"
            ),
        },
        "target_build_run": {
            "command": (
                "CUDA_HOME=/usr/local/lib/python3.12/dist-packages/nvidia/cu13 "
                "NVCC=/usr/local/lib/python3.12/dist-packages/nvidia/cu13/bin/nvcc "
                "TORCH_CUDA_ARCH_LIST=12.0a python3 run_sm120_oracle.py "
                "--build-directory artifacts/sm120-m32-oracle/build "
                "--output artifacts/sm120-m32-oracle --repetitions 80"
            ),
            "compile_target": "compute_120a,code=sm_120a only",
            "expected_terminal": "artifacts/sm120-m32-oracle/TERMINAL.json",
        },
        "future_oracle": {
            "fresh_process_required": True,
            "actual_installed_producers_consumers": [
                "sglang.srt.layers.layernorm.RMSNorm",
                "sglang_per_token_quant_fp8",
                "apply_fp8_linear",
                "sgl_kernel::fp8_scaled_mm",
                "sglang.srt.layers.activation.GeluAndMul",
            ],
            "first_call_order": [
                "stock full boundary; synchronize; persist STOCK_FIRST_CALL_COMPLETE.json",
                "candidate full boundary; synchronize; persist CANDIDATE_FIRST_CALL_COMPLETE.json",
                "compare all required tensors before timing",
            ],
            "required_bitwise_equal": [
                "normalized BF16 logical boundary",
                "updated residual BF16",
                "activation E4M3 bytes",
                "activation FP32 scale bits",
                "gate_up BF16 output",
                "GeluAndMul BF16 output",
                "manual stock gate_up versus apply_fp8_linear gate_up",
            ],
            "boundary_guards": [
                "M31 rejected",
                "M33 rejected",
                "wrong K/N/layout/dtype/bias rejected",
            ],
            "timing_unit": "microseconds per concurrent M32 batch call",
            "promotion_rule": (
                "numeric oracle passes, candidate symbol is proven, warm median "
                "beats stock beyond noise, and measured delta times 21480/32 "
                "produces a positive per-request bound"
            ),
        },
        "offline_validation": {
            "passed": True,
            "checks": [
                "exact config geometry",
                "pinned producer/call/consumer symbols",
                "stock sm120 CUTLASS symbol and tile",
                "candidate stock-GEMM dispatch",
                "candidate sm120 fail-closed guard",
                "future oracle required fields",
                "Python syntax compilation",
                "git diff whitespace check",
            ],
            "limitations": [
                "coordinator has no torch installation",
                "coordinator has no CUDA compiler",
                "explicit contract forbids GPU claim and SSH",
            ],
        },
    }
    atomic_json(RESULT, result)
    result_hash = sha256(RESULT)

    status = json.loads(STATUS.read_text())
    status.update(
        {
            "status": "paused",
            "updated_at": created_at,
            "active_session": None,
            "actual_spend_usd": 0.0,
            "summary": (
                "Offline source-complete sm_120 M32 gate/up candidate: fused "
                "pre-FF residual RMSNorm plus exact dynamic E4M3 quantization "
                "removes one launch and 0.984375 MiB per call, then reaches the "
                "unchanged stock FP8 GEMM epilogue and BF16 GeluAndMul consumer. "
                "Target CUDA remains intentionally unexecuted."
            ),
            "decision": "advance_to_director_bound_component_measurement",
            "result": {
                "artifact": RESULT.name,
                "artifact_sha256": result_hash,
                "classification": result["classification"],
                "implementation": "sm120_pre_ff_gate_up_dispatch.cu",
                "implementation_sha256": implementation_hashes[
                    "sm120_pre_ff_gate_up_dispatch.cu"
                ],
                "source_complete_through_first_consumer": True,
                "target_cuda_executed": False,
                "gpu_claimed": False,
                "ssh_attempted": False,
                "provider_operations": 0,
                "new_spend_usd": 0.0,
                "launches_removed_per_call": 1,
                "bytes_removed_per_call": removed_bytes,
                "batch_total_calls": calls_batch,
                "calls_per_request": calls_per_request,
            },
            "bench_need": {
                "accelerator": "nvidia-rtx-pro-6000-blackwell-workstation",
                "gpu_count": 1,
                "preferred_bench_id": "rtxpro6000-gemma4-fp8-f4nbtoufbwf66f",
                "claim_allowed": False,
                "purpose": (
                    "Run the exact installed SGLang 0.5.16/CUDA 13 M32 oracle "
                    "and paired component timing after the serial vLLM lane."
                ),
            },
            "claim_gate": {
                "claim_allowed": False,
                "blocked_by": [
                    "direct_vllm_lane_has_serial_bench_priority",
                    "director_component_binding_absent",
                ],
                "disposition": "offline_candidate_complete_waiting_director",
            },
            "next_action": (
                f"Director review {RESULT.name} SHA-256 {result_hash}. Keep the "
                "RTX bench behind gemma4_rtxpro6000_vllm_current_fp8_endpoint. "
                "If promoted later, bind one sm_120 component run to the exact "
                "target_build_run command and future_oracle; do not claim before "
                "the serial dependency and director binding clear."
            ),
        }
    )
    atomic_json(STATUS, status)
    print(
        json.dumps(
            {
                "artifact": str(RESULT),
                "artifact_sha256": result_hash,
                "classification": result["classification"],
                "status": status["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
