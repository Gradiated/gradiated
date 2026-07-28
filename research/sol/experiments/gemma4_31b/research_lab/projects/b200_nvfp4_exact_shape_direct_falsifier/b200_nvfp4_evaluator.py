#!/usr/bin/env python3
"""Checkpoint-free exact-shape B200 native-NVFP4 discovery evaluator."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

EXPECTED_MECHANISM_SHA256 = "0ced5b18806b14f6fd0070f00c52640af5e9764886fed46752da43028f8b1119"
EXPECTED_UPSTREAM_SHA256 = "667f935dceac3acba4bfd808b8c02ac7bcf5d525f2c044ee78cd291da5b1b80d"
EXPECTED_VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
EXPECTED_IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
MS = (8, 16, 32, 3679)
WARMUPS = 20
REPETITIONS = 50
L2_BYTES = 126 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def metrics(actual, reference) -> dict[str, float | bool]:
    import torch

    a = actual.float().reshape(-1)
    b = reference.float().reshape(-1)
    finite = bool(torch.isfinite(a).all() and torch.isfinite(b).all())
    nontrivial = bool(a.abs().max().item() > 0 and b.abs().max().item() > 0)
    cosine = float(torch.nn.functional.cosine_similarity(a, b, dim=0).item())
    nrmse = float(torch.sqrt(torch.mean((a - b) ** 2)).item() / max(torch.sqrt(torch.mean(b**2)).item(), 1e-12))
    return {"finite": finite, "nontrivial": nontrivial, "cosine": cosine, "normalized_rmse": nrmse}


def load_inputs(mechanism_path: Path, upstream_path: Path):
    mechanism_sha = sha256(mechanism_path)
    upstream_sha = sha256(upstream_path)
    if mechanism_sha != EXPECTED_MECHANISM_SHA256:
        raise RuntimeError(f"mechanism digest mismatch: {mechanism_sha}")
    if upstream_sha != EXPECTED_UPSTREAM_SHA256:
        raise RuntimeError(f"upstream benchmark digest mismatch: {upstream_sha}")
    mechanism = json.loads(mechanism_path.read_text())
    identities = mechanism["identities"]
    if identities["runtime_vllm_commit"] != EXPECTED_VLLM_COMMIT or identities["runtime_image"] != EXPECTED_IMAGE:
        raise RuntimeError("mechanism runtime identity mismatch")
    shapes = mechanism["exact_geometry_and_tiles"]["shapes"]
    expected = {"sliding_qkv", "global_qkv", "sliding_output", "global_output", "merged_gate_up", "down"}
    if {row["name"] for row in shapes} != expected or len(shapes) != 6:
        raise RuntimeError("mechanism does not contain the exact six-shape set")
    for row in shapes:
        if not all(int(row[key]) > 0 for key in ("k", "n", "multiplicity")):
            raise RuntimeError("invalid exact geometry")
    sys.path.insert(0, str(upstream_path.parent))
    spec = importlib.util.spec_from_file_location("pinned_benchmark_nvfp4_gemm", upstream_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned upstream benchmark")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return mechanism, shapes, module, mechanism_sha, upstream_sha


def runtime_source_hashes(mechanism: dict[str, object], upstream_path: Path) -> dict[str, object]:
    repository_root = upstream_path.parents[2]
    observed = []
    for expected in mechanism["source_trace"]["files"]:
        path = repository_root / expected["path"]
        digest = sha256(path) if path.is_file() else None
        observed.append({"path": expected["path"], "expected_sha256": expected["sha256"], "observed_sha256": digest, "available": digest is not None, "pass": digest is None or digest == expected["sha256"]})
    return {"repository_root": str(repository_root), "files": observed, "pass": all(row["pass"] for row in observed)}


def time_call(call, repetitions: int, eviction, cold: bool) -> tuple[list[float], list[float], float, object]:
    import torch

    cuda_ms: list[float] = []
    wall_ms: list[float] = []
    checksum = 0.0
    last = None
    for _ in range(repetitions):
        if cold:
            eviction.add_(1)
            torch.cuda.synchronize()
        start_event = torch.cuda.Event(enable_timing=True)
        end_event = torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall_start = time.perf_counter_ns()
        start_event.record()
        output = call()
        end_event.record()
        torch.cuda.synchronize()
        wall_end = time.perf_counter_ns()
        if not torch.isfinite(output).all() or output.numel() == 0 or output.abs().max().item() == 0:
            raise RuntimeError("a timed output was empty, zero, or nonfinite")
        checksum += float(output.float().sum().item())
        cuda_ms.append(float(start_event.elapsed_time(end_event)))
        wall_ms.append((wall_end - wall_start) / 1e6)
        last = output
    return cuda_ms, wall_ms, checksum, last


def time_paired(arms: dict[str, object], repetitions: int, eviction, cold: bool, seed: int):
    import torch

    samples = {name: {"cuda": [], "wall": [], "checksum": 0.0, "last": None} for name in arms}
    rng = random.Random(seed)
    for _ in range(repetitions):
        order = list(arms)
        rng.shuffle(order)
        for name in order:
            if cold:
                eviction.add_(1)
                torch.cuda.synchronize()
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            torch.cuda.synchronize()
            wall_start = time.perf_counter_ns()
            start_event.record()
            output = arms[name]()
            end_event.record()
            torch.cuda.synchronize()
            wall_end = time.perf_counter_ns()
            if not torch.isfinite(output).all() or output.numel() == 0 or output.abs().max().item() == 0:
                raise RuntimeError("a timed output was empty, zero, or nonfinite")
            samples[name]["cuda"].append(float(start_event.elapsed_time(end_event)))
            samples[name]["wall"].append((wall_end - wall_start) / 1e6)
            samples[name]["checksum"] += float(output.float().sum().item())
            samples[name]["last"] = output
    return samples


def summarize(cuda_ms: list[float], wall_ms: list[float], checksum: float) -> dict[str, object]:
    return {
        "cuda_event_ms": {"p50": statistics.median(cuda_ms), "p95": percentile(cuda_ms, 0.95), "min": min(cuda_ms), "max": max(cuda_ms)},
        "synchronized_wall_ms": {"p50": statistics.median(wall_ms), "p95": percentile(wall_ms, 0.95), "min": min(wall_ms), "max": max(wall_ms)},
        "repetitions": len(cuda_ms),
        "timed_output_checksum": checksum,
        "all_timed_outputs_consumed": True,
    }


def run_row(shape: dict[str, object], m: int, official, eviction, seed: int) -> dict[str, object]:
    import torch
    from vllm.model_executor.layers.quantization.utils.nvfp4_emulation_utils import dequantize_to_dtype, ref_nvfp4_quant

    name, k, n = str(shape["name"]), int(shape["k"]), int(shape["n"])
    torch.manual_seed(seed)
    a = torch.randn((m, k), device="cuda", dtype=torch.bfloat16)
    b = torch.randn((n, k), device="cuda", dtype=torch.bfloat16)
    cfg = {"no_a_quant": False, "enabled": True}
    call_counts = {"scaled_fp4_quant": 0, "cutlass_scaled_fp4_mm": 0}
    original_quant = official.ops.scaled_fp4_quant
    original_mm = official.ops.cutlass_scaled_fp4_mm
    def counted_quant(*args, **kwargs):
        call_counts["scaled_fp4_quant"] += 1
        return original_quant(*args, **kwargs)
    def counted_mm(*args, **kwargs):
        call_counts["cutlass_scaled_fp4_mm"] += 1
        return original_mm(*args, **kwargs)
    try:
        official.ops.scaled_fp4_quant = counted_quant
        official.ops.cutlass_scaled_fp4_mm = counted_mm
        discovery = official.build_nvfp4_runner(cfg, a, b, torch.bfloat16, "cuda")
        discovery_output = discovery()
        torch.cuda.synchronize()
        if not torch.isfinite(discovery_output).all() or discovery_output.numel() == 0:
            raise RuntimeError("actual-consumer discovery call produced invalid output")
    finally:
        official.ops.scaled_fp4_quant = original_quant
        official.ops.cutlass_scaled_fp4_mm = original_mm
    if min(call_counts.values()) < 1:
        raise RuntimeError(f"actual-consumer discovery call missed required operators: {call_counts}")
    del discovery, discovery_output
    nvfp4 = official.build_nvfp4_runner(cfg, a, b, torch.bfloat16, "cuda")
    closure = inspect.getclosurevars(nvfp4).nonlocals
    required_closure = {"a_global_scale", "alpha", "b_fp4", "scale_b_fp4"}
    if not required_closure.issubset(closure):
        raise RuntimeError(f"pinned build_nvfp4_runner closure changed: {sorted(closure)}")
    # Pinned build_nvfp4_runner defines alpha = 1 / (a_global_scale *
    # b_global_scale), so this is the exact observer-side inverse relation.
    a_global_scale = closure["a_global_scale"]
    alpha = closure["alpha"]
    b_global_scale = 1.0 / (alpha * a_global_scale)
    scales = torch.as_tensor([float(alpha), float(a_global_scale), float(b_global_scale)], device=a.device)
    if not torch.isfinite(scales).all() or (scales == 0).any():
        raise RuntimeError("pinned build_nvfp4_runner produced invalid alpha/global scales")
    bf16 = lambda: torch.nn.functional.linear(a, b)
    for _ in range(WARMUPS):
        if random.Random(seed + _).random() < 0.5:
            nvfp4(); bf16()
        else:
            bf16(); nvfp4()
    torch.cuda.synchronize()
    arms = {"nvfp4": nvfp4, "bf16": bf16}
    warm_samples = time_paired(arms, REPETITIONS, eviction, False, seed)
    cold_samples = time_paired(arms, REPETITIONS, eviction, True, seed + 1)
    warm = {name: summarize(row["cuda"], row["wall"], row["checksum"]) for name, row in warm_samples.items()}
    cold = {name: summarize(row["cuda"], row["wall"], row["checksum"]) for name, row in cold_samples.items()}
    last_nvfp4 = cold_samples["nvfp4"]["last"]
    assert last_nvfp4 is not None

    a_fp4, a_scale = ref_nvfp4_quant(a, a_global_scale, 16)
    a_dq = (a_fp4.reshape(m, k // 16, 16) * (a_scale.unsqueeze(-1) / a_global_scale)).reshape(m, k).to(torch.bfloat16)
    b_dq = dequantize_to_dtype(closure["b_fp4"], closure["scale_b_fp4"], b_global_scale, torch.bfloat16, a.device, 16)
    quantized_reference = torch.matmul(a_dq, b_dq.t())
    original_bf16 = torch.nn.functional.linear(a, b)
    kernel_oracle = metrics(last_nvfp4, quantized_reference)
    representation_oracle = metrics(quantized_reference, original_bf16)
    kernel_pass = kernel_oracle["finite"] and kernel_oracle["nontrivial"] and kernel_oracle["cosine"] >= 0.999 and kernel_oracle["normalized_rmse"] <= 0.03
    representation_pass = representation_oracle["finite"] and representation_oracle["nontrivial"] and representation_oracle["cosine"] >= 0.98 and representation_oracle["normalized_rmse"] <= 0.20
    del a, b, a_fp4, a_scale, a_dq, b_dq, quantized_reference, original_bf16, last_nvfp4
    torch.cuda.empty_cache()
    return {
        "name": name, "m": m, "k": k, "n": n, "multiplicity": int(shape["multiplicity"]),
        "warm": warm, "cold": cold,
        "kernel_oracle": {**kernel_oracle, "pass": bool(kernel_pass)},
        "representation_oracle": {**representation_oracle, "pass": bool(representation_pass)},
        "actual_call_chain": {"required": ["scaled_fp4_quant", "cutlass_scaled_fp4_mm"], "discovery_call_counts": call_counts, "pass": min(call_counts.values()) >= 1},
        "allocator": {"max_allocated_bytes": torch.cuda.max_memory_allocated(), "max_reserved_bytes": torch.cuda.max_memory_reserved()},
        "pass": bool(kernel_pass and representation_pass),
    }


def economic(rows: list[dict[str, object]], mechanism: dict[str, object]) -> dict[str, object]:
    by_m = {m: 0.0 for m in (8, 16, 32)}
    prefill = 0.0
    for row in rows:
        seconds = float(row["cold"]["nvfp4"]["cuda_event_ms"]["p50"]) / 1000
        if row["m"] in by_m:
            by_m[row["m"]] += seconds * int(row["multiplicity"]) * 358 / int(row["m"])
        elif row["m"] == 3679:
            prefill += seconds * int(row["multiplicity"])
    floors = {f"c{m}": by_m[m] + prefill for m in by_m}
    ceiling = float(mechanism["economic_screen"]["b200_equivalent_service_ceiling_seconds_per_request"])
    return {"linear_floor_seconds_per_request": floors, "prefill_seconds_once": prefill, "ceiling_seconds_per_request": ceiling, "any_below_ceiling": any(v < ceiling for v in floors.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mechanism", type=Path, required=True)
    parser.add_argument("--upstream-benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("sentinel", "sweep", "profile", "shape-contract"), default="sweep")
    parser.add_argument("--shape", choices=("sliding_qkv", "global_qkv", "sliding_output", "global_output", "merged_gate_up", "down"))
    parser.add_argument("--m", type=int, choices=MS)
    args = parser.parse_args()
    mechanism_sha = sha256(args.mechanism)
    upstream_sha = sha256(args.upstream_benchmark)
    mechanism = json.loads(args.mechanism.read_text())
    shapes = mechanism["exact_geometry_and_tiles"]["shapes"]
    if args.mode == "shape-contract":
        passed = mechanism_sha == EXPECTED_MECHANISM_SHA256 and upstream_sha == EXPECTED_UPSTREAM_SHA256 and len(shapes) == 6
        atomic_json(args.output, {"classification": "offline_exact_shape_contract", "pass": passed, "mechanism_sha256": mechanism_sha, "upstream_sha256": upstream_sha, "rows": [{"name": s["name"], "m": m, "k": s["k"], "n": s["n"], "multiplicity": s["multiplicity"]} for s in shapes for m in MS]})
        return 0 if passed else 2

    os.environ["VLLM_NVFP4_GEMM_BACKEND"] = "cutlass"
    import torch
    from vllm import __version__ as vllm_version
    from vllm import _custom_ops as ops
    from vllm.platforms import current_platform

    mechanism, shapes, official, mechanism_sha, upstream_sha = load_inputs(args.mechanism, args.upstream_benchmark)
    capability = torch.cuda.get_device_capability()
    compiled_cuda = torch._C._cuda_getCompiledVersion()
    source_hashes = runtime_source_hashes(mechanism, args.upstream_benchmark)
    identity = {
        "mechanism_sha256": mechanism_sha, "upstream_benchmark_sha256": upstream_sha,
        "expected_image": EXPECTED_IMAGE, "expected_vllm_commit": EXPECTED_VLLM_COMMIT,
        "observed_vllm_version": vllm_version, "device_name": torch.cuda.get_device_name(),
        "compute_capability": list(capability), "compiled_cuda": compiled_cuda,
        "runtime_cuda": torch.version.cuda,
        "cutlass_scaled_mm_supports_fp4": bool(ops.cutlass_scaled_mm_supports_fp4(100)),
        "current_platform_sm100": bool(current_platform.has_device_capability(100)),
        "source_hashes": source_hashes,
    }
    identity_pass = capability[0] == 10 and compiled_cuda >= 12080 and identity["cutlass_scaled_mm_supports_fp4"] and identity["current_platform_sm100"] and f"g{EXPECTED_VLLM_COMMIT[:9]}" in vllm_version and source_hashes["pass"]
    if not identity_pass:
        atomic_json(args.output, {"classification": "typed_b200_nvfp4_runtime_unsupported", "pass": False, "identity": identity})
        return 2
    eviction = torch.empty((3 * L2_BYTES // 4,), device="cuda", dtype=torch.float32)
    selected = [next(s for s in shapes if s["name"] == "sliding_qkv")]
    ms = (8,)
    if args.mode == "sweep":
        selected, ms = shapes, MS
    elif args.mode == "profile":
        if args.shape is None or args.m is None:
            parser.error("--mode profile requires --shape and --m")
        selected, ms = [next(s for s in shapes if s["name"] == args.shape)], (args.m,)
    rows: list[dict[str, object]] = []
    torch.cuda.reset_peak_memory_stats()
    for shape in selected:
        for m in ms:
            row = run_row(shape, m, official, eviction, 1701 + len(rows))
            rows.append(row)
            partial = {"classification": "b200_nvfp4_partial", "pass": False, "identity": identity, "rows": rows}
            atomic_json(args.output, partial)
            if not row["pass"]:
                partial["classification"] = "typed_b200_nvfp4_oracle_failure"
                atomic_json(args.output, partial)
                return 2
    classifications = {"sentinel": "b200_nvfp4_sentinel_pass", "profile": "b200_nvfp4_profile_row_pass", "sweep": "b200_nvfp4_exact_24_row_terminal"}
    result = {"classification": classifications[args.mode], "pass": True, "identity": identity, "rows": rows}
    if args.mode == "sweep":
        result["economics"] = economic(rows, mechanism)
        result["claim_boundary"] = "linear-component lower bound only; no endpoint or quality claim"
    atomic_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
