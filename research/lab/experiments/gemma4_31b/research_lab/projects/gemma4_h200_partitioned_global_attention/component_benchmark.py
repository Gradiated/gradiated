#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import pathlib
import statistics
import time
from typing import Any

import torch

from forced_residency_attention import (
    PINNED_SOURCE_SHA256,
    transform_source,
    write_atomic,
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_candidate(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(
        "partitioned_global_extend_attention", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate_module_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def mark_invocation(path: pathlib.Path, **updates: Any) -> None:
    value: dict[str, Any] = {}
    if path.exists():
        value = json.loads(path.read_text())
    value.update(updates)
    value["updated_unix_s"] = time.time()
    atomic_json(path, value)


def call_kernel(module, tensors: dict[str, torch.Tensor]) -> None:
    module.extend_attention_fwd(
        tensors["q"],
        tensors["k"],
        tensors["v"],
        tensors["o"],
        tensors["k_buffer"],
        tensors["v_buffer"],
        tensors["qo_indptr"],
        tensors["kv_indptr"],
        tensors["kv_indices"],
        None,
        True,
        None,
        tensors["q"].shape[0],
        1.0,
        1.0,
        sliding_window_size=-1,
    )


def make_tensors(seed: int, query_tokens: int) -> dict[str, torch.Tensor]:
    torch.manual_seed(seed)
    device = torch.device("cuda")
    q = torch.randn(
        (query_tokens, 32, 512), device=device, dtype=torch.bfloat16
    ) / math.sqrt(512)
    k = torch.randn(
        (query_tokens, 4, 512), device=device, dtype=torch.bfloat16
    ) / math.sqrt(512)
    v = torch.randn(
        (query_tokens, 4, 512), device=device, dtype=torch.bfloat16
    )
    fp8 = getattr(torch, "float8_e5m2", None)
    if fp8 is None:
        raise RuntimeError("torch_float8_e5m2_unavailable")
    return {
        "q": q,
        "k": k,
        "v": v,
        "o": torch.empty_like(q),
        "k_buffer": torch.zeros((1, 4, 512), device=device, dtype=fp8),
        "v_buffer": torch.zeros((1, 4, 512), device=device, dtype=fp8),
        "qo_indptr": torch.tensor([0, query_tokens], device=device, dtype=torch.int32),
        "kv_indptr": torch.tensor([0, 0], device=device, dtype=torch.int32),
        "kv_indices": torch.zeros((1,), device=device, dtype=torch.int64),
    }


def timed_once_ms(module, tensors: dict[str, torch.Tensor]) -> float:
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    call_kernel(module, tensors)
    end.record()
    end.synchronize()
    return float(start.elapsed_time(end))


def summarize(samples: list[float]) -> dict[str, Any]:
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "minimum_ms": min(samples),
        "maximum_ms": max(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--query-tokens", type=int, default=2048)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=21)
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--promotion-threshold", type=float, default=0.05)
    parser.add_argument("--profile-candidate", action="store_true")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    if tuple(torch.cuda.get_device_capability()) != (9, 0):
        raise RuntimeError(
            f"wrong_cuda_capability:{torch.cuda.get_device_capability()}"
        )
    if sha256(args.source) != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"pinned_source_mismatch:{sha256(args.source)}")

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    terminal_path = args.artifact_root / "COMPONENT_TERMINAL.json"
    candidate_source = args.artifact_root / "candidate_forced_residency_attention.py"
    write_atomic(candidate_source, transform_source(args.source.read_bytes()))

    baseline = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    baseline_path = pathlib.Path(baseline.__file__).resolve()
    if sha256(baseline_path) != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"loaded_baseline_source_mismatch:{sha256(baseline_path)}")
    candidate = load_candidate(candidate_source)

    tensors = make_tensors(args.seed, args.query_tokens)
    control_output = torch.empty_like(tensors["o"])
    candidate_output = torch.empty_like(tensors["o"])

    mark_invocation(
        invocation_path,
        candidate_cuda_invocation_started=False,
        scientific_invocation_started=False,
        source_sha256=PINNED_SOURCE_SHA256,
    )
    call_kernel(baseline, tensors)
    torch.cuda.synchronize()
    control_output.copy_(tensors["o"])

    mark_invocation(
        invocation_path,
        candidate_cuda_invocation_started=True,
        scientific_invocation_started=True,
    )
    call_kernel(candidate, tensors)
    torch.cuda.synchronize()
    candidate_output.copy_(tensors["o"])

    delta = (candidate_output.float() - control_output.float()).abs()
    reference_scale = control_output.float().abs().clamp_min(1e-6)
    oracle = {
        "all_finite": bool(torch.isfinite(candidate_output).all().item()),
        "max_abs_error": float(delta.max().item()),
        "mean_abs_error": float(delta.mean().item()),
        "max_relative_error": float((delta / reference_scale).max().item()),
        "allclose_atol_0_005_rtol_0_005": bool(
            torch.allclose(
                candidate_output.float(),
                control_output.float(),
                atol=0.005,
                rtol=0.005,
            )
        ),
        "output_l1": float(candidate_output.float().abs().sum().item()),
    }

    for _ in range(args.warmups):
        call_kernel(baseline, tensors)
        call_kernel(candidate, tensors)
    torch.cuda.synchronize()

    control_samples = []
    candidate_samples = []
    for index in range(args.iterations):
        ordered = (
            ((baseline, control_samples), (candidate, candidate_samples))
            if index % 2 == 0
            else ((candidate, candidate_samples), (baseline, control_samples))
        )
        for module, samples in ordered:
            samples.append(timed_once_ms(module, tensors))
    control = summarize(control_samples)
    candidate_timing = summarize(candidate_samples)
    reduction = 1.0 - candidate_timing["median_ms"] / control["median_ms"]
    mechanism_pass = (
        oracle["all_finite"]
        and oracle["allclose_atol_0_005_rtol_0_005"]
        and oracle["output_l1"] > 0
        and reduction >= args.promotion_threshold
    )
    if args.profile_candidate:
        mark_invocation(invocation_path, ncu_candidate_capture_started=True)
        torch.cuda.cudart().cudaProfilerStart()
        call_kernel(candidate, tensors)
        torch.cuda.synchronize()
        torch.cuda.cudart().cudaProfilerStop()
        mark_invocation(invocation_path, ncu_candidate_capture_completed=True)
    device = torch.cuda.get_device_properties(0)
    terminal = {
        "schema_version": 1,
        "status": "component_pass" if mechanism_pass else "component_reject",
        "mechanism_pass": mechanism_pass,
        "promotion_threshold_fraction": args.promotion_threshold,
        "latency_reduction_fraction": reduction,
        "control": control,
        "candidate": candidate_timing,
        "oracle": oracle,
        "shape": {
            "query_tokens": args.query_tokens,
            "q_heads": 32,
            "kv_heads": 4,
            "qk_head_dim": 512,
            "v_head_dim": 512,
            "control_query_tile": 32,
            "key_tile": 64,
            "candidate_value_splits": 1,
            "candidate_value_slice": 512,
            "candidate_maxnreg": 128,
            "causal": True,
            "prefix_tokens": 0,
            "kv_cache_dtype": "fp8_e5m2",
        },
        "identity": {
            "baseline_source": str(args.source.resolve()),
            "baseline_source_sha256": PINNED_SOURCE_SHA256,
            "candidate_source_sha256": sha256(candidate_source),
            "torch": torch.__version__,
            "triton": importlib.import_module("triton").__version__,
            "seed": args.seed,
        },
        "device": {
            "name": device.name,
            "capability": list(torch.cuda.get_device_capability()),
            "sm_count": device.multi_processor_count,
            "total_memory_bytes": device.total_memory,
        },
        "candidate_path": "extend_attention_fwd.global_head512_maxnreg128",
        "ncu_candidate_capture_requested": args.profile_candidate,
    }
    atomic_json(terminal_path, terminal)
    mark_invocation(invocation_path, scientific_terminal_recorded=True)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if mechanism_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
