#!/usr/bin/env python3
import argparse
import json
import math
import os
import time
from pathlib import Path

try:
    import torch
except ModuleNotFoundError:
    torch = None


def elapsed_ms(fn, repeats):
    for _ in range(2):
        fn()
    torch.cuda.synchronize()
    wall = time.perf_counter()
    start, end = torch.cuda.Event(True), torch.cuda.Event(True)
    start.record()
    for _ in range(repeats):
        fn()
    end.record(); end.synchronize()
    return {"cuda_event_ms": start.elapsed_time(end) / repeats, "wall_ms": (time.perf_counter() - wall) * 1000 / repeats}


def fp8_mm(a, w, sa, sw):
    return torch._scaled_mm(a, w.t(), scale_a=sa, scale_b=sw, out_dtype=torch.bfloat16, use_fast_accum=True)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def run_linear(name, m, k, n, seed, fp8=True):
    torch.manual_seed(seed + m + k + n)
    a = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    w = torch.randn((n, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    torch.cuda.reset_peak_memory_stats()
    ref = torch.mm(a, w.t())
    reference = elapsed_ms(lambda: torch.mm(a, w.t()), 5)
    row = {"name": name, "m": m, "k": k, "n": n, "reference_dtype": "bfloat16", "reference": reference}
    if fp8:
        scale_a = torch.tensor(448.0 / max(float(a.abs().max()), 1e-8), device="cuda")
        scale_w = torch.tensor(448.0 / max(float(w.abs().max()), 1e-8), device="cuda")
        a8 = (a * scale_a).to(torch.float8_e4m3fn)
        w8 = (w * scale_w).to(torch.float8_e4m3fn)
        out = fp8_mm(a8, w8, scale_a.reciprocal(), scale_w.reciprocal())
        error = (out.float() - ref.float()).abs()
        candidate = elapsed_ms(lambda: fp8_mm(a8, w8, scale_a.reciprocal(), scale_w.reciprocal()), 5)
        row.update({"candidate_dtype": "float8_e4m3fn", "candidate": candidate, "max_absolute_error": float(error.max()), "max_relative_error": float((error / ref.float().abs().clamp_min(1e-3)).max()), "finite": bool(torch.isfinite(out).all()), "kernel": "torch._scaled_mm", "pass": bool(torch.isfinite(out).all() and float(error.max()) <= 0.25)})
    else:
        row.update({"candidate_dtype": "bfloat16_retained", "candidate": reference, "max_absolute_error": 0.0, "max_relative_error": 0.0, "finite": True, "kernel": "torch.mm", "pass": True})
    row["memory"] = {"allocated": torch.cuda.memory_allocated(), "reserved": torch.cuda.memory_reserved(), "peak_allocated": torch.cuda.max_memory_allocated()}
    del a, w, ref
    torch.cuda.empty_cache()
    return row


def kv_kind(label, layers, tokens, heads, dimension, output, seed):
    torch.manual_seed(seed + tokens + heads + dimension)
    torch.cuda.reset_peak_memory_stats()
    cache = torch.empty((tokens, 2, heads, dimension), device="cuda", dtype=torch.float8_e4m3fn)
    scales = torch.empty((tokens, 2, heads, 1), device="cuda", dtype=torch.float32)
    rows = []
    for layer in range(layers):
        max_error, finite = 0.0, True
        for offset in range(0, tokens, 128):
            count = min(128, tokens - offset)
            source = torch.randn((count, 2, heads, dimension), device="cuda", dtype=torch.bfloat16) / math.sqrt(dimension)
            scale = (448.0 / source.abs().amax(dim=-1, keepdim=True).clamp_min(1e-8)).float()
            encoded = (source * scale).to(torch.float8_e4m3fn)
            cache[offset:offset + count].copy_(encoded)
            scales[offset:offset + count].copy_(scale)
            decoded = cache[offset:offset + count].float() * scales[offset:offset + count].reciprocal()
            error = (decoded - source.float()).abs().max()
            max_error = max(max_error, float(error))
            finite = finite and bool(torch.isfinite(decoded).all())
            del source, scale, encoded, decoded, error
        rows.append({"kind": label, "layer": layer, "shape": [tokens, 2, heads, dimension], "tile_tokens": 128, "cache_value_dtype": "float8_e4m3fn", "scale_dtype": "float32", "scale_shape": [tokens, 2, heads, 1], "scale_mode": "dynamic_per_token_head", "symbol": "torch.Tensor.copy_ and float8_e4m3fn conversion", "max_absolute_error": max_error, "finite": finite, "allocated": torch.cuda.memory_allocated(), "reserved": torch.cuda.memory_reserved(), "peak_allocated": torch.cuda.max_memory_allocated(), "pass": finite and max_error <= 0.25})
    atomic_json(output, {"kind": label, "rows": rows})
    del cache, scales
    torch.cuda.empty_cache()
    return rows


def kv_arm(seed, output_dir):
    rows = []
    rows += kv_kind("local_c8_1024", 50, 8 * 1024, 16, 256, output_dir / "kv-local-c8.json", seed)
    rows += kv_kind("global_c8_4214", 10, 8 * 4214, 4, 512, output_dir / "kv-global-c8-primary.json", seed)
    rows += kv_kind("global_c8_4572", 10, 8 * 4572, 4, 512, output_dir / "kv-global-c8-peak.json", seed)
    rows += kv_kind("global_c8_10000", 10, 8 * 10000, 4, 512, output_dir / "kv-global-c8-10k.json", seed)
    return rows


def self_test(path):
    primary = {"linear_cases": [{"name": "synthetic-primary", "pass": True}], "primary_fp8_pass": True}
    atomic_json(path / "primary-rows.json", primary)
    try:
        raise RuntimeError("injected_kv_failure")
    except RuntimeError:
        persisted = json.loads((path / "primary-rows.json").read_text())
    return persisted == primary


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--seed", type=int, required=True); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        return 0 if self_test(args.output.parent) else 1
    if torch is None:
        raise RuntimeError("CUDA consumer requires PyTorch in the pinned runtime image")
    cases = []
    for name, k, n in (("sliding_qkv", 5376, 12288), ("global_qkv", 5376, 6144), ("attention_output", 8192, 5376), ("mlp_gate_up", 5376, 21504), ("mlp_down", 21504, 5376)):
        for m in (1, 2, 4, 8, 4214): cases.append(run_linear(name, m, k, n, args.seed))
    cases.append(run_linear("tied_vocab", 1, 5376, 262144, args.seed, fp8=False))
    primary = all(row["pass"] for row in cases)
    primary_record = {"linear_cases": cases, "primary_fp8_pass": primary}
    atomic_json(args.output.parent / "primary-rows.json", primary_record)
    kv = kv_arm(args.seed, args.output.parent) if primary else []
    result = {"schema_version": 1, "kind": "gemma4_31b_l40s_exact_shape_fp8", "seed": args.seed, "device": torch.cuda.get_device_name(), "capability": torch.cuda.get_device_capability(), "warmup_iterations": 2, "timed_iterations": 5, "linear_cases": cases, "primary_fp8_pass": primary, "retained_kv_arm": {"triggered": primary, "rows": kv, "pass": bool(kv) and all(row["pass"] for row in kv)}, "sweep_pass": primary and (not kv or all(row["pass"] for row in kv))}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["sweep_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
