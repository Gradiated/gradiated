#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import pathlib
import statistics
import time
from typing import Any, Callable

import torch

import multistage_attention as candidate


PINNED_SOURCE_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def mark(path: pathlib.Path, **updates: Any) -> None:
    value = json.loads(path.read_text()) if path.exists() else {}
    value.update(updates)
    value["updated_unix_s"] = time.time()
    atomic_json(path, value)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_tensors(seed: int, tokens: int) -> dict[str, torch.Tensor]:
    torch.manual_seed(seed)
    device = torch.device("cuda")
    q = torch.randn((tokens, 32, 512), device=device, dtype=torch.bfloat16) / math.sqrt(512)
    k = torch.randn((tokens, 4, 512), device=device, dtype=torch.bfloat16) / math.sqrt(512)
    v = torch.randn((tokens, 4, 512), device=device, dtype=torch.bfloat16)
    fp8 = torch.float8_e5m2
    return {
        "q": q, "k": k, "v": v,
        "control_o": torch.empty_like(q), "candidate_o": torch.empty_like(q),
        "k_buffer": torch.zeros((1, 4, 512), device=device, dtype=fp8),
        "v_buffer": torch.zeros((1, 4, 512), device=device, dtype=fp8),
        "qo_indptr": torch.tensor([0, tokens], device=device, dtype=torch.int32),
        "kv_indptr": torch.tensor([0, 0], device=device, dtype=torch.int32),
        "kv_indices": torch.zeros((1,), device=device, dtype=torch.int64),
    }


def control_call(module: Any, tensors: dict[str, torch.Tensor]) -> None:
    module.extend_attention_fwd(
        tensors["q"], tensors["k"], tensors["v"], tensors["control_o"],
        tensors["k_buffer"], tensors["v_buffer"], tensors["qo_indptr"],
        tensors["kv_indptr"], tensors["kv_indices"], None, True, None,
        tensors["q"].shape[0], 1.0, 1.0, sliding_window_size=-1,
    )


def candidate_call(tensors: dict[str, torch.Tensor]) -> None:
    candidate.run(tensors["q"], tensors["k"], tensors["v"], tensors["candidate_o"])


def timed_ms(function: Callable[[], None]) -> float:
    start = torch.cuda.Event(enable_timing=True); end = torch.cuda.Event(enable_timing=True)
    start.record(); function(); end.record(); end.synchronize()
    return float(start.elapsed_time(end))


def summary(samples: list[float]) -> dict[str, Any]:
    return {"samples_ms": samples, "median_ms": statistics.median(samples), "minimum_ms": min(samples), "maximum_ms": max(samples)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--query-tokens", type=int, default=2048)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--promotion-threshold", type=float, default=0.05)
    parser.add_argument("--profile-candidate", action="store_true")
    args = parser.parse_args()
    if not torch.cuda.is_available() or tuple(torch.cuda.get_device_capability()) != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    if sha256(args.source) != PINNED_SOURCE_SHA256:
        raise RuntimeError("pinned_source_mismatch")
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_float32_matmul_precision("high")
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    terminal_path = args.artifact_root / "COMPONENT_TERMINAL.json"
    baseline = importlib.import_module("sglang.srt.layers.attention.triton_ops.extend_attention")
    if sha256(pathlib.Path(baseline.__file__).resolve()) != PINNED_SOURCE_SHA256:
        raise RuntimeError("loaded_baseline_source_mismatch")
    mark(invocation, discovery_cuda_invocation_started=False, candidate_cuda_invocation_started=False, scientific_invocation_started=False, source_sha256=PINNED_SOURCE_SHA256)
    smoke = make_tensors(args.seed, 64)
    mark(invocation, discovery_cuda_invocation_started=True)
    candidate_call(smoke); torch.cuda.synchronize()
    if not torch.isfinite(smoke["candidate_o"]).all().item():
        raise RuntimeError("multistage_discovery_nonfinite")
    mark(invocation, discovery_cuda_invocation_completed=True)
    del smoke
    tensors = make_tensors(args.seed, args.query_tokens)
    control_call(baseline, tensors); torch.cuda.synchronize()
    mark(invocation, candidate_cuda_invocation_started=True, scientific_invocation_started=True)
    candidate_call(tensors); torch.cuda.synchronize()
    delta = (tensors["candidate_o"].float() - tensors["control_o"].float()).abs()
    scale = tensors["control_o"].float().abs().clamp_min(1e-6)
    oracle = {
        "all_finite": bool(torch.isfinite(tensors["candidate_o"]).all().item()),
        "allclose_atol_0_005_rtol_0_005": bool(torch.allclose(tensors["candidate_o"].float(), tensors["control_o"].float(), atol=0.005, rtol=0.005)),
        "max_abs_error": float(delta.max().item()), "mean_abs_error": float(delta.mean().item()),
        "max_relative_error": float((delta / scale).max().item()),
        "output_l1": float(tensors["candidate_o"].float().abs().sum().item()),
    }
    for _ in range(args.warmups):
        control_call(baseline, tensors); candidate_call(tensors)
    torch.cuda.synchronize()
    control_samples: list[float] = []; candidate_samples: list[float] = []
    for index in range(args.iterations):
        order = ((lambda: control_call(baseline, tensors), control_samples), (lambda: candidate_call(tensors), candidate_samples))
        if index % 2: order = order[::-1]
        for function, samples in order: samples.append(timed_ms(function))
    control = summary(control_samples); measured = summary(candidate_samples)
    reduction = 1.0 - measured["median_ms"] / control["median_ms"]
    mechanism_pass = bool(oracle["all_finite"] and oracle["allclose_atol_0_005_rtol_0_005"] and oracle["output_l1"] > 0 and reduction >= args.promotion_threshold)
    if args.profile_candidate:
        probs, v_grouped = candidate.profile_inputs(tensors["q"], tensors["k"], tensors["v"])
        torch.cuda.synchronize(); mark(invocation, ncu_sliced_v_capture_started=True)
        torch.cuda.cudart().cudaProfilerStart()
        candidate.sliced_value_from_grouped(probs, v_grouped, tensors["candidate_o"])
        torch.cuda.synchronize(); torch.cuda.cudart().cudaProfilerStop()
        mark(invocation, ncu_sliced_v_capture_completed=True)
    device = torch.cuda.get_device_properties(0)
    terminal = {
        "schema_version": 1, "status": "component_pass" if mechanism_pass else "component_reject",
        "mechanism_pass": mechanism_pass, "promotion_threshold_fraction": args.promotion_threshold,
        "latency_reduction_fraction": reduction, "control": control, "candidate": measured, "oracle": oracle,
        "shape": {"query_tokens": args.query_tokens, "q_heads": 32, "kv_heads": 4, "qk_head_dim": 512, "v_head_dim": 512, "value_slices": 4, "value_slice_width": 128, "causal": True, "prefix_tokens": 0, "kv_cache_dtype": "fp8_e5m2"},
        "dataflow": {"stages": ["grouped_fp32_qk_gemm", "causal_fp32_softmax", "four_independent_fp32_v_gemms_width128", "concatenate_and_bf16_store"], "kernel_boundary_ends_value_accumulator_live_range": True, "temporary_memory": candidate.temporary_bytes(args.query_tokens)},
        "identity": {"baseline_source_sha256": PINNED_SOURCE_SHA256, "candidate_module_sha256": sha256(pathlib.Path(candidate.__file__).resolve()), "torch": torch.__version__, "seed": args.seed},
        "device": {"name": device.name, "capability": list(torch.cuda.get_device_capability()), "sm_count": device.multi_processor_count, "total_memory_bytes": device.total_memory},
        "candidate_path": "multistage.grouped_qk_softmax.sliced_v_4x128", "ncu_sliced_v_capture_requested": args.profile_candidate,
    }
    atomic_json(terminal_path, terminal); mark(invocation, scientific_terminal_recorded=True)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if mechanism_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
