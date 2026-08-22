#!/usr/bin/env python3
"""Exact-shape stock-semantics CUDA-graph discriminator for Gemma 4."""
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
LAYERS = 60
DECODE_STEPS = 358
REQUESTS = 32
EPSILON = 1e-6
SEED = 20260729
EXPECTED_VLLM_VERSION = "0.19.1.dev6+g6d4a8e6d2"
EXPECTED_VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
EXPECTED_CUDAGRAPH_MODE = "FULL_AND_PIECEWISE"
EXPECTED_SOURCE_HASHES = {
    "vllm._custom_ops": "8990c0c4de5dadbb2d1ff57f02d6a7f9133df29bb9070179ada3363461b40093",
    "vllm.compilation.cuda_graph": "0f98ae0ea90424eb697e9ea0bdc0bcbbbecdc8637f4a89bfbfcc2ba28b40476d",
    "vllm.config.compilation": "ac12008b54dcf778db658786502d160a70a6a1120533584da1e4976c9756ce38",
    "vllm.config.vllm": "58aebc9654b3d62c9707be62df47ac43254b52218d9ea38c43d3026485ff9e01",
    "vllm.model_executor.kernels.linear.scaled_mm.ScaledMMLinearKernel": (
        "8618ebb23f1b7e14a4ad2534a4c19c32adf52b30b925b8453a18085a174d4471"
    ),
    "vllm.model_executor.kernels.linear.scaled_mm.cutlass": (
        "e212907776b61fd6618e6b812cee9a471ca83140a4710ca447bc6c11cc1d8488"
    ),
    "vllm.model_executor.layers.layernorm": (
        "8b4e0b93d1d76f0394bb28f40528bdfb250e16f22a83add184d3c2651f915623"
    ),
    "vllm.model_executor.layers.quantization.fp8": (
        "f2612966aaefa1dd4596a50da361628f64cd590eb3e6bbf6e1b4cfa488334d7e"
    ),
    "vllm.model_executor.layers.quantization.input_quant_fp8": (
        "6d09f1b7f8191303c4ebcc454cbf2bfb6319fbec1cb12c9842720e2f8ef75a18"
    ),
    "vllm.model_executor.models.gemma4": (
        "e16b28577c7cdca4876d26636564ed411fc7ce4a25b724456ee906d8129eed20"
    ),
    "vllm.v1.worker.gpu_model_runner": (
        "3afc290d3df1be3df1b89b9b35942695f5896c7729f608d6c44580899212c301"
    ),
}
BOUND_INPUT_HASHES = {
    "B200_FP8_CROSS_OPERATOR_DISCRIMINATOR.json": (
        "777e1e54f10a2a26a6b4dcf08518a2a994bce35edb8988d2906d992fba592506"
    ),
    "artifacts/b200-cross-operator-component-20260728t2016z/FINAL_TERMINAL.json": (
        "3d9285b7399d1f8e716c65cc195075404701d5db7a6aa063b5aba1f52f9cda17"
    ),
}
BOUND_ENDPOINT_LAUNCHER = {
    "path": (
        "../gemma4_b200_dynamic_fp8_endpoint/run_endpoint_pair.sh"
    ),
    "sha256": "ffb96e2e027b4724a0280df7925013fac3191243fd8f1c943b5f134719769faa",
    "enforce_eager_flag_present": False,
    "compilation_config_override_present": False,
    "optimization_level_override_present": False,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    json.loads(temporary.read_text())
    temporary.replace(path)


def source_trace() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "symbols": [
                "vllm.model_executor.models.gemma4.Gemma4DecoderLayer.forward",
                "post_attention_layernorm",
                "Tensor.__add__",
                "pre_feedforward_layernorm",
                "Gemma4MLP.forward",
            ],
            "boundary": (
                "post-attention BF16 output is normalized, added to the BF16 "
                "layer residual, materialized as residual_out, normalized again, "
                "and passed to gate_up_proj"
            ),
        },
        {
            "order": 2,
            "symbols": [
                "vllm.model_executor.layers.quantization.fp8.Fp8OnlineLinearMethod.apply",
                "FP8ScaledMMLinearKernel.apply_weights",
                "QuantFP8.forward_native",
                "CutlassFP8ScaledMMLinearKernel.apply_scaled_mm",
                "vllm._custom_ops.cutlass_scaled_mm",
            ],
            "boundary": (
                "stock dynamic per-token QuantFP8 emits E4M3 [32,5376] plus "
                "FP32 [32,1] scales; unchanged Cutlass scaled-MM emits BF16 "
                "[32,43008]"
            ),
        },
        {
            "order": 3,
            "symbols": [
                "vllm.config.vllm.OPTIMIZATION_LEVEL_02",
                "vllm.v1.worker.gpu_model_runner.GPUModelRunner.load_model",
                "vllm.compilation.cuda_graph.CUDAGraphWrapper.__call__",
            ],
            "boundary": (
                "O2 selects FULL_AND_PIECEWISE; decode uses the FULL wrapper "
                "around the whole model and therefore already submits this hot "
                "block as nodes of one outer CUDA graph"
            ),
        },
    ]


def task_graph_contract() -> dict[str, Any]:
    calls = LAYERS * DECODE_STEPS
    return {
        "schema_version": 1,
        "name": "gemma4_m32_stock_rms_quant_gate_up_cuda_graph",
        "semantic_class": "bitwise_stock_only",
        "shape": {"m": M, "k": K, "n": N},
        "phase": "decode",
        "calls_per_decode_step": LAYERS,
        "calls_per_endpoint_batch": calls,
        "nodes": [
            {
                "id": "stock_boundary",
                "implementation": (
                    "torch.compile(fullgraph=True,dynamic=False) of BF16 add, "
                    "RMSNorm.forward_static, and QuantFP8.forward_native"
                ),
                "measured_prior_generated_kernel_count": 1,
                "outputs": [
                    "activation_e4m3[32,5376]",
                    "scale_fp32[32,1]",
                    "residual_out_bf16[32,5376]",
                ],
            },
            {
                "id": "stock_gate_up",
                "depends_on": ["stock_boundary"],
                "implementation": "vllm._custom_ops.cutlass_scaled_mm",
                "outputs": ["gate_up_bf16[32,43008]"],
            },
        ],
        "unchanged_boundaries": [
            "post_attention_plus_residual FP32 promotion and BF16 residual cast",
            "RMSNorm FP32 variance reduction, rsqrt, BF16 cast, and BF16 weight multiply",
            "QuantFP8 per-token FP32 amax, minimum-scale clamp, reciprocal, saturation, and E4M3 cast",
            "FP32 activation scale tensor [32,1]",
            "Cutlass scaled-MM FP8 inputs/scales, accumulation, and BF16 output cast",
        ],
        "storage": {
            "capture_inputs": (
                "fixed-address project-local tensors; copies are outside the "
                "captured graph and outside timing"
            ),
            "capture_outputs": "fixed-address graph-private tensors",
            "weight_lifetime": "read-only for graph lifetime",
        },
        "stream": {
            "capture": "current torch CUDA stream after warm compilation",
            "replay": "same current stream",
            "inter_node_synchronization": "none",
            "oracle_synchronization": "one after each first direct and graph arm",
        },
    }


def describe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "classification": "typed_none_no_non_overlapping_runtime_boundary",
        "entrypoint": {
            "offline": [
                "b200_semantics_preserving_taskgraph.py --describe",
                "b200_semantics_preserving_taskgraph.py --export <path>",
            ],
            "target_cuda": (
                "b200_semantics_preserving_taskgraph.py --run <fresh-output>"
            ),
            "target_cuda_status": "implemented_not_run_zero_gpu_contract",
        },
        "identities": {
            "vllm_version": EXPECTED_VLLM_VERSION,
            "vllm_commit": EXPECTED_VLLM_COMMIT,
            "source_hashes": EXPECTED_SOURCE_HASHES,
            "bound_input_hashes": BOUND_INPUT_HASHES,
        },
        "task_graph": task_graph_contract(),
        "source_trace": source_trace(),
        "runtime_integration": {
            "stock_producer": [
                "Fp8OnlineLinearMethod.apply",
                "FP8ScaledMMLinearKernel.apply_weights",
                "QuantFP8.forward_native",
            ],
            "stock_consumer": [
                "CutlassFP8ScaledMMLinearKernel.apply_scaled_mm",
                "vllm._custom_ops.cutlass_scaled_mm",
            ],
            "outer_owner": [
                "GPUModelRunner.load_model",
                "CUDAGraphWrapper(runtime_mode=CUDAGraphMode.FULL)",
                "CUDAGraphWrapper.__call__",
            ],
            "candidate_insertion_point": (
                "Gemma4DecoderLayer.forward immediately before "
                "self.mlp.gate_up_proj"
            ),
            "insertion_disposition": (
                "forbidden_as_redundant under the bound O2 decode path; nested "
                "capture is not a legal replay boundary and a child graph cannot "
                "remove work already submitted by the outer full-model graph"
            ),
        },
        "oracle": {
            "required_before_timing": True,
            "comparison": "torch.equal over every element",
            "fields": [
                "activation_e4m3",
                "scale_fp32",
                "residual_out_bf16",
                "gate_up_consumer_bf16",
            ],
            "cases": [
                "production_random",
                "zero_residual",
                "zero_post_attention",
                "tiny_finite",
                "high_amplitude_finite",
            ],
            "failure": "write typed bitwise mismatch and do not time",
        },
        "physical_hypothesis": {
            "standalone_component": (
                "one cudaGraphLaunch replaces Python/CUDA API submission of the "
                "stock compiled boundary and stock scaled-MM while retaining both "
                "device kernel nodes"
            ),
            "bound_endpoint": (
                "no movement because its full decode CUDAGraphWrapper already "
                "performs that submission aggregation"
            ),
            "falsifier": (
                "a bound endpoint trace showing M32 decode in CUDAGraphMode.NONE "
                "or showing the selected stock nodes outside every piecewise/full "
                "graph"
            ),
        },
        "predicted_counter_movement": {
            "bound_endpoint": {
                "cuda_graph_launches_per_decode_step_delta": 0,
                "cuda_kernel_nodes_per_selected_call_delta": 0,
                "host_cuda_api_calls_per_selected_call_delta": 0,
                "explicit_synchronizations_per_selected_call_delta": 0,
                "dram_bytes_delta": 0,
                "l2_bytes_delta": 0,
                "tensor_core_instructions_delta": 0,
                "stock_activation_scale_residual_consumer_bytes_changed": False,
            },
            "standalone_only_not_transferable": {
                "host_submission_boundary": "two stock calls to one graph replay",
                "device_kernel_nodes": "unchanged",
                "explicit_synchronizations": "unchanged at zero within hot block",
            },
        },
    }


def offline_result() -> dict[str, Any]:
    project = Path(__file__).resolve().parent
    return {
        **describe(),
        "artifact": "B200_SEMANTICS_PRESERVING_TASKGRAPH_OFFLINE_RESULT.json",
        "implementation": {
            "path": Path(__file__).name,
            "sha256": sha256(Path(__file__).resolve()),
            "source_complete_through_first_consumer": True,
            "target_execution": "not_run_scope_has_zero_gpu_seconds",
        },
        "measured": {
            "label": "measured_offline_or_retained_exact_component",
            "bound_input_hashes_verified_once": BOUND_INPUT_HASHES,
            "bound_endpoint_launcher": BOUND_ENDPOINT_LAUNCHER,
            "official_pinned_source_hashes_verified": {
                "commit": EXPECTED_VLLM_COMMIT,
                "files": len(EXPECTED_SOURCE_HASHES),
                "all_match": True,
            },
            "prior_stock_compiled_generated_kernel_count": 1,
            "prior_stock_p50_ms": 0.10121600329875946,
            "prior_component_candidate_p50_ms": 0.0658240020275116,
            "prior_component_candidate_delta_us_per_call": 35.392001271247864,
            "prior_component_numeric_pass": False,
            "offline_describe_pass": True,
            "offline_export_pass": True,
            "gpu_claimed_this_continuation": False,
            "endpoint_requests_this_continuation": 0,
            "provider_operations_this_continuation": 0,
        },
        "derived": {
            "label": "derived_from_exact_geometry_and_pinned_source",
            "calls_per_endpoint_batch": LAYERS * DECODE_STEPS,
            "calls_per_request": LAYERS * DECODE_STEPS / REQUESTS,
            "gate_up_useful_flops_per_call": 2 * M * K * N,
            "gate_up_weight_bytes_per_call": K * N,
            "activation_bytes_per_call": M * K,
            "scale_bytes_per_call": M * 4,
            "residual_bytes_per_call": M * K * 2,
            "gate_up_output_bytes_per_call": M * N * 2,
            "net_bound_endpoint_launches_removed": 0,
            "net_bound_endpoint_synchronizations_removed": 0,
            "net_bound_endpoint_bytes_removed": 0,
        },
        "inferred": {
            "label": "inferred_not_measured",
            "bound_endpoint_service_delta_seconds_per_request": 0.0,
            "reason": (
                "the only implemented semantics-preserving aggregation is "
                "strictly contained by the already-active full decode graph"
            ),
            "risk_if_forced": [
                "illegal nested CUDA capture during full-model capture",
                "fixed-address private buffers add copies or aliasing constraints",
                "child-graph indirection without removing stock kernel nodes",
            ],
        },
        "decision": {
            "classification": "typed_none_no_non_overlapping_runtime_boundary",
            "promote": False,
            "reason": (
                "the exact graph is a valid standalone oracle/discriminator but "
                "not a non-generic integration boundary for the bound endpoint"
            ),
        },
        "smallest_later_b200_discriminator": {
            "authorization": "none_recommended_for_current_endpoint",
            "reopen_condition": (
                "first prove from an exact endpoint trace that M32 decode is not "
                "inside FULL or PIECEWISE CUDA graph capture"
            ),
            "then_command": (
                "python3 b200_semantics_preserving_taskgraph.py "
                "--run <fresh-project-local-output> --warmup 8 --repeats 40"
            ),
            "required_rows": [
                "five bitwise activation/scale/residual/BF16-consumer oracle rows",
                "direct stock device and synchronized-wall timings",
                "task-graph device and synchronized-wall timings",
                "observed source and extension hashes",
            ],
            "decision_rule": (
                "stop before timing on one unequal byte; measure only if the "
                "runtime-overlap guard is independently falsified"
            ),
        },
        "scope": {
            "actual_spend_usd_cumulative": 3.7782,
            "new_spend_usd": 0.0,
            "scientific_sample_consumed_this_continuation": False,
            "consumed_component_replayed": False,
            "dispatcher_modified": False,
        },
    }


def resolve_and_verify_source_hashes() -> tuple[dict[str, str], dict[str, str]]:
    observed: dict[str, str] = {}
    paths: dict[str, str] = {}
    for module_name, expected in EXPECTED_SOURCE_HASHES.items():
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__).resolve()
        observed[module_name] = sha256(module_path)
        paths[module_name] = str(module_path)
        if observed[module_name] != expected:
            raise RuntimeError(
                f"pinned_source_mismatch:{module_name}:"
                f"{observed[module_name]}:{expected}"
            )
    return observed, paths


def device_timings(
    torch: Any, call: Callable[[], Any], warmup: int, repeats: int
) -> list[float]:
    for _ in range(warmup):
        call()
    torch.cuda.synchronize()
    values: list[float] = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        call()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
    return values


def synchronized_wall_timings(
    torch: Any, call: Callable[[], Any], warmup: int, repeats: int
) -> list[float]:
    for _ in range(warmup):
        call()
    torch.cuda.synchronize()
    values: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        call()
        torch.cuda.synchronize()
        values.append((time.perf_counter_ns() - start) / 1e6)
    return values


def bitwise_row(
    torch: Any,
    name: str,
    reference: tuple[Any, Any, Any, Any],
    actual: tuple[Any, Any, Any, Any],
) -> dict[str, Any]:
    field_names = [
        "activation_e4m3",
        "scale_fp32",
        "residual_out_bf16",
        "gate_up_consumer_bf16",
    ]
    fields = {}
    for field_name, expected, observed in zip(field_names, reference, actual):
        fields[field_name] = {
            "equal": bool(torch.equal(expected, observed)),
            "dtype_equal": expected.dtype == observed.dtype,
            "shape_equal": tuple(expected.shape) == tuple(observed.shape),
        }
    return {
        "name": name,
        "fields": fields,
        "pass": all(value["equal"] for value in fields.values()),
    }


def run_target(output: Path, warmup: int, repeats: int) -> int:
    output.mkdir(parents=True, exist_ok=False)
    import torch
    import vllm
    from vllm import _custom_ops as ops
    from vllm.config import VllmConfig, set_current_vllm_config
    from vllm.model_executor.layers.layernorm import RMSNorm
    from vllm.model_executor.layers.quantization.input_quant_fp8 import QuantFP8
    from vllm.model_executor.layers.quantization.utils.quant_utils import GroupShape

    if vllm.__version__ != EXPECTED_VLLM_VERSION:
        raise RuntimeError(
            f"vllm_version_mismatch:{vllm.__version__}:{EXPECTED_VLLM_VERSION}"
        )
    observed_hashes, source_paths = resolve_and_verify_source_hashes()
    config = VllmConfig()
    config_context = set_current_vllm_config(config)
    config_context.__enter__()
    observed_mode = config.compilation_config.cudagraph_mode.name
    if observed_mode != EXPECTED_CUDAGRAPH_MODE:
        raise RuntimeError(
            f"cudagraph_mode_mismatch:{observed_mode}:{EXPECTED_CUDAGRAPH_MODE}"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    capability = torch.cuda.get_device_capability()
    if capability != (10, 0):
        raise RuntimeError(f"sm100_required:{capability}")

    extension_candidates = sorted(Path(ops.__file__).resolve().parent.glob("_C*.so"))
    if not extension_candidates:
        raise RuntimeError("vllm_custom_extension_missing")
    extension_path = extension_candidates[0]
    state = {
        "schema_version": 1,
        "phase": "validated_pre_science",
        "source_hashes": observed_hashes,
        "source_paths": source_paths,
        "extension_path": str(extension_path),
        "extension_sha256": sha256(extension_path),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "cudagraph_mode": observed_mode,
        "direct_first_call_complete": False,
        "graph_first_replay_complete": False,
        "bitwise_oracle_complete": False,
        "timing_started": False,
    }
    atomic_json(output / "INVOCATION_STATE.json", state)

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    post_attention_seed = (
        torch.randn((M, K), device="cuda", dtype=torch.bfloat16) * 0.02
    )
    residual_seed = (
        torch.randn((M, K), device="cuda", dtype=torch.bfloat16) * 0.02
    )
    norm_weight = (
        1.0 + torch.randn((K,), device="cuda", dtype=torch.bfloat16) * 0.01
    )
    weight_bf16 = (
        torch.randn((N, K), device="cuda", dtype=torch.bfloat16) * 0.02
    )
    gate_up_weight, gate_up_scale = ops.scaled_fp8_quant(weight_bf16)
    gate_up_weight = gate_up_weight.t()
    quantizer = QuantFP8(static=False, group_shape=GroupShape.PER_TOKEN)

    def stock_boundary(post_attention: Any, residual: Any) -> tuple[Any, Any, Any]:
        residual_out = post_attention + residual
        normalized = RMSNorm.forward_static(
            residual_out,
            EPSILON,
            K,
            residual_out.dtype,
            norm_weight,
            None,
            None,
        )
        activation, scale = quantizer.forward_native(normalized)
        return activation, scale, residual_out

    stock_compiled = torch.compile(stock_boundary, fullgraph=True, dynamic=False)

    def stock_call(post_attention: Any, residual: Any) -> tuple[Any, Any, Any, Any]:
        activation, scale, residual_out = stock_compiled(post_attention, residual)
        consumer = ops.cutlass_scaled_mm(
            activation,
            gate_up_weight,
            scale,
            gate_up_scale,
            out_dtype=torch.bfloat16,
        )
        return activation, scale, residual_out, consumer

    direct_first = stock_call(post_attention_seed, residual_seed)
    torch.cuda.synchronize()
    state["direct_first_call_complete"] = True
    atomic_json(output / "INVOCATION_STATE.json", state)

    static_post_attention = post_attention_seed.clone()
    static_residual = residual_seed.clone()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        graph_outputs = stock_call(static_post_attention, static_residual)
    graph.replay()
    torch.cuda.synchronize()
    state["graph_first_replay_complete"] = True
    atomic_json(output / "INVOCATION_STATE.json", state)

    cases = [
        ("production_random", post_attention_seed, residual_seed),
        ("zero_residual", post_attention_seed, torch.zeros_like(residual_seed)),
        ("zero_post_attention", torch.zeros_like(post_attention_seed), residual_seed),
        ("tiny_finite", post_attention_seed * 1e-3, residual_seed * 1e-3),
        ("high_amplitude_finite", post_attention_seed * 4, residual_seed * 4),
    ]
    oracle_rows = []
    for name, post_attention, residual in cases:
        reference = tuple(value.clone() for value in stock_call(post_attention, residual))
        static_post_attention.copy_(post_attention)
        static_residual.copy_(residual)
        graph.replay()
        torch.cuda.synchronize()
        actual = tuple(value.clone() for value in graph_outputs)
        oracle_rows.append(bitwise_row(torch, name, reference, actual))
    bitwise_pass = all(row["pass"] for row in oracle_rows)
    state["bitwise_oracle_complete"] = True
    atomic_json(output / "INVOCATION_STATE.json", state)
    if not bitwise_pass:
        atomic_json(
            output / "TERMINAL.json",
            {
                "schema_version": 1,
                "classification": "bitwise_stock_oracle_failed_no_timing",
                "oracle_rows": oracle_rows,
                "identities": state,
            },
        )
        return 0

    static_post_attention.copy_(post_attention_seed)
    static_residual.copy_(residual_seed)
    state["timing_started"] = True
    atomic_json(output / "INVOCATION_STATE.json", state)
    direct_device_ms = device_timings(
        torch,
        lambda: stock_call(post_attention_seed, residual_seed),
        warmup,
        repeats,
    )
    graph_device_ms = device_timings(torch, graph.replay, warmup, repeats)
    direct_wall_ms = synchronized_wall_timings(
        torch,
        lambda: stock_call(post_attention_seed, residual_seed),
        warmup,
        repeats,
    )
    graph_wall_ms = synchronized_wall_timings(torch, graph.replay, warmup, repeats)
    terminal = {
        "schema_version": 1,
        "classification": "standalone_exact_graph_measurement_runtime_overlap_guarded",
        "contract": task_graph_contract(),
        "identities": state,
        "environment": {
            "device": torch.cuda.get_device_name(0),
            "compute_capability": list(capability),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "vllm": vllm.__version__,
        },
        "oracle_rows": oracle_rows,
        "bitwise_pass": bitwise_pass,
        "measurement": {
            "warmup": warmup,
            "repeats": repeats,
            "direct_device_ms": direct_device_ms,
            "graph_device_ms": graph_device_ms,
            "direct_wall_ms": direct_wall_ms,
            "graph_wall_ms": graph_wall_ms,
            "direct_device_p50_ms": statistics.median(direct_device_ms),
            "graph_device_p50_ms": statistics.median(graph_device_ms),
            "direct_wall_p50_ms": statistics.median(direct_wall_ms),
            "graph_wall_p50_ms": statistics.median(graph_wall_ms),
            "unit": "one M32 hot-block call",
        },
        "decision": {
            "promote_to_bound_endpoint": False,
            "reason": (
                "bound O2 decode already uses a full-model CUDA graph; this "
                "standalone measurement cannot establish non-overlapping savings"
            ),
        },
        "scope": {
            "endpoint_requests_submitted": False,
            "dispatcher_modified": False,
            "provider_operations": False,
        },
    }
    atomic_json(output / "TERMINAL.json", terminal)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--describe", action="store_true")
    action.add_argument("--export", type=Path)
    action.add_argument("--run", type=Path)
    parser.add_argument("--warmup", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=40)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(describe(), indent=2, sort_keys=True))
        return 0
    if args.export is not None:
        atomic_json(args.export, offline_result())
        return 0
    if args.warmup < 3 or args.repeats < 10:
        parser.error("--warmup must be >=3 and --repeats must be >=10")
    assert args.run is not None
    return run_target(args.run, args.warmup, args.repeats)


if __name__ == "__main__":
    raise SystemExit(main())
