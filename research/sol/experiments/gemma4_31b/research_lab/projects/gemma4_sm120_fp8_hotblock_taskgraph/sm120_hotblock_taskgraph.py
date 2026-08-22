#!/usr/bin/env python3
"""Exact Gemma 4 M32 stock-semantics CUDA-graph discriminator for SM120."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable

M = 32
K = 5376
N = 43008
INTERMEDIATE = 21504
LAYERS = 60
DECODE_STEPS = 358
REQUESTS = 32
EPSILON = 1e-6
SEED = 20260729
FP8_MAX = 448.0
SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
CHECKPOINT_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
PROJECT = Path(__file__).resolve().parent

EXPECTED_FILES = {
    "evidence/pinned_endpoint/consumers.jsonl": "218f68c0b4c9f21a8587eef919f6534c1aa683d786e3ee0741c7b6642bc12a1a",
    "evidence/current_support/sglang_decode_cuda_graph.py": "ec7d7613fbb592954f2f2aa1b1641a1583c6f7f9c69ed8133e7a7d30abb1633c",
    "evidence/current_support/sglang_fp8_gemm_kernel.cu": "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
    "evidence/current_support/sglang_full_graph_backend.py": "141ed3003b076191f9a0b35e4d633c6e00d3ed520411a31e034446180a040194",
    "evidence/current_support/sglang_test_fp8_gemm_sm120.py": "eb7ba7aef9daad811aa6fed3516fe01c749d1f7cdea1966b95b0c87d5dcc2eb2",
    "evidence/current_support/vllm_cuda_graph.py": "cbc474f9098386d2eef2e3ff61364c611fbc1338d9c259ad5a24439aa7f06412",
    "evidence/current_support/vllm_gpu_model_runner.py": "b351c375388cc70cc2bba6b4ab9ce2a0eb6ab3cb8e508946e4f17a06ea42e257",
    "inputs/component/config.json": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    "inputs/component/layer0-rms-qkv-gate-up.safetensors": "8230f5dcca70dd7e3b6f63d9614fc9b7ece632b539da00813b1a5af1d41923af",
    "inputs/source/activation.cu": "dffb5a9cbbb4d26a75e7e8aea0c0acfa2e68c64158466854fd6d54262103a7d6",
    "inputs/source/activation.py": "e0bfddf2c5ad0ba62df2c68b5682518f11f0592c8a51f144a363ea5ddcc772ca",
    "inputs/source/cuda_graph_runner.py": "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e",
    "inputs/source/fp8.py": "c7368db317513e5823283eb5567d15fdb742c3b01a98bfc483cb500291b4285a",
    "inputs/source/fp8_gemm_kernel.cu": "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
    "inputs/source/fp8_kernel.py": "95882e4fed8ac449240ffc8e62b13176bb5057db6c77a06cdfcfffa5f5d89a06",
    "inputs/source/fp8_utils.py": "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9",
    "inputs/source/gemma3_causal.py": "a9827bde583c5b8b0abfeaced097c4e9d060fb99ec2961b4f9c66173d3027282",
    "inputs/source/gemma4_causal.py": "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    "inputs/source/layernorm.py": "e31523f8090d41e642761617b7253b5a2833676dfd35dad86ae9c18e69144c3b",
    "inputs/source/per_token_quant_fp8.cu": "c8a3e755dc165cecfa09232bed58e8b36010061f050acf2f82722b75c3c1edb8",
    "inputs/source/server_args.py": "cc4f440c0987d7a6ee6868f3e41271809c5c1d3015ddcfbd6f79dc19367d5c8d",
    "inputs/source/sgl_kernel_elementwise.py": "5af8a849dff586835b679618c568940afe8d6859b329268311ff5538f1b7356a",
    "inputs/source/sgl_kernel_gemm.py": "e9593bc5761cc5315b8da7fe59125a829b4c8ce85f4855588ff80fab31cd46a9",
}

EXPECTED_RUNTIME_MODULES = {
    "sglang.srt.layers.activation": EXPECTED_FILES["inputs/source/activation.py"],
    "sglang.srt.layers.layernorm": EXPECTED_FILES["inputs/source/layernorm.py"],
    "sglang.srt.layers.quantization.fp8": EXPECTED_FILES["inputs/source/fp8.py"],
    "sglang.srt.layers.quantization.fp8_kernel": EXPECTED_FILES[
        "inputs/source/fp8_kernel.py"
    ],
    "sglang.srt.layers.quantization.fp8_utils": EXPECTED_FILES[
        "inputs/source/fp8_utils.py"
    ],
    "sglang.srt.model_executor.cuda_graph_runner": EXPECTED_FILES[
        "inputs/source/cuda_graph_runner.py"
    ],
    "sglang.srt.models.gemma3_causal": EXPECTED_FILES[
        "inputs/source/gemma3_causal.py"
    ],
    "sglang.srt.models.gemma4_causal": EXPECTED_FILES[
        "inputs/source/gemma4_causal.py"
    ],
    "sglang.srt.server_args": EXPECTED_FILES["inputs/source/server_args.py"],
    "sgl_kernel.elementwise": EXPECTED_FILES["inputs/source/sgl_kernel_elementwise.py"],
    "sgl_kernel.gemm": EXPECTED_FILES["inputs/source/sgl_kernel_gemm.py"],
}

CURRENT_SUPPORT = {
    "cutlass": {
        "head": "7ac18190ca2d876117abd1c06bc788e87f8c8734",
        "support": "SM120 E4M3 and Blackwell GEMM templates are present; no cross-operator RMSNorm/quant/GEMM task primitive.",
        "url": "https://github.com/NVIDIA/cutlass",
    },
    "cuda_graph": {
        "support": "A captured workflow replays through one submission while retaining dependency-ordered kernel nodes; child graphs do not delete those nodes.",
        "url": "https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/cuda-graphs.html",
    },
    "cuda_pdl": {
        "support": "Programmatic graph edges require a producer trigger and a consumer cudaGridDependencySynchronize; neither exists in the pinned quantizer/CUTLASS GEMM pair.",
        "url": "https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/programmatic-dependent-launch.html",
    },
    "cublaslt": {
        "support": "Current cuBLASLt documents FP8 outer-vector scaling, but the pinned SGLang SM120 path is CUTLASS and cuBLASLt does not aggregate the preceding stock RMSNorm/quantizer.",
        "url": "https://docs.nvidia.com/cuda/cublas/",
    },
    "sglang": {
        "head": "b21cc8eb9b86f1d639ed6021f7411ef769909281",
        "source_hashes": {
            "decode_cuda_graph_runner.py": "ec7d7613fbb592954f2f2aa1b1641a1583c6f7f9c69ed8133e7a7d30abb1633c",
            "fp8_gemm_kernel.cu": "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
            "full_cuda_graph_backend.py": "141ed3003b076191f9a0b35e4d633c6e00d3ed520411a31e034446180a040194",
            "test_fp8_gemm_sm120.py": "eb7ba7aef9daad811aa6fed3516fe01c749d1f7cdea1966b95b0c87d5dcc2eb2",
        },
        "support": "Current upstream retains an SM120 FP8 GEMM test and a full backend that captures the entire model forward and calls graph.replay().",
        "url": "https://github.com/sgl-project/sglang",
    },
    "vllm": {
        "head": "32a423ac0aad67f94f93e97f73338f484b55faec",
        "source_hashes": {
            "cuda_graph.py": "cbc474f9098386d2eef2e3ff61364c611fbc1338d9c259ad5a24439aa7f06412",
            "gpu_model_runner.py": "b351c375388cc70cc2bba6b4ab9ce2a0eb6ab3cb8e508946e4f17a06ea42e257",
        },
        "support": "Current upstream dispatches uniform decode through CUDAGraphMode.FULL when compatible, so it exposes no distinct nested hot-block replay boundary either.",
        "url": "https://github.com/vllm-project/vllm",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def verify_project_inputs() -> dict[str, str]:
    observed = {name: sha256(PROJECT / name) for name in EXPECTED_FILES}
    mismatches = {
        name: {"expected": EXPECTED_FILES[name], "observed": observed[name]}
        for name in EXPECTED_FILES
        if EXPECTED_FILES[name] != observed[name]
    }
    if mismatches:
        raise RuntimeError(f"project_input_hash_mismatch:{json.dumps(mismatches)}")
    return observed


def assert_source_trace() -> None:
    fragments = {
        "inputs/source/gemma4_causal.py": [
            "hidden_states, residual = self.pre_feedforward_layernorm(",
            "hidden_states = self.mlp(hidden_states)",
        ],
        "inputs/source/gemma3_causal.py": [
            "gate_up, _ = self.gate_up_proj(x)",
            "x = self.act_fn(gate_up)",
        ],
        "inputs/source/fp8_utils.py": [
            "qinput, x_scale = sglang_per_token_quant_fp8(input_2d)",
            "output = fp8_scaled_mm(",
        ],
        "inputs/source/fp8_kernel.py": [
            "x_s = torch.empty(",
            "sgl_per_token_quant_fp8(x, x_q, x_s)",
        ],
        "inputs/source/fp8_gemm_kernel.cu": [
            "DeviceGemmFp8RowwiseSm120",
            "using CTAShapeDefault = Shape<_128, _128, _128>;",
            "using AccumElementType = float;",
            "sm120_fp8_dispatch_shape<cutlass::bfloat16_t>",
        ],
        "inputs/source/cuda_graph_runner.py": [
            "self.capture_forward_mode = ForwardMode.DECODE",
            "self.graphs[graph_key].replay()",
        ],
        "inputs/source/server_args.py": [
            "list(range(16, 257, 8))",
            "disable_cuda_graph: bool = False",
        ],
        "evidence/current_support/sglang_full_graph_backend.py": [
            "captures the entire model forward",
            "self._graphs[shape_key].replay()",
        ],
        "evidence/current_support/sglang_test_fp8_gemm_sm120.py": [
            "class TestFP8PerTensorGemmSM120Auto",
            "--fp8-gemm-backend",
        ],
        "evidence/current_support/vllm_gpu_model_runner.py": [
            "CUDAGraphMode.FULL",
            "uniform_decode",
        ],
        "evidence/pinned_endpoint/consumers.jsonl": [
            '"prefix":"model.language_model.layers.0.mlp.gate_up_proj"',
            '"weight":{"dtype":"torch.float8_e4m3fn","shape":[5376,43008]}',
            '"weight_scale":{"dtype":"torch.float32","shape":[1,43008]}',
        ],
    }
    failures = []
    for name, required in fragments.items():
        text = (PROJECT / name).read_text()
        for fragment in required:
            if fragment not in text:
                failures.append({"path": name, "fragment": fragment})
    if failures:
        raise RuntimeError(f"source_trace_fragment_missing:{json.dumps(failures)}")


def description() -> dict[str, Any]:
    hashes = verify_project_inputs()
    assert_source_trace()
    implementation_hash = sha256(Path(__file__).resolve())
    calls_per_batch = LAYERS * DECODE_STEPS
    calls_per_request = calls_per_batch / REQUESTS
    hidden_bytes = M * K * 2
    q_bytes = M * K
    scale_bytes = M * 4
    weight_bytes = K * N
    gate_up_bytes = M * N * 2
    gelu_bytes = M * INTERMEDIATE * 2
    rms_compulsory = 4 * hidden_bytes + K * 2
    quant_compulsory = hidden_bytes + q_bytes + scale_bytes
    quant_implementation = 2 * hidden_bytes + q_bytes + scale_bytes
    gemm_compulsory = q_bytes + scale_bytes + weight_bytes + N * 4 + gate_up_bytes
    gelu_compulsory = gate_up_bytes + gelu_bytes
    return {
        "schema_version": 1,
        "name": "gemma4_sm120_m32_stock_pre_ff_gate_up_taskgraph",
        "semantic_class": "bitwise_stock_only",
        "phase": "decode_m32",
        "identities": {
            "checkpoint": f"google/gemma-4-31B-it@{CHECKPOINT_REVISION}",
            "sglang_commit": SGLANG_COMMIT,
            "target": {
                "accelerator": "nvidia-rtx-pro-6000-blackwell-server",
                "compute_capability": [12, 0],
                "sms": 188,
            },
            "project_input_sha256": hashes,
            "current_support": CURRENT_SUPPORT,
        },
        "source_trace": [
            {
                "order": 1,
                "symbols": [
                    "sglang.srt.models.gemma4_causal.Gemma4DecoderLayer.forward",
                    "pre_feedforward_layernorm(hidden_states, residual)",
                    "sgl_kernel.fused_add_rmsnorm",
                ],
                "contract": "in-place BF16 residual add and stock FP32 RMS reduction/rsqrt with BF16 normalized output and BF16 residual_out",
            },
            {
                "order": 2,
                "symbols": [
                    "sglang.srt.layers.quantization.fp8.Fp8LinearMethod.apply",
                    "sglang.srt.layers.quantization.fp8_utils.apply_fp8_linear",
                    "sglang.srt.layers.quantization.fp8_kernel.sglang_per_token_quant_fp8",
                    "sgl_kernel.sgl_per_token_quant_fp8",
                    "per_token_quant_fp8_small_batch_kernel",
                ],
                "contract": "row-major contiguous E4M3 [32,5376] plus contiguous FP32 dequantization scale [32,1]; on 188-SM SM120, M32 selects per_token_quant_fp8_small_batch_kernel, which writes scale=max_abs/448 with no epsilon floor and q=saturating_e4m3(clamp(x/scale,-448,448))",
            },
            {
                "order": 3,
                "symbols": [
                    "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
                    "sgl_kernel.fp8_scaled_mm",
                    "sm120_fp8_dispatch_shape<cutlass::bfloat16_t>",
                    "DeviceGemmFp8RowwiseSm120",
                ],
                "contract": "A row-major E4M3 [32,5376], B column-major E4M3 [5376,43008] stride [1,5376], FP32 A [32,1] and B [1,43008] scales, FP32 accumulation, BF16 [32,43008] output",
            },
            {
                "order": 4,
                "symbols": [
                    "sglang.srt.models.gemma3_causal.Gemma3MLP.forward",
                    "sglang.srt.layers.activation.GeluAndMul.forward_cuda",
                    "sgl_kernel.gelu_tanh_and_mul",
                ],
                "contract": "first real BF16 consumer reads [32,43008] and emits BF16 [32,21504] without moving any preceding rounding boundary",
            },
        ],
        "task_graph": {
            "nodes": [
                {
                    "id": "stock_residual_rmsnorm",
                    "implementation": "sgl_kernel.fused_add_rmsnorm",
                    "outputs": ["normalized_bf16[32,5376]", "residual_out_bf16[32,5376]"],
                },
                {
                    "id": "stock_per_token_e4m3",
                    "depends_on": ["stock_residual_rmsnorm"],
                    "implementation": "sgl_kernel.sgl_per_token_quant_fp8",
                    "outputs": ["activation_e4m3[32,5376]", "scale_fp32[32,1]"],
                },
                {
                    "id": "stock_sm120_scaled_mm",
                    "depends_on": ["stock_per_token_e4m3"],
                    "implementation": "DeviceGemmFp8RowwiseSm120<128x128x128,cluster=1x1x1>",
                    "outputs": ["gate_up_bf16[32,43008]"],
                },
                {
                    "id": "stock_first_bf16_consumer",
                    "depends_on": ["stock_sm120_scaled_mm"],
                    "implementation": "sgl_kernel.gelu_tanh_and_mul",
                    "outputs": ["gelu_mul_bf16[32,21504]"],
                },
            ],
            "capture": "torch.cuda.CUDAGraph on one current stream after first-call completion",
            "replay": "one graph.replay() on the same stream with fixed-address input/weight storage",
            "copies": "case-to-static input copies stay outside graph and outside timing",
            "calls_per_decode_step": LAYERS,
            "calls_per_c32_batch": calls_per_batch,
            "calls_per_completed_request": calls_per_request,
        },
        "geometry": {
            "m": M,
            "k": K,
            "n": N,
            "intermediate": INTERMEDIATE,
            "epsilon": EPSILON,
            "layouts": {
                "activation_bf16": {"shape": [M, K], "stride": [K, 1]},
                "activation_e4m3": {"shape": [M, K], "stride": [K, 1]},
                "activation_scale_fp32": {"shape": [M, 1], "stride": [1, 1]},
                "weight_e4m3": {"shape": [K, N], "stride": [1, K]},
                "weight_scale_fp32": {"shape": [1, N], "stride": [N, 1]},
                "gate_up_bf16": {"shape": [M, N], "stride": [N, 1]},
            },
        },
        "physical_model": {
            "label": "derived_from_exact_geometry_and_pinned_source",
            "useful_gate_up_flops_per_call": 2 * M * K * N,
            "compulsory_bytes_per_call": {
                "residual_rmsnorm": rms_compulsory,
                "quant_one_read_lower_bound": quant_compulsory,
                "quant_stock_two_pass_implementation": quant_implementation,
                "scaled_mm": gemm_compulsory,
                "gelu_mul": gelu_compulsory,
                "stock_total_with_quant_two_pass": (
                    rms_compulsory
                    + quant_implementation
                    + gemm_compulsory
                    + gelu_compulsory
                ),
            },
            "stock_bytes_per_c32_batch_with_no_cache_credit": (
                rms_compulsory
                + quant_implementation
                + gemm_compulsory
                + gelu_compulsory
            )
            * calls_per_batch,
            "stock_bytes_per_request_with_no_cache_credit": (
                rms_compulsory
                + quant_implementation
                + gemm_compulsory
                + gelu_compulsory
            )
            * calls_per_request,
        },
        "oracle": {
            "required_before_timing": True,
            "comparison": "torch.equal and dtype/shape/stride equality over every element",
            "cases": [
                "production_random",
                "zero_residual",
                "zero_post_attention",
                "tiny_finite",
                "high_amplitude_finite",
            ],
            "fields": [
                "normalized_bf16",
                "activation_e4m3",
                "scale_fp32",
                "residual_out_bf16",
                "gate_up_bf16",
                "gelu_mul_bf16",
            ],
            "failure": "persist typed bitwise_mismatch and do not enter timing",
        },
        "predicted_movement": {
            "standalone_discriminator_only": {
                "host_submission_boundaries_per_call": {"stock": 4, "graph": 1},
                "device_kernel_nodes_delta": 0,
                "tensor_core_instructions_delta": 0,
                "dram_and_l2_bytes_delta": 0,
                "rounding_or_scale_bytes_changed": False,
            },
            "bound_sglang_decode_endpoint": {
                "outer_owner": [
                    "CudaGraphRunner.capture_forward_mode=ForwardMode.DECODE",
                    "capture batch-size 32",
                    "CudaGraphRunner.graphs[graph_key].replay()",
                ],
                "graph_launches_removed_per_decode_step": 0,
                "host_cuda_api_calls_removed_per_selected_call": 0,
                "synchronizations_removed_per_selected_call": 0,
                "bytes_removed_per_selected_call": 0,
                "batch_total_service_seconds_delta_bound": 0.0,
                "seconds_per_completed_request_delta_bound": 0.0,
            },
        },
        "integration": {
            "standalone_entrypoint": str(Path(__file__).name),
            "exact_insertion_point": "Gemma4DecoderLayer.forward at pre_feedforward_layernorm -> Gemma3MLP.gate_up_proj -> GeluAndMul",
            "disposition": "no_non_overlapping_boundary",
            "reason": "the pinned production decode path already captures the whole M32 model forward, including all four stock nodes, into one outer graph replay",
            "why_not_child_graph": "a child node retains all stock device nodes and replaces no outer host submission; it adds indirection and fixed-address ownership",
            "why_not_pdl": "the pinned per-token quantizer has no programmatic completion trigger and the pinned SM120 GEMM has no grid-dependency wait, so adding only an edge is invalid",
        },
        "implementation": {
            "path": str(Path(__file__).name),
            "sha256": implementation_hash,
            "source_complete_through_first_bf16_consumer": True,
            "offline_commands": [
                "python3 sm120_hotblock_taskgraph.py --describe",
                "python3 sm120_hotblock_taskgraph.py --export <fresh-output.json>",
            ],
            "sm120_target_run_command": (
                "PYTHONPATH=/sgl-workspace/sglang/python:"
                "/sgl-workspace/sglang/sgl-kernel/python "
                "CUDA_VISIBLE_DEVICES=0 python3 sm120_hotblock_taskgraph.py "
                "--run artifacts/sm120-hotblock-$(date -u +%Y%m%dT%H%M%SZ) "
                "--checkpoint inputs/component --warmup 8 --repeats 40"
            ),
            "target_cuda_status": "implemented_not_run_explicit_zero_gpu_contract",
        },
        "measured": {
            "label": "measured_offline",
            "project_local_hashes_verified": len(hashes),
            "offline_source_trace_resolved": True,
            "gpu_seconds": 0,
            "endpoint_requests": 0,
            "provider_operations": 0,
        },
        "evidence_classes": {
            "measured": [
                "the retained pinned endpoint audit records M32 gate_up input [32,5376], weight [5376,43008], activation scale [32,1], weight scale [1,43008], and BF16 output",
                "all project-local source, support, checkpoint-component, and endpoint-audit hashes verified offline",
            ],
            "source_backed": [
                "the pinned SGLang symbols and source fragments define the exact four-node path and numerical boundaries",
                "the pinned and current graph-runner sources place uniform decode M32 inside a full-model CUDA graph replay",
            ],
            "derived": [
                "calls per c32 batch/request and no-cache physical-byte totals derive from the fixed campaign shape and exact source geometry",
                "a child graph preserves all device nodes and therefore has zero endpoint launch, synchronization, and byte savings under the outer graph",
            ],
            "inferred": [
                "the standalone graph should reduce four Python-level submissions to one only when run outside the production outer graph; target timing remains unmeasured",
            ],
        },
        "decision": {
            "classification": "typed_none_no_non_overlapping_sm120_runtime_boundary",
            "promote": False,
            "reason": "the working standalone exact-stock graph is strictly contained by the existing full decode CUDA graph",
            "reopen_condition": "an exact RTX PRO 6000 endpoint trace proves decode-M32 ran outside CudaGraphRunner or identifies a stock host synchronization between these nodes",
        },
        "scope": {
            "gpu_claimed": False,
            "provider_operations": 0,
            "new_spend_usd": 0.0,
            "scientific_sample_consumed": False,
        },
    }


def verify_runtime_modules() -> tuple[dict[str, str], dict[str, str]]:
    observed = {}
    paths = {}
    for module_name, expected in EXPECTED_RUNTIME_MODULES.items():
        module = importlib.import_module(module_name)
        path = Path(module.__file__).resolve()
        observed[module_name] = sha256(path)
        paths[module_name] = str(path)
        if observed[module_name] != expected:
            raise RuntimeError(
                f"pinned_runtime_source_mismatch:{module_name}:"
                f"{observed[module_name]}:{expected}"
            )
    return observed, paths


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum_ms": ordered[0],
        "p50_ms": statistics.median(ordered),
        "p90_ms": ordered[max(0, int(0.9 * len(ordered)) - 1)],
        "maximum_ms": ordered[-1],
    }


def tensor_sha256(torch: Any, tensor: Any) -> str:
    value = tensor.detach().contiguous().view(torch.uint8)
    return hashlib.sha256(value.cpu().numpy().tobytes()).hexdigest()


def clone_outputs(outputs: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(value.detach().clone() for value in outputs)


def equality_row(
    torch: Any,
    case: str,
    reference: tuple[Any, ...],
    actual: tuple[Any, ...],
) -> dict[str, Any]:
    names = [
        "normalized_bf16",
        "activation_e4m3",
        "scale_fp32",
        "residual_out_bf16",
        "gate_up_bf16",
        "gelu_mul_bf16",
    ]
    fields = {}
    for name, expected, observed in zip(names, reference, actual):
        fields[name] = {
            "equal": bool(torch.equal(expected, observed)),
            "dtype_equal": expected.dtype == observed.dtype,
            "shape_equal": tuple(expected.shape) == tuple(observed.shape),
            "stride_equal": tuple(expected.stride()) == tuple(observed.stride()),
            "reference_sha256": tensor_sha256(torch, expected),
            "graph_sha256": tensor_sha256(torch, observed),
        }
    return {
        "case": case,
        "fields": fields,
        "pass": all(
            all(
                value[key]
                for key in ("equal", "dtype_equal", "shape_equal", "stride_equal")
            )
            for value in fields.values()
        ),
    }


def cuda_event_timings(
    torch: Any,
    prepare: Callable[[], None],
    call: Callable[[], Any],
    warmup: int,
    repeats: int,
) -> list[float]:
    for _ in range(warmup):
        prepare()
        call()
    torch.cuda.synchronize()
    values = []
    for _ in range(repeats):
        prepare()
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        call()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
    return values


def synchronized_wall_timings(
    torch: Any,
    prepare: Callable[[], None],
    call: Callable[[], Any],
    warmup: int,
    repeats: int,
) -> list[float]:
    for _ in range(warmup):
        prepare()
        call()
    torch.cuda.synchronize()
    values = []
    for _ in range(repeats):
        prepare()
        torch.cuda.synchronize()
        start = time.perf_counter_ns()
        call()
        torch.cuda.synchronize()
        values.append((time.perf_counter_ns() - start) / 1e6)
    return values


def run_target(output: Path, checkpoint: Path, warmup: int, repeats: int) -> int:
    verify_project_inputs()
    assert_source_trace()
    if output.exists():
        raise RuntimeError(f"fresh_output_required:{output}")
    output.mkdir(parents=True)
    state_path = output / "INVOCATION_STATE.json"
    state = {
        "schema_version": 1,
        "pre_science": True,
        "science_started": False,
        "direct_first_call_complete": False,
        "graph_first_call_complete": False,
        "timing_started": False,
    }
    atomic_json(state_path, state)

    import torch
    from safetensors import safe_open
    from sgl_kernel import fused_add_rmsnorm
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available():
        raise RuntimeError("target_sm120_cuda_unavailable")
    properties = torch.cuda.get_device_properties(0)
    if (properties.major, properties.minor) != (12, 0):
        raise RuntimeError(
            f"target_sm120_required:{properties.name}:"
            f"{properties.major}.{properties.minor}"
        )
    runtime_hashes, runtime_paths = verify_runtime_modules()
    shard = checkpoint / "layer0-rms-qkv-gate-up.safetensors"
    if sha256(shard) != EXPECTED_FILES[
        "inputs/component/layer0-rms-qkv-gate-up.safetensors"
    ]:
        raise RuntimeError("checkpoint_component_hash_mismatch")
    keys = {
        "pre_ff_norm": "model.language_model.layers.0.pre_feedforward_layernorm.weight",
        "gate": "model.language_model.layers.0.mlp.gate_proj.weight",
        "up": "model.language_model.layers.0.mlp.up_proj.weight",
    }
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        tensors = {name: handle.get_tensor(key) for name, key in keys.items()}
    norm_weight = tensors["pre_ff_norm"].cuda().contiguous()
    weight_bf16 = torch.cat([tensors["gate"], tensors["up"]], dim=0).cuda()
    weight_scale_column = (
        weight_bf16.float()
        .abs()
        .amax(dim=1, keepdim=True)
        .div(FP8_MAX)
        .clamp_min(1e-8)
        .float()
    )
    weight = (
        (weight_bf16 / weight_scale_column)
        .clamp(-FP8_MAX, FP8_MAX)
        .to(torch.float8_e4m3fn)
        .t()
    )
    weight_scale = weight_scale_column.t().contiguous()
    if tuple(weight.shape) != (K, N) or tuple(weight.stride()) != (1, K):
        raise RuntimeError(
            f"gate_up_layout_mismatch:{tuple(weight.shape)}:{tuple(weight.stride())}"
        )
    activation = GeluAndMul()

    def stock_body(hidden: Any, residual: Any) -> tuple[Any, ...]:
        fused_add_rmsnorm(hidden, residual, norm_weight, EPSILON)
        quantized, scale = sglang_per_token_quant_fp8(hidden)
        gate_up = fp8_scaled_mm(
            quantized,
            weight,
            scale,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )
        gelu_mul = activation(gate_up)
        return hidden, quantized, scale, residual, gate_up, gelu_mul

    generator = torch.Generator(device="cuda")
    generator.manual_seed(SEED)
    base_hidden = torch.randn(
        (M, K), device="cuda", dtype=torch.bfloat16, generator=generator
    )
    base_residual = torch.randn(
        (M, K), device="cuda", dtype=torch.bfloat16, generator=generator
    )
    cases = {
        "production_random": (base_hidden, base_residual),
        "zero_residual": (base_hidden, torch.zeros_like(base_residual)),
        "zero_post_attention": (torch.zeros_like(base_hidden), base_residual),
        "tiny_finite": (base_hidden * 2**-12, base_residual * 2**-12),
        "high_amplitude_finite": (base_hidden * 64, base_residual * 64),
    }

    static_hidden = base_hidden.clone()
    static_residual = base_residual.clone()
    direct_hidden = base_hidden.clone()
    direct_residual = base_residual.clone()
    state["science_started"] = True
    state["pre_science"] = False
    atomic_json(state_path, state)

    direct_first = stock_body(direct_hidden, direct_residual)
    torch.cuda.synchronize()
    state["direct_first_call_complete"] = True
    atomic_json(state_path, state)

    graph = torch.cuda.CUDAGraph()
    capture_stream = torch.cuda.Stream()
    capture_stream.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(capture_stream):
        static_hidden.copy_(base_hidden)
        static_residual.copy_(base_residual)
        graph_outputs = stock_body(static_hidden, static_residual)
    torch.cuda.current_stream().wait_stream(capture_stream)
    torch.cuda.synchronize()
    static_hidden.copy_(base_hidden)
    static_residual.copy_(base_residual)
    with torch.cuda.graph(graph, stream=capture_stream):
        graph_outputs = stock_body(static_hidden, static_residual)
    static_hidden.copy_(base_hidden)
    static_residual.copy_(base_residual)
    graph.replay()
    torch.cuda.synchronize()
    state["graph_first_call_complete"] = True
    atomic_json(state_path, state)

    oracle_rows = []
    for name, (hidden, residual) in cases.items():
        direct_hidden.copy_(hidden)
        direct_residual.copy_(residual)
        direct = stock_body(direct_hidden, direct_residual)
        torch.cuda.synchronize()
        direct = clone_outputs(direct)
        static_hidden.copy_(hidden)
        static_residual.copy_(residual)
        graph.replay()
        torch.cuda.synchronize()
        captured = clone_outputs(graph_outputs)
        row = equality_row(torch, name, direct, captured)
        oracle_rows.append(row)
        atomic_json(output / f"ORACLE_{name}.json", row)
    oracle_pass = all(row["pass"] for row in oracle_rows)
    if not oracle_pass:
        terminal = {
            "schema_version": 1,
            "classification": "bitwise_mismatch",
            "pass": False,
            "oracle_rows": oracle_rows,
            "timing_consumed": False,
        }
        atomic_json(output / "TERMINAL.json", terminal)
        return 20

    state["timing_started"] = True
    atomic_json(state_path, state)

    def prepare_direct() -> None:
        direct_hidden.copy_(base_hidden)
        direct_residual.copy_(base_residual)

    def prepare_graph() -> None:
        static_hidden.copy_(base_hidden)
        static_residual.copy_(base_residual)

    direct_device = cuda_event_timings(
        torch,
        prepare_direct,
        lambda: stock_body(direct_hidden, direct_residual),
        warmup,
        repeats,
    )
    graph_device = cuda_event_timings(
        torch, prepare_graph, graph.replay, warmup, repeats
    )
    direct_wall = synchronized_wall_timings(
        torch,
        prepare_direct,
        lambda: stock_body(direct_hidden, direct_residual),
        warmup,
        repeats,
    )
    graph_wall = synchronized_wall_timings(
        torch, prepare_graph, graph.replay, warmup, repeats
    )
    extension_hashes = {}
    package = importlib.import_module("sgl_kernel")
    for path in sorted(Path(package.__file__).resolve().parent.glob("*.so")):
        extension_hashes[str(path)] = sha256(path)
    terminal = {
        "schema_version": 1,
        "classification": "standalone_taskgraph_measured_not_endpoint_promotable",
        "pass": True,
        "hardware": {
            "name": properties.name,
            "compute_capability": [properties.major, properties.minor],
            "sms": properties.multi_processor_count,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
        },
        "runtime_source_hashes": runtime_hashes,
        "runtime_source_paths": runtime_paths,
        "extension_hashes": extension_hashes,
        "weight": {
            "shape": list(weight.shape),
            "stride": list(weight.stride()),
            "dtype": str(weight.dtype),
            "scale_shape": list(weight_scale.shape),
            "scale_dtype": str(weight_scale.dtype),
        },
        "oracle_rows": oracle_rows,
        "timing": {
            "unit": "milliseconds_per_hotblock_call",
            "warmup": warmup,
            "repeats": repeats,
            "direct_device": summarize(direct_device),
            "graph_device": summarize(graph_device),
            "direct_synchronized_wall": summarize(direct_wall),
            "graph_synchronized_wall": summarize(graph_wall),
        },
        "endpoint_transfer": {
            "allowed": False,
            "reason": "the production decode path already owns these nodes in one outer graph replay",
        },
    }
    atomic_json(output / "TERMINAL.json", terminal)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--export", type=Path)
    mode.add_argument("--run", type=Path)
    parser.add_argument(
        "--checkpoint", type=Path, default=PROJECT / "inputs/component"
    )
    parser.add_argument("--warmup", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=40)
    args = parser.parse_args()
    if args.warmup < 1 or args.repeats < 2:
        raise RuntimeError("warmup>=1 and repeats>=2 required")
    if args.describe:
        print(json.dumps(description(), indent=2, sort_keys=True))
        return 0
    if args.export is not None:
        atomic_json(args.export, description())
        return 0
    return run_target(args.run, args.checkpoint, args.warmup, args.repeats)


if __name__ == "__main__":
    raise SystemExit(main())
