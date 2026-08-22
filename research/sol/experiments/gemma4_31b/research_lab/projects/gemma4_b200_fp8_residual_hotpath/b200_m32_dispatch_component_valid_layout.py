#!/usr/bin/env python3
"""Exact-shape stock-versus-patched SM100 FP8 dispatch discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path

SHAPES = (("sliding_qkv", 5376, 16384, 50), ("sliding_o", 8192, 5376, 50),
          ("global_qkv_k_eq_v_materialized", 5376, 20480, 10),
          ("global_o", 16384, 5376, 10), ("gate_up", 5376, 43008, 60),
          ("down", 21504, 5376, 60))
M = 32
COSINE_MIN, NRMSE_MAX, MAX_ABS_MAX = 0.99999, 0.005, 0.01

def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    tmp.replace(path)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()

def timed(torch, fn, warmup: int, repeats: int) -> list[float]:
    for _ in range(warmup): fn()
    torch.cuda.synchronize(); values = []
    for _ in range(repeats):
        start, end = torch.cuda.Event(True), torch.cuda.Event(True)
        start.record(); fn(); end.record(); end.synchronize(); values.append(float(start.elapsed_time(end)))
    return values

def metrics(torch, actual, reference) -> dict[str, float | bool]:
    actual, reference = actual.float().flatten(), reference.float().flatten()
    diff = actual - reference; rmse = torch.sqrt(torch.mean(diff * diff)); rms = torch.sqrt(torch.mean(reference * reference)).clamp_min(1e-12)
    return {"finite": bool(torch.isfinite(actual).all()), "cosine": float(torch.nn.functional.cosine_similarity(actual, reference, dim=0)), "normalized_rmse": float(rmse / rms), "max_abs": float(diff.abs().max())}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--arm", choices=("stock", "patched"), required=True); parser.add_argument("--warmup", type=int, default=5); parser.add_argument("--repeats", type=int, default=15); parser.add_argument("--seed", type=int, default=20260728)
    args = parser.parse_args()
    if args.warmup < 2 or args.repeats < 5: raise ValueError("warmup>=2 and repeats>=5 required")
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    from vllm import _custom_ops as ops
    if not torch.cuda.is_available(): raise RuntimeError("cuda_unavailable")
    capability = torch.cuda.get_device_capability()
    if capability != (10, 0): raise RuntimeError(f"sm100_required:{capability}")
    import vllm
    custom_ops_path = Path(ops.__file__).resolve()
    extension_candidates = sorted(custom_ops_path.parent.glob("_C*.so"))
    if not extension_candidates:
        raise RuntimeError("vllm_custom_extension_missing")
    extension_path = extension_candidates[0]
    state = {"schema_version": 1, "arm": args.arm, "candidate_science_started": False, "first_shape": None, "vllm_python": str(Path(vllm.__file__).resolve()), "custom_ops_python": str(custom_ops_path), "custom_extension": str(extension_path), "custom_extension_sha256": sha256(extension_path)}
    atomic_json(args.output / "INVOCATION_STATE.json", state)
    rows = []
    for index, (name, k, n, multiplicity) in enumerate(SHAPES):
        torch.manual_seed(args.seed + index); torch.cuda.manual_seed_all(args.seed + index)
        x = torch.randn((M, k), device="cuda", dtype=torch.bfloat16) * 0.02
        weight_bf16 = torch.randn((n, k), device="cuda", dtype=torch.bfloat16) * 0.02
        weight, weight_scale = ops.scaled_fp8_quant(weight_bf16); weight = weight.t()
        x_quantized, x_scale = ops.scaled_fp8_quant(x)
        reference = x @ weight_bf16.t()
        def gemm_only(): return ops.cutlass_scaled_mm(x_quantized, weight, x_scale, weight_scale, out_dtype=torch.bfloat16)
        def quant_and_gemm():
            qx, sx = ops.scaled_fp8_quant(x)
            return ops.cutlass_scaled_mm(qx, weight, sx, weight_scale, out_dtype=torch.bfloat16)
        if not state["candidate_science_started"]:
            state["candidate_science_started"], state["first_shape"] = True, name
            atomic_json(args.output / "INVOCATION_STATE.json", state)
        output = gemm_only(); torch.cuda.synchronize(); numeric = metrics(torch, output, reference)
        if not (numeric["finite"] and numeric["cosine"] >= COSINE_MIN and numeric["normalized_rmse"] <= NRMSE_MAX and numeric["max_abs"] <= MAX_ABS_MAX): raise RuntimeError(f"numeric_guard_failed:{name}:{numeric}")
        gemm_ms, quant_ms = timed(torch, gemm_only, args.warmup, args.repeats), timed(torch, quant_and_gemm, args.warmup, args.repeats)
        row = {"name": name, "m": M, "k": k, "n": n, "multiplicity_per_decode_step": multiplicity, "gemm_ms": gemm_ms, "quant_and_gemm_ms": quant_ms, "gemm_p50_ms": statistics.median(gemm_ms), "quant_and_gemm_p50_ms": statistics.median(quant_ms), "numeric": numeric, "candidate_symbol": "cutlass_gemm_caller_sm100_fp8<Cutlass3xGemmM16SwapAB>" if args.arm == "patched" else "cutlass_gemm_sm100_fp8_dispatch:stock_runtime_selection"}
        rows.append(row); atomic_json(args.output / f"ROW_{name}.json", row)
        del x, weight_bf16, weight, weight_scale, x_quantized, x_scale, reference; torch.cuda.empty_cache()
    terminal = {"schema_version": 1, "classification": "component_arm_measurement", "arm": args.arm, "candidate_science_started": state["candidate_science_started"], "vllm_python": state["vllm_python"], "custom_ops_python": state["custom_ops_python"], "custom_extension": state["custom_extension"], "custom_extension_sha256": state["custom_extension_sha256"], "rows": rows, "weighted_quant_and_gemm_p50_ms": sum(r["multiplicity_per_decode_step"] * r["quant_and_gemm_p50_ms"] for r in rows), "weighted_gemm_p50_ms": sum(r["multiplicity_per_decode_step"] * r["gemm_p50_ms"] for r in rows), "runner_sha256": sha256(Path(__file__).resolve()), "stop_conditions": {"shape_regression_limit_fraction": 0.05, "weighted_gain_min_fraction": 0.10, "projected_endpoint_saving_min_per_request": 0.005, "correctness": {"cosine_min": COSINE_MIN, "normalized_rmse_max": NRMSE_MAX, "max_abs_max": MAX_ABS_MAX}}, "environment": {"device": torch.cuda.get_device_name(0), "compute_capability": list(capability), "torch": torch.__version__, "cuda_runtime": torch.version.cuda}, "measurement": "profiler_off_warm_cuda_events_p50_same_deterministic_tensors"}
    atomic_json(args.output / "TERMINAL.json", terminal); return 0

if __name__ == "__main__": raise SystemExit(main())
